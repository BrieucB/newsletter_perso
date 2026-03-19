from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.db import connect, init_db
from app.llm.schemas import NewsletterIssuePayload
from app.pipeline.run_once import NewsletterPipeline, PipelineResult
from app.settings import EnvironmentConfig
from tests.conftest import build_test_profile_context, build_test_settings
from tests.test_repositories_services_extra import _insert_item, _make_item


def _issue_payload(item_ids: list[int]) -> NewsletterIssuePayload:
    return NewsletterIssuePayload.model_validate(
        {
            "subject": "Briefing | 2026-03-19",
            "intro": "Short intro.",
            "sections": [
                {
                    "name": "Most relevant for your work",
                    "items": [
                        {
                            "candidate_id": str(item_id),
                            "title": f"Item {item_id}",
                            "what_happened": "Short summary.",
                            "why_you_should_care": "Useful.",
                            "fit_tag": "current_work" if index < 4 else "llm_background",
                            "source_name": "Source",
                            "source_url": f"https://example.com/{item_id}",
                        }
                        for index, item_id in enumerate(item_ids)
                    ],
                }
            ],
            "selection_notes": ["Balanced issue."],
        }
    )


def test_pipeline_build_llm_client_requires_api_key(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path).model_copy(
        update={"env": EnvironmentConfig(newsletter_recipient="reader@example.com")}
    )
    pipeline = NewsletterPipeline(settings, connection=connect(settings.db_path))

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        pipeline._build_llm_client()


def test_pipeline_send_via_gmail_delegates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    pipeline = NewsletterPipeline(settings, connection=connect(settings.db_path))

    monkeypatch.setattr(
        "app.email.gmail_send.send_gmail_message",
        lambda **kwargs: {"id": "msg-1", "subject": kwargs["subject"]},
    )

    result = pipeline._send_via_gmail(subject="Subject")

    assert result["id"] == "msg-1"


