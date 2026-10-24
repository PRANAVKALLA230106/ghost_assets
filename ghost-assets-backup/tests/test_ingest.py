from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ingest import load_case

CASE_DIR = Path(__file__).resolve().parents[2] / "data" / "ramesh"
ID_FORMAT = {"sms": r"sms_\d{4}", "email": r"email_\d{3}", "ais": r"ais_\d{2}", "photo": r"photo_\w+"}


@pytest.fixture(scope="module")
def evidence():
    return load_case(CASE_DIR)


@pytest.fixture(scope="module")
def truth():
    return json.loads((CASE_DIR / "ground_truth.json").read_text(encoding="utf-8"))


def test_counts_match_ground_truth(evidence, truth):
    counts = {s: sum(1 for e in evidence if e.source == s) for s in ("sms", "email", "ais", "photo")}
    want = truth["counts"]
    assert counts == {"sms": want["sms"], "email": want["emails"], "ais": want["ais_rows"], "photo": want["photos"]}


def test_id_format(evidence):
    for e in evidence:
        assert re.fullmatch(ID_FORMAT[e.source], e.id), e.id


def test_ids_unique_and_sequential(evidence):
    assert len({e.id for e in evidence}) == len(evidence)
    sms = [e.id for e in evidence if e.source == "sms"]
    assert sms[:2] == ["sms_0001", "sms_0002"] and sms[-1] == f"sms_{len(sms):04d}"
    assert [e.id for e in evidence if e.source == "ais"] == ["ais_01", "ais_02", "ais_03", "ais_04"]


def test_every_key_evidence_id_exists(evidence, truth):
    ids = {e.id for e in evidence}
    for asset in truth["assets"]:
        assert set(asset["key_evidence"]) <= ids, asset["id"]


def test_ais_rows_exclude_header_and_carry_fy_end(evidence):
    ais = [e for e in evidence if e.source == "ais"]
    assert not any("Information Code" in e.text for e in ais)
    assert all(e.timestamp == "2025-03-31" for e in ais)


def test_photos_have_path_and_no_text(evidence):
    photos = [e for e in evidence if e.source == "photo"]
    assert {e.id for e in photos} == {"photo_passbook", "photo_policy_bond"}
    assert all(e.path and e.text == "" for e in photos)
