# Submission Checklist

Generated 2026-10-25, final reconciled session. Verify every line below
before submitting — this session does not submit on your behalf.

## Contents of this folder

| File | What it is | Verified |
|---|---|---|
| `code.zip` | Runnable code, `README.md`, `code/evaluation/` reports, `tools/` (incl. viz), `docs/`, `requirements.txt`, `.env.example`. Excludes `.venv`, `.env`, `build/`, `__pycache__`, `dataset/`. | Secret-scanned clean by `tools/make_zip.py` (see output below) |
| `output.csv` | 518 rows, the full-run submission output | `code/validate.py` passed (row count, sort order, step ordering/numbering, evidence-citation rules) |
| `chat_transcript.txt` | Copy of `log.txt` (repo root) — the full session log per AGENTS.md | Includes the parallel-session incident and its reconciliation |
| `SUBMISSION_CHECKLIST.md` | This file | — |
| `INTERVIEW_PREP.md` | Interview prep notes (pitch, architecture, failure stories, hard questions) | — |

## Before you submit

- [ ] Open `code.zip` and spot-check: no `.env`, no `.venv`, no `dataset/`, no `__pycache__`, no nested archives.
- [ ] Re-run the command sequence in `code/README.md` once more yourself if you have time — it reproduced 0.812 status accuracy / 0.706 step F1 at generation time (see `code/evaluation/evaluation_report.md`).
- [ ] `output.csv` here matches the one `code/validate.py` last validated — if you touch the pipeline again before submitting, re-copy it.
- [ ] Confirm no stray Python process from an old session is still running before you do anything else with this repo (`Get-CimInstance Win32_Process | Where-Object CommandLine -like '*Hackerrank orchestrate*'` on Windows) — this bit us once this session.
- [ ] Read `INTERVIEW_PREP.md` once before the interview; it has the 60-second pitch, the architecture walkthrough, and the failure stories you'll likely be asked about.
- [ ] Decide whether you want to demo `tools/viz/index.html` live (`python -m http.server 8765 -d tools/viz`) — it's built and tested, but test it once yourself on your interview machine beforehand.

## Known gaps (tell the interviewer proactively, don't wait to be caught)

1. Screenshot (PNG) evidence parsing works but isn't merged into the pipeline — tried twice, found non-reproducible (vision LLM non-determinism), reverted both times for reproducibility. See `docs/DECISIONS.md` D8-D10.
2. 157 full-run cases have no resolvable `account_service` id.
3. SUPPORT_ATTACHMENT vs. SUPPORT_MESSAGE disambiguation is incomplete beyond two PDF-backed cases.
4. A parallel-session race happened mid-build (an old session never stopped) — fully reconciled and logged, but worth mentioning if asked about process/safety.

## Final numbers (reproducible)

- Status accuracy: **0.812** (26/32 sample cases)
- Step F1: **0.706** (precision 0.807 / recall 0.627)
- Sequence accuracy: **0.156** (5/32)
- Full run: 518/518 rows valid — COMPLETE=211, INCOMPLETE=297, NOT_APPLICABLE=10
- LLM usage: 17 calls, ~44K tokens, ~$0.006 at list price (see `code/evaluation/usage_report.md`)
