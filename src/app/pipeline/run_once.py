from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from app.collectors.arxiv import ArxivCollector
from app.collectors.github import GitHubCollector
from app.collectors.rss import RSSCollector
from app.db import connect, init_db
from app.llm.generate_issue import generate_issue_from_shortlist
from app.llm.schemas import NewsletterIssuePayload
from app.models import NormalizedItem, ShortlistCandidate, StoredItem
from app.ranking.shortlist import score_and_shortlist
from app.render.html import render_issue_html, render_issue_text
from app.repositories.issues import IssuesRepository
from app.repositories.items import ItemsRepository
from app.repositories.runs import PipelineRunsRepository
from app.settings import AppSettings
from app.utils.hashing import stable_hash
from app.utils.text import normalize_title
from app.utils.time import utc_now

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    subject: str
    preview_path: Path | None
    fetched_count: int
    shortlisted_count: int
    selected_count: int
    issue_id: int | None
    status: str
    reused_existing_issue: bool = False


class NewsletterPipeline:
    def __init__(
        self,
        settings: AppSettings,
        *,
        connection: sqlite3.Connection | None = None,
        http_session: requests.Session | None = None,
        llm_client: Any | None = None,
        gmail_sender: Any | None = None,
        arxiv_collector: ArxivCollector | None = None,
        rss_collector: RSSCollector | None = None,
        github_collector: GitHubCollector | None = None,
    ) -> None:
        self.settings = settings
        self._owns_connection = connection is None
        self.connection = connection or connect(settings.db_path)
        self.http_session = http_session or requests.Session()
        self.items_repo = ItemsRepository(self.connection)
        self.issues_repo = IssuesRepository(self.connection)
        self.runs_repo = PipelineRunsRepository(self.connection)
        self.arxiv_collector = arxiv_collector or ArxivCollector(session=self.http_session)
        self.rss_collector = rss_collector or RSSCollector(session=self.http_session)
        self.github_collector = github_collector or GitHubCollector(
            token=self.settings.env.github_token,
            session=self.http_session,
        )
        self.llm_client = llm_client
        self.gmail_sender = gmail_sender or self._send_via_gmail

    def close(self) -> None:
        if self._owns_connection:
            self.connection.close()

    def __enter__(self) -> NewsletterPipeline:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def _build_llm_client(self) -> Any:
        if not self.settings.env.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required to generate newsletter editions.")
        from app.llm.client import OpenAIClient

        return OpenAIClient(
            api_key=self.settings.env.openai_api_key,
            model=self.settings.openai_model,
        )

    def _send_via_gmail(self, **kwargs: Any) -> dict[str, Any]:
        from app.email.gmail_send import send_gmail_message

        return send_gmail_message(**kwargs)

    def initialize(self) -> None:
        init_db(self.settings.db_path)

    def _edition_subject(self) -> str:
        tz = ZoneInfo(self.settings.global_config.timezone)
        local_date = datetime.now(tz).date()
        return f"UQ / HPC + LLM Briefing | {local_date.isoformat()}"

    def _persist_item(self, normalized_item: NormalizedItem) -> int:
        source_id = self.items_repo.ensure_source(
            kind=normalized_item.source_kind,
            name=normalized_item.source_name,
            config={
                "source_name": normalized_item.source_name,
                "source_kind": normalized_item.source_kind,
            },
        )
        normalized = normalize_title(normalized_item.title)
        content_hash = stable_hash(
            [
                normalized_item.title,
                normalized_item.raw_summary or "",
                ",".join(normalized_item.authors),
                normalized_item.url,
            ]
        )
        return self.items_repo.upsert_normalized_item(
            source_id=source_id,
            normalized_item=normalized_item,
            normalized_title=normalized,
            content_hash=content_hash,
        )

    def fetch_sources(self, logs: list[str]) -> int:
        fetched_count = 0
        collector_errors = 0

        for query in self.settings.arxiv_queries:
            if not query.is_enabled:
                continue
            try:
                items = self.arxiv_collector.fetch_query(
                    query=query.query,
                    max_results=self.settings.global_config.max_candidates_per_source,
                    source_name=f"arXiv: {query.name}",
                )
                for item in items:
                    self._persist_item(item)
                fetched_count += len(items)
                logs.append(f"arxiv:{query.name}:{len(items)}")
            except Exception as exc:
                collector_errors += 1
                logs.append(f"arxiv:{query.name}:error:{exc}")

        for feed in self.settings.rss_feeds:
            if not feed.is_enabled:
                continue
            try:
                items = self.rss_collector.fetch_feed(
                    source_name=feed.name,
                    feed_url=feed.url,
                    topic=feed.topic,
                    max_results=self.settings.global_config.max_candidates_per_source,
                )
                for item in items:
                    self._persist_item(item)
                fetched_count += len(items)
                logs.append(f"rss:{feed.name}:{len(items)}")
            except Exception as exc:
                collector_errors += 1
                logs.append(f"rss:{feed.name}:error:{exc}")

        for repo in self.settings.github_tracked_repos:
            if not repo.is_enabled:
                continue
            try:
                items = self.github_collector.fetch_tracked_repo(repo=repo.repo, topic=repo.topic)
                for item in items:
                    self._persist_item(item)
                fetched_count += len(items)
                logs.append(f"github_repo:{repo.repo}:{len(items)}")
            except Exception as exc:
                collector_errors += 1
                logs.append(f"github_repo:{repo.repo}:error:{exc}")

        for search_query in self.settings.github_search_queries:
            if not search_query.is_enabled:
                continue
            try:
                items = self.github_collector.fetch_search(
                    name=search_query.name,
                    query=search_query.query,
                    topic=search_query.topic,
                    max_results=self.settings.global_config.max_candidates_per_source,
                )
                for item in items:
                    self._persist_item(item)
                fetched_count += len(items)
                logs.append(f"github_search:{search_query.name}:{len(items)}")
            except Exception as exc:
                collector_errors += 1
                logs.append(f"github_search:{search_query.name}:error:{exc}")

        self.connection.commit()
        if fetched_count == 0 and collector_errors > 0:
            raise RuntimeError("All collectors failed or returned no items.")
        return fetched_count

    def score_candidates(self, logs: list[str]) -> dict[str, list[ShortlistCandidate]]:
        candidate_items: list[StoredItem] = []
        for topic in ("uq_hpc", "llm"):
            candidate_items.extend(self.items_repo.list_recent_candidates(topic=topic, limit=400))

        if not candidate_items:
            raise RuntimeError("No candidate items available to score.")

        score_updates, shortlists = score_and_shortlist(
            candidate_items,
            sent_titles=self.items_repo.recent_sent_titles(),
            sent_domain_titles=self.items_repo.recent_sent_domain_titles(),
            max_per_topic=self.settings.global_config.max_shortlist_per_topic,
        )
        self.items_repo.update_scores(score_updates)
        self.connection.commit()
        shortlist_sizes = {topic: len(candidates) for topic, candidates in shortlists.items()}
        logs.append("shortlists:" + json.dumps(shortlist_sizes, sort_keys=True))
        return shortlists

    def _create_issue_from_payload(
        self,
        *,
        issue_payload: NewsletterIssuePayload,
        subject: str,
        run_at: str,
    ) -> tuple[int, str]:
        html_body = render_issue_html(issue_payload, generated_at=utc_now())
        issue_id = self.issues_repo.create_issue(
            run_at=run_at,
            subject=subject,
            model_name=self.settings.openai_model,
            status="drafted",
            html_body=html_body,
            json_payload=issue_payload.model_dump(),
        )
        for section in issue_payload.sections:
            for rank, item in enumerate(section.items, start=1):
                self.items_repo.attach_generated_content(
                    issue_id=issue_id,
                    section_name=section.name,
                    rank_in_section=rank,
                    item_id=int(item.candidate_id),
                    generated_summary=item.summary,
                    generated_why_it_matters=item.why_it_matters,
                )
        self.connection.commit()
        return issue_id, html_body

    def generate_issue(
        self,
        *,
        shortlists: dict[str, list[ShortlistCandidate]],
        logs: list[str],
    ) -> tuple[int, NewsletterIssuePayload, str, bool]:
        subject = self._edition_subject()
        existing_issue = self.issues_repo.get_by_subject(subject)
        if existing_issue is not None and str(existing_issue["status"]) in {"drafted", "sent"}:
            issue_payload = NewsletterIssuePayload.model_validate_json(
                existing_issue["json_payload"]
            )
            logs.append(f"issue:reused:{existing_issue['id']}:{existing_issue['status']}")
            return int(existing_issue["id"]), issue_payload, str(existing_issue["html_body"]), True

        run_at = utc_now().isoformat()
        issue_payload = generate_issue_from_shortlist(
            run_date=datetime.now(ZoneInfo(self.settings.global_config.timezone)).date(),
            shortlists=shortlists,
            llm_client=self.llm_client or self._build_llm_client(),
        )
        issue_payload.subject = subject
        issue_id, html_body = self._create_issue_from_payload(
            issue_payload=issue_payload,
            subject=subject,
            run_at=run_at,
        )
        logs.append(f"issue:created:{issue_id}")
        return issue_id, issue_payload, html_body, False

    def _write_preview(self, html_body: str) -> Path:
        preview_path = self.settings.preview_output_path
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_text(html_body, encoding="utf-8")
        return preview_path

    def _send_issue_email(self, *, issue_payload: NewsletterIssuePayload, html_body: str) -> None:
        self.gmail_sender(
            client_secret_file=self.settings.gmail_client_secret_path,
            token_file=self.settings.gmail_token_path,
            sender=self.settings.sender_email,
            recipient=self.settings.recipient_email,
            subject=issue_payload.subject,
            html_body=html_body,
            text_body=render_issue_text(issue_payload),
        )

    def fetch_only(self) -> PipelineResult:
        self.initialize()
        run_id = self.runs_repo.create_run()
        logs: list[str] = []
        fetched_count = 0
        try:
            fetched_count = self.fetch_sources(logs)
            self.runs_repo.finish_run(
                run_id,
                status="fetched",
                fetched_count=fetched_count,
                shortlisted_count=0,
                selected_count=0,
                logs=logs,
            )
            self.connection.commit()
            return PipelineResult(
                subject=self._edition_subject(),
                preview_path=None,
                fetched_count=fetched_count,
                shortlisted_count=0,
                selected_count=0,
                issue_id=None,
                status="fetched",
            )
        except Exception as exc:
            self.runs_repo.fail_run(
                run_id,
                error_message=str(exc),
                fetched_count=fetched_count,
                shortlisted_count=0,
                selected_count=0,
                logs=logs,
            )
            self.connection.commit()
            raise

    def score_only(self) -> PipelineResult:
        self.initialize()
        run_id = self.runs_repo.create_run()
        logs: list[str] = []
        shortlisted_count = 0
        try:
            shortlists = self.score_candidates(logs)
            shortlisted_count = sum(len(bucket) for bucket in shortlists.values())
            self.runs_repo.finish_run(
                run_id,
                status="scored",
                fetched_count=0,
                shortlisted_count=shortlisted_count,
                selected_count=0,
                logs=logs,
            )
            self.connection.commit()
            return PipelineResult(
                subject=self._edition_subject(),
                preview_path=None,
                fetched_count=0,
                shortlisted_count=shortlisted_count,
                selected_count=0,
                issue_id=None,
                status="scored",
            )
        except Exception as exc:
            self.runs_repo.fail_run(
                run_id,
                error_message=str(exc),
                fetched_count=0,
                shortlisted_count=shortlisted_count,
                selected_count=0,
                logs=logs,
            )
            self.connection.commit()
            raise

    def preview_only(self) -> PipelineResult:
        self.initialize()
        run_id = self.runs_repo.create_run()
        logs: list[str] = []
        shortlisted_count = selected_count = 0
        try:
            shortlists = self.score_candidates(logs)
            shortlisted_count = sum(len(bucket) for bucket in shortlists.values())
            issue_id, issue_payload, html_body, reused = self.generate_issue(
                shortlists=shortlists,
                logs=logs,
            )
            selected_count = sum(len(section.items) for section in issue_payload.sections)
            preview_path = self._write_preview(html_body)
            self.runs_repo.finish_run(
                run_id,
                status="previewed",
                fetched_count=0,
                shortlisted_count=shortlisted_count,
                selected_count=selected_count,
                logs=logs,
            )
            self.connection.commit()
            return PipelineResult(
                subject=issue_payload.subject,
                preview_path=preview_path,
                fetched_count=0,
                shortlisted_count=shortlisted_count,
                selected_count=selected_count,
                issue_id=issue_id,
                status="previewed",
                reused_existing_issue=reused,
            )
        except Exception as exc:
            self.runs_repo.fail_run(
                run_id,
                error_message=str(exc),
                fetched_count=0,
                shortlisted_count=shortlisted_count,
                selected_count=selected_count,
                logs=logs,
            )
            self.connection.commit()
            raise

    def run(self, *, send_email: bool) -> PipelineResult:
        self.initialize()
        run_id = self.runs_repo.create_run()
        logs: list[str] = []
        fetched_count = shortlisted_count = selected_count = 0
        preview_path: Path | None = None
        try:
            fetched_count = self.fetch_sources(logs)
            shortlists = self.score_candidates(logs)
            shortlisted_count = sum(len(bucket) for bucket in shortlists.values())
            issue_id, issue_payload, html_body, reused = self.generate_issue(
                shortlists=shortlists,
                logs=logs,
            )
            selected_count = sum(len(section.items) for section in issue_payload.sections)
            preview_path = self._write_preview(html_body)

            if send_email:
                issue_row = self.issues_repo.get_issue(issue_id)
                if issue_row is None or issue_row["status"] != "sent":
                    self._send_issue_email(issue_payload=issue_payload, html_body=html_body)
                    self.issues_repo.update_status(issue_id, status="sent")
                    logs.append(f"email:sent:{issue_id}")
                else:
                    logs.append(f"email:reused-sent:{issue_id}")

            final_status = "sent" if send_email else "previewed"
            self.runs_repo.finish_run(
                run_id,
                status=final_status,
                fetched_count=fetched_count,
                shortlisted_count=shortlisted_count,
                selected_count=selected_count,
                logs=logs,
            )
            self.connection.commit()
            return PipelineResult(
                subject=issue_payload.subject,
                preview_path=preview_path,
                fetched_count=fetched_count,
                shortlisted_count=shortlisted_count,
                selected_count=selected_count,
                issue_id=issue_id,
                status=final_status,
                reused_existing_issue=reused,
            )
        except Exception as exc:
            logger.exception("Pipeline run failed")
            self.runs_repo.fail_run(
                run_id,
                error_message=str(exc),
                fetched_count=fetched_count,
                shortlisted_count=shortlisted_count,
                selected_count=selected_count,
                logs=logs,
            )
            self.connection.commit()
            raise


def run_once(settings: AppSettings, *, send_email: bool) -> PipelineResult:
    with NewsletterPipeline(settings) as pipeline:
        return pipeline.run(send_email=send_email)
