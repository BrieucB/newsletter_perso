from __future__ import annotations

import pytest

from app.llm.generate_issue import generate_issue_from_shortlist
from app.llm.schemas import NewsletterIssuePayload
from app.models import ShortlistCandidate, StoredItem


class FakeLLMClient:
    def __init__(self, payload: NewsletterIssuePayload) -> None:
        self.payload = payload

    def generate(self, *, system_prompt: str, user_prompt: str) -> NewsletterIssuePayload:
        assert "strict JSON" in system_prompt
        assert "candidates" in user_prompt
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
    return ShortlistCandidate(item=item, score=5.0, reasons=["freshness:+4.0"])


def test_generate_issue_from_shortlist_validates_schema() -> None:
    payload = NewsletterIssuePayload.model_validate(
        {
            "subject": "Briefing | 2026-03-18",
            "intro": "Short intro.",
            "sections": [
                {
                    "name": "UQ / HPC",
                    "items": [
                        {
                            "candidate_id": "1",
                            "title": "Title 1",
                            "summary": "Summary.",
                            "why_it_matters": "Because it changes practice.",
                            "source_name": "OpenAI News",
                            "source_url": "https://example.com/1",
                        }
                    ],
                }
            ],
        }
    )

    issue = generate_issue_from_shortlist(
        run_date=__import__("datetime").date(2026, 3, 18),
        shortlists={"uq_hpc": [_candidate(1, "uq_hpc")]},
        llm_client=FakeLLMClient(payload),
    )

    assert issue.subject == "Briefing | 2026-03-18"


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
                            "summary": "Summary.",
                            "why_it_matters": "Why.",
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
            shortlists={"llm": [_candidate(1, "llm")]},
            llm_client=FakeLLMClient(payload),
        )
