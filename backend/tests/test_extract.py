from __future__ import annotations

import pytest

from extract import clean_fields, ground, normalise_amount
from models import Clue, Evidence


@pytest.mark.parametrize("text, want", [
    ("Rs.2,00,000", 200000.0),
    ("INR 200000.00", 200000.0),
    ("2,00,000/-", 200000.0),
    ("Rs 5000", 5000.0),
    ("Rs32,500.00", 32500.0),
    ("Rs.1,72,500.00", 172500.0),
    ("no number here", None),
])
def test_normalise_amount(text, want):
    assert normalise_amount(text) == want


EV = Evidence(id="sms_0001", source="sms", sender="AD-CANBNK",
              text="Dear Customer, your FD A/c XX4521 of Rs.2,00,000 has been renewed for 36 months.")


def clue(**kw) -> Clue:
    base = dict(id="cl_0001", evidence_id="sms_0001", institution_raw="CANBNK", asset_type="fixed_deposit",
                identifier="XX4521", amount=200000.0, amount_kind="principal",
                quote="your FD A/c XX4521 of Rs.2,00,000 has been renewed")
    return Clue(**{**base, **kw})


def test_ground_accepts_supported_clue():
    assert ground(clue(), EV) == (True, "")


def test_ground_quote_is_case_and_whitespace_insensitive():
    assert ground(clue(quote="YOUR FD   a/c xx4521\nof Rs.2,00,000"), EV)[0]


def test_ground_rejects_paraphrased_quote():
    ok, reason = ground(clue(quote="FD XX4521 renewed for Rs 2 lakh"), EV)
    assert not ok and "quote" in reason


def test_ground_rejects_wrong_identifier():
    ok, reason = ground(clue(identifier="XX9999"), EV)
    assert not ok and "identifier" in reason


def test_ground_rejects_invented_amount():
    ok, reason = ground(clue(amount=238000.0), EV)
    assert not ok and "amount" in reason


def test_ground_allows_missing_identifier_and_amount():
    assert ground(clue(identifier=None, amount=None), EV)[0]


def test_ground_rejects_quote_from_another_message():
    c = clue(quote="Your SIP of Rs.5,000.00 in Kaveri Flexi Cap Fund - Growth is processed.", amount=None)
    assert not ground(c, EV)[0]


def test_clean_fields_drops_share_count_used_as_rupees():
    ev = Evidence(id="email_002", source="email", sender="x", text="Folio No.: GT0042\nHolding: 400 equity shares of Rs 10 each")
    c = clue(evidence_id="email_002", asset_type="shares", identifier="GT0042", amount=400, amount_kind="market_value",
             quote="Holding: 400 equity shares")
    assert clean_fields(c, ev) and c.amount is None and c.amount_kind == "unknown"
    assert ground(c, ev)[0]


def test_clean_fields_keeps_rupee_amounts():
    for text, amount in [("Rs 5000 debited", 5000), ("INR 12450.00 debited", 12450), ("value 2,00,000/-", 200000),
                         ("CANARA BANK | 18,200.00", 18200)]:
        ev = Evidence(id="sms_0002", source="sms", sender="x", text=text)
        c = clue(evidence_id="sms_0002", identifier=None, amount=amount, quote=text)
        assert clean_fields(c, ev) == [] and c.amount == amount


def test_clean_fields_drops_invented_nominee():
    c = clue(nominee="not registered")
    assert clean_fields(c, EV) and c.nominee is None


def test_clean_fields_keeps_stated_nominee():
    ev = Evidence(id="email_003", source="email", sender="x", text="Nomination registered. Nominee: S KUMAR (Wife) for XX4521")
    c = clue(evidence_id="email_003", amount=None, nominee="S KUMAR (Wife)", quote="Nominee: S KUMAR (Wife)")
    assert clean_fields(c, ev) == [] and c.nominee == "S KUMAR (Wife)"


def test_ground_matches_amount_in_other_format():
    ev = Evidence(id="ais_02", source="ais", sender="AIS", text="2 | SFT-016(TD) | Interest from deposit | CANARA BANK | 18,200.00")
    c = clue(evidence_id="ais_02", identifier=None, amount=18200, amount_kind="interest", quote="CANARA BANK | 18,200.00")
    assert ground(c, ev)[0]
