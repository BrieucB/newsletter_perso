from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.collectors import arxiv, rss
from app.collectors.arxiv import ArxivCollector, parse_arxiv_feed
from app.collectors.github import (
    GitHubCollector,
    normalize_repo_activity,
    normalize_repo_release,
)
from app.collectors.rss import RSSCollector, parse_rss_feed

ARXIV_XML = """
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1</id>
    <title>  New calibration method  </title>
    <summary>  Useful abstract.  </summary>
    <published>{published}</published>
    <author><name>Alice</name></author>
    <category term="bayes" />
    <link rel="alternate" href="https://arxiv.org/abs/1v1" />
  </entry>
</feed>
"""

RSS_XML = """
<rss version="2.0">
  <channel>
    <item>
      <title>  Engineering update  </title>
      <link>https://example.com/post</link>
      <guid>guid-1</guid>
      <description>  Useful summary. </description>
      <pubDate>Tue, 18 Mar 2026 08:00:00</pubDate>
      <category>serving</category>
    </item>
  </channel>
</rss>
"""


class FakeResponse:
    def __init__(self, text: str, payload: Any | None = None) -> None:
        self.text = text
        self._payload = payload
        self.raised = False

    def raise_for_status(self) -> None:
        self.raised = True

    def json(self) -> Any:
        return self._payload


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []
        self.headers: dict[str, str] = {}

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.response


def test_parse_arxiv_feed_elementtree_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(arxiv, "feedparser", None)

    items = parse_arxiv_feed(
        ARXIV_XML.format(published="2026-03-18T08:00:00Z"),
        source_name="arXiv: Bayesian calibration",
        query="bayesian calibration",
    )

    assert len(items) == 1
    assert items[0].authors == ["Alice"]
    assert items[0].tags == ["bayes"]
    assert items[0].raw_summary == "Useful abstract."


def test_arxiv_collector_filters_old_items() -> None:
    recent = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    old = (datetime.now(tz=UTC) - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    response = FakeResponse(
        f"""
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry><id>1</id><title>Recent</title><summary>s</summary><published>{recent}</published></entry>
          <entry><id>2</id><title>Old</title><summary>s</summary><published>{old}</published></entry>
        </feed>
        """
    )
    collector = ArxivCollector(session=FakeSession(response))

    items = collector.fetch_query(query="calibration", max_results=5, source_name="arXiv")

    assert response.raised is True
    assert [item.title for item in items] == ["Recent"]


def test_parse_rss_feed_elementtree_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rss, "feedparser", None)

    items = parse_rss_feed(RSS_XML, source_name="OpenAI News", topic="llm")

    assert len(items) == 1
    assert items[0].external_id == "guid-1"
    assert items[0].tags == ["serving"]
    assert items[0].published_at is not None
    assert items[0].published_at.tzinfo is not None


def test_rss_collector_uses_author_fallback_and_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = SimpleNamespace(
        entries=[
            SimpleNamespace(
                id="entry-1",
                title="Title 1",
                link="https://example.com/1",
                summary="Summary 1",
                author="Author 1",
                published_parsed=datetime.now(tz=UTC).timetuple(),
                tags=[SimpleNamespace(term="tag-1")],
            ),
            SimpleNamespace(
                id="entry-2",
                title="Title 2",
                link="https://example.com/2",
                summary="Summary 2",
                author_detail=SimpleNamespace(name="Author 2"),
                updated_parsed=datetime.now(tz=UTC).timetuple(),
                tags=[],
            ),
        ]
    )
    monkeypatch.setattr(rss, "feedparser", SimpleNamespace(parse=lambda text: parsed))
    response = FakeResponse("<rss />")
    collector = RSSCollector(session=FakeSession(response))

    items = collector.fetch_feed(
        source_name="OpenAI News",
        feed_url="https://example.com/feed.xml",
        topic="llm",
        max_results=1,
    )

    assert response.raised is True
    assert len(items) == 1
    assert items[0].authors == ["Author 1"]


