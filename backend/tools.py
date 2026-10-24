"""Role B, step B2. The tools the agent can call. Each returns a SMALL JSON-serialisable
summary (aim < 2 KB) and updates CaseState; the full data stays in CaseState.

Tools: scan_sources, extract_clues, build_asset_map, search_evidence, read_photo,
check_portal, apply_claim_rules, ask_family, generate_claim_pack, finish.
TOOL_SCHEMAS describes them in the JSON-schema form our provider's tool calling expects.

Every tool is `async def tool(state, **args) -> dict`. Use call_tool(state, name, args) from the agent.
Portal results and family answers are kept as overrides keyed by (institution, type, last 4 digits),
so they survive a rebuild of the asset map.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from rapidfuzz import fuzz, utils

import extract
import rules
from claimpack import build_claim_pack
from confidence import explain as explain_confidence
from ingest import load_case
from models import Asset, Case, Claim, Clue, Evidence
from resolve import ALIASES, build_assets, normalise_institution
from triage import triage

ROOT = Path(__file__).resolve().parents[1]
PORTALS_PATH = Path(__file__).parent / "portals_mock.json"
CLAIMPACK_DIR = ROOT / "out" / "claimpacks"
MAX_RESULT_BYTES = 2000
SOURCES = ("sms", "email", "ais", "photo")
NAME_MIN = 85                 # token_sort_ratio: "RAMESH KUMAR" matches, "RAMESH KUMAR SHARMA" does not
INSTITUTION_MIN = 85
SNIPPET_CHARS = 140
ANSWER_TIMEOUT_S = 600.0

Emit = Callable[[str, dict], Any]


@dataclass
class CaseState:
    case: Case
    evidence: list[Evidence] = field(default_factory=list)
    clues: list[Clue] = field(default_factory=list)
    assets: list[Asset] = field(default_factory=list)
    claims: dict[str, Claim] = field(default_factory=dict)
    answers: dict[str, str] = field(default_factory=dict)
    as_of: date = field(default_factory=date.today)
    emit: Optional[Emit] = None                                   # emit(type, data) -> SSE; may be async
    overrides: dict[tuple, dict] = field(default_factory=dict)    # asset key -> fields set by portals/family
    portal_hits: dict[str, dict] = field(default_factory=dict)    # asset_id -> portal record
    pending: dict[str, asyncio.Future] = field(default_factory=dict)  # question_id -> answer future
    claim_packs: dict[str, str] = field(default_factory=dict)     # asset_id -> docx path
    extracted: bool = False                                       # the one full extraction pass has run
    finished: bool = False
    summary: str = ""

    def answer(self, question_id: str, answer: str) -> bool:
        """Called by app.py when the family answers. Returns False if the question is unknown or done."""
        fut = self.pending.get(question_id)
        if fut is None or fut.done():
            return False
        fut.get_loop().call_soon_threadsafe(fut.set_result, answer)
        return True


# ---- helpers -----------------------------------------------------------------------------------

async def _emit(state: CaseState, type_: str, data: dict) -> None:
    if state.emit is None:
        return
    result = state.emit(type_, data)
    if asyncio.iscoroutine(result):
        await result


class _Stream:
    """A plain (sync) emit for the pipeline functions, which are not async and may run in a worker
    thread. Events are queued on the event loop in call order; flush() waits until all are sent."""

    def __init__(self, state: CaseState) -> None:
        self.state, self.loop, self.tasks = state, asyncio.get_running_loop(), []

    def __call__(self, type_: str, data: dict) -> None:
        if self.state.emit is not None:
            self.loop.call_soon_threadsafe(self._start, type_, data)

    def _start(self, type_: str, data: dict) -> None:
        self.tasks.append(self.loop.create_task(_emit(self.state, type_, data)))

    def progress(self, stage: str, done: int, total: int) -> None:
        self("progress", {"stage": stage, "done": done, "total": total})

    async def flush(self) -> None:
        await asyncio.sleep(0)            # run the queued _start callbacks
        await asyncio.gather(*self.tasks)
        self.tasks.clear()


def _limit() -> Optional[int]:
    """LIMIT env var: cap on financial evidence items, for quick runs. Unset or invalid -> no cap."""
    raw = os.getenv("LIMIT", "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else None


def _size(obj: Any) -> int:
    return len(json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))


def _small(result: dict) -> dict:
    """Trim the longest list in the result until it fits in MAX_RESULT_BYTES."""
    while _size(result) > MAX_RESULT_BYTES:
        lists = [(k, v) for k, v in result.items() if isinstance(v, list) and v]
        if not lists:
            break
        key, longest = max(lists, key=lambda kv: _size(kv[1]))
        result[key] = longest[:-1]
        result["truncated"] = True
    return result


def _last4(identifier: Optional[str]) -> Optional[str]:
    digits = re.sub(r"\D", "", identifier or "")
    return digits[-4:] if len(digits) >= 4 else None


def _asset_key(a: Asset) -> tuple:
    return (a.institution, a.asset_type, _last4(a.identifier) or a.identifier)


def _find_asset(state: CaseState, asset_id: str) -> Optional[Asset]:
    return next((a for a in state.assets if a.id == asset_id), None)


def confidence_detail(state: CaseState, asset: Asset) -> dict:
    """Explainable confidence for one asset (see confidence.py), using its portal record if found."""
    ev_by_id = {e.id: e for e in state.evidence}
    return explain_confidence(asset, state.clues, ev_by_id, state.as_of, state.portal_hits.get(asset.id))


def _rescore(state: CaseState, asset: Asset) -> Asset:
    updated = asset.model_copy(update={"confidence": confidence_detail(state, asset)["score"]})
    _replace_asset(state, updated)
    return updated


def _replace_asset(state: CaseState, asset: Asset) -> None:
    state.assets = [asset if a.id == asset.id else a for a in state.assets]


def _set_override(state: CaseState, asset: Asset, **fields: Any) -> Asset:
    state.overrides.setdefault(_asset_key(asset), {}).update(fields)
    updated = asset.model_copy(update=fields)
    _replace_asset(state, updated)
    return updated


UNCONFIRMED_TRANSFER = {"transferred_dea": "UDGAM", "transferred_iepf": "IEPF"}
GENERIC_WORDS = {"BANK", "OF", "INDIA", "LTD", "LIMITED", "LIFE", "INSURANCE", "MUTUAL", "FUND", "THE", "AND", "&"}
KNOWN_TYPE_WORDS: list[tuple[str, set[str]]] = [
    (r"\bsavings?\b|\bsb\b", {"savings_account"}),
    (r"\bfd\b|fixed deposit|\bdeposit\b", {"fixed_deposit"}),
    (r"\bpolicy\b|insurance", {"life_insurance"}),
    (r"mutual fund|\bsip\b|\bfolio\b", {"mutual_fund"}),
    (r"\bshares?\b|\bstock\b", {"shares"}),
    (r"\bpf\b|provident", {"provident_fund"}),
]


def _names_institution(text: str, institution: str) -> bool:
    """True if the family's free text names this institution: by an alias (SBI, LIC) or by all of its
    distinctive words (Canara, Kaveri)."""
    words = set(re.findall(r"[A-Z0-9&]+", text.upper()))
    if any(inst == institution and alias in words for alias, inst in ALIASES.items()):
        return True
    own = set(institution.upper().split())
    return own.issubset(words) or bool(own - GENERIC_WORDS) and (own - GENERIC_WORDS).issubset(words)


def _known_matches(text: str, assets: list[Asset]) -> list[Asset]:
    """Assets one line of 'the family already knows about' refers to. Digits in the text (3+) must end the
    asset's identifier; a type word (savings, FD, policy...) must match the asset type."""
    found = [a for a in assets if _names_institution(text, a.institution)]
    for num in re.findall(r"\d{3,}", text):
        found = [a for a in found if re.sub(r"\D", "", a.identifier or "").endswith(num[-4:])]
    for pattern, types in KNOWN_TYPE_WORDS:
        if re.search(pattern, text, re.I):
            found = [a for a in found if a.asset_type in types]
            break
    return found


