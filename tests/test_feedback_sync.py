from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.feedback.client import FeedbackSyncClient
from app.feedback.models import RemoteFeedbackEvent


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeSession:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.requested_url: str | None = None

    def get(self, url: str, timeout: int) -> FakeResponse:
        self.requested_url = url
        assert timeout == 20
        return FakeResponse(self.payload)


def test_feedback_sync_client_parses_events() -> None:
    session = FakeSession(
        {
            "events": [
                {
                    "external_event_id": "event-1",
                    "issue_id": 2,
                    "item_id": 46,
                    "vote": "+",
                    "recipient_key": "reader-key",
                    "subject": "Briefing | 2026-03-18",
                    "item_title": "Serving benchmark",
                    "source_url": "https://example.com/item",
                    "created_at": datetime.now(tz=UTC).isoformat(),
                }
            ]
        }
    )
    client = FeedbackSyncClient(
        base_url="https://script.google.com/macros/s/test/exec",
        secret="feedback-secret",
        session=session,  # type: ignore[arg-type]
    )

    events = client.fetch_events()

    assert len(events) == 1
    assert isinstance(events[0], RemoteFeedbackEvent)
    assert session.requested_url is not None and "payload=" in session.requested_url


def test_feedback_sync_client_rejects_invalid_payload() -> None:
    session = FakeSession({"events": "not-a-list"})
    client = FeedbackSyncClient(
        base_url="https://script.google.com/macros/s/test/exec",
        secret="feedback-secret",
        session=session,  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError):
        client.fetch_events()
