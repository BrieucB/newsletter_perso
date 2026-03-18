from __future__ import annotations

import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, cast

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.email.gmail_auth import load_or_refresh_credentials


def send_gmail_message(
    *,
    client_secret_file: Path,
    token_file: Path,
    sender: str,
    recipient: str,
    subject: str,
    html_body: str,
    text_body: str,
) -> dict[str, Any]:
    credentials = load_or_refresh_credentials(
        client_secret_file=client_secret_file,
        token_file=token_file,
    )
    service = build("gmail", "v1", credentials=credentials)

    message = MIMEMultipart("alternative")
    message["To"] = recipient
    message["From"] = sender
    message["Subject"] = subject
    message.attach(MIMEText(text_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    try:
        result = service.users().messages().send(userId="me", body={"raw": raw_message}).execute()
    except HttpError as exc:
        raise RuntimeError(f"Gmail API send failed: {exc}") from exc
    return cast(dict[str, Any], result)
