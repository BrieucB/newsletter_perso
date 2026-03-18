from __future__ import annotations

from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest

from app.feedback.signing import (
    build_feedback_url,
    build_signed_token,
    verify_feedback_vote,
    verify_signed_token,
)
from app.utils.time import utc_now


def _link_params(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    return params["payload"][0], params["signature"][0]


def test_feedback_link_signature_round_trip() -> None:
    url = build_feedback_url(
        base_url="https://script.google.com/macros/s/test/exec",
        secret="feedback-secret",
        issue_id=2,
        item_id=46,
        vote="+",
        recipient_key="reader-key",
        subject="Briefing | 2026-03-18",
        item_title="Serving benchmark",
        source_url="https://example.com/item",
        ttl_days=90,
    )

    token, signature = _link_params(url)
    payload = verify_feedback_vote(
        token=token,
        signature=signature,
        secret="feedback-secret",
    )

    assert payload.issue_id == 2
    assert payload.item_id == 46
    assert payload.vote == "+"


def test_feedback_link_rejects_tampering() -> None:
    url = build_feedback_url(
        base_url="https://script.google.com/macros/s/test/exec",
        secret="feedback-secret",
        issue_id=2,
        item_id=46,
        vote="+",
        recipient_key="reader-key",
        subject="Briefing | 2026-03-18",
        item_title="Serving benchmark",
        source_url="https://example.com/item",
        ttl_days=90,
    )
    token, signature = _link_params(url)
    tampered_payload = verify_signed_token(
        token=token,
        signature=signature,
        secret="feedback-secret",
    )
    tampered_payload["item_id"] = 999
    tampered_token = build_signed_token(tampered_payload)

    with pytest.raises(ValueError):
        verify_feedback_vote(
            token=tampered_token,
            signature=signature,
            secret="feedback-secret",
        )


def test_feedback_link_rejects_expired_token() -> None:
    url = build_feedback_url(
        base_url="https://script.google.com/macros/s/test/exec",
        secret="feedback-secret",
        issue_id=2,
        item_id=46,
        vote="-",
        recipient_key="reader-key",
        subject="Briefing | 2026-03-18",
        item_title="Serving benchmark",
        source_url="https://example.com/item",
        ttl_days=1,
    )
    token, signature = _link_params(url)

    with pytest.raises(ValueError):
        verify_feedback_vote(
            token=token,
            signature=signature,
            secret="feedback-secret",
            now=utc_now() + timedelta(days=2),
        )
