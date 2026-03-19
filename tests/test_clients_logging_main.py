from __future__ import annotations

import base64
import json
import sys
from email import message_from_bytes
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.email import gmail_auth, gmail_send
from app.llm.client import OpenAIClient
from app.llm.schemas import NewsletterIssuePayload
from app.logging_config import configure_logging
from tests.conftest import build_test_settings


class FakeCredentials:
    def __init__(
        self,
        *,
        valid: bool,
        expired: bool = False,
        refresh_token: str | None = None,
    ) -> None:
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self.refreshed_with: object | None = None

    def refresh(self, request: object) -> None:
        self.refreshed_with = request
        self.valid = True
        self.expired = False

    def to_json(self) -> str:
        return json.dumps({"valid": self.valid, "expired": self.expired})


class FakeFlow:
    def __init__(self, credentials: FakeCredentials) -> None:
        self.credentials = credentials
        self.port: int | None = None

    def run_local_server(self, port: int) -> FakeCredentials:
        self.port = port
        return self.credentials


def _sample_issue_payload() -> NewsletterIssuePayload:
    return NewsletterIssuePayload.model_validate(
        {
            "subject": "Briefing | 2026-03-19",
            "intro": "Short intro.",
            "sections": [
                {
                    "name": "Most relevant for your work",
                    "items": [
                        {
                            "candidate_id": "1",
                            "title": "Calibration pattern",
                            "what_happened": "Two concise sentences.",
                            "why_you_should_care": "It matches calibration work.",
                            "fit_tag": "current_work",
                            "source_name": "arXiv",
                            "source_url": "https://example.com/item",
                        }
                    ],
                }
            ],
        }
    )


def test_load_or_refresh_credentials_returns_existing_valid_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_file = tmp_path / "token.json"
    token_file.write_text("{}", encoding="utf-8")
    credentials = FakeCredentials(valid=True)

    monkeypatch.setattr(
        gmail_auth.Credentials,
        "from_authorized_user_file",
        lambda path, scopes: credentials,
    )

    loaded = gmail_auth.load_or_refresh_credentials(
        client_secret_file=tmp_path / "client.json",
        token_file=token_file,
    )

    assert loaded is credentials
    assert credentials.refreshed_with is None


def test_load_or_refresh_credentials_refreshes_expired_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_file = tmp_path / "token.json"
    token_file.write_text("{}", encoding="utf-8")
    credentials = FakeCredentials(valid=False, expired=True, refresh_token="refresh-token")

    monkeypatch.setattr(
        gmail_auth.Credentials,
        "from_authorized_user_file",
        lambda path, scopes: credentials,
    )
    monkeypatch.setattr(gmail_auth, "Request", lambda: "request-object")

    loaded = gmail_auth.load_or_refresh_credentials(
        client_secret_file=tmp_path / "client.json",
        token_file=token_file,
    )

    assert loaded is credentials
    assert credentials.refreshed_with == "request-object"
    assert '"valid": true' in token_file.read_text(encoding="utf-8")


def test_bootstrap_oauth_runs_local_flow_and_writes_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_file = tmp_path / "nested" / "token.json"
    oauth_credentials = FakeCredentials(valid=True)
    fake_flow = FakeFlow(oauth_credentials)

    monkeypatch.setattr(
        gmail_auth.InstalledAppFlow,
        "from_client_secrets_file",
        lambda path, scopes: fake_flow,
    )

    written_path = gmail_auth.bootstrap_oauth(
        client_secret_file=tmp_path / "client.json",
        token_file=token_file,
    )

    assert written_path == token_file
    assert token_file.exists()
    assert fake_flow.port == 0


