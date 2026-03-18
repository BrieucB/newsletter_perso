from __future__ import annotations

from datetime import UTC, datetime

from app.models import RuleScore, StoredItem
from app.utils.text import url_domain

TOPIC_KEYWORDS = {
    "uq_hpc": {
        "simulation-based inference",
        "bayesian",
        "surrogate",
        "uncertainty quantification",
        "inverse problem",
        "mcmc",
        "gaussian process",
        "neural operator",
        "high-performance computing",
        "gpu",
        "microbubble",
    },
    "llm": {
        "llm",
        "inference",
        "serving",
        "agent",
        "rag",
        "prompt",
        "eval",
        "evaluation",
        "openai-compatible",
        "release",
        "gpu",
        "api",
    },
}

OFFICIAL_SOURCE_BONUS = {
    "OpenAI News": 2.8,
    "Anthropic News": 2.8,
    "Hugging Face Blog": 2.2,
}

KIND_BONUS = {
    "arxiv": 1.8,
    "github_repo": 1.6,
    "github_search": 0.9,
    "rss": 2.0,
}

GENERIC_TITLE_PHRASES = {
    "update",
    "release notes",
    "news",
    "announcing",
}


def _freshness_bonus(item: StoredItem, *, now: datetime) -> tuple[float, str]:
    published_at = item.published_at or item.fetched_at
    age_days = max((now - published_at).total_seconds() / 86400.0, 0.0)
    if age_days <= 1:
        return 4.0, "freshness:+4.0"
    if age_days <= 3:
        return 3.0, "freshness:+3.0"
    if age_days <= 7:
        return 2.0, "freshness:+2.0"
    if age_days <= 14:
        return 1.0, "freshness:+1.0"
    return 0.25, "freshness:+0.25"


def _source_bonus(item: StoredItem) -> tuple[float, str]:
    bonus = KIND_BONUS.get(item.source_kind, 0.5) + OFFICIAL_SOURCE_BONUS.get(item.source_name, 0.0)
    return bonus, f"source:+{bonus:.1f}"


def _keyword_bonus(item: StoredItem) -> tuple[float, str]:
    haystack = f"{item.title} {item.raw_summary or ''}".lower()
    matches = sum(1 for keyword in TOPIC_KEYWORDS[item.topic] if keyword in haystack)
    bonus = min(matches * 0.7, 3.5)
    return bonus, f"keywords:+{bonus:.1f}"


def _generic_penalty(item: StoredItem) -> tuple[float, str]:
    title = item.title.strip().lower()
    token_count = len(title.split())
    if token_count < 4 or title in GENERIC_TITLE_PHRASES:
        return -1.4, "generic:-1.4"
    return 0.0, "generic:+0.0"


def _missing_summary_penalty(item: StoredItem) -> tuple[float, str]:
    if item.raw_summary:
        return 0.0, "summary:+0.0"
    return -1.0, "summary:-1.0"


def _duplicate_penalty(item: StoredItem, title_frequency: dict[str, int]) -> tuple[float, str]:
    if title_frequency.get(item.normalized_title, 0) > 1:
        return -2.0, "duplicates:-2.0"
    return 0.0, "duplicates:+0.0"


def compute_rule_score(
    item: StoredItem,
    *,
    sent_titles: set[str],
    sent_domain_titles: set[tuple[str, str]],
    title_frequency: dict[str, int],
    now: datetime | None = None,
) -> RuleScore:
    if item.normalized_title in sent_titles:
        return RuleScore(score=-1000.0, excluded=True, reasons=["exact-title-already-sent"])

    domain_signature = (url_domain(item.url), item.normalized_title)
    if domain_signature in sent_domain_titles:
        return RuleScore(score=-1000.0, excluded=True, reasons=["same-domain-same-title"])

    resolved_now = now or datetime.now(tz=UTC)
    parts = [
        _freshness_bonus(item, now=resolved_now),
        _source_bonus(item),
        _keyword_bonus(item),
        _duplicate_penalty(item, title_frequency),
        _generic_penalty(item),
        _missing_summary_penalty(item),
    ]
    score = round(sum(part[0] for part in parts), 3)
    return RuleScore(score=score, excluded=False, reasons=[part[1] for part in parts])
