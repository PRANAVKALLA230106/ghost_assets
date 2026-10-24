"""Generate a THIRD synthetic case, Srijan Malhotra, to prove Ghost Assets isn't hardcoded.
Writes data/srijan/ in the exact formats the pipeline expects, plus ground_truth.json and the
portal records to merge. Smaller than Ramesh (~1000 SMS) so the one live run is fast.
All SAMPLE DATA."""
from __future__ import annotations
import json, random
from datetime import datetime, timedelta, date
from pathlib import Path
from xml.sax.saxutils import quoteattr

OUT = Path(__file__).resolve().parent / "data" / "srijan"
PHOTOS = OUT / "photos"
rng = random.Random(31)
DEATH = datetime(2026, 3, 22)
START = datetime(2012, 1, 1)


def inr(n, paise=True):
    whole = int(round(n * 100)) // 100; frac = int(round(n * 100)) % 100
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]; g = []
        while len(head) > 2:
            g.insert(0, head[-2:]); head = head[:-2]
        if head:
            g.insert(0, head)
        s = ",".join(g + [tail])
    return f"{s}.{frac:02d}" if paise else s


def months(start, count):
    y, m = start.year, start.month
    for _ in range(count):
        yield y, m
        m += 1
        if m > 12:
            y, m = y + 1, 1


def rt(d):
    return d.replace(hour=rng.randint(7, 21), minute=rng.randint(0, 59), second=rng.randint(0, 59))


def rand_dt(a=START, b=DEATH - timedelta(days=1)):
    return a + timedelta(seconds=rng.randint(0, int((b - a).total_seconds())))


sms = []
def add(dt, address, body, tag=None):
    sms.append({"dt": dt, "address": address, "body": body, "tag": tag})


AXIS = ["VM-AXISBK", "AD-AXISBK", "JD-AXISBK"]
ICICI = ["VM-ICICIB", "AD-ICICIB"]

# Asset 1: Axis savings XX6034, salary account (known), nominee wife. Final bal 1,40,000
pm = list(months(date(2023, 4, 1), 36)); bals = []; b = 140000.0
for _ in pm:
    bals.insert(0, b); b = round(b - rng.uniform(-9000, 12000), 2)
for (y, m), bal in zip(pm, bals):
    d = rt(datetime(y, m, rng.randint(28, 28)))
    add(d, rng.choice(AXIS), f"INR 1,12,500.00 credited to A/c no. XX6034 on {d:%d-%m-%y} by NEFT SALARY ORIONSOFT TECH. Avl Bal INR {inr(bal)} - Axis Bank", "axis_6034")
for _ in range(80):
    d = rand_dt(datetime(2021, 1, 1)); amt = rng.choice([60, 120, 249, 450, 799, 1200, 2400])
    add(d, rng.choice(AXIS), f"INR {inr(amt)} debited from A/c no. XX6034 on {d:%d-%m-%y} UPI/{rng.choice(['zomato','dmart','uber','petrol.iocl','chemist.apollo'])}@axl Ref {rng.randint(10**11,10**12-1)} - Axis Bank", "axis_6034_upi")
add(rt(datetime(2018, 11, 6)), "AD-AXISBK", "Nomination updated for A/c no. XX6034. Nominee: NEHA MALHOTRA (Spouse). - Axis Bank", "axis_6034")

# Asset 2: EPF, UAN XXXXXXXX5521 (unknown to family)
pf = 512000.0
for (y, m) in months(date(2023, 4, 1), 35):
    pf += 14400 + rng.uniform(0, 900)
    d = rt(datetime(y, m, rng.randint(12, 18)))
    bal = 680000 if (y, m) == (2026, 2) else round(pf, -2)
    add(d, "VM-EPFOHO", f"Dear Member, contribution of Rs. 14,400 for {d:%m/%Y} received in your PF account linked to UAN XXXXXXXX5521. Total PF balance Rs. {inr(bal, False)}. -EPFO", "epf_5521")

