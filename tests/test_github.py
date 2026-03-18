from __future__ import annotations

from app.collectors.github import (
    normalize_repo_activity,
    normalize_repo_release,
    normalize_search_repo,
)


def test_normalize_repo_release() -> None:
    item = normalize_repo_release(
        repo="vllm-project/vllm",
        source_name="vllm-project/vllm",
        topic="llm",
        release_payload={
            "id": 10,
            "tag_name": "v1.2.3",
            "html_url": "https://github.com/vllm-project/vllm/releases/tag/v1.2.3",
            "published_at": "2026-03-17T12:00:00+00:00",
            "body": "Release notes body",
            "author": {"login": "maintainer"},
        },
    )

    assert item.source_kind == "github_repo"
    assert item.title == "vllm-project/vllm released v1.2.3"
    assert item.authors == ["maintainer"]


def test_normalize_repo_activity() -> None:
    item = normalize_repo_activity(
        repo_payload={
            "full_name": "ggml-org/llama.cpp",
            "html_url": "https://github.com/ggml-org/llama.cpp",
            "updated_at": "2026-03-17T12:00:00+00:00",
            "owner": {"login": "ggml-org"},
            "description": "Local inference engine",
            "stargazers_count": 123,
        },
        source_name="ggml-org/llama.cpp",
        topic="llm",
    )

    assert item.source_kind == "github_repo"
    assert item.title == "ggml-org/llama.cpp repository activity"
    assert "GitHub stars: 123." in (item.raw_summary or "")


def test_normalize_search_repo() -> None:
    item = normalize_search_repo(
        source_name="rag evaluation",
        topic="llm",
        repo_payload={
            "id": 44,
            "full_name": "org/repo",
            "html_url": "https://github.com/org/repo",
            "updated_at": "2026-03-17T12:00:00+00:00",
            "description": "Repository description",
            "owner": {"login": "org"},
            "topics": ["rag", "evals"],
        },
    )

    assert item.source_kind == "github_search"
    assert item.title == "org/repo is trending around rag evaluation"
    assert item.tags == ["rag", "evals"]
