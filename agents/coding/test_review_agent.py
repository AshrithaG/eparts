"""
Test Review Agent — a quality step that runs late in the cycle and reviews the
TESTS, not the implementation.

Green tests are not the question; whether they would catch a real defect is.
This agent asks three things:
  1. Are happy paths AND sad/error paths both covered?
  2. Are the assertions meaningful — or is the test a smoke test, a tautology,
     or an assertion on a mock rather than on the value the system produced?
  3. Is the coverage number meaningful, or is it inflated by lines that were
     executed but never asserted on?

It exists because of a specific failure mode: build agents (and rushed humans)
tend to make tests pass rather than make code correct. Skipped tests, xfail
markers, commented-out assertions, and swallowed exceptions are the fingerprints
of that, and this agent looks for them directly.

It never edits tests or implementation, and never recommends weakening a test to
get green. Output is a review that a human engineer reads and acts on; nothing is
baselined without that human gate.

Runs AST-based static heuristics first (works with no API key), then asks the LLM
to confirm, refine, and extend those findings. With no LLM provider configured it
degrades to static-analysis-only and reports that limitation explicitly.

Triggered by: test_generator output, PR containing test changes, or a late-cycle
              quality sweep (cron / manual)
Outputs: test quality review (markdown) posted as a PR comment when a repo MCP
         client is available; always flagged requires_human_review
"""

from __future__ import annotations

import ast
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.test_review_agent")

# A test whose name contains one of these is claiming to cover a sad path.
SAD_PATH_NAME_HINTS = (
    "invalid", "error", "fail", "failure", "raise", "raises", "missing",
    "empty", "none", "null", "negative", "bad", "malformed", "corrupt",
    "timeout", "unauthorized", "forbidden", "duplicate", "conflict",
    "not_found", "notfound", "boundary", "edge", "overflow", "zero",
    "unavailable", "reject", "denied", "exception", "wrong", "mismatch",
)

# Attribute names that mean "I asserted on the mock, not on the result".
MOCK_ASSERT_PREFIXES = ("assert_called", "assert_any_call", "assert_has_calls",
                        "assert_not_called", "assert_awaited", "assert_not_awaited")
MOCK_ATTRS = {"called", "call_count", "call_args", "call_args_list", "await_count"}

# Coverage below this is reported as thin regardless of assertion quality.
LOW_COVERAGE_THRESHOLD = 60.0
# Coverage at or above this, combined with weak assertions, means "misleading".
HIGH_COVERAGE_THRESHOLD = 80.0
# Fraction of tests that may lack real assertions before coverage is suspect.
UNASSERTED_TEST_TOLERANCE = 0.25

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

VERDICT_ORDER = {"MEANINGFUL": 0, "GAPS_FOUND": 1, "COVERAGE_MISLEADING": 2}

CATEGORIES = {
    "MISSING_HAPPY_PATH", "MISSING_SAD_PATH", "WEAK_ASSERTION", "NO_ASSERTION",
    "MOCK_ONLY_ASSERTION", "TAUTOLOGY", "OVER_MOCKING", "SUPPRESSED_FAILURE",
    "GAMED_COVERAGE",
}

NO_LLM_NOTICE = (
    "No LLM provider configured (set GEMINI_API_KEY or ANTHROPIC_API_KEY in .env). "
    "Ran in static-analysis-only mode: assertion structure, sad-path signals and "
    "coverage arithmetic were checked, but semantic gaps (whether the assertions "
    "check the RIGHT thing for this domain) were not assessed."
)


