from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast
from urllib.parse import urlparse

from app.models import ContentType, FitTag, ItemFeatures, RuleScore, StoredItem
from app.profile.models import RuntimeProfileContext
from app.utils.text import content_snippet, url_domain

CONTENT_TYPE_PRIORITY = {
    "engineering_blog": 2.6,
    "tool_or_repo": 2.2,
    "paper": 1.6,
    "release_note": 1.2,
    "news": 0.8,
    "other": 0.3,
}

OFFICIAL_DOMAINS = {
    "openai.com",
    "anthropic.com",
    "huggingface.co",
    "developers.googleblog.com",
    "deepmind.google",
    "github.com",
    "arxiv.org",
}

MAJOR_LLM_PLAYERS = {
    "openai",
    "anthropic",
    "google",
    "deepmind",
    "meta",
    "mistral",
    "vllm",
    "llama.cpp",
    "dspy",
    "litellm",
    "serving",
    "inference",
    "rag",
    "eval",
    "standard",
}

PRACTICAL_TERMS = {
    "workflow",
    "serving",
    "deployment",
    "benchmark",
    "implementation",
    "library",
    "repo",
    "tool",
    "gpu",
    "parallel",
    "calibration",
    "surrogate",
    "inference",
    "cluster",
}

THEORETICAL_TERMS = {
    "theorem",
    "proof",
    "asymptotic",
    "formalism",
    "lemma",
    "posterior contraction",
}

HYPE_TERMS = {
    "breakthrough",
    "revolutionary",
    "game changing",
    "world class",
    "state of the art",
    "magical",
    "incredible",
    "new model dropped",
}

GENERIC_TITLE_PHRASES = {
    "update",
    "release notes",
    "news",
    "announcing",
    "introducing",
}


def _payload(item: StoredItem) -> dict[str, object]:
    try:
        payload = json.loads(item.raw_payload_json)
    except json.JSONDecodeError:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _text_haystack(item: StoredItem) -> str:
    payload = _payload(item)
    payload_text = " ".join(
        str(value) for value in payload.values() if isinstance(value, (str, int, float))
    )
    return f"{item.title} {item.raw_summary or ''} {payload_text}".lower()


def _count_matches(haystack: str, phrases: list[str] | set[str]) -> int:
    return sum(1 for phrase in phrases if phrase in haystack)


def infer_content_type(item: StoredItem) -> str:
    payload = _payload(item)
    path = urlparse(item.url).path.lower()
    summary = (item.raw_summary or "").lower()

    if item.source_kind == "arxiv":
        return "paper"
    if item.source_kind in {"github_repo", "github_search"}:
        return "tool_or_repo"
    if "/releases" in path or "release note" in item.title.lower() or "changelog" in summary:
        return "release_note"
    if any(token in path for token in ("/blog", "/news", "/posts")):
        return "engineering_blog"
    if payload.get("query") or "engineering" in item.source_name.lower():
        return "engineering_blog"
    if item.source_kind == "rss":
        return "engineering_blog"
    return "other"


def _payload_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _freshness_score(item: StoredItem, *, now: datetime) -> float:
    published_at = item.published_at or item.fetched_at
    age_days = max((now - published_at).total_seconds() / 86400.0, 0.0)
    if age_days <= 1:
        return 4.5
    if age_days <= 3:
        return 3.8
    if age_days <= 7:
        return 2.8
    if age_days <= 14:
        return 1.6
    return 0.5


def _source_quality_score(item: StoredItem, *, content_type: str) -> float:
    domain = url_domain(item.url)
    score = CONTENT_TYPE_PRIORITY.get(content_type, 0.3)
    if domain in OFFICIAL_DOMAINS or any(domain.endswith(f".{root}") for root in OFFICIAL_DOMAINS):
        score += 1.6
    if item.source_kind == "arxiv":
        score += 1.2
    if item.source_kind == "github_repo":
        score += 1.0
    return round(min(score, 5.5), 3)


def _profile_match_score(haystack: str, keywords: list[str]) -> float:
    if not keywords:
        return 0.0
    matches = sum(1 for keyword in keywords if keyword.lower() in haystack)
    return round(min(matches * 0.7, 4.0), 3)