# Asset 3: Max Life term policy XXXXXX4472 (unknown), premiums debited from Axis
for y in (2022, 2023, 2024, 2025):
    add(rt(datetime(y, 5, 20)), "AD-MAXLIF", f"Renewal premium of Rs 21,600 for your Max Life term policy XXXXXX4472 is due on 05-06-{y}. Sum assured Rs 25,00,000.", "maxlife_4472")
    d2 = rt(datetime(y, 6, 5))
    add(d2, rng.choice(AXIS), f"INR 21,600.00 debited from A/c no. XX6034 on {d2:%d-%m-%y} towards MAX LIFE premium policy XXXXXX4472 - Axis Bank", "maxlife_4472")

# Asset 4: Bandhan MF SIP folio XXXXXXX3390 (unknown)
for (y, m) in months(date(2023, 3, 1), 37):
    d = rt(datetime(y, m, 10)); nav = round(rng.uniform(38, 61), 2); units = round(8000 / nav, 3)
    add(d, "VM-BNDHMF", f"SIP of Rs 8,000.00 in Bandhan Small Cap Fund - Direct Growth, Folio XXXXXXX3390 processed. Units {units} @ NAV {nav}. -Bandhan MF", "bandhan_3390")
    add(d - timedelta(hours=3), rng.choice(AXIS), f"INR 8,000.00 debited from A/c no. XX6034 on {d:%d-%m-%y} for SIP BANDHAN MF Folio XXXXXXX3390 - Axis Bank", "bandhan_3390")

# Asset 5: ICICI FD XX8817 (unknown, no nominee info anywhere)
add(rt(datetime(2022, 7, 4)), "VM-ICICIB", "Fixed Deposit A/c XX8817 opened for Rs 2,75,000.00 for 3 years. -ICICI Bank", "icici_8817")
add(rt(datetime(2025, 7, 4)), "AD-ICICIB", "Your FD A/c XX8817 has matured and is renewed for 1 year. Renewed principal Rs 3,00,000.00. Maturity date 04-07-2026. -ICICI Bank", "icici_8817")
add(rt(datetime(2025, 12, 31)), "VM-ICICIB", "Interest of Rs 5,250.00 credited to FD A/c XX8817 for the quarter ending 31-12-2025. -ICICI Bank", "icici_8817")

# Asset 6: Indus Polymers shares, dividends stop after 2017 -> IEPF
for y in (2015, 2016, 2017):
    d = rt(datetime(y, 9, 10))
    add(d, rng.choice(AXIS), f"INR 1,800.00 credited to A/c no. XX6034 on {d:%d-%m-%y} - INDUS POLYMERS LTD FINAL DIV. Avl Bal INR {inr(rng.uniform(40000,90000))} - Axis Bank", "indus")

relevant = len(sms)

def otp():
    return f"{rng.randint(100000,999999)} is your OTP for {rng.choice(['login','payment','KYC'])}. Valid 10 mins. Do not share."
NOISE = [
    ("VM-AMZNIN", lambda: f"Order #{rng.randint(10**6,10**7)} delivered. Rate now."),
    ("VK-ZOMATO", lambda: "Your order is out for delivery!"),
    ("JM-AJIOIN", lambda: f"BIG SALE {rng.choice([40,50,70])}% off."),
    ("AX-JIOINF", lambda: f"You used {rng.choice([80,90,100])}% of daily data."),
    ("BZ-BSESDL", lambda: f"BSES bill Rs {rng.randint(900,4800)} due on {rng.randint(1,28)}th."),
    ("VM-IGLGAS", lambda: f"IGL bill Rs {rng.randint(300,900)} generated."),
    ("+919811045672", lambda: rng.choice(["Papa where are you","Pick up Aarav at 4","Reached office","Call when free"])),
    ("VM-OTPSMS", otp), ("AD-HDFCBK", otp),
]
while len(sms) < 1000:
    a, f = rng.choice(NOISE); add(rand_dt(), a, f(), None)

sms.sort(key=lambda r: r["dt"])
for i, r in enumerate(sms, 1):
    r["id"] = f"sms_{i:04d}"
OUT.mkdir(parents=True, exist_ok=True)
lines = ["<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>", f'<smses count="{len(sms)}">']
for r in sms:
    ms = int(r["dt"].timestamp() * 1000)
    lines.append(f'  <sms protocol="0" address={quoteattr(r["address"])} date="{ms}" type="1" subject="null" body={quoteattr(r["body"])} read="1" status="-1" readable_date={quoteattr(r["dt"].strftime("%d %b %Y %I:%M:%S %p"))} contact_name="(Unknown)" />')
