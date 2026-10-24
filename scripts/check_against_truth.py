"""Check pipeline output against data/<case>/ground_truth.json.

Usage (from the repo root):
  python scripts/check_against_truth.py triage out/evidence.json
  python scripts/check_against_truth.py assets out/assets.json
  python scripts/check_against_truth.py claims out/assets.json out/claims.json

triage  every planted key-evidence item must be present and marked is_financial
assets  each of the 7 true assets must appear exactly once, value within 5%, status right
claims  each matched asset's claim path must equal the expected one
Exit code 0 = pass, 1 = fail, so Claude Code can run it as a test.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_truth(case: str) -> dict:
    return json.loads((ROOT / "data" / case / "ground_truth.json").read_text(encoding="utf-8"))


def digits_suffix(identifier: str | None, n: int = 4) -> str | None:
    if not identifier:
        return None
    d = re.sub(r"\D", "", identifier)
    return d[-n:] if len(d) >= n else (d or None)


def check_triage(truth: dict, evidence_path: str) -> bool:
    evidence = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    by_id = {e["id"]: e for e in evidence}
    ok = True
    print(f"{'asset':<16}{'kept':>8}{'planted':>9}  missing (first 5)")
    for a in truth["assets"]:
        missing = [i for i in a["key_evidence"] if not by_id.get(i, {}).get("is_financial")]
        kept = len(a["key_evidence"]) - len(missing)
        print(f"{a['id']:<16}{kept:>8}{len(a['key_evidence']):>9}  {missing[:5]}")
        ok &= not missing
    n_fin = sum(1 for e in evidence if e.get("is_financial"))
    print(f"\nEvidence items: {len(evidence)}   marked financial: {n_fin}")
    for src, key in (("sms", "sms"), ("email", "emails")):
        got = sum(1 for e in evidence if e.get("source") == src)
        want = truth["counts"][key]
        if got != want:
            print(f"WARNING: {got} {src} items loaded, expected {want}")
            ok = False
    print("PASS: triage keeps every planted message" if ok else "FAIL: triage dropped planted evidence (see above)")
    return ok


def match(truth_assets: list[dict], out_assets: list[dict]):
    matches: dict[str, list[dict]] = {a["id"]: [] for a in truth_assets}
    unmatched = []
    for o in out_assets:
        hit = None
        for t in truth_assets:
            if o.get("asset_type") != t["asset_type"]:
                continue
            if digits_suffix(o.get("identifier")) and digits_suffix(o.get("identifier")) == digits_suffix(t["identifier"]):
                hit = t
                break
            if not digits_suffix(o.get("identifier")) and t["institution"].lower() in (o.get("institution") or "").lower():
                hit = t
        if hit:
            matches[hit["id"]].append(o)
        else:
            unmatched.append(o)
    return matches, unmatched


def check_assets(truth: dict, assets_path: str) -> bool:
    out = json.loads(Path(assets_path).read_text(encoding="utf-8"))
    matches, unmatched = match(truth["assets"], out)
    ok = True
    print(f"{'asset':<16}{'found':>7}{'value want':>13}{'value got':>12}{'status want':>19}{'status got':>19}")
    for t in truth["assets"]:
        ms = matches[t["id"]]
        if not ms:
            print(f"{t['id']:<16}{'NO':>7}{t['value']:>13,}{'-':>12}{t['expected_status']:>19}{'-':>19}")
            ok = False
            continue
        o = ms[0]
        v = o.get("est_value") or 0
        v_ok = abs(v - t["value"]) <= 0.05 * t["value"]
        if not v and t.get("value_source", "evidence") != "evidence":
            v_ok = True  # value comes from a portal lookup (step B2), not from the pipeline
        s = o.get("status", "unknown")
        s_ok = s in (t["expected_status"], "unknown")
        flag = "" if (v_ok and s_ok and len(ms) == 1) else "  <--"
        dup = f" x{len(ms)} (split!)" if len(ms) > 1 else ""
        print(f"{t['id']:<16}{'yes' + dup:>7}{t['value']:>13,}{int(v):>12,}{t['expected_status']:>19}{s:>19}{flag}")
        ok &= v_ok and s_ok and len(ms) == 1
    if unmatched:
        print(f"\nExtra assets not in the ground truth ({len(unmatched)}):")
        for o in unmatched:
            print(f"  {o.get('institution')} {o.get('asset_type')} {o.get('identifier')} value={o.get('est_value')}")
        ok = False
    total = sum((m[0].get("est_value") or 0) for m in matches.values() if m)
    print(f"\nTotal found: Rs {int(total):,}  (expected Rs {truth['total_value']:,})")
    print("PASS: asset map matches ground truth" if ok else "FAIL: see rows marked <-- and any extras")
    print("Note: status 'unknown' is accepted until rules.py runs.")
    return ok


def check_claims(truth: dict, assets_path: str, claims_path: str) -> bool:
    out = json.loads(Path(assets_path).read_text(encoding="utf-8"))
    claims = {c["asset_id"]: c for c in json.loads(Path(claims_path).read_text(encoding="utf-8"))}
    matches, _ = match(truth["assets"], out)
    ok = True
    for t in truth["assets"]:
        if not matches[t["id"]]:
            print(f"{t['id']:<16} asset not found")
            ok = False
            continue
        c = claims.get(matches[t["id"]][0]["id"])
        got = c["path"] if c else "-"
        good = got == t["expected_claim_path"]
        ok &= good
        print(f"{t['id']:<16} want {t['expected_claim_path']:<24} got {got:<24}{'' if good else '<--'}")
    print("PASS: claim paths correct" if ok else "FAIL: claim paths differ")
    return ok


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode", choices=["triage", "assets", "claims"])
    p.add_argument("paths", nargs="+")
    p.add_argument("--case", default="ramesh")
    a = p.parse_args()
    truth = load_truth(a.case)
    if a.mode == "triage":
        ok = check_triage(truth, a.paths[0])
    elif a.mode == "assets":
        ok = check_assets(truth, a.paths[0])
    else:
        ok = check_claims(truth, a.paths[0], a.paths[1])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
