from __future__ import annotations

import requests

from app.feedback.models import RemoteFeedbackEvent
from app.feedback.signing import build_sync_url


class FeedbackSyncClient:
    def __init__(
        self,
        *,
        base_url: str,
        secret: str,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url
        self.secret = secret
        self.session = session or requests.Session()

    def fetch_events(self) -> list[RemoteFeedbackEvent]:
        response = self.session.get(
            build_sync_url(base_url=self.base_url, secret=self.secret),
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Feedback sync response must be a JSON object.")
        events = payload.get("events", [])
        if not isinstance(events, list):
            raise ValueError("Feedback sync response must contain a list of events.")
        parsed_events: list[RemoteFeedbackEvent] = []
        for event in events:
            if not isinstance(event, dict):
                raise ValueError("Feedback event entries must be objects.")
            parsed_events.append(RemoteFeedbackEvent.model_validate(event))
        return parsed_events
