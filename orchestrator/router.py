"""
Trigger-to-agent routing table.

Maps incoming trigger types to the agent(s) that should handle them.
The orchestrator uses this to decide which agent to dispatch for any
given webhook, cron tick, or manual invocation.

Triggered by: orchestrator/main.py on every incoming event
Outputs: list of agent names to run for the given trigger
"""

from __future__ import annotations

TRIGGER_ROUTES: dict[str, list[str]] = {
    "transcript": [
        "transcript_parser",
        "priority_classifier",
        "req_extractor",
        "drift_detector",
        "decision_logger",
    ],
    "coach_transcript": [
        "transcript_parser",
        "session_memory",
        "commitment_tracker",
        "concern_tracker",
        "coach_linker",
    ],
    "jira_webhook": [
        "wbs_updater",
        "traceability_builder",
    ],
    "pr_event": [
        "pr_reviewer",
        "traceability_builder",
        "doc_generator",
        "prompt_regression",
    ],
    "slack_event": [
        "decision_logger",
    ],
    "cron_monday_8am": [
        "stale_detector",
        "context_packager",
    ],
    "cron_friday_6pm": [
        "weekly_digest",
    ],
    "cron_6h_alert": [
        "alert_agent",
    ],
    "cron_pre_meeting": [
        "briefing_generator",
    ],
    "poc_result": [
        "evidence_accumulator",
        "readiness_detector",
    ],
    "manual": [],  # manual triggers specify the agent directly
}


def resolve_agents(trigger_type: str, agent_override: str | None = None) -> list[str]:
    """
    Return the list of agent names to run for a given trigger type.
    If agent_override is set (manual trigger), return only that agent.
    """
    if agent_override:
        return [agent_override]

    agents = TRIGGER_ROUTES.get(trigger_type, [])
    if not agents:
        return []
    return list(agents)
