from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models import StoredItem
from app.ranking.rules import (
    _freshness_score,
    _genericity_penalty,
    _hype_penalty,
    _payload,
    _payload_int,
    _source_quality_score,
    _theoretical_penalty,
    _traction_score,
    compute_rule_score,
    infer_content_type,
    infer_fit_tag,
)
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


def test_rule_helpers_cover_content_type_and_penalties() -> None:
    now = datetime.now(tz=UTC)
    release_item = _stored_item(
        item_id=4,
        title="Release note: benchmark changelog",
        summary="changelog",
        topic="llm",
        published_delta_days=2,
    ).model_copy(
        update={
            "url": "https://example.com/releases/v1",
            "raw_payload_json": '{"query":"engineering"}',
        }
    )
    other_item = release_item.model_copy(
        update={
            "id": 5,
            "source_kind": "other",
            "url": "https://example.com/page",
            "title": "New model",
            "raw_summary": None,
            "raw_payload_json": "not-json",
        }
    )
    github_item = release_item.model_copy(
        update={
            "id": 6,
            "source_kind": "github_search",
            "raw_payload_json": '{"stargazers_count":"120","forks_count":"11"}',
            "title": "Revolutionary trade-off benchmark",
            "url": "https://linkedin.example.com/post",
        }
    )

    assert infer_content_type(release_item) == "release_note"
    assert infer_content_type(github_item) == "tool_or_repo"
    assert infer_content_type(other_item) == "other"
    assert _payload(other_item) == {}
    assert _payload_int({"ok": True}, "ok") == 1
    assert _payload_int({"stars": "120"}, "stars") == 120
    assert _payload_int({"stars": "oops"}, "stars") == 0
    assert _freshness_score(release_item, now=now) == 3.8
    assert _source_quality_score(github_item, content_type="tool_or_repo") >= 2.2
    assert _traction_score(github_item, content_type="tool_or_repo") == 2.2
    assert _hype_penalty(github_item, haystack="revolutionary new model dropped") >= 3.3
    assert _genericity_penalty(other_item, haystack="new model") >= 2.4
    assert infer_fit_tag(work_score=2.0, llm_score=2.1) == "both"


def test_compute_rule_score_exclusion_paths() -> None:
    theoretical_item = _stored_item(
        item_id=7,
        title="Posterior contraction theorem",
        summary="Proof and theorem for posterior contraction formalism.",
        topic="uq_hpc",
        published_delta_days=1,
    ).model_copy(
        update={
            "source_kind": "arxiv",
            "source_name": "arXiv: Bayesian calibration",
            "url": "https://arxiv.org/abs/7",
        }
    )
    duplicate_title_item = _stored_item(
        item_id=8,
        title="Useful applied title",
        summary="GPU workflow details.",
        topic="llm",
        published_delta_days=1,
    )

    same_domain_score = compute_rule_score(
        duplicate_title_item,
        context=build_test_profile_context(),
        sent_titles=set(),
        sent_domain_titles={("example.com", duplicate_title_item.normalized_title)},
        title_frequency={duplicate_title_item.normalized_title: 1},
    )
    theoretical_score = compute_rule_score(
        theoretical_item,
        context=build_test_profile_context(),
        sent_titles=set(),
        sent_domain_titles=set(),
        title_frequency={theoretical_item.normalized_title: 1},
    )
    duplicate_score = compute_rule_score(
        duplicate_title_item,
        context=build_test_profile_context(),
        sent_titles=set(),
        sent_domain_titles=set(),
        title_frequency={duplicate_title_item.normalized_title: 2},
    )

    assert same_domain_score.reasons == ["same-domain-same-title"]
    assert theoretical_score.excluded is True
    assert "overly-theoretical-without-applied-angle" in theoretical_score.reasons
    assert duplicate_score.excluded is True
    assert "near-duplicate-title" in duplicate_score.reasons


@pytest.mark.parametrize(
    ("content_type", "haystack", "expected"),
    [
        ("paper", "theorem proof formalism", 2.4),
        ("engineering_blog", "workflow benchmark", 0.0),
    ],
)
def test_theoretical_penalty_varies_by_content_type(
    content_type: str, haystack: str, expected: float
) -> None:
    item = _stored_item(
        item_id=9,
        title="Title",
        summary="summary",
        topic="uq_hpc",
        published_delta_days=1,
    )

    assert _theoretical_penalty(item, content_type=content_type, haystack=haystack) == expected
