"""Smoke test for backend/llm.py: the same JSON call twice; the second must be a cache hit.

Run from the repo root:  python scripts/llm_smoke.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import llm  # noqa: E402


def main() -> None:
    for i in (1, 2):
        result = llm.call_llm_json("Reply with JSON.", 'Return {"ok": true}')
        print(f"[smoke] call {i}: {result}  stats={llm.cache_stats()}")


if __name__ == "__main__":
    main()
