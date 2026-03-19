from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.db import connect, init_db
from app.feedback.models import RemoteFeedbackEvent
from app.feedback.service import FeedbackService
from app.llm.schemas import NewsletterIssuePayload
from app.models import ItemFeatures, NormalizedItem
from app.profile.models import AggregatedRepoProfile, RepoProfile
from app.profile.service import ProfileService
from app.repositories.features import FeaturesRepository
from app.repositories.feedback import FeedbackRepository
from app.repositories.issues import IssuesRepository
from app.repositories.items import ItemsRepository
from app.repositories.profiles import ProfilesRepository
from app.settings import LocalRepoConfig, RepoProfilingConfig
from app.utils.hashing import stable_hash
from app.utils.text import normalize_title
from tests.conftest import build_test_settings


def _make_item(
    *,
    topic: str = "llm",
    source_kind: str = "rss",
    source_name: str = "OpenAI News",
    external_id: str = "item-1",
    title: str = "Serving benchmark update",
    url: str = "https://example.com/item-1",
    summary: str = "Engineering update.",
) -> NormalizedItem:
    return NormalizedItem(
        topic=topic,  # type: ignore[arg-type]
        source_kind=source_kind,
        source_name=source_name,
        external_id=external_id,
        title=title,
        url=url,
        authors=["Author"],
        published_at=datetime.now(tz=UTC),
        raw_summary=summary,
        raw_payload={"feed_url": "https://example.com/feed.xml", "stargazers_count": 1200},
        tags=["tag-1"],
    )


def _insert_item(repository: ItemsRepository, item: NormalizedItem) -> int:
    source_id = repository.ensure_source(
        kind=item.source_kind,
        name=item.source_name,
        config={"source_name": item.source_name, "source_kind": item.source_kind},
    )
    return repository.upsert_normalized_item(
        source_id=source_id,
        normalized_item=item,
        normalized_title=normalize_title(item.title),
        content_hash=stable_hash([item.title, item.raw_summary or "", item.url]),
    )


def _make_features(item_id: int) -> ItemFeatures:
    return ItemFeatures(
        item_id=item_id,
        content_type="tool_or_repo",
        fit_tag="llm_background",
        freshness_score=4.5,
        source_quality_score=4.0,
        work_relevance_score=1.0,
        llm_map_value_score=3.0,
        architectural_tradeoff_score=1.2,
        practical_reusability_score=3.4,
        interview_background_score=2.1,
        repo_profile_match_score=0.6,
        traction_score=2.4,
        theoretical_penalty=0.0,
        hype_penalty=0.0,
        genericity_penalty=0.0,
        feature_json={"kind": "test"},
    )


def _make_issue_payload(item_id: int) -> NewsletterIssuePayload:
    return NewsletterIssuePayload.model_validate(
        {
            "subject": "Briefing | 2026-03-19",
            "intro": "Short intro.",
            "sections": [
                {
                    "name": "LLM engineering you should understand",
                    "items": [
                        {
                            "candidate_id": str(item_id),
                            "title": "Serving benchmark update",
                            "what_happened": "Short summary.",
                            "why_you_should_care": "Useful for systems understanding.",
                            "fit_tag": "llm_background",
                            "source_name": "OpenAI News",
                            "source_url": "https://example.com/item-1",
                        }
                    ],
                }
            ],
        }
    )


def test_features_repository_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "features.sqlite3"
    init_db(db_path)
    connection = connect(db_path)
    items_repository = ItemsRepository(connection)
    repository = FeaturesRepository(connection)

    assert repository.get_item_features(999) is None

    item_id = _insert_item(items_repository, _make_item())
    features = _make_features(item_id=item_id)
    repository.upsert_item_features(features)
    loaded = repository.get_item_features(item_id)

    assert loaded is not None
    assert loaded.item_id == item_id
    assert loaded.content_type == "tool_or_repo"
    assert loaded.created_at is not None


def test_profiles_repository_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "profiles.sqlite3"
    init_db(db_path)
    connection = connect(db_path)
    repository = ProfilesRepository(connection)

    repository.replace_active_user_profile({"tone": "mentor_note_to_self"})
    active_user = repository.get_active_user_profile()
    assert active_user is not None
    assert "mentor_note_to_self" in active_user["profile_json"]

    repo_profile = RepoProfile(
        repo_name="Korali",
        repo_path="/tmp/korali",
        detected_languages=["python"],
        detected_libraries_tools=["numpy"],
        inferred_scientific_domains=["bayesian inference"],
        inferred_engineering_themes=["gpu computing"],
        inferred_infra_themes=["slurm orchestration"],
        workflow_markers=["SLURM"],
        summary="Profile summary.",
        keywords=["bayesian inference"],
        confidence_by_theme={"bayesian inference": 1.0},
        fingerprint_hash="hash-1",
    )
    repository.replace_active_repo_profiles([repo_profile])
    rows = repository.list_active_repo_profiles()
    assert len(rows) == 1
    assert repository.row_to_repo_profile(rows[0]).repo_name == "Korali"

    snapshot_id = repository.create_profile_snapshot(
        explicit_profile_json={"tone": "mentor_note_to_self"},
        aggregated_repo_profile_json=AggregatedRepoProfile(repo_count=1).model_dump(),
        learned_preferences_json={"source_weights": {"OpenAI News": 0.2}},
    )
    snapshot = repository.get_latest_profile_snapshot()
    assert snapshot is not None and snapshot["id"] == snapshot_id
    assert repository.snapshot_learned_preferences(snapshot).source_weights["OpenAI News"] == 0.2


