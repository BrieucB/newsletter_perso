from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator


class FeedbackVotePayload(BaseModel):
    action: Literal["vote"] = "vote"
    issue_id: int
    item_id: int
    vote: Literal["+", "-"]
    recipient_key: str
    subject: str
    item_title: str
    source_url: str
    expires_at: datetime


class FeedbackSyncPayload(BaseModel):
    action: Literal["sync"] = "sync"
    requested_at: datetime


class RemoteFeedbackEvent(BaseModel):
    external_event_id: str
    issue_id: int
    item_id: int
    vote: Literal["+", "-"]
    recipient_key: str
    created_at: datetime
    subject: str | None = None
    item_title: str | None = None
    source_url: str | None = None

    @field_validator("vote", mode="before")
    @classmethod
    def normalize_vote(cls, value: object) -> str:
        if not isinstance(value, str):
            raise TypeError("Feedback vote must be a string.")
        normalized = value.strip().upper()
        if normalized in {"+", "POSITIVE"}:
            return "+"
        if normalized in {"-", "NEGATIVE"}:
            return "-"
        raise ValueError("Feedback vote must be one of +, -, POSITIVE, or NEGATIVE.")


class FeedbackRenderLinks(BaseModel):
    upvote_url: str
    downvote_url: str
