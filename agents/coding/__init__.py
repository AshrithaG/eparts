"""
Coding domain agents — each one is a distinct step in the development process,
with a single responsibility, run in this order:

  1. boilerplate_generator  scaffold a new module from ADR + REQ context
  2. test_generator         generate test stubs for the scaffolded code
  3. refactor_agent         clean up and reorganize code that already WORKS
  4. test_review_agent      review the tests: happy vs sad paths, assertion
                            strength, whether coverage is meaningful
  5. pr_reviewer            comment on the PR (style, tests, traceability)
  6. doc_generator          generate/refresh docs for the change

Build and refactor are deliberately separate agents. A build agent prioritizes
getting things working over organizing code well, much as a human does on a
first pass; a second agent whose sole job is cleanup brings a different point of
view to code that already works.

Every agent here is advisory: they comment, propose, and review. None of them
auto-merges or baselines an artifact — a human gate stands in front of that.

Runtime wiring to the task queue lives in orchestrator/registry.py; this module
only exposes the classes.
"""

from __future__ import annotations

from agents.coding.boilerplate_generator import BoilerplateGeneratorAgent
from agents.coding.doc_generator import DocGeneratorAgent
from agents.coding.pr_reviewer import PRReviewerAgent
from agents.coding.refactor_agent import RefactorAgent
from agents.coding.test_generator import TestGeneratorAgent
from agents.coding.test_review_agent import TestReviewAgent

# agent name (as registered with the orchestrator) -> agent class
CODING_AGENTS = {
    "boilerplate_generator": BoilerplateGeneratorAgent,
    "test_generator": TestGeneratorAgent,
    "refactor_agent": RefactorAgent,
    "test_review_agent": TestReviewAgent,
    "pr_reviewer": PRReviewerAgent,
    "doc_generator": DocGeneratorAgent,
}

__all__ = [
    "BoilerplateGeneratorAgent",
    "DocGeneratorAgent",
    "PRReviewerAgent",
    "RefactorAgent",
    "TestGeneratorAgent",
    "TestReviewAgent",
    "CODING_AGENTS",
]
