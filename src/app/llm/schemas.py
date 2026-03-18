from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class NewsletterItemPayload(BaseModel):
    candidate_id: str
    title: str
    what_happened: str
    why_you_should_care: str
    fit_tag: Literal["current_work", "llm_background", "both"]
    source_name: str
    source_url: str
    selection_rationale: str | None = None


class NewsletterSectionPayload(BaseModel):
    name: str
    items: list[NewsletterItemPayload] = Field(default_factory=list)


class NewsletterIssuePayload(BaseModel):
    subject: str
    intro: str
    sections: list[NewsletterSectionPayload]
    selection_notes: list[str] = Field(default_factory=list)
