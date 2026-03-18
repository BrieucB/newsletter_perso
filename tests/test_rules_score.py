from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models import StoredItem
from app.ranking.rules import compute_rule_score
from tests.conftest import build_test_profile_context


def _stored_item(
    *, item_id: int, title: str, summary: str | None, topic: str, published_delta_days: int
) -> StoredItem:
    now = datetime.now(tz=UTC)
    return StoredItem(
        id=item_id,
        source_id=1,
        external_id=str(item_id),
        source_kind="rss",
        source_name="OpenAI News",
        topic=topic,  # type: ignore[arg-type]
        title=title,
        normalized_title=title.lower(),
        url=f"https://example.com/{item_id}",
        authors_json="[]",
        published_at=now - timedelta(days=published_delta_days),
        fetched_at=now,
        raw_summary=summary,
        raw_payload_json="{}",
        content_hash=str(item_id),
        deterministic_score=None,
        llm_score=None,
        final_score=None,
        selected_for_issue=False,
        issue_id=None,
        generated_summary=None,
        generated_why_it_matters=None,
        created_at=now,
        updated_at=now,
    )


def test_compute_rule_score_prefers_fresh_keyword_rich_items() -> None:
    strong = _stored_item(
        item_id=1,
        title="OpenAI evals update for LLM inference serving",
        summary="Covers eval workflows for inference serving.",
        topic="llm",
        published_delta_days=0,
    )
    weak = _stored_item(
        item_id=2,
        title="Update",
        summary=None,
        topic="llm",
        published_delta_days=20,
    )

    strong_score = compute_rule_score(
        strong,
        context=build_test_profile_context(),
        sent_titles=set(),
        sent_domain_titles=set(),
        title_frequency={strong.normalized_title: 1, weak.normalized_title: 1},
    )
    weak_score = compute_rule_score(
        weak,
        context=build_test_profile_context(),
        sent_titles=set(),
        sent_domain_titles=set(),
        title_frequency={strong.normalized_title: 1, weak.normalized_title: 1},
    )

    assert strong_score.excluded is False
    assert strong_score.score > weak_score.score
    assert strong_score.features is not None
    assert strong_score.features.fit_tag == "llm_background"
    assert strong_score.features.content_type == "engineering_blog"


def test_compute_rule_score_excludes_exact_sent_titles() -> None:
    item = _stored_item(
        item_id=3,
        title="Repeated title",
        summary="summary",
        topic="llm",
        published_delta_days=1,
    )

    score = compute_rule_score(
        item,
        context=build_test_profile_context(),
        sent_titles={item.normalized_title},
        sent_domain_titles=set(),
        title_frequency={item.normalized_title: 1},
    )

    assert score.excluded is True
    assert score.score == -1000.0
