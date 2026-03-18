from __future__ import annotations

import pytest

from app.llm.generate_issue import generate_issue_from_shortlist
from app.llm.schemas import NewsletterIssuePayload
from app.models import ItemFeatures, ShortlistCandidate, StoredItem
from tests.conftest import build_test_profile_context


class FakeLLMClient:
    def __init__(self, payload: NewsletterIssuePayload) -> None:
        self.payload = payload

    def generate(self, *, system_prompt: str, user_prompt: str) -> NewsletterIssuePayload:
        assert "strict JSON" in system_prompt
        assert "candidates" in user_prompt
        assert "explicit_profile" in user_prompt
        return self.payload


def _candidate(item_id: int, topic: str) -> ShortlistCandidate:
    item = StoredItem.model_validate(
        {
            "id": item_id,
            "source_id": 1,
            "external_id": str(item_id),
            "source_kind": "rss",
            "source_name": "OpenAI News",
            "topic": topic,
            "title": f"Title {item_id}",
            "normalized_title": f"title {item_id}",
            "url": f"https://example.com/{item_id}",
            "authors_json": "[]",
            "published_at": "2026-03-17T12:00:00+00:00",
            "fetched_at": "2026-03-17T12:00:00+00:00",
            "raw_summary": "Raw summary",
            "raw_payload_json": "{}",
            "content_hash": "hash",
            "content_type": "engineering_blog",
            "fit_tag": "current_work" if topic == "uq_hpc" else "llm_background",
            "relevance_for_work": 4.0 if topic == "uq_hpc" else 1.0,
            "relevance_for_llm_learning": 1.0 if topic == "uq_hpc" else 4.0,
            "applicability_score": 3.5,
            "deterministic_score": 5.0,
            "llm_score": None,
            "final_score": None,
            "selected_for_issue": False,
            "issue_id": None,
            "generated_summary": None,
            "generated_why_it_matters": None,
            "created_at": "2026-03-17T12:00:00+00:00",
            "updated_at": "2026-03-17T12:00:00+00:00",
        }
    )
    return ShortlistCandidate(
        item=item,
        features=ItemFeatures(
            item_id=item_id,
            content_type="engineering_blog",
            fit_tag="current_work" if topic == "uq_hpc" else "llm_background",
            freshness_score=4.0,
            source_quality_score=4.2,
            work_relevance_score=4.5 if topic == "uq_hpc" else 1.5,
            llm_map_value_score=1.5 if topic == "uq_hpc" else 4.5,
            architectural_tradeoff_score=1.0,
            practical_reusability_score=3.5,
            interview_background_score=1.2 if topic == "uq_hpc" else 3.4,
            repo_profile_match_score=2.1,
            traction_score=1.0,
            theoretical_penalty=0.0,
            hype_penalty=0.0,
            genericity_penalty=0.0,
            feature_json={"topic": topic},
        ),
        score=5.0,
        reasons=["freshness:+4.0"],
    )


def _valid_issue_payload() -> NewsletterIssuePayload:
    items = []
    for item_id in range(1, 5):
        items.append(
            {
                "candidate_id": str(item_id),
                "title": f"Title {item_id}",
                "what_happened": "Short analytical summary.",
                "why_you_should_care": "This connects directly to calibration workflow choices.",
                "fit_tag": "current_work",
                "source_name": "OpenAI News",
                "source_url": f"https://example.com/{item_id}",
            }
        )
    llm_items = []
    for item_id in range(5, 9):
        llm_items.append(
            {
                "candidate_id": str(item_id),
                "title": f"Title {item_id}",
                "what_happened": "Short analytical summary.",
                "why_you_should_care": "This improves your LLM systems map for interviews.",
                "fit_tag": "llm_background",
                "source_name": "OpenAI News",
                "source_url": f"https://example.com/{item_id}",
            }
        )
    return NewsletterIssuePayload.model_validate(
        {
            "subject": "Briefing | 2026-03-18",
            "intro": "Short intro.",
            "sections": [
                {"name": "Most relevant for your work", "items": items},
                {"name": "LLM engineering you should understand", "items": llm_items},
            ],
            "selection_notes": [
                "Balanced four work-relevant items with four LLM-background items."
            ],
        }
    )


def test_generate_issue_from_shortlist_validates_schema() -> None:
    payload = _valid_issue_payload()

    issue = generate_issue_from_shortlist(
        run_date=__import__("datetime").date(2026, 3, 18),
        shortlists={
            "uq_hpc": [_candidate(item_id, "uq_hpc") for item_id in range(1, 5)],
            "llm": [_candidate(item_id, "llm") for item_id in range(5, 9)],
        },
        context=build_test_profile_context(),
        llm_client=FakeLLMClient(payload),
    )

    assert issue.subject == "Briefing | 2026-03-18"
    assert sum(len(section.items) for section in issue.sections) == 8


def test_generate_issue_from_shortlist_rejects_unknown_candidate_id() -> None:
    payload = NewsletterIssuePayload.model_validate(
        {
            "subject": "Briefing | 2026-03-18",
            "intro": "Short intro.",
            "sections": [
                {
                    "name": "LLM",
                    "items": [
                        {
                            "candidate_id": "999",
                            "title": "Title",
                            "what_happened": "Summary.",
                            "why_you_should_care": "Why.",
                            "fit_tag": "llm_background",
                            "source_name": "OpenAI News",
                            "source_url": "https://example.com/999",
                        }
                    ],
                }
            ],
        }
    )

    with pytest.raises(ValueError):
        generate_issue_from_shortlist(
            run_date=__import__("datetime").date(2026, 3, 18),
            shortlists={"llm": [_candidate(item_id, "llm") for item_id in range(1, 9)]},
            context=build_test_profile_context(),
            llm_client=FakeLLMClient(payload),
        )


def test_generate_issue_from_shortlist_trims_overlong_output_to_balanced_eight() -> None:
    payload = NewsletterIssuePayload.model_validate(
        {
            "subject": "Briefing | 2026-03-18",
            "intro": "Short intro.",
            "sections": [
                {
                    "name": "Most relevant for your work",
                    "items": [
                        {
                            "candidate_id": str(item_id),
                            "title": f"Title {item_id}",
                            "what_happened": "Short analytical summary.",
                            "why_you_should_care": "Useful for calibration work.",
                            "fit_tag": "current_work",
                            "source_name": "OpenAI News",
                            "source_url": f"https://example.com/{item_id}",
                        }
                        for item_id in range(1, 6)
                    ],
                },
                {
                    "name": "LLM engineering you should understand",
                    "items": [
                        {
                            "candidate_id": str(item_id),
                            "title": f"Title {item_id}",
                            "what_happened": "Short analytical summary.",
                            "why_you_should_care": "Useful for LLM systems background.",
                            "fit_tag": "llm_background",
                            "source_name": "OpenAI News",
                            "source_url": f"https://example.com/{item_id}",
                        }
                        for item_id in range(6, 10)
                    ],
                },
            ],
        }
    )

    issue = generate_issue_from_shortlist(
        run_date=__import__("datetime").date(2026, 3, 18),
        shortlists={
            "uq_hpc": [_candidate(item_id, "uq_hpc") for item_id in range(1, 6)],
            "llm": [_candidate(item_id, "llm") for item_id in range(6, 10)],
        },
        context=build_test_profile_context(),
        llm_client=FakeLLMClient(payload),
    )

    assert sum(len(section.items) for section in issue.sections) == 8
    assert issue.sections[0].items[0].candidate_id == "1"
    assert issue.sections[1].items[-1].candidate_id == "9"
