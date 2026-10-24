# Ghost Assets (HACK-O-WEEN '26, The Afterlife Auditors)

Finds the money families never knew they inherited.

## Quick start
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt          # then pip install your LLM provider's SDK
copy .env.example .env                            # (cp on macOS/Linux) and fill in your key + model
python scripts/make_dataset.py                    # regenerates data/ramesh (already included)
```
Open the repo in Claude Code (`claude` in this folder). It reads `CLAUDE.md` automatically.
Follow the "Ghost Assets: Claude Code Build Guide" step by step.

## What's in the starter
- `CLAUDE.md`: the brief Claude Code works from (architecture, contracts, prompts, rules).
- `backend/models.py`: shared data contracts (complete).
- `backend/*.py`: stubs with signatures and docstrings, to be implemented step by step.
- `backend/rules.yaml`, `backend/portals_mock.json`: claim rules and mock portal records.
- `data/ramesh/`: synthetic case: 3,000 SMS, 60 emails, AIS PDF, 2 photos, ground truth, fake events.
- `scripts/check_against_truth.py`: verifies triage, assets and claim paths against the ground truth.

If your hackathon's rules ban pre-written code, keep only `CLAUDE.md`, `data/` and `scripts/`.

All data in `data/` is synthetic SAMPLE DATA.
