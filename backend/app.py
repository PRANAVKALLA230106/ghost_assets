"""FastAPI app. Built in step 1 (fake events) and wired to the real agent in step E1.

Routes (see CLAUDE.md):
  GET  /health
  POST /cases                                   -> {case_id}
  POST /cases/upload                            -> multipart upload; saves to data/uploads/<id>/, starts the real agent
  POST /cases/{case_id}/run                     -> starts the agent (or fake replay) in the background
  GET  /cases/{case_id}/events                  -> SSE stream of {"type", "data"} events
  POST /cases/{case_id}/answers                 -> {question_id, answer}
  GET  /cases/{case_id}/assets/{asset_id}       -> asset + evidence quotes
  GET  /cases/{case_id}/assets/{asset_id}/claimpack.docx
CORS: allow http://localhost:5173.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agent import run_agent
from models import Case, Event, EventType
from tools import CaseState, asset_quotes, confidence_detail

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

FAKE_EVENT_DELAY = 0.3          # seconds between replayed fake events
TERMINAL_EVENTS = {"done", "error"}
UPLOADS_DIR = ROOT / "data" / "uploads"


@dataclass
class CaseRecord:
    case: Case
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    answers: dict[str, str] = field(default_factory=dict)
    task: asyncio.Task | None = None
    state: CaseState | None = None      # filled by the real pipeline; empty in fake-event mode


CASES: dict[str, CaseRecord] = {}


class CreateCaseRequest(BaseModel):
    deceased_name: str
    date_of_death: str
    data_dir: str
    documents_have: list[str] = []
    known_assets: list[str] = []       # free text, e.g. "SBI savings account ending 8812"


class AnswerRequest(BaseModel):
    question_id: str
    answer: str


app = FastAPI(title="Ghost Assets")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_record(case_id: str) -> CaseRecord:
    rec = CASES.get(case_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"unknown case {case_id}")
    return rec


async def emit(rec: CaseRecord, type_: EventType, data: dict) -> None:
    await rec.queue.put(Event(type=type_, data=data))


async def replay_fake_events(rec: CaseRecord) -> None:
    path = ROOT / rec.case.data_dir / "fake_events.jsonl"
    print(f"[app] case {rec.case.id}: replaying {path}")
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            await emit(rec, raw["type"], raw["data"])
            await asyncio.sleep(FAKE_EVENT_DELAY)
    except Exception as exc:  # surface any failure to the UI instead of hanging the stream
        print(f"[app] case {rec.case.id}: replay failed: {exc!r}")
        await emit(rec, "error", {"message": f"fake replay failed: {exc}"})


async def run_real_agent(rec: CaseRecord) -> None:
    """The real pipeline: the agent drives ingest, triage, extract, resolve, rules and claim packs through
    tools.py, and every tool streams its events into this case's queue."""
    state = rec.state
    limit = os.getenv("LIMIT")
    print(f"[app] case {rec.case.id}: running the agent" + (f" (LIMIT={limit})" if limit else ""))

    async def case_emit(type_: str, data: dict) -> None:
        await emit(rec, type_, data)

    try:
        await run_agent(state, case_emit)
    except Exception as exc:  # never leave the stream hanging without a terminal event
        print(f"[app] case {rec.case.id}: agent crashed: {exc!r}")
        await emit(rec, "error", {"message": f"agent crashed: {type(exc).__name__}: {str(exc)[:300]}"})


async def run_case(rec: CaseRecord) -> None:
    if os.getenv("FAKE_EVENTS") == "1":
        await replay_fake_events(rec)
    else:
        await run_real_agent(rec)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "fake_events": os.getenv("FAKE_EVENTS") == "1"}


@app.post("/cases")
async def create_case(req: CreateCaseRequest) -> dict:
    case_id = uuid.uuid4().hex[:8]
    case = Case(id=case_id, deceased_name=req.deceased_name, date_of_death=req.date_of_death, data_dir=req.data_dir,
                documents_have=req.documents_have, known_assets=req.known_assets)
    CASES[case_id] = CaseRecord(case=case, state=CaseState(case=case))
    print(f"[app] created case {case_id} for {req.deceased_name}")
    return {"case_id": case_id}