lines.append("</smses>")
(OUT / "sms.xml").write_text("\n".join(lines), encoding="utf-8")

# EMAILS
emails = []
def email(dt, frm, subj, body, att="", tag=None):
    emails.append({"dt": dt, "from": frm, "subject": subj, "body": body, "attachment_text": att, "tag": tag})
email(datetime(2014, 8, 20, 10, 0), "investor.relations@induspolymers.example", "Indus Polymers Ltd - Notice of 22nd AGM",
      "Dear Shareholder,\nNotice of the 22nd AGM of Indus Polymers Ltd on 26 Sep 2014.\nFolio No.: IP20774\nShareholder: SRIJAN MALHOTRA\nHolding: 600 equity shares of Rs 2 each.", tag="indus")
email(datetime(2025, 7, 5, 9, 0), "fd.advice@icicibank.example", "FD XX8817 - renewal advice",
      "Dear Customer, the renewal advice for your fixed deposit ending 8817 is attached.",
      "ICICI BANK - FIXED DEPOSIT RENEWAL ADVICE\nFD A/c: XX8817\nDepositor: SRIJAN MALHOTRA\nRenewed on: 04-07-2025\nPrincipal: Rs 3,00,000.00\nMaturity date: 04-07-2026", tag="icici_8817")
email(datetime(2022, 6, 6, 18, 0), "service@maxlifeinsurance.example", "Your Max Life policy XXXXXX4472 is issued",
      "Dear Srijan Malhotra,\nPolicy No.: XXXXXX4472 (Max Life Smart Term Plan)\nSum Assured: Rs 25,00,000\nAnnual premium: Rs 21,600, due 5 June.", tag="maxlife_4472")
email(datetime(2026, 3, 8, 7, 0), "statements@cas.example", "Consolidated Account Statement - Feb 2026",
      "Dear Investor, your CAS for Feb 2026 is attached.",
      "CONSOLIDATED ACCOUNT STATEMENT - FEB 2026\nInvestor: SRIJAN MALHOTRA\nBandhan Small Cap Fund - Direct Growth | Folio XXXXXXX3390 | Market Value Rs 4,10,000.00", tag="bandhan_3390")
noise_e = [("newsletter@hindustantimes.example", "Morning brief", "Top stories today."),
           ("noreply@orionsoft.example", "Town hall on Friday", "Join the all-hands at 4 PM."),
           ("orders@shop.example", "Order shipped", "Your order ships in 2 days."),
           ("school@dpsrkp.example", "PTM schedule", "Parent-teacher meeting on Saturday.")]
while len(emails) < 30:
    t = rng.choice(noise_e); email(rand_dt(datetime(2016, 1, 1)), t[0], t[1], t[2])
emails.sort(key=lambda e: e["dt"])
for i, e in enumerate(emails, 1):
    e["id"] = f"email_{i:03d}"
(OUT / "emails.json").write_text(json.dumps([{"from": e["from"], "date": e["dt"].isoformat(), "subject": e["subject"], "body": e["body"], "attachment_text": e["attachment_text"]} for e in emails], indent=2, ensure_ascii=False), encoding="utf-8")

# AIS
from fpdf import FPDF
ais_rows = [("SFT-016(SB)", "Interest from savings bank", "AXIS BANK (A/C XX6034)", 4100, "axis_6034"),
            ("SFT-016(TD)", "Interest from deposit", "ICICI BANK", 21000, "icici_8817"),
            ("SFT-018", "Purchase of mutual fund units", "BANDHAN MUTUAL FUND", 96000, "bandhan_3390"),
            ("TDS-192", "Salary", "ORIONSOFT TECHNOLOGIES PVT LTD", 1350000, None)]
