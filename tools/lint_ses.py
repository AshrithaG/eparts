#!/usr/bin/env python3
"""Custom linter for the eParts SES repo: enforces the **Agent Contract**.

WHY THIS EXISTS
---------------
Every capability in this repo is a class under ``agents/`` that the orchestrator
discovers by convention, not by compiler-checked interface. Nothing today stops
an agent from being written in a way that *silently* never runs or never works:

  * a module under ``agents/`` that forgets to subclass ``BaseAgent`` loses
    metrics, the JSONL audit trail, retry/backoff and the ``requires_human_review``
    gate — and ``orchestrator/registry.py`` cannot wrap it as a task handler;
  * an agent class that is never wired into ``orchestrator/registry.py`` is dead
    code: the queue has no handler for it, so it simply never fires and no error
    is ever raised;
  * a ``load_prompt("x.txt")`` call whose prompt file does not exist raises
    ``FileNotFoundError`` only on the code path that uses it, i.e. in production,
    long after the PR merged (``agents/base.py::load_prompt``);
  * the trigger/outputs header in each agent's module docstring is the source
    the architecture docs and artifact catalogue are written from — 28 agents
    maintained by five people will drift the moment it is unenforced.

All four of those are *deterministic* properties of the source tree. Checking
them costs no tokens and no judgement, which is exactly the class of quality
assurance that should be automated first (Cory Gwin coaching session,
2026-07-24: "a great deal of quality assurance is deterministic and consumes no
tokens ... if there is a rule the team wants enforced, work with AI to write a
linter for it").

THE RULE
--------
Blocking (exit 1):

  SES001  Each module under ``agents/`` (except ``__init__.py`` and ``base.py``)
          defines at least one class that inherits from ``BaseAgent``.
  SES002  That module's docstring declares both ``Triggered by:`` and
          ``Outputs:``, so the agent's contract is readable without running it.
  SES003  Each ``BaseAgent`` subclass is imported *and* instantiated in
          ``orchestrator/registry.py`` — i.e. it is actually wired to the queue.
  SES004  Every prompt filename passed as a literal to ``load_prompt()`` or
          ``call_claude()`` resolves to a real file under ``prompts/``.

Advisory (reported, exit 0 unless ``--strict``):

  SES005  ``commit_file(...)`` called from an agent without an explicit
          ``branch`` argument. ``BitbucketMCP.commit_file`` /
          ``GitHubMCP.commit_file`` default to ``branch="main"``, so such a call
          writes straight to the protected branch with no PR and no human
          approval gate. Several agents do this deliberately today (append-only
          record keeping), so it warns rather than blocks — but any *new*
          occurrence should be an explicit, reviewed decision.

Stdlib only. Exit 0 = clean, exit 1 = blocking violations found.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

BASE_AGENT = "BaseAgent"

# Modules under agents/ that are infrastructure, not agents.
AGENT_DIR_EXEMPT = {"__init__.py", "base.py"}

RULES = {
    "SES001": "agent module must define a BaseAgent subclass",
    "SES002": "agent module docstring must declare 'Triggered by:' and 'Outputs:'",
    "SES003": "agent class must be registered in orchestrator/registry.py",
    "SES004": "referenced prompt file must exist in prompts/",
    "SES005": "commit_file() without explicit branch= writes directly to main (advisory)",
}

ADVISORY_RULES = {"SES005"}

PROMPT_LOADERS = {"load_prompt", "call_claude"}


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    code: str
    message: str

    def render(self, root: Path) -> str:
        try:
            rel = self.path.relative_to(root)
        except ValueError:
            rel = self.path
        return f"{rel}:{self.line}: {self.code} {self.message}"

    @property
    def advisory(self) -> bool:
        return self.code in ADVISORY_RULES


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _base_name(node: ast.expr) -> str:
    """Return the trailing identifier of a base-class expression.

    ``BaseAgent`` -> "BaseAgent"; ``base.BaseAgent`` -> "BaseAgent";
    anything else (subscripts, calls) -> "".
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def agent_classes(tree: ast.Module) -> list[ast.ClassDef]:
    """Classes in this module that transitively inherit from BaseAgent."""
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    known = {BASE_AGENT}
    found: list[ast.ClassDef] = []

    # Fixpoint so `class A(BaseAgent)` / `class B(A)` are both recognised.
    changed = True
    while changed:
        changed = False
        for cls in classes:
            if cls in found:
                continue
            if any(_base_name(b) in known for b in cls.bases):
                found.append(cls)
                known.add(cls.name)
                changed = True
    return found


