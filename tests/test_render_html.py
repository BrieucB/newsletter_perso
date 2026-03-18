from __future__ import annotations

from datetime import UTC, datetime

from app.llm.schemas import NewsletterIssuePayload
from app.render.html import render_issue_html, render_issue_text


def test_render_issue_html_contains_sections_and_links() -> None:
    issue = NewsletterIssuePayload.model_validate(
        {
            "subject": "Briefing | 2026-03-18",
            "intro": "Short intro.",
            "sections": [
                {
                    "name": "LLM",
                    "items": [
                        {
                            "candidate_id": "1",
                            "title": "A useful update",
                            "summary": "Two short sentences.",
                            "why_it_matters": "It changes deployment choices.",
                            "source_name": "OpenAI News",
                            "source_url": "https://example.com/item",
                        }
                    ],
                }
            ],
        }
    )

    html = render_issue_html(issue, generated_at=datetime.now(tz=UTC))
    text = render_issue_text(issue)

    assert "A useful update" in html
    assert "Source link" in html
    assert "Why it matters:" in text
    assert "https://example.com/item" in text