def _work_relevance_score(item: StoredItem, context: RuntimeProfileContext, haystack: str) -> float:
    profile_terms = (
        context.explicit_profile.work_priorities + context.aggregated_repo_profile.workflow_markers
    )
    repo_terms = (
        context.aggregated_repo_profile.scientific_domains
        + context.aggregated_repo_profile.engineering_themes
    )
    score = _profile_match_score(haystack, profile_terms + repo_terms)
    if item.topic == "uq_hpc":
        score += 1.2
    if any(marker in haystack for marker in ("gpu", "cuda", "slurm", "calibration", "surrogate")):
        score += 0.8
    return round(min(score, 6.0), 3)


def _llm_map_value_score(item: StoredItem, context: RuntimeProfileContext, haystack: str) -> float:
    terms = context.explicit_profile.llm_learning_goals + list(MAJOR_LLM_PLAYERS)
    score = _profile_match_score(haystack, terms)
    if item.topic == "llm":
        score += 1.2
    if any(marker in haystack for marker in ("architecture", "serving", "eval", "standard", "api")):
        score += 0.8
    return round(min(score, 6.0), 3)


def _architectural_tradeoff_score(haystack: str) -> float:
    keywords = [
        "trade-off",
        "tradeoff",
        "latency",
        "throughput",
        "serving",
        "scaling",
        "architecture",
        "memory",
        "benchmark",
        "cost",
    ]
    matches = _count_matches(haystack, keywords)
    return round(min(matches * 0.8, 4.5), 3)


def _practical_reusability_score(item: StoredItem, *, content_type: str, haystack: str) -> float:
    matches = _count_matches(haystack, PRACTICAL_TERMS)
    score = matches * 0.6 + (0.8 if content_type in {"engineering_blog", "tool_or_repo"} else 0.0)
    if content_snippet(item.raw_summary, limit=220):
        score += 0.4
    return round(min(score, 5.0), 3)


def _interview_background_score(item: StoredItem, *, haystack: str) -> float:
    matches = _count_matches(haystack, MAJOR_LLM_PLAYERS)
    if item.topic == "llm" and any(
        keyword in haystack for keyword in ("architecture", "standard", "ecosystem", "players")
    ):
        matches += 2
    return round(min(matches * 0.7, 4.5), 3)


def _repo_profile_match_score(context: RuntimeProfileContext, haystack: str) -> float:
    weighted_keywords = list(context.aggregated_repo_profile.keyword_weights.keys())
    return _profile_match_score(haystack, weighted_keywords)


def _traction_score(item: StoredItem, *, content_type: str) -> float:
    payload = _payload(item)
    stars = _payload_int(payload, "stargazers_count")
    forks = _payload_int(payload, "forks_count")
    if content_type == "tool_or_repo":
        if stars >= 10_000:
            return 4.0
        if stars >= 1_000:
            return 3.2
        if stars >= 100:
            return 2.2
        if stars >= 30 or forks >= 10:
            return 1.2
        return 0.2
    if url_domain(item.url) in OFFICIAL_DOMAINS:
        return 2.4
    return 0.8


def _theoretical_penalty(item: StoredItem, *, content_type: str, haystack: str) -> float:
    if content_type != "paper":
        return 0.0
    theoretical_matches = _count_matches(haystack, THEORETICAL_TERMS)
    practical_matches = _count_matches(haystack, PRACTICAL_TERMS)
    if theoretical_matches == 0:
        return 0.0
    return round(max(theoretical_matches * 0.8 - practical_matches * 0.4, 0.0), 3)


def _hype_penalty(item: StoredItem, *, haystack: str) -> float:
    penalty = _count_matches(haystack, HYPE_TERMS) * 0.8
    if "linkedin" in item.url.lower():
        penalty += 2.5
    return round(min(penalty, 4.0), 3)


def _genericity_penalty(item: StoredItem, *, haystack: str) -> float:
    penalty = 0.0
    title = item.title.strip().lower()
    if len(title.split()) < 4 or title in GENERIC_TITLE_PHRASES:
        penalty += 1.4
    if not item.raw_summary:
        penalty += 1.0
    if "new model" in haystack and _count_matches(haystack, PRACTICAL_TERMS) == 0:
        penalty += 1.1
    return round(min(penalty, 4.0), 3)


def infer_fit_tag(*, work_score: float, llm_score: float) -> FitTag:
    if abs(work_score - llm_score) <= 0.9:
        return "both"
    if work_score > llm_score:
        return "current_work"
    return "llm_background"


