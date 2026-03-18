# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.profile.models import AggregatedRepoProfile, LearnedPreferences, RuntimeProfileContext
from app.settings import (
    AppSettings,
    ArxivQueryConfig,
    EnvironmentConfig,
    ExplicitProfileConfig,
    GitHubRepoConfig,
    GitHubSearchConfig,
    GlobalConfig,
    RepoProfilingConfig,
    RSSFeedConfig,
    TargetRatio,
)


def build_test_explicit_profile() -> ExplicitProfileConfig:
    return ExplicitProfileConfig(
        work_priorities=[
            "HPC / GPU",
            "calibration",
            "surrogate modeling",
            "Bayesian inference",
            "coupling multi-scale / multi-physics",
        ],
        llm_learning_goals=[
            "architecture trade-offs",
            "major players / tools / standards",
            "engineering perspective",
            "product/system understanding",
            "interview-level technical background",
        ],
        preferred_content_types=["engineering_blog", "tool_or_repo", "paper", "release_note"],
        avoid_content=[
            "linkedin_marketing_style",
            "overly_theoretical_without_applied_angle",
            "tiny_low-traction_open_source",
        ],
        tone="mentor_note_to_self",
        target_ratio=TargetRatio(current_work=0.5, llm_background=0.5),
        desired_effects=[
            "I should try this in my project",
            "this could be a direction worth exploring",
            "this improves my LLM technical background",
        ],
        feedback_adaptation_strength=0.2,
    )


def build_test_profile_context() -> RuntimeProfileContext:
    return RuntimeProfileContext(
        explicit_profile=build_test_explicit_profile(),
        aggregated_repo_profile=AggregatedRepoProfile(
            repo_count=2,
            scientific_domains=["bayesian inference", "calibration", "surrogate modeling"],
            engineering_themes=["gpu computing", "hpc scaling"],
            infra_themes=["slurm orchestration", "cmake builds"],
            workflow_markers=["GPU/CUDA", "SLURM", "TMCMC / MCMC"],
            libraries_tools=["cuda", "mpi", "cmake"],
            dominant_languages=["python", "cpp", "cuda"],
            summary=(
                "Your repo fingerprint centers on bayesian inference and calibration, "
                "with strong GPU and HPC workflow markers."
            ),
            keyword_weights={
                "bayesian inference": 3.0,
                "calibration": 3.0,
                "surrogate modeling": 2.5,
                "GPU/CUDA": 2.0,
                "SLURM": 1.5,
            },
        ),
        learned_preferences=LearnedPreferences(
            source_weights={"OpenAI News": 0.2},
            content_type_weights={"engineering_blog": 0.3},
            fit_tag_weights={"both": 0.2},
            feature_weight_adjustments={"practical_reusability_score": 0.15},
            positive_patterns=["engineering_blog"],
        ),
    )


def build_test_settings(project_root: Path) -> AppSettings:
    return AppSettings(
        project_root=project_root,
        config_path=project_root / "config" / "sources.yaml",
        profile_path=project_root / "config" / "profile.yaml",
        local_repos_path=project_root / "config" / "local_repos.yaml",
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
        explicit_profile=build_test_explicit_profile(),
        repo_profiling=RepoProfilingConfig(enabled=False),
        local_repos=[],
        local_repo_ignore_dirs=[".git", ".venv", "build", "dist"],
        local_repo_ignore_file_globs=["*.png", "*.jpg", "*.pdf"],
        env=EnvironmentConfig(
            openai_api_key="test-key",
            gmail_client_secret_file="client_secret.json",
            gmail_token_file="token.json",
            newsletter_recipient="reader@example.com",
            newsletter_sender="sender@example.com",
            github_token="gh-token",
            feedback_web_app_url="https://script.google.com/macros/s/test/exec",
            feedback_signing_secret="feedback-secret",
            feedback_link_ttl_days=90,
        ),
    )
