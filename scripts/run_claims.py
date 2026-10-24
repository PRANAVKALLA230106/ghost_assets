"""Deterministic run of the tool chain (no agent LLM): scan, extract, build map, portal checks for assets
the rules flag as transferred, nominee questions, claim rules, a claim pack per asset.
Writes out/assets.json, out/claims.json and out/claimpacks/*.docx.

Run from the repo root:  python scripts/run_claims.py [--cache-only] [--answer No]
Without --answer, nominee questions are asked in the terminal.
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
from tools import CaseState, call_tool  # noqa: E402

AS_OF = date(2026, 10, 24)
OUT = ROOT / "out"
PORTAL_FOR_STATUS = {"transferred_dea": "UDGAM", "transferred_iepf": "IEPF"}


async def main(answer: str | None) -> None:
    state = CaseState(case=Case(id="ramesh", deceased_name="Ramesh Kumar", date_of_death="2026-02-10",
                                data_dir="data/ramesh"), as_of=AS_OF)

    async def reply(data: dict) -> None:
        text = answer or (await asyncio.to_thread(input, f"\n>>> {data['text']} {data['options']}: ")).strip()
        state.answer(data["id"], text)

    def emit(type_: str, data: dict) -> None:
        if type_ == "question":
            asyncio.get_running_loop().create_task(reply(data))

    state.emit = emit

    async def run(tool: str, **args) -> dict:
        result = await call_tool(state, tool, args)
        print(f"[run_claims] {tool}({json.dumps(args, ensure_ascii=False)}) -> "
              f"{json.dumps(result, ensure_ascii=False, default=str)[:300]}")
        return result

    await run("scan_sources")
    await run("extract_clues", source="all")
    await run("build_asset_map")
    for a in list(state.assets):
        portal = PORTAL_FOR_STATUS.get(a.status)
        if portal:
            await run("check_portal", portal=portal, name=state.case.deceased_name, institution=a.institution)
    for a in list(state.assets):
        if a.asset_type in ("savings_account", "fixed_deposit") and a.nominee == "unknown":
            await run("ask_family", question=f"Did {state.case.deceased_name} register a nominee for the "
                      f"{a.institution} {a.asset_type.replace('_', ' ')} {a.identifier or ''}?".replace(" ?", "?"),
                      options=["Yes", "No", "Not sure"], asset_id=a.id)
    await run("apply_claim_rules", asset_id="all")
    for a in state.assets:
        await run("generate_claim_pack", asset_id=a.id)

    OUT.mkdir(exist_ok=True)
    (OUT / "assets.json").write_text(json.dumps([a.model_dump() for a in state.assets], indent=1, ensure_ascii=False),
                                     encoding="utf-8")
    (OUT / "claims.json").write_text(json.dumps([c.model_dump() for c in state.claims.values()], indent=1,
                                                ensure_ascii=False), encoding="utf-8")
    print(f"\n[run_claims] wrote {len(state.assets)} assets, {len(state.claims)} claims, "
          f"{len(state.claim_packs)} claim packs")
    for a in state.assets:
        print(f"  {a.id}  {a.institution:<24}{a.identifier or '-':<13}{state.claims[a.id].path:<24}"
              f"{Path(state.claim_packs[a.id]).name}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--cache-only", action="store_true", help="serve LLM calls from backend/cache only")
    p.add_argument("--answer", default=None, help="answer every family question with this text")
    a = p.parse_args()
    if a.cache_only:
        os.environ["LLM_CACHE_ONLY"] = "1"
    asyncio.run(main(a.answer))
