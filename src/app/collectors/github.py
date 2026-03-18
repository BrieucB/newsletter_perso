from __future__ import annotations

from typing import Any

import requests

from app.collectors.base import BaseCollector
from app.models import NormalizedItem
from app.utils.time import parse_iso8601

GITHUB_API_URL = "https://api.github.com"


def _clean_description(payload: dict[str, Any]) -> str | None:
    description = str(payload.get("description") or "").strip()
    return description or None


def normalize_repo_release(
    *,
    repo: str,
    source_name: str,
    topic: str,
    release_payload: dict[str, Any],
) -> NormalizedItem:
    published_at = parse_iso8601(release_payload.get("published_at"))
    name = str(release_payload.get("name") or release_payload.get("tag_name") or f"{repo} release")
    summary = str(release_payload.get("body") or "").strip() or _clean_description(release_payload)
    return NormalizedItem(
        topic=topic,  # type: ignore[arg-type]
        source_kind="github_repo",
        source_name=source_name,
        external_id=(
            f"release:{repo}:{release_payload.get('id', release_payload.get('tag_name', 'latest'))}"
        ),
        title=f"{repo} released {name}",
        url=str(release_payload.get("html_url") or f"https://github.com/{repo}/releases"),
        authors=[str(release_payload["author"]["login"])] if release_payload.get("author") else [],
        published_at=published_at,
        raw_summary=summary,
        raw_payload=release_payload,
        tags=["release", repo],
    )


def normalize_repo_activity(
    *,
    repo_payload: dict[str, Any],
    source_name: str,
    topic: str,
) -> NormalizedItem:
    repo_name = str(repo_payload.get("full_name"))
    pushed_at = parse_iso8601(repo_payload.get("pushed_at")) or parse_iso8601(
        repo_payload.get("updated_at")
    )
    stars = repo_payload.get("stargazers_count")
    summary = _clean_description(repo_payload)
    if stars is not None:
        summary = f"{summary or 'Repository activity update.'} GitHub stars: {stars}."
    return NormalizedItem(
        topic=topic,  # type: ignore[arg-type]
        source_kind="github_repo",
        source_name=source_name,
        external_id=(
            f"activity:{repo_name}:"
            f"{repo_payload.get('pushed_at', repo_payload.get('updated_at', ''))}"
        ),
        title=f"{repo_name} repository activity",
        url=str(repo_payload.get("html_url") or f"https://github.com/{repo_name}"),
        authors=[str(repo_payload["owner"]["login"])] if repo_payload.get("owner") else [],
        published_at=pushed_at,
        raw_summary=summary,
        raw_payload=repo_payload,
        tags=["repository", repo_name],
    )


def normalize_search_repo(
    *,
    source_name: str,
    topic: str,
    repo_payload: dict[str, Any],
) -> NormalizedItem:
    repo_name = str(repo_payload.get("full_name"))
    updated_at = parse_iso8601(repo_payload.get("updated_at"))
    topics = [str(topic_name) for topic_name in repo_payload.get("topics", [])]
    return NormalizedItem(
        topic=topic,  # type: ignore[arg-type]
        source_kind="github_search",
        source_name=source_name,
        external_id=f"search:{repo_payload.get('id')}",
        title=f"{repo_name} is trending around {source_name}",
        url=str(repo_payload.get("html_url")),
        authors=[str(repo_payload["owner"]["login"])] if repo_payload.get("owner") else [],
        published_at=updated_at,
        raw_summary=_clean_description(repo_payload),
        raw_payload=repo_payload,
        tags=topics or ["github", source_name],
    )


class GitHubCollector(BaseCollector):
    kind = "github"

    def __init__(
        self, *, token: str | None = None, session: requests.Session | None = None
    ) -> None:
        session = session or requests.Session()
        session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        if token:
            session.headers["Authorization"] = f"Bearer {token}"
        super().__init__(session)

    def _get_json(self, url: str, *, params: dict[str, Any] | None = None) -> Any:
        response = self.session.get(url, params=params, timeout=30)
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
        return response.json()

    def fetch_tracked_repo(self, *, repo: str, topic: str) -> list[NormalizedItem]:
        repo_payload = self._get_json(f"{GITHUB_API_URL}/repos/{repo}")
        release_payloads = self._get_json(
            f"{GITHUB_API_URL}/repos/{repo}/releases", params={"per_page": 1}
        )
        items = [normalize_repo_activity(repo_payload=repo_payload, source_name=repo, topic=topic)]
        if release_payloads:
            items.insert(
                0,
                normalize_repo_release(
                    repo=repo,
                    source_name=repo,
                    topic=topic,
                    release_payload=release_payloads[0],
                ),
            )
        return items

    def fetch_search(
        self, *, name: str, query: str, topic: str, max_results: int
    ) -> list[NormalizedItem]:
        payload = self._get_json(
            f"{GITHUB_API_URL}/search/repositories",
            params={"q": query, "sort": "updated", "order": "desc", "per_page": max_results},
        )
        return [
            normalize_search_repo(source_name=name, topic=topic, repo_payload=item)
            for item in payload.get("items", [])
        ]
