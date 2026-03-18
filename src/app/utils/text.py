from __future__ import annotations

import re
from urllib.parse import urlparse

_NON_WORD_RE = re.compile(r"[^a-z0-9]+")
_WHITESPACE_RE = re.compile(r"\s+")


def clean_whitespace(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip()


def normalize_title(title: str) -> str:
    cleaned = clean_whitespace(title).lower()
    return _NON_WORD_RE.sub(" ", cleaned).strip()


def content_snippet(summary: str | None, limit: int = 320) -> str:
    if not summary:
        return ""
    normalized = clean_whitespace(summary)
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def url_domain(url: str) -> str:
    return urlparse(url).netloc.lower()