pdf = FPDF(orientation="L", unit="mm", format="A4"); pdf.add_page()
pdf.set_font("Helvetica", "B", 14); pdf.cell(0, 9, "Annual Information Statement (AIS) - SAMPLE DATA", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Helvetica", "", 10); pdf.cell(0, 6, "Name: SRIJAN MALHOTRA   PAN: XXXXX4129M   Financial Year: 2024-25", new_x="LMARGIN", new_y="NEXT"); pdf.ln(4)
w = [12, 32, 70, 110, 40]; hd = ["Sr", "Information Code", "Information Description", "Information Source", "Amount (Rs)"]
pdf.set_font("Helvetica", "B", 10)
for wi, h in zip(w, hd):
    pdf.cell(wi, 8, h, border=1)
pdf.ln(); pdf.set_font("Helvetica", "", 10)
for i, (c, d, s, a, _) in enumerate(ais_rows, 1):
    for wi, v in zip(w, [str(i), c, d, s, inr(a)]):
        pdf.cell(wi, 8, v, border=1)
    pdf.ln()
pdf.ln(4); pdf.set_font("Helvetica", "I", 9); pdf.cell(0, 6, "Synthetic document for a hackathon demo. Not a real tax record.")
pdf.output(str(OUT / "ais.pdf"))

# PHOTOS
from PIL import Image, ImageDraw, ImageFont, ImageFilter
def font(sz, b=False):
    for n in (["DejaVuSans-Bold.ttf"] if b else ["DejaVuSans.ttf"]):
        try:
            return ImageFont.truetype(n, sz)
        except OSError:
            pass
    return ImageFont.load_default(size=sz)
def paper(w, h):
    img = Image.new("RGB", (w, h), (244, 238, 220)); d = ImageDraw.Draw(img)
    for _ in range(3000):
        x, y = rng.randint(0, w - 1), rng.randint(0, h - 1); c = rng.randint(225, 245); d.point((x, y), fill=(c, c - 6, c - 22))
    return img, d
PHOTOS.mkdir(parents=True, exist_ok=True)
img, d = paper(1400, 1000)
d.text((60, 40), "PUNJAB NATIONAL BANK - SAVINGS FUND PASSBOOK", font=font(34, True), fill=(110, 20, 30))
d.text((60, 95), "Branch: Lajpat Nagar, New Delhi      A/c No: XXXXXXX2045", font=font(24), fill=(20, 20, 20))
d.text((60, 130), "Name: SRIJAN MALHOTRA      Nomination: ____ (not registered)", font=font(24), fill=(20, 20, 20))
cols = [60, 260, 760, 960, 1160]
for x, h in zip(cols, ["Date", "Particulars", "Withdrawal", "Deposit", "Balance"]):
    d.text((x, 200), h, font=font(24, True), fill=(20, 20, 20))
d.line((50, 240, 1350, 240), fill=(90, 90, 90), width=2)
for r, row in enumerate([("14-06-2012", "BY CASH", "", "25,000.00", "25,000.00"), ("02-01-2013", "BY CLG", "", "18,000.00", "43,000.00"), ("30-09-2013", "INT CREDIT", "", "1,200.00", "44,200.00"), ("11-03-2014", "BY TRANSFER", "", "3,800.00", "48,000.00")]):
    y = 265 + r * 60
    for x, v in zip(cols, row):
        d.text((x, y), v, font=font(24), fill=(25, 25, 60))
d.text((60, 900), "SAMPLE DATA - synthetic passbook for a hackathon demo", font=font(22, True), fill=(180, 60, 40))
img.rotate(-1.6, expand=True, fillcolor=(60, 60, 60)).filter(ImageFilter.GaussianBlur(0.6)).save(PHOTOS / "pnb_passbook.png")
img, d = paper(1100, 1400)
d.text((60, 60), "POLICY SCHEDULE - TERM LIFE INSURANCE", font=font(36, True), fill=(20, 40, 90))
d.text((60, 120), "Insurer: Max Life Insurance", font=font(28, True), fill=(20, 20, 20))
for i, (k, v) in enumerate([("Policy No.", "XXXXXX4472"), ("Life Assured", "SRIJAN MALHOTRA"), ("Plan", "Smart Term Plan"), ("Sum Assured", "Rs 25,00,000"), ("Annual Premium", "Rs 21,600"), ("Nominee", "NEHA MALHOTRA (Spouse)")]):
    y = 220 + i * 90; d.text((60, y), k, font=font(28), fill=(60, 60, 60)); d.text((520, y), v, font=font(30, True), fill=(20, 20, 20))
d.text((60, 1280), "SAMPLE DATA - synthetic document for a hackathon demo", font=font(24, True), fill=(180, 60, 40))
img.rotate(0.9, expand=True, fillcolor=(60, 60, 60)).filter(ImageFilter.GaussianBlur(0.5)).save(PHOTOS / "maxlife_policy.png")

# GROUND TRUTH
def eids(tag, src):
    return [r["id"] for r in sms if r["tag"] == tag] if src == "sms" else [e["id"] for e in emails if e["tag"] == tag]
ais_ids = {t: f"ais_{i:02d}" for i, (*_, t) in enumerate(ais_rows, 1) if t}
assets = [
    dict(id="axis_6034", institution="Axis Bank", asset_type="savings_account", identifier="XX6034", value=140000, known_to_family=True, nominee="yes", expected_status="active", expected_claim_path="nominee"),
    dict(id="epf_5521", institution="EPFO", asset_type="provident_fund", identifier="XXXXXXXX5521", value=680000, known_to_family=False, nominee="unknown", expected_status="active", expected_claim_path="epf_claim"),
    dict(id="maxlife_4472", institution="Max Life", asset_type="life_insurance", identifier="XXXXXX4472", value=2500000, known_to_family=False, nominee="yes", expected_status="active", expected_claim_path="insurance_death_claim"),
    dict(id="bandhan_3390", institution="Bandhan Mutual Fund", asset_type="mutual_fund", identifier="XXXXXXX3390", value=410000, known_to_family=False, nominee="unknown", expected_status="active", expected_claim_path="transmission"),
    dict(id="icici_8817", institution="ICICI Bank", asset_type="fixed_deposit", identifier="XX8817", value=300000, known_to_family=False, nominee="no", expected_status="active", expected_claim_path="simplified_no_nominee"),
    dict(id="indus", institution="Indus Polymers", asset_type="shares", identifier="IP20774", value=120000, known_to_family=False, nominee="unknown", expected_status="transferred_iepf", expected_claim_path="iepf_refund"),
    dict(id="pnb_2045", institution="Punjab National Bank", asset_type="savings_account", identifier="XXXXXXX2045", value=48000, known_to_family=False, nominee="no", expected_status="transferred_dea", expected_claim_path="dea_claim_via_bank"),
]
photo_for = {"pnb_2045": ["photo_pnb_passbook"], "maxlife_4472": ["photo_maxlife_policy"]}
for a in assets:
    a["key_evidence"] = eids(a["id"], "sms") + eids(a["id"], "email") + ([ais_ids[a["id"]]] if a["id"] in ais_ids else []) + photo_for.get(a["id"], [])
    a["value_source"] = {"indus": "IEPF portal", "pnb_2045": "UDGAM portal"}.get(a["id"], "evidence")
truth = {"case": {"deceased_name": "Srijan Malhotra", "date_of_death": DEATH.date().isoformat(), "as_of": "2026-10-24"},
         "counts": {"sms": len(sms), "emails": len(emails), "ais_rows": len(ais_rows), "photos": 2, "sms_relevant_planted": relevant},
         "assets": assets, "total_value": sum(a["value"] for a in assets), "known_value": sum(a["value"] for a in assets if a["known_to_family"])}
(OUT / "ground_truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")

portals = {"UDGAM": [{"name": "SRIJAN MALHOTRA", "bank": "Punjab National Bank", "branch": "Lajpat Nagar, New Delhi", "account_masked": "XXXXXXX2045", "amount": 48000, "udrn": "UDRN2026PNB0031187", "transferred_to_dea": "2024-04-30"}],
           "IEPF": [{"holder": "SRIJAN MALHOTRA", "company": "Indus Polymers Ltd", "folio": "IP20774", "shares": 600, "share_value": 111000, "unclaimed_dividend": 9000, "total": 120000, "transferred_on": "2025-10-28"}]}
(OUT / "portal_records_to_merge.json").write_text(json.dumps(portals, indent=2), encoding="utf-8")

print(f"SMS {len(sms)} ({relevant} planted)  Emails {len(emails)}  AIS {len(ais_rows)}  Photos 2")
print(f"Assets {len(assets)}  Total Rs {inr(truth['total_value'], False)}  Known Rs {inr(truth['known_value'], False)}")
