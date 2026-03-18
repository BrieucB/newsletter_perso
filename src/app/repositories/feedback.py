from __future__ import annotations

import json
import sqlite3
from uuid import uuid4

from app.profile.models import FeedbackContext
from app.utils.time import utc_now


class FeedbackRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def record_feedback(
        self,
        *,
        issue_id: int,
        item_id: int,
        vote: str,
        context_json: dict[str, object],
        channel: str = "cli",
        recipient_key: str | None = None,
        external_event_id: str | None = None,
        created_at: str | None = None,
    ) -> int:
        resolved_event_id = external_event_id or str(uuid4())
        resolved_created_at = created_at or utc_now().isoformat()
        cursor = self.connection.execute(
            """
            INSERT INTO feedback (
                issue_id,
                item_id,
                vote,
                external_event_id,
                channel,
                recipient_key,
                context_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                issue_id,
                item_id,
                vote,
                resolved_event_id,
                channel,
                recipient_key,
                json.dumps(context_json, sort_keys=True),
                resolved_created_at,
            ),
        )
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)

    def upsert_feedback_event(
        self,
        *,
        issue_id: int,
        item_id: int,
        vote: str,
        external_event_id: str,
        channel: str,
        recipient_key: str | None,
        context_json: dict[str, object],
        created_at: str,
    ) -> bool:
        cursor = self.connection.execute(
            """
            INSERT INTO feedback (
                issue_id,
                item_id,
                vote,
                external_event_id,
                channel,
                recipient_key,
                context_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(external_event_id) DO NOTHING
            """,
            (
                issue_id,
                item_id,
                vote,
                external_event_id,
                channel,
                recipient_key,
                json.dumps(context_json, sort_keys=True),
                created_at,
            ),
        )
        return cursor.rowcount > 0

    def list_feedback_contexts(self) -> list[FeedbackContext]:
        rows = self.connection.execute(
            "SELECT * FROM feedback ORDER BY created_at ASC, id ASC"
        ).fetchall()
        contexts = []
        for row in rows:
            payload = json.loads(row["context_json"])
            payload["issue_id"] = int(row["issue_id"])
            payload["item_id"] = int(row["item_id"])
            payload["vote"] = row["vote"]
            payload["external_event_id"] = row["external_event_id"]
            payload["channel"] = row["channel"]
            payload["recipient_key"] = row["recipient_key"]
            payload["created_at"] = row["created_at"]
            contexts.append(FeedbackContext.model_validate(payload))
        return contexts

    def list_effective_feedback_contexts(self) -> list[FeedbackContext]:
        latest_by_key: dict[tuple[int, int, str], FeedbackContext] = {}
        for context in self.list_feedback_contexts():
            key = (context.issue_id, context.item_id, context.recipient_key or "")
            latest_by_key[key] = context
        return sorted(
            latest_by_key.values(),
            key=lambda context: context.created_at or utc_now(),
        )
