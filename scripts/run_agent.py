"""Run the agent on Ramesh's case in the terminal: prints each agent step, asks ask_family questions here.

Run from the repo root:  python scripts/run_agent.py [--cache-only]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from agent import run_agent  # noqa: E402
from models import Case  # noqa: E402
from tools import CaseState  # noqa: E402

AS_OF = date(2026, 10, 24)


async def ask_in_terminal(state: CaseState, data: dict) -> None:
    options = data.get("options") or []
    print(f"\n>>> QUESTION {data['id']}: {data['text']}")
    for n, opt in enumerate(options, start=1):
        print(f"    {n}) {opt}")
    raw = (await asyncio.to_thread(input, "    answer (number or text): ")).strip()
    answer = options[int(raw) - 1] if raw.isdigit() and 1 <= int(raw) <= len(options) else raw
    state.answer(data["id"], answer)


async def main() -> None:
    state = CaseState(case=Case(id="ramesh", deceased_name="Ramesh Kumar", date_of_death="2026-02-10",
                                data_dir="data/ramesh", documents_have=["death_certificate", "claimant_id"],
                                known_assets=["SBI savings account ending 8812", "LIC life insurance policy"]),
                      as_of=AS_OF)
    counts: Counter[str] = Counter()
    step = 0

    def emit(type_: str, data: dict) -> None:
        nonlocal step
        counts[type_] += 1
        if type_ == "agent_step":
            step += 1
            print(f"\n--- step {step}: {data['tool']}({json.dumps(data['args'], ensure_ascii=False)})")
            if data["thought"]:
                print(f"    thought: {data['thought']}")
            print(f"    result:  {data['result_summary'][:400]}")
        elif type_ == "question":
            asyncio.get_running_loop().create_task(ask_in_terminal(state, data))
        elif type_ in ("done", "error"):
            print(f"\n=== {type_.upper()}: {json.dumps(data, ensure_ascii=False)}")

    await run_agent(state, emit)

    print(f"\nevents: {dict(counts)}")
    for a in state.assets:
        claim = state.claims.get(a.id)
        val = f"{a.est_value:,.0f}" if a.est_value else "-"
        print(f"  {a.id}  {a.institution:<24}{a.asset_type:<16}{a.identifier or '-':<13}{val:>10}  "
              f"status={a.status:<16} nominee={a.nominee:<8} path={claim.path if claim else '-'}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--cache-only", action="store_true", help="serve LLM calls from backend/cache only")
    if p.parse_args().cache_only:
        os.environ["LLM_CACHE_ONLY"] = "1"
    asyncio.run(main())
