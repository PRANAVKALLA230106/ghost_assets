from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from models import Asset
from rules import apply_status, claim_for

TRUTH = json.loads((Path(__file__).resolve().parents[2] / "data/ramesh/ground_truth.json").read_text(encoding="utf-8"))
AS_OF = date(2026, 10, 24)
LAST_ACTIVITY = {"sbi_3307": "2013-11-14", "gangatech": "2017-08-22"}


def truth_assets() -> list[Asset]:
    return [Asset(id=t["id"], institution=t["institution"], asset_type=t["asset_type"],
                  identifier=t["identifier"], est_value=t["value"], nominee=t["nominee"],
                  last_activity=LAST_ACTIVITY.get(t["id"], "2025-12-01"))
            for t in TRUTH["assets"]]


@pytest.mark.parametrize("truth", TRUTH["assets"], ids=lambda t: t["id"])
def test_ground_truth_status_and_path(truth):
    assets = [apply_status(a, AS_OF) for a in truth_assets()]
    asset = next(a for a in assets if a.id == truth["id"])
    assert asset.status == truth["expected_status"]
    assert claim_for(asset, assets, []).path == truth["expected_claim_path"]


def canara(**kw) -> Asset:
    base = dict(id="canara_4521", institution="Canara Bank", asset_type="fixed_deposit", identifier="XX4521",
                est_value=238000, nominee="no", last_activity="2025-12-01")
    return apply_status(Asset(**{**base, **kw}), AS_OF)


def test_unknown_nominee_needs_answer():
    asset = canara(nominee="unknown")
    claim = claim_for(asset, [asset], [])
    assert claim.path == "needs_nominee_answer"
    assert claim.documents == []


def test_bank_total_over_threshold_is_standard_succession():
    first = canara()
    assert claim_for(first, [first], []).path == "simplified_no_nominee"
    second = canara(id="canara_9900", identifier="XX9900", asset_type="savings_account", est_value=1300000)
    both = [first, second]
    assert claim_for(first, both, []).path == "standard_succession"
    assert claim_for(second, both, []).path == "standard_succession"


def test_documents_have_marked():
    asset = canara()
    claim = claim_for(asset, [asset], ["death_certificate"])
    have = {d.name: d.have for d in claim.documents}
    assert have["death_certificate"] is True
    assert have["claim_form"] is False
    assert claim.deadline_note and "15 calendar days" in claim.deadline_note
