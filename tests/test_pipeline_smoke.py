from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.db import connect
from app.feedback.models import RemoteFeedbackEvent
from app.llm.schemas import NewsletterIssuePayload
from app.models import NormalizedItem
from app.pipeline.run_once import NewsletterPipeline
from tests.conftest import build_test_settings


class FakeArxivCollector:
    def fetch_query(
        self,
        *,
        query: str,
        max_results: int,
        source_name: str,
    ) -> list[NormalizedItem]:
        return [
            NormalizedItem(
                topic="uq_hpc",
                source_kind="arxiv",
                source_name=source_name,
                external_id=f"arxiv-{index}",
                title=f"Simulation-based inference pattern {index} accelerates calibration",
                url=f"https://arxiv.org/abs/{index}",
                authors=["A"],
                published_at=datetime.now(tz=UTC),
                raw_summary=(
                    "Recent paper on calibration, surrogate modeling, "
                    "and GPU workflows."
                ),
                raw_payload={"query": query},
                tags=["uq"],
            )
            for index in range(1, 5)
        ]


class FakeRSSCollector:
    def fetch_feed(
        self,
        *,
        source_name: str,
        feed_url: str,
        topic: str,
        max_results: int,
    ) -> list[NormalizedItem]:
        return [
            NormalizedItem(
                topic="llm",
                source_kind="rss",
                source_name=source_name,
                external_id=f"rss-{index}",
                title=f"OpenAI adds eval workflow {index}",
                url=f"https://example.com/rss/{index}",
                authors=[],
                published_at=datetime.now(tz=UTC),
                raw_summary=(
                    "Official workflow update with architecture and "
                    "serving implications."
                ),
                raw_payload={"feed_url": feed_url},
                tags=["evals"],
            )
            for index in range(1, 3)
        ]


class FakeGitHubCollector:
    def fetch_tracked_repo(self, *, repo: str, topic: str) -> list[NormalizedItem]:
        return [
            NormalizedItem(
                topic="llm",
                source_kind="github_repo",
                source_name=repo,
                external_id="repo-1",
                title=f"{repo} released v1.0.0",
                url=f"https://github.com/{repo}/releases/tag/v1.0.0",
                authors=["maintainer"],
                published_at=datetime.now(tz=UTC),
                raw_summary="New release with serving and architecture trade-off notes.",
                raw_payload={"repo": repo, "stargazers_count": 32000, "forks_count": 4200},
                tags=["release"],
            )
        ]

    def fetch_search(
        self,
        *,
        name: str,
        query: str,
        topic: str,
        max_results: int,
    ) -> list[NormalizedItem]:
        return [
            NormalizedItem(
                topic="llm",
                source_kind="github_search",
                source_name=name,
                external_id="search-1",
                title="RAG evaluation benchmark repo compares architecture trade-offs",
                url="https://github.com/example/rag-eval",
                authors=["maintainer"],
                published_at=datetime.now(tz=UTC),
                raw_summary="Repository benchmark with evaluation workflow details.",
                raw_payload={"query": query, "stargazers_count": 1800, "forks_count": 120},
                tags=["repo"],
            )
        ]


class FakeLLMClient:
    def generate(self, *, system_prompt: str, user_prompt: str) -> NewsletterIssuePayload:
        payload = json.loads(user_prompt)
        uq_candidates = [
            candidate for candidate in payload["candidates"] if candidate["topic"] == "uq_hpc"
        ]
        llm_candidates = [
            candidate for candidate in payload["candidates"] if candidate["topic"] == "llm"
        ]
        return NewsletterIssuePayload.model_validate(
            {
                "subject": "will be overridden",
                "intro": "Two short paragraphs on the week.",
                "sections": [
                    {
                        "name": "Most relevant for your work",
                        "items": [
                            {
                                "candidate_id": candidate["candidate_id"],
                                "title": candidate["title"],
                                "what_happened": "Short UQ summary.",
                                "why_you_should_care": (
                                    "It sharpens calibration and surrogate workflow choices."
                                ),
                                "fit_tag": "current_work",
                                "source_name": candidate["source_name"],
                                "source_url": candidate["source_url"],
                            }
                            for candidate in uq_candidates
                        ],
                    },
                    {
                        "name": "LLM engineering you should understand",
                        "items": [
                            {
                                "candidate_id": candidate["candidate_id"],
                                "title": candidate["title"],
                                "what_happened": "Short LLM summary.",
                                "why_you_should_care": (
                                    "It improves your understanding of serving and eval trade-offs."
                                ),
                                "fit_tag": "llm_background",
                                "source_name": candidate["source_name"],
                                "source_url": candidate["source_url"],
                            }
                            for candidate in llm_candidates
                        ],
                    },
                ],
                "selection_notes": [
                    "Balanced work-relevant UQ/HPC items with LLM ecosystem mapping."
                ],
            }
        )


class FakeFeedbackSyncClient:
    def fetch_events(self) -> list[RemoteFeedbackEvent]:
        return []


def test_pipeline_send_smoke(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    sent_messages: list[dict[str, Any]] = []

    def fake_gmail_sender(**kwargs: Any) -> dict[str, str]:
        sent_messages.append(kwargs)
        return {"id": "msg-1"}

    pipeline = NewsletterPipeline(
        settings,
        connection=connect(settings.db_path),
        llm_client=FakeLLMClient(),
        feedback_client=FakeFeedbackSyncClient(),
        gmail_sender=fake_gmail_sender,
        arxiv_collector=FakeArxivCollector(),  # type: ignore[arg-type]
        rss_collector=FakeRSSCollector(),  # type: ignore[arg-type]
        github_collector=FakeGitHubCollector(),  # type: ignore[arg-type]
    )
    result = pipeline.run(send_email=True)

    assert result.status == "sent"
    assert result.selected_count == 8
    assert result.preview_path is not None and result.preview_path.exists()
    assert len(sent_messages) == 1
    assert "+ good rec" in sent_messages[0]["html_body"]
    assert "payload=" in sent_messages[0]["html_body"]
    assert "Feedback: + good rec" in sent_messages[0]["text_body"]

    issue_row = pipeline.connection.execute("SELECT status FROM issues LIMIT 1").fetchone()
    assert issue_row["status"] == "sent"
