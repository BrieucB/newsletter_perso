from __future__ import annotations

import json
import sqlite3
from typing import cast

from app.profile.models import LearnedPreferences, RepoProfile
from app.utils.time import utc_now


class ProfilesRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def replace_active_user_profile(self, profile_json: dict[str, object]) -> None:
        now = utc_now().isoformat()
        self.connection.execute("UPDATE user_profiles SET is_active = 0")
        self.connection.execute(
            """
            INSERT INTO user_profiles (profile_json, created_at, updated_at, is_active)
            VALUES (?, ?, ?, 1)
            """,
            (json.dumps(profile_json, sort_keys=True), now, now),
        )

    def get_active_user_profile(self) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            self.connection.execute(
                "SELECT * FROM user_profiles WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
            ).fetchone(),
        )

    def replace_active_repo_profiles(self, repo_profiles: list[RepoProfile]) -> None:
        self.connection.execute("UPDATE repo_profiles SET is_active = 0")
        for profile in repo_profiles:
            self.connection.execute(
                """
                INSERT INTO repo_profiles (
                    repo_name,
                    repo_path,
                    profile_json,
                    fingerprint_hash,
                    generated_at,
                    is_active
                )
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(repo_name, repo_path) DO UPDATE SET
                    profile_json = excluded.profile_json,
                    fingerprint_hash = excluded.fingerprint_hash,
                    generated_at = excluded.generated_at,
                    is_active = 1
                """,
                (
                    profile.repo_name,
                    profile.repo_path,
                    profile.model_dump_json(),
                    profile.fingerprint_hash,
                    utc_now().isoformat(),
                ),
            )

    def list_active_repo_profiles(self) -> list[sqlite3.Row]:
        rows = self.connection.execute(
            "SELECT * FROM repo_profiles WHERE is_active = 1 ORDER BY repo_name ASC"
        ).fetchall()
        return [cast(sqlite3.Row, row) for row in rows]

    def row_to_repo_profile(self, row: sqlite3.Row) -> RepoProfile:
        return RepoProfile.model_validate_json(row["profile_json"])

    def create_profile_snapshot(
        self,
        *,
        explicit_profile_json: dict[str, object],
        aggregated_repo_profile_json: dict[str, object],
        learned_preferences_json: dict[str, object],
    ) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO profile_snapshots (
                explicit_profile_json,
                aggregated_repo_profile_json,
                learned_preferences_json,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                json.dumps(explicit_profile_json, sort_keys=True),
                json.dumps(aggregated_repo_profile_json, sort_keys=True),
                json.dumps(learned_preferences_json, sort_keys=True),
                utc_now().isoformat(),
            ),
        )
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)

    def get_latest_profile_snapshot(self) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            self.connection.execute(
                "SELECT * FROM profile_snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone(),
        )

    def snapshot_learned_preferences(self, row: sqlite3.Row) -> LearnedPreferences:
        return LearnedPreferences.model_validate_json(row["learned_preferences_json"])
