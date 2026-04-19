"""
Boilerplate Generator — scaffolds new service/module directories
from ADR + REQ context when a Jira ticket is tagged as new module.

Triggered by: Jira ticket assigned with "new-module" label
Outputs: PR with scaffolded directory, interface stubs, test file
"""

from __future__ import annotations

import logging
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.boilerplate_generator")


class BoilerplateGeneratorAgent(BaseAgent):
    """Scaffolds new modules from ADR and REQ context."""

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="boilerplate_generator", mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        module_name = trigger.metadata.get("module_name", "")
        context = trigger.metadata.get("context", "")
        ticket_key = trigger.metadata.get("ticket_key", "")

        if not module_name:
            return AgentResult(
                agent=self.name, success=False,
                errors=["No module_name provided"],
            )

        scaffold = self._generate_scaffold(module_name, context)
        outputs = []

        bitbucket = self.mcp.get("bitbucket")
        if bitbucket:
            branch = f"feature/{module_name}-scaffold"
            bitbucket.create_branch(branch)

            for filepath, content in scaffold.items():
                bitbucket.commit_file(
                    file_path=filepath, content=content,
                    message=f"Scaffold {module_name}: {filepath}",
                    branch=branch, agent_name=self.name,
                )

            pr_result = bitbucket.open_pr(
                title=f"[Scaffold] {module_name} module ({ticket_key})",
                source_branch=branch,
                description=f"Auto-scaffolded from {ticket_key}.\n\nContext: {context[:200]}",
            )
            if pr_result.get("ok"):
                outputs.append(AgentOutput(
                    output_type="pr_opened",
                    description=f"Scaffold PR for {module_name}",
                    reference=pr_result.get("pr_url", ""),
                ))

        return AgentResult(
            agent=self.name, success=True, outputs=outputs,
            requires_human_review=True,
        )

    def _generate_scaffold(self, module_name: str, context: str) -> dict[str, str]:
        """Generate scaffold files for a new module."""
        base_path = f"src/{module_name}"
        return {
            f"{base_path}/__init__.py": f'"""{module_name} module."""\n',
            f"{base_path}/service.py": self._generate_service(module_name, context),
            f"{base_path}/models.py": self._generate_models(module_name),
            f"tests/test_{module_name}.py": self._generate_tests(module_name),
        }

    def _generate_service(self, name: str, context: str) -> str:
        prompt = f"""Generate a Python service skeleton for a module called '{name}'.
Context: {context[:500]}
Include: class with interface methods (pass bodies), docstrings, type hints.
Keep it minimal — just the interface."""
        return self.call_claude(prompt)

    def _generate_models(self, name: str) -> str:
        return f'"""{name} data models."""\n\nfrom dataclasses import dataclass\n'

    def _generate_tests(self, name: str) -> str:
        return f'"""Tests for {name} module."""\n\nimport pytest\n\n\ndef test_{name}_placeholder():\n    """Placeholder test — implement after module is built."""\n    assert True\n'
