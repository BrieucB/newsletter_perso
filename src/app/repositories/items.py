from __future__ import annotations

import json
import sqlite3
from typing import Any, cast

from app.models import ItemFeatures, NormalizedItem, StoredItem
from app.utils.text import url_domain
from app.utils.time import parse_iso8601, to_iso8601, utc_now


def _row_to_item(row: sqlite3.Row) -> StoredItem:
    payload = dict(row)
    payload["published_at"] = parse_iso8601(payload["published_at"])
    payload["fetched_at"] = parse_iso8601(payload["fetched_at"])
    payload["created_at"] = parse_iso8601(payload["created_at"])
    payload["updated_at"] = parse_iso8601(payload["updated_at"])
    payload["selected_for_issue"] = bool(payload["selected_for_issue"])
    return StoredItem.model_validate(payload)


class ItemsRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def ensure_source(
        self,
        *,
        kind: str,
        name: str,
        config: dict[str, Any],
        is_enabled: bool = True,
    ) -> int:
        created_at = utc_now().isoformat()
        config_json = json.dumps(config, sort_keys=True)
        self.connection.execute(
            """
            INSERT INTO sources (kind, name, config_json, is_enabled, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(kind, name) DO UPDATE SET
                config_json = excluded.config_json,
                is_enabled = excluded.is_enabled
            """,
            (kind, name, config_json, int(is_enabled), created_at),
        )
        row = self.connection.execute(
            "SELECT id FROM sources WHERE kind = ? AND name = ?",
            (kind, name),
        ).fetchone()
        assert row is not None
        return int(row["id"])

    def find_duplicate_id(
        self,
        *,
        url: str,
        normalized_title: str,
        content_hash: str,
    ) -> int | None:
        row = self.connection.execute(
            """
            SELECT id
            FROM items
            WHERE url = ?
               OR normalized_title = ?
               OR content_hash = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (url, normalized_title, content_hash),
        ).fetchone()
        return int(row["id"]) if row else None

    def upsert_normalized_item(
        self,
        *,
        source_id: int,
        normalized_item: NormalizedItem,
        normalized_title: str,
        content_hash: str,
    ) -> int:
        now = utc_now().isoformat()
        duplicate_id = self.find_duplicate_id(
            url=normalized_item.url,
            normalized_title=normalized_title,
            content_hash=content_hash,
        )
        authors_json = json.dumps(normalized_item.authors)
        raw_payload_json = json.dumps(normalized_item.raw_payload, sort_keys=True)
        if duplicate_id is not None:
            self.connection.execute(
                """
                UPDATE items
                SET source_id = ?,
                    external_id = ?,
                    source_kind = ?,
                    source_name = ?,
                    topic = ?,
                    title = ?,
                    normalized_title = ?,
                    url = ?,
                    authors_json = ?,
                    published_at = ?,
                    fetched_at = ?,
                    raw_summary = ?,
                    raw_payload_json = ?,
                    content_hash = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    source_id,
                    normalized_item.external_id,
                    normalized_item.source_kind,
                    normalized_item.source_name,
                    normalized_item.topic,
                    normalized_item.title,
                    normalized_title,
                    normalized_item.url,
                    authors_json,
                    to_iso8601(normalized_item.published_at),
                    now,
                    normalized_item.raw_summary,
                    raw_payload_json,
                    content_hash,
                    now,
                    duplicate_id,
                ),
            )
            return duplicate_id

        cursor = self.connection.execute(
            """
            INSERT INTO items (
                source_id,
                external_id,
                source_kind,
                source_name,
                topic,
                title,
                normalized_title,
                url,
                authors_json,
                published_at,
                fetched_at,
                raw_summary,
                raw_payload_json,
                content_hash,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                normalized_item.external_id,
                normalized_item.source_kind,
                normalized_item.source_name,
                normalized_item.topic,
                normalized_item.title,
                normalized_title,
                normalized_item.url,
                authors_json,
                to_iso8601(normalized_item.published_at),
                now,
                normalized_item.raw_summary,
                raw_payload_json,
                content_hash,
                now,
                now,
            ),
        )
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)

    def list_recent_candidates(self, *, topic: str, limit: int = 200) -> list[StoredItem]:
        rows = self.connection.execute(
            """
            SELECT i.*
            FROM items AS i
            WHERE i.topic = ?
              AND i.id NOT IN (
                  SELECT ii.item_id
                  FROM issue_items AS ii
                  JOIN issues AS iss ON iss.id = ii.issue_id
                  WHERE iss.status = 'sent'
              )
            ORDER BY COALESCE(i.published_at, i.fetched_at) DESC, i.id DESC
            LIMIT ?
            """,
            (topic, limit),
        ).fetchall()
        return [_row_to_item(row) for row in rows]

    def list_shortlist_candidates(self, *, topic: str, limit: int) -> list[StoredItem]:
        rows = self.connection.execute(
            """
            SELECT i.*
            FROM items AS i
            WHERE i.topic = ?
              AND i.deterministic_score IS NOT NULL
              AND i.id NOT IN (
                  SELECT ii.item_id
                  FROM issue_items AS ii
                  JOIN issues AS iss ON iss.id = ii.issue_id
                  WHERE iss.status = 'sent'
              )
            ORDER BY i.deterministic_score DESC, COALESCE(i.published_at, i.fetched_at) DESC
            LIMIT ?
            """,
            (topic, limit),
        ).fetchall()
        return [_row_to_item(row) for row in rows]

    def update_scores(self, score_updates: dict[int, float]) -> None:
        now = utc_now().isoformat()
        for item_id, score in score_updates.items():
            self.connection.execute(
                """
                UPDATE items
                SET deterministic_score = ?, updated_at = ?
                WHERE id = ?
                """,
                (score, now, item_id),
            )

    def update_personalization_fields(
        self,
        *,
        features_by_item_id: dict[int, ItemFeatures],
        score_updates: dict[int, float],
    ) -> None:
        now = utc_now().isoformat()
        for item_id, features in features_by_item_id.items():
            self.connection.execute(
                """
                UPDATE items
                SET content_type = ?,
                    fit_tag = ?,
                    relevance_for_work = ?,
                    relevance_for_llm_learning = ?,
                    applicability_score = ?,
                    deterministic_score = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    features.content_type,
                    features.fit_tag,
                    features.work_relevance_score,
                    features.llm_map_value_score,
                    features.practical_reusability_score,
                    score_updates[item_id],
                    now,
                    item_id,
                ),
            )

    def recent_sent_titles(self) -> set[str]:
        rows = self.connection.execute(
            """
            SELECT i.normalized_title
            FROM items AS i
            JOIN issues AS iss ON iss.id = i.issue_id
            WHERE iss.status = 'sent'
            """,
        ).fetchall()
        return {str(row["normalized_title"]) for row in rows}

    def recent_sent_domain_titles(self) -> set[tuple[str, str]]:
        rows = self.connection.execute(
            """
            SELECT i.url, i.normalized_title
            FROM items AS i
            JOIN issues AS iss ON iss.id = i.issue_id
            WHERE iss.status = 'sent'
            """,
        ).fetchall()
        return {(url_domain(str(row["url"])), str(row["normalized_title"])) for row in rows}

    def get_items_by_ids(self, item_ids: list[int]) -> list[StoredItem]:
        if not item_ids:
            return []
        placeholders = ",".join("?" for _ in item_ids)
        rows = self.connection.execute(
            f"SELECT * FROM items WHERE id IN ({placeholders})",
            item_ids,
        ).fetchall()
        return [_row_to_item(row) for row in rows]

    def get_item(self, item_id: int) -> StoredItem | None:
        row = self.connection.execute(
            "SELECT * FROM items WHERE id = ?",
            (item_id,),
        ).fetchone()
        return _row_to_item(row) if row else None

    def get_latest_issue_context_for_item(self, item_id: int) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            self.connection.execute(
                """
                SELECT ii.issue_id, ii.section_name, iss.subject, iss.status
                FROM issue_items AS ii
                JOIN issues AS iss ON iss.id = ii.issue_id
                WHERE ii.item_id = ?
                ORDER BY ii.id DESC
                LIMIT 1
                """,
                (item_id,),
            ).fetchone(),
        )

    def list_issue_items(self, issue_id: int) -> list[sqlite3.Row]:
        return self.connection.execute(
            """
            SELECT ii.section_name, ii.rank_in_section, i.*
            FROM issue_items AS ii
            JOIN items AS i ON i.id = ii.item_id
            WHERE ii.issue_id = ?
            ORDER BY ii.section_name ASC, ii.rank_in_section ASC
            """,
            (issue_id,),
        ).fetchall()

    def attach_generated_content(
        self,
        *,
        issue_id: int,
        section_name: str,
        rank_in_section: int,
        item_id: int,
        generated_summary: str,
        generated_why_it_matters: str,
        fit_tag: str,
        selection_reason_json: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO issue_items (issue_id, item_id, section_name, rank_in_section)
            VALUES (?, ?, ?, ?)
            """,
            (issue_id, item_id, section_name, rank_in_section),
        )
        self.connection.execute(
            """
            UPDATE items
            SET selected_for_issue = 1,
                issue_id = ?,
                generated_summary = ?,
                generated_why_it_matters = ?,
                why_you_should_care_generated = ?,
                fit_tag = ?,
                selection_reason_json = ?,
                final_score = COALESCE(llm_score, deterministic_score),
                updated_at = ?
            WHERE id = ?
            """,
            (
                issue_id,
                generated_summary,
                generated_why_it_matters,
                generated_why_it_matters,
                fit_tag,
                selection_reason_json,
                utc_now().isoformat(),
                item_id,
            ),
        )
