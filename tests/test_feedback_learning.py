from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.db import connect, init_db
from app.models import NormalizedItem
from app.profile.learning import learn_from_feedback
from app.repositories.feedback import FeedbackRepository
from app.repositories.issues import IssuesRepository
from app.repositories.items import ItemsRepository
from app.utils.hashing import stable_hash
from app.utils.text import normalize_title


def test_feedback_write_read_and_learning(tmp_path: Path) -> None:
    db_path = tmp_path / "feedback.sqlite3"
    init_db(db_path)
    connection = connect(db_path)
    items_repository = ItemsRepository(connection)
    issues_repository = IssuesRepository(connection)
    repository = FeedbackRepository(connection)
    source_id = items_repository.ensure_source(
        kind="rss",
        name="OpenAI News",
        config={"source_name": "OpenAI News", "source_kind": "rss"},
    )
    normalized_item = NormalizedItem(
        topic="llm",
        source_kind="rss",
        source_name="OpenAI News",
        external_id="rss-1",
        title="Serving benchmark update",
        url="https://example.com/1",
        authors=[],
        published_at=datetime.now(tz=UTC),
        raw_summary="Engineering update.",
        raw_payload={"feed_url": "https://example.com/feed.xml"},
        tags=["evals"],
    )
    item_id = items_repository.upsert_normalized_item(
        source_id=source_id,
        normalized_item=normalized_item,
        normalized_title=normalize_title(normalized_item.title),
        content_hash=stable_hash(
            [normalized_item.title, normalized_item.raw_summary or "", normalized_item.url]
        ),
    )
    issue_id = issues_repository.create_issue(
        run_at=datetime.now(tz=UTC).isoformat(),
        subject="Briefing | 2026-03-18",
        model_name="gpt-5.4-mini",
        status="drafted",
        html_body="<p>preview</p>",
        json_payload={"subject": "Briefing | 2026-03-18", "intro": "", "sections": []},
    )

    repository.record_feedback(
        issue_id=issue_id,
        item_id=item_id,
        vote="+",
        channel="cli",
        recipient_key="reader-key",
        external_event_id="event-1",
        context_json={
            "source_name": "OpenAI News",
            "topic": "llm",
            "content_type": "engineering_blog",
            "fit_tag": "both",
            "section_name": "LLM engineering you should understand",
            "feature_snapshot": {
                "practical_reusability_score": 4.8,
                "architectural_tradeoff_score": 3.4,
                "interview_background_score": 3.2,
                "work_relevance_score": 2.5,
                "llm_map_value_score": 4.9,
            },
        },
    )
    repository.record_feedback(
        issue_id=issue_id,
        item_id=item_id,
        vote="-",
        channel="email_link",
        recipient_key="reader-key",
        external_event_id="event-2",
        context_json={
            "source_name": "Generic Source",
            "topic": "llm",
            "content_type": "other",
            "fit_tag": "llm_background",
            "section_name": "Could be useful later",
            "feature_snapshot": {
                "practical_reusability_score": 0.8,
                "architectural_tradeoff_score": 0.4,
                "interview_background_score": 0.5,
                "work_relevance_score": 0.2,
                "llm_map_value_score": 1.0,
            },
        },
    )

    feedback_rows = repository.list_feedback_contexts()
    effective_feedback_rows = repository.list_effective_feedback_contexts()
    preferences = learn_from_feedback(effective_feedback_rows, adaptation_strength=0.2)

    assert len(feedback_rows) == 2
    assert len(effective_feedback_rows) == 1
    assert effective_feedback_rows[0].vote == "-"
    assert preferences.source_weights["Generic Source"] == -0.2
    assert preferences.content_type_weights["other"] == -0.2
    assert preferences.fit_tag_weights["llm_background"] == -0.2
    assert "llm_background" in preferences.negative_patterns
    assert preferences.feature_weight_adjustments["practical_reusability_score"] < 0