def test_send_gmail_message_returns_api_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sent: dict[str, Any] = {}

    class FakeSendCall:
        def execute(self) -> dict[str, str]:
            return {"id": "message-1"}

    class FakeMessages:
        def send(self, *, userId: str, body: dict[str, str]) -> FakeSendCall:
            sent["userId"] = userId
            sent["body"] = body
            return FakeSendCall()

    class FakeUsers:
        def messages(self) -> FakeMessages:
            return FakeMessages()

    class FakeService:
        def users(self) -> FakeUsers:
            return FakeUsers()

    monkeypatch.setattr(gmail_send, "load_or_refresh_credentials", lambda **kwargs: "credentials")
    monkeypatch.setattr(gmail_send, "build", lambda name, version, credentials: FakeService())

    result = gmail_send.send_gmail_message(
        client_secret_file=tmp_path / "client.json",
        token_file=tmp_path / "token.json",
        sender="sender@example.com",
        recipient="reader@example.com",
        subject="Subject line",
        html_body="<p>Hello</p>",
        text_body="Hello",
    )

    assert result == {"id": "message-1"}
    raw_bytes = base64.urlsafe_b64decode(sent["body"]["raw"])
    parsed = message_from_bytes(raw_bytes)
    assert sent["userId"] == "me"
    assert parsed["Subject"] == "Subject line"
    assert parsed["To"] == "reader@example.com"
    payloads = parsed.get_payload()
    assert isinstance(payloads, list)
    assert payloads[0].get_payload(decode=True).decode("utf-8") == "Hello"
    assert payloads[1].get_payload(decode=True).decode("utf-8") == "<p>Hello</p>"


def test_send_gmail_message_wraps_http_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FakeHttpError(Exception):
        pass

    class FakeSendCall:
        def execute(self) -> dict[str, str]:
            raise FakeHttpError("boom")

    class FakeMessages:
        def send(self, *, userId: str, body: dict[str, str]) -> FakeSendCall:
            return FakeSendCall()

    class FakeUsers:
        def messages(self) -> FakeMessages:
            return FakeMessages()

    class FakeService:
        def users(self) -> FakeUsers:
            return FakeUsers()

    monkeypatch.setattr(gmail_send, "load_or_refresh_credentials", lambda **kwargs: "credentials")
    monkeypatch.setattr(gmail_send, "build", lambda name, version, credentials: FakeService())
    monkeypatch.setattr(gmail_send, "HttpError", FakeHttpError)

    with pytest.raises(RuntimeError, match="Gmail API send failed"):
        gmail_send.send_gmail_message(
            client_secret_file=tmp_path / "client.json",
            token_file=tmp_path / "token.json",
            sender="sender@example.com",
            recipient="reader@example.com",
            subject="Subject line",
            html_body="<p>Hello</p>",
            text_body="Hello",
        )


def test_openai_client_generate_returns_structured_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    expected_issue = _sample_issue_payload()
    captured: dict[str, Any] = {}

    class FakeResponses:
        def parse(self, **kwargs: Any) -> Any:
            captured.update(kwargs)
            return SimpleNamespace(output_parsed=expected_issue)

    class FakeOpenAI:
        def __init__(self, *, api_key: str) -> None:
            captured["api_key"] = api_key
            self.responses = FakeResponses()

    monkeypatch.setattr("app.llm.client.OpenAI", FakeOpenAI)

    client = OpenAIClient(api_key="test-key", model="gpt-5.4-mini")
    result = client.generate(system_prompt="system", user_prompt="user")

    assert result == expected_issue
    assert captured["api_key"] == "test-key"
    assert captured["model"] == "gpt-5.4-mini"
    assert captured["text_format"] is NewsletterIssuePayload


def test_openai_client_generate_raises_for_missing_parsed_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponses:
        def parse(self, **kwargs: Any) -> Any:
            return SimpleNamespace(output_parsed=None)

    class FakeOpenAI:
        def __init__(self, *, api_key: str) -> None:
            self.responses = FakeResponses()

    monkeypatch.setattr("app.llm.client.OpenAI", FakeOpenAI)

    client = OpenAIClient(api_key="test-key", model="gpt-5.4-mini")
    with pytest.raises(ValueError, match="parsed structured output"):
        client.generate(system_prompt="system", user_prompt="user")


