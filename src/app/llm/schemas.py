from __future__ import annotations

from pydantic import BaseModel, Field


class NewsletterItemPayload(BaseModel):
    candidate_id: str
    title: str
    summary: str
    why_it_matters: str
    source_name: str
    source_url: str


class NewsletterSectionPayload(BaseModel):
    name: str
    items: list[NewsletterItemPayload] = Field(default_factory=list)


class NewsletterIssuePayload(BaseModel):
    subject: str
    intro: str
    sections: list[NewsletterSectionPayload]
