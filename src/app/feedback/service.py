from __future__ import annotations

import logging

import requests

from app.feedback.client import FeedbackSyncClient
from app.feedback.models import FeedbackRenderLinks
from app.feedback.signing import build_feedback_url
from app.llm.schemas import NewsletterIssuePayload
from app.repositories.features import FeaturesRepository
from app.repositories.feedback import FeedbackRepository
from app.repositories.items import ItemsRepository
from app.settings import AppSettings

logger = logging.getLogger(__name__)


class FeedbackService:
    def __init__(
        self,
        settings: AppSettings,
        *,
        feedback_repo: FeedbackRepository,
        items_repo: ItemsRepository,
        features_repo: FeaturesRepository,
        client: FeedbackSyncClient | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.settings = settings
        self.feedback_repo = feedback_repo
        self.items_repo = items_repo
        self.features_repo = features_repo
        self.session = session or requests.Session()
        self.client = client or self._build_client()

    def _build_client(self) -> FeedbackSyncClient | None:
        if not self.settings.feedback_enabled:
            return None
        assert self.settings.feedback_web_app_url is not None
        assert self.settings.feedback_signing_secret is not None
        return FeedbackSyncClient(
            base_url=self.settings.feedback_web_app_url,
            secret=self.settings.feedback_signing_secret,
            session=self.session,
        )

    def build_issue_feedback_links(
        self,
        *,
        issue_id: int,
        issue_payload: NewsletterIssuePayload,
    ) -> dict[str, FeedbackRenderLinks]:
        if not self.settings.feedback_enabled:
            return {}
        assert self.settings.feedback_web_app_url is not None
        assert self.settings.feedback_signing_secret is not None
        links: dict[str, FeedbackRenderLinks] = {}
        for section in issue_payload.sections:
            for item in section.items:
                item_id = int(item.candidate_id)
                links[item.candidate_id] = FeedbackRenderLinks(
                    upvote_url=build_feedback_url(
                        base_url=self.settings.feedback_web_app_url,
                        secret=self.settings.feedback_signing_secret,
                        issue_id=issue_id,
                        item_id=item_id,
                        vote="+",
                        recipient_key=self.settings.feedback_recipient_key,
                        subject=issue_payload.subject,
                        item_title=item.title,
                        source_url=item.source_url,
                        ttl_days=self.settings.feedback_link_ttl_days,
                    ),
                    downvote_url=build_feedback_url(
                        base_url=self.settings.feedback_web_app_url,
                        secret=self.settings.feedback_signing_secret,
                        issue_id=issue_id,
                        item_id=item_id,
                        vote="-",
                        recipient_key=self.settings.feedback_recipient_key,
                        subject=issue_payload.subject,
                        item_title=item.title,
                        source_url=item.source_url,
                        ttl_days=self.settings.feedback_link_ttl_days,
                    ),
                )
        return links

    def sync_remote_feedback(self) -> int:
        if self.client is None:
            return 0

        inserted_count = 0
        for event in self.client.fetch_events():
            if event.recipient_key != self.settings.feedback_recipient_key:
                continue
            item = self.items_repo.get_item(event.item_id)
            issue_context = self.items_repo.get_issue_context(
                issue_id=event.issue_id,
                item_id=event.item_id,
            )
            if item is None or issue_context is None:
                logger.warning(
                    "Skipping feedback event for unknown item/issue context",
                    extra={"event_id": event.external_event_id},
                )
                continue
            feature_snapshot = self.features_repo.get_item_features(event.item_id)
            inserted = self.feedback_repo.upsert_feedback_event(
                issue_id=event.issue_id,
                item_id=event.item_id,
                vote=event.vote,
                external_event_id=event.external_event_id,
                channel="email_link",
                recipient_key=event.recipient_key,
                context_json={
                    "source_name": item.source_name,
                    "topic": item.topic,
                    "content_type": item.content_type,
                    "fit_tag": item.fit_tag,
                    "section_name": issue_context["section_name"],
                    "source_url": event.source_url or item.url,
                    "item_title": event.item_title or item.title,
                    "feature_snapshot": (
                        feature_snapshot.model_dump(mode="json") if feature_snapshot else {}
                    ),
                },
                created_at=event.created_at.isoformat(),
            )
            inserted_count += int(inserted)
        return inserted_count

    def html_contains_feedback_links(self, html_body: str) -> bool:
        return "+ good rec" in html_body and "- bad rec" in html_body
