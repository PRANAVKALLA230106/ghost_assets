"""Role A, step A2. Cheap regex filter so only financial evidence reaches the LLM.

Keep: KEEP regex matches and DROP does not, OR the sender is a known financial sender.
Always keep: emails with attachment_text, every AIS row, every photo.
Never add rules that mention Ramesh's specific account numbers or amounts.
"""
from __future__ import annotations

import re
from typing import Callable

from models import Evidence

Progress = Callable[[str, int, int], None]   # (stage, done, total)
PROGRESS_EVERY = 300

DROP = re.compile(r"\b(OTP|one[- ]time password|verification code|offer|cashback|sale|delivered|"
                  r"out for delivery|order #|coupon|data quota)\b", re.I)
KEEP = re.compile(r"\b(a/c|account|credited|debited|FD|deposit|matur\w*|premium|policy|folio|SIP|NAV|"
                  r"units|dividends?|interest|PF|UAN|nominee|shareholder|shares)\b", re.I)
# DLT header codes of banks, insurers and fund houses (the part after "XX-").
FINANCIAL_SENDERS: set[str] = {
    # seen in the data
    "SBIINB", "CANBNK", "LICIND", "SURKSH", "KAVRMF",
    # other common Indian banks / insurers / depositories
    "SBIPSG", "SBMSMS", "HDFCBK", "ICICIB", "AXISBK", "KOTAKB", "PNBSMS", "BOBTXN", "UNIONB", "IDBIBK",
    "INDBNK", "CBSSBI", "IOBCHN", "UCOBNK", "YESBNK", "IDFCFB", "FEDBNK", "CANBKS", "EPFOHO", "IPPBNK",
    "CDSLEV", "NSDLCA", "CAMSMF", "KFINTK",
}
ATTACHMENT_LABEL = "\nAttachment:\n"   # set by ingest._email_text when an email has attachment_text


def sender_code(sender: str) -> str:
    """'VM-SBIINB' -> 'SBIINB'; anything without a prefix is returned upper-cased."""
    return sender.split("-", 1)[-1].upper()


def is_financial(ev: Evidence) -> bool:
    if ev.source in ("ais", "photo"):
        return True
    if ev.source == "email" and ATTACHMENT_LABEL in ev.text:
        return True
    if ev.source == "sms" and sender_code(ev.sender) in FINANCIAL_SENDERS:
        return True
    return bool(KEEP.search(ev.text)) and not DROP.search(ev.text)


def triage(evidence: list[Evidence], progress: Progress | None = None) -> list[Evidence]:
    """Set is_financial on every item and return the same list.
    progress(stage, done, total), if given, gets "triage" every PROGRESS_EVERY items, then
    "triage_done" with done = the number kept as financial."""
    total = len(evidence)
    for n, ev in enumerate(evidence, start=1):
        ev.is_financial = is_financial(ev)
        if progress and (n % PROGRESS_EVERY == 0 or n == total):
            progress("triage", n, total)
    kept = sum(e.is_financial for e in evidence)
    if progress:
        progress("triage_done", kept, total)
    print(f"[triage] kept {kept} of {total} as financial")
    return evidence
