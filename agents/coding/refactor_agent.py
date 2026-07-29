"""
Refactor Agent — the second pass over code a build agent already made work.

A build agent optimizes for getting things working, not for organizing code
well. This agent is a separate development-process step whose sole
responsibility is cleanup and reorganization of WORKING code: duplication,
poor cohesion, dead code, unclear naming, overlong functions, and misplaced
responsibilities.

Two hard rules, enforced in this module:
  1. It only runs on code that already works. If the trigger says tests are
     failing (or the build did not succeed), the agent refuses and hands back
     to the build agent — refactoring broken code hides the break.
  2. Every proposal must preserve observable behavior. This agent NEVER commits
     code. It produces a refactoring proposal that a human engineer reviews and
     applies. Nothing is baselined without the human gate.

Runs AST-based static heuristics first (works with no API key), then asks the
LLM to confirm, refine, and extend those findings. With no LLM provider
configured it degrades to static-analysis-only and reports that limitation
explicitly in the result.

Triggered by: build agent completion (boilerplate_generator / build step),
              PR containing new implementation code, or manual invocation
Outputs: refactoring proposal (markdown) posted as a PR comment when a repo
         MCP client is available; always flagged requires_human_review
"""

from __future__ import annotations

import ast
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.refactor_agent")

# --- static heuristic thresholds -------------------------------------------
MAX_FUNCTION_LINES = 50
MAX_FUNCTION_PARAMS = 6
MAX_NESTING_DEPTH = 4
MAX_CLASS_METHODS = 15
MAX_MODULE_LINES = 600
MIN_DUPLICATE_BLOCK_LINES = 6

# Names that carry no information about what the thing is or does.
VAGUE_NAMES = {
    "data", "data2", "info", "temp", "tmp", "obj", "object", "thing", "stuff",
    "val", "value2", "res", "result2", "ret", "out", "output2", "foo", "bar",
    "baz", "helper", "helper2", "util", "utils", "misc", "process", "handle",
    "do_it", "doit", "run_it", "stuff2", "manager", "manager2", "doer",
}

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

CATEGORY_LABELS = {
    "DUPLICATION": "Duplicated logic",
    "COHESION": "Low cohesion",
    "DEAD_CODE": "Dead code",
    "NAMING": "Unclear naming",
    "LONG_FUNCTION": "Overlong / overloaded function",
    "MISPLACED_RESPONSIBILITY": "Misplaced responsibility",
    "STRUCTURE": "Module structure",
}

NO_LLM_NOTICE = (
    "No LLM provider configured (set GEMINI_API_KEY or ANTHROPIC_API_KEY in .env). "
    "Ran in static-analysis-only mode: findings are limited to AST-detectable "
    "structural smells, and semantic issues such as misplaced responsibilities "
    "were not assessed."
)


