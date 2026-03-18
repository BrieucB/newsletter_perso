# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.settings import (
    AppSettings,
    ArxivQueryConfig,
    EnvironmentConfig,
    GitHubRepoConfig,
    GitHubSearchConfig,
    GlobalConfig,
    RSSFeedConfig,
)


def build_test_settings(project_root: Path) -> AppSettings:
    return AppSettings(
        project_root=project_root,
        config_path=project_root / "config" / "sources.yaml",
        global_config=GlobalConfig(
            recipient_email="reader@example.com",
            sender_email="sender@example.com",
            timezone="Europe/Madrid",
            max_candidates_per_source=5,
            max_shortlist_per_topic=5,
            openai_model="gpt-5.4-mini",
            database_path="data/test.sqlite3",
            preview_output_path="preview/test_preview.html",
        ),
        arxiv_queries=[ArxivQueryConfig(name="uq", query="simulation-based inference")],
        github_tracked_repos=[GitHubRepoConfig(repo="vllm-project/vllm")],
        github_search_queries=[GitHubSearchConfig(name="rag evaluation", query="rag evaluation")],
        rss_feeds=[RSSFeedConfig(name="OpenAI News", url="https://example.com/feed.xml")],
        env=EnvironmentConfig(
            openai_api_key="test-key",
            gmail_client_secret_file="client_secret.json",
            gmail_token_file="token.json",
            newsletter_recipient="reader@example.com",
            newsletter_sender="sender@example.com",
            github_token="gh-token",
        ),
    )
