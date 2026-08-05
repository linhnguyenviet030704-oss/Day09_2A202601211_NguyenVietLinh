"""
Shared LLM client wrapper (Member A: Data + Coordinator + Runner).

Model declared here per README section 9.1 (must be in code, not .env):
gpt-4o-mini via the OpenAI API, using OPENAI_API_KEY from .env.
"""
from __future__ import annotations

import json
import os

from openai import OpenAI

MODEL_NAME = "gpt-4o-mini"

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set in the environment (.env)")
        _client = OpenAI(api_key=api_key)
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