def test_items_repository_issue_helpers_and_shortlists(tmp_path: Path) -> None:
    db_path = tmp_path / "items.sqlite3"
    init_db(db_path)
    connection = connect(db_path)
    items_repo = ItemsRepository(connection)
    issues_repo = IssuesRepository(connection)

    first_id = _insert_item(items_repo, _make_item(topic="llm", external_id="item-1"))
    second_id = _insert_item(
        items_repo,
        _make_item(
            topic="uq_hpc",
            source_kind="arxiv",
            source_name="arXiv: Bayesian calibration",
            external_id="item-2",
            title="Calibration paper",
            url="https://arxiv.org/abs/2",
        ),
    )
    items_repo.update_scores({first_id: 9.0, second_id: 8.0})
    items_repo.update_personalization_fields(
        features_by_item_id={
            first_id: _make_features(first_id),
            second_id: _make_features(second_id).model_copy(
                update={"content_type": "paper", "fit_tag": "current_work"}
            ),
        },
        score_updates={first_id: 9.0, second_id: 8.0},
    )

    shortlist = items_repo.list_shortlist_candidates(topic="llm", limit=5)
    assert [item.id for item in shortlist] == [first_id]
    assert {item.id for item in items_repo.get_items_by_ids([first_id, second_id])} == {
        first_id,
        second_id,
    }

    issue_id = issues_repo.create_issue(
        run_at=datetime.now(tz=UTC).isoformat(),
        subject="Briefing | 2026-03-19",
        model_name="gpt-5.4-mini",
        status="sent",
        html_body="<p>sent</p>",
        json_payload={"subject": "Briefing | 2026-03-19", "intro": "", "sections": []},
    )
    items_repo.attach_generated_content(
        issue_id=issue_id,
        section_name="LLM engineering you should understand",
        rank_in_section=1,
        item_id=first_id,
        generated_summary="summary",
        generated_why_it_matters="why",
        fit_tag="llm_background",
        selection_reason_json='{"why":"selected"}',
    )
    connection.commit()

    latest_context = items_repo.get_latest_issue_context_for_item(first_id)
    issue_context = items_repo.get_issue_context(issue_id=issue_id, item_id=first_id)
    issue_items = items_repo.list_issue_items(issue_id)

    assert latest_context is not None and latest_context["issue_id"] == issue_id
    assert issue_context is not None
    assert issue_context["section_name"] == latest_context["section_name"]
    assert len(issue_items) == 1
    assert normalize_title("Serving benchmark update") in items_repo.recent_sent_titles()
    assert (
        "example.com",
        normalize_title("Serving benchmark update"),
    ) in items_repo.recent_sent_domain_titles()
    assert items_repo.list_recent_candidates(topic="llm", limit=5) == []


class FakeFeedbackClient:
    def __init__(self, events: list[RemoteFeedbackEvent]) -> None:
        self.events = events

    def fetch_events(self) -> list[RemoteFeedbackEvent]:
        return self.events


