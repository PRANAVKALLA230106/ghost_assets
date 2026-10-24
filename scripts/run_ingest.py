"""Load a case folder, triage it and write out/evidence.json.

Run from the repo root:  python scripts/run_ingest.py [data/ramesh]
"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ingest import load_case  # noqa: E402
from triage import triage  # noqa: E402


def main() -> None:
    case_dir = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "data/ramesh")
    evidence = triage(load_case(case_dir))

    print("\n[run_ingest] counts per source (total / financial):")
    for source, n in Counter(e.source for e in evidence).items():
        fin = sum(1 for e in evidence if e.source == source and e.is_financial)
        print(f"  {source:<6}{n:>6}{fin:>6}")
    print(f"  {'total':<6}{len(evidence):>6}{sum(e.is_financial for e in evidence):>6}")

    by_id = {e.id: e for e in evidence}
    for eid in ("sms_0001", "email_001"):
        print(f"\n[run_ingest] {eid}:\n{by_id[eid].model_dump_json(indent=2)}")

    out = ROOT / "out" / "evidence.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps([e.model_dump() for e in evidence], indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n[run_ingest] wrote {len(evidence)} items to {out.relative_to(ROOT)}")

    dropped = [e for e in evidence if not e.is_financial]
    print(f"\n[run_ingest] 15 random items marked NOT financial (of {len(dropped)}):")
    for e in random.Random(0).sample(dropped, min(15, len(dropped))):
        print(f"  {e.id:<10} {e.sender:<32} {e.text[:100]!r}")


if __name__ == "__main__":
    main()
