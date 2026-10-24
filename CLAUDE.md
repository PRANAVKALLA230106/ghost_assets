# Ghost Assets: project brief for Claude Code

## What we are building (10-hour hackathon, demo at 6 PM)
When someone dies in India, their family can't find every bank account, FD, insurance policy,
mutual fund, share and PF they owned, so the money goes unclaimed. Ghost Assets is an AI agent
that, with the legal heir's consent, reads the trail the person left behind (SMS backup, email
export, tax statement (AIS), photos of old passbooks), builds a verified map of every asset, works out
where each asset sits now and which legal claim procedure applies, and generates a claim pack for each.

Demo case: **Ramesh Kumar**, died 2026-02-10. Family knew about Rs 3,00,000. The pipeline must find
**7 assets worth Rs 14,60,000**. Ground truth: `data/ramesh/ground_truth.json`.

## Architecture
```
uploads -> ingest -> triage (regex) -> extract (LLM, grounded) -> resolve (graph) -> rules (YAML) -> claim packs
                         ^------------------- agent (LLM tool loop) drives all of these -------------------^
every step emits SSE events -> React frontend (live graph, agent trace, questions, claim packs)
```
- Deterministic Python wherever correctness matters (triage, grounding, resolution, rules, claim text).
- The LLM is used ONLY in `extract.py` (reading text/images into a schema) and `agent.py` (deciding what to do next).
- All LLM calls go through `llm.py`, which caches every response on disk. Never call a provider SDK anywhere else.

## Repo layout
```
backend/   app.py models.py ingest.py triage.py llm.py extract.py resolve.py rules.py rules.yaml
           tools.py agent.py claimpack.py portals_mock.json cache/ requirements.txt
data/ramesh/   sms.xml emails.json ais.pdf photos/ ground_truth.json fake_events.jsonl
scripts/   make_dataset.py check_against_truth.py   (+ run_*.py scripts you create)
frontend/  Vite + React + TypeScript + Tailwind (created in step C1)
out/       pipeline outputs: evidence.json clues.json assets.json claims.json (git-ignored)
```
Run backend from `backend/`: `uvicorn app:app --reload --port 8000`. Frontend: `npm run dev` (port 5173).
Scripts are run from the repo root and import backend modules by adding `backend/` to `sys.path`.

## Contracts (frozen)
- `backend/models.py` is complete and shared. **Do not change it without the user explicitly approving.**
- Evidence IDs: `sms_0001` (file order in sms.xml), `email_001` (order in emails.json), `ais_01` (table data rows
  of ais.pdf, header excluded), `photo_<file stem>`. ground_truth.json depends on these exact IDs.
- SSE: each event is `{"type": ..., "data": ...}` with types:
  `progress {stage, done, total}`, `clue <Clue>`, `asset <Asset>`, `agent_step {thought, tool, args, result_summary}`,
  `question {id, text, options}`, `claim <Claim>`, `done {total_value, known_value, asset_count}`, `error {message}`.
- Routes: `GET /health`, `POST /cases`, `POST /cases/{id}/run`, `GET /cases/{id}/events` (SSE),
  `POST /cases/{id}/answers` `{question_id, answer}`, `GET /cases/{id}/assets/{asset_id}`,
  `GET /cases/{id}/assets/{asset_id}/claimpack.docx`. CORS allows `http://localhost:5173`.

