"""Role B, step B3. The agent loop. See CLAUDE.md for SYSTEM_PROMPT and behaviour.

run_agent(state, emit): up to MAX_STEPS tool calls via llm.call_llm_tools; after each tool call
emit("agent_step", {thought, tool, args, result_summary}). Stops on finish() or a reply with no
tool call. SCRIPTED=1 in .env runs the same tools in a fixed order with prewritten thoughts
from scripted_trace.json (demo fallback).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from llm import call_llm_tools
from tools import TOOL_SCHEMAS, CaseState, Emit, call_tool, finish

MAX_STEPS = 30
SYSTEM_PROMPT = """You are Ghost Assets, an agent that helps a legal heir find and claim every financial asset a
deceased person left. Work step by step:
1) scan and extract all sources (SMS, email, AIS, photos), 2) build the asset map,
3) investigate gaps: assets with weak evidence; old assets that may have moved to unclaimed funds
   (bank accounts silent 10+ years -> check UDGAM; shares whose dividends stopped 7+ years ago ->
   search the evidence for the company, then check IEPF); bank accounts or FDs with no nominee
   information -> ask the family,
4) apply claim rules to every asset, 5) generate a claim pack for every asset, 6) finish.
Use tools; never guess facts. Ask the family only when the evidence cannot answer.
Before each tool call, state your reason in one short sentence."""


def _case_message(state: CaseState) -> str:
    c = state.case
    lines = [f"Deceased: {c.deceased_name}, died {c.date_of_death}. Case date: {state.as_of.isoformat()}."]
    if c.known_assets:
        lines.append("The family already knows about: " + "; ".join(c.known_assets) + ".")
    if c.documents_have:
        lines.append("Documents the heir already has: " + ", ".join(c.documents_have) + ".")
    lines.append("Find and prepare claims for every asset.")
    return "\n".join(lines)


def _summary(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, default=str)


async def _send(emit: Emit, type_: str, data: dict) -> None:
    out = emit(type_, data)
    if asyncio.iscoroutine(out):
        await out


async def _run_tool(state: CaseState, name: str, args: dict) -> dict:
    try:
        return await call_tool(state, name, args)
    except Exception as exc:   # the model sees the failure and can choose another step
        print(f"[agent] tool {name} raised {type(exc).__name__}: {exc}")
        return {"error": f"{name} failed: {type(exc).__name__}: {str(exc)[:300]}"}


async def run_agent(state: CaseState, emit: Emit) -> None:
    if state.emit is None:
        state.emit = emit
    messages: list[dict[str, Any]] = [{"role": "user", "content": _case_message(state)}]
    stop_reason = f"step limit ({MAX_STEPS}) reached"

    for step in range(1, MAX_STEPS + 1):
        try:
            reply = await asyncio.to_thread(call_llm_tools, SYSTEM_PROMPT, messages, TOOL_SCHEMAS)
        except Exception as exc:
            print(f"[agent] step {step}: LLM call failed: {type(exc).__name__}: {exc}")
            await _send(emit, "error", {"message": f"agent LLM call failed: {type(exc).__name__}: {str(exc)[:300]}"})
            return
        messages.append(reply["raw"])
        call = reply["tool_call"]
        thought = (reply["text"] or "").strip()
        if call is None:
            stop_reason = "model returned no tool call"
            print(f"[agent] step {step}: no tool call; text: {thought[:200]!r}")
            break

        name, args = call["name"], call["args"] or {}
        print(f"[agent] step {step}: {name}({_summary(args)})")
        result = await _run_tool(state, name, args)
        summary = _summary(result)
        messages.append({"role": "tool", "tool_call_id": call["id"], "content": summary})
        await _send(emit, "agent_step", {"thought": thought, "tool": name, "args": args, "result_summary": summary})
        if name == "finish" and not result.get("error"):
            print(f"[agent] finished after {step} steps")
            return

    # Stopped without finish(): close the run so the frontend still gets its done event.
    print(f"[agent] stopping: {stop_reason}")
    result = await finish(state, f"Stopped: {stop_reason}.")
    await _send(emit, "agent_step", {"thought": f"Stopping: {stop_reason}.", "tool": "finish",
                                     "args": {"summary": state.summary}, "result_summary": _summary(result)})
