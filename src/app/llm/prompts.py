from __future__ import annotations

import json
from datetime import date
from typing import Any

SYSTEM_PROMPT = """You are writing a short personal newsletter in English.

Constraints:
- Return strict JSON only.
- Be concise, analytical, practical, and personal.
- Write like a mentor note to self.
- No hype, no marketing tone, no fabricated details.
- Prefer significant updates over noise.
- Prefer official or primary sources when available.
- Preserve the original source URL for every selected item.
- Do not repeat the source title verbatim in what_happened unless needed for clarity.
- Each what_happened should be 2 to 4 concise sentences.
- Each why_you_should_care should explain why the item matters to this user specifically.
- Each why_you_should_care should connect to current UQ/HPC work, LLM background,
  tools/systems thinking, interview readiness, or something worth trying experimentally.
- Each item must include fit_tag with one of: current_work, llm_background, both.
- Select exactly 8 items total.
- Keep the issue balanced across current work and LLM understanding goals.
- Use semi-dynamic sections from a controlled set or close variants, such as:
  - Most relevant for your work
  - Broaden your UQ/HPC map
  - LLM engineering you should understand
  - Architecture ideas worth understanding
  - Tools and systems worth watching
  - Could be useful later
  - For interviews / background
  - Worth trying in your workflow
- Output should fit a 5-minute read.
"""


def build_generation_prompt(
    *,
    run_date: date,
    candidates: list[dict[str, Any]],
    explicit_profile: dict[str, Any],
    aggregated_repo_profile: dict[str, Any],
    learned_preferences: dict[str, Any],
) -> str:
    payload = {
        "run_date": run_date.isoformat(),
        "explicit_profile": explicit_profile,
        "aggregated_repo_profile": aggregated_repo_profile,
        "learned_preferences": learned_preferences,
        "instructions": {
            "required_total_items": 8,
            "target_ratio": explicit_profile.get("target_ratio", {}),
            "selection_rules": [
                "Keep only strong, relevant items.",
                "Preserve each candidate_id for chosen items.",
                "Keep the original source_name and source_url.",
                "Subject must contain the date.",
                "Intro should be 1 to 2 short sentences.",
                "selection_notes should briefly explain the issue balance and "
                "personalization logic.",
                "Respect the user's preferred ordering of content types: "
                "engineering_blog, tool_or_repo, paper, release_note.",
                "Aggressively avoid hype, LinkedIn-style marketing, tiny weak OSS, "
                "and purely theoretical items with no applied angle.",
            ],
        },
        "candidates": candidates,
    }
    return json.dumps(payload, indent=2, sort_keys=True)
