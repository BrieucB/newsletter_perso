from __future__ import annotations

import os
from pathlib import Path
from string import Template
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


class GlobalConfig(BaseModel):
    recipient_email: str
    sender_email: str
    timezone: str = "Europe/Madrid"
    max_candidates_per_source: int = 10
    max_shortlist_per_topic: int = 8
    openai_model: str = "gpt-5.4-mini"
    database_path: str = "data/newsletter.sqlite3"
    preview_output_path: str = "preview/newsletter_preview.html"
    schedule: str = "Monday / Wednesday / Friday at 08:00 Europe/Madrid"


class ArxivQueryConfig(BaseModel):
    name: str
    query: str
    topic: str = "uq_hpc"
    is_enabled: bool = True


class GitHubRepoConfig(BaseModel):
    repo: str
    topic: str = "llm"
    is_enabled: bool = True


class GitHubSearchConfig(BaseModel):
    name: str
    query: str
    topic: str = "llm"
    is_enabled: bool = True


class RSSFeedConfig(BaseModel):
    name: str
    url: str
    topic: str = "llm"
    is_enabled: bool = True


class SourceConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    global_config: GlobalConfig = Field(alias="global")
    arxiv_queries: list[ArxivQueryConfig] = Field(default_factory=list)
    github_tracked_repos: list[GitHubRepoConfig] = Field(default_factory=list)
    github_search_queries: list[GitHubSearchConfig] = Field(default_factory=list)
    rss_feeds: list[RSSFeedConfig] = Field(default_factory=list)


class EnvironmentConfig(BaseModel):
    openai_api_key: str | None = None
    openai_model_override: str | None = None
    gmail_client_secret_file: str = "oauth_client_secret.json"
    gmail_token_file: str = "token.json"
    newsletter_recipient: str | None = None
    newsletter_sender: str | None = None
    github_token: str | None = None

    @classmethod
    def from_env(cls) -> EnvironmentConfig:
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_model_override=os.getenv("OPENAI_MODEL"),
            gmail_client_secret_file=os.getenv(
                "GMAIL_CLIENT_SECRET_FILE", "oauth_client_secret.json"
            ),
            gmail_token_file=os.getenv("GMAIL_TOKEN_FILE", "token.json"),
            newsletter_recipient=os.getenv("NEWSLETTER_RECIPIENT"),
            newsletter_sender=os.getenv("NEWSLETTER_SENDER"),
            github_token=os.getenv("GITHUB_TOKEN"),
        )


class AppSettings(BaseModel):
    project_root: Path
    config_path: Path
    global_config: GlobalConfig
    arxiv_queries: list[ArxivQueryConfig]
    github_tracked_repos: list[GitHubRepoConfig]
    github_search_queries: list[GitHubSearchConfig]
    rss_feeds: list[RSSFeedConfig]
    env: EnvironmentConfig

    @property
    def db_path(self) -> Path:
        return self.project_root / self.global_config.database_path

    @property
    def preview_output_path(self) -> Path:
        return self.project_root / self.global_config.preview_output_path

    @property
    def openai_model(self) -> str:
        return self.env.openai_model_override or self.global_config.openai_model

    @property
    def recipient_email(self) -> str:
        return self.env.newsletter_recipient or self.global_config.recipient_email

    @property
    def sender_email(self) -> str:
        return self.env.newsletter_sender or self.global_config.sender_email

    @property
    def gmail_client_secret_path(self) -> Path:
        return self.project_root / self.env.gmail_client_secret_file

    @property
    def gmail_token_path(self) -> Path:
        return self.project_root / self.env.gmail_token_file


def _expand_env_vars(raw_text: str) -> str:
    return Template(raw_text).safe_substitute(os.environ)


def load_settings(config_path: str | Path | None = None) -> AppSettings:
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")
    env = EnvironmentConfig.from_env()

    resolved_config = Path(config_path) if config_path else project_root / "config" / "sources.yaml"
    if not resolved_config.exists():
        resolved_config = project_root / "config" / "sources.example.yaml"

    raw_text = _expand_env_vars(resolved_config.read_text(encoding="utf-8"))
    payload = yaml.safe_load(raw_text) or {}
    source_config = SourceConfig.model_validate(payload)
    global_config = source_config.global_config.model_copy(
        update={
            "recipient_email": env.newsletter_recipient
            or source_config.global_config.recipient_email,
            "sender_email": env.newsletter_sender or source_config.global_config.sender_email,
            "openai_model": env.openai_model_override or source_config.global_config.openai_model,
        },
    )

    return AppSettings(
        project_root=project_root,
        config_path=resolved_config,
        global_config=global_config,
        arxiv_queries=source_config.arxiv_queries,
        github_tracked_repos=source_config.github_tracked_repos,
        github_search_queries=source_config.github_search_queries,
        rss_feeds=source_config.rss_feeds,
        env=env,
    )


def summarize_source_counts(settings: AppSettings) -> dict[str, Any]:
    return {
        "arxiv_queries": len([query for query in settings.arxiv_queries if query.is_enabled]),
        "github_tracked_repos": len(
            [repo for repo in settings.github_tracked_repos if repo.is_enabled]
        ),
        "github_search_queries": len(
            [query for query in settings.github_search_queries if query.is_enabled]
        ),
        "rss_feeds": len([feed for feed in settings.rss_feeds if feed.is_enabled]),
    }
