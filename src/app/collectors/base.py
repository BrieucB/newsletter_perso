from __future__ import annotations

from typing import Any


class BaseCollector:
    kind: str

    def __init__(self, session: Any) -> None:
        self.session = session
