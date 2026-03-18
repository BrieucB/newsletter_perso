from __future__ import annotations

from datetime import UTC, datetime

from app.feedback.models import FeedbackRenderLinks
from app.llm.schemas import NewsletterIssuePayload
from app.render.html import render_issue_html, render_issue_text


def test_render_issue_html_contains_sections_and_links() -> None:
    issue = NewsletterIssuePayload.model_validate(
        {
            "subject": "Briefing | 2026-03-18",
            "intro": "Short intro.",
            "selection_notes": ["Balanced current-work and LLM-background items."],
            "sections": [
                {
                    "name": "LLM",
                    "items": [
                        {
                            "candidate_id": "1",
                            "title": "A useful update",
                            "what_happened": "Two short sentences.",
                            "why_you_should_care": "It changes deployment choices.",
                            "fit_tag": "both",
                            "source_name": "OpenAI News",
                            "source_url": "https://example.com/item",
                        }
                    ],
                }
            ],
        }
    )

    feedback_links = {
        "1": FeedbackRenderLinks(
            upvote_url="https://example.com/feedback/up",
            downvote_url="https://example.com/feedback/down",
        )
    }
    html = render_issue_html(
        issue,
        generated_at=datetime.now(tz=UTC),
        feedback_links=feedback_links,
    )
    text = render_issue_text(issue, feedback_links=feedback_links)

    assert "A useful update" in html
    assert "Source link" in html
    assert "+ good rec" in html
    assert "- bad rec" in html
    assert "Why you should care:" in text
    assert "[both]" in text
    assert "Feedback: + good rec https://example.com/feedback/up" in text
    assert "https://example.com/item" in text
