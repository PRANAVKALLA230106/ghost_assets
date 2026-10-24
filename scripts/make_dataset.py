"""Generate Ramesh Kumar's synthetic case for the Ghost Assets demo.

Run from the repo root:   python scripts/make_dataset.py
Writes to data/ramesh/:
  sms.xml            ~3,000 SMS in the "SMS Backup & Restore" Android format
  emails.json        60 emails: {from, date, subject, body, attachment_text}
  ais.pdf            a simplified Annual Information Statement table
  photos/passbook.png, photos/policy_bond.png
  ground_truth.json  the 7 assets the pipeline must find, with key evidence IDs
  fake_events.jsonl  a scripted event stream so the frontend can be built before the backend

Everything is seeded, so every run produces identical files.
All names, numbers, institutions' messages and documents are SAMPLE DATA.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, date
from pathlib import Path
from xml.sax.saxutils import quoteattr

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "ramesh"
PHOTOS = OUT / "photos"

rng = random.Random(42)
DEATH = datetime(2026, 2, 10)
START = datetime(2012, 1, 1)


def inr(n: float, paise: bool = True) -> str:
    """Indian digit grouping: 238000 -> '2,38,000.00'."""
    whole = int(round(n * 100)) // 100
    frac = int(round(n * 100)) % 100
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return f"{s}.{frac:02d}" if paise else s


def months(start: date, count: int):
    y, m = start.year, start.month
    for _ in range(count):
        yield y, m
        m += 1
        if m > 12:
            y, m = y + 1, 1


def rand_time(d: datetime) -> datetime:
    return d.replace(hour=rng.randint(7, 21), minute=rng.randint(0, 59), second=rng.randint(0, 59))


def rand_dt(a: datetime = START, b: datetime = DEATH - timedelta(days=1)) -> datetime:
    span = int((b - a).total_seconds())
    return a + timedelta(seconds=rng.randint(0, span))


# --------------------------------------------------------------------------- SMS
sms: list[dict] = []  # {dt, address, body, tag}


def add(dt, address, body, tag=None):
    sms.append({"dt": dt, "address": address, "body": body, "tag": tag})


SBI = ["VM-SBIINB", "AD-SBIINB", "JD-SBIINB"]

# Asset 1: SBI savings XX8812, pension credits (known to family). Final balance 1,20,000.00
pension_months = list(months(date(2023, 3, 1), 35))  # Mar 2023 .. Jan 2026
balances = []
bal = 120000.00
for _ in pension_months:
    balances.insert(0, bal)
    bal = round(bal - rng.uniform(-6000, 9000), 2)
for (y, m), b in zip(pension_months, balances):
    d = rand_time(datetime(y, m, 1))
    fmt = rng.choice([
        "Dear Customer, your A/c XX8812 is credited by Rs.32,500.00 on {d} by PENSION. Avl Bal Rs.{b} -SBI",
        "Your a/c no. XX8812 is credited by Rs32,500.00 on {d} (PENSION CR). Avl Bal: Rs {b}. -SBI",
    ])
    add(d, rng.choice(SBI), fmt.format(d=d.strftime("%d-%m-%y"), b=inr(b)), "sbi_8812")

# UPI payments from XX8812 to shops (financial-looking; same account)
shops = ["chaiwala", "freshmart", "medplus.jayanagar", "auto.ravi", "kirana.manju", "bescom.pay", "milk.nandini", "pharmacy.apollo"]
for _ in range(150):
    d = rand_dt(datetime(2020, 1, 1))
    amt = rng.choice([40, 60, 120, 240, 350, 480, 760, 1200, 1840, 2300])
    add(d, rng.choice(SBI),
        f"Rs.{inr(amt)} debited from A/c XX8812 on {d:%d-%m-%y} to VPA {rng.choice(shops)}@ybl. UPI Ref {rng.randint(10**11, 10**12 - 1)}. Not you? Call 1800111109 -SBI",
        "sbi_8812_upi")

# Asset 2: LIC policy XXXXX5271 (known). Premium reminders + debits from XX8812
for y in range(2019, 2026):
    d = rand_time(datetime(y, 6, 1))
    add(d, "VM-LICIND", f"LIC: Premium of Rs.9,850 for Policy No. XXXXX5271 is due on 15/06/{y}. Pay online. Ignore if already paid.", "lic_5271")
    d2 = rand_time(datetime(y, 6, rng.randint(5, 14)))
    add(d2, rng.choice(SBI), f"Rs.9,850.00 debited from A/c XX8812 on {d2:%d-%m-%y} towards LIC PREMIUM Policy XXXXX5271 -SBI", "lic_5271")

# Asset 3: Suraksha Life policy XXXXX0903 (unknown to family)
for y in (2023, 2024, 2025):
    d = rand_time(datetime(y, 8, 25))
    add(d, "AD-SURKSH", f"Dear Policyholder, premium of Rs 12,450.00 for policy XXXXX0903 (Suraksha Smart Protect) is due on 05-09-{y}. Pay via app or auto-debit.", "suraksha_0903")
    d2 = rand_time(datetime(y, 9, 5))
    add(d2, rng.choice(SBI), f"INR 12450.00 debited from A/c XX8812 on {d2:%d-%m-%y} towards SURAKSHA LIFE premium policy XXXXX0903 -SBI", "suraksha_0903")

# Asset 4: Kaveri Flexi Cap Fund SIP, folio XXXXXX3312 (unknown)
for (y, m) in months(date(2023, 3, 1), 35):
    d = rand_time(datetime(y, m, 5))
    nav = round(rng.uniform(118, 168), 2)
    units = round(5000 / nav, 3)
    add(d, "VM-KAVRMF", f"Your SIP of Rs.5,000.00 in Kaveri Flexi Cap Fund - Growth, Folio XXXXXX3312 is processed. Units: {units} @ NAV {nav}. -Kaveri MF", "kaveri_3312")
    add(d - timedelta(hours=3), rng.choice(SBI), f"Rs 5000 debited from A/c XX8812 on {d:%d-%m-%y} for SIP KAVERI MF Folio XXXXXX3312 -SBI", "kaveri_3312")

# Asset 5: Canara Bank FD XX4521 (unknown)
add(rand_time(datetime(2016, 3, 15)), "VM-CANBNK", "Dear Customer, Term Deposit A/c XX4521 opened for Rs.1,72,500.00 for 36 months. -Canara Bank", "canara_4521")
add(rand_time(datetime(2019, 3, 15)), "AD-CANBNK", "Dear Customer, your FD A/c XX4521 of Rs.2,00,000 has been renewed for 36 months. Maturity date 15-03-2022. -Canara Bank", "canara_4521")

# Asset 6: Ganga Tech Ltd shares (dividends stop after 2017)
for y in (2015, 2016, 2017):
    d = rand_time(datetime(y, 8, 22))
    add(d, rng.choice(SBI), f"Your A/c XX8812 is credited by Rs.1,840.00 on {d:%d-%m-%y} - GANGA TECH LTD DIV. Avl Bal Rs.{inr(rng.uniform(40000, 90000))} -SBI", "gangatech")

relevant_count = len(sms)

# Noise
def otp():
    return f"{rng.randint(100000, 999999)} is your OTP for {rng.choice(['login', 'transaction', 'Aadhaar update', 'order verification'])}. Valid for 10 mins. Do not share it with anyone."

NOISE = [
    ("VM-AMZNIN", lambda: f"Your order #{rng.randint(10**6, 10**7)} has been delivered. Rate your experience."),
    ("AD-FLPKRT", lambda: f"Out for delivery: your package arrives today by 8 PM. Track: fkrt.example/{rng.randint(1000, 9999)}"),
    ("VK-SWIGGY", lambda: "Your food is on the way! Track your order in the app."),
    ("JM-MYNTRA", lambda: f"BIG FESTIVE SALE! Flat {rng.choice([40, 50, 60, 70])}% off. Shop now."),
    ("AX-AIRTEL", lambda: f"You have used {rng.choice([50, 80, 90, 100])}% of your daily data quota."),
    ("VM-JIOINF", lambda: f"Recharge of Rs {rng.choice([239, 299, 666])} successful. Validity {rng.choice([28, 56, 84])} days."),
    ("AD-LOANSX", lambda: "Pre-approved personal loan offer of Rs 5,00,000 just for you! Apply in 2 minutes."),
    ("VM-CRDOFR", lambda: "Congratulations! You are eligible for a lifetime-free credit card offer. Apply now."),
    ("BZ-BESCOM", lambda: f"BESCOM: Bill of Rs {rng.randint(400, 2200)} for RR No. JY{rng.randint(1000, 9999)} is due on {rng.randint(1, 28)}th."),
    ("VM-PRACTO", lambda: "Reminder: your appointment with Dr. Shetty is tomorrow at 10:30 AM."),
    ("+919845012345", lambda: rng.choice(["Papa call me when free", "Reached office", "Will come by 7", "Did you take your tablets?", "Happy birthday Appa!"])),
    ("+919900087654", lambda: rng.choice(["Ramesh, temple committee meeting on Sunday", "Morning walk tomorrow 6am?", "Sent the photos on WhatsApp"])),
    ("VM-OTPSMS", otp),
    ("AD-HDFCOT", otp),
]
target_total = 3000
while len(sms) < target_total:
    addr, f = rng.choice(NOISE)
    add(rand_dt(), addr, f(), None)

sms.sort(key=lambda r: r["dt"])
sms_ids = {}
for i, r in enumerate(sms, start=1):
    r["id"] = f"sms_{i:04d}"

lines = ["<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>", f'<smses count="{len(sms)}">']
for r in sms:
    ms = int(r["dt"].timestamp() * 1000)
    lines.append(
        f'  <sms protocol="0" address={quoteattr(r["address"])} date="{ms}" type="1" subject="null" '
        f'body={quoteattr(r["body"])} read="1" status="-1" readable_date={quoteattr(r["dt"].strftime("%d %b %Y %I:%M:%S %p"))} contact_name="(Unknown)" />'
    )
lines.append("</smses>")
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "sms.xml").write_text("\n".join(lines), encoding="utf-8")

# ------------------------------------------------------------------------- EMAILS
emails: list[dict] = []


def email(dt, frm, subject, body, attachment_text="", tag=None):
    emails.append({"dt": dt, "from": frm, "subject": subject, "body": body, "attachment_text": attachment_text, "tag": tag})


email(datetime(2014, 8, 20, 10, 12), "secretarial@gangatech.example", "Ganga Tech Ltd - Notice of 21st Annual General Meeting",
      "Dear Shareholder,\nNotice is hereby given that the 21st AGM of Ganga Tech Ltd will be held on 18 September 2014.\n"
      "Folio No.: GT004217\nShareholder: RAMESH KUMAR\nHolding: 400 equity shares of Rs 10 each\n"
      "Please update your bank mandate to receive dividends electronically.", tag="gangatech")
email(datetime(2022, 3, 16, 9, 40), "termdeposits@canarabank.example", "Term Deposit XX4521 - maturity and auto-renewal advice",
      "Dear Customer,\nPlease find attached the advice for your term deposit ending 4521.",
      "CANARA BANK - TERM DEPOSIT ADVICE\nDeposit A/c: XX4521\nDepositor: RAMESH KUMAR\nMatured on: 15-03-2022\n"
      "Maturity value: Rs 2,38,000.00\nAction: auto-renewed for 60 months", tag="canara_4521")
email(datetime(2018, 5, 3, 11, 20), "alerts@sbi.example", "Nomination registered for your account XX8812",
      "Dear Customer,\nAs requested, nomination has been registered for your savings account XX8812.\n"
      "Nominee: SUNITA KUMAR (Wife)\nIf you did not request this, contact your branch.", tag="sbi_8812")
email(datetime(2022, 9, 7, 18, 5), "welcome@surakshalife.example", "Welcome to Suraksha Life - Policy XXXXX0903",
      "Dear Ramesh Kumar,\nThank you for choosing Suraksha Smart Protect.\nPolicy No.: XXXXX0903\nSum Assured: Rs 4,00,000\n"
      "Annual premium: Rs 12,450.00, due every 5 September\nPolicy term: 20 years", tag="suraksha_0903")
email(datetime(2026, 1, 12, 7, 30), "statements@cas.example", "Consolidated Account Statement - December 2025",
      "Dear Investor, your Consolidated Account Statement for December 2025 is attached.",
      "CONSOLIDATED ACCOUNT STATEMENT - DEC 2025\nInvestor: RAMESH KUMAR  PAN: XXXXX1234K\n"
      "Kaveri Flexi Cap Fund - Growth | Folio XXXXXX3312 | Units 1,624.552 | NAV 160.05 | Market Value Rs 2,60,000.00\n"
      "Total portfolio value: Rs 2,60,000.00", tag="kaveri_3312")

noise_emails = [
    ("newsletter@morningbrief.example", "Your morning brief", "Markets, monsoon and more. Read today's top stories."),
    ("orders@shopkart.example", "Your ShopKart order has shipped", "Order #{n}: 1 item(s) shipped. Expected delivery in 3 days."),
    ("billing@bescom.example", "Electricity bill for RR No. JY{n}", "Your bill of Rs {m} is due on the 20th.", "BESCOM BILL\nAmount due: Rs {m}"),
    ("noreply@trains.example", "Booking confirmed: Bengaluru to Mysuru", "PNR {n}. 2 passengers. Have a safe journey."),
    ("temple@sriramtemple.example", "Donation receipt", "Thank you for your donation of Rs {m} towards the temple renovation."),
    ("alerts@healthlab.example", "Your lab report is ready", "Your HbA1c report is ready to download.", "LAB REPORT\nHbA1c: 6.8%"),
    ("community@rwajayanagar.example", "RWA meeting minutes", "Minutes of the residents' welfare meeting are attached."),
    ("offers@creditcards.example", "Exclusive card offer for you", "Get a lifetime-free card. Limited period offer."),
]
while len(emails) < 60:
    t = rng.choice(noise_emails)
    n, m = rng.randint(10000, 99999), rng.randint(300, 4000)
    email(rand_dt(datetime(2016, 1, 1)), t[0], t[1].format(n=n, m=m), t[2].format(n=n, m=m),
          (t[3].format(n=n, m=m) if len(t) > 3 else ""))
emails.sort(key=lambda e: e["dt"])
email_rows = []
for i, e in enumerate(emails, start=1):
    e["id"] = f"email_{i:03d}"
    email_rows.append({"from": e["from"], "date": e["dt"].isoformat(), "subject": e["subject"], "body": e["body"], "attachment_text": e["attachment_text"]})
(OUT / "emails.json").write_text(json.dumps(email_rows, indent=2, ensure_ascii=False), encoding="utf-8")

# ---------------------------------------------------------------------------- AIS
from fpdf import FPDF  # noqa: E402

ais_rows = [
    ("SFT-016(SB)", "Interest from savings bank", "STATE BANK OF INDIA (A/C XX8812)", 3100, "sbi_8812"),
    ("SFT-016(TD)", "Interest from deposit", "CANARA BANK", 18200, "canara_4521"),
    ("SFT-018", "Purchase of mutual fund units", "KAVERI MUTUAL FUND", 60000, "kaveri_3312"),
    ("TDS-192A", "Pension", "STATE BANK OF INDIA (PENSION)", 390000, None),
]
pdf = FPDF(orientation="L", unit="mm", format="A4")
pdf.add_page()
pdf.set_font("Helvetica", "B", 14)
pdf.cell(0, 9, "Annual Information Statement (AIS) - SAMPLE DATA", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Helvetica", "", 10)
pdf.cell(0, 6, "Name: RAMESH KUMAR    PAN: XXXXX1234K    Financial Year: 2024-25 (Assessment Year 2025-26)", new_x="LMARGIN", new_y="NEXT")
pdf.ln(4)
widths = [12, 32, 70, 110, 40]
headers = ["Sr", "Information Code", "Information Description", "Information Source", "Amount (Rs)"]
pdf.set_font("Helvetica", "B", 10)
for w, h in zip(widths, headers):
    pdf.cell(w, 8, h, border=1)
pdf.ln()
pdf.set_font("Helvetica", "", 10)
for i, (code, desc, src, amt, _) in enumerate(ais_rows, start=1):
    for w, v in zip(widths, [str(i), code, desc, src, inr(amt)]):
        pdf.cell(w, 8, v, border=1)
    pdf.ln()
pdf.ln(4)
pdf.set_font("Helvetica", "I", 9)
pdf.cell(0, 6, "Synthetic document generated for a hackathon demo. Not a real tax record.")
pdf.output(str(OUT / "ais.pdf"))

# ------------------------------------------------------------------------- PHOTOS
from PIL import Image, ImageDraw, ImageFont, ImageFilter  # noqa: E402


def font(size, bold=False):
    names = (["DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"] if bold else ["DejaVuSans.ttf", "arial.ttf", "Arial.ttf"])
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def paper(w, h):
    img = Image.new("RGB", (w, h), (246, 240, 222))
    d = ImageDraw.Draw(img)
    for _ in range(4000):
        x, y = rng.randint(0, w - 1), rng.randint(0, h - 1)
        c = rng.randint(225, 245)
        d.point((x, y), fill=(c, c - 6, c - 22))
    return img, d


PHOTOS.mkdir(parents=True, exist_ok=True)
img, d = paper(1400, 1000)
d.text((60, 40), "STATE BANK OF INDIA - SAVINGS BANK PASSBOOK", font=font(34, True), fill=(30, 40, 90))
d.text((60, 95), "Branch: Jayanagar 4th Block, Bengaluru      A/c No: XXXXXXX3307", font=font(24), fill=(20, 20, 20))
d.text((60, 130), "Name: RAMESH KUMAR      Nomination: ____ (not registered)", font=font(24), fill=(20, 20, 20))
cols = [60, 260, 760, 960, 1160]
for x, h in zip(cols, ["Date", "Particulars", "Withdrawal", "Deposit", "Balance"]):
    d.text((x, 200), h, font=font(24, True), fill=(20, 20, 20))
d.line((50, 240, 1350, 240), fill=(90, 90, 90), width=2)
entries = [("02-04-2012", "BY CASH", "", "25,000.00", "25,000.00"), ("18-07-2012", "BY TRANSFER", "", "30,000.00", "55,000.00"),
           ("09-01-2013", "TO SELF", "8,000.00", "", "47,000.00"), ("21-06-2013", "BY CLG 004512", "", "24,000.00", "71,000.00"),
           ("30-09-2013", "INT. CREDIT", "", "1,000.00", "72,000.00"), ("14-11-2013", "BALANCE C/F", "", "", "72,000.00")]
for r, row in enumerate(entries):
    y = 265 + r * 60
    for x, v in zip(cols, row):
        d.text((x, y), v, font=font(24), fill=(25, 25, 60))
d.text((60, 900), "SAMPLE DATA - synthetic passbook for a hackathon demo", font=font(22, True), fill=(180, 60, 40))
img = img.rotate(1.6, expand=True, fillcolor=(60, 60, 60)).filter(ImageFilter.GaussianBlur(0.6))
img.save(PHOTOS / "passbook.png")

img, d = paper(1100, 1400)
d.text((60, 60), "POLICY BOND - LIFE INSURANCE", font=font(38, True), fill=(20, 60, 40))
d.text((60, 120), "Insurer: LIC", font=font(28, True), fill=(20, 20, 20))
rows = [("Policy No.", "XXXXX5271"), ("Life Assured", "RAMESH KUMAR"), ("Date of Commencement", "15-06-2010"),
        ("Plan", "Endowment, 20 years"), ("Sum Assured", "Rs 1,80,000"), ("Annual Premium", "Rs 9,850"),
        ("Nominee", "SUNITA KUMAR (Wife)")]
for i, (k, v) in enumerate(rows):
    y = 220 + i * 80
    d.text((60, y), k, font=font(28), fill=(60, 60, 60))
    d.text((520, y), v, font=font(30, True), fill=(20, 20, 20))
d.text((60, 1280), "SAMPLE DATA - synthetic document for a hackathon demo", font=font(24, True), fill=(180, 60, 40))
img = img.rotate(-1.2, expand=True, fillcolor=(60, 60, 60)).filter(ImageFilter.GaussianBlur(0.5))
img.save(PHOTOS / "policy_bond.png")

# ------------------------------------------------------------------- GROUND TRUTH
def ev_ids(tag, src):
    if src == "sms":
        return [r["id"] for r in sms if r["tag"] == tag]
    return [e["id"] for e in emails if e["tag"] == tag]


ais_ids = {t: f"ais_{i:02d}" for i, (*_, t) in enumerate(ais_rows, start=1) if t}
assets = [
    dict(id="sbi_8812", institution="State Bank of India", asset_type="savings_account", identifier="XX8812", value=120000,
         known_to_family=True, nominee="yes", expected_status="active", expected_claim_path="nominee"),
    dict(id="lic_5271", institution="LIC", asset_type="life_insurance", identifier="XXXXX5271", value=180000,
         known_to_family=True, nominee="yes", expected_status="active", expected_claim_path="insurance_death_claim"),
    dict(id="suraksha_0903", institution="Suraksha Life Insurance", asset_type="life_insurance", identifier="XXXXX0903", value=400000,
         known_to_family=False, nominee="unknown", expected_status="active", expected_claim_path="insurance_death_claim"),
    dict(id="kaveri_3312", institution="Kaveri Mutual Fund", asset_type="mutual_fund", identifier="XXXXXX3312", value=260000,
         known_to_family=False, nominee="unknown", expected_status="active", expected_claim_path="transmission"),
    dict(id="canara_4521", institution="Canara Bank", asset_type="fixed_deposit", identifier="XX4521", value=238000,
         known_to_family=False, nominee="no", expected_status="active", expected_claim_path="simplified_no_nominee"),
    dict(id="gangatech", institution="Ganga Tech Ltd", asset_type="shares", identifier="GT004217", value=190000,
         known_to_family=False, nominee="unknown", expected_status="transferred_iepf", expected_claim_path="iepf_refund"),
    dict(id="sbi_3307", institution="State Bank of India", asset_type="savings_account", identifier="XXXXXXX3307", value=72000,
         known_to_family=False, nominee="no", expected_status="transferred_dea", expected_claim_path="dea_claim_via_bank"),
]
photo_for = {"sbi_3307": ["photo_passbook"], "lic_5271": ["photo_policy_bond"]}
for a in assets:
    ids = ev_ids(a["id"], "sms") + ev_ids(a["id"], "email") + ([ais_ids[a["id"]]] if a["id"] in ais_ids else []) + photo_for.get(a["id"], [])
    a["key_evidence"] = ids
    a["value_source"] = {"gangatech": "IEPF portal lookup (mock)"}.get(a["id"], "evidence")

truth = {
    "case": {"deceased_name": "Ramesh Kumar", "date_of_death": DEATH.date().isoformat(), "as_of": "2026-10-24"},
    "counts": {"sms": len(sms), "emails": len(emails), "ais_rows": len(ais_rows), "photos": 2,
               "sms_relevant_planted": relevant_count},
    "assets": assets,
    "total_value": sum(a["value"] for a in assets),
    "known_value": sum(a["value"] for a in assets if a["known_to_family"]),
    "notes": "key_evidence lists every planted message for an asset; triage must keep all of them. "
             "Values are within +-5% tolerance in check_against_truth.py.",
}
(OUT / "ground_truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")

# -------------------------------------------------------------------- FAKE EVENTS
ev = []
def E(t, **data):
    ev.append({"type": t, "data": data})

E("agent_step", thought="Starting the case. First I'll scan every source the family uploaded.", tool="scan_sources", args={}, result_summary=f"{len(sms)} SMS, {len(emails)} emails, 4 AIS rows, 2 photos")
for done in range(0, len(sms) + 1, 300):
    E("progress", stage="triage", done=min(done, len(sms)), total=len(sms))
financial = sum(1 for r in sms if r["tag"]) + 6
E("progress", stage="triage_done", done=financial, total=len(sms))
E("agent_step", thought="Extracting clues from the financial messages.", tool="extract_clues", args={"source": "sms"}, result_summary="Grounded 268 clues, rejected 4")
clue_n = 0
for a in assets[:5]:
    for k in range(6):
        clue_n += 1
        E("clue", id=f"cl_{clue_n:04d}", evidence_id=a["key_evidence"][min(k, len(a["key_evidence"]) - 1)], institution_raw=a["institution"],
          institution=a["institution"], asset_type=a["asset_type"], identifier=a["identifier"], amount=None, amount_kind="unknown",
          date=None, nominee=None, quote="(sample)")
E("agent_step", thought="Merging clues into assets.", tool="build_asset_map", args={}, result_summary="5 assets so far")
for a in assets[:5]:
    E("asset", id=a["id"], institution=a["institution"], asset_type=a["asset_type"], identifier=a["identifier"], est_value=a["value"],
      confidence=0.9, last_activity=None, status="unknown", nominee=a["nominee"], known_to_family=a["known_to_family"],
      clue_ids=[c["data"]["id"] for c in ev if c["type"] == "clue" and c["data"]["institution"] == a["institution"]])
E("agent_step", thought="The passbook photo shows an SBI account with no entries after 2013. That is over 10 years, so it may be with RBI's DEA Fund.", tool="read_photo", args={"file": "passbook.png"}, result_summary="SBI A/c XXXXXXX3307, last entry 14-11-2013, balance 72,000")
E("agent_step", thought="Checking UDGAM for this account.", tool="check_portal", args={"portal": "UDGAM", "name": "Ramesh Kumar", "institution": "State Bank of India"}, result_summary="Match: XXXXXXX3307, Rs 72,000, UDRN2026SBI0004417")
a = assets[6]
E("asset", id=a["id"], institution=a["institution"], asset_type=a["asset_type"], identifier=a["identifier"], est_value=a["value"], confidence=0.85,
  last_activity="2013-11-14", status="transferred_dea", nominee="no", known_to_family=False, clue_ids=[])
E("agent_step", thought="Ganga Tech dividends stop after 2017. Searching all evidence for Ganga Tech.", tool="search_evidence", args={"query": "Ganga Tech"}, result_summary="AGM notice 2014: folio GT004217, 400 shares")
E("agent_step", thought="Dividends unclaimed for 7+ years usually move shares to IEPF. Checking IEPF.", tool="check_portal", args={"portal": "IEPF", "name": "Ramesh Kumar", "institution": "Ganga Tech Ltd"}, result_summary="Match: 400 shares + unclaimed dividends, Rs 1,90,000")
a = assets[5]
E("asset", id=a["id"], institution=a["institution"], asset_type=a["asset_type"], identifier=a["identifier"], est_value=a["value"], confidence=0.8,
  last_activity="2017-08-22", status="transferred_iepf", nominee="unknown", known_to_family=False, clue_ids=[])
E("agent_step", thought="No nominee appears anywhere for the Canara Bank FD. I need to ask the family.", tool="ask_family", args={}, result_summary="Waiting for answer")
E("question", id="q1", text="Did your father name a nominee on his Canara Bank FD (XX4521)?", options=["Yes", "No", "Not sure"])
for a in assets:
    E("agent_step", thought=f"Applying claim rules to {a['institution']} {a['identifier']}.", tool="apply_claim_rules", args={"asset_id": a["id"]}, result_summary=a["expected_claim_path"])
    E("claim", asset_id=a["id"], path=a["expected_claim_path"], where="Branch / claims desk", documents=[{"name": "Death certificate", "have": True}, {"name": "Claimant ID", "have": True}], deadline_note=None)
E("agent_step", thought="All assets found and claim packs ready.", tool="finish", args={}, result_summary="7 assets, Rs 14,60,000")
E("done", total_value=truth["total_value"], known_value=truth["known_value"], asset_count=len(assets))
(OUT / "fake_events.jsonl").write_text("\n".join(json.dumps(x) for x in ev), encoding="utf-8")

print(f"SMS: {len(sms)} ({relevant_count} planted financial)  Emails: {len(emails)}  AIS rows: {len(ais_rows)}  Photos: 2")
print(f"Assets: {len(assets)}  Total: Rs {inr(truth['total_value'], False)}  Known to family: Rs {inr(truth['known_value'], False)}")
print(f"Fake events: {len(ev)}  -> {OUT}")
