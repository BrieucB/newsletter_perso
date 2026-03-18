from __future__ import annotations

import hashlib


def stable_hash(parts: list[str]) -> str:
    payload = "||".join(part.strip() for part in parts if part.strip())
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
