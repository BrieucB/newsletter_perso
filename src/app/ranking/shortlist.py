from __future__ import annotations

from collections import Counter, defaultdict

from app.models import ItemFeatures, ShortlistCandidate, StoredItem
from app.profile.models import RuntimeProfileContext
from app.ranking.rules import compute_rule_score


def score_and_shortlist(
    items: list[StoredItem],
    *,
    context: RuntimeProfileContext,
    sent_titles: set[str],
    sent_domain_titles: set[tuple[str, str]],
    max_per_topic: int,
) -> tuple[dict[int, float], dict[int, ItemFeatures], dict[str, list[ShortlistCandidate]]]:
    title_frequency = Counter(item.normalized_title for item in items)
    score_updates: dict[int, float] = {}
    feature_updates: dict[int, ItemFeatures] = {}
    buckets: dict[str, list[ShortlistCandidate]] = defaultdict(list)

    for item in items:
        rule_score = compute_rule_score(
            item,
            context=context,
            sent_titles=sent_titles,
            sent_domain_titles=sent_domain_titles,
            title_frequency=title_frequency,
        )
        score_updates[item.id] = rule_score.score
        if rule_score.features is not None:
            feature_updates[item.id] = rule_score.features
        if not rule_score.excluded:
            buckets[item.topic].append(
                ShortlistCandidate(
                    item=item,
                    features=rule_score.features or feature_updates[item.id],
                    score=rule_score.score,
                    reasons=rule_score.reasons,
                )
            )

    for topic in list(buckets):
        buckets[topic].sort(
            key=lambda candidate: (
                candidate.score,
                candidate.item.published_at or candidate.item.fetched_at,
                candidate.item.id,
            ),
            reverse=True,
        )
        buckets[topic] = buckets[topic][:max_per_topic]

    return score_updates, feature_updates, buckets
