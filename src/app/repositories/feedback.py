from __future__ import annotations

import json
import sqlite3

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
    ) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO feedback (issue_id, item_id, vote, context_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                issue_id,
                item_id,
                vote,
                json.dumps(context_json, sort_keys=True),
                utc_now().isoformat(),
            ),
        )
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)

    def list_feedback_contexts(self) -> list[FeedbackContext]:
        rows = self.connection.execute("SELECT * FROM feedback ORDER BY id ASC").fetchall()
        contexts = []
        for row in rows:
            payload = json.loads(row["context_json"])
            payload["issue_id"] = int(row["issue_id"])
            payload["item_id"] = int(row["item_id"])
            payload["vote"] = row["vote"]
            payload["created_at"] = row["created_at"]
            contexts.append(FeedbackContext.model_validate(payload))
        return contexts
