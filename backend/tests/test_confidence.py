"""The confidence score is explainable and rewards independent, official proof."""
from datetime import date

from confidence import explain
from models import Asset, Clue, Evidence

AS_OF = date(2026, 10, 24)


def _ev(i, src, ts="2026-01-05T10:00:00"):
    return Evidence(id=i, source=src, sender="x", timestamp=ts, text="t")


def _clue(i, ev, ident="XX4521"):
    return Clue(id=i, evidence_id=ev, institution_raw="Canara", asset_type="fixed_deposit", identifier=ident,
                amount_kind="unknown", quote="q")


def test_three_sources_with_tax_record_is_high():
    evs = {e.id: e for e in [_ev("sms_0001", "sms"), _ev("email_001", "email"), _ev("ais_01", "ais")]}
    clues = [_clue("c1", "sms_0001"), _clue("c2", "email_001"), _clue("c3", "ais_01")]
    a = Asset(id="as_01", institution="Canara Bank", asset_type="fixed_deposit", identifier="XX4521",
              last_activity="2026-01-05", clue_ids=["c1", "c2", "c3"])
    d = explain(a, clues, evs, AS_OF)
    assert d["level"] == "High" and d["sources"] == {"sms": 1, "email": 1, "ais": 1}
    assert {f["key"] for f in d["factors"]} == {"identifier", "sources", "official", "repeated", "alive"}
    assert sum(f["max"] for f in d["factors"]) == 100


def test_portal_record_explains_an_old_silent_account():
    evs = {"photo_passbook": _ev("photo_passbook", "photo", "2013-09-30T00:00:00")}
    clues = [_clue("c1", "photo_passbook", "XXXXXXX3307")]
    a = Asset(id="as_07", institution="State Bank of India", asset_type="savings_account", identifier="XXXXXXX3307",
              last_activity="2013-09-30", status="transferred_dea", clue_ids=["c1"])
    before = explain(a, clues, evs, AS_OF)
    after = explain(a, clues, evs, AS_OF, portal_hit={"portal": "UDGAM"})
    assert before["score"] <= 0.5 and after["level"] == "High"
    assert after["sources"]["portal"] == 1
