from __future__ import annotations

import json
from datetime import UTC, datetime

from app.db import connect
from app.llm.schemas import NewsletterIssuePayload
from app.pipeline.run_once import NewsletterPipeline
from tests.conftest import build_test_settings


class FakeArxivCollector:
    def fetch_query(self, *, query: str, max_results: int, source_name: str):
        return [
            {
                "topic": "uq_hpc",
                "source_kind": "arxiv",
                "source_name": source_name,
                "external_id": "arxiv-1",
                "title": "Simulation-based inference accelerates calibration",
                "url": "https://arxiv.org/abs/1",
                "authors": ["A"],
                "published_at": datetime.now(tz=UTC),
                "raw_summary": "Recent paper on calibration.",
                "raw_payload": {"query": query},
                "tags": ["uq"],
            }
        ]


class FakeRSSCollector:
    def fetch_feed(self, *, source_name: str, feed_url: str, topic: str, max_results: int):
        return [
            {
                "topic": "llm",
                "source_kind": "rss",
                "source_name": source_name,
                "external_id": "rss-1",
                "title": "OpenAI adds a new eval workflow",
                "url": "https://example.com/rss",
                "authors": [],
                "published_at": datetime.now(tz=UTC),
                "raw_summary": "Official workflow update.",
                "raw_payload": {"feed_url": feed_url},
                "tags": ["evals"],
            }
        ]


class FakeGitHubCollector:
    def fetch_tracked_repo(self, *, repo: str, topic: str):
        return [
            {
                "topic": "llm",
                "source_kind": "github_repo",
                "source_name": repo,
                "external_id": "repo-1",
                "title": f"{repo} released v1.0.0",
                "url": f"https://github.com/{repo}/releases/tag/v1.0.0",
                "authors": ["maintainer"],
                "published_at": datetime.now(tz=UTC),
                "raw_summary": "New release.",
                "raw_payload": {"repo": repo},
                "tags": ["release"],
            }
        ]

    def fetch_search(self, *, name: str, query: str, topic: str, max_results: int):
        return []


class FakeLLMClient:
    def generate(self, *, system_prompt: str, user_prompt: str) -> NewsletterIssuePayload:
        payload = json.loads(user_prompt)
        uq_candidate = next(
            candidate for candidate in payload["candidates"] if candidate["topic"] == "uq_hpc"
        )
        llm_candidate = next(
            candidate for candidate in payload["candidates"] if candidate["topic"] == "llm"
        )
        return NewsletterIssuePayload.model_validate(
            {
                "subject": "will be overridden",
                "intro": "Two short paragraphs on the week.",
                "sections": [
                    {
                        "name": "UQ / HPC",
                        "items": [
                            {
                                "candidate_id": uq_candidate["candidate_id"],
                                "title": uq_candidate["title"],
                                "summary": "Short UQ summary.",
                                "why_it_matters": "It sharpens calibration workflows.",
                                "source_name": uq_candidate["source_name"],
                                "source_url": uq_candidate["source_url"],
                            }
                        ],
                    },
                    {
                        "name": "LLM",
                        "items": [
                            {
                                "candidate_id": llm_candidate["candidate_id"],
                                "title": llm_candidate["title"],
                                "summary": "Short LLM summary.",
                                "why_it_matters": "It affects production stack choices.",
                                "source_name": llm_candidate["source_name"],
                                "source_url": llm_candidate["source_url"],
                            }
                        ],
                    },
                ],
            }
        )


def test_pipeline_send_smoke(tmp_path) -> None:
    settings = build_test_settings(tmp_path)
    sent_messages: list[dict[str, str]] = []

    def fake_gmail_sender(**kwargs):
        sent_messages.append(kwargs)
        return {"id": "msg-1"}

    pipeline = NewsletterPipeline(
        settings,
        connection=connect(settings.db_path),
        llm_client=FakeLLMClient(),
        gmail_sender=fake_gmail_sender,
        arxiv_collector=FakeArxivCollector(),  # type: ignore[arg-type]
        rss_collector=FakeRSSCollector(),  # type: ignore[arg-type]
        github_collector=FakeGitHubCollector(),  # type: ignore[arg-type]
    )

    original_persist = pipeline._persist_item

    def persist_from_dict(item_dict):
        from app.models import NormalizedItem

        return original_persist(NormalizedItem.model_validate(item_dict))

    pipeline._persist_item = persist_from_dict  # type: ignore[method-assign]
    result = pipeline.run(send_email=True)

    assert result.status == "sent"
    assert result.selected_count == 2
    assert result.preview_path is not None and result.preview_path.exists()
    assert len(sent_messages) == 1

    issue_row = pipeline.connection.execute("SELECT status FROM issues LIMIT 1").fetchone()
    assert issue_row["status"] == "sent"
