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


class TargetRatio(BaseModel):
    current_work: float = 0.5
    llm_background: float = 0.5


class ExplicitProfileConfig(BaseModel):
    work_priorities: list[str]
    llm_learning_goals: list[str]
    preferred_content_types: list[str]
    avoid_content: list[str]
    tone: str = "mentor_note_to_self"
    target_ratio: TargetRatio = Field(default_factory=TargetRatio)
    desired_effects: list[str]
    feedback_adaptation_strength: float = 0.2


class RepoProfilingConfig(BaseModel):
    enabled: bool = True
    ignore_dirs: list[str] = Field(default_factory=lambda: [".git", ".venv", "build", "dist"])
    ignore_file_globs: list[str] = Field(
        default_factory=lambda: ["*.png", "*.jpg", "*.jpeg", "*.pdf", "*.parquet"]
    )


class LocalRepoConfig(BaseModel):
    name: str
    path: str
    clone_url: str | None = None
    enabled: bool = True


class LocalReposConfig(BaseModel):
    repos: list[LocalRepoConfig] = Field(default_factory=list)
    ignore_dirs: list[str] = Field(default_factory=list)
    ignore_file_globs: list[str] = Field(default_factory=list)


class SourceConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    global_config: GlobalConfig = Field(alias="global")
    arxiv_queries: list[ArxivQueryConfig] = Field(default_factory=list)
    github_tracked_repos: list[GitHubRepoConfig] = Field(default_factory=list)
    github_search_queries: list[GitHubSearchConfig] = Field(default_factory=list)
    rss_feeds: list[RSSFeedConfig] = Field(default_factory=list)


class ProfileConfigFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_priorities: list[str]
    llm_learning_goals: list[str]
    preferred_content_types: list[str]
    avoid_content: list[str]
    tone: str = "mentor_note_to_self"
    target_ratio: TargetRatio = Field(default_factory=TargetRatio)
    desired_effects: list[str]
    feedback_adaptation_strength: float = 0.2
    repo_profiling: RepoProfilingConfig = Field(default_factory=RepoProfilingConfig)


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
    profile_path: Path
    local_repos_path: Path
    global_config: GlobalConfig
    arxiv_queries: list[ArxivQueryConfig]
    github_tracked_repos: list[GitHubRepoConfig]
    github_search_queries: list[GitHubSearchConfig]
    rss_feeds: list[RSSFeedConfig]
    explicit_profile: ExplicitProfileConfig
    repo_profiling: RepoProfilingConfig
    local_repos: list[LocalRepoConfig]
    local_repo_ignore_dirs: list[str]
    local_repo_ignore_file_globs: list[str]
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

    def resolve_repo_path(self, repo: LocalRepoConfig) -> Path:
        candidate = Path(repo.path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate


def _expand_env_vars(raw_text: str) -> str:
    return Template(raw_text).safe_substitute(os.environ)


def load_settings(config_path: str | Path | None = None) -> AppSettings:
    project_root = Path(__file__).resolve().parents[2]
    os.environ.setdefault("PROJECT_ROOT", str(project_root))
    load_dotenv(project_root / ".env")
    env = EnvironmentConfig.from_env()

    resolved_config = Path(config_path) if config_path else project_root / "config" / "sources.yaml"
    if not resolved_config.exists():
        resolved_config = project_root / "config" / "sources.example.yaml"

    raw_text = _expand_env_vars(resolved_config.read_text(encoding="utf-8"))
    payload = yaml.safe_load(raw_text) or {}
    source_config = SourceConfig.model_validate(payload)
    profile_path = project_root / "config" / "profile.yaml"
    if not profile_path.exists():
        profile_path = project_root / "config" / "profile.example.yaml"
    profile_payload = (
        yaml.safe_load(_expand_env_vars(profile_path.read_text(encoding="utf-8"))) or {}
    )
    profile_config = ProfileConfigFile.model_validate(profile_payload)

    local_repos_path = project_root / "config" / "local_repos.yaml"
    if not local_repos_path.exists():
        local_repos_path = project_root / "config" / "local_repos.example.yaml"
    local_repos_payload = (
        yaml.safe_load(_expand_env_vars(local_repos_path.read_text(encoding="utf-8"))) or {}
    )
    local_repos_config = LocalReposConfig.model_validate(local_repos_payload)

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
        profile_path=profile_path,
        local_repos_path=local_repos_path,
        global_config=global_config,
        arxiv_queries=source_config.arxiv_queries,
        github_tracked_repos=source_config.github_tracked_repos,
        github_search_queries=source_config.github_search_queries,
        rss_feeds=source_config.rss_feeds,
        explicit_profile=ExplicitProfileConfig.model_validate(profile_config.model_dump()),
        repo_profiling=profile_config.repo_profiling,
        local_repos=local_repos_config.repos,
        local_repo_ignore_dirs=(
            local_repos_config.ignore_dirs or profile_config.repo_profiling.ignore_dirs
        ),
        local_repo_ignore_file_globs=(
            local_repos_config.ignore_file_globs or profile_config.repo_profiling.ignore_file_globs
        ),
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