def test_configure_logging_calls_basic_config(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        "logging.basicConfig",
        lambda **kwargs: captured.update(kwargs),
    )

    configure_logging()

    assert captured["format"] == "%(asctime)s %(levelname)s %(name)s %(message)s"


@pytest.mark.parametrize(
    ("argv", "expected_output", "expected_call"),
    [
        (["prog", "init-db"], "Initialized database at", ("initialize", None)),
        (["prog", "fetch"], "Fetched 12 items into", ("fetch_only", None)),
        (["prog", "score"], "Shortlisted 8 items", ("score_only", None)),
        (["prog", "preview"], "Selected 8 items", ("preview_only", None)),
        (["prog", "profile-refresh"], '"profile": "refreshed"', ("refresh_profiles", None)),
        (["prog", "feedback-sync"], "Imported 3 feedback events", ("feedback_sync_only", None)),
        (["prog", "profile-show"], '"profile": "shown"', ("show_profile", None)),
        (
            ["prog", "feedback", "--item-id", "42", "--vote", "+"],
            "Recorded feedback 9",
            ("record_feedback", {"item_id": 42, "vote": "+"}),
        ),
        (
            ["prog", "issue-explain", "--issue-id", "7"],
            '"issue_id": 7',
            ("explain_issue", {"issue_id": 7}),
        ),
        (["prog", "send"], "Sent Briefing | 2026-03-19 to", ("run", {"send_email": True})),
        (["prog", "run"], "Preview: preview/out.html", ("run", {"send_email": False})),
    ],
)
def test_main_dispatches_all_commands(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    argv: list[str],
    expected_output: str,
    expected_call: tuple[str, dict[str, Any] | None],
) -> None:
    import app.main as main_module

    settings = build_test_settings(tmp_path)
    settings = settings.model_copy(
        update={
            "global_config": settings.global_config.model_copy(
                update={"preview_output_path": "preview/out.html"}
            )
        }
    )
    calls: list[tuple[str, dict[str, Any] | None]] = []

    class FakePipeline:
        def __init__(self, loaded_settings: Any) -> None:
            assert loaded_settings == settings

        def __enter__(self) -> FakePipeline:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def initialize(self) -> None:
            calls.append(("initialize", None))

        def fetch_only(self) -> Any:
            calls.append(("fetch_only", None))
            return SimpleNamespace(fetched_count=12)

        def score_only(self) -> Any:
            calls.append(("score_only", None))
            return SimpleNamespace(shortlisted_count=8)

        def preview_only(self) -> Any:
            calls.append(("preview_only", None))
            return SimpleNamespace(
                subject="Briefing | 2026-03-19",
                selected_count=8,
                preview_path=Path("preview/out.html"),
            )

        def refresh_profiles(self) -> dict[str, str]:
            calls.append(("refresh_profiles", None))
            return {"profile": "refreshed"}

        def feedback_sync_only(self) -> int:
            calls.append(("feedback_sync_only", None))
            return 3

        def show_profile(self) -> dict[str, str]:
            calls.append(("show_profile", None))
            return {"profile": "shown"}

        def record_feedback(self, *, item_id: int, vote: str) -> int:
            calls.append(("record_feedback", {"item_id": item_id, "vote": vote}))
            return 9

        def explain_issue(self, *, issue_id: int) -> list[dict[str, int]]:
            calls.append(("explain_issue", {"issue_id": issue_id}))
            return [{"issue_id": issue_id}]

        def run(self, *, send_email: bool) -> Any:
            calls.append(("run", {"send_email": send_email}))
            return SimpleNamespace(
                subject="Briefing | 2026-03-19",
                preview_path=Path("preview/out.html"),
            )

    monkeypatch.setattr(main_module, "NewsletterPipeline", FakePipeline)
    monkeypatch.setattr(main_module, "load_settings", lambda config: settings)
    monkeypatch.setattr(main_module, "configure_logging", lambda: None)
    monkeypatch.setattr(sys, "argv", argv)

    main_module.main()

    assert calls == [expected_call]
    assert expected_output in capsys.readouterr().out
