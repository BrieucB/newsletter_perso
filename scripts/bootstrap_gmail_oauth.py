from __future__ import annotations

from app.email.gmail_auth import bootstrap_oauth
from app.settings import load_settings


def main() -> None:
    settings = load_settings()
    token_path = bootstrap_oauth(
        client_secret_file=settings.gmail_client_secret_path,
        token_file=settings.gmail_token_path,
    )
    print(f"Stored Gmail token at {token_path}")


if __name__ == "__main__":
    main()
