from __future__ import annotations

from datetime import date
from itertools import combinations
from typing import Any

from app.llm.prompts import SYSTEM_PROMPT, build_generation_prompt
from app.llm.schemas import NewsletterIssuePayload, NewsletterItemPayload, NewsletterSectionPayload
from app.models import ShortlistCandidate
from app.profile.models import RuntimeProfileContext


def _candidate_payload(candidate: ShortlistCandidate) -> dict[str, Any]:
    item = candidate.item
    return {
        "candidate_id": str(item.id),
        "topic": item.topic,
        "title": item.title,
        "source_name": item.source_name,
        "source_url": item.url,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "deterministic_score": candidate.score,
        "raw_summary": item.raw_summary,
        "authors_json": item.authors_json,
        "content_type": candidate.features.content_type,
        "suggested_fit_tag": candidate.features.fit_tag,
        "feature_snapshot": candidate.features.model_dump(mode="json"),
        "rule_reasons": candidate.reasons,
    }


def _validate_issue_payload(
    issue: NewsletterIssuePayload,
    *,
    available_candidate_ids: set[str],
) -> NewsletterIssuePayload:
    seen_candidate_ids: set[str] = set()
    total_items = 0
    work_balance = 0
    llm_balance = 0
    for section in issue.sections:
        if not section.name.strip():
            raise ValueError("Section names must be non-empty.")
        for item in section.items:
            if item.candidate_id not in available_candidate_ids:
                raise ValueError(f"LLM selected unknown candidate_id: {item.candidate_id}")
            if item.candidate_id in seen_candidate_ids:
                raise ValueError(f"Duplicate candidate_id in output: {item.candidate_id}")
            seen_candidate_ids.add(item.candidate_id)
            total_items += 1
            if item.fit_tag in {"current_work", "both"}:
                work_balance += 1
            if item.fit_tag in {"llm_background", "both"}:
                llm_balance += 1
    if total_items != 8:
        raise ValueError(f"Expected exactly 8 selected items, got {total_items}")
    if work_balance < 4 or llm_balance < 4:
        raise ValueError(
            "Issue balance is too skewed; expected at least 4 work-relevant "
            "and 4 llm-relevant item counts."
        )
    return issue


def _item_balance(item: NewsletterItemPayload) -> tuple[int, int]:
    work = 1 if item.fit_tag in {"current_work", "both"} else 0
    llm = 1 if item.fit_tag in {"llm_background", "both"} else 0
    return work, llm


def _normalize_issue_payload(issue: NewsletterIssuePayload) -> NewsletterIssuePayload:
    flattened: list[tuple[int, str, NewsletterItemPayload]] = []
    seen_candidate_ids: set[str] = set()
    dropped_duplicates = False

    for section in issue.sections:
        for item in section.items:
            if item.candidate_id in seen_candidate_ids:
                dropped_duplicates = True
                continue
            seen_candidate_ids.add(item.candidate_id)
            flattened.append((len(flattened), section.name, item))

    if not dropped_duplicates and len(flattened) <= 8:
        return issue

    candidate_combinations = (
        combinations(range(len(flattened)), 8)
        if len(flattened) > 8
        else [tuple(range(len(flattened)))]
    )
    selected_combo: tuple[int, ...] | None = None
    best_score: tuple[int, int] | None = None

    for combo in candidate_combinations:
        if len(combo) != 8:
            continue
        work_balance = llm_balance = 0
        for index in combo:
            work, llm = _item_balance(flattened[index][2])
            work_balance += work
            llm_balance += llm
        if work_balance < 4 or llm_balance < 4:
            continue
        score = (sum(combo), combo[-1])
        if best_score is None or score < best_score:
            best_score = score
            selected_combo = combo

    if selected_combo is None:
        return issue

    selected_indices = set(selected_combo)
    section_items: dict[str, list[NewsletterItemPayload]] = {}
    for index, section_name, item in flattened:
        if index not in selected_indices:
            continue
        section_items.setdefault(section_name, []).append(item)

    return issue.model_copy(
        update={
            "sections": [
                NewsletterSectionPayload(
                    name=section.name,
                    items=section_items.get(section.name, []),
                )
                for section in issue.sections
                if section_items.get(section.name)
            ]
        }
    )


def generate_issue_from_shortlist(
    *,
    run_date: date,
    shortlists: dict[str, list[ShortlistCandidate]],
    context: RuntimeProfileContext,
    llm_client: Any,
) -> NewsletterIssuePayload:
    candidates = [
        _candidate_payload(candidate) for bucket in shortlists.values() for candidate in bucket
    ]
    if not candidates:
        raise ValueError("No shortlisted candidates available for issue generation.")

    issue = llm_client.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_generation_prompt(
            run_date=run_date,
            candidates=candidates,
            explicit_profile=context.explicit_profile.model_dump(mode="json"),
            aggregated_repo_profile=context.aggregated_repo_profile.model_dump(mode="json"),
            learned_preferences=context.learned_preferences.model_dump(mode="json"),
        ),
    )
    issue = _normalize_issue_payload(issue)
    return _validate_issue_payload(
        issue, available_candidate_ids={candidate["candidate_id"] for candidate in candidates}
    )
