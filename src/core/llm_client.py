"""
Shared LLM client wrapper (Member A: Data + Coordinator + Runner).

Model declared here per README section 9.1 (must be in code, not .env):
google/gemma-3-4b-it (4B params, publicly disclosed, satisfies the
<=10B rule) via OpenRouter's OpenAI-compatible API, using
OPENROUTER_API_KEY from .env.

Note: Gemma 2 9B / Gemma 3 9B ("Gemma 9B") is no longer served by
either Google AI Studio or OpenRouter as of this run (confirmed via
their model-list APIs; both return 404 for gemma-2-9b-it /
gemma-3-9b-it). gemma-3-4b-it is the closest available Gemma model
with a disclosed, verifiable parameter count under the 10B cap.
"""
from __future__ import annotations

import json
import os

from openai import OpenAI

MODEL_NAME = "google/gemma-3-4b-it"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set in the environment (.env)")
        _client = OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)
    return _client


def call_llm_json(system: str, user: str, model: str = MODEL_NAME) -> dict:
    """Call the LLM and parse a JSON object response."""
    client = get_client()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    content = resp.choices[0].message.content
    return json.loads(content)


def call_llm_text(system: str, user: str, model: str = MODEL_NAME) -> str:
    client = get_client()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0,
    )
    return resp.choices[0].message.content