## Extraction prompt (use verbatim in extract.py)
```
You extract financial asset clues from messages a person received.
For each message, return zero or more clues. A clue is evidence that the person held an account,
deposit, policy, fund, shareholding or provident fund.
Rules:
- evidence_id: copy the id of the message the clue came from.
- institution_raw: the bank/insurer/fund/company exactly as written (sender IDs like VM-CANBNK count).
- asset_type: one of savings_account, fixed_deposit, life_insurance, mutual_fund, shares, provident_fund, post_office, other.
- identifier: the account/FD/policy/folio number exactly as written, masked digits included (e.g. XX4521).
- amount: a number in rupees; amount_kind: balance, principal, maturity_value, sum_assured, premium,
  sip_instalment, dividend, interest, credit, debit, market_value or unknown.
- date: ISO date if the message states one. nominee: the nominee's name or "not registered" if stated.
- quote: the exact substring of the message that supports the clue. Copy, never paraphrase.
- A UPI payment to a shop or person is evidence of the account it was paid FROM, not a new asset.
- A premium or SIP debited from a bank account is evidence of BOTH the bank account and the policy/fund.
- Never invent values. Use null when a field is not in the text. Ignore OTPs, ads and offers.
Return JSON: {"clues": [{"evidence_id", "institution_raw", "asset_type", "identifier", "amount",
"amount_kind", "date", "nominee", "quote"}]}
```
Grounding check (extract.ground): reject a clue unless the quote appears in the text (case/whitespace-insensitive),
the identifier's last 4 characters appear in the text, and the amount equals some number in the text after
normalising Indian formats (`Rs.2,00,000`, `INR 200000.00`, `2,00,000/-`, `Rs 5000`). Log every rejection with its reason.

## Agent (agent.py + tools.py)
Tools: `scan_sources()`, `extract_clues(source)`, `build_asset_map()`, `search_evidence(query)`,
`read_photo(file)`, `check_portal(portal, name, institution)` (portal in UDGAM | IEPF | BIMA_BHAROSA; reads
portals_mock.json), `apply_claim_rules(asset_id)`, `ask_family(question, options)`,
`generate_claim_pack(asset_id)`, `finish(summary)`.
Tool results returned to the model must be SMALL summaries (IDs, counts, short lists), never raw dumps.

System prompt:
```
You are Ghost Assets, an agent that helps a legal heir find and claim every financial asset a
deceased person left. Work step by step:
1) scan and extract all sources (SMS, email, AIS, photos), 2) build the asset map,
3) investigate gaps: assets with weak evidence; old assets that may have moved to unclaimed funds
   (bank accounts silent 10+ years -> check UDGAM; shares whose dividends stopped 7+ years ago ->
   search the evidence for the company, then check IEPF); bank accounts or FDs with no nominee
   information -> ask the family,
4) apply claim rules to every asset, 5) generate a claim pack for every asset, 6) finish.
Use tools; never guess facts. Ask the family only when the evidence cannot answer.
Before each tool call, state your reason in one short sentence.
```
Expected demo moments: (1) passbook photo -> SBI XXXXXXX3307 silent since 2013 -> check_portal UDGAM -> transferred_dea;
(2) Ganga Tech dividends stop in 2017 -> search_evidence("Ganga Tech") finds the AGM email -> check_portal IEPF;
(3) no nominee info for Canara FD XX4521 -> ask_family -> answer "No" -> simplified_no_nominee.

## Rules
`rules.yaml` holds status and claim-path rules (first match wins). Simplified procedure threshold:
Rs 15 lakh per bank for commercial banks (Rs 5 lakh co-operative), summed across that bank's no-nominee assets.
Banks must settle within 15 calendar days of receiving all documents.

## Verification (run these, read the output)
- `python scripts/check_against_truth.py triage out/evidence.json`  -> every planted message kept
- `python scripts/check_against_truth.py assets out/assets.json`    -> 7 assets, values within 5%, no splits/extras
- `python scripts/check_against_truth.py claims out/assets.json out/claims.json` -> claim paths right
- `pytest backend -q`

## Conventions
- Python 3.11, type hints, Pydantic models from models.py, small functions, print-based logging with a stage prefix.
- Never hard-code Ramesh's numbers, IDs or answers into pipeline logic to pass a check. Fix the logic or the prompt.
- Keep LLM calls batched (20 evidence items per extraction call) and concurrent (Semaphore(4)).
- When unsure about a contract, ask the user instead of changing it.
- After finishing a step, run the step's verification command and report the result honestly.

## Team
Role A = pipeline (ingest, triage, extract, resolve). Role B = llm.py, rules, tools, agent, claim packs.
Role C = app.py fake events + frontend. Each works on its own git branch; merge at 9 AM, 1 PM, 3:30 PM.
