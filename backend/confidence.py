"""How sure are we that an asset is real? An explainable 0-100 score. No LLM.

Every clue that reaches this point already passed the grounding check (its quote, identifier and amount
were found word-for-word in the original message), so the score measures how much independent proof
backs the asset, not whether the AI made it up. Five factors, each with a plain-English reason:

  Account number       25  a number with 4+ digits ties the evidence to one specific account
  Independent sources  30  SMS, email, tax statement, photo, government portal: 10 points each, max 3
  Official record      20  government portal (RBI UDGAM / IEPF) or Income Tax AIS = 20, family = 20,
                           photo of an original document = 12
  Repeated evidence    10  5+ separate messages = 10, 2-4 = 6, 1 = 3
  Still alive          15  activity in the last 2 years = 15; long silence explained by a portal
                           record (money moved to RBI/IEPF) = 15; otherwise fades to 0 at 10 years
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from models import Asset, Clue, Evidence

SOURCE_LABEL = {"sms": "SMS", "email": "Email", "ais": "Tax statement (AIS)", "photo": "Photo", "portal": "Govt portal"}
PORTAL_LABEL = {"UDGAM": "RBI UDGAM record", "IEPF": "IEPF Authority record", "BIMA_BHAROSA": "Bima Bharosa record"}
SOURCE_ORDER = ["sms", "email", "ais", "photo", "portal"]


def _digits4(identifier: Optional[str]) -> bool:
    return len(re.sub(r"\D", "", identifier or "")) >= 4


def _factor(key: str, label: str, points: float, max_points: int, detail: str) -> dict:
    return {"key": key, "label": label, "points": round(points, 1), "max": max_points, "detail": detail}


def explain(asset: Asset, clues: list[Clue], ev_by_id: dict[str, Evidence], as_of: date,
            portal_hit: Optional[dict] = None) -> dict:
    """-> {score (0..1), level, summary, factors[], sources{type: count}, evidence_count, verified_quotes}"""
    ids = set(asset.clue_ids)
    own = [c for c in clues if c.id in ids]
    sources: dict[str, int] = {}
    for c in own:
        ev = ev_by_id.get(c.evidence_id)
        src = ev.source if ev else c.evidence_id.split("_")[0]
        sources[src] = sources.get(src, 0) + 1
    if portal_hit:
        sources["portal"] = 1
    evidence_items = len({c.evidence_id for c in own}) + (1 if portal_hit else 0)

    factors = []
    # 1. account number
    if _digits4(asset.identifier):
        n = sum(1 for c in own if c.identifier and re.sub(r"\D", "", c.identifier)[-4:] == re.sub(r"\D", "", asset.identifier)[-4:])
        where = f" in {n} place{'s' if n != 1 else ''}" if n else ""
        factors.append(_factor("identifier", "Account number", 25, 25, f"{asset.identifier} appears{where}"))
    elif asset.identifier:
        factors.append(_factor("identifier", "Account number", 12, 25, f"Partial number only ({asset.identifier})"))
    else:
        factors.append(_factor("identifier", "Account number", 0, 25, "No account or policy number found"))

    # 2. independent sources
    kinds = [s for s in SOURCE_ORDER if s in sources]
    factors.append(_factor("sources", "Independent sources", min(len(kinds), 3) * 10, 30,
                           f"{len(kinds)} source{'s' if len(kinds) != 1 else ''}: " + ", ".join(SOURCE_LABEL[k] for k in kinds)
                           if kinds else "No sources"))

    # 3. official record
    if portal_hit:
        official = (20, PORTAL_LABEL.get(portal_hit.get("portal", ""), "Government portal record") + " matches")
    elif "ais" in sources:
        official = (20, "Listed in the Income Tax AIS (reported by the institution itself)")
    elif asset.known_to_family:
        official = (20, "The family confirmed this asset")
    elif "photo" in sources:
        official = (12, "Photo of an original document (passbook / policy bond)")
    else:
        official = (0, "No official record yet")
    factors.append(_factor("official", "Official record", official[0], 20, official[1]))

    # 4. repeated evidence
    rep = 10 if evidence_items >= 5 else 6 if evidence_items >= 2 else 3 if evidence_items else 0
    factors.append(_factor("repeated", "Repeated evidence", rep, 10,
                           f"{evidence_items} separate piece{'s' if evidence_items != 1 else ''} of evidence"))

    # 5. still alive (or silence explained)
    last = date.fromisoformat(asset.last_activity[:10]) if asset.last_activity else None
    years = (as_of - last).days / 365.25 if last else None
    moved = asset.status in ("transferred_dea", "transferred_iepf") and portal_hit
    if moved:
        alive = (15, f"Silent since {last.year if last else 'long ago'}, explained: the money was moved to "
                     f"{'the RBI DEA fund' if asset.status == 'transferred_dea' else 'IEPF'}")
    elif years is None:
        alive = (0, "No dated activity")
    elif years <= 2:
        alive = (15, f"Last activity {last:%b %Y}")
    else:
        alive = (max(0.0, 15 * (1 - (years - 2) / 8)), f"Last activity {last:%b %Y} ({years:.0f} years ago)")
    factors.append(_factor("alive", "Still alive", alive[0], 15, alive[1]))

    total = sum(f["points"] for f in factors)
    score = round(total / 100, 2)
    level = "High" if score >= 0.8 else "Medium" if score >= 0.5 else "Low"
    strong = [f["detail"] for f in factors if f["points"] >= 0.75 * f["max"]]
    weak = [f["label"].lower() for f in factors if f["points"] < 0.5 * f["max"]]
    summary = "; ".join(strong[:2]) if strong else "Weak evidence"
    if weak:
        summary += f". Weaker on: {', '.join(weak)}"
    return {"score": score, "level": level, "summary": summary, "factors": factors,
            "sources": {k: sources[k] for k in SOURCE_ORDER if k in sources},
            "evidence_count": evidence_items, "verified_quotes": len(own)}
