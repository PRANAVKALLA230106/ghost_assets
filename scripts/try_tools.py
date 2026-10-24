"""Call every agent tool once on Ramesh's case and print each result with its size in bytes.

Run from the repo root:  python scripts/try_tools.py [--cache-only]
ask_family is answered automatically ("No") the way the frontend would answer it.
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

from models import Case  # noqa: E402
from tools import MAX_RESULT_BYTES, CaseState, call_tool  # noqa: E402

AS_OF = date(2026, 10, 24)


def show(name: str, args: dict, result: dict) -> int:
    size = len(json.dumps(result, ensure_ascii=False, default=str).encode("utf-8"))
    flag = "OK " if size <= MAX_RESULT_BYTES else "BIG"
    print(f"\n=== [{flag}] {name}({json.dumps(args, ensure_ascii=False)})  {size} bytes")
    print(json.dumps(result, ensure_ascii=False, default=str)[:600])
    return size


async def main() -> None:
    events: list[str] = []
    state = CaseState(case=Case(id="ramesh", deceased_name="Ramesh Kumar", date_of_death="2026-02-10",
                                data_dir="data/ramesh"),
                      as_of=AS_OF)

    def emit(type_: str, data: dict) -> None:
        events.append(type_)
        if type_ == "question":   # stand-in for the family answering in the UI
            asyncio.get_running_loop().call_later(0.1, state.answer, data["id"], "No")

    state.emit = emit
    sizes: dict[str, int] = {}

    async def run(tool: str, **args) -> dict:
        result = await call_tool(state, tool, args)
        sizes[tool] = max(sizes.get(tool, 0), show(tool, args, result))
        return result

    await run("scan_sources")
    await run("extract_clues", source="all")
    await run("build_asset_map")
    await run("search_evidence", query="Ganga Tech")
    await run("read_photo", file="passbook.png")
    await run("check_portal", portal="UDGAM", name=state.case.deceased_name, institution="State Bank of India")
    await run("check_portal", portal="IEPF", name=state.case.deceased_name, institution="Ganga Tech")
    no_nominee_info = next((a for a in state.assets if a.asset_type in ("savings_account", "fixed_deposit")
                            and a.nominee == "unknown"), None)
    await run("ask_family", question=f"Did {state.case.deceased_name} register a nominee for the "
              f"{no_nominee_info.institution if no_nominee_info else 'bank'} deposit?",
              options=["Yes", "No", "Not sure"], asset_id=no_nominee_info.id if no_nominee_info else None)
    await run("apply_claim_rules", asset_id="all")
    await run("generate_claim_pack", asset_id=state.assets[0].id)
    await run("finish", summary="Tool smoke test complete.")

    print("\n--- sizes (bytes) ---")
    for name, size in sizes.items():
        print(f"  {name:<20}{size:>6}{'  OVER LIMIT' if size > MAX_RESULT_BYTES else ''}")
    print(f"events emitted: {dict((t, events.count(t)) for t in dict.fromkeys(events))}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--cache-only", action="store_true", help="serve LLM calls from backend/cache only")
    if p.parse_args().cache_only:
        os.environ["LLM_CACHE_ONLY"] = "1"
    asyncio.run(main())
