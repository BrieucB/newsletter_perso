from __future__ import annotations

import json
from collections import defaultdict
from typing import cast

from app.profile.models import FeedbackContext, LearnedPreferences


def _bump(mapping: dict[str, float], key: str | None, delta: float) -> None:
    if not key:
        return
    mapping[key] = round(mapping.get(key, 0.0) + delta, 3)


def learn_from_feedback(
    feedback_rows: list[FeedbackContext],
    *,
    adaptation_strength: float,
) -> LearnedPreferences:
    preferences = LearnedPreferences()
    feature_deltas: dict[str, float] = defaultdict(float)

    for row in feedback_rows:
        delta = adaptation_strength if row.vote == "+" else -adaptation_strength
        _bump(preferences.source_weights, row.source_name, delta)
        _bump(preferences.content_type_weights, row.content_type, delta)
        _bump(preferences.fit_tag_weights, row.fit_tag, delta)
        _bump(preferences.section_weights, row.section_name, delta)

        feature_snapshot = row.feature_snapshot
        if feature_snapshot:
            for feature_name in (
                "practical_reusability_score",
                "architectural_tradeoff_score",
                "interview_background_score",
                "work_relevance_score",
                "llm_map_value_score",
            ):
                value = float(feature_snapshot.get(feature_name, 0.0))
                feature_deltas[feature_name] += delta * min(value / 6.0, 1.0)

        if row.vote == "+":
            tag = row.fit_tag or row.content_type or row.source_name
            if tag and tag not in preferences.positive_patterns:
                preferences.positive_patterns.append(tag)
        else:
            tag = row.fit_tag or row.content_type or row.source_name
            if tag and tag not in preferences.negative_patterns:
                preferences.negative_patterns.append(tag)

    preferences.feature_weight_adjustments = {
        key: round(value, 3) for key, value in feature_deltas.items()
    }
    preferences.tone_biases = {
        "mentor_note_to_self": round(
            len(preferences.positive_patterns) * adaptation_strength / 2.0, 3
        ),
        "avoid_hype": round(len(preferences.negative_patterns) * adaptation_strength / 2.0, 3),
    }
    return preferences


def learned_preferences_summary(preferences: LearnedPreferences) -> dict[str, object]:
    return cast(dict[str, object], json.loads(preferences.model_dump_json()))
