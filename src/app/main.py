from __future__ import annotations

import argparse
import json

from app.logging_config import configure_logging
from app.pipeline.run_once import NewsletterPipeline
from app.settings import load_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Personalized technical radar CLI")
    parser.add_argument("--config", default=None, help="Path to YAML config file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("run", "fetch", "score", "preview", "send", "init-db"):
        subparsers.add_parser(command)
    subparsers.add_parser("profile-refresh")
    subparsers.add_parser("profile-show")
    feedback_parser = subparsers.add_parser("feedback")
    feedback_parser.add_argument("--item-id", type=int, required=True)
    feedback_parser.add_argument("--vote", choices=["+", "-"], required=True)
    explain_parser = subparsers.add_parser("issue-explain")
    explain_parser.add_argument("--issue-id", type=int, required=True)
    return parser


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


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
        if args.command == "profile-refresh":
            profile = pipeline.refresh_profiles()
            _print_json(profile)
            return
        if args.command == "profile-show":
            _print_json(pipeline.show_profile())
            return
        if args.command == "feedback":
            feedback_id = pipeline.record_feedback(item_id=args.item_id, vote=args.vote)
            print(f"Recorded feedback {feedback_id} for item {args.item_id}")
            return
        if args.command == "issue-explain":
            _print_json(pipeline.explain_issue(issue_id=args.issue_id))
            return
        if args.command == "send":
            result = pipeline.run(send_email=True)
            print(f"Sent {result.subject} to {settings.recipient_email}")
            return
        result = pipeline.run(send_email=False)
        print(f"{result.subject}\nPreview: {result.preview_path}")


if __name__ == "__main__":
    main()
