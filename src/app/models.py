from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Topic = Literal["uq_hpc", "llm"]
FitTag = Literal["current_work", "llm_background", "both"]
ContentType = Literal[
    "engineering_blog",
    "tool_or_repo",
    "paper",
    "release_note",
    "news",
    "other",
]


class NormalizedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: Topic
    source_kind: str
    source_name: str
    external_id: str
    title: str
    url: str
    authors: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    raw_summary: str | None = None
    raw_payload: dict[str, Any]
    tags: list[str] = Field(default_factory=list)


class StoredItem(BaseModel):
    id: int
    source_id: int
    external_id: str
    source_kind: str
    source_name: str
    topic: Topic
    title: str
    normalized_title: str
    url: str
    authors_json: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime
    raw_summary: str | None = None
    raw_payload_json: str
    content_hash: str
    content_type: str | None = None
    fit_tag: FitTag | None = None
    relevance_for_work: float | None = None
    relevance_for_llm_learning: float | None = None
    applicability_score: float | None = None
    deterministic_score: float | None = None
    llm_score: float | None = None
    final_score: float | None = None
    selected_for_issue: bool = False
    issue_id: int | None = None
    generated_summary: str | None = None
    generated_why_it_matters: str | None = None
    why_you_should_care_generated: str | None = None
    selection_reason_json: str | None = None
    created_at: datetime
    updated_at: datetime


class ItemFeatures(BaseModel):
    item_id: int
    content_type: ContentType
    fit_tag: FitTag
    freshness_score: float
    source_quality_score: float
    work_relevance_score: float
    llm_map_value_score: float
    architectural_tradeoff_score: float
    practical_reusability_score: float
    interview_background_score: float
    repo_profile_match_score: float
    traction_score: float
    theoretical_penalty: float
    hype_penalty: float
    genericity_penalty: float
    feature_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None

    @property
    def pre_score(self) -> float:
        return round(
            self.freshness_score
            + self.source_quality_score
            + self.work_relevance_score
            + self.llm_map_value_score
            + self.architectural_tradeoff_score
            + self.practical_reusability_score
            + self.interview_background_score
            + self.repo_profile_match_score
            + self.traction_score
            - self.theoretical_penalty
            - self.hype_penalty
            - self.genericity_penalty,
            3,
        )


class RuleScore(BaseModel):
    score: float
    excluded: bool = False
    reasons: list[str] = Field(default_factory=list)
    features: ItemFeatures | None = None


class ShortlistCandidate(BaseModel):
    item: StoredItem
    features: ItemFeatures
    score: float
    reasons: list[str] = Field(default_factory=list)