def _build_features(
    item: StoredItem,
    context: RuntimeProfileContext,
    *,
    now: datetime,
) -> ItemFeatures:
    haystack = _text_haystack(item)
    content_type = cast(ContentType, infer_content_type(item))
    work_relevance = _work_relevance_score(item, context, haystack)
    llm_map_value = _llm_map_value_score(item, context, haystack)
    practical_reuse = _practical_reusability_score(
        item,
        content_type=content_type,
        haystack=haystack,
    )
    fit_tag = infer_fit_tag(work_score=work_relevance, llm_score=llm_map_value)
    features = ItemFeatures(
        item_id=item.id,
        content_type=content_type,
        fit_tag=fit_tag,
        freshness_score=_freshness_score(item, now=now),
        source_quality_score=_source_quality_score(item, content_type=content_type),
        work_relevance_score=work_relevance,
        llm_map_value_score=llm_map_value,
        architectural_tradeoff_score=_architectural_tradeoff_score(haystack),
        practical_reusability_score=practical_reuse,
        interview_background_score=_interview_background_score(item, haystack=haystack),
        repo_profile_match_score=_repo_profile_match_score(context, haystack),
        traction_score=_traction_score(item, content_type=content_type),
        theoretical_penalty=_theoretical_penalty(
            item,
            content_type=content_type,
            haystack=haystack,
        ),
        hype_penalty=_hype_penalty(item, haystack=haystack),
        genericity_penalty=_genericity_penalty(item, haystack=haystack),
        feature_json={
            "content_type": content_type,
            "fit_tag": fit_tag,
            "source_domain": url_domain(item.url),
            "title": item.title,
        },
    )
    return features


def _apply_learned_weighting(
    features: ItemFeatures,
    item: StoredItem,
    context: RuntimeProfileContext,
) -> float:
    learned = context.learned_preferences
    score = features.pre_score
    score += learned.source_weights.get(item.source_name, 0.0)
    score += learned.content_type_weights.get(features.content_type, 0.0)
    score += learned.fit_tag_weights.get(features.fit_tag, 0.0)
    for feature_name, adjustment in learned.feature_weight_adjustments.items():
        if hasattr(features, feature_name):
            score += adjustment * float(getattr(features, feature_name))
    return round(score, 3)


def _hard_exclusion_reasons(
    item: StoredItem,
    *,
    features: ItemFeatures,
    title_frequency: dict[str, int],
) -> list[str]:
    reasons: list[str] = []
    if title_frequency.get(item.normalized_title, 0) > 1:
        reasons.append("near-duplicate-title")
    if "linkedin" in item.url.lower():
        reasons.append("linkedin-style-marketing")
    if (
        features.content_type == "tool_or_repo"
        and item.source_kind == "github_search"
        and features.traction_score < 1.0
    ):
        reasons.append("tiny-low-traction-open-source")
    if features.theoretical_penalty >= 2.4 and features.practical_reusability_score < 1.5:
        reasons.append("overly-theoretical-without-applied-angle")
    if features.hype_penalty >= 2.4 and features.source_quality_score < 3.0:
        reasons.append("low-signal-hype")
    if (
        features.genericity_penalty >= 2.0
        and features.architectural_tradeoff_score < 1.0
        and features.practical_reusability_score < 1.0
    ):
        reasons.append("generic-without-substance")
    return reasons


def compute_rule_score(
    item: StoredItem,
    *,
    context: RuntimeProfileContext,
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
    features = _build_features(item, context, now=resolved_now)
    exclusion_reasons = _hard_exclusion_reasons(
        item,
        features=features,
        title_frequency=title_frequency,
    )
    if exclusion_reasons:
        return RuleScore(
            score=-500.0,
            excluded=True,
            reasons=exclusion_reasons,
            features=features,
        )

    final_score = _apply_learned_weighting(features, item, context)
    reasons = [
        f"content_type:{features.content_type}",
        f"fit_tag:{features.fit_tag}",
        f"work:{features.work_relevance_score:.1f}",
        f"llm:{features.llm_map_value_score:.1f}",
        f"practical:{features.practical_reusability_score:.1f}",
        f"architecture:{features.architectural_tradeoff_score:.1f}",
    ]
    return RuleScore(score=final_score, excluded=False, reasons=reasons, features=features)
