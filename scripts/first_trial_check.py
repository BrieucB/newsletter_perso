from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FOR_PREVIEW = [
    "OPENAI_API_KEY",
    "NEWSLETTER_RECIPIENT",
    "NEWSLETTER_SENDER",
]

OPTIONAL = ["GITHUB_TOKEN"]

REQUIRED_FOR_SEND = ["GMAIL_CLIENT_SECRET_FILE", "GMAIL_TOKEN_FILE"]

REQUIRED_PACKAGES = [
    "feedparser",
    "requests",
    "jinja2",
    "pydantic",
    "openai",
    "googleapiclient",
    "google_auth_oauthlib",
]


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def is_missing(value: str | None) -> bool:
    return value is None or value == "" or value == "fill_me"


def package_installed(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def main() -> None:
    env_path = ROOT / ".env"
    config_path = ROOT / "config" / "sources.yaml"
    env = load_env(env_path)

    preview_missing = [key for key in REQUIRED_FOR_PREVIEW if is_missing(env.get(key))]
    optional_missing = [key for key in OPTIONAL if is_missing(env.get(key))]
    send_missing = []

    client_secret_name = env.get("GMAIL_CLIENT_SECRET_FILE", "oauth_client_secret.json")
    token_name = env.get("GMAIL_TOKEN_FILE", "token.json")
    client_secret_path = ROOT / client_secret_name
    token_path = ROOT / token_name

    if is_missing(env.get("GMAIL_CLIENT_SECRET_FILE")) or not client_secret_path.exists():
        send_missing.append("GMAIL_CLIENT_SECRET_FILE / local client secret JSON file")
    if is_missing(env.get("GMAIL_TOKEN_FILE")) or not token_path.exists():
        send_missing.append("GMAIL_TOKEN_FILE / local Gmail OAuth token")

    missing_packages = [name for name in REQUIRED_PACKAGES if not package_installed(name)]

    print("First trial preflight")
    print("====================")
    print(f".env: {'present' if env_path.exists() else 'missing'}")
    print(f"config/sources.yaml: {'present' if config_path.exists() else 'missing'}")
    print()

    if missing_packages:
        print("Missing Python packages:")
        for package in missing_packages:
            print(f"- {package}")
        print()
        print('Install with: pip install -e ".[dev]"')
        print()

    if preview_missing:
        print("Preview trial is not ready. Fill these in .env:")
        for key in preview_missing:
            print(f"- {key}")
    else:
        print("Preview trial is ready.")
        print("Run:")
        print("  python -m app.main init-db")
        print("  python -m app.main fetch")
        print("  python -m app.main score")
        print("  python -m app.main preview")

    print()
    if optional_missing:
        print("Optional but recommended:")
        for key in optional_missing:
            print(f"- {key}")
        print()

    if send_missing:
        print("Send trial is not ready. Missing:")
        for item in send_missing:
            print(f"- {item}")
        print()
        print("After adding the Gmail client secret, run:")
        print("  python scripts/bootstrap_gmail_oauth.py")
        print("Then send with:")
        print("  python -m app.main send")
    else:
        print("Send trial is ready.")
        print("Run:")
        print("  python -m app.main send")


if __name__ == "__main__":
    main()