def mark_known_assets(state: CaseState, assets: list[Asset]) -> list[Asset]:
    """Flag known_to_family on the assets the family told us about (Case.known_assets)."""
    known: set[str] = set()
    for text in state.case.known_assets:
        matches = _known_matches(text, assets)
        print(f"[tools] known asset {text!r} -> {[a.id for a in matches] or 'no match'}")
        known.update(a.id for a in matches)
    return [a.model_copy(update={"known_to_family": a.id in known}) for a in assets]


def _asset_row(state: CaseState, a: Asset) -> dict:
    row = {"id": a.id, "institution": a.institution, "type": a.asset_type, "identifier": a.identifier,
           "value": a.est_value, "last_activity": a.last_activity, "status": a.status, "nominee": a.nominee,
           "confidence": a.confidence, "clues": len(a.clue_ids)}
    portal = UNCONFIRMED_TRANSFER.get(a.status)
    if portal and a.id not in state.portal_hits:
        # The status is inferred from inactivity; only the portal record confirms it and gives the value.
        row["todo"] = f'transfer inferred, not confirmed: check_portal(portal="{portal}", institution="{a.institution}")'
    return row


def _ev_date(ev: Evidence) -> Optional[str]:
    return ev.timestamp[:10] if ev.timestamp else None


def _snippet(text: str, start: int, end: int) -> str:
    pad = max(0, (SNIPPET_CHARS - (end - start)) // 2)
    lo, hi = max(0, start - pad), min(len(text), end + pad)
    s = re.sub(r"\s+", " ", text[lo:hi]).strip()
    return ("…" if lo > 0 else "") + s + ("…" if hi < len(text) else "")


def _next_clue_id(state: CaseState) -> int:
    nums = [int(c.id.split("_")[1]) for c in state.clues if c.id.startswith("cl_") and c.id[3:].isdigit()]
    return max(nums, default=0) + 1


async def _extract_into_state(state: CaseState, items: list[Evidence], stage: str | None = None) -> list[Clue]:
    """Extract clues from items, replacing any clues already held for those evidence ids.
    Each clue is streamed as soon as its batch is collected; with stage, progress events too."""
    ids = {ev.id for ev in items}
    state.clues = [c for c in state.clues if c.evidence_id not in ids]
    stream = _Stream(state)
    on_progress = (lambda done, total: stream.progress(stage, done, total)) if stage else None
    new = await extract.extract_clues(items, start_id=_next_clue_id(state),
                                      on_clue=lambda c: stream("clue", c.model_dump()), on_progress=on_progress)
    await stream.flush()
    state.clues.extend(new)
    return new


def _clue_summary(clues: list[Clue]) -> dict:
    return {"by_type": dict(Counter(c.asset_type for c in clues)),
            "institutions": [k for k, _ in Counter(c.institution_raw for c in clues).most_common(10)]}


# ---- tools -------------------------------------------------------------------------------------

async def scan_sources(state: CaseState) -> dict:
    """Load every upload for the case and mark which items look financial."""
    data_dir = Path(state.case.data_dir)
    data_dir = data_dir if data_dir.is_absolute() else ROOT / data_dir
    stream = _Stream(state)
    # Parsing 3,000 SMS and the AIS PDF blocks; a worker thread lets the progress events stream meanwhile.
    state.evidence = await asyncio.to_thread(lambda: triage(load_case(data_dir, stream.progress), stream.progress))
    limit = _limit()
    if limit is not None:
        financial_items = [ev for ev in state.evidence if ev.is_financial]
        for ev in financial_items[limit:]:
            ev.is_financial = False
        print(f"[tools] LIMIT={limit}: kept the first {min(limit, len(financial_items))} "
              f"of {len(financial_items)} financial items")
    await stream.flush()
    total = Counter(ev.source for ev in state.evidence)
    financial = Counter(ev.source for ev in state.evidence if ev.is_financial)
    await _emit(state, "progress", {"stage": "scan", "done": len(state.evidence), "total": len(state.evidence)})
    return _small({"sources": {s: {"items": total[s], "financial": financial[s]} for s in SOURCES},
                   "photos": [Path(ev.path).name for ev in state.evidence if ev.source == "photo" and ev.path]})


async def extract_clues(state: CaseState, source: str = "all") -> dict:
    """Extract grounded clues from the financial items of one source (sms|email|ais|photo|all)."""
    if not state.evidence:
        return {"error": "no evidence loaded; call scan_sources first"}
    if source != "all" and source not in SOURCES:
        return {"error": f"unknown source {source!r}; use one of {', '.join(SOURCES)} or all"}
    financial = [ev for ev in state.evidence if ev.is_financial]
    items = [ev for ev in financial if source == "all" or ev.source == source]
    if not state.extracted:
        # One pass over ALL financial evidence, whichever source was asked for: the batches then match
        # the cached full run. Per-source passes shift batch boundaries and miss the LLM cache.
        await _emit(state, "progress", {"stage": "extract:all", "done": 0, "total": len(financial)})
        await _extract_into_state(state, financial, stage="extract:all")
        state.extracted = True
    ids = {ev.id for ev in items}
    new = [c for c in state.clues if c.evidence_id in ids]
    return _small({"source": source, "items_read": len(items), "clues_added": len(new),
                   "clues_total": len(state.clues), **_clue_summary(new)})


async def build_asset_map(state: CaseState) -> dict:
    """Cluster all clues into assets, compute status, re-apply portal results and family answers."""
    if not state.clues:
        return {"error": "no clues yet; call extract_clues first"}
    stream = _Stream(state)
    built = build_assets(state.clues, state.evidence, state.as_of, progress=stream.progress)
    await stream.flush()
    assets = []
    for a in built:
        a = rules.apply_status(a, state.as_of)
        override = state.overrides.get(_asset_key(a))
        assets.append(a.model_copy(update=override) if override else a)
    # Assets that exist only because a portal reported them (no clues) are kept across rebuilds.
    keys = {_asset_key(a) for a in assets}
    assets += [a for a in state.assets if not a.clue_ids and _asset_key(a) not in keys]
    state.assets = mark_known_assets(state, assets)
    for a in list(state.assets):
        _rescore(state, a)
    assets = state.assets
    for a in assets:
        await _emit(state, "asset", a.model_dump())
    total = sum(a.est_value or 0 for a in assets)
    known = sum(a.est_value or 0 for a in assets if a.known_to_family)
    return _small({"asset_count": len(assets), "total_value": total, "known_value": known, "assets": [_asset_row(state, a) for a in assets]})


async def search_evidence(state: CaseState, query: str) -> dict:
    """Case-insensitive search over ALL evidence (financial or not), sender included."""
    if not query.strip():
        return {"error": "empty query"}
    pattern = re.compile(re.escape(query.strip()), re.I)
    hits = []
    for ev in state.evidence:
        haystack = f"{ev.sender}\n{ev.text}"
        m = pattern.search(haystack)
        if m:
            hits.append({"id": ev.id, "date": _ev_date(ev), "snippet": _snippet(haystack, m.start(), m.end())})
    return _small({"query": query, "matches": len(hits), "results": hits[:5]})


async def read_photo(state: CaseState, file: str) -> dict:
    """Transcribe one photo (by file name or evidence id) and extract clues from it."""
    stem = Path(file).stem
    ev = next((e for e in state.evidence if e.source == "photo"
               and (e.id == file or e.id == f"photo_{stem}" or (e.path and Path(e.path).name == file))), None)
    if ev is None:
        photos = [Path(e.path).name for e in state.evidence if e.source == "photo" and e.path]
        return _small({"error": f"no photo {file!r}", "photos": photos})
    try:
        await extract.transcribe_photo(ev)
    except extract.CacheMiss:
        return {"error": f"{ev.id}: transcription not cached (cache-only mode)"}
    new = [c for c in state.clues if c.evidence_id == ev.id]
    if not new and ev.text:
        new = await _extract_into_state(state, [ev])
    clues = [{"type": c.asset_type, "institution": c.institution_raw, "identifier": c.identifier,
              "amount": c.amount, "date": c.date, "nominee": c.nominee} for c in new]
    return _small({"evidence_id": ev.id, "text": ev.text[:500], "clues": clues})


def _load_portals() -> dict:
    return json.loads(PORTALS_PATH.read_text(encoding="utf-8"))


PORTAL_FIELDS = {   # portal -> (person field, institution field, identifier field, value field, status)
    "UDGAM": ("name", "bank", "account_masked", "amount", "transferred_dea"),
    "IEPF": ("holder", "company", "folio", "total", "transferred_iepf"),
    "BIMA_BHAROSA": ("policyholder", "insurer", "policy_masked", "unclaimed_amount", None),
}
PORTAL_TYPES = {"UDGAM": {"savings_account", "fixed_deposit"}, "IEPF": {"shares"}, "BIMA_BHAROSA": {"life_insurance"}}


def _institution_match(a: str, b: str) -> bool:
    na, nb = normalise_institution(a), normalise_institution(b)
    return na == nb or fuzz.token_set_ratio(na, nb, processor=utils.default_process) >= INSTITUTION_MIN


def _matching_asset(state: CaseState, portal: str, institution: str, ident: str) -> Optional[Asset]:
    pool = [a for a in state.assets if a.asset_type in PORTAL_TYPES[portal]
            and _institution_match(a.institution, institution)]
    exact = [a for a in pool if a.identifier and _last4(a.identifier) == _last4(ident)]
    if exact:
        return exact[0]
    unnamed = [a for a in pool if not a.identifier]
    return unnamed[0] if len(unnamed) == 1 else None


async def check_portal(state: CaseState, portal: str, name: str, institution: str) -> dict:
    """Look up the deceased in an unclaimed-money portal (mock). UDGAM/IEPF hits update the asset."""
    portal = portal.upper()
    if portal not in PORTAL_FIELDS:
        return {"error": f"unknown portal {portal!r}; use UDGAM, IEPF or BIMA_BHAROSA"}
    person_f, inst_f, ident_f, value_f, status = PORTAL_FIELDS[portal]
    records = _load_portals().get(portal, [])
    hits = [r for r in records
            if fuzz.token_sort_ratio(name, r[person_f], processor=utils.default_process) >= NAME_MIN
            and _institution_match(institution, r[inst_f])]
    results = []
    for r in hits:
        row = {"institution": r[inst_f], "identifier": r[ident_f], "value": r[value_f]}
        asset = _matching_asset(state, portal, r[inst_f], r[ident_f])
        if status is not None:
            fields = {"est_value": float(r[value_f]), "status": status, "value_basis": f"{portal} portal record"}
            if asset is None:     # the portal knows of a holding the trail never mentioned
                asset = Asset(id=f"as_{len(state.assets) + 1:02d}", institution=normalise_institution(r[inst_f]),
                              asset_type=sorted(PORTAL_TYPES[portal])[0], identifier=r[ident_f], confidence=0.6,
                              nominee="unknown")
                state.assets.append(asset)
            asset = _set_override(state, asset, **fields)
            state.portal_hits[asset.id] = {"portal": portal, **r}
            asset = _rescore(state, asset)
            await _emit(state, "asset", asset.model_dump())
            row.update(asset_id=asset.id, status=asset.status)
        elif asset is not None:
            row["asset_id"] = asset.id
        results.append(row)
    out = {"portal": portal, "name": name, "institution": institution, "hits": len(hits), "results": results}
    pending = [a for a in state.assets if UNCONFIRMED_TRANSFER.get(a.status) == portal and a.id not in state.portal_hits]
    if pending:
        # Usually the model searched the wrong institution; name the ones still waiting for this portal.
        out["still_unconfirmed"] = [{"asset_id": a.id, "institution": a.institution, "identifier": a.identifier}
                                    for a in pending]
    return _small(out)


async def apply_claim_rules(state: CaseState, asset_id: str = "all") -> dict:
    """Work out the claim path for one asset, or for every asset with asset_id='all'."""
    targets = state.assets if asset_id == "all" else [a for a in state.assets if a.id == asset_id]
    if not targets:
        return {"error": f"no asset {asset_id!r}"}
    rows = []
    for a in targets:
        claim = rules.claim_for(a, state.assets, state.case.documents_have)
        state.claims[a.id] = claim
        await _emit(state, "claim", claim.model_dump())
        rows.append({"asset_id": a.id, "status": a.status, "nominee": a.nominee, "path": claim.path,
                     "missing_docs": sum(not d.have for d in claim.documents)})
    return _small({"claims": rows})


def _nominee_from_answer(answer: str) -> Optional[str]:
    word = answer.strip().lower()
    if word.startswith("yes"):
        return "yes"
    if word.startswith("no") and not word.startswith("not sure"):
        return "no"
    return None


async def ask_family(state: CaseState, question: str, options: list[str] | None = None,
                     asset_id: str | None = None) -> dict:
    """Ask the family a question and wait for the answer. With asset_id and a yes/no answer to a
    nominee question, the asset's nominee is updated."""
    qid = f"q_{len(state.answers) + len(state.pending) + 1:02d}"
    fut: asyncio.Future = asyncio.get_running_loop().create_future()
    state.pending[qid] = fut
    await _emit(state, "question", {"id": qid, "text": question, "options": options or []})
    try:
        answer = str(await asyncio.wait_for(fut, ANSWER_TIMEOUT_S))
    except asyncio.TimeoutError:
        return {"question_id": qid, "answer": None, "error": "no answer from the family"}
    finally:
        state.pending.pop(qid, None)
    state.answers[qid] = answer
    result: dict[str, Any] = {"question_id": qid, "answer": answer}
    asset = _find_asset(state, asset_id) if asset_id else None
    nominee = _nominee_from_answer(answer)
    if asset is not None and nominee and "nomin" in question.lower():
        asset = _set_override(state, asset, nominee=nominee)
        await _emit(state, "asset", asset.model_dump())
        result.update(asset_id=asset.id, nominee=nominee)
    return result


def asset_quotes(state: CaseState, asset: Asset) -> list[dict]:
    """{evidence_id, date, quote} for every clue of the asset, plus its portal record if one was found.
    A clue's date falls back to its evidence timestamp."""
    ev_by_id = {e.id: e for e in state.evidence}
    ids = set(asset.clue_ids)
    quotes = [{"evidence_id": c.evidence_id,
               "date": c.date or (_ev_date(ev_by_id[c.evidence_id]) if c.evidence_id in ev_by_id else None),
               "quote": c.quote} for c in state.clues if c.id in ids]
    hit = state.portal_hits.get(asset.id)
    if hit:
        when = hit.get("transferred_to_dea") or hit.get("transferred_on")
        record = "; ".join(f"{k}: {v}" for k, v in hit.items() if k != "portal")
        quotes.append({"evidence_id": f"portal_{hit['portal']}", "date": when, "quote": f"{hit['portal']} record: {record}"})
    return quotes


async def _write_claim_pack(state: CaseState, asset: Asset) -> dict:
    claim = rules.claim_for(asset, state.assets, state.case.documents_have)
    state.claims[asset.id] = claim
    path = build_claim_pack(state.case, asset, claim, asset_quotes(state, asset), CLAIMPACK_DIR)
    state.claim_packs[asset.id] = str(path)
    await _emit(state, "claim", claim.model_dump())
    return {"asset_id": asset.id, "path": claim.path, "file": Path(path).name,
            "documents": len(claim.documents), "missing_docs": sum(not d.have for d in claim.documents)}


async def generate_claim_pack(state: CaseState, asset_id: str = "all") -> dict:
    """Write the .docx claim pack for one asset, or for every asset with asset_id='all', to out/claimpacks/
    (claim rules are re-applied first)."""
    if asset_id == "all":
        if not state.assets:
            return {"error": "no assets yet; call build_asset_map first"}
        return _small({"packs": [await _write_claim_pack(state, a) for a in state.assets]})
    asset = _find_asset(state, asset_id)
    if asset is None:
        return {"error": f"no asset {asset_id!r}"}
    return await _write_claim_pack(state, asset)


async def finish(state: CaseState, summary: str) -> dict:
    """End the run and report totals."""
    state.finished, state.summary = True, summary
    data = {"total_value": sum(a.est_value or 0 for a in state.assets),
            "known_value": sum(a.est_value or 0 for a in state.assets if a.known_to_family),
            "asset_count": len(state.assets)}
    await _emit(state, "done", data)
    return {**data, "claims": len(state.claims), "claim_packs": len(state.claim_packs)}


# ---- registry ----------------------------------------------------------------------------------

def _schema(name: str, description: str, properties: dict | None = None, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties or {}, "required": required or []}}}


