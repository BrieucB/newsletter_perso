from __future__ import annotations

from openai import OpenAI

from app.llm.schemas import NewsletterIssuePayload


class OpenAIClient:
    def __init__(self, *, api_key: str, model: str) -> None:
        self.model = model
        self._client = OpenAI(api_key=api_key)

    def generate(self, *, system_prompt: str, user_prompt: str) -> NewsletterIssuePayload:
        response = self._client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            text_format=NewsletterIssuePayload,
        )
        if response.output_parsed is None:
            raise ValueError("OpenAI response did not contain parsed structured output.")
        return response.output_parsed
