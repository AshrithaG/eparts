"""
Slack MCP server — all Slack interactions go through this module.

Tools exposed:
  send_message()  — post to a channel or thread
  read_channel()  — fetch recent messages from a channel
  pin_message()   — pin a message in a channel

No agent should import slack_sdk directly. Use this wrapper.
"""

from __future__ import annotations

import logging
import os

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger("mcp.slack")


class SlackMCP:
    def __init__(self, bot_token: str | None = None):
        token = bot_token or os.getenv("SLACK_BOT_TOKEN", "")
        self._client = WebClient(token=token)
        self._team_channel = os.getenv("SLACK_TEAM_CHANNEL", "")
        self._alert_channel = os.getenv("SLACK_ALERT_CHANNEL", "")

    def send_message(
        self,
        text: str,
        *,
        channel: str | None = None,
        thread_ts: str | None = None,
        blocks: list[dict] | None = None,
    ) -> dict:
        """
        Post a message to a Slack channel.
        Defaults to the team channel if no channel specified.
        Returns the Slack API response data.
        """
        target = channel or self._team_channel
        if not target:
            raise ValueError("No channel specified and SLACK_TEAM_CHANNEL not set")

        try:
            kwargs: dict = {
                "channel": target,
                "text": text,
            }
            if thread_ts:
                kwargs["thread_ts"] = thread_ts
            if blocks:
                kwargs["blocks"] = blocks

            response = self._client.chat_postMessage(**kwargs)
            logger.info(f"Message sent to {target}: ts={response['ts']}")
            return {
                "ok": True,
                "channel": target,
                "ts": response["ts"],
                "message": response.get("message", {}),
            }

        except SlackApiError as exc:
            logger.error(f"Slack send_message failed: {exc.response['error']}")
            return {
                "ok": False,
                "error": exc.response["error"],
                "channel": target,
            }

    def send_alert(self, text: str, **kwargs) -> dict:
        """Convenience: send to the alert channel."""
        return self.send_message(text, channel=self._alert_channel, **kwargs)

    def read_channel(
        self,
        channel: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """
        Fetch recent messages from a channel.
        Returns a list of message dicts.
        """
        target = channel or self._team_channel
        if not target:
            raise ValueError("No channel specified and SLACK_TEAM_CHANNEL not set")

        try:
            response = self._client.conversations_history(
                channel=target,
                limit=limit,
            )
            messages = response.get("messages", [])
            logger.info(f"Read {len(messages)} messages from {target}")
            return messages

        except SlackApiError as exc:
            logger.error(f"Slack read_channel failed: {exc.response['error']}")
            return []

    def pin_message(self, channel: str, timestamp: str) -> dict:
        """Pin a specific message by its timestamp."""
        try:
            self._client.pins_add(channel=channel, timestamp=timestamp)
            logger.info(f"Pinned message {timestamp} in {channel}")
            return {"ok": True, "channel": channel, "ts": timestamp}

        except SlackApiError as exc:
            logger.error(f"Slack pin_message failed: {exc.response['error']}")
            return {"ok": False, "error": exc.response["error"]}