def test_feedback_service_builds_links_and_syncs_remote_feedback(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    init_db(settings.db_path)
    connection = connect(settings.db_path)
    items_repo = ItemsRepository(connection)
    issues_repo = IssuesRepository(connection)
    features_repo = FeaturesRepository(connection)
    feedback_repo = FeedbackRepository(connection)

    item_id = _insert_item(items_repo, _make_item())
    issue_id = issues_repo.create_issue(
        run_at=datetime.now(tz=UTC).isoformat(),
        subject="Briefing | 2026-03-19",
        model_name="gpt-5.4-mini",
        status="drafted",
        html_body="<p>draft</p>",
        json_payload=_make_issue_payload(item_id).model_dump(),
    )
    items_repo.attach_generated_content(
        issue_id=issue_id,
        section_name="LLM engineering you should understand",
        rank_in_section=1,
        item_id=item_id,
        generated_summary="summary",
        generated_why_it_matters="why",
        fit_tag="llm_background",
        selection_reason_json='{"why":"selected"}',
    )
    features_repo.upsert_item_features(_make_features(item_id))
    connection.commit()

    service = FeedbackService(
        settings,
        feedback_repo=feedback_repo,
        items_repo=items_repo,
        features_repo=features_repo,
        client=FakeFeedbackClient(
            [
                RemoteFeedbackEvent(
                    external_event_id="ignored-recipient",
                    issue_id=issue_id,
                    item_id=item_id,
                    vote="+",
                    recipient_key="someone-else",
                    created_at=datetime.now(tz=UTC),
                ),
                RemoteFeedbackEvent(
                    external_event_id="unknown-item",
                    issue_id=issue_id,
                    item_id=item_id + 100,
                    vote="+",
                    recipient_key=settings.feedback_recipient_key,
                    created_at=datetime.now(tz=UTC),
                ),
                RemoteFeedbackEvent(
                    external_event_id="event-1",
                    issue_id=issue_id,
                    item_id=item_id,
                    vote="+",
                    recipient_key=settings.feedback_recipient_key,
                    created_at=datetime.now(tz=UTC),
                    source_url="https://example.com/item-1",
                ),
            ]
        ),
    )

    links = service.build_issue_feedback_links(
        issue_id=issue_id,
        issue_payload=_make_issue_payload(item_id),
    )
    inserted_count = service.sync_remote_feedback()

    assert str(item_id) in links
    assert "vote" not in links[str(item_id)].upvote_url
    assert inserted_count == 1
    assert service.html_contains_feedback_links("Feedback: + good rec and - bad rec")
    rows = feedback_repo.list_feedback_contexts()
    assert len(rows) == 1
    assert rows[0].channel == "email_link"


def test_feedback_service_disables_links_when_feedback_not_configured(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    settings = settings.model_copy(
        update={
            "env": settings.env.model_copy(
                update={
                    "feedback_web_app_url": None,
                    "feedback_signing_secret": None,
                }
            )
        }
    )
    init_db(settings.db_path)
    connection = connect(settings.db_path)
    service = FeedbackService(
        settings,
        feedback_repo=FeedbackRepository(connection),
        items_repo=ItemsRepository(connection),
        features_repo=FeaturesRepository(connection),
    )

    assert (
        service.build_issue_feedback_links(issue_id=1, issue_payload=_make_issue_payload(1))
        == {}
    )
    assert service.sync_remote_feedback() == 0
    assert not service.html_contains_feedback_links("No feedback controls here")


def test_profile_service_refresh_and_snapshot_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = build_test_settings(tmp_path)
    settings = settings.model_copy(
        update={
            "repo_profiling": RepoProfilingConfig(enabled=True),
            "local_repos": [LocalRepoConfig(name="Korali", path="repo_cache/Korali", clone_url="https://example.com/repo.git")],
        }
    )
    init_db(settings.db_path)
    connection = connect(settings.db_path)
    profiles_repo = ProfilesRepository(connection)
    feedback_repo = FeedbackRepository(connection)
    service = ProfileService(settings, profiles_repo=profiles_repo, feedback_repo=feedback_repo)

    repo_profile = RepoProfile(
        repo_name="Korali",
        repo_path=str(tmp_path / "repo_cache" / "Korali"),
        detected_languages=["python"],
        detected_libraries_tools=["numpy"],
        inferred_scientific_domains=["bayesian inference"],
        inferred_engineering_themes=["gpu computing"],
        inferred_infra_themes=["slurm orchestration"],
        workflow_markers=["SLURM"],
        summary="Profile summary.",
        keywords=["bayesian inference"],
        confidence_by_theme={"bayesian inference": 1.0},
        fingerprint_hash="hash-1",
    )

    monkeypatch.setattr(
        "app.profile.service.ensure_local_clone",
        lambda repo_path, clone_url: repo_path,
    )
    monkeypatch.setattr(
        "app.profile.service.scan_repo",
        lambda resolved_path, repo_name, ignore_dirs, ignore_file_globs: SimpleNamespace(
            repo_name=repo_name,
            repo_path=resolved_path,
        ),
    )
    monkeypatch.setattr("app.profile.service.build_repo_profile", lambda scan_result: repo_profile)
    monkeypatch.setattr(
        "app.profile.service.aggregate_repo_profiles",
        lambda profiles: AggregatedRepoProfile(repo_count=len(profiles), summary="Aggregated."),
    )

    service.ensure_explicit_profile()
    service.ensure_explicit_profile()
    context = service.refresh_profiles()
    loaded = service.load_runtime_context()
    described = service.describe_context()
    service.rebuild_snapshot_from_feedback()

    active_profile = profiles_repo.get_active_user_profile()
    snapshots = connection.execute("SELECT COUNT(*) AS count FROM profile_snapshots").fetchone()

    assert active_profile is not None
    assert context.aggregated_repo_profile.repo_count == 1
    assert loaded.aggregated_repo_profile.summary == "Aggregated."
    assert described["aggregated_repo_profile"]["repo_count"] == 1
    assert snapshots["count"] >= 2
