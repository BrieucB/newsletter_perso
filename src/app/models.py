from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Topic = Literal["uq_hpc", "llm"]


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
    deterministic_score: float | None = None
    llm_score: float | None = None
    final_score: float | None = None
    selected_for_issue: bool = False
    issue_id: int | None = None
    generated_summary: str | None = None
    generated_why_it_matters: str | None = None
    created_at: datetime
    updated_at: datetime


class RuleScore(BaseModel):
    score: float
    excluded: bool = False
    reasons: list[str] = Field(default_factory=list)


class ShortlistCandidate(BaseModel):
    item: StoredItem
    score: float
    reasons: list[str] = Field(default_factory=list)
