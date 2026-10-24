"""ingest -> triage -> extract -> resolve on a case folder; writes out/evidence.json, clues.json, assets.json.

Run from the repo root:  python scripts/run_pipeline.py [--case data/ramesh] [--as-of 2026-10-24]
                         python scripts/run_pipeline.py --from-clues out/clues.json   (resolve only, no LLM)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import llm  # noqa: E402
from extract import extract_clues  # noqa: E402
from ingest import load_case  # noqa: E402
from models import Clue  # noqa: E402
from resolve import build_assets  # noqa: E402
from triage import triage  # noqa: E402

OUT = ROOT / "out"


def dump(name: str, items: list) -> None:
    (OUT / name).write_text(json.dumps([i.model_dump() for i in items], indent=1, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--case", default="data/ramesh")
    p.add_argument("--as-of", default=None, help="ISO date for recency; default today")
    p.add_argument("--from-clues", default=None, help="saved clues.json: skip extraction (no LLM calls)")
    p.add_argument("--cache-only", action="store_true",
                   help="re-run extraction from backend/cache only (re-grounds saved replies; no network calls)")
    a = p.parse_args()
    if a.cache_only:
        os.environ["LLM_CACHE_ONLY"] = "1"
    as_of = date.fromisoformat(a.as_of) if a.as_of else date.today()
    OUT.mkdir(exist_ok=True)

    evidence = triage(load_case(ROOT / a.case))
    if a.from_clues:
        raw = json.loads(Path(a.from_clues).read_text(encoding="utf-8"))
        clues = [Clue(**c) for c in raw]
        print(f"[run_pipeline] loaded {len(clues)} clues from {a.from_clues}; extraction skipped")
    else:
        clues = asyncio.run(extract_clues(evidence))  # transcribes photos into evidence.text
        dump("evidence.json", evidence)
        dump("clues.json", clues)
    assets = build_assets(clues, evidence, as_of)
    dump("assets.json", assets)

    print(f"\n[run_pipeline] {len(clues)} clues -> {len(assets)} assets   cache {llm.cache_stats()}")
    for x in assets:
        val = f"{x.est_value:,.0f}" if x.est_value else "-"
        print(f"  {x.id}  {x.institution:<24}{x.asset_type:<16}{x.identifier or '-':<13}{val:>10}  "
              f"{x.value_basis or '-':<26}last={x.last_activity}  nominee={x.nominee}  conf={x.confidence}  clues={len(x.clue_ids)}")


if __name__ == "__main__":
    main()
