from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlencode

from app.feedback.models import FeedbackSyncPayload, FeedbackVotePayload
from app.utils.time import parse_iso8601, utc_now


def _urlsafe_b64encode(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("utf-8").rstrip("=")


def _urlsafe_b64decode(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}").decode("utf-8")


def _sign_token(token: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def build_signed_token(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return _urlsafe_b64encode(serialized)


def verify_signed_token(*, token: str, signature: str, secret: str) -> dict[str, Any]:
    expected_signature = _sign_token(token, secret)
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("Invalid feedback signature.")
    decoded = _urlsafe_b64decode(token)
    payload = json.loads(decoded)
    if not isinstance(payload, dict):
        raise ValueError("Signed feedback payload must decode to an object.")
    return payload


def _join_url(base_url: str, params: dict[str, str]) -> str:
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode(params)}"


def build_feedback_url(
    *,
    base_url: str,
    secret: str,
    issue_id: int,
    item_id: int,
    vote: Literal["+", "-"],
    recipient_key: str,
    subject: str,
    item_title: str,
    source_url: str,
    ttl_days: int,
) -> str:
    expires_at = utc_now() + timedelta(days=ttl_days)
    payload = FeedbackVotePayload(
        issue_id=issue_id,
        item_id=item_id,
        vote=vote,
        recipient_key=recipient_key,
        subject=subject,
        item_title=item_title,
        source_url=source_url,
        expires_at=expires_at,
    ).model_dump(mode="json")
    token = build_signed_token(payload)
    signature = _sign_token(token, secret)
    return _join_url(base_url, {"payload": token, "signature": signature})


def verify_feedback_vote(
    *,
    token: str,
    signature: str,
    secret: str,
    now: datetime | None = None,
) -> FeedbackVotePayload:
    payload = verify_signed_token(token=token, signature=signature, secret=secret)
    vote_payload = FeedbackVotePayload.model_validate(payload)
    expires_at = parse_iso8601(str(payload["expires_at"]))
    resolved_now = now or utc_now()
    if expires_at is None or expires_at < resolved_now:
        raise ValueError("Feedback link has expired.")
    return vote_payload


def build_sync_url(*, base_url: str, secret: str) -> str:
    payload = FeedbackSyncPayload(requested_at=utc_now()).model_dump(mode="json")
    token = build_signed_token(payload)
    signature = _sign_token(token, secret)
    return _join_url(base_url, {"payload": token, "signature": signature})


def verify_sync_request(*, token: str, signature: str, secret: str) -> FeedbackSyncPayload:
    payload = verify_signed_token(token=token, signature=signature, secret=secret)
    return FeedbackSyncPayload.model_validate(payload)
