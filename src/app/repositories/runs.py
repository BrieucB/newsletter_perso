from __future__ import annotations

import json
import sqlite3

from app.utils.time import utc_now


class PipelineRunsRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create_run(self, *, status: str = "running") -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO pipeline_runs (started_at, status, logs_json)
            VALUES (?, ?, ?)
            """,
            (utc_now().isoformat(), status, json.dumps([])),
        )
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        fetched_count: int,
        shortlisted_count: int,
        selected_count: int,
        logs: list[str],
    ) -> None:
        self.connection.execute(
            """
            UPDATE pipeline_runs
            SET finished_at = ?,
                status = ?,
                fetched_count = ?,
                shortlisted_count = ?,
                selected_count = ?,
                logs_json = ?
            WHERE id = ?
            """,
            (
                utc_now().isoformat(),
                status,
                fetched_count,
                shortlisted_count,
                selected_count,
                json.dumps(logs),
                run_id,
            ),
        )

    def fail_run(
        self,
        run_id: int,
        *,
        error_message: str,
        fetched_count: int,
        shortlisted_count: int,
        selected_count: int,
        logs: list[str],
    ) -> None:
        self.connection.execute(
            """
            UPDATE pipeline_runs
            SET finished_at = ?,
                status = 'failed',
                fetched_count = ?,
                shortlisted_count = ?,
                selected_count = ?,
                error_message = ?,
                logs_json = ?
            WHERE id = ?
            """,
            (
                utc_now().isoformat(),
                fetched_count,
                shortlisted_count,
                selected_count,
                error_message,
                json.dumps(logs),
                run_id,
            ),
        )