def save_upload(upload: UploadFile, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        shutil.copyfileobj(upload.file, f)


@app.post("/cases/upload")
async def upload_case(
    deceased_name: str = Form(...),
    date_of_death: str = Form(...),
    documents_have: list[str] = Form(default=[]),
    known_assets: list[str] = Form(default=[]),
    sms: UploadFile = File(...),
    email: UploadFile = File(...),
    ais: UploadFile = File(...),
    photos: list[UploadFile] = File(default=[]),
) -> dict:
    """Save the heir's files under the names ingest.py expects, then run the real agent on them.
    Photo file names are kept: evidence IDs are photo_<file stem>."""
    case_id = uuid.uuid4().hex[:8]
    case_dir = UPLOADS_DIR / case_id
    save_upload(sms, case_dir / "sms.xml")
    save_upload(email, case_dir / "emails.json")
    save_upload(ais, case_dir / "ais.pdf")
    (case_dir / "photos").mkdir(parents=True, exist_ok=True)
    for photo in photos:
        if photo.filename:
            save_upload(photo, case_dir / "photos" / Path(photo.filename).name)
    case = Case(id=case_id, deceased_name=deceased_name, date_of_death=date_of_death,
                data_dir=str(case_dir.relative_to(ROOT).as_posix()), documents_have=documents_have,
                known_assets=[k.strip() for k in known_assets if k.strip()])
    rec = CaseRecord(case=case, state=CaseState(case=case))
    CASES[case_id] = rec
    print(f"[app] uploaded case {case_id} for {deceased_name} to {case.data_dir} "
          f"({len(photos)} photos, documents {documents_have}, known {case.known_assets})")
    rec.task = asyncio.create_task(run_real_agent(rec))   # always real: uploads have no fake_events.jsonl
    return {"case_id": case_id}


@app.post("/cases/{case_id}/run")
async def run(case_id: str) -> dict:
    rec = get_record(case_id)
    if rec.task is not None and not rec.task.done():
        raise HTTPException(status_code=409, detail="case is already running")
    rec.task = asyncio.create_task(run_case(rec))
    return {"case_id": case_id, "status": "started"}


@app.get("/cases/{case_id}/events")
async def events(case_id: str) -> EventSourceResponse:
    rec = get_record(case_id)

    async def stream():
        while True:
            ev: Event = await rec.queue.get()
            yield {"event": ev.type, "data": json.dumps(ev.data)}
            if ev.type in TERMINAL_EVENTS:
                break

    return EventSourceResponse(stream())


@app.post("/cases/{case_id}/answers")
async def answers(case_id: str, req: AnswerRequest) -> dict:
    rec = get_record(case_id)
    rec.answers[req.question_id] = req.answer
    if rec.state is not None:
        rec.state.answer(req.question_id, req.answer)
    print(f"[app] case {case_id}: answer {req.question_id} = {req.answer!r}")
    return {"ok": True}


def get_asset(rec: CaseRecord, asset_id: str):
    asset = next((a for a in rec.state.assets if a.id == asset_id), None) if rec.state else None
    if asset is None:
        raise HTTPException(status_code=404, detail=f"unknown asset {asset_id}")
    return asset


@app.get("/cases/{case_id}/assets/{asset_id}")
async def asset_detail(case_id: str, asset_id: str) -> dict:
    rec = get_record(case_id)
    asset = get_asset(rec, asset_id)
    claim = rec.state.claims.get(asset_id)
    quotes = sorted(asset_quotes(rec.state, asset), key=lambda q: q["date"] or "", reverse=True)
    # Attach the original message so the UI can show the quote highlighted in context.
    ev_by_id = {e.id: e for e in rec.state.evidence}
    for q in quotes:
        ev = ev_by_id.get(q["evidence_id"])
        q["source"], q["sender"], q["text"] = (ev.source, ev.sender, ev.text) if ev else (None, None, None)
    return {"asset": asset.model_dump(), "claim": claim.model_dump() if claim else None, "quotes": quotes,
            "has_claim_pack": asset_id in rec.state.claim_packs, "confidence": confidence_detail(rec.state, asset)}


@app.get("/cases/{case_id}/confidence")
async def case_confidence(case_id: str) -> dict:
    """Confidence breakdown for every asset, for the Proof screen."""
    rec = get_record(case_id)
    return {a.id: confidence_detail(rec.state, a) for a in rec.state.assets}


@app.get("/cases/{case_id}/assets/{asset_id}/claimpack.docx")
async def claim_pack(case_id: str, asset_id: str) -> FileResponse:
    rec = get_record(case_id)
    asset = get_asset(rec, asset_id)
    path = rec.state.claim_packs.get(asset_id)
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail=f"no claim pack generated yet for {asset_id}")
    return FileResponse(path, filename=f"claimpack_{asset.institution.replace(' ', '_')}_{asset_id}.docx",
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