class TestReviewAgent(BaseAgent):
    """
    Reviews test suites for happy/sad path balance, assertion strength, and
    whether reported coverage is meaningful. Advisory only — never edits code.
    """

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="test_review_agent", mcp_clients=mcp_clients)

    # ------------------------------------------------------------------ run

    def run(self, trigger: AgentTrigger) -> AgentResult:
        module_name = trigger.metadata.get("module_name", "") or trigger.source
        test_files = self._collect_test_files(trigger)
        implementation = self._collect_implementation(trigger)
        coverage_percent, coverage_note = self._parse_coverage(trigger)

        if not test_files:
            return AgentResult(
                agent=self.name, success=True,
                outputs=[AgentOutput(
                    output_type="test_review_skipped",
                    description=(
                        "No test code provided. Note that 'no tests supplied' is not "
                        "the same as 'no tests needed' — if this module has no tests "
                        "at all, that is itself the finding."
                    ),
                    reference=module_name,
                )],
                data={"module_name": module_name, "test_files": []},
            )

        errors: list[str] = []
        metrics, static_findings = self._analyze_static(
            test_files, implementation, coverage_percent
        )

        llm_review: dict[str, Any] | None = None
        if self._settings.has_llm:
            llm_review = self._review_with_llm(
                test_files, implementation, module_name,
                coverage_percent, coverage_note, static_findings,
            )
            if llm_review is None:
                errors.append(
                    "LLM test review returned no usable output; falling back to "
                    "static analysis results only."
                )
        else:
            errors.append(NO_LLM_NOTICE)

        llm_findings = (llm_review or {}).get("findings", [])
        findings = self._merge_findings(static_findings, llm_findings)

        verdict = self._verdict(metrics, findings, coverage_percent)
        llm_verdict = str((llm_review or {}).get("verdict", "")).upper()
        if llm_verdict in VERDICT_ORDER and VERDICT_ORDER[llm_verdict] > VERDICT_ORDER[verdict]:
            verdict = llm_verdict

        coverage_assessment = (
            str((llm_review or {}).get("coverage_assessment", "")).strip()
            or self._coverage_assessment(metrics, coverage_percent, coverage_note)
        )
        missing_sad_paths = [
            str(item) for item in (llm_review or {}).get("missing_sad_paths", [])
            if str(item).strip()
        ]
        questions = [
            str(item) for item in (llm_review or {}).get("questions_for_human", [])
            if str(item).strip()
        ]

        review_md = self._format_review(
            module_name=module_name, test_files=test_files, metrics=metrics,
            findings=findings, verdict=verdict,
            summary=str((llm_review or {}).get("summary", "")).strip(),
            coverage_assessment=coverage_assessment,
            missing_sad_paths=missing_sad_paths,
            questions=questions, errors=errors,
        )

        outputs = self._publish(trigger, module_name, review_md, verdict, findings)

        self._record_to_wiki(module_name, verdict, metrics, findings)
        self.emit("tests_reviewed", {
            "module_name": module_name,
            "verdict": verdict,
            "findings_count": len(findings),
            "test_count": metrics["test_count"],
            "sad_path_tests": metrics["sad_path_tests"],
            "tests_without_real_assertions": metrics["tests_without_real_assertions"],
            "coverage_percent": coverage_percent,
        }, pipeline="coding")

        return AgentResult(
            agent=self.name,
            success=True,
            outputs=outputs,
            errors=errors,
            requires_human_review=True,
            review_items=[
                {
                    "type": "test_quality_finding",
                    "finding_id": f.get("id", ""),
                    "category": f.get("category", ""),
                    "severity": f.get("severity", "medium"),
                    "test_name": f.get("test_name", "(none)"),
                    "message": (
                        f"[{f.get('severity', 'medium')}] {f.get('category', '?')} "
                        f"in {f.get('test_name', '(none)')}: "
                        f"{str(f.get('problem', ''))[:160]}"
                    ),
                    "recommendation": f.get("recommendation", ""),
                }
                for f in findings
            ],
            data={
                "module_name": module_name,
                "verdict": verdict,
                "metrics": metrics,
                "findings": findings,
                "findings_count": len(findings),
                "missing_sad_paths": missing_sad_paths,
                "questions_for_human": questions,
                "coverage_percent": coverage_percent,
                "coverage_assessment": coverage_assessment,
                "review_markdown": review_md,
                "auto_applied": False,
            },
        )

    # -------------------------------------------------------------- inputs

    def _collect_test_files(self, trigger: AgentTrigger) -> dict[str, str]:
        """Normalize the shapes callers use into {path: test source}."""
        meta = trigger.metadata
        files: dict[str, str] = {}

        candidates = meta.get("test_files") or {}
        if not candidates:
            pipeline_ctx = meta.get("pipeline_context", {})
            if isinstance(pipeline_ctx, dict):
                candidates = pipeline_ctx.get("test_files") or {}

        if isinstance(candidates, dict):
            for path, content in candidates.items():
                if isinstance(content, str) and content.strip():
                    files[str(path)] = content
        elif isinstance(candidates, list):
            for entry in candidates:
                if isinstance(entry, dict):
                    path = entry.get("path") or entry.get("file_path")
                    content = entry.get("content") or entry.get("test_code")
                    if path and isinstance(content, str) and content.strip():
                        files[str(path)] = content

        # A generic `files` dict may contain both tests and implementation.
        generic = meta.get("files") or {}
        if isinstance(generic, dict):
            for path, content in generic.items():
                if not isinstance(content, str) or not content.strip():
                    continue
                if self._looks_like_tests(str(path)):
                    files[str(path)] = content

        test_code = meta.get("test_code") or meta.get("tests")
        if isinstance(test_code, str) and test_code.strip():
            path = meta.get("test_file_path")
            if not path:
                base = (meta.get("module_name") or "module").replace("/", "_")
                base = base[:-3] if base.endswith(".py") else base
                path = f"tests/test_{base}.py"
            files.setdefault(str(path), test_code)

        return files

    def _looks_like_tests(self, path: str) -> bool:
        name = path.split("/")[-1]
        return (
            path.startswith("tests/") or "/tests/" in path
            or name.startswith("test_") or name.endswith("_test.py")
            or name == "conftest.py"
        )

    def _collect_implementation(self, trigger: AgentTrigger) -> dict[str, str]:
        """Implementation is reference context only — this agent reviews tests."""
        meta = trigger.metadata
        impl: dict[str, str] = {}

        generic = meta.get("files") or {}
        if isinstance(generic, dict):
            for path, content in generic.items():
                if isinstance(content, str) and content.strip() and not self._looks_like_tests(str(path)):
                    impl[str(path)] = content

        source_code = meta.get("source_code") or meta.get("implementation_code")
        if isinstance(source_code, str) and source_code.strip():
            path = meta.get("file_path") or meta.get("module_name") or "module.py"
            if not str(path).endswith(".py"):
                path = f"{path}.py"
            impl.setdefault(str(path), source_code)

        return impl

    def _parse_coverage(self, trigger: AgentTrigger) -> tuple[float | None, str]:
        """
        Pull a line-coverage percentage out of whatever the caller supplied:
        a number, a coverage.py JSON dict, a Cobertura-ish dict, or report text.
        Returns (percent or None, human-readable note).
        """
        raw = trigger.metadata.get("coverage")
        if raw is None:
            raw = trigger.metadata.get("coverage_report")
        if raw is None:
            raw = trigger.metadata.get("coverage_percent")
        if raw is None:
            return None, "No coverage data was supplied with this review."

        if isinstance(raw, bool):
            return None, "Coverage field was a boolean, not a measurement."

        if isinstance(raw, (int, float)):
            percent = float(raw)
            if 0.0 <= percent <= 1.0:
                percent *= 100.0
            return percent, f"Reported line coverage: {percent:.1f}%."

        if isinstance(raw, dict):
            totals = raw.get("totals") if isinstance(raw.get("totals"), dict) else raw
            for key in ("percent_covered", "line_rate", "line_coverage",
                        "coverage_percent", "percent", "lines_percent"):
                value = totals.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    percent = float(value)
                    if 0.0 <= percent <= 1.0:
                        percent *= 100.0
                    note = f"Reported line coverage: {percent:.1f}% (from {key})."
                    covered = totals.get("covered_lines")
                    statements = totals.get("num_statements") or totals.get("total_lines")
                    if isinstance(covered, int) and isinstance(statements, int) and statements:
                        note += f" {covered}/{statements} statements executed."
                    return percent, note
            return None, "Coverage dict supplied but no recognizable percentage field."

        if isinstance(raw, str):
            match = re.search(r"TOTAL\D+(\d+(?:\.\d+)?)\s*%", raw)
            if not match:
                match = re.search(r"(\d+(?:\.\d+)?)\s*%", raw)
            if match:
                percent = float(match.group(1))
                return percent, f"Reported line coverage: {percent:.1f}% (parsed from report text)."
            return None, "Coverage text supplied but no percentage could be parsed from it."

        return None, "Coverage data was in an unrecognized format."

    # ------------------------------------------------------- static analysis

    def _analyze_static(
        self, test_files: dict[str, str], implementation: dict[str, str],
        coverage_percent: float | None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """AST + text heuristics over the test suite. Works with no API key."""
        findings: list[dict[str, Any]] = []
        test_records: list[dict[str, Any]] = []

        for path, source in test_files.items():
            try:
                tree = ast.parse(source)
            except SyntaxError as exc:
                findings.append(self._finding(
                    category="SUPPRESSED_FAILURE", test_name=f"{path} (whole file)",
                    severity="high",
                    problem=f"Test file does not parse: {exc.msg} (line {exc.lineno}).",
                    recommendation="Fix the syntax error; an unparseable test file cannot be running.",
                    would_catch="Everything — a file that does not import runs zero tests.",
                ))
                continue

            findings.extend(self._find_commented_assertions(path, source))
            for node, class_name in self._iter_test_functions(tree):
                record = self._analyze_test_function(path, node, class_name)
                test_records.append(record)
                findings.extend(record["findings"])

        metrics = self._build_metrics(test_records, coverage_percent)
        findings.extend(self._suite_level_findings(metrics, test_records))
        findings.extend(self._untested_public_functions(implementation, test_files))
        return metrics, findings

    def _iter_test_functions(self, tree: ast.Module):
        """Yield (function_node, enclosing_class_name_or_None) for every test."""
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test"):
                    yield node, None
            elif isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                            and child.name.startswith("test"):
                        yield child, node.name

    def _analyze_test_function(
        self, path: str, node: ast.FunctionDef | ast.AsyncFunctionDef,
        class_name: str | None,
    ) -> dict[str, Any]:
        """Classify one test: assertion strength, happy/sad path, suppression."""
        display = f"{class_name}.{node.name}" if class_name else node.name
        qualified = f"{path}::{display}"

        real_assertions = 0
        mock_assertions = 0
        tautologies: list[str] = []
        truthiness_only = 0
        not_none_only = 0
        raises_contexts = 0
        findings: list[dict[str, Any]] = []

        for child in ast.walk(node):
            if isinstance(child, ast.Assert):
                kind = self._classify_assert(child)
                if kind == "tautology":
                    tautologies.append(ast.dump(child.test)[:80])
                elif kind == "mock":
                    mock_assertions += 1
                elif kind == "truthiness":
                    truthiness_only += 1
                elif kind == "not_none":
                    not_none_only += 1
                else:
                    real_assertions += 1

            elif isinstance(child, ast.Call):
                func = child.func
                if isinstance(func, ast.Attribute):
                    attr = func.attr
                    if attr.startswith(MOCK_ASSERT_PREFIXES):
                        mock_assertions += 1
                    elif attr == "assertTrue" and self._is_constant_arg(child):
                        tautologies.append("assertTrue(<constant>)")
                    elif attr.startswith("assertRaises") or attr.startswith("assertWarns"):
                        raises_contexts += 1
                        real_assertions += 1
                    elif attr.startswith("assert"):
                        real_assertions += 1
                    elif self._is_pytest_raises(func):
                        raises_contexts += 1
                        real_assertions += 1

        skip_marker = self._skip_marker(node)
        swallowed = self._swallows_failure(node)
        name_lower = display.lower()
        sad_by_name = any(hint in name_lower for hint in SAD_PATH_NAME_HINTS)
        is_sad_path = bool(raises_contexts) or sad_by_name

        total_assertion_like = real_assertions + mock_assertions + len(tautologies) \
            + truthiness_only + not_none_only

        if total_assertion_like == 0:
            findings.append(self._finding(
                category="NO_ASSERTION", test_name=qualified, severity="high",
                problem=(
                    f"{display} contains no assertion of any kind. It only proves the "
                    "code under test did not raise — it cannot fail for a wrong result."
                ),
                recommendation=(
                    "Assert on the actual value the function returns (or the state it "
                    "changes), not merely that it ran."
                ),
                would_catch="Any defect that produces a wrong-but-non-crashing result.",
            ))
        elif real_assertions == 0 and mock_assertions > 0:
            findings.append(self._finding(
                category="MOCK_ONLY_ASSERTION", test_name=qualified, severity="high",
                problem=(
                    f"{display} asserts only on mocks ({mock_assertions} mock "
                    "assertion(s), 0 assertions on real values). It verifies that the "
                    "test's own stubs were called, not that the system produced the "
                    "right output."
                ),
                recommendation=(
                    "Keep the call-verification if the interaction matters, but add at "
                    "least one assertion on the value returned to the caller or the "
                    "state left behind."
                ),
                would_catch=(
                    "A defect where the right collaborators are called but the result is "
                    "assembled incorrectly."
                ),
            ))

        if tautologies:
            findings.append(self._finding(
                category="TAUTOLOGY", test_name=qualified, severity="high",
                problem=(
                    f"{display} contains {len(tautologies)} assertion(s) that cannot "
                    "fail (e.g. `assert True`). This is a placeholder, not a test, and it "
                    "still counts toward coverage."
                ),
                recommendation=(
                    "Replace with an assertion on real behavior, or delete the test and "
                    "record the gap — a permanently-passing test is worse than a missing one."
                ),
                would_catch="Nothing today; it is pure coverage inflation.",
            ))

        if real_assertions == 0 and (truthiness_only or not_none_only):
            detail = "truthiness-only" if truthiness_only else "is-not-None-only"
            findings.append(self._finding(
                category="WEAK_ASSERTION", test_name=qualified, severity="medium",
                problem=(
                    f"{display}'s only assertions are {detail} checks, so any non-empty "
                    "value passes regardless of whether it is correct."
                ),
                recommendation=(
                    "Assert the expected value, shape, or specific fields — for eParts "
                    "that usually means the extracted attribute values and their "
                    "confidence scores, not just that something came back."
                ),
                would_catch="A defect that returns a well-formed but wrong result.",
            ))

        if skip_marker:
            findings.append(self._finding(
                category="SUPPRESSED_FAILURE", test_name=qualified, severity="high",
                problem=(
                    f"{display} is marked {skip_marker}, so it does not run. Skips and "
                    "xfails are the usual way a failing test gets made 'green' instead of "
                    "the code getting fixed."
                ),
                recommendation=(
                    "Either fix the code under test and unskip, or delete the test and "
                    "log the gap explicitly so it is visible to the team."
                ),
                would_catch="Whatever it was written to catch — currently nothing.",
            ))

        if swallowed:
            findings.append(self._finding(
                category="SUPPRESSED_FAILURE", test_name=qualified, severity="high",
                problem=(
                    f"{display} wraps its body in try/except with a bare pass or "
                    "equivalent, so a real failure inside is silently discarded and the "
                    "test passes anyway."
                ),
                recommendation=(
                    "Remove the exception swallowing. If an exception is the expected "
                    "outcome, assert it with pytest.raises instead."
                ),
                would_catch="Any exception the code under test raises.",
            ))

        return {
            "name": display,
            "qualified": qualified,
            "file": path,
            "real_assertions": real_assertions,
            "mock_assertions": mock_assertions,
            "tautologies": len(tautologies),
            "truthiness_only": truthiness_only,
            "not_none_only": not_none_only,
            "raises_contexts": raises_contexts,
            "is_sad_path": is_sad_path,
            "skipped": bool(skip_marker),
            "swallows_failure": swallowed,
            "findings": findings,
        }

    def _classify_assert(self, node: ast.Assert) -> str:
        """One of: real | tautology | mock | truthiness | not_none."""
        test = node.test

        if isinstance(test, ast.Constant):
            return "tautology"

        if isinstance(test, ast.Compare):
            operands = [test.left] + list(test.comparators)
            if all(isinstance(o, ast.Constant) for o in operands):
                return "tautology"
            is_none_cmp = any(
                isinstance(op, (ast.Is, ast.IsNot)) for op in test.ops
            ) and any(
                isinstance(o, ast.Constant) and o.value is None for o in operands
            )
            if is_none_cmp and len(test.ops) == 1:
                return "not_none"
            return "real"

        if isinstance(test, ast.Attribute):
            if test.attr in MOCK_ATTRS or "mock" in self._root_name(test).lower():
                return "mock"
            return "truthiness"

        if isinstance(test, ast.Name):
            return "truthiness"

        if isinstance(test, ast.Call):
            func = test.func
            if isinstance(func, ast.Attribute) and func.attr.startswith(MOCK_ASSERT_PREFIXES):
                return "mock"
            return "real"

        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            inner = test.operand
            if isinstance(inner, ast.Attribute) and inner.attr in MOCK_ATTRS:
                return "mock"
            return "real"

        return "real"

    def _root_name(self, node: ast.AST) -> str:
        """Left-most identifier of an attribute chain (`a.b.c` -> `a`)."""
        current = node
        while isinstance(current, ast.Attribute):
            current = current.value
        return current.id if isinstance(current, ast.Name) else ""

    def _is_pytest_raises(self, func: ast.Attribute) -> bool:
        return func.attr in {"raises", "warns"} and self._root_name(func) == "pytest"

    def _is_constant_arg(self, call: ast.Call) -> bool:
        return bool(call.args) and isinstance(call.args[0], ast.Constant)

    def _skip_marker(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """Return the skip/xfail marker name if the test is disabled."""
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if not isinstance(target, ast.Attribute):
                continue
            chain: list[str] = []
            current: ast.AST = target
            while isinstance(current, ast.Attribute):
                chain.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                chain.append(current.id)
            dotted = ".".join(reversed(chain))
            if any(marker in dotted for marker in ("skip", "xfail")):
                return dotted
        return ""

    def _swallows_failure(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        """True if the test catches exceptions and does nothing about them."""
        for child in ast.walk(node):
            if not isinstance(child, ast.Try):
                continue
            for handler in child.handlers:
                body = handler.body
                if all(isinstance(stmt, (ast.Pass, ast.Expr)) for stmt in body) and not any(
                    isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
                    and self._is_failing_call(stmt.value)
                    for stmt in body
                ):
                    has_assert = any(isinstance(n, ast.Assert) for stmt in body
                                     for n in ast.walk(stmt))
                    has_raise = any(isinstance(n, ast.Raise) for stmt in body
                                    for n in ast.walk(stmt))
                    if not has_assert and not has_raise:
                        return True
        return False

    def _is_failing_call(self, call: ast.Call) -> bool:
        func = call.func
        if isinstance(func, ast.Attribute):
            return func.attr in {"fail", "xfail"}
        if isinstance(func, ast.Name):
            return func.id == "fail"
        return False

    def _find_commented_assertions(self, path: str, source: str) -> list[dict[str, Any]]:
        """Commented-out assertions are a direct fingerprint of 'made it pass'."""
        hits: list[int] = []
        for lineno, raw in enumerate(source.splitlines(), start=1):
            stripped = raw.strip()
            if re.match(r"#\s*(assert\b|self\.assert)", stripped):
                hits.append(lineno)
        if not hits:
            return []
        return [self._finding(
            category="SUPPRESSED_FAILURE",
            test_name=f"{path} (lines {', '.join(str(h) for h in hits[:10])})",
            severity="high",
            problem=(
                f"{len(hits)} commented-out assertion(s) in {path}. The surrounding "
                "tests still execute the code and still count toward coverage, but the "
                "check that would have caught a defect has been disabled."
            ),
            recommendation=(
                "Restore each assertion. If it fails, the code under test is the "
                "suspect — fix the code, do not delete the assertion."
            ),
            would_catch="Exactly the defects the original author wrote them to catch.",
        )]

    def _build_metrics(
        self, records: list[dict[str, Any]], coverage_percent: float | None
    ) -> dict[str, Any]:
        total = len(records)
        sad = sum(1 for r in records if r["is_sad_path"])
        no_real = sum(1 for r in records if r["real_assertions"] == 0)
        real_assertions = sum(r["real_assertions"] for r in records)
        return {
            "test_count": total,
            "sad_path_tests": sad,
            "happy_path_tests": total - sad,
            "tests_without_any_assertion": sum(
                1 for r in records
                if r["real_assertions"] == 0 and r["mock_assertions"] == 0
                and r["tautologies"] == 0 and r["truthiness_only"] == 0
                and r["not_none_only"] == 0
            ),
            "tests_without_real_assertions": no_real,
            "mock_only_tests": sum(
                1 for r in records
                if r["real_assertions"] == 0 and r["mock_assertions"] > 0
            ),
            "tautology_tests": sum(1 for r in records if r["tautologies"] > 0),
            "skipped_tests": sum(1 for r in records if r["skipped"]),
            "failure_swallowing_tests": sum(1 for r in records if r["swallows_failure"]),
            "total_real_assertions": real_assertions,
            "assertions_per_test": round(real_assertions / total, 2) if total else 0.0,
            "unasserted_fraction": round(no_real / total, 3) if total else 0.0,
            "coverage_percent": coverage_percent,
            "test_names": [r["name"] for r in records],
        }

    def _suite_level_findings(
        self, metrics: dict[str, Any], records: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        total = metrics["test_count"]
        if total == 0:
            return out

        if metrics["sad_path_tests"] == 0:
            out.append(self._finding(
                category="MISSING_SAD_PATH", test_name="(suite)", severity="high",
                problem=(
                    f"All {total} tests exercise happy paths. No test uses "
                    "pytest.raises/assertRaises, and no test name indicates an error, "
                    "empty, malformed, or boundary case."
                ),
                recommendation=(
                    "Add error-path tests for the failure modes this module can actually "
                    "hit: malformed or empty vendor file, missing required attribute, "
                    "unexpected column type, upstream API failure/timeout, and "
                    "duplicate records."
                ),
                would_catch=(
                    "Any regression in error handling — currently 100% untested."
                ),
            ))
        elif metrics["sad_path_tests"] / total < 0.2:
            out.append(self._finding(
                category="MISSING_SAD_PATH", test_name="(suite)", severity="medium",
                problem=(
                    f"Only {metrics['sad_path_tests']} of {total} tests cover sad paths "
                    f"({metrics['sad_path_tests'] / total:.0%}). Error handling is "
                    "substantially thinner than the happy path."
                ),
                recommendation=(
                    "Enumerate each raise/error branch in the implementation and add one "
                    "test per branch asserting the specific exception and message."
                ),
                would_catch="Regressions in the untested error branches.",
            ))

        coverage = metrics["coverage_percent"]
        if coverage is not None:
            if coverage >= HIGH_COVERAGE_THRESHOLD and \
                    metrics["unasserted_fraction"] > UNASSERTED_TEST_TOLERANCE:
                out.append(self._finding(
                    category="GAMED_COVERAGE", test_name="(suite)", severity="high",
                    problem=(
                        f"Coverage reads {coverage:.1f}%, but "
                        f"{metrics['tests_without_real_assertions']} of {total} tests "
                        f"({metrics['unasserted_fraction']:.0%}) make no assertion on a "
                        "real value. Those lines are executed, not verified — the "
                        "coverage number overstates how protected this code is."
                    ),
                    recommendation=(
                        "Treat coverage as meaningful only for lines covered by an "
                        "asserting test. Strengthen the listed tests before trusting "
                        "the percentage, and consider adding mutation testing or a "
                        "no-assert lint to the pipeline."
                    ),
                    would_catch=(
                        "The false confidence that a high coverage number currently buys."
                    ),
                ))
            elif coverage < LOW_COVERAGE_THRESHOLD:
                out.append(self._finding(
                    category="MISSING_HAPPY_PATH", test_name="(suite)", severity="medium",
                    problem=(
                        f"Line coverage is {coverage:.1f}%, below the "
                        f"{LOW_COVERAGE_THRESHOLD:.0f}% floor — a large share of the "
                        "module is never executed by any test."
                    ),
                    recommendation=(
                        "Identify the uncovered lines from the coverage report and add "
                        "tests for the highest-risk ones first."
                    ),
                    would_catch="Defects anywhere in the never-executed code.",
                ))

        if metrics["assertions_per_test"] < 1 and total > 2:
            out.append(self._finding(
                category="WEAK_ASSERTION", test_name="(suite)", severity="medium",
                problem=(
                    f"The suite averages {metrics['assertions_per_test']} real "
                    f"assertions per test across {total} tests, which is characteristic "
                    "of smoke-testing rather than verification."
                ),
                recommendation=(
                    "For each test, add assertions covering the return value, any state "
                    "mutation, and the error case — one meaningful assertion per "
                    "behavior claimed by the test name."
                ),
                would_catch="Wrong-result defects that currently pass silently.",
            ))

        heavily_mocked = [
            r["name"] for r in records
            if r["mock_assertions"] >= 3 and r["real_assertions"] <= 1
        ]
        if heavily_mocked:
            out.append(self._finding(
                category="OVER_MOCKING", test_name=", ".join(heavily_mocked[:5]),
                severity="medium",
                problem=(
                    f"{len(heavily_mocked)} test(s) make 3+ mock assertions with at most "
                    "one assertion on a real value, which suggests the logic under test "
                    "has been stubbed out rather than exercised."
                ),
                recommendation=(
                    "Mock only the true external boundaries (network, DB, filesystem, "
                    "LLM provider) and let the module's own logic run, then assert on "
                    "its output."
                ),
                would_catch="Defects in the logic the mocks currently replace.",
            ))
        return out

    def _untested_public_functions(
        self, implementation: dict[str, str], test_files: dict[str, str]
    ) -> list[dict[str, Any]]:
        """Public implementation callables never named anywhere in the tests."""
        if not implementation:
            return []

        test_blob = "\n".join(test_files.values())
        untested: list[str] = []

        for path, source in implementation.items():
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                name = node.name
                if name.startswith("_"):
                    continue
                if not re.search(rf"\b{re.escape(name)}\b", test_blob):
                    untested.append(f"{path}::{name}()")

        if not untested:
            return []
        return [self._finding(
            category="MISSING_HAPPY_PATH", test_name="(none)", severity="high",
            problem=(
                f"{len(untested)} public callable(s) are never referenced by any test: "
                f"{', '.join(untested[:12])}"
                + (" …" if len(untested) > 12 else "")
                + ". Not even the happy path is covered."
            ),
            recommendation=(
                "Add at least one asserting happy-path test per public callable, then a "
                "sad-path test for each documented failure mode."
            ),
            would_catch="Any defect in these functions, including total breakage.",
        )]

    def _finding(
        self, *, category: str, test_name: str, severity: str, problem: str,
        recommendation: str, would_catch: str,
    ) -> dict[str, Any]:
        return {
            "id": "",  # assigned in _merge_findings so IDs are stable and ordered
            "category": category,
            "test_name": test_name,
            "severity": severity,
            "problem": problem,
            "recommendation": recommendation,
            "would_catch": would_catch,
            "detected_by": "static_analysis",
        }

    # ---------------------------------------------------------- LLM review

    def _review_with_llm(
        self, test_files: dict[str, str], implementation: dict[str, str],
        module_name: str, coverage_percent: float | None,
        coverage_note: str, static_findings: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        try:
            prompt = self.load_prompt(
                "test_review_agent.txt",
                module_name=module_name or "(unnamed module)",
                test_code=self._render_files(test_files, budget=10000),
                implementation_code=self._render_files(implementation, budget=6000)
                or "(implementation not supplied)",
                coverage_summary=coverage_note,
                static_findings=self._render_static_findings(static_findings),
            )
        except FileNotFoundError as exc:
            logger.error(f"Prompt file missing: {exc}")
            return None

        try:
            raw = self.call_claude(prompt, max_tokens=4096)
        except Exception as exc:
            logger.warning(f"LLM test review failed, using static findings only: {exc}")
            return None

        parsed = self._parse_json_object(raw)
        if parsed is None:
            logger.warning("Could not parse LLM test-review response as JSON")
            return None

        findings: list[dict[str, Any]] = []
        for item in parsed.get("findings", []) or []:
            if not isinstance(item, dict):
                continue
            category = str(item.get("category", "WEAK_ASSERTION")).upper()
            findings.append({
                "id": "",
                "category": category if category in CATEGORIES else "WEAK_ASSERTION",
                "test_name": str(item.get("test_name", "(none)")),
                "severity": str(item.get("severity", "medium")).lower(),
                "problem": str(item.get("problem", "")).strip(),
                "recommendation": str(item.get("recommendation", "")).strip(),
                "would_catch": str(item.get("would_catch", "")).strip(),
                "detected_by": "llm",
            })

        parsed["findings"] = [f for f in findings if f["problem"] and f["recommendation"]]
        return parsed

    def _render_files(self, files: dict[str, str], budget: int) -> str:
        parts: list[str] = []
        remaining = budget
        for path in sorted(files):
            if remaining <= 0:
                parts.append(f"\n# --- {path} (omitted: prompt budget exhausted) ---")
                continue
            body = files[path][:remaining]
            remaining -= len(body)
            truncated = " (truncated)" if len(body) < len(files[path]) else ""
            parts.append(f"\n# --- {path}{truncated} ---\n{body}")
        return "\n".join(parts)

    def _render_static_findings(self, findings: list[dict[str, Any]]) -> str:
        if not findings:
            return "(none — AST heuristics found nothing)"
        return "\n".join(
            f"- [{f['severity']}] {f['category']} {f['test_name']}: {f['problem']}"
            for f in findings[:40]
        )

    def _parse_json_object(self, raw: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                return {"findings": parsed}
        except (json.JSONDecodeError, TypeError):
            pass

        match = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
        return None

    # ------------------------------------------------------------- merging

    def _merge_findings(
        self, static_findings: list[dict[str, Any]], llm_findings: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for finding in list(static_findings) + list(llm_findings):
            if finding.get("category") not in CATEGORIES:
                finding["category"] = "WEAK_ASSERTION"
            if finding.get("severity") not in SEVERITY_ORDER:
                finding["severity"] = "medium"
            key = (
                finding["category"],
                re.sub(r"[^a-z0-9]", "", str(finding.get("test_name", "")).lower())[:60],
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(finding)

        merged.sort(key=lambda f: (
            SEVERITY_ORDER.get(f.get("severity", "medium"), 1),
            f.get("category", ""),
            f.get("test_name", ""),
        ))
        for index, finding in enumerate(merged, start=1):
            finding["id"] = f"TR-{index:03d}"
        return merged

    def _verdict(
        self, metrics: dict[str, Any], findings: list[dict[str, Any]],
        coverage_percent: float | None,
    ) -> str:
        categories = {f["category"] for f in findings}
        if "GAMED_COVERAGE" in categories:
            return "COVERAGE_MISLEADING"
        if coverage_percent is not None and coverage_percent >= HIGH_COVERAGE_THRESHOLD:
            weak = (
                metrics["tautology_tests"] + metrics["mock_only_tests"]
                + metrics["tests_without_any_assertion"] + metrics["skipped_tests"]
                + metrics["failure_swallowing_tests"]
            )
            if metrics["test_count"] and weak / metrics["test_count"] > UNASSERTED_TEST_TOLERANCE:
                return "COVERAGE_MISLEADING"
        if findings:
            return "GAPS_FOUND"
        return "MEANINGFUL"

    def _coverage_assessment(
        self, metrics: dict[str, Any], coverage_percent: float | None, note: str
    ) -> str:
        if coverage_percent is None:
            return (
                f"{note} Without a coverage report this review can only judge the tests "
                "that were supplied — treat the assessment below as a lower bound on the gaps."
            )
        unasserted = metrics["tests_without_real_assertions"]
        total = metrics["test_count"]
        if total and unasserted / total > UNASSERTED_TEST_TOLERANCE:
            return (
                f"{note} Not trustworthy: {unasserted}/{total} tests execute code without "
                "asserting on a real value, so a meaningful share of those covered lines "
                "is merely executed, not verified."
            )
        return (
            f"{note} Reasonably meaningful: {total - unasserted}/{total} tests assert on "
            f"real values (average {metrics['assertions_per_test']} real assertions per test)."
        )

    # ------------------------------------------------------------- outputs

    def _format_review(
        self, *, module_name: str, test_files: dict[str, str],
        metrics: dict[str, Any], findings: list[dict[str, Any]], verdict: str,
        summary: str, coverage_assessment: str, missing_sad_paths: list[str],
        questions: list[str], errors: list[str],
    ) -> str:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        high = sum(1 for f in findings if f["severity"] == "high")
        coverage = metrics["coverage_percent"]
        coverage_str = f"{coverage:.1f}%" if coverage is not None else "not supplied"

        lines = [
            f"## Test quality review — {module_name or 'unnamed module'}",
            "",
            f"**Verdict: {verdict}** — {high} high-severity finding(s) of "
            f"{len(findings)} total.",
            "",
            "This review looks at the **tests**, not the implementation. Passing tests "
            "are assumed; the question is whether they would fail if the code were wrong.",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Test functions found | {metrics['test_count']} |",
            f"| Happy-path tests | {metrics['happy_path_tests']} |",
            f"| Sad/error-path tests | {metrics['sad_path_tests']} |",
            f"| Tests with no assertion at all | {metrics['tests_without_any_assertion']} |",
            f"| Tests with no assertion on a real value | {metrics['tests_without_real_assertions']} |",
            f"| Mock-assertion-only tests | {metrics['mock_only_tests']} |",
            f"| Tests containing a tautology | {metrics['tautology_tests']} |",
            f"| Skipped / xfail tests | {metrics['skipped_tests']} |",
            f"| Tests swallowing failures | {metrics['failure_swallowing_tests']} |",
            f"| Real assertions per test | {metrics['assertions_per_test']} |",
            f"| Reported line coverage | {coverage_str} |",
            "",
            f"- Test files reviewed: {', '.join(sorted(test_files)) or '(none)'}",
            f"- Generated: {date}",
            "",
        ]

        if summary:
            lines.extend(["### Summary", summary, ""])

        lines.extend(["### Is the coverage number meaningful?", coverage_assessment, ""])

        if errors:
            lines.append("### Limitations of this review")
            lines.extend(f"- {e}" for e in errors)
            lines.append("")

        if findings:
            lines.append("### Findings")
            lines.append("")
            for finding in findings:
                lines.extend([
                    f"#### {finding['id']} · {finding['category']} · "
                    f"severity {finding['severity']}",
                    f"**Test:** `{finding['test_name']}`",
                    "",
                    f"**Problem:** {finding['problem']}",
                    "",
                    f"**Recommendation:** {finding['recommendation']}",
                    "",
                    f"**Defect this would catch:** "
                    f"{finding.get('would_catch') or 'not specified'}",
                    "",
                    f"_Detected by: {finding.get('detected_by', 'unknown')}_",
                    "",
                ])
        else:
            lines.extend([
                "### Findings",
                "",
                "No test-quality problems detected. Happy and sad paths are both "
                "represented and assertions check real values.",
                "",
            ])

        if missing_sad_paths:
            lines.append("### Specific untested error cases")
            lines.extend(f"- {item}" for item in missing_sad_paths)
            lines.append("")

        if questions:
            lines.append("### Questions for the human reviewer")
            lines.extend(f"- {item}" for item in questions)
            lines.append("")

        lines.extend([
            "---",
            "### Human gate",
            "This review is **advisory**. No test or source file was modified by this "
            "agent, and no finding is resolved until a human engineer decides on it. "
            "Nothing is baselined without that review.",
            "",
            "- [ ] Each high-severity finding triaged (accepted, deferred with a reason, or rejected)",
            "- [ ] New/strengthened tests written by a human or reviewed line-by-line if agent-written",
            "- [ ] No test was skipped, deleted, or weakened to close a finding",
            "- [ ] Coverage re-read only after assertions were strengthened",
            "",
            f"_Review generated by the {self.name} agent._",
        ])
        return "\n".join(lines)

    def _publish(
        self, trigger: AgentTrigger, module_name: str, review_md: str,
        verdict: str, findings: list[dict[str, Any]],
    ) -> list[AgentOutput]:
        outputs = [AgentOutput(
            output_type="test_review_completed",
            description=(
                f"Test quality review for {module_name or 'unnamed module'}: "
                f"{verdict}, {len(findings)} finding(s) (awaiting human review)"
            ),
            reference=module_name,
        )]

        pr_id = trigger.metadata.get("pr_id")
        repo = self.mcp.get("bitbucket") or self.mcp.get("github")
        if pr_id and repo and hasattr(repo, "add_pr_comment"):
            try:
                repo.add_pr_comment(pr_id, review_md)
                outputs.append(AgentOutput(
                    output_type="pr_comment",
                    description="Test quality review posted as a PR comment (comment only, no auto-merge)",
                    reference=str(pr_id),
                ))
            except Exception as exc:
                logger.warning(f"Could not post test review to PR {pr_id}: {exc}")
        return outputs

    def _record_to_wiki(
        self, module_name: str, verdict: str, metrics: dict[str, Any],
        findings: list[dict[str, Any]],
    ) -> None:
        """Best-effort traceability write; must never break a run."""
        try:
            self.wiki.put(
                "test_quality",
                module_name or "unnamed_module",
                {
                    "verdict": verdict,
                    "findings_count": len(findings),
                    "test_count": metrics["test_count"],
                    "sad_path_tests": metrics["sad_path_tests"],
                    "coverage_percent": metrics["coverage_percent"],
                    "status": "reviewed_awaiting_human_triage",
                    "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                },
                agent=self.name,
                pipeline="coding",
            )
        except Exception as exc:
            logger.debug(f"Wiki write skipped: {exc}")
