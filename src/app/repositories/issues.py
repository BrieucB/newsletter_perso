from __future__ import annotations

import json
import sqlite3
from typing import Any, cast

from app.utils.time import utc_now


class IssuesRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get_by_subject(self, subject: str) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            self.connection.execute(
                "SELECT * FROM issues WHERE subject = ? ORDER BY id DESC LIMIT 1",
                (subject,),
            ).fetchone(),
        )

    def create_issue(
        self,
        *,
        run_at: str,
        subject: str,
        model_name: str,
        status: str,
        html_body: str,
        json_payload: dict[str, Any],
    ) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO issues (
                run_at,
                subject,
                model_name,
                status,
                html_body,
                json_payload,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_at,
                subject,
                model_name,
                status,
                html_body,
                json.dumps(json_payload, sort_keys=True),
                utc_now().isoformat(),
            ),
        )
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)

    def update_status(self, issue_id: int, *, status: str) -> None:
        sent_at = utc_now().isoformat() if status == "sent" else None
        self.connection.execute(
            """
            UPDATE issues
            SET status = ?, sent_at = COALESCE(?, sent_at)
            WHERE id = ?
            """,
            (status, sent_at, issue_id),
        )

    def update_html_body(self, issue_id: int, *, html_body: str) -> None:
        self.connection.execute(
            """
            UPDATE issues
            SET html_body = ?
            WHERE id = ?
            """,
            (html_body, issue_id),
        )

    def get_issue(self, issue_id: int) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            self.connection.execute(
                "SELECT * FROM issues WHERE id = ?",
                (issue_id,),
            ).fetchone(),
        )
