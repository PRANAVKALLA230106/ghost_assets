"""Shared data contracts. COMPLETE - do not change without telling the whole team.

Every module, every SSE event and the frontend store are built on these shapes.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

AssetType = Literal[
    "savings_account", "fixed_deposit", "life_insurance", "mutual_fund",
    "shares", "provident_fund", "post_office", "other",
]
AmountKind = Literal[
    "balance", "principal", "maturity_value", "sum_assured", "premium",
    "sip_instalment", "dividend", "interest", "credit", "debit", "market_value", "unknown",
]
Status = Literal["active", "dormant", "transferred_dea", "transferred_iepf", "transferred_scwf", "unknown"]
Nominee = Literal["yes", "no", "unknown"]


class Evidence(BaseModel):
    """One raw item the family uploaded: an SMS, an email, an AIS row or a photo."""
    id: str                                   # sms_0001 | email_001 | ais_01 | photo_<stem>
    source: Literal["sms", "email", "ais", "photo"]
    sender: str                               # "VM-CANBNK", email from, "AIS", file name
    timestamp: Optional[str] = None           # ISO 8601
    text: str = ""                            # photos: empty until read by the vision model
    path: Optional[str] = None                # photos only: file path
    is_financial: bool = False


class Clue(BaseModel):
    """A grounded fact extracted from one Evidence item."""
    id: str                                   # cl_0001
    evidence_id: str
    institution_raw: str                      # exactly as written: "CANBNK", "Canara Bk"
    institution: Optional[str] = None         # canonical name, filled by resolve.py
    asset_type: AssetType
    identifier: Optional[str] = None          # "XX4521", folio, policy no. (masked digits kept)
    amount: Optional[float] = None
    amount_kind: AmountKind = "unknown"
    date: Optional[str] = None                # ISO date if stated
    nominee: Optional[str] = None             # name, "not registered", or None if not mentioned
    quote: str                                # exact substring of the evidence text


class Asset(BaseModel):
    """One real-world holding, built by clustering clues."""
    id: str                                   # as_01
    institution: str
    asset_type: AssetType
    identifier: Optional[str] = None
    est_value: Optional[float] = None
    value_basis: Optional[str] = None         # "latest balance", "sum assured", "portal record", ...
    confidence: float = 0.0                   # 0..1
    last_activity: Optional[str] = None       # ISO date of the newest clue
    status: Status = "unknown"
    nominee: Nominee = "unknown"
    known_to_family: bool = False
    clue_ids: list[str] = Field(default_factory=list)


class ClaimDocument(BaseModel):
    name: str
    have: bool = False


class Claim(BaseModel):
    asset_id: str
    path: str                                 # nominee | simplified_no_nominee | standard_succession |
                                              # dea_claim_via_bank | insurance_death_claim | transmission |
                                              # iepf_refund | epf_claim | needs_nominee_answer
    where: str                                # "SBI branch", "IEPF Authority (online)", "Insurer claims desk"
    documents: list[ClaimDocument] = Field(default_factory=list)
    deadline_note: Optional[str] = None


class Case(BaseModel):
    id: str
    deceased_name: str
    date_of_death: str                        # ISO date
    data_dir: str                             # e.g. data/ramesh
    documents_have: list[str] = Field(default_factory=list)   # e.g. ["death_certificate", "claimant_id"]
    known_assets: list[str] = Field(default_factory=list)     # free text the family already knows about


# ---- SSE events: {"type": <name>, "data": <payload>} ----------------------------------------
EventType = Literal["progress", "clue", "asset", "agent_step", "question", "claim", "done", "error"]


class Event(BaseModel):
    type: EventType
    data: dict
