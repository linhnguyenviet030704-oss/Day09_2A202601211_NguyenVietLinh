"""Thin LLM helper: one JSON-returning chat call plus a trace record.

Every agent calls `chat_json` so all LLM traffic is uniform and traceable. The
returned trace dict is what the Coordinator/runner (Member A) appends to
logging/trace.jsonl.
"""

import json
import time
from typing import Tuple

from .config import OPENAI_MODEL, get_client


def chat_json(
    system: str,
    user: str,
    *,
    agent: str = "",
    case_id: str = "",
    temperature: float = 0.0,
    max_tokens: int = 600,
) -> Tuple[dict, dict]:
    """Send one chat request expecting a JSON object back.

    Returns (parsed_json, trace_record). On any failure the parsed dict is empty
    and the trace records the error, so callers can fall back to deterministic
    values instead of crashing the whole run.
    """
    client = get_client()
    t0 = time.time()
    trace = {
        "agent": agent,
        "case_id": case_id,
        "model": OPENAI_MODEL,
        "prompt": {"system": system, "user": user},
    }
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = resp.choices[0].message.content or "{}"
        trace["raw_response"] = content
        trace["latency_ms"] = round((time.time() - t0) * 1000)
        if resp.usage is not None:
            trace["usage"] = resp.usage.model_dump()
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            data = {}
            trace["parse_error"] = True
        return data, trace
    except Exception as exc:  # network / auth / rate-limit — degrade gracefully
        trace["error"] = f"{type(exc).__name__}: {exc}"
        trace["latency_ms"] = round((time.time() - t0) * 1000)
        return {}, trace