_STR = {"type": "string"}
TOOL_SCHEMAS: list[dict] = [
    _schema("scan_sources", "Load every uploaded source (SMS, email, AIS, photos) and count financial items."),
    _schema("extract_clues", "Extract grounded asset clues from one source's financial items.",
            {"source": {"type": "string", "enum": [*SOURCES, "all"]}}, ["source"]),
    _schema("build_asset_map", "Cluster all clues into assets with value, last activity, nominee and status."),
    _schema("search_evidence", "Case-insensitive text search over ALL evidence, including non-financial items. "
            "Returns up to 5 {id, date, snippet}.", {"query": _STR}, ["query"]),
    _schema("read_photo", "Transcribe one uploaded photo and extract clues from it.",
            {"file": {"type": "string", "description": "photo file name, e.g. passbook.jpg"}}, ["file"]),
    _schema("check_portal", "Search an unclaimed-money portal for the deceased: UDGAM (bank deposits moved to the "
            "RBI DEA Fund), IEPF (shares/dividends), BIMA_BHAROSA (insurance). A hit updates the asset.",
            {"portal": {"type": "string", "enum": list(PORTAL_FIELDS)},
             "name": {"type": "string", "description": "deceased person's name"},
             "institution": {"type": "string", "description": "bank, company or insurer"}},
            ["portal", "name", "institution"]),
    _schema("apply_claim_rules", "Work out the legal claim path for an asset, or for all assets with 'all'.",
            {"asset_id": {"type": "string", "description": "asset id like as_01, or 'all'"}}, ["asset_id"]),
    _schema("ask_family", "Ask the legal heir a question the evidence cannot answer, and wait for the reply. "
            "Pass asset_id when the question is about one asset's nominee.",
            {"question": _STR, "options": {"type": "array", "items": _STR},
             "asset_id": {"type": "string", "description": "asset the question is about (optional)"}},
            ["question", "options"]),
    _schema("generate_claim_pack", "Write the claim pack documents for all assets with 'all' (preferred, one call), "
            "or for one asset.",
            {"asset_id": {"type": "string", "description": "'all', or an asset id like as_01"}}, ["asset_id"]),
    _schema("finish", "End the investigation with a short summary for the family.", {"summary": _STR}, ["summary"]),
]

ToolFn = Callable[..., Awaitable[dict]]
TOOLS: dict[str, ToolFn] = {
    "scan_sources": scan_sources, "extract_clues": extract_clues, "build_asset_map": build_asset_map,
    "search_evidence": search_evidence, "read_photo": read_photo, "check_portal": check_portal,
    "apply_claim_rules": apply_claim_rules, "ask_family": ask_family,
    "generate_claim_pack": generate_claim_pack, "finish": finish,
}


async def call_tool(state: CaseState, name: str, args: dict | None = None) -> dict:
    """Run a tool by name; bad names or arguments come back as an error result, not an exception."""
    fn = TOOLS.get(name)
    if fn is None:
        return {"error": f"unknown tool {name!r}"}
    try:
        inspect.signature(fn).bind(state, **(args or {}))
    except TypeError as exc:
        return {"error": f"bad arguments for {name}: {exc}"}
    return await fn(state, **(args or {}))
