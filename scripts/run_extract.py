"""Run ingest + triage + extract and write out/clues.json.

Run from the repo root:  python scripts/run_extract.py [--limit N] [--case data/ramesh]
--limit N extracts only the first N financial items (in evidence order); omit it for all.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import llm  # noqa: E402
from extract import extract_clues  # noqa: E402
from ingest import load_case  # noqa: E402
from triage import triage  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--case", default="data/ramesh")
    a = p.parse_args()

    financial = [e for e in triage(load_case(ROOT / a.case)) if e.is_financial]
    if a.limit is not None:
        financial = financial[:a.limit]
    print(f"[run_extract] extracting {len(financial)} financial items")

    clues = asyncio.run(extract_clues(financial))

    out = ROOT / "out" / "clues.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps([c.model_dump() for c in clues], indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"\n[run_extract] {len(clues)} clues from {len({c.evidence_id for c in clues})} of {len(financial)} items")
    for (inst, kind), n in Counter((c.institution_raw, c.asset_type) for c in clues).most_common():
        print(f"  {n:>4}  {kind:<16} {inst}")
    print(f"[run_extract] cache {llm.cache_stats()}  wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
