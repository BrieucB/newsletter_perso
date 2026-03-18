from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.settings import ExplicitProfileConfig


class RepoProfile(BaseModel):
    repo_name: str
    repo_path: str
    detected_languages: list[str] = Field(default_factory=list)
    detected_libraries_tools: list[str] = Field(default_factory=list)
    inferred_scientific_domains: list[str] = Field(default_factory=list)
    inferred_engineering_themes: list[str] = Field(default_factory=list)
    inferred_infra_themes: list[str] = Field(default_factory=list)
    workflow_markers: list[str] = Field(default_factory=list)
    summary: str
    keywords: list[str] = Field(default_factory=list)
    confidence_by_theme: dict[str, float] = Field(default_factory=dict)
    fingerprint_hash: str


class AggregatedRepoProfile(BaseModel):
    repo_count: int = 0
    scientific_domains: list[str] = Field(default_factory=list)
    engineering_themes: list[str] = Field(default_factory=list)
    infra_themes: list[str] = Field(default_factory=list)
    workflow_markers: list[str] = Field(default_factory=list)
    libraries_tools: list[str] = Field(default_factory=list)
    dominant_languages: list[str] = Field(default_factory=list)
    summary: str = "No active repo profile available."
    keyword_weights: dict[str, float] = Field(default_factory=dict)


class LearnedPreferences(BaseModel):
    source_weights: dict[str, float] = Field(default_factory=dict)
    content_type_weights: dict[str, float] = Field(default_factory=dict)
    fit_tag_weights: dict[str, float] = Field(default_factory=dict)
    section_weights: dict[str, float] = Field(default_factory=dict)
    feature_weight_adjustments: dict[str, float] = Field(default_factory=dict)
    tone_biases: dict[str, float] = Field(default_factory=dict)
    negative_patterns: list[str] = Field(default_factory=list)
    positive_patterns: list[str] = Field(default_factory=list)


class RuntimeProfileContext(BaseModel):
    explicit_profile: ExplicitProfileConfig
    aggregated_repo_profile: AggregatedRepoProfile = Field(default_factory=AggregatedRepoProfile)
    learned_preferences: LearnedPreferences = Field(default_factory=LearnedPreferences)


class RepoScanResult(BaseModel):
    repo_name: str
    repo_path: Path
    text_fragments: list[str] = Field(default_factory=list)
    file_names: list[str] = Field(default_factory=list)
    commit_messages: list[str] = Field(default_factory=list)
    languages: dict[str, int] = Field(default_factory=dict)
    tools: dict[str, int] = Field(default_factory=dict)
    markers: dict[str, int] = Field(default_factory=dict)
    scientific_domains: dict[str, int] = Field(default_factory=dict)
    engineering_themes: dict[str, int] = Field(default_factory=dict)
    infra_themes: dict[str, int] = Field(default_factory=dict)


class FeedbackContext(BaseModel):
    issue_id: int
    item_id: int
    vote: str
    source_name: str
    topic: str
    content_type: str | None = None
    fit_tag: str | None = None
    section_name: str | None = None
    feature_snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
