from __future__ import annotations

import json
from datetime import date

from app.llm.prompts import build_generation_prompt
from tests.conftest import build_test_profile_context


def test_build_generation_prompt_includes_personalization_context() -> None:
    context = build_test_profile_context()
    prompt = build_generation_prompt(
        run_date=date(2026, 3, 18),
        candidates=[
            {
                "candidate_id": "1",
                "topic": "llm",
                "title": "Serving benchmark",
                "source_name": "OpenAI News",
                "source_url": "https://example.com/1",
                "content_type": "engineering_blog",
                "suggested_fit_tag": "both",
                "feature_snapshot": {"practical_reusability_score": 4.2},
                "rule_reasons": ["content_type:engineering_blog"],
            }
        ],
        explicit_profile=context.explicit_profile.model_dump(mode="json"),
        aggregated_repo_profile=context.aggregated_repo_profile.model_dump(mode="json"),
        learned_preferences=context.learned_preferences.model_dump(mode="json"),
    )
    payload = json.loads(prompt)

    assert payload["instructions"]["required_total_items"] == 8
    assert payload["explicit_profile"]["tone"] == "mentor_note_to_self"
    assert "bayesian inference" in payload["aggregated_repo_profile"]["scientific_domains"]
    assert payload["learned_preferences"]["content_type_weights"]["engineering_blog"] == 0.3
