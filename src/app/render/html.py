from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.llm.schemas import NewsletterIssuePayload


def _environment() -> Environment:
    template_dir = Path(__file__).resolve().parent / "templates"
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_issue_html(issue: NewsletterIssuePayload, *, generated_at: datetime) -> str:
    template = _environment().get_template("newsletter.html.j2")
    return template.render(issue=issue, generated_at=generated_at)


def render_issue_text(issue: NewsletterIssuePayload) -> str:
    lines = [issue.subject, "", issue.intro, ""]
    for section in issue.sections:
        if not section.items:
            continue
        lines.append(section.name)
        lines.append("-" * len(section.name))
        for item in section.items:
            lines.append(item.title)
            lines.append(item.summary)
            lines.append(f"Why it matters: {item.why_it_matters}")
            lines.append(f"Source: {item.source_name} - {item.source_url}")
            lines.append("")
    return "\n".join(lines).strip() + "\n"