def test_normalize_github_helpers_handle_missing_optional_fields() -> None:
    release = normalize_repo_release(
        repo="org/repo",
        source_name="org/repo",
        topic="llm",
        release_payload={"tag_name": "v1.0.0"},
    )
    activity = normalize_repo_activity(
        repo_payload={"full_name": "org/repo", "updated_at": "2026-03-19T00:00:00Z"},
        source_name="org/repo",
        topic="llm",
    )

    assert release.raw_summary is None
    assert activity.raw_summary is None
    assert release.url.endswith("/releases")
    assert activity.url.endswith("/org/repo")


def test_github_collector_fetch_paths_and_headers() -> None:
    responses = {
        "https://api.github.com/repos/org/repo": {
            "full_name": "org/repo",
            "html_url": "https://github.com/org/repo",
            "owner": {"login": "maintainer"},
            "updated_at": "2026-03-19T00:00:00Z",
            "stargazers_count": 55,
            "description": "Repo description",
        },
        "https://api.github.com/repos/org/repo/releases": [],
        "https://api.github.com/search/repositories": {
            "items": [
                {
                    "id": 1,
                    "full_name": "org/search-repo",
                    "html_url": "https://github.com/org/search-repo",
                    "owner": {"login": "searcher"},
                    "updated_at": "2026-03-19T00:00:00Z",
                    "topics": ["serving"],
                    "description": "Search repo",
                }
            ]
        },
    }

    class GitHubSession(FakeSession):
        def get(self, url: str, **kwargs: Any) -> FakeResponse:
            self.calls.append({"url": url, **kwargs})
            payload = responses[url]
            return FakeResponse("", payload=payload)

    session = GitHubSession(FakeResponse(""))
    collector = GitHubCollector(token="gh-token", session=session)

    tracked = collector.fetch_tracked_repo(repo="org/repo", topic="llm")
    searched = collector.fetch_search(
        name="llm inference serving",
        query="llm inference serving",
        topic="llm",
        max_results=3,
    )

    assert session.headers["Authorization"] == "Bearer gh-token"
    assert tracked[0].title == "org/repo repository activity"
    assert searched[0].tags == ["serving"]
    assert session.calls[1]["params"] == {"per_page": 1}
    assert session.calls[2]["params"]["per_page"] == 3


def test_repo_profile_helpers_cover_clone_and_text_edge_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.profile import repo_profile

    existing = tmp_path / "existing"
    existing.mkdir()
    assert repo_profile.ensure_local_clone(repo_path=existing, clone_url=None) == existing

    missing = tmp_path / "missing"
    with pytest.raises(FileNotFoundError):
        repo_profile.ensure_local_clone(repo_path=missing, clone_url=None)

    created = tmp_path / "created"
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> Any:
        commands.append(command)
        created.mkdir()
        return SimpleNamespace(stdout="commit one\ncommit two")

    monkeypatch.setattr("app.profile.repo_profile.subprocess.run", fake_run)
    assert (
        repo_profile.ensure_local_clone(
            repo_path=created,
            clone_url="https://example.com/repo.git",
        )
        == created
    )
    assert commands[0][:3] == ["git", "clone", "--depth"]

    notebook = tmp_path / "notebook.ipynb"
    notebook.write_text('{"cells":[{"source":["line 1","line 2"]}]}', encoding="utf-8")
    invalid_notebook = tmp_path / "broken.ipynb"
    invalid_notebook.write_text("{bad json", encoding="utf-8")
    binary = tmp_path / "binary.txt"
    binary.write_bytes(b"\xff\xfe\x00")

    assert repo_profile._read_text_fragments(notebook) == ["line 1 line 2"]
    assert repo_profile._read_text_fragments(invalid_notebook) == []
    assert repo_profile._read_text_fragments(binary) == []
