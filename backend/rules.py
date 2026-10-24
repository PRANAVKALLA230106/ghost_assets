"""Role B, step B1. Status and claim path from rules.yaml. No LLM.

years_inactive = (case date - asset.last_activity) in years.
bank_total = sum of est_value of all no-nominee bank assets at the same institution
(the simplified-procedure threshold is per bank, not per account).
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

from models import Asset, Claim, ClaimDocument

RULES_PATH = Path(__file__).parent / "rules.yaml"
BANK_TYPES = {"savings_account", "fixed_deposit"}


@lru_cache(maxsize=1)
def load_rules() -> dict[str, Any]:
    return yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))


def years_inactive(asset: Asset, as_of: date) -> Optional[float]:
    if not asset.last_activity:
        return None
    last = date.fromisoformat(asset.last_activity[:10])
    return (as_of - last).days / 365.25


def bank_total(asset: Asset, all_assets: list[Asset]) -> float:
    """Sum of est_value over no-nominee bank assets at this asset's institution (this asset included)."""
    pool = {a.id: a for a in all_assets}
    pool[asset.id] = asset
    return sum(a.est_value or 0.0 for a in pool.values()
               if a.institution == asset.institution and a.asset_type in BANK_TYPES and a.nominee == "no")


def yaml_word(value: Any) -> Any:
    """YAML 1.1 reads unquoted yes/no as booleans; map them back to the nominee words."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return value


def matches(cond: dict[str, Any], facts: dict[str, Any]) -> bool:
    """True if every key in cond holds. List values mean 'fact is one of'; _gte/_lt compare numbers."""
    for key, want in cond.items():
        if key.endswith("_gte"):
            got = facts.get(key[:-4])
            if got is None or got < want:
                return False
        elif key.endswith("_lt"):
            got = facts.get(key[:-3])
            if got is None or got >= want:
                return False
        else:
            options = [yaml_word(w) for w in (want if isinstance(want, list) else [want])]
            if facts.get(key) not in options:
                return False
    return True


def first_match(rules: list[dict[str, Any]], facts: dict[str, Any]) -> Any:
    for rule in rules:
        if "else" in rule:
            return rule["else"]
        if matches(rule["if"], facts):
            return rule["then"]
    return None


def apply_status(asset: Asset, as_of: date) -> Asset:
    years = years_inactive(asset, as_of)
    if years is None:
        status = "unknown"
    else:
        facts = {"asset_type": asset.asset_type, "years_inactive": years}
        status = first_match(load_rules()["status"], facts) or "unknown"
    print(f"[rules] {asset.id} {asset.asset_type} years_inactive={years if years is None else round(years, 1)}"
          f" -> {status}")
    return asset.model_copy(update={"status": status})


def claim_for(asset: Asset, all_assets: list[Asset], documents_have: list[str]) -> Claim:
    facts = {"asset_type": asset.asset_type, "status": asset.status, "nominee": asset.nominee,
             "bank_total": bank_total(asset, all_assets)}
    then = first_match(load_rules()["claim_paths"], facts)
    have = set(documents_have)
    claim = Claim(
        asset_id=asset.id,
        path=then["path"],
        where=then["where"],
        documents=[ClaimDocument(name=d, have=d in have) for d in then.get("docs", [])],
        deadline_note=then.get("deadline"),
    )
    print(f"[rules] {asset.id} status={asset.status} nominee={asset.nominee}"
          f" bank_total={facts['bank_total']:.0f} -> {claim.path}")
    return claim
