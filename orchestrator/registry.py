"""
Agent Registry — instantiation and wiring of all agents to the task queue.

This is where the architecture diagram becomes executable. Each agent is
instantiated with its MCP client dependencies, then registered as a handler
in the TaskQueue. When a task arrives, the queue calls the handler, which
converts the AgentTask payload into an AgentTrigger and calls agent.execute().

Separating instantiation from routing keeps the orchestrator testable:
swap any agent with a mock by replacing its registry entry.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from agents.base import AgentTrigger, AgentResult
from orchestrator.queue import AgentTask, TaskQueue

logger = logging.getLogger("orchestrator.registry")


def _make_handler(agent):
    """
    Wrap a BaseAgent subclass into a TaskQueue handler.
    Converts AgentTask payload → AgentTrigger, calls execute(), returns dict.
    """
    def handler(task: AgentTask) -> dict[str, Any]:
        trigger = AgentTrigger(
            trigger_type=task.trigger_type,
            source=task.payload.get("source", "unknown"),
            metadata=task.payload.get("metadata", {}),
        )
        result = agent.execute(trigger)
        return {
            "agent": result.agent,
            "success": result.success,
            "outputs": [asdict(o) for o in result.outputs],
            "errors": result.errors,
            "requires_human_review": result.requires_human_review,
            "review_items": result.review_items,
        }
    return handler


def _build_mcp_clients() -> dict[str, Any]:
    """
    Instantiate all MCP server clients. Agents pick what they need by key.
    Each client wraps a third-party API (Jira, Slack, Bitbucket, etc.)
    """
    from mcp.slack import SlackMCP
    from mcp.jira import JiraMCP
    from mcp.bitbucket import BitbucketMCP
    from mcp.confluence import ConfluenceMCP
    from mcp.drive import DriveMCP
    from mcp.vector_store import VectorStoreMCP
    from mcp.github import GitHubMCP

    return {
        "slack": SlackMCP(),
        "jira": JiraMCP(),
        "bitbucket": BitbucketMCP(),
        "confluence": ConfluenceMCP(),
        "drive": DriveMCP(),
        "vector_store": VectorStoreMCP(),
        "github": GitHubMCP(),
    }


def register_all_agents(task_queue: TaskQueue) -> dict[str, Any]:
    """
    Instantiate every agent and register it with the task queue.
    Returns the dict of agent instances (useful for testing).
    """
    mcp = _build_mcp_clients()
    agents: dict[str, Any] = {}

    # --- Requirements Domain ---
    from agents.requirements.transcript_parser import TranscriptParserAgent
    from agents.requirements.priority_classifier import PriorityClassifierAgent
    from agents.requirements.req_extractor import ReqExtractorAgent
    from agents.requirements.stale_detector import StaleDetectorAgent

    agents["transcript_parser"] = TranscriptParserAgent(
        mcp_clients={"bitbucket": mcp["bitbucket"], "github": mcp["github"]}
    )
    agents["priority_classifier"] = PriorityClassifierAgent()
    agents["req_extractor"] = ReqExtractorAgent(
        mcp_clients={"bitbucket": mcp["bitbucket"], "github": mcp["github"]}
    )
    agents["stale_detector"] = StaleDetectorAgent(
        mcp_clients={"jira": mcp["jira"], "slack": mcp["slack"]}
    )

    # --- Architecture Domain ---
    from agents.architecture.drift_detector import DriftDetectorAgent
    from agents.architecture.adr_generator import ADRGeneratorAgent
    from agents.architecture.diagram_updater import DiagramUpdaterAgent
    from agents.architecture.traceability_builder import TraceabilityBuilderAgent

    agents["drift_detector"] = DriftDetectorAgent()
    agents["adr_generator"] = ADRGeneratorAgent(
        mcp_clients={"bitbucket": mcp["bitbucket"], "github": mcp["github"]}
    )
    agents["diagram_updater"] = DiagramUpdaterAgent(
        mcp_clients={"bitbucket": mcp["bitbucket"], "github": mcp["github"]}
    )
    agents["traceability_builder"] = TraceabilityBuilderAgent(
        mcp_clients={"jira": mcp["jira"], "bitbucket": mcp["bitbucket"], "github": mcp["github"]}
    )

    # --- Coding Domain ---
    from agents.coding.boilerplate_generator import BoilerplateGeneratorAgent
    from agents.coding.pr_reviewer import PRReviewerAgent
    from agents.coding.test_generator import TestGeneratorAgent
    from agents.coding.doc_generator import DocGeneratorAgent

    agents["boilerplate_generator"] = BoilerplateGeneratorAgent(
        mcp_clients={"bitbucket": mcp["bitbucket"], "github": mcp["github"]}
    )
    agents["pr_reviewer"] = PRReviewerAgent(
        mcp_clients={"bitbucket": mcp["bitbucket"], "github": mcp["github"]}
    )
    agents["test_generator"] = TestGeneratorAgent(
        mcp_clients={"bitbucket": mcp["bitbucket"], "github": mcp["github"]}
    )
    agents["doc_generator"] = DocGeneratorAgent(
        mcp_clients={"bitbucket": mcp["bitbucket"], "github": mcp["github"]}
    )

    # --- Project Management Domain ---
    from agents.project_mgmt.ticket_creator import TicketCreatorAgent
    from agents.project_mgmt.wbs_updater import WBSUpdaterAgent
    from agents.project_mgmt.weekly_digest import WeeklyDigestAgent
    from agents.project_mgmt.alert_agent import AlertAgent

    agents["ticket_creator"] = TicketCreatorAgent(
        mcp_clients={"jira": mcp["jira"], "slack": mcp["slack"]}
    )
    agents["wbs_updater"] = WBSUpdaterAgent(
        mcp_clients={"jira": mcp["jira"], "github": mcp["github"]}
    )
    agents["weekly_digest"] = WeeklyDigestAgent(
        mcp_clients={"slack": mcp["slack"], "confluence": mcp["confluence"]}
    )
    agents["alert_agent"] = AlertAgent(
        mcp_clients={"slack": mcp["slack"], "jira": mcp["jira"]}
    )

    # --- Knowledge Domain ---
    from agents.knowledge.minutes_publisher import MinutesPublisherAgent
    from agents.knowledge.decision_logger import DecisionLoggerAgent
    from agents.knowledge.prompt_regression import PromptRegressionAgent
    from agents.knowledge.context_packager import ContextPackagerAgent

    agents["minutes_publisher"] = MinutesPublisherAgent(
        mcp_clients={"confluence": mcp["confluence"]}
    )
    agents["decision_logger"] = DecisionLoggerAgent(
        mcp_clients={"bitbucket": mcp["bitbucket"], "github": mcp["github"]}
    )
    agents["prompt_regression"] = PromptRegressionAgent()
    agents["context_packager"] = ContextPackagerAgent(
        mcp_clients={
            "bitbucket": mcp["bitbucket"],
            "jira": mcp["jira"],
            "slack": mcp["slack"],
        }
    )

    # --- Coach Session Memory (eParts-specific) ---
    from agents.coach_memory.session_memory import SessionMemoryAgent
    from agents.coach_memory.commitment_tracker import CommitmentTrackerAgent
    from agents.coach_memory.concern_tracker import ConcernTrackerAgent
    from agents.coach_memory.briefing_generator import BriefingGeneratorAgent

    agents["session_memory"] = SessionMemoryAgent(
        mcp_clients={"vector_store": mcp["vector_store"]}
    )
    agents["commitment_tracker"] = CommitmentTrackerAgent()
    agents["concern_tracker"] = ConcernTrackerAgent()
    agents["briefing_generator"] = BriefingGeneratorAgent(
        mcp_clients={"slack": mcp["slack"]}
    )

    # --- ML Decision Memory (eParts-specific) ---
    from agents.ml_decision.decision_log import DecisionLogAgent
    from agents.ml_decision.evidence_accumulator import EvidenceAccumulatorAgent
    from agents.ml_decision.readiness_detector import ReadinessDetectorAgent
    from agents.ml_decision.coach_linker import CoachLinkerAgent

    agents["decision_log"] = DecisionLogAgent()
    agents["evidence_accumulator"] = EvidenceAccumulatorAgent()
    agents["readiness_detector"] = ReadinessDetectorAgent(
        mcp_clients={"slack": mcp["slack"]}
    )
    agents["coach_linker"] = CoachLinkerAgent(
        mcp_clients={"vector_store": mcp["vector_store"]}
    )

    # Register all agents with the task queue
    for name, agent in agents.items():
        task_queue.register_agent(name, _make_handler(agent))
        logger.info(f"Registered agent: {name}")

    logger.info(f"Agent registry complete: {len(agents)} agents registered")
    return agents
