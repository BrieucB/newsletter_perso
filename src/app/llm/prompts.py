from __future__ import annotations

import json
from datetime import date
from typing import Any

SYSTEM_PROMPT = """You are writing a short personal newsletter in English.

Constraints:
- Return strict JSON only.
- Be concise, analytical, and practical.
- No hype, no marketing tone, no fabricated details.
- Prefer significant updates over noise.
- Prefer official or primary sources when available.
- Preserve the original source URL for every selected item.
- Do not repeat the source title verbatim in the summary unless needed for clarity.
- Each summary should be 2 to 4 sentences.
- why_it_matters should explain practical relevance in 1 to 2 sentences.
- Output should fit a 5-minute read.
- Use these section limits:
  - UQ / HPC: 3 to 5 items if enough quality candidates exist.
  - LLM: 3 to 5 items if enough quality candidates exist.
  - Worth watching: at most 1 item.
"""


def build_generation_prompt(*, run_date: date, candidates: list[dict[str, Any]]) -> str:
    payload = {
        "run_date": run_date.isoformat(),
        "instructions": {
            "required_sections": ["UQ / HPC", "LLM"],
            "optional_sections": ["Worth watching"],
            "selection_rules": [
                "Keep only strong, relevant items.",
                "Preserve each candidate_id for chosen items.",
                "Keep the original source_name and source_url.",
                "Subject must contain the date.",
                "Intro should be 1 to 2 short sentences.",
            ],
        },
        "candidates": candidates,
    }
    return json.dumps(payload, indent=2, sort_keys=True)