def test_pipeline_fetch_sources_raises_when_all_collectors_fail(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    init_db(settings.db_path)

    class FailingArxiv:
        def fetch_query(self, **kwargs: Any) -> list[object]:
            raise RuntimeError("arxiv failed")

    class FailingRSS:
        def fetch_feed(self, **kwargs: Any) -> list[object]:
            raise RuntimeError("rss failed")

    class FailingGitHub:
        def fetch_tracked_repo(self, **kwargs: Any) -> list[object]:
            raise RuntimeError("repo failed")

        def fetch_search(self, **kwargs: Any) -> list[object]:
            raise RuntimeError("search failed")

    pipeline = NewsletterPipeline(
        settings,
        connection=connect(settings.db_path),
        arxiv_collector=FailingArxiv(),  # type: ignore[arg-type]
        rss_collector=FailingRSS(),  # type: ignore[arg-type]
        github_collector=FailingGitHub(),  # type: ignore[arg-type]
    )

    logs: list[str] = []
    with pytest.raises(RuntimeError, match="All collectors failed"):
        pipeline.fetch_sources(logs)

    assert any("arxiv:" in entry for entry in logs)
    assert any("github_search:" in entry for entry in logs)


def test_pipeline_fetch_score_preview_wrappers_succeed(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    init_db(settings.db_path)
    pipeline = NewsletterPipeline(settings, connection=connect(settings.db_path))
    preview_path = settings.preview_output_path
    issue_payload = _issue_payload([1, 2, 3, 4, 5, 6, 7, 8])

    pipeline.fetch_sources = lambda logs: 5  # type: ignore[method-assign]
    fetch_result = pipeline.fetch_only()

    pipeline.score_candidates = (  # type: ignore[method-assign]
        lambda logs: ({"uq_hpc": [object()] * 3, "llm": [object()] * 2}, {})
    )
    score_result = pipeline.score_only()

    pipeline.profile_service.load_runtime_context = lambda: build_test_profile_context()  # type: ignore[method-assign]
    pipeline.generate_issue = lambda **kwargs: (7, issue_payload, "<p>html</p>", False)  # type: ignore[method-assign]
    pipeline._write_preview = lambda html: preview_path  # type: ignore[method-assign]
    preview_result = pipeline.preview_only()

    assert fetch_result.status == "fetched"
    assert fetch_result.fetched_count == 5
    assert score_result.status == "scored"
    assert score_result.shortlisted_count == 5
    assert preview_result.status == "previewed"
    assert preview_result.selected_count == 8
    assert preview_result.preview_path == preview_path


def test_pipeline_generate_issue_reuses_existing_issue_and_refreshes_html(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    init_db(settings.db_path)
    pipeline = NewsletterPipeline(settings, connection=connect(settings.db_path))
    issue_payload = _issue_payload([1, 2, 3, 4, 5, 6, 7, 8])
    issue_id = pipeline.issues_repo.create_issue(
        run_at=datetime.now(tz=UTC).isoformat(),
        subject=pipeline._edition_subject(),
        model_name=settings.openai_model,
        status="drafted",
        html_body="<p>stale</p>",
        json_payload=issue_payload.model_dump(),
    )
    pipeline.connection.commit()
    pipeline._render_issue_html_for_issue = lambda **kwargs: "<p>refreshed</p>"  # type: ignore[method-assign]

    reused_id, reused_payload, html_body, reused = pipeline.generate_issue(
        shortlists={},
        profile_context=build_test_profile_context(),
        logs=[],
    )

    stored_issue = pipeline.issues_repo.get_issue(issue_id)
    assert reused is True
    assert reused_id == issue_id
    assert reused_payload.subject == issue_payload.subject
    assert html_body == "<p>refreshed</p>"
    assert stored_issue is not None and stored_issue["html_body"] == "<p>refreshed</p>"


def test_pipeline_generate_issue_with_invalid_existing_payload_falls_back_to_new_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = build_test_settings(tmp_path)
    init_db(settings.db_path)
    pipeline = NewsletterPipeline(
        settings,
        connection=connect(settings.db_path),
        llm_client=object(),
    )
    item_ids = [
        _insert_item(
            pipeline.items_repo,
            _make_item(
                external_id=f"item-{index}",
                url=f"https://example.com/{index}",
            ),
        )
        for index in range(1, 9)
    ]
    pipeline.issues_repo.create_issue(
        run_at=datetime.now(tz=UTC).isoformat(),
        subject=pipeline._edition_subject(),
        model_name=settings.openai_model,
        status="drafted",
        html_body="<p>broken</p>",
        json_payload={"bad": "payload"},
    )
    issue_payload = _issue_payload(item_ids)
    monkeypatch.setattr(
        "app.pipeline.run_once.generate_issue_from_shortlist",
        lambda **kwargs: issue_payload,
    )

    issue_id, created_payload, html_body, reused = pipeline.generate_issue(
        shortlists={"uq_hpc": [], "llm": []},
        profile_context=build_test_profile_context(),
        logs=[],
    )

    assert reused is False
    assert created_payload.subject == pipeline._edition_subject()
    assert html_body
    stored_issue = pipeline.issues_repo.get_issue(issue_id)
    assert stored_issue is not None and stored_issue["status"] == "drafted"


def test_pipeline_sync_feedback_handles_error_and_rebuilds_on_insert(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    init_db(settings.db_path)
    pipeline = NewsletterPipeline(settings, connection=connect(settings.db_path))
    logs: list[str] = []

    pipeline.feedback_service.sync_remote_feedback = lambda: 2  # type: ignore[method-assign]
    rebuilt = {"called": 0}
    pipeline.profile_service.rebuild_snapshot_from_feedback = (  # type: ignore[method-assign]
        lambda: rebuilt.__setitem__("called", 1)
    )

    inserted = pipeline.sync_feedback(logs, fail_on_error=False)

    assert inserted == 2
    assert rebuilt["called"] == 1
    assert "feedback_sync:2" in logs

    pipeline.feedback_service.sync_remote_feedback = (  # type: ignore[method-assign]
        lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    logs = []
    assert pipeline.sync_feedback(logs, fail_on_error=False) == 0
    assert any("feedback_sync:error:boom" in entry for entry in logs)
    with pytest.raises(RuntimeError, match="boom"):
        pipeline.sync_feedback([], fail_on_error=True)


@pytest.mark.parametrize(
    ("method_name", "failing_method"),
    [
        ("fetch_only", "fetch_sources"),
        ("score_only", "score_candidates"),
        ("preview_only", "score_candidates"),
    ],
)
def test_pipeline_wrapper_methods_record_failed_runs(
    tmp_path: Path,
    method_name: str,
    failing_method: str,
) -> None:
    settings = build_test_settings(tmp_path)
    init_db(settings.db_path)
    pipeline = NewsletterPipeline(settings, connection=connect(settings.db_path))
    setattr(
        pipeline,
        failing_method,
        lambda logs: (_ for _ in ()).throw(RuntimeError(f"{failing_method} failed")),
    )

    with pytest.raises(RuntimeError, match="failed"):
        getattr(pipeline, method_name)()

    row = pipeline.connection.execute(
        "SELECT status, error_message FROM pipeline_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None and row["status"] == "failed"


def test_pipeline_run_handles_preview_and_sent_reuse(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    init_db(settings.db_path)
    pipeline = NewsletterPipeline(settings, connection=connect(settings.db_path))
    preview_path = settings.preview_output_path
    issue_payload = _issue_payload([1, 2, 3, 4, 5, 6, 7, 8])
    issue_id = 5
    sent_calls = {"count": 0}

    pipeline.fetch_sources = lambda logs: 6  # type: ignore[method-assign]
    pipeline.score_candidates = (  # type: ignore[method-assign]
        lambda logs: ({"uq_hpc": [object()] * 4, "llm": [object()] * 4}, {})
    )
    pipeline.profile_service.load_runtime_context = lambda: build_test_profile_context()  # type: ignore[method-assign]
    pipeline.generate_issue = lambda **kwargs: (issue_id, issue_payload, "<p>html</p>", True)  # type: ignore[method-assign]
    pipeline._write_preview = lambda html: preview_path  # type: ignore[method-assign]
    pipeline._send_issue_email = (  # type: ignore[method-assign]
        lambda **kwargs: sent_calls.__setitem__("count", sent_calls["count"] + 1)
    )
    pipeline.issues_repo.get_issue = lambda issue_id: {"status": "sent"}  # type: ignore[method-assign]

    preview_result = pipeline.run(send_email=False)
    send_result = pipeline.run(send_email=True)

    assert preview_result.status == "previewed"
    assert send_result.status == "sent"
    assert sent_calls["count"] == 0


def test_pipeline_run_sends_email_when_issue_not_sent(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    init_db(settings.db_path)
    pipeline = NewsletterPipeline(settings, connection=connect(settings.db_path))
    preview_path = settings.preview_output_path
    issue_payload = _issue_payload([1, 2, 3, 4, 5, 6, 7, 8])
    issue_id = 8
    sent_calls = {"count": 0}

    pipeline.fetch_sources = lambda logs: 6  # type: ignore[method-assign]
    pipeline.score_candidates = (  # type: ignore[method-assign]
        lambda logs: ({"uq_hpc": [object()] * 4, "llm": [object()] * 4}, {})
    )
    pipeline.profile_service.load_runtime_context = lambda: build_test_profile_context()  # type: ignore[method-assign]
    pipeline.generate_issue = lambda **kwargs: (issue_id, issue_payload, "<p>html</p>", False)  # type: ignore[method-assign]
    pipeline._write_preview = lambda html: preview_path  # type: ignore[method-assign]
    pipeline._send_issue_email = (  # type: ignore[method-assign]
        lambda **kwargs: sent_calls.__setitem__("count", sent_calls["count"] + 1)
    )
    pipeline.issues_repo.get_issue = lambda issue_id: {"status": "drafted"}  # type: ignore[method-assign]

    result = pipeline.run(send_email=True)

    issue_row = pipeline.connection.execute(
        "SELECT status FROM issues ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert result.status == "sent"
    assert sent_calls["count"] == 1
    assert issue_row is None or issue_row["status"] == "sent"


def test_pipeline_record_feedback_and_explain_issue(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    init_db(settings.db_path)
    pipeline = NewsletterPipeline(settings, connection=connect(settings.db_path))
    item_id = _insert_item(pipeline.items_repo, _make_item())
    issue_id = pipeline.issues_repo.create_issue(
        run_at=datetime.now(tz=UTC).isoformat(),
        subject="Briefing | 2026-03-19",
        model_name=settings.openai_model,
        status="drafted",
        html_body="<p>draft</p>",
        json_payload=_issue_payload([item_id]).model_dump(),
    )
    pipeline.items_repo.attach_generated_content(
        issue_id=issue_id,
        section_name="LLM engineering you should understand",
        rank_in_section=1,
        item_id=item_id,
        generated_summary="summary",
        generated_why_it_matters="why",
        fit_tag="llm_background",
        selection_reason_json='{"why":"selected"}',
    )
    pipeline.connection.commit()

    feedback_id = pipeline.record_feedback(item_id=item_id, vote="+")
    explanations = pipeline.explain_issue(issue_id=issue_id)

    assert feedback_id > 0
    assert explanations[0]["item_id"] == item_id


def test_pipeline_record_feedback_errors_for_unknown_context(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    init_db(settings.db_path)
    pipeline = NewsletterPipeline(settings, connection=connect(settings.db_path))

    with pytest.raises(ValueError, match="Unknown item_id"):
        pipeline.record_feedback(item_id=999, vote="+")

    item_id = _insert_item(pipeline.items_repo, _make_item())
    with pytest.raises(ValueError, match="has not been part of any issue yet"):
        pipeline.record_feedback(item_id=item_id, vote="+")


def test_pipeline_refresh_show_sync_wrappers(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    init_db(settings.db_path)
    pipeline = NewsletterPipeline(settings, connection=connect(settings.db_path))

    pipeline.profile_service.refresh_profiles = lambda: build_test_profile_context()  # type: ignore[method-assign]
    pipeline.profile_service.describe_context = lambda: {"profile": "shown"}  # type: ignore[method-assign]
    pipeline.sync_feedback = lambda logs, fail_on_error: 3  # type: ignore[method-assign]

    refreshed = pipeline.refresh_profiles()
    shown = pipeline.show_profile()
    synced = pipeline.feedback_sync_only()

    assert refreshed["explicit_profile"]["tone"] == "mentor_note_to_self"
    assert shown == {"profile": "shown"}
    assert synced == 3


def test_run_once_helper_uses_pipeline_context(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = build_test_settings(tmp_path)
    expected = PipelineResult(
        subject="Briefing | 2026-03-19",
        preview_path=Path("preview/out.html"),
        fetched_count=1,
        shortlisted_count=1,
        selected_count=1,
        issue_id=1,
        status="previewed",
    )

    class FakePipeline:
        def __init__(self, loaded_settings: Any) -> None:
            assert loaded_settings == settings

        def __enter__(self) -> FakePipeline:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def run(self, *, send_email: bool) -> PipelineResult:
            assert send_email is False
            return expected

    monkeypatch.setattr("app.pipeline.run_once.NewsletterPipeline", FakePipeline)

    from app.pipeline.run_once import run_once

    assert run_once(settings, send_email=False) == expected
