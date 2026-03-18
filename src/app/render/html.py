from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.feedback.models import FeedbackRenderLinks
from app.llm.schemas import NewsletterIssuePayload


def _environment() -> Environment:
    template_dir = Path(__file__).resolve().parent / "templates"
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_issue_html(
    issue: NewsletterIssuePayload,
    *,
    generated_at: datetime,
    feedback_links: Mapping[str, FeedbackRenderLinks] | None = None,
) -> str:
    template = _environment().get_template("newsletter.html.j2")
    return template.render(
        issue=issue,
        generated_at=generated_at,
        feedback_links=feedback_links or {},
    )


def render_issue_text(
    issue: NewsletterIssuePayload,
    *,
    feedback_links: Mapping[str, FeedbackRenderLinks] | None = None,
) -> str:
    lines = [issue.subject, "", issue.intro, ""]
    resolved_feedback_links = feedback_links or {}
    if issue.selection_notes:
        lines.append("Selection notes")
        lines.append("----------------")
        for note in issue.selection_notes:
            lines.append(f"- {note}")
        lines.append("")
    for section in issue.sections:
        if not section.items:
            continue
        lines.append(section.name)
        lines.append("-" * len(section.name))
        for item in section.items:
            lines.append(f"{item.title} [{item.fit_tag}]")
            lines.append(item.what_happened)
            lines.append(f"Why you should care: {item.why_you_should_care}")
            lines.append(f"Source: {item.source_name} - {item.source_url}")
            item_feedback_links = resolved_feedback_links.get(item.candidate_id)
            if item_feedback_links is not None:
                lines.append(
                    "Feedback: "
                    f"+ good rec {item_feedback_links.upvote_url} | "
                    f"- bad rec {item_feedback_links.downvote_url}"
                )
            lines.append("")
    return "\n".join(lines).strip() + "\n"
