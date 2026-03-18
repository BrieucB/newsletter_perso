from __future__ import annotations

from datetime import UTC, datetime, timedelta
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

ARXIV_API_URL = "https://export.arxiv.org/api/query"


def _struct_time_to_datetime(value: struct_time | None) -> datetime | None:
    if value is None:
        return None
    return datetime(*value[:6], tzinfo=UTC)


def _iso_to_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_arxiv_with_elementtree(
    feed_text: str, *, source_name: str, query: str
) -> list[NormalizedItem]:
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    root = ElementTree.fromstring(feed_text)
    items: list[NormalizedItem] = []

    for entry in root.findall("atom:entry", namespace):
        entry_id = entry.findtext("atom:id", default="", namespaces=namespace)
        link = entry.find("atom:link[@rel='alternate']", namespace)
        url = link.attrib.get("href", entry_id) if link is not None else entry_id
        authors = [
            clean_whitespace(author.findtext("atom:name", default="", namespaces=namespace))
            for author in entry.findall("atom:author", namespace)
            if author.findtext("atom:name", default="", namespaces=namespace)
        ]
        tags = [
            category.attrib["term"]
            for category in entry.findall("atom:category", namespace)
            if category.attrib.get("term")
        ]
        items.append(
            NormalizedItem(
                topic="uq_hpc",
                source_kind="arxiv",
                source_name=source_name,
                external_id=entry_id or url,
                title=clean_whitespace(
                    entry.findtext("atom:title", default="", namespaces=namespace)
                ),
                url=url,
                authors=authors,
                published_at=_iso_to_datetime(
                    entry.findtext("atom:published", default=None, namespaces=namespace)
                ),
                raw_summary=clean_whitespace(
                    entry.findtext("atom:summary", default="", namespaces=namespace)
                )
                or None,
                raw_payload={"query": query, "entry_id": entry_id, "categories": tags},
                tags=tags,
            )
        )
    return items


def parse_arxiv_feed(feed_text: str, *, source_name: str, query: str) -> list[NormalizedItem]:
    if feedparser is None:
        return _parse_arxiv_with_elementtree(feed_text, source_name=source_name, query=query)

    parsed = feedparser.parse(feed_text)
    items: list[NormalizedItem] = []
    for entry in parsed.entries:
        authors = [
            author.name for author in getattr(entry, "authors", []) if getattr(author, "name", None)
        ]
        published_at = _struct_time_to_datetime(getattr(entry, "published_parsed", None))
        item = NormalizedItem(
            topic="uq_hpc",
            source_kind="arxiv",
            source_name=source_name,
            external_id=str(getattr(entry, "id", getattr(entry, "link", ""))),
            title=str(getattr(entry, "title", "")).strip(),
            url=str(getattr(entry, "link", getattr(entry, "id", ""))),
            authors=authors,
            published_at=published_at,
            raw_summary=str(getattr(entry, "summary", "")).strip() or None,
            raw_payload={
                "query": query,
                "entry_id": getattr(entry, "id", None),
                "categories": [
                    tag.term for tag in getattr(entry, "tags", []) if getattr(tag, "term", None)
                ],
            },
            tags=[tag.term for tag in getattr(entry, "tags", []) if getattr(tag, "term", None)],
        )
        items.append(item)
    return items


class ArxivCollector(BaseCollector):
    kind = "arxiv"

    def __init__(self, session: requests.Session | None = None) -> None:
        super().__init__(session or requests.Session())

    def fetch_query(
        self, *, query: str, max_results: int, source_name: str
    ) -> list[NormalizedItem]:
        response = self.session.get(
            ARXIV_API_URL,
            params={
                "search_query": f'all:"{query}"',
                "start": 0,
                "max_results": max_results,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            },
            timeout=30,
        )
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
        text = str(getattr(response, "text", ""))
        recent_cutoff = datetime.now(tz=UTC) - timedelta(days=45)
        items = parse_arxiv_feed(text, source_name=source_name, query=query)
        return [
            item
            for item in items
            if item.published_at is None or item.published_at >= recent_cutoff
        ]
