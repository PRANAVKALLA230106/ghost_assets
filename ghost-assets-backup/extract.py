"""Role A, step A3. Financial Evidence -> grounded Clues, using the LLM.

- 10 evidence items per LLM call, 2 calls concurrently (free-tier limits; see BATCH_SIZE).
- Photos are sent as images (one per call): the vision model transcribes the photo into
  ev.text, then the transcript is extracted and grounded like any other text.
- Every clue passes ground() or is dropped and logged with a reason.
The extraction prompt lives in CLAUDE.md; keep it in EXTRACTION_PROMPT below.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any, Callable

import openai
from pydantic import ValidationError

from llm import CacheMiss, OutputTruncated, _limit_kind, call_llm_json
from models import Clue, Evidence

EXTRACTION_PROMPT = """You extract financial asset clues from messages a person received.
For each message, return zero or more clues. A clue is evidence that the person held an account,
deposit, policy, fund, shareholding or provident fund.
Rules:
- evidence_id: copy the id of the message the clue came from.
- institution_raw: the bank/insurer/fund/company exactly as written (sender IDs like VM-CANBNK count).
- asset_type: one of savings_account, fixed_deposit, life_insurance, mutual_fund, shares, provident_fund, post_office, other.
- identifier: the account/FD/policy/folio number exactly as written, masked digits included (e.g. XX4521).
- amount: a number in rupees; amount_kind: balance, principal, maturity_value, sum_assured, premium,
  sip_instalment, dividend, interest, credit, debit, market_value or unknown.
