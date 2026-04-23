"""
Test Generator — generates unit test stubs from function signatures
when a module is scaffolded.

Triggered by: boilerplate_generator output
Outputs: test file added to same PR
"""

from __future__ import annotations

import logging
from typing import Any

from agents.base import AgentOutput, AgentResult, AgentTrigger, BaseAgent

logger = logging.getLogger("agent.test_generator")


class TestGeneratorAgent(BaseAgent):
    """Generates test stubs from function signatures."""

    def __init__(self, mcp_clients: dict[str, Any] | None = None):
        super().__init__(name="test_generator", mcp_clients=mcp_clients)

    def run(self, trigger: AgentTrigger) -> AgentResult:
        source_code = trigger.metadata.get("source_code", "")
        module_name = trigger.metadata.get("module_name", "")

        if not source_code:
            return AgentResult(
                agent=self.name, success=True,
                outputs=[AgentOutput(
                    output_type="test_gen_skipped",
                    description="No source code provided",
                )],
            )

        tests = self._generate_tests(source_code, module_name)
        outputs = []

        if tests:
            test_path = f"tests/test_{module_name.replace('/', '_').replace('.py', '')}.py"
            repo = self.mcp.get("github") or self.mcp.get("bitbucket")
            if repo:
                result = repo.commit_file(
                    file_path=test_path,
                    content=tests,
                    message=f"Add test stubs for {module_name}",
                    agent_name=self.name,
                )
                if result.get("ok"):
                    outputs.append(AgentOutput(
                        output_type="file_committed",
                        description=f"Test stubs committed for {module_name}",
                        reference=test_path,
                    ))

            outputs.append(AgentOutput(
                output_type="tests_generated",
                description=f"Generated test stubs for {module_name}",
            ))

        return AgentResult(agent=self.name, success=True, outputs=outputs)

    def _generate_tests(self, source_code: str, module_name: str) -> str:
        prompt = f"""Generate pytest unit test stubs for this Python module.

Module: {module_name}
Source code:
{source_code[:4000]}

Requirements:
- One test function per public method
- Use descriptive test names (test_[method]_[scenario])
- Include docstrings explaining what each test validates
- Add TODO comments for assertions that need real implementation
- Use pytest fixtures where appropriate"""

        return self.call_claude(prompt)
