from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import struct_time
from xml.etree import ElementTree

import requests

try:
    import feedparser
except ModuleNotFoundError:  # pragma: no cover - exercised in dependency-light environments
    feedparser = None

from app.collectors.base import BaseCollector
from app.models import NormalizedItem
from app.utils.text import clean_whitespace


def _struct_time_to_datetime(value: struct_time | None) -> datetime | None:
    if value is None:
        return None
    return datetime(*value[:6], tzinfo=UTC)


def _rss_pubdate_to_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _parse_rss_with_elementtree(
    feed_text: str, *, source_name: str, topic: str
) -> list[NormalizedItem]:
    root = ElementTree.fromstring(feed_text)
    items: list[NormalizedItem] = []

    for entry in root.findall("./channel/item"):
        tags = [clean_whitespace(category.text or "") for category in entry.findall("category")]
        tags = [tag for tag in tags if tag]
        link = clean_whitespace(entry.findtext("link", default=""))
        guid = clean_whitespace(entry.findtext("guid", default=link))
        items.append(
            NormalizedItem(
                topic=topic,  # type: ignore[arg-type]
                source_kind="rss",
                source_name=source_name,
                external_id=guid or link,
                title=clean_whitespace(entry.findtext("title", default="")),
                url=link,
                authors=[],
                published_at=_rss_pubdate_to_datetime(entry.findtext("pubDate", default=None)),
                raw_summary=clean_whitespace(entry.findtext("description", default="")) or None,
                raw_payload={"entry_id": guid or link, "tags": tags},
                tags=tags,
            )
        )
    return items


def parse_rss_feed(feed_text: str, *, source_name: str, topic: str) -> list[NormalizedItem]:
    if feedparser is None:
        return _parse_rss_with_elementtree(feed_text, source_name=source_name, topic=topic)

    parsed = feedparser.parse(feed_text)
    items: list[NormalizedItem] = []
    for entry in parsed.entries:
        published_at = _struct_time_to_datetime(
            getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
        )
        authors: list[str] = []
        author_detail = getattr(entry, "author_detail", None)
        if author_detail is not None and getattr(author_detail, "name", None):
            authors = [str(author_detail.name)]
        elif getattr(entry, "author", None):
            authors = [str(entry.author)]
        items.append(
            NormalizedItem(
                topic=topic,  # type: ignore[arg-type]
                source_kind="rss",
                source_name=source_name,
                external_id=str(getattr(entry, "id", getattr(entry, "link", ""))),
                title=str(getattr(entry, "title", "")).strip(),
                url=str(getattr(entry, "link", "")),
                authors=authors,
                published_at=published_at,
                raw_summary=str(getattr(entry, "summary", "")).strip() or None,
                raw_payload={
                    "entry_id": getattr(entry, "id", None),
                    "tags": [
                        tag.term for tag in getattr(entry, "tags", []) if getattr(tag, "term", None)
                    ],
                },
                tags=[tag.term for tag in getattr(entry, "tags", []) if getattr(tag, "term", None)],
            )
        )
    return items


class RSSCollector(BaseCollector):
    kind = "rss"

    def __init__(self, session: requests.Session | None = None) -> None:
        super().__init__(session or requests.Session())

    def fetch_feed(
        self, *, source_name: str, feed_url: str, topic: str, max_results: int
    ) -> list[NormalizedItem]:
        response = self.session.get(feed_url, timeout=30)
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
        items = parse_rss_feed(
            str(getattr(response, "text", "")), source_name=source_name, topic=topic
        )
        return items[:max_results]
