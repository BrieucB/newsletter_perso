from __future__ import annotations

from datetime import date
from typing import Any

from app.llm.prompts import SYSTEM_PROMPT, build_generation_prompt
from app.llm.schemas import NewsletterIssuePayload
from app.models import ShortlistCandidate

TOPIC_TO_SECTION = {
    "uq_hpc": "UQ / HPC",
    "llm": "LLM",
}

MAX_ITEMS_PER_SECTION = {
    "UQ / HPC": 5,
    "LLM": 5,
    "Worth watching": 1,
}


def _candidate_payload(candidate: ShortlistCandidate) -> dict[str, Any]:
    item = candidate.item
    return {
        "candidate_id": str(item.id),
        "topic": item.topic,
        "target_section": TOPIC_TO_SECTION[item.topic],
        "title": item.title,
        "source_name": item.source_name,
        "source_url": item.url,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "deterministic_score": candidate.score,
        "raw_summary": item.raw_summary,
        "authors_json": item.authors_json,
        "rule_reasons": candidate.reasons,
    }


def _validate_issue_payload(
    issue: NewsletterIssuePayload,
    *,
    available_candidate_ids: set[str],
) -> NewsletterIssuePayload:
    seen_candidate_ids: set[str] = set()
    for section in issue.sections:
        if section.name not in MAX_ITEMS_PER_SECTION:
            raise ValueError(f"Unexpected section name: {section.name}")
        if len(section.items) > MAX_ITEMS_PER_SECTION[section.name]:
            raise ValueError(f"Too many items in section: {section.name}")
        for item in section.items:
            if item.candidate_id not in available_candidate_ids:
                raise ValueError(f"LLM selected unknown candidate_id: {item.candidate_id}")
            if item.candidate_id in seen_candidate_ids:
                raise ValueError(f"Duplicate candidate_id in output: {item.candidate_id}")
            seen_candidate_ids.add(item.candidate_id)
    return issue


def generate_issue_from_shortlist(
    *,
    run_date: date,
    shortlists: dict[str, list[ShortlistCandidate]],
    llm_client: Any,
) -> NewsletterIssuePayload:
    candidates = [
        _candidate_payload(candidate) for bucket in shortlists.values() for candidate in bucket
    ]
    if not candidates:
        raise ValueError("No shortlisted candidates available for issue generation.")

    issue = llm_client.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_generation_prompt(run_date=run_date, candidates=candidates),
    )
    return _validate_issue_payload(
        issue, available_candidate_ids={candidate["candidate_id"] for candidate in candidates}
    )