class RefactorAgent(BaseAgent):
    """
    Cleans up and reorganizes code that a build agent already made work.

    Behavior-preserving proposals only. Never commits code, never edits tests,
    always requires human review before anything is applied.
    """

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="refactor_agent", mcp_clients=mcp_clients)

    # ------------------------------------------------------------------ run

    def run(self, trigger: AgentTrigger) -> AgentResult:
        module_name = trigger.metadata.get("module_name", "") or trigger.source
        files = self._collect_files(trigger)

        if not files:
            return AgentResult(
                agent=self.name, success=True,
                outputs=[AgentOutput(
                    output_type="refactor_skipped",
                    description="No source code provided to refactor",
                )],
            )

        # Rule 1: this agent only operates on code that already works.
        works, reason = self._code_already_works(trigger)
        if not works:
            logger.warning(f"Refusing to refactor {module_name}: {reason}")
            return AgentResult(
                agent=self.name, success=True,
                outputs=[AgentOutput(
                    output_type="refactor_refused",
                    description=(
                        f"Refused to refactor {module_name}: {reason}. "
                        "Refactoring runs only on working code — returning to the build step."
                    ),
                    reference=module_name,
                )],
                data={"refused": True, "reason": reason, "module_name": module_name},
            )

        errors: list[str] = []
        static_findings = self._analyze_static(files)

        llm_findings: list[dict[str, Any]] = []
        if self._settings.has_llm:
            llm_findings = self._analyze_with_llm(
                files, module_name, trigger, static_findings
            ) or []
            if not llm_findings:
                errors.append(
                    "LLM review returned no usable findings; falling back to "
                    "static analysis results only."
                )
        else:
            errors.append(NO_LLM_NOTICE)

        findings = self._merge_findings(static_findings, llm_findings)

        if not findings:
            return AgentResult(
                agent=self.name, success=True,
                outputs=[AgentOutput(
                    output_type="refactor_clean",
                    description=f"No structural problems found in {module_name}",
                    reference=module_name,
                )],
                errors=errors,
                data={
                    "module_name": module_name,
                    "findings": [],
                    "findings_count": 0,
                    "files_reviewed": sorted(files),
                },
            )

        proposal = self._format_proposal(module_name, files, findings, errors)
        outputs = self._publish(trigger, module_name, proposal, findings)

        self._record_to_wiki(module_name, findings)
        self.emit("refactoring_proposed", {
            "module_name": module_name,
            "findings_count": len(findings),
            "high_severity": sum(1 for f in findings if f.get("severity") == "high"),
            "files": sorted(files),
        }, pipeline="coding")

        return AgentResult(
            agent=self.name,
            success=True,
            outputs=outputs,
            errors=errors,
            # Rule 2: a human applies these, not the agent.
            requires_human_review=True,
            review_items=[
                {
                    "type": "refactoring_approval",
                    "finding_id": f.get("id", ""),
                    "category": f.get("category", ""),
                    "severity": f.get("severity", "medium"),
                    "file": f.get("file", ""),
                    "location": f.get("location", ""),
                    "message": (
                        f"[{f.get('severity', 'medium')}] {f.get('category', '?')} in "
                        f"{f.get('file', '?')} ({f.get('location', '?')}): "
                        f"{str(f.get('proposed_refactoring', ''))[:160]}"
                    ),
                    "behavior_risk": f.get("behavior_risk", "unknown"),
                    "verification": f.get("verification", ""),
                }
                for f in findings
            ],
            data={
                "module_name": module_name,
                "findings": findings,
                "findings_count": len(findings),
                "proposal_markdown": proposal,
                "files_reviewed": sorted(files),
                "behavior_preserving_only": True,
                "auto_applied": False,
            },
        )

    # -------------------------------------------------------------- inputs

    def _collect_files(self, trigger: AgentTrigger) -> dict[str, str]:
        """
        Normalize the several shapes a build agent can hand us into
        {path: source}. Accepts `files`/`scaffold` dicts, or a single
        `source_code` blob with an optional `file_path`/`module_name`.
        """
        meta = trigger.metadata
        candidates = meta.get("files") or meta.get("scaffold") or {}

        if not candidates:
            pipeline_ctx = meta.get("pipeline_context", {})
            if isinstance(pipeline_ctx, dict):
                candidates = pipeline_ctx.get("files") or pipeline_ctx.get("scaffold") or {}

        files: dict[str, str] = {}
        if isinstance(candidates, dict):
            for path, content in candidates.items():
                if isinstance(content, str) and content.strip():
                    files[str(path)] = content
        elif isinstance(candidates, list):
            for entry in candidates:
                if isinstance(entry, dict):
                    path = entry.get("path") or entry.get("file_path")
                    content = entry.get("content") or entry.get("source_code")
                    if path and isinstance(content, str) and content.strip():
                        files[str(path)] = content

        source_code = meta.get("source_code", "")
        if source_code and isinstance(source_code, str) and source_code.strip():
            path = meta.get("file_path") or meta.get("module_name") or "module.py"
            if not str(path).endswith(".py"):
                path = f"{path}.py"
            files.setdefault(str(path), source_code)

        # A refactor agent must not touch tests — that is the test reviewer's job,
        # and rewriting tests is how behavior changes slip through unnoticed.
        return {
            p: c for p, c in files.items()
            if not (p.startswith("tests/") or "/tests/" in p
                    or p.split("/")[-1].startswith("test_")
                    or p.endswith("_test.py"))
        }

    def _code_already_works(self, trigger: AgentTrigger) -> tuple[bool, str]:
        """
        Precondition check. This agent's whole premise is that it operates on
        code that already works, so any explicit signal to the contrary is a
        refusal. Absence of a signal is treated as "caller asserts it works".
        """
        meta = trigger.metadata

        tests_passing = meta.get("tests_passing")
        if tests_passing is False:
            return False, "trigger reports tests_passing=False"

        build_success = meta.get("build_success")
        if build_success is False:
            return False, "trigger reports build_success=False"

        status = str(meta.get("build_status", "")).lower()
        if status in {"failed", "failing", "error", "broken", "red"}:
            return False, f"trigger reports build_status={status!r}"

        failing = meta.get("failing_tests") or []
        if isinstance(failing, (list, tuple)) and failing:
            return False, f"{len(failing)} failing test(s) reported by the trigger"

        return True, "caller asserts the code works (no failure signal in trigger)"

    # ------------------------------------------------------- static analysis

    def _analyze_static(self, files: dict[str, str]) -> list[dict[str, Any]]:
        """AST + text heuristics. Works with no API key."""
        findings: list[dict[str, Any]] = []
        trees: dict[str, ast.Module] = {}

        for path, source in files.items():
            try:
                trees[path] = ast.parse(source)
            except SyntaxError as exc:
                findings.append(self._finding(
                    category="STRUCTURE", file=path,
                    location=f"line {exc.lineno or 0}", severity="high",
                    problem=f"File does not parse as Python: {exc.msg}",
                    proposed_refactoring=(
                        "Fix the syntax error before refactoring. This agent assumes "
                        "working code; a parse failure contradicts that premise."
                    ),
                    behavior_risk="none",
                    verification="Run the module's existing test suite.",
                ))

        for path, tree in trees.items():
            source = files[path]
            findings.extend(self._find_long_and_overloaded(path, tree))
            findings.extend(self._find_dead_code(path, tree, source))
            findings.extend(self._find_unclear_names(path, tree))
            findings.extend(self._find_cohesion_problems(path, tree, source))

        findings.extend(self._find_duplicate_blocks(files))
        return findings

    def _find_long_and_overloaded(self, path: str, tree: ast.Module) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            end = getattr(node, "end_lineno", None) or node.lineno
            length = end - node.lineno + 1
            if length > MAX_FUNCTION_LINES:
                out.append(self._finding(
                    category="LONG_FUNCTION", file=path,
                    location=f"{node.name}() lines {node.lineno}-{end}",
                    severity="high" if length > MAX_FUNCTION_LINES * 2 else "medium",
                    problem=(
                        f"{node.name}() is {length} lines long (threshold "
                        f"{MAX_FUNCTION_LINES}); it almost certainly does several "
                        "things that could be named separately."
                    ),
                    proposed_refactoring=(
                        f"Extract the distinct steps inside {node.name}() into "
                        "well-named private helpers and have it orchestrate them. "
                        "Pure extraction only — no logic changes."
                    ),
                    behavior_risk="low",
                    verification=(
                        "Existing tests for this function must pass unchanged; diff "
                        "the extracted bodies line-by-line against the original."
                    ),
                ))

            args = node.args
            param_count = (
                len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
                + (1 if args.vararg else 0) + (1 if args.kwarg else 0)
            )
            if param_count > MAX_FUNCTION_PARAMS:
                out.append(self._finding(
                    category="LONG_FUNCTION", file=path,
                    location=f"{node.name}() line {node.lineno}",
                    severity="medium",
                    problem=(
                        f"{node.name}() takes {param_count} parameters (threshold "
                        f"{MAX_FUNCTION_PARAMS}); long parameter lists usually mean "
                        "several related values want to be one object."
                    ),
                    proposed_refactoring=(
                        "Group the cohesive parameters into a dataclass and pass that. "
                        "Keep a thin wrapper with the old signature if external callers "
                        "exist, so no caller has to change."
                    ),
                    behavior_risk="low",
                    verification="Call sites must be updated mechanically; existing tests must pass.",
                ))

            depth = self._max_nesting_depth(node)
            if depth > MAX_NESTING_DEPTH:
                out.append(self._finding(
                    category="LONG_FUNCTION", file=path,
                    location=f"{node.name}() line {node.lineno}",
                    severity="medium",
                    problem=(
                        f"{node.name}() nests control flow {depth} levels deep "
                        f"(threshold {MAX_NESTING_DEPTH}), which hides the main path."
                    ),
                    proposed_refactoring=(
                        "Flatten with early returns / guard clauses and extract the "
                        "innermost blocks into helpers."
                    ),
                    behavior_risk="low",
                    verification=(
                        "Guard-clause inversion is easy to get subtly wrong — re-run "
                        "the full test suite and review each inverted condition."
                    ),
                ))
        return out

    def _max_nesting_depth(self, node: ast.AST) -> int:
        """Deepest nesting of control-flow statements inside a function body."""
        nesting_types = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With,
                         ast.AsyncWith, ast.Try)

        def walk(n: ast.AST, depth: int) -> int:
            best = depth
            for child in ast.iter_child_nodes(n):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue  # nested definitions are measured on their own
                child_depth = depth + 1 if isinstance(child, nesting_types) else depth
                best = max(best, walk(child, child_depth))
            return best

        return walk(node, 0)

    def _find_dead_code(self, path: str, tree: ast.Module, source: str) -> list[dict[str, Any]]:
        """
        Unreferenced private helpers and unused imports. Uses whole-file
        identifier counts so `self._helper` and decorator references count.
        Only private names are reported: a public name may be used by callers
        outside this file, and this agent does not see the whole repo.
        """
        out: list[dict[str, Any]] = []

        def occurrences(name: str) -> int:
            return len(re.findall(rf"\b{re.escape(name)}\b", source))

        exported = self._exported_names(tree)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = node.name
                if not name.startswith("_") or name.startswith("__"):
                    continue
                if name in exported:
                    continue
                if occurrences(name) <= 1:
                    kind = "class" if isinstance(node, ast.ClassDef) else "function"
                    out.append(self._finding(
                        category="DEAD_CODE", file=path,
                        location=f"{name} line {node.lineno}", severity="medium",
                        problem=(
                            f"Private {kind} {name} is never referenced anywhere in "
                            "this file — most likely leftover scaffolding from the build pass."
                        ),
                        proposed_refactoring=(
                            f"Delete {name}, or make it public and add a test if it is "
                            "genuinely needed by another module."
                        ),
                        behavior_risk="none",
                        verification=(
                            f"Grep the repository for `{name}` before deleting (this agent "
                            "only saw the files handed to it), then run the test suite."
                        ),
                    ))

        for node in tree.body:
            if isinstance(node, ast.Import):
                bound = [(a.asname or a.name.split(".")[0], a.name) for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                bound = [(a.asname or a.name, a.name) for a in node.names
                         if a.name != "*"]
            else:
                continue

            for local, original in bound:
                if local in exported:
                    continue
                if occurrences(local) <= 1:
                    out.append(self._finding(
                        category="DEAD_CODE", file=path,
                        location=f"import line {node.lineno}", severity="low",
                        problem=f"Imported name {local!r} ({original}) is never used.",
                        proposed_refactoring=f"Remove the unused import of {local!r}.",
                        behavior_risk="low",
                        verification=(
                            "Confirm the import has no side effects (some modules "
                            "register things on import) before removing it."
                        ),
                    ))
        return out

    def _exported_names(self, tree: ast.Module) -> set[str]:
        """Names listed in __all__, which count as referenced."""
        exported: set[str] = set()
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "__all__" not in targets:
                continue
            if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                for elt in node.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        exported.add(elt.value)
        return exported

    def _find_unclear_names(self, path: str, tree: ast.Module) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bare = node.name.lstrip("_").lower()
                if bare in VAGUE_NAMES:
                    kind = "class" if isinstance(node, ast.ClassDef) else "function"
                    out.append(self._finding(
                        category="NAMING", file=path,
                        location=f"{node.name} line {node.lineno}", severity="medium",
                        problem=(
                            f"{kind.capitalize()} name {node.name!r} does not say what it "
                            "is or does — the reader has to read the body to find out."
                        ),
                        proposed_refactoring=(
                            f"Rename {node.name!r} to describe its actual effect "
                            "(verb phrase for functions, noun phrase for classes) and "
                            "update all call sites."
                        ),
                        behavior_risk="low",
                        verification=(
                            "A rename is behavior-preserving only if every reference is "
                            "updated, including strings and dynamic lookups — grep for the old name."
                        ),
                    ))

            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                params = list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs)
                vague = [
                    a.arg for a in params
                    if a.arg.lower() in VAGUE_NAMES
                    or (len(a.arg) == 1 and a.arg not in {"x", "y", "n", "_"})
                ]
                if vague:
                    out.append(self._finding(
                        category="NAMING", file=path,
                        location=f"{node.name}() line {node.lineno}", severity="low",
                        problem=(
                            f"Parameters {', '.join(repr(v) for v in vague)} in "
                            f"{node.name}() are uninformative."
                        ),
                        proposed_refactoring=(
                            "Rename these parameters to describe the domain concept they "
                            "carry (e.g. `data` -> `vendor_rows`)."
                        ),
                        behavior_risk="low",
                        verification=(
                            "Check for keyword-argument call sites — renaming a parameter "
                            "breaks callers that pass it by name."
                        ),
                    ))
        return out

    def _find_cohesion_problems(
        self, path: str, tree: ast.Module, source: str
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []

        line_count = len(source.splitlines())
        if line_count > MAX_MODULE_LINES:
            top_level_classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
            out.append(self._finding(
                category="STRUCTURE", file=path,
                location=f"whole file ({line_count} lines)", severity="medium",
                problem=(
                    f"Module is {line_count} lines (threshold {MAX_MODULE_LINES})"
                    + (f" and defines {len(top_level_classes)} top-level classes"
                       if len(top_level_classes) > 1 else "")
                    + ", which makes it hard to navigate."
                ),
                proposed_refactoring=(
                    "Split along the seams already visible in the file (one concern per "
                    "module) and re-export from the package __init__ so imports keep working."
                ),
                behavior_risk="low",
                verification=(
                    "Import paths must stay valid — run the full test suite and check "
                    "for circular imports after the split."
                ),
            ))

        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue

            methods = [
                n for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            if len(methods) > MAX_CLASS_METHODS:
                out.append(self._finding(
                    category="COHESION", file=path,
                    location=f"class {node.name} line {node.lineno}", severity="medium",
                    problem=(
                        f"class {node.name} has {len(methods)} methods (threshold "
                        f"{MAX_CLASS_METHODS}); it is probably several responsibilities "
                        "that were convenient to put in one place while building."
                    ),
                    proposed_refactoring=(
                        f"Group the methods of {node.name} by the state they touch and "
                        "extract each group into its own collaborator class, delegating "
                        "from the original so the public surface is unchanged."
                    ),
                    behavior_risk="low",
                    verification=(
                        "Keep the original public methods as delegating one-liners; "
                        "existing tests should need no edits at all."
                    ),
                ))

            for method in methods:
                decorators = {
                    d.id for d in method.decorator_list if isinstance(d, ast.Name)
                }
                if decorators & {"staticmethod", "classmethod", "property"}:
                    continue
                params = list(method.args.posonlyargs) + list(method.args.args)
                if not params or params[0].arg != "self":
                    continue
                uses_self = any(
                    isinstance(n, ast.Name) and n.id == "self"
                    for n in ast.walk(method)
                )
                if not uses_self:
                    out.append(self._finding(
                        category="MISPLACED_RESPONSIBILITY", file=path,
                        location=f"{node.name}.{method.name}() line {method.lineno}",
                        severity="low",
                        problem=(
                            f"{node.name}.{method.name}() never touches `self`, so it is "
                            "not really behavior of this class — it is a free function "
                            "parked inside it."
                        ),
                        proposed_refactoring=(
                            f"Move {method.name}() to module level (or mark it "
                            "@staticmethod if it belongs to the class conceptually)."
                        ),
                        behavior_risk="low",
                        verification=(
                            "If any test or caller invokes it through an instance, keep a "
                            "@staticmethod shim so the call still resolves."
                        ),
                    ))
        return out

    def _find_duplicate_blocks(self, files: dict[str, str]) -> list[dict[str, Any]]:
        """
        Sliding-window duplicate detection over normalized code lines.
        Catches the copy-paste a build agent leaves behind when it needs the
        same logic in two branches.
        """
        windows: dict[tuple[str, ...], list[tuple[str, int]]] = {}

        for path, source in files.items():
            normalized: list[tuple[int, str]] = []
            for lineno, raw in enumerate(source.splitlines(), start=1):
                stripped = raw.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                normalized.append((lineno, re.sub(r"\s+", " ", stripped)))

            limit = len(normalized) - MIN_DUPLICATE_BLOCK_LINES + 1
            for start in range(max(0, limit)):
                chunk = normalized[start:start + MIN_DUPLICATE_BLOCK_LINES]
                key = tuple(text for _, text in chunk)
                windows.setdefault(key, []).append((path, chunk[0][0]))

        out: list[dict[str, Any]] = []
        claimed: dict[str, set[int]] = {}

        for key, locations in windows.items():
            if len(locations) < 2:
                continue
            # Skip windows overlapping an already-reported duplicate region.
            if any(
                first_line in claimed.get(path, set())
                for path, first_line in locations
            ):
                continue
            for path, first_line in locations:
                claimed.setdefault(path, set()).update(
                    range(first_line, first_line + MIN_DUPLICATE_BLOCK_LINES * 2)
                )

            where = "; ".join(f"{p}:{ln}" for p, ln in locations)
            cross_file = len({p for p, _ in locations}) > 1
            out.append(self._finding(
                category="DUPLICATION",
                file=locations[0][0],
                location=where,
                severity="high" if len(locations) > 2 or cross_file else "medium",
                problem=(
                    f"A block of {MIN_DUPLICATE_BLOCK_LINES}+ equivalent lines appears "
                    f"{len(locations)} times ({where}). First line of the block: "
                    f"`{key[0][:110]}`."
                ),
                proposed_refactoring=(
                    "Extract the repeated block into a single well-named function and "
                    "call it from each site. Pure extraction — parameterize only the "
                    "values that actually differ."
                ),
                behavior_risk="low",
                verification=(
                    "Diff each call site against the extracted body to confirm the "
                    "copies were truly identical, then run the full test suite."
                ),
            ))
        return out

    def _finding(
        self, *, category: str, file: str, location: str, severity: str,
        problem: str, proposed_refactoring: str, behavior_risk: str,
        verification: str,
    ) -> dict[str, Any]:
        return {
            "id": "",  # assigned in _merge_findings so IDs are stable and ordered
            "category": category,
            "file": file,
            "location": location,
            "severity": severity,
            "problem": problem,
            "proposed_refactoring": proposed_refactoring,
            "behavior_risk": behavior_risk,
            "verification": verification,
            "rationale": CATEGORY_LABELS.get(category, category),
            "detected_by": "static_analysis",
        }

    # ---------------------------------------------------------- LLM review

    def _analyze_with_llm(
        self, files: dict[str, str], module_name: str,
        trigger: AgentTrigger, static_findings: list[dict[str, Any]],
    ) -> list[dict[str, Any]] | None:
        """Ask the LLM to confirm/refine/extend the static findings."""
        code_blob = self._render_code(files)
        build_context = self._render_build_context(trigger)
        static_blob = self._render_static_findings(static_findings)

        try:
            prompt = self.load_prompt(
                "refactor_agent.txt",
                module_name=module_name or "(unnamed module)",
                build_context=build_context,
                code=code_blob,
                static_findings=static_blob,
            )
        except FileNotFoundError as exc:
            logger.error(f"Prompt file missing: {exc}")
            return None

        try:
            raw = self.call_claude(prompt, max_tokens=4096)
        except Exception as exc:
            logger.warning(f"LLM refactor review failed, using static findings only: {exc}")
            return None

        parsed = self._parse_json_array(raw)
        if parsed is None:
            logger.warning("Could not parse LLM refactor response as a JSON array")
            return None

        findings: list[dict[str, Any]] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            findings.append({
                "id": "",
                "category": str(item.get("category", "STRUCTURE")).upper(),
                "file": str(item.get("file", module_name)),
                "location": str(item.get("location", "unspecified")),
                "severity": str(item.get("severity", "medium")).lower(),
                "problem": str(item.get("problem", "")).strip(),
                "proposed_refactoring": str(item.get("proposed_refactoring", "")).strip(),
                "behavior_risk": str(item.get("behavior_risk", "unknown")).lower(),
                "verification": str(item.get("verification", "")).strip(),
                "rationale": str(item.get("rationale", "")).strip(),
                "detected_by": "llm",
            })
        return [f for f in findings if f["problem"] and f["proposed_refactoring"]]

    def _render_code(self, files: dict[str, str], budget: int = 12000) -> str:
        """Concatenate files with headers, within a token budget."""
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

    def _render_build_context(self, trigger: AgentTrigger) -> str:
        meta = trigger.metadata
        lines = [
            f"- trigger_type: {trigger.trigger_type}",
            f"- source: {trigger.source}",
        ]
        for key in ("build_agent", "ticket_key", "req_ids", "context",
                    "tests_passing", "build_status", "coverage_percent"):
            if meta.get(key) not in (None, "", [], {}):
                lines.append(f"- {key}: {str(meta[key])[:400]}")
        lines.append(
            "- working-code assertion: no failure signal was present in the trigger, "
            "so this code is treated as already working."
        )
        return "\n".join(lines)

    def _render_static_findings(self, findings: list[dict[str, Any]]) -> str:
        if not findings:
            return "(none — AST heuristics found nothing)"
        return "\n".join(
            f"- [{f['severity']}] {f['category']} {f['file']} ({f['location']}): {f['problem']}"
            for f in findings[:40]
        )

    def _parse_json_array(self, raw: str) -> list[Any] | None:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict) and isinstance(parsed.get("findings"), list):
                return parsed["findings"]
        except (json.JSONDecodeError, TypeError):
            pass

        match = re.search(r"\[.*\]", raw or "", re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
        return None

    # ------------------------------------------------------------- merging

    def _merge_findings(
        self, static_findings: list[dict[str, Any]], llm_findings: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Union of both sources, de-duplicated on (category, file, location-ish),
        sorted by severity, with stable RF-XXX ids assigned last.
        """
        merged: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()

        for finding in list(static_findings) + list(llm_findings):
            category = finding.get("category", "STRUCTURE")
            if category not in CATEGORY_LABELS:
                category = "STRUCTURE"
                finding["category"] = category
            if finding.get("severity") not in SEVERITY_ORDER:
                finding["severity"] = "medium"

            key = (
                category,
                finding.get("file", ""),
                re.sub(r"[^a-z0-9]", "", str(finding.get("location", "")).lower())[:40],
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(finding)

        merged.sort(key=lambda f: (
            SEVERITY_ORDER.get(f.get("severity", "medium"), 1),
            f.get("category", ""),
            f.get("file", ""),
        ))
        for index, finding in enumerate(merged, start=1):
            finding["id"] = f"RF-{index:03d}"
        return merged

    # ------------------------------------------------------------- outputs

    def _format_proposal(
        self, module_name: str, files: dict[str, str],
        findings: list[dict[str, Any]], errors: list[str],
    ) -> str:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        counts: dict[str, int] = {}
        for finding in findings:
            counts[finding["category"]] = counts.get(finding["category"], 0) + 1
        summary = ", ".join(
            f"{CATEGORY_LABELS.get(c, c)}: {n}" for c, n in sorted(counts.items())
        )
        high = sum(1 for f in findings if f["severity"] == "high")

        lines = [
            f"## Refactoring proposal — {module_name or 'unnamed module'}",
            "",
            "This code **already works**. Everything below is cleanup and "
            "reorganization only: no behavior change, no new features, no bug fixes, "
            "no test edits.",
            "",
            f"- Files reviewed: {', '.join(sorted(files)) or '(none)'}",
            f"- Findings: {len(findings)} ({high} high severity)",
            f"- Breakdown: {summary}",
            f"- Generated: {date}",
            "",
            "**Nothing here has been applied.** A human engineer decides which of these "
            "to take, applies them, and confirms the test suite is still green. This "
            "agent does not commit code, and no artifact is baselined without that review.",
            "",
        ]

        if errors:
            lines.append("### Limitations of this review")
            lines.extend(f"- {e}" for e in errors)
            lines.append("")

        for finding in findings:
            lines.extend([
                f"### {finding['id']} · {finding['category']} · "
                f"severity {finding['severity']}",
                f"**Where:** `{finding['file']}` — {finding['location']}",
                "",
                f"**Problem:** {finding['problem']}",
                "",
                f"**Proposed refactoring:** {finding['proposed_refactoring']}",
                "",
                f"**Behavior-change risk:** {finding.get('behavior_risk', 'unknown')}",
                "",
                f"**How to verify behavior is unchanged:** "
                f"{finding.get('verification') or 'Run the existing test suite unchanged.'}",
                "",
                f"_Detected by: {finding.get('detected_by', 'unknown')}_",
                "",
            ])

        lines.extend([
            "---",
            "### Review checklist for the human reviewer",
            "- [ ] Test suite was green **before** any of these changes",
            "- [ ] Each accepted refactoring was applied as its own reviewable commit",
            "- [ ] Test suite is green **after**, with no test file modified",
            "- [ ] Public API / call sites unchanged, or all callers updated",
            "",
            f"_Proposal generated by the {self.name} agent. Advisory only._",
        ])
        return "\n".join(lines)

    def _publish(
        self, trigger: AgentTrigger, module_name: str,
        proposal: str, findings: list[dict[str, Any]],
    ) -> list[AgentOutput]:
        outputs = [AgentOutput(
            output_type="refactoring_proposed",
            description=(
                f"{len(findings)} behavior-preserving refactorings proposed for "
                f"{module_name or 'unnamed module'} (awaiting human review)"
            ),
            reference=module_name,
        )]

        pr_id = trigger.metadata.get("pr_id")
        repo = self.mcp.get("bitbucket") or self.mcp.get("github")
        if pr_id and repo and hasattr(repo, "add_pr_comment"):
            try:
                repo.add_pr_comment(pr_id, proposal)
                outputs.append(AgentOutput(
                    output_type="pr_comment",
                    description="Refactoring proposal posted as a PR comment (comment only, no auto-merge)",
                    reference=str(pr_id),
                ))
            except Exception as exc:
                logger.warning(f"Could not post refactoring proposal to PR {pr_id}: {exc}")
        return outputs

    def _record_to_wiki(self, module_name: str, findings: list[dict[str, Any]]) -> None:
        """Best-effort traceability write; metrics/wiki must never break a run."""
        try:
            self.wiki.put(
                "refactoring",
                module_name or "unnamed_module",
                {
                    "findings_count": len(findings),
                    "categories": sorted({f["category"] for f in findings}),
                    "status": "proposed_awaiting_human_review",
                    "applied": False,
                    "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                },
                agent=self.name,
                pipeline="coding",
            )
        except Exception as exc:
            logger.debug(f"Wiki write skipped: {exc}")
