"""Role B, step B3. The agent loop. See CLAUDE.md for SYSTEM_PROMPT and behaviour.

run_agent(state, emit): up to MAX_STEPS tool calls via llm.call_llm_tools; after each tool call
emit("agent_step", {thought, tool, args, result_summary}). Stops on finish() or a reply with no
tool call. SCRIPTED=1 in .env runs the same tools in a fixed order with prewritten thoughts
from scripted_trace.json (demo fallback).
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from llm import call_llm_tools
from tools import TOOL_SCHEMAS, CaseState, Emit, call_tool, finish

MAX_STEPS = 30
MAX_NUDGES = 4      # replies with no tool call that get a reminder instead of ending the run
NUDGE = ("The heir's sources are already uploaded and are reachable only through your tools. "
         "Continue by calling the next tool; call finish(summary) when every step is done.")
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


def _thought(reply: dict, name: str, args: dict) -> str:
    """The model's stated reason: its message text, else the first sentence of its reasoning field,
    else (the model gave neither) a plain description of the call it made."""
    text = (reply.get("text") or "").strip()
    if text:
        return text
    reasoning = " ".join((reply.get("reasoning") or "").split())
    first = re.split(r"(?<=[.!?])\s", reasoning, maxsplit=1)[0]
    if first:
        return first[:240]
    target = ", ".join(f"{k}={v}" for k, v in args.items() if isinstance(v, (str, int, float)))
    return f"Next step: {name.replace('_', ' ')}" + (f" ({target[:160]})." if target else ".")


def _unfinished(state: CaseState) -> list[str]:
    """Assets that still have no claim pack; finish() is refused until this is empty."""
    return [a.id for a in state.assets if a.id not in state.claim_packs]


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
    nudges = 0

    for step in range(1, MAX_STEPS + 1):
        try:
            reply = await asyncio.to_thread(call_llm_tools, SYSTEM_PROMPT, messages, TOOL_SCHEMAS)
        except Exception as exc:
            print(f"[agent] step {step}: LLM call failed: {type(exc).__name__}: {exc}")
            await _send(emit, "error", {"message": f"agent LLM call failed: {type(exc).__name__}: {str(exc)[:300]}"})
            return
        messages.append(reply["raw"])
        call = reply["tool_call"]
        thought = _thought(reply, call["name"], call["args"] or {}) if call else (reply["text"] or "").strip()
        if call is None:
            print(f"[agent] step {step}: no tool call; text: {thought[:200]!r}")
            if state.assets and not _unfinished(state):
                # Work is complete; gpt-oss sometimes writes its summary as prose instead of calling finish.
                summary = thought or "Every asset has a claim pack."
                result = await finish(state, summary)
                await _send(emit, "agent_step", {"thought": "Every asset has a claim pack; closing the case.",
                                                 "tool": "finish", "args": {"summary": summary[:500]},
                                                 "result_summary": _summary(result)})
                print(f"[agent] closed after step {step}: the model wrote its summary instead of calling finish")
                return
            if nudges < MAX_NUDGES:
                nudges += 1
                messages.append({"role": "user", "content": NUDGE})
                continue
            stop_reason = "model returned no tool call"
            break

        name, args = call["name"], call["args"] or {}
        print(f"[agent] step {step}: {name}({_summary(args)})")
        missing = _unfinished(state) if name == "finish" else []
        if missing:
            print(f"[agent] step {step}: finish refused; no claim pack for {missing}")
            result = {"error": "finish refused: generate_claim_pack has not been run for " + ", ".join(missing)}
        else:
            result = await _run_tool(state, name, args)
            if name == "generate_claim_pack" and not result.get("error"):
                result["assets_without_claim_pack"] = _unfinished(state)
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
