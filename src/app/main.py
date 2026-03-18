from __future__ import annotations

import argparse

from app.logging_config import configure_logging
from app.pipeline.run_once import NewsletterPipeline
from app.settings import load_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Newsletter V0 CLI")
    parser.add_argument("--config", default=None, help="Path to YAML config file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("run", "fetch", "score", "preview", "send", "init-db"):
        subparsers.add_parser(command)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    configure_logging()
    settings = load_settings(args.config)

    with NewsletterPipeline(settings) as pipeline:
        if args.command == "init-db":
            pipeline.initialize()
            print(f"Initialized database at {settings.db_path}")
            return
        if args.command == "fetch":
            result = pipeline.fetch_only()
            print(f"Fetched {result.fetched_count} items into {settings.db_path}")
            return
        if args.command == "score":
            result = pipeline.score_only()
            print(f"Shortlisted {result.shortlisted_count} items")
            return
        if args.command == "preview":
            result = pipeline.preview_only()
            print(
                f"{result.subject}\n"
                f"Selected {result.selected_count} items\n"
                f"Preview: {result.preview_path}"
            )
            return
        if args.command == "send":
            result = pipeline.run(send_email=True)
            print(f"Sent {result.subject} to {settings.recipient_email}")
            return
        result = pipeline.run(send_email=False)
        print(f"{result.subject}\nPreview: {result.preview_path}")


if __name__ == "__main__":
    main()
