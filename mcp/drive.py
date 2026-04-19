"""
Google Drive MCP server — polls for new transcript files.

Tools exposed:
  list_files()    — list files in the transcript folder
  read_file()     — download a file's content
  watch_folder()  — check for new files since last poll

Used by: Transcript parser (polls every 15 min for new .vtt files)
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("mcp.drive")


class DriveMCP:
    def __init__(
        self,
        service_account_json: str | None = None,
        folder_id: str | None = None,
    ):
        self._sa_json = service_account_json or os.getenv("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON", "")
        self._folder_id = folder_id or os.getenv("GOOGLE_DRIVE_TRANSCRIPT_FOLDER_ID", "")
        self._service = None

        if self._sa_json and self._folder_id:
            self._init_service()
        else:
            logger.warning("Drive MCP initialized without credentials — offline mode")

    def _init_service(self) -> None:
        """Initialize the Google Drive API service."""
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            credentials = service_account.Credentials.from_service_account_file(
                self._sa_json,
                scopes=["https://www.googleapis.com/auth/drive.readonly"],
            )
            self._service = build("drive", "v3", credentials=credentials)
        except Exception as exc:
            logger.error(f"Drive service init failed: {exc}")

    def list_files(
        self,
        folder_id: str | None = None,
        mime_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """List files in the transcript folder."""
        if not self._service:
            return []

        fid = folder_id or self._folder_id
        query = f"'{fid}' in parents and trashed = false"
        if mime_type:
            query += f" and mimeType = '{mime_type}'"

        try:
            results = self._service.files().list(
                q=query,
                fields="files(id, name, mimeType, modifiedTime, createdTime)",
                orderBy="modifiedTime desc",
            ).execute()
            return results.get("files", [])
        except Exception as exc:
            logger.error(f"Drive list_files failed: {exc}")
            return []

    def read_file(self, file_id: str) -> str:
        """Download a file's text content."""
        if not self._service:
            return ""

        try:
            content = self._service.files().get_media(fileId=file_id).execute()
            return content.decode("utf-8") if isinstance(content, bytes) else str(content)
        except Exception as exc:
            logger.error(f"Drive read_file failed: {exc}")
            return ""

    def watch_folder(self, since: str | None = None) -> list[dict[str, Any]]:
        """
        Check for new files since a given timestamp.
        Returns list of new files added since `since` (ISO format).
        """
        if not self._service:
            return []

        query = f"'{self._folder_id}' in parents and trashed = false"
        if since:
            query += f" and modifiedTime > '{since}'"

        try:
            results = self._service.files().list(
                q=query,
                fields="files(id, name, mimeType, modifiedTime)",
                orderBy="modifiedTime desc",
            ).execute()
            files = results.get("files", [])
            logger.info(f"Watch folder: {len(files)} new file(s) since {since}")
            return files
        except Exception as exc:
            logger.error(f"Drive watch_folder failed: {exc}")
            return []
