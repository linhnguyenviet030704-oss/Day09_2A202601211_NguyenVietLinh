"""
Batch runner (Member A): input/EC_*.json -> output/EC_*.json + logging/trace.jsonl.

Usage:
    python run.py
"""
from __future__ import annotations

import json
import os

from dotenv import load_dotenv

from src.agents.coordinator import process_case

ROOT = os.path.dirname(__file__)
INPUT_DIR = os.path.join(ROOT, "input")
OUTPUT_DIR = os.path.join(ROOT, "output")
LOGGING_DIR = os.path.join(ROOT, "logging")
TRACE_PATH = os.path.join(LOGGING_DIR, "trace.jsonl")


def main() -> None:
    load_dotenv()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(LOGGING_DIR, exist_ok=True)

    n_ok, n_fail = 0, 0
    trace_lines = []

    for i in range(1, 51):
        case_id = f"EC_{i:03d}"
        with open(os.path.join(INPUT_DIR, f"{case_id}.json"), encoding="utf-8") as f:
            case = json.load(f)

        result = process_case(case)
        trace_lines.append(json.dumps(result["trace"], ensure_ascii=False))

        if not result["ok"]:
            n_fail += 1
            print(f"[FAIL] {case_id}: {result['errors']}")
            continue

        n_ok += 1
        out_path = os.path.join(OUTPUT_DIR, f"{case_id}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result["output"], f, ensure_ascii=False, indent=2)

    with open(TRACE_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(trace_lines) + "\n")

    print(f"\nWrote {n_ok} files to {OUTPUT_DIR}, {n_fail} cases failed verification.")
    print(f"Trace written to {TRACE_PATH} ({len(trace_lines)} lines).")


if __name__ == "__main__":
    main()
