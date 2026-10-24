"""Role A, step A4. Clues -> Assets. No LLM.

1. normalise_institution: alias dict, email sender domains, then rapidfuzz against INSTITUTIONS (>= 85).
2. Effective type: a savings/FD clue at a non-bank (insurer, fund house, company...) takes that
   institution's natural type. Block by (institution, effective type).
3. Link two clues when
   a. in the same block, identifiers share the last 4 digits; or both have no identifier and
      form the same recurring amount (a SIP);
   b. at the same bank, a clue's identifier shares the last 4 digits with a savings/FD clue there
      (a pension credit typed as provident_fund is still that account);
   c. for policies, funds, shares and PF (not deposits), across institutions, the asset type and
      the FULL masked identifier match (same digits, same length): a bank's debit SMS naming
      "LIC Policy XXXXX5271" joins the LIC policy, but a policy ending 5271 never joins an account
      ending 5271.
   A component with no identifier then attaches to the identified component in its block whose
   activity dates are closest to its own (it stays separate only if the block has none).
4. networkx connected components -> one Asset per component. Its institution is the most common
   non-bank institution among its clues (else the most common), its type the most common type.
5. est_value priority: market_value > balance (latest) > maturity_value > sum_assured > principal;
   a deposit account with no balance clue takes the newest "Avl Bal Rs ..." in its own evidence text;
   SIP with no market value: instalment x count as a floor. Record value_basis.
6. confidence: confidence.explain (account number, independent sources, official record, repetition, recency).
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date
from typing import Callable

import networkx as nx
from rapidfuzz import fuzz, process, utils

from confidence import explain as explain_confidence
from models import Asset, Clue, Evidence

ALIASES: dict[str, str] = {
    "SBI": "State Bank of India", "SBIINB": "State Bank of India",
    "CANBNK": "Canara Bank", "LICIND": "LIC", "LIC OF INDIA": "LIC",
    "LIFE INSURANCE CORPORATION OF INDIA": "LIC", "PNBSMS": "Punjab National Bank", "HDFCBK": "HDFC Bank",
    "ICICIB": "ICICI Bank", "AXISBK": "Axis Bank", "KOTAKB": "Kotak Mahindra Bank", "BOBTXN": "Bank of Baroda",
    "EPFOHO": "EPFO", "SURKSH": "Suraksha Life Insurance", "KAVRMF": "Kaveri Mutual Fund",
}
INSTITUTIONS: list[str] = [
    "State Bank of India", "Canara Bank", "Punjab National Bank", "Bank of Baroda", "Union Bank of India",
    "Bank of India", "Indian Bank", "Central Bank of India", "Indian Overseas Bank", "UCO Bank",
    "Bank of Maharashtra", "Punjab & Sind Bank", "HDFC Bank", "ICICI Bank", "Axis Bank", "Kotak Mahindra Bank",
    "IndusInd Bank", "Yes Bank", "IDFC First Bank", "Federal Bank", "Karnataka Bank", "South Indian Bank",
    "India Post", "LIC", "Suraksha Life Insurance", "Kaveri Mutual Fund", "Ganga Tech Ltd", "EPFO",
]
# Institutions whose category is not obvious from the name; the rest are classified by keyword.
CATEGORIES: dict[str, str] = {"LIC": "insurer", "EPFO": "epfo", "India Post": "post_office"}
NATURAL_TYPE = {"insurer": "life_insurance", "fund": "mutual_fund", "company": "shares",
                "epfo": "provident_fund", "post_office": "post_office"}
DEPOSIT_TYPES = {"savings_account", "fixed_deposit"}
FUZZY_MIN = 85
# Common abbreviations in sender names and statements, expanded before fuzzy matching.
EXPANSIONS = {"MF": "Mutual Fund", "BK": "Bank", "BNK": "Bank", "LTD": "Ltd", "INS": "Insurance"}
VALUE_PRIORITY = [("market_value", "market value"), ("balance", "latest balance"),
                  ("maturity_value", "maturity value"), ("sum_assured", "sum assured"), ("principal", "principal")]
BALANCE_RE = re.compile(r"\b(?:avl\.?\s*bal(?:ance)?|available\s+balance|closing\s+balance|bal(?:ance)?)"
                        r"\s*[:.\-]?\s*(?:rs\.?|inr|₹)\s*(\d[\d,]*(?:\.\d+)?)", re.I)


# ---- institutions ------------------------------------------------------------------------------

def _clean(raw: str) -> str:
    s = re.sub(r"\(.*?\)", " ", raw or "")                 # 'STATE BANK OF INDIA (A/C XX8812)'
    s = re.sub(r"^[A-Z]{2}-(?=[A-Z0-9]{4,})", "", s.strip(), flags=re.I)   # DLT prefix 'VM-'
    s = re.sub(r"[^\w&\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _squashed(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _from_email(raw: str) -> str | None:
    """'termdeposits@canarabank.example' -> 'Canara Bank' (domain label vs names without spaces)."""
    label = _squashed(raw.split("@", 1)[1].split(".")[0])
    if label.upper() in ALIASES:
        return ALIASES[label.upper()]
    for inst in INSTITUTIONS:
        key = _squashed(inst)
        if key == label or (len(label) >= 5 and key.startswith(label)) or fuzz.ratio(label, key) >= FUZZY_MIN:
            return inst
    return None


def normalise_institution(raw: str) -> str:
    if raw and "@" in raw:
        found = _from_email(raw)
        if found:
            return found
        raw = raw.split("@", 1)[1].split(".")[0]
    cleaned = _clean(raw)
    if not cleaned:
        return raw or "Unknown"
    if cleaned.upper() in ALIASES:
        return ALIASES[cleaned.upper()]
    expanded = " ".join(EXPANSIONS.get(w.upper(), w) for w in cleaned.split())
    first = utils.default_process(expanded).split()[0] if utils.default_process(expanded) else ""
    for name, score, _ in process.extract(expanded, INSTITUTIONS, scorer=fuzz.WRatio, processor=utils.default_process, limit=5):
        # a shared generic word ('Life', 'Bank') is not enough: 'Max Life' must not become 'Suraksha Life Insurance'
        if score >= FUZZY_MIN and fuzz.ratio(first, utils.default_process(name).split()[0]) >= 80:
            return name
    return cleaned.title()


def category(institution: str) -> str:
    if institution in CATEGORIES:
        return CATEGORIES[institution]
    name = institution.lower()
    if "bank" in name:
        return "bank"
    if "insurance" in name or "life" in name:
        return "insurer"
    if "mutual fund" in name or name.endswith(" amc"):
        return "fund"
    if re.search(r"\b(ltd|limited)\b", name):
        return "company"
    return "unknown"


def _effective_type(c: Clue) -> str:
    natural = NATURAL_TYPE.get(category(c.institution))
    return natural if c.asset_type in DEPOSIT_TYPES and natural else c.asset_type


# ---- helpers ---------------------------------------------------------------------------------

def _digits4(identifier: str | None) -> str | None:
    d = re.sub(r"\D", "", identifier or "")
    return d[-4:] if len(d) >= 4 else None


def _full_identifier(identifier: str | None) -> str | None:
    """'XXXXX5271' / 'xxxxx-5271' -> 'XXXXX5271'; None unless it carries at least 4 digits."""
    if not _digits4(identifier):
        return None
    return re.sub(r"[^A-Z0-9]", "", identifier.upper())


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _clue_date(c: Clue, ev_dates: dict[str, date | None]) -> date | None:
    return _parse_date(c.date) or ev_dates.get(c.evidence_id)


def _nominee(clues: list[Clue], ev_dates) -> str:
    stated = [(c, _clue_date(c, ev_dates) or date.min) for c in clues if c.nominee]
    if not stated:
        return "unknown"
    latest = max(stated, key=lambda t: t[1])[0].nominee.strip().lower()
    return "no" if re.search(r"not registered|^no(ne)?$|nil|not available", latest) else "yes"


def _text_balance(clues: list[Clue], ev_by_id: dict[str, Evidence]) -> float | None:
    """Newest 'Avl Bal Rs ...' figure in the evidence behind these clues (ordered by timestamp)."""
    found = []
    for eid in {c.evidence_id for c in clues}:
        ev = ev_by_id.get(eid)
        if ev is None:
            continue
        for m in BALANCE_RE.finditer(ev.text):
            found.append((ev.timestamp or "", m.start(), float(m.group(1).replace(",", ""))))
    return max(found)[2] if found else None


def _value(clues: list[Clue], asset_type: str, ev_dates, ev_by_id) -> tuple[float | None, str | None]:
    for kind, basis in VALUE_PRIORITY:
        hits = [c for c in clues if c.amount_kind == kind and c.amount is not None]
        if hits:
            latest = max(hits, key=lambda c: _clue_date(c, ev_dates) or date.min)
            return latest.amount, basis
        if kind == "balance" and asset_type in DEPOSIT_TYPES:
            bal = _text_balance(clues, ev_by_id)
            if bal is not None:
                return bal, "latest balance (message text)"
    sips = [c for c in clues if c.amount_kind == "sip_instalment" and c.amount is not None]
    if sips:
        amount = Counter(c.amount for c in sips).most_common(1)[0][0]
        n = len({_clue_date(c, ev_dates) for c in sips})
        return amount * n, f"SIP instalments x {n} (floor)"
    return None, None


def _chain(g: nx.Graph, ids: list[str]) -> None:
    for a, b in zip(ids, ids[1:]):
        g.add_edge(a, b)


# ---- linking -----------------------------------------------------------------------------------

def _link_block(g: nx.Graph, block: list[Clue]) -> None:
    """Rule 3a."""
    by_digits: dict[str, list[str]] = {}
    sip_groups: dict[float, list[str]] = {}
    for c in block:
        d = _digits4(c.identifier)
        if d:
            by_digits.setdefault(d, []).append(c.id)
        elif c.amount_kind == "sip_instalment" and c.amount is not None:
            sip_groups.setdefault(c.amount, []).append(c.id)
    for group in [*by_digits.values(), *(s for s in sip_groups.values() if len(s) >= 2)]:
        _chain(g, group)


def _link_bank_accounts(g: nx.Graph, clues: list[Clue], ctype: dict[str, str]) -> None:
    """Rule 3b: at the same bank, any clue whose last 4 digits match a savings/FD clue joins it."""
    accounts: dict[tuple[str, str], str] = {}
    for c in clues:
        d = _digits4(c.identifier)
        if d and ctype[c.id] in DEPOSIT_TYPES and category(c.institution) == "bank":
            accounts.setdefault((c.institution, d), c.id)
    for c in clues:
        d = _digits4(c.identifier)
        if d and ctype[c.id] not in DEPOSIT_TYPES and (c.institution, d) in accounts:
            g.add_edge(c.id, accounts[(c.institution, d)])


def _link_across_institutions(g: nx.Graph, clues: list[Clue], ctype: dict[str, str]) -> None:
    """Rule 3c: same non-deposit type and same full masked identifier, any institution."""
    groups: dict[tuple[str, str], list[str]] = {}
    for c in clues:
        full = _full_identifier(c.identifier)
        if full and ctype[c.id] not in DEPOSIT_TYPES:
            groups.setdefault((ctype[c.id], full), []).append(c.id)
    for ids in groups.values():
        _chain(g, ids)


def _attach_orphans(g: nx.Graph, block: list[Clue], ev_dates) -> None:
    """Join identifier-less components to the identified component whose dates are nearest."""
    by_id = {c.id: c for c in block}
    comps = [list(comp) for comp in nx.connected_components(g.subgraph(by_id))]
    identified = [comp for comp in comps if any(_digits4(by_id[i].identifier) for i in comp)]
    if not identified:
        return

    def dates(comp):
        return [d for d in (_clue_date(by_id[i], ev_dates) for i in comp) if d]

    for comp in comps:
        if comp in identified:
            continue
        mine = dates(comp)

        def distance(target):
            theirs = dates(target)
            if not mine or not theirs:
                return float("inf")
            return min(abs((a - b).days) for a in mine for b in theirs)

        target = min(identified, key=lambda t: (distance(t), -len(t)))
        g.add_edge(comp[0], target[0])


# ---- main ------------------------------------------------------------------------------------

CODE_RE = re.compile(r"^[A-Za-z]{4,15}$")
WORD_RE = re.compile(r"[A-Za-z]+")


def _is_subsequence(code: str, text: str) -> bool:
    it = iter(text)
    return all(ch in it for ch in code)


def _expand_code(code: str, texts: list[str]) -> str | None:
    """'STRHLT' + 'premium for STAR HEALTH policy' -> 'Star Health'. Indian SMS sender codes abbreviate
    the institution by dropping letters, so the full name is the shortest 1-4 word phrase in the asset's
    own messages whose letters contain the code in order, and whose word initials also appear in order."""
    code = code.upper()
    best: tuple[int, int, str] | None = None
    for text in texts:
        words = WORD_RE.findall(text or "")
        for i, w in enumerate(words):
            if w[0].upper() != code[0]:
                continue
            for j in range(i + 1, min(i + 4, len(words)) + 1):
                span = words[i:j]
                joined = "".join(span).upper()
                if (joined == code and len(span) < 2) or not _is_subsequence(code, joined):
                    continue
                if not _is_subsequence("".join(x[0].upper() for x in span), code):
                    continue
                key = (len(span), len(joined), " ".join(span))
                if best is None or key < best:
                    best = key
                break
    if not best:
        return None
    phrase = " ".join(EXPANSIONS.get(w.upper(), w.title()) for w in best[2].split())
    return normalise_institution(phrase)


def _pick_institution(cs: list[Clue], ev_by_id: dict | None = None) -> str:
    non_bank = Counter(c.institution for c in cs if category(c.institution) != "bank")
    name = (non_bank or Counter(c.institution for c in cs)).most_common(1)[0][0]
    if name in INSTITUTIONS or not CODE_RE.match(name):
        return name
    texts = [c.quote for c in cs] + [ev_by_id[c.evidence_id].text for c in cs if ev_by_id and c.evidence_id in ev_by_id]
    return _expand_code(name, texts) or name


def build_assets(clues: list[Clue], evidence: list[Evidence] | None = None, as_of: date | None = None,
                 progress: Callable[[str, int, int], None] | None = None) -> list[Asset]:
    """evidence (optional) supplies timestamps, source types and text for clues that state no date.
    progress(stage, done, total), if given, is called with ("resolve", assets built, clues) at the end."""
    as_of = as_of or date.today()
    ev_by_id = {e.id: e for e in evidence or []}
    ev_dates = {e.id: _parse_date(e.timestamp) for e in evidence or []}

    for c in clues:
        c.institution = normalise_institution(c.institution_raw)
    ctype = {c.id: _effective_type(c) for c in clues}

    g = nx.Graph()
    g.add_nodes_from(c.id for c in clues)
    blocks: dict[tuple[str, str], list[Clue]] = {}
    for c in clues:
        blocks.setdefault((c.institution, ctype[c.id]), []).append(c)
    for block in blocks.values():
        _link_block(g, block)
    _link_bank_accounts(g, clues, ctype)
    _link_across_institutions(g, clues, ctype)
    for block in blocks.values():
        _attach_orphans(g, block, ev_dates)

    by_id = {c.id: c for c in clues}
    comps = sorted((sorted(comp) for comp in nx.connected_components(g)), key=lambda comp: comp[0])
    assets = []
    for n, comp in enumerate(comps, start=1):
        cs = [by_id[i] for i in comp]
        asset_type = Counter(ctype[c.id] for c in cs).most_common(1)[0][0]
        idents = Counter(c.identifier for c in cs if c.identifier and ctype[c.id] == asset_type)
        identifier = max(idents, key=lambda k: (idents[k], len(k))) if idents else None
        dates = [d for d in (_clue_date(c, ev_dates) for c in cs) if d]
        last = max(dates) if dates else None
        sources = {ev_by_id[c.evidence_id].source if c.evidence_id in ev_by_id else c.evidence_id.split("_")[0] for c in cs}
        value, basis = _value(cs, asset_type, ev_dates, ev_by_id)
        asset = Asset(
            id=f"as_{n:02d}", institution=_pick_institution(cs, ev_by_id), asset_type=asset_type, identifier=identifier,
            est_value=value, value_basis=basis,
            last_activity=last.isoformat() if last else None, nominee=_nominee(cs, ev_dates), clue_ids=comp,
        )
        asset.confidence = explain_confidence(asset, cs, ev_by_id, as_of)["score"]
        assets.append(asset)
    print(f"[resolve] {len(clues)} clues -> {len(assets)} assets")
    if progress:
        progress("resolve", len(assets), len(clues))
    return assets