- date: ISO date if the message states one. nominee: the nominee's name or "not registered" if stated.
- quote: the exact substring of the message that supports the clue. Copy, never paraphrase.
- A UPI payment to a shop or person is evidence of the account it was paid FROM, not a new asset.
- A premium or SIP debited from a bank account is evidence of BOTH the bank account and the policy/fund.
- Never invent values. Use null when a field is not in the text. Ignore OTPs, ads and offers.
Return JSON: {"clues": [{"evidence_id", "institution_raw", "asset_type", "identifier", "amount",
"amount_kind", "date", "nominee", "quote"}]}"""

TRANSCRIBE_PROMPT = """You transcribe photos of financial documents (passbooks, policy bonds, statements).
Copy every piece of visible text exactly as printed, line by line, keeping numbers, masks (X) and
punctuation unchanged. Do not summarise or correct anything.
Return JSON: {"text": "<the transcript>"}"""

BATCH_SIZE = 10                 # CLAUDE.md says 20; 10 keeps replies under MAX_TOKENS on Groq's free tier
CONCURRENCY = 2                 # CLAUDE.md says 4; 2 suits the 8,000 tokens/minute free-tier limit
MAX_TOKENS = 4096               # per extraction reply; finish_reason "length" means the batch was too big
NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
CURRENCY_BEFORE = re.compile(r"(?:rs\.?|inr|₹)\s*$", re.I)
NOMINEE_RE = re.compile(r"nomin", re.I)
CLUE_FIELDS = ("evidence_id", "institution_raw", "asset_type", "identifier", "amount",
               "amount_kind", "date", "nominee", "quote")


def normalise_amount(text: str) -> float | None:
    """'Rs.2,00,000' / 'INR 200000.00' / '2,00,000/-' / 'Rs 5000' -> 200000.0 / 5000.0"""
    m = NUMBER_RE.search(text or "")
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "").rstrip("."))
    except ValueError:
        return None


def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _money_numbers(text: str) -> tuple[set[float], set[float]]:
    """(numbers written as rupee amounts, every number). A rupee amount has Rs/INR/₹ just before it,
    Indian comma grouping, or exactly two decimals; '400' in '400 equity shares' is not one."""
    money, every = set(), set()
    for m in NUMBER_RE.finditer(text):
        value = normalise_amount(m.group(0))
        if value is None:
            continue
        every.add(value)
        s = m.group(0).rstrip(".,")
        if (CURRENCY_BEFORE.search(text[max(0, m.start() - 6):m.start()]) or "," in s
                or re.fullmatch(r"\d+\.\d{2}", s)):
            money.add(value)
    return money, every


def clean_fields(clue: Clue, ev: Evidence) -> list[str]:
    """Drop fields the text does not support while keeping the clue (its identifier and quote may
    still be good evidence). Returns a note per dropped field.
    - nominee: kept only if the text mentions a nominee/nomination at all.
    - amount: kept only if it matches a number written as a rupee amount. If it matches only a
      bare number (a share count, a term in months), the amount is dropped. If it matches no
      number at all it is left for ground() to reject."""
    notes = []
    if clue.nominee and not NOMINEE_RE.search(ev.text):
        notes.append(f"nominee {clue.nominee!r} dropped: text never mentions a nominee")
        clue.nominee = None
    if clue.amount is not None:
        money, every = _money_numbers(ev.text)
        near = lambda pool: any(abs(n - clue.amount) < 0.01 for n in pool)  # noqa: E731
        if not near(money) and near(every):
            notes.append(f"amount {clue.amount} dropped: not written as a rupee amount")
            clue.amount, clue.amount_kind = None, "unknown"
    return notes


def ground(clue: Clue, ev: Evidence) -> tuple[bool, str]:
    """(True, "") if the clue is supported by the evidence text, else (False, reason).
    Rules: quote appears verbatim (case/whitespace-insensitive); identifier's last 4
    characters appear in the text; amount appears in the text after normalising every
    number found in the text with normalise_amount.
    (A fuzzy quote match was tried and dropped: it changes which items count as covered, which
    changes the retry-missed requests, which turns cached runs into new LLM calls.)"""
    text = _squash(ev.text)
    quote = _squash(clue.quote)
    if not quote or quote not in text:
        return False, f"quote not in text: {clue.quote[:60]!r}"
    if clue.identifier:
        tail = clue.identifier.strip()[-4:].lower()
        if tail not in text:
            return False, f"identifier {clue.identifier!r}: last 4 {tail!r} not in text"
    if clue.amount is not None:
        numbers = {normalise_amount(n) for n in NUMBER_RE.findall(ev.text)}
        if not any(n is not None and abs(n - clue.amount) < 0.01 for n in numbers):
            return False, f"amount {clue.amount} not in text"
    return True, ""


# ---- LLM output -> Clue ------------------------------------------------------------------------

def _coerce_amount(value: Any) -> float | None:
    if value is None or isinstance(value, (int, float)):
        return value
    return normalise_amount(str(value))


def _to_clue(raw: dict) -> Clue:
    """Build an unnumbered Clue from one LLM dict; raises ValueError/ValidationError if malformed."""
    data = {k: raw.get(k) for k in CLUE_FIELDS}
    data["amount"] = _coerce_amount(data["amount"])
    data["amount_kind"] = data["amount_kind"] or "unknown"
    for k in ("identifier", "date", "nominee", "institution_raw"):
        if data[k] is not None:
            data[k] = str(data[k])
    return Clue(id="", **data)


def _check_one(raw: Any, by_id: dict[str, Evidence]) -> tuple[Clue | None, str]:
    if not isinstance(raw, dict):
        return None, f"not an object: {raw!r:.60}"
    ev = by_id.get(str(raw.get("evidence_id")))
    if ev is None:
        return None, f"unknown evidence_id {raw.get('evidence_id')!r}"
    try:
        clue = _to_clue(raw)
    except (ValidationError, ValueError, TypeError) as exc:
        first = exc.errors()[0] if isinstance(exc, ValidationError) else {"msg": str(exc), "loc": ()}
        return None, f"invalid field {'.'.join(map(str, first['loc']))}: {first['msg']}"
    for note in clean_fields(clue, ev):
        print(f"[extract] FIELD {ev.id}: {note}")
    ok, reason = ground(clue, ev)
    return (clue, "") if ok else (None, reason)


def _batch_user_message(batch: list[Evidence]) -> str:
    items = [{"id": ev.id, "sender": ev.sender, "text": ev.text} for ev in batch]
    ids = ", ".join(ev.id for ev in batch)
    return (f"{len(batch)} messages follow. Go through every one of them in order ({ids}) and return the clues "
            f"from each; do not stop early.\nMessages:\n" + json.dumps(items, ensure_ascii=False, indent=1))


async def _call_batch(batch: list[Evidence], sem: asyncio.Semaphore, label: str) -> list[Clue] | None:
    """One LLM call, logged as one line. Returns None if the call failed outright.
    Rate limits are waited out inside llm.py and never cause a split. A truncated reply
    (finish_reason == "length") or output that stays malformed after llm.py's retries means the
    batch is too big: split it in half. A single item that still fails is logged and skipped."""
    meta: dict = {}
    t0 = time.perf_counter()
    try:
        async with sem:
            result = await asyncio.to_thread(call_llm_json, EXTRACTION_PROMPT, _batch_user_message(batch),
                                             None, MAX_TOKENS, meta)
    except CacheMiss:
        print(f"[extract] {label}: CACHE MISS items={len(batch)} (cache-only mode, no call made) "
              f"({batch[0].id}..{batch[-1].id})")
        return None
    except openai.RateLimitError as exc:
        msg = exc.body.get("message", str(exc)) if isinstance(exc.body, dict) else str(exc)
        print(f"[extract] {label}: FAILED items={len(batch)} {time.perf_counter() - t0:.1f}s 429 on "
              f"{_limit_kind(exc)}, not retried: {re.sub(r'org_\w+', 'org_…', msg)[:400]}")
        return None
    except Exception as exc:
        reason = "too big" if isinstance(exc, OutputTruncated) else type(exc).__name__
        print(f"[extract] {label}: FAILED items={len(batch)} {time.perf_counter() - t0:.1f}s "
              f"cache={meta.get('cache')} finish_reason={meta.get('finish_reason')} ({reason}): {str(exc)[:200]}")
        if len(batch) == 1:
            return None
        mid = len(batch) // 2
        halves = [await _call_batch(batch[:mid], sem, f"{label}a"), await _call_batch(batch[mid:], sem, f"{label}b")]
        return None if all(h is None for h in halves) else [c for h in halves for c in h or []]
    by_id = {ev.id: ev for ev in batch}
    raw_clues = result.get("clues") or []
    grounded = []
    for raw in raw_clues:
        clue, reason = _check_one(raw, by_id)
        if clue is None:
            eid = raw.get("evidence_id") if isinstance(raw, dict) else "?"
            print(f"[extract] REJECT {eid}: {reason}")
        else:
            grounded.append(clue)
    print(f"[extract] {label}: items={len(batch)} clues={len(grounded)}/{len(raw_clues)} "
          f"{time.perf_counter() - t0:.1f}s cache={meta.get('cache')} ({batch[0].id}..{batch[-1].id})")
    return grounded


async def _run_batch(batch: list[Evidence], sem: asyncio.Semaphore, n: int) -> list[Clue]:
    """One batch call, then one coverage pass: models tend to skip the tail of a long batch,
    so items that produced no clue are sent again on their own batch."""
    clues = await _call_batch(batch, sem, f"batch {n}")
    if clues is None:                        # failed outright: re-sending the same items would fail too
        return []
    covered = {c.evidence_id for c in clues}
    missed = [ev for ev in batch if ev.id not in covered]
    # Retry only a skipped tail: if nothing came back, the same request would return the same answer.
    if missed and covered and len(batch) > 1:
        clues += await _call_batch(missed, sem, f"batch {n} retry-missed") or []
    order = {ev.id: i for i, ev in enumerate(batch)}
    return sorted(clues, key=lambda c: order[c.evidence_id])     # stable sort keeps per-item order


async def transcribe_photo(ev: Evidence, sem: asyncio.Semaphore | None = None) -> Evidence:
    """Fill ev.text from the photo with the vision model (no-op if already transcribed)."""
    if ev.text or not ev.path:
        return ev
    sem = sem or asyncio.Semaphore(1)
    async with sem:
        result = await asyncio.to_thread(call_llm_json, TRANSCRIBE_PROMPT, f"Photo file: {Path(ev.path).name}",
                                         [Path(ev.path)])
    ev.text = str(result.get("text") or "")
    print(f"[extract] transcribed {ev.id}: {len(ev.text)} chars")
    return ev


async def _run_photo(ev: Evidence, sem: asyncio.Semaphore, n: int) -> list[Clue]:
    try:
        await transcribe_photo(ev, sem)
    except CacheMiss:
        print(f"[extract] {ev.id}: CACHE MISS on transcription (cache-only mode, no call made)")
        return []
    if not ev.text:
        print(f"[extract] REJECT {ev.id}: empty transcript")
        return []
    return await _run_batch([ev], sem, n)


async def extract_clues(evidence: list[Evidence], on_clue: Callable[[Clue], None] | None = None,
                        start_id: int = 1,
                        on_progress: Callable[[int, int], None] | None = None) -> list[Clue]:
    """Run extraction over financial evidence; call on_clue for each grounded clue (for SSE).
    Batches run concurrently, but clues are numbered and emitted in evidence order so ids are stable.
    on_progress(items_done, items_total), if given, is called as each batch or photo is collected."""
    sem = asyncio.Semaphore(CONCURRENCY)
    financial = [ev for ev in evidence if ev.is_financial]
    texts = [ev for ev in financial if ev.source != "photo"]
    photos = [ev for ev in financial if ev.source == "photo"]
    batches = [texts[i:i + BATCH_SIZE] for i in range(0, len(texts), BATCH_SIZE)]
    jobs = [_run_batch(b, sem, n) for n, b in enumerate(batches, start=1)]
    jobs += [_run_photo(ev, sem, len(batches) + k) for k, ev in enumerate(photos, start=1)]
    print(f"[extract] {len(texts)} text items in {len(batches)} batches of <= {BATCH_SIZE}, "
          f"{len(photos)} photos, concurrency {CONCURRENCY}")

    tasks = [asyncio.create_task(j) for j in jobs]
    sizes = [len(b) for b in batches] + [1] * len(photos)
    clues: list[Clue] = []
    done = 0
    for task, size in zip(tasks, sizes):
        for clue in await task:
            clue.id = f"cl_{start_id + len(clues):04d}"
            clues.append(clue)
            if on_clue:
                on_clue(clue)
        done += size
        if on_progress:
            on_progress(done, len(financial))
    print(f"[extract] done: {len(clues)} grounded clues")
    return clues
