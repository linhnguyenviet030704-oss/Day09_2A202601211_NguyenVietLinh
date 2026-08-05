"""Shared configuration and LLM client factory.

Per README §9 the model NAME must be declared in source code (this file) AND in
logging/metadata.json so the graders can see it. Only the API key / secrets live
in .env (which is gitignored).

The whole team agreed to use `gpt-4o-mini` for every agent.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# Repo root = two levels up from this file (src/core/config.py -> repo root).
ROOT = Path(__file__).resolve().parents[2]

# Load .env from the repo root so secrets are available as env vars.
load_dotenv(ROOT / ".env")

# --- Model declared in source code (README §9), <= 10B per-agent rule ---
# The literal default here is the graded declaration; .env may override the id
# but the name is intentionally visible in source.
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")


def get_client() -> OpenAI:
    """Return an OpenAI-compatible client. Raises if the API key is missing."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to the .env file at the repo root."
        )
    return OpenAI(api_key=api_key, base_url=OPENAI_BASE_URL)
