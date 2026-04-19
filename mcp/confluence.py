"""
Confluence MCP server — all Confluence interactions go through this module.

Tools exposed:
  create_page()  — create a new page under a parent
  update_page()  — update an existing page's content
  get_page()     — fetch a page by ID or title

No agent should call Confluence APIs directly. Use this wrapper.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from atlassian import Confluence

logger = logging.getLogger("mcp.confluence")


class ConfluenceMCP:
    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
    ):
        self._url = url or os.getenv("CONFLUENCE_URL", "")
        self._token = token or os.getenv("CONFLUENCE_TOKEN", "")
        self._space_key = os.getenv("CONFLUENCE_SPACE_KEY", "")

        if self._url and self._token:
            self._client = Confluence(url=self._url, token=self._token, cloud=True)
        else:
            self._client = None
            logger.warning("Confluence MCP initialized without credentials — offline mode")

    def create_page(
        self,
        title: str,
        body: str,
        parent_id: str | None = None,
        space_key: str | None = None,
    ) -> dict[str, Any]:
        """Create a new Confluence page."""
        if not self._client:
            return {"ok": False, "error": "Confluence not configured"}

        space = space_key or self._space_key
        try:
            result = self._client.create_page(
                space=space,
                title=title,
                body=body,
                parent_id=parent_id,
                type="page",
                representation="storage",
            )
            page_id = result.get("id", "")
            logger.info(f"Page created: {title} (id={page_id})")
            return {"ok": True, "page_id": page_id, "title": title}
        except Exception as exc:
            logger.error(f"Confluence create_page failed: {exc}")
            return {"ok": False, "error": str(exc)}

    def update_page(
        self,
        page_id: str,
        title: str,
        body: str,
    ) -> dict[str, Any]:
        """Update an existing Confluence page."""
        if not self._client:
            return {"ok": False, "error": "Confluence not configured"}

        try:
            self._client.update_page(
                page_id=page_id,
                title=title,
                body=body,
                representation="storage",
            )
            logger.info(f"Page updated: {title} (id={page_id})")
            return {"ok": True, "page_id": page_id, "title": title}
        except Exception as exc:
            logger.error(f"Confluence update_page failed: {exc}")
            return {"ok": False, "error": str(exc)}

    def get_page(
        self,
        title: str | None = None,
        page_id: str | None = None,
        space_key: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a page by title or ID."""
        if not self._client:
            return {"ok": False, "error": "Confluence not configured"}

        space = space_key or self._space_key
        try:
            if page_id:
                result = self._client.get_page_by_id(page_id, expand="body.storage")
            elif title:
                result = self._client.get_page_by_title(space=space, title=title)
            else:
                return {"ok": False, "error": "Provide title or page_id"}

            if result:
                return {
                    "ok": True,
                    "page_id": result.get("id"),
                    "title": result.get("title"),
                    "body": result.get("body", {}).get("storage", {}).get("value", ""),
                }
            return {"ok": False, "error": "Page not found"}
        except Exception as exc:
            logger.error(f"Confluence get_page failed: {exc}")
            return {"ok": False, "error": str(exc)}