def _attr_calls(tree: ast.Module, attr_names: set[str]) -> list[ast.Call]:
    """All ``<something>.<attr>(...)`` calls whose attribute is in attr_names."""
    out = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in attr_names
        ):
            out.append(node)
    return out


def _first_str_arg(call: ast.Call) -> str | None:
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(
        call.args[0].value, str
    ):
        return call.args[0].value
    return None


# ---------------------------------------------------------------------------
# Registry parsing (for SES003)
# ---------------------------------------------------------------------------


@dataclass
class RegistryFacts:
    """What orchestrator/registry.py imports from agents.* and what it builds."""

    imported: set[tuple[str, str]]  # (module dotted path, class name)
    instantiated: set[str]  # class names called as Foo(...)
    parsed: bool


def read_registry(registry_path: Path) -> RegistryFacts:
    if not registry_path.is_file():
        return RegistryFacts(set(), set(), parsed=False)

    tree = ast.parse(registry_path.read_text(encoding="utf-8"), str(registry_path))
    imported: set[tuple[str, str]] = set()
    instantiated: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if node.module.startswith("agents."):
                for alias in node.names:
                    imported.add((node.module, alias.name))
        elif isinstance(node, ast.Call):
            name = _base_name(node.func)
            if name:
                instantiated.add(name)

    return RegistryFacts(imported, instantiated, parsed=True)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def module_dotted_path(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    return ".".join(rel.with_suffix("").parts)


def check_agent_module(
    path: Path,
    tree: ast.Module,
    root: Path,
    registry: RegistryFacts,
) -> list[Violation]:
    violations: list[Violation] = []
    classes = agent_classes(tree)

    # --- SES001 -----------------------------------------------------------
    if not classes:
        violations.append(
            Violation(
                path,
                1,
                "SES001",
                f"module defines no {BASE_AGENT} subclass; agents must inherit "
                f"{BASE_AGENT} (agents/base.py) to get logging, metrics, retry "
                "and the human-review gate",
            )
        )

    # --- SES002 -----------------------------------------------------------
    doc = ast.get_docstring(tree) or ""
    missing = [m for m in ("Triggered by:", "Outputs:") if m not in doc]
    if missing:
        detail = " and ".join(f"'{m}'" for m in missing)
        violations.append(
            Violation(
                path,
                1,
                "SES002",
                f"module docstring is missing {detail}; every agent must state "
                "what triggers it and what it produces",
            )
        )

    # --- SES003 -----------------------------------------------------------
    if classes and registry.parsed:
        dotted = module_dotted_path(path, root)
        wired = [
            cls
            for cls in classes
            if (dotted, cls.name) in registry.imported
            and cls.name in registry.instantiated
        ]
        if not wired:
            names = ", ".join(c.name for c in classes)
            violations.append(
                Violation(
                    path,
                    classes[0].lineno,
                    "SES003",
                    f"{names} is not wired into orchestrator/registry.py "
                    f"(expected 'from {dotted} import <Agent>' plus an "
                    "instantiation in register_all_agents); an unregistered "
                    "agent never runs and never errors",
                )
            )

    # --- SES005 (advisory) ------------------------------------------------
    for call in _attr_calls(tree, {"commit_file"}):
        kw_names = {kw.arg for kw in call.keywords}
        if None in kw_names:
            continue  # **kwargs passthrough — cannot prove it is missing
        # BitbucketMCP/GitHubMCP signature: (file_path, content, message, branch, agent_name)
        branch_positional = len(call.args) >= 4
        if "branch" not in kw_names and not branch_positional:
            violations.append(
                Violation(
                    path,
                    call.lineno,
                    "SES005",
                    "commit_file() has no explicit branch=; it defaults to "
                    "'main', so this writes to the protected branch with no PR "
                    "and no human approval gate",
                )
            )

    return violations


def check_prompt_references(path: Path, tree: ast.Module, prompts_dir: Path) -> list[Violation]:
    """SES004 — literal prompt filenames must resolve under prompts/."""
    violations: list[Violation] = []
    for call in _attr_calls(tree, PROMPT_LOADERS):
        literal = _first_str_arg(call)
        if literal is None:
            continue
        loader = call.func.attr  # type: ignore[union-attr]
        # call_claude() takes an inline prompt *or* a bare prompt filename; only
        # a .txt literal is a filename (see BaseAgent.call_claude resolution).
        if loader == "call_claude" and not literal.endswith(".txt"):
            continue
        if "/" in literal or "\\" in literal:
            continue  # not a plain prompts/ filename; out of scope
        if not (prompts_dir / literal).is_file():
            violations.append(
                Violation(
                    path,
                    call.lineno,
                    "SES004",
                    f"{loader}('{literal}') but prompts/{literal} does not "
                    "exist; this raises FileNotFoundError at runtime, not at "
                    "import time",
                )
            )
    return violations


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def iter_python_files(base: Path) -> list[Path]:
    return sorted(
        p
        for p in base.rglob("*.py")
        if not any(part in {".git", ".venv", "venv", "__pycache__", "node_modules"} for part in p.parts)
    )


def lint(root: Path) -> tuple[list[Violation], int]:
    """Returns (violations, number of files checked)."""
    agents_dir = root / "agents"
    prompts_dir = root / "prompts"
    registry = read_registry(root / "orchestrator" / "registry.py")

    violations: list[Violation] = []
    checked = 0

    # Prompt references: every Python file in the repo can load a prompt.
    for path in iter_python_files(root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        except (SyntaxError, UnicodeDecodeError) as exc:
            violations.append(
                Violation(path, getattr(exc, "lineno", 1) or 1, "SES000", f"cannot parse: {exc}")
            )
            continue
        checked += 1
        violations.extend(check_prompt_references(path, tree, prompts_dir))

        in_agents_dir = agents_dir in path.parents
        if in_agents_dir and path.name not in AGENT_DIR_EXEMPT:
            violations.extend(check_agent_module(path, tree, root, registry))

    violations.sort(key=lambda v: (str(v.path), v.line, v.code))
    return violations, checked


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lint_ses.py",
        description=(
            "Enforce the eParts Agent Contract: every module under agents/ "
            "subclasses BaseAgent, documents its trigger and outputs, is wired "
            "into orchestrator/registry.py, and only references prompt files "
            "that exist. Deterministic, stdlib-only, zero tokens."
        ),
        epilog=(
            "Rules:\n"
            + "\n".join(
                f"  {code}  {desc}" for code, desc in RULES.items()
            )
            + "\n\nExit codes: 0 = clean, 1 = blocking violations."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repository root to lint (default: the repo containing this script)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat advisory findings (%s) as blocking" % ", ".join(sorted(ADVISORY_RULES)),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="print violations only, no summary line",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()

    if not (root / "agents").is_dir():
        print(f"lint_ses: no agents/ directory under {root}", file=sys.stderr)
        return 2

    violations, checked = lint(root)

    for v in violations:
        prefix = "advisory: " if v.advisory and not args.strict else ""
        print(prefix + v.render(root))

    blocking = [v for v in violations if args.strict or not v.advisory]
    advisory = [v for v in violations if not args.strict and v.advisory]

    if not args.quiet:
        if violations:
            print()
        print(
            f"lint_ses: {checked} file(s) checked, "
            f"{len(blocking)} blocking, {len(advisory)} advisory"
        )

    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
