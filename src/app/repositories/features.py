from __future__ import annotations

import json
import sqlite3

from app.models import ItemFeatures
from app.utils.time import parse_iso8601, utc_now


class FeaturesRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def upsert_item_features(self, features: ItemFeatures) -> None:
        feature_payload = features.model_dump(
            mode="json",
            exclude={"item_id", "created_at"},
        )
        created_at = utc_now().isoformat()
        self.connection.execute(
            """
            INSERT INTO item_features (
                item_id,
                freshness_score,
                source_quality_score,
                work_relevance_score,
                llm_map_value_score,
                architectural_tradeoff_score,
                practical_reusability_score,
                interview_background_score,
                repo_profile_match_score,
                traction_score,
                theoretical_penalty,
                hype_penalty,
                genericity_penalty,
                feature_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_id) DO UPDATE SET
                freshness_score = excluded.freshness_score,
                source_quality_score = excluded.source_quality_score,
                work_relevance_score = excluded.work_relevance_score,
                llm_map_value_score = excluded.llm_map_value_score,
                architectural_tradeoff_score = excluded.architectural_tradeoff_score,
                practical_reusability_score = excluded.practical_reusability_score,
                interview_background_score = excluded.interview_background_score,
                repo_profile_match_score = excluded.repo_profile_match_score,
                traction_score = excluded.traction_score,
                theoretical_penalty = excluded.theoretical_penalty,
                hype_penalty = excluded.hype_penalty,
                genericity_penalty = excluded.genericity_penalty,
                feature_json = excluded.feature_json,
                created_at = excluded.created_at
            """,
            (
                features.item_id,
                features.freshness_score,
                features.source_quality_score,
                features.work_relevance_score,
                features.llm_map_value_score,
                features.architectural_tradeoff_score,
                features.practical_reusability_score,
                features.interview_background_score,
                features.repo_profile_match_score,
                features.traction_score,
                features.theoretical_penalty,
                features.hype_penalty,
                features.genericity_penalty,
                json.dumps(feature_payload, sort_keys=True),
                created_at,
            ),
        )

    def get_item_features(self, item_id: int) -> ItemFeatures | None:
        row = self.connection.execute(
            "SELECT * FROM item_features WHERE item_id = ?",
            (item_id,),
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["feature_json"])
        payload["item_id"] = int(row["item_id"])
        payload["created_at"] = parse_iso8601(row["created_at"])
        return ItemFeatures.model_validate(payload)
