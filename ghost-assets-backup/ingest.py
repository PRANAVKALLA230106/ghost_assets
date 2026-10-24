"""Role A, step A1. Turn a case folder into Evidence objects.

ID scheme (must match ground_truth.json exactly):
  SMS     sms_0001, sms_0002 ... in the order they appear in sms.xml
  Email   email_001 ... in the order of emails.json
  AIS     ais_01 ... one per table data row of ais.pdf, header row excluded
  Photo   photo_<file stem>, e.g. photo_passbook (text stays "" until extract reads the image)
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

import pdfplumber

from models import Evidence

Progress = Callable[[str, int, int], None]   # (stage, done, total)

PHOTO_SUFFIXES ={".png", ".jpg", ".jpeg"}
FY_RE = re.compile(r"Financial Year:\s*(\d{4})-(\d{2,4})")


def _epoch_ms_to_iso(ms: str) -> str:
    # Epochs are UTC; naive ISO keeps them comparable with the naive email dates.
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).replace(tzinfo=None).isoformat()


def load_sms(path: Path) -> list[Evidence]:
    """Parse the 'SMS Backup & Restore' XML: <sms address=.. date=<epoch ms> body=.. />."""
    root = ET.parse(path).getroot()
    out = []
    for i, el in enumerate(root.iter("sms"), start=1):
        out.append(Evidence(
            id=f"sms_{i:04d}", source="sms", sender=el.get("address", ""),
            timestamp=_epoch_ms_to_iso(el.get("date", "0")), text=el.get("body", ""),
        ))
    print(f"[ingest] sms: {len(out)} from {path.name}")
    return out


def _email_text(e: dict) -> str:
    parts = [f"Subject: {e.get('subject', '')}", f"Body:\n{e.get('body', '')}"]
    if e.get("attachment_text"):
        parts.append(f"Attachment:\n{e['attachment_text']}")
    return "\n".join(parts)


def load_emails(path: Path) -> list[Evidence]:
    """emails.json -> Evidence. text = subject + body + attachment_text (labelled)."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    out = [
        Evidence(id=f"email_{i:03d}", source="email", sender=e.get("from", ""), timestamp=e.get("date"), text=_email_text(e))
        for i, e in enumerate(rows, start=1)
    ]
    print(f"[ingest] email: {len(out)} from {path.name}")
    return out


def _fy_end(page_text: str) -> str | None:
    """'Financial Year: 2024-25' -> '2025-03-31' (AIS rows carry no date of their own)."""
    m = FY_RE.search(page_text or "")
    return date(int(m.group(1)) + 1, 3, 31).isoformat() if m else None


def load_ais(path: Path) -> list[Evidence]:
    """ais.pdf -> one Evidence per data row, using pdfplumber's extract_tables()."""
    out: list[Evidence] = []
    with pdfplumber.open(path) as pdf:
        fy_end = None
        for page in pdf.pages:
            fy_end = _fy_end(page.extract_text()) or fy_end
            for table in page.extract_tables():
                for row in table[1:]:                        # table[0] is the header row
                    cells = [(c or "").strip() for c in row]
                    if not any(cells):
                        continue
                    out.append(Evidence(
                        id=f"ais_{len(out) + 1:02d}", source="ais", sender="AIS",
                        timestamp=fy_end, text=" | ".join(cells),
                    ))
    print(f"[ingest] ais: {len(out)} rows from {path.name} (dated {fy_end})")
    return out


def load_photos(folder: Path) -> list[Evidence]:
    """Each .png/.jpg -> Evidence(source='photo', path=..., text='')."""
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in PHOTO_SUFFIXES) if folder.is_dir() else []
    out = [Evidence(id=f"photo_{p.stem}", source="photo", sender=p.name, path=str(p)) for p in files]
    print(f"[ingest] photo: {len(out)} from {folder}")
    return out


def load_case(case_dir: str | Path, progress: Progress | None = None) -> list[Evidence]:
    """All four loaders, concatenated in the order sms, email, ais, photo.
    progress(stage, done, total), if given, is called once per source as "ingest:<source>"."""
    d = Path(case_dir)
    loaders = (("sms", lambda: load_sms(d / "sms.xml")), ("email", lambda: load_emails(d / "emails.json")),
               ("ais", lambda: load_ais(d / "ais.pdf")), ("photo", lambda: load_photos(d / "photos")))
    evidence: list[Evidence] = []
    for source, load in loaders:
        items = load()
        evidence += items
        if progress:
            progress(f"ingest:{source}", len(items), len(items))
    return evidence
