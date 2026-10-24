"""Role B, step B5. python-docx claim pack. Fixed template text only - no LLM-written legal text.

Contents: cover letter (deceased, asset, identifier, claimant, claim path, where to submit),
document checklist (tick = have), evidence quotes with dates, deadline note.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from docx import Document
from docx.shared import Pt

from models import Asset, Case, Claim

MAX_QUOTES = 20                # newest first; the rest are counted, not listed

ASSET_LABELS = {
    "savings_account": "Savings bank account", "fixed_deposit": "Fixed deposit", "life_insurance": "Life insurance policy",
    "mutual_fund": "Mutual fund folio", "shares": "Shareholding", "provident_fund": "Provident fund account",
    "post_office": "Post office deposit", "other": "Financial asset",
}
PATH_TITLES = {
    "nominee": "Claim by registered nominee",
    "simplified_no_nominee": "Claim by legal heirs without nomination (simplified procedure)",
    "standard_succession": "Claim by legal heirs without nomination (succession certificate / probate)",
    "dea_claim_via_bank": "Claim for a deposit transferred to the RBI Depositor Education and Awareness (DEA) Fund",
    "insurance_death_claim": "Death claim under a life insurance policy",
    "transmission": "Transmission of units / securities to the legal heir",
    "iepf_refund": "Refund of shares and dividends from the IEPF Authority",
    "epf_claim": "Provident fund death claim",
    "needs_nominee_answer": "Claim path pending: nomination status not yet confirmed",
    "manual_review": "Claim path to be reviewed with a professional",
}
PATH_REQUESTS = {
    "nominee": "As the registered nominee, I request settlement of the above {label} in my favour.",
    "simplified_no_nominee": "No nominee was registered for the above {label}. As legal heir, I request settlement "
                             "under the bank's simplified procedure for claims without nomination.",
    "standard_succession": "No nominee was registered for the above {label}. As legal heir, I request settlement "
                           "on production of a succession certificate or probate.",
    "dea_claim_via_bank": "The above {label} appears to have been transferred to the RBI DEA Fund as unclaimed. "
                          "As legal heir, I request that the bank claim the amount back from the DEA Fund and "
                          "settle it in my favour.",
    "insurance_death_claim": "I request settlement of the death claim under the above {label}.",
    "transmission": "I request transmission of the holdings under the above {label} to my name.",
    "iepf_refund": "The shares and unclaimed dividends under the above {label} appear to have been transferred to "
                   "the IEPF Authority. As legal heir, I request their refund.",
    "epf_claim": "I request settlement of the balance under the above {label}.",
    "needs_nominee_answer": "Please confirm whether a nominee was registered for the above {label} so that the "
                            "correct claim procedure can be followed.",
    "manual_review": "I request guidance on the procedure to claim the above {label}.",
}
DOC_LABELS = {
    "claim_form": "Claim form of the institution, filled and signed",
    "death_certificate": "Death certificate (original and self-attested copy)",
    "claimant_id": "Claimant's identity and address proof",
    "nominee_id": "Nominee's identity and address proof",
    "legal_heir_certificate_or_affidavit": "Legal heir certificate, or affidavit and indemnity as the bank requires",
    "no_objection_other_heirs": "No-objection letters from the other legal heirs",
    "succession_certificate_or_probate": "Succession certificate or probate",
    "udgam_reference": "UDGAM search result / unclaimed deposit reference number (UDRN)",
    "policy_document_or_number": "Policy bond, or the policy number",
    "claimant_bank_proof": "Claimant's bank account proof (cancelled cheque or passbook copy)",
    "iepf_5_form": "Form IEPF-5, filed online and printed",
    "transmission_documents": "Transmission documents (succession certificate, or affidavit and indemnity)",
    "original_share_details": "Folio number and share certificate details",
    "transmission_request_form": "Transmission request form of the fund house / registrar",
    "claimant_kyc": "Claimant's KYC documents",
}
DISCLAIMER = ("This pack was prepared by Ghost Assets from records shared by the family. It is a checklist and draft, "
              "not legal advice. Confirm the exact requirements with the institution before submitting.")


def _money(value: float | None) -> str:
    if value is None:
        return "not known"
    whole = f"{int(round(value))}"
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return "Rs " + ",".join([*groups, tail]) if groups else f"Rs {tail}"


def _cover_letter(doc: Document, case: Case, asset: Asset, claim: Claim, label: str) -> None:
    doc.add_paragraph(f"Date: {date.today().strftime('%d %B %Y')}")
    doc.add_paragraph(f"To,\n{claim.where}\n{asset.institution}")
    doc.add_paragraph(f"Subject: {PATH_TITLES.get(claim.path, claim.path)} - {label} "
                      f"{asset.identifier or '(number not known)'} of late {case.deceased_name}")
    doc.add_paragraph("Dear Sir / Madam,")
    doc.add_paragraph(f"{case.deceased_name} passed away on {case.date_of_death}. Our records show that "
                      f"{case.deceased_name} held the following {label.lower()} with {asset.institution}:")
    table = doc.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for k, v in [("Holder", case.deceased_name), ("Institution", asset.institution), ("Type", label),
                 ("Account / policy / folio", asset.identifier or "not known"),
                 ("Estimated value", f"{_money(asset.est_value)} ({asset.value_basis or 'basis not recorded'})"),
                 ("Status", asset.status.replace("_", " ")), ("Nominee registered", asset.nominee)]:
        row = table.add_row().cells
        row[0].text, row[1].text = k, v
    doc.add_paragraph()
    doc.add_paragraph(PATH_REQUESTS.get(claim.path, PATH_REQUESTS["manual_review"]).format(label=label.lower()))
    doc.add_paragraph("The documents listed in the enclosed checklist are submitted with this letter.")
    doc.add_paragraph("Yours faithfully,\n\nName of claimant: ______________________\n"
                      f"Relationship to {case.deceased_name}: ______________________\n"
                      "Phone: ______________________\nSignature: ______________________")


def _checklist(doc: Document, claim: Claim) -> None:
    doc.add_heading("Document checklist", level=1)
    if not claim.documents:
        doc.add_paragraph("No documents can be listed until the claim path is confirmed.")
        return
    for d in claim.documents:
        doc.add_paragraph(f"[{'x' if d.have else ' '}] {DOC_LABELS.get(d.name, d.name.replace('_', ' '))}")
    missing = sum(not d.have for d in claim.documents)
    doc.add_paragraph(f"{len(claim.documents) - missing} of {len(claim.documents)} documents in hand.")


def _evidence(doc: Document, quotes: list[dict]) -> None:
    doc.add_heading("Evidence found", level=1)
    if not quotes:
        doc.add_paragraph("No evidence quotes recorded.")
        return
    ordered = sorted(quotes, key=lambda q: q.get("date") or "", reverse=True)
    for q in ordered[:MAX_QUOTES]:
        p = doc.add_paragraph(style="List Bullet")
        p.add_run(f"{q.get('date') or 'undated'}  [{q.get('evidence_id')}]  ").bold = True
        p.add_run(f"“{q.get('quote', '')}”")
    if len(ordered) > MAX_QUOTES:
        doc.add_paragraph(f"... and {len(ordered) - MAX_QUOTES} older records.")


def build_claim_pack(case: Case, asset: Asset, claim: Claim, quotes: list[dict], out_dir: Path) -> Path:
    label = ASSET_LABELS.get(asset.asset_type, "Financial asset")
    doc = Document()
    doc.styles["Normal"].font.size = Pt(11)
    doc.add_heading(f"Claim pack: {asset.institution} {label.lower()} {asset.identifier or ''}".strip(), level=0)
    doc.add_paragraph(f"Claim path: {PATH_TITLES.get(claim.path, claim.path)}\nSubmit to: {claim.where}")
    _cover_letter(doc, case, asset, claim, label)
    doc.add_page_break()
    _checklist(doc, claim)
    _evidence(doc, quotes)
    doc.add_heading("Timeline", level=1)
    doc.add_paragraph(claim.deadline_note or "No statutory settlement deadline is recorded for this claim path.")
    doc.add_paragraph(DISCLAIMER).runs[0].italic = True

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{case.id}_{asset.id}.docx"
    doc.save(path)
    print(f"[claimpack] {asset.id} {claim.path} -> {path}")
    return path
