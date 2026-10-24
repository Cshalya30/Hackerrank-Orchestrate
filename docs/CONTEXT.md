# CONTEXT: handoff — paste into any AI to continue

Last updated: 2026-10-25T11:30+05:30, by Claude Code (Sonnet 5), final session
(reconciled a parallel-session incident, error audit, pipeline visualizer,
final packaging).

## HANDOFF SUMMARY (read this first)
- What works: full pipeline runs end to end, LLM-backed intent
  classification. `output.csv` at repo root, 518 rows, passes
  `code/validate.py`. Distribution: COMPLETE=211, INCOMPLETE=297,
  NOT_APPLICABLE=10.
- **Final, reproducible scores** (32 public samples vs
  `dataset/sample_output.csv`): status accuracy **0.812**, step F1
  **0.706** (precision 0.807 / recall 0.627), sequence accuracy **0.156**.
  Verified by a clean-shell re-run of the full command sequence in
  `code/README.md`. See `docs/EVAL_LOG.md` for every intermediate run.
- `GEMINI_API_KEY` is configured (`.env`, never printed/logged). Intent
  classification (`code/intent.py`, 3-label: DELETE_REQUEST /
  DELETION_VERIFICATION / OTHER_SERVICE) runs on `gemini-flash-lite-latest`
  (thinking off), batched/cached. Screenshot parsing
  (`code/ingest/image_parser.py`) works but is **not** part of the committed
  pipeline — see "Known gaps" below.
- **Incident this session:** an earlier session (misplaced cwd) never
  actually stopped and kept editing/committing in parallel. Reconciled — see
  `log.txt`'s "Parallel-session incident" entry and `docs/DECISIONS.md`
  D8-D10 for the full trace of what was tried, what looked like an
  improvement, and why it was re-reverted.
- Known gaps (ranked by likely score impact):
  1. **Screenshot (PNG) evidence is not merged.** `code/ingest/image_parser.py`
     parses all 11 cleanly, but two separate merge attempts moved sample F1
     in opposite directions across different runs — the vision model's
     per-call row extraction is not perfectly deterministic for the same
     cached image, so the net effect on F1 cannot be trusted. See
     `docs/DECISIONS.md` D8/D9/D10. A future session with more time budget
     should run the same image through the vision call 3-5 times and diff
     the extracted rows before re-attempting a merge.
  2. **157 full-run cases have no resolvable `account_service` id** even
     after `account_linker.py`'s batch-matching/fallback chain — several of
     these accounts have zero evidence anywhere in the corpus.
  3. **SUPPORT_ATTACHMENT vs SUPPORT_MESSAGE** still not reliably
     distinguished beyond the two PDF-backed cases wired in RUN2 Group B5.
- Next actions, in priority order:
  1. If re-attempting the screenshot merge, first establish determinism
     (repeat calls, diff output) rather than trusting a single run's score.
  2. Investigate the 157 unresolved `account_service` ids.
  3. Continue the SUPPORT_ATTACHMENT/SUPPORT_MESSAGE heuristic work.
  4. Re-run the sample eval after each fix and append a row to
     `docs/EVAL_LOG.md`; only keep a change that improves step F1 or status
     accuracy (owner's rule — revert and note anything that doesn't help).

## Who and what
- Chirantan, solo entrant, HackerRank Orchestrate October 2026, "Ghost Data Still Exists".
- Owner-supplied deadline: 2026-10-25T18:00:00+05:30.
- Repo root: `D:\Users\Chirantan\Documents\Competitions - 5th Sem\Hackerrank orchestrate\project` (cloned from `github.com/interviewstreet/hackerrank-orchestrate-october26`).
- Never submit to HackerRank from this session or any continuation — the owner submits personally; submission starts their interview.

## Problem in one paragraph
518 data-deletion requests. For each, decide COMPLETE / INCOMPLETE / NOT_APPLICABLE and output an ordered JSON list of FINDING / REMEDIATION / VERIFICATION steps over (system_id, resource_id) with evidence citations. Evidence: 94 files (24 SQL dumps, 28 JSON + 1 TXT, 26 logs, 4 PDFs, 11 screenshots) plus identities (850), identity change log (306), 4011 activity claims, 15 deletion rules. 32 solved samples (0 NOT_APPLICABLE, 22 INCOMPLETE, 10 COMPLETE).

## Key decisions (full detail in docs/DECISIONS.md)
1. Evaluation artifacts go under `code/evaluation/`, not root `evaluation/`.
2. Evidence-first: parse the shared corpus once into `build/observations.jsonl`; per-case logic is deterministic except the one Gemini intent call.
3. Point-in-time state at `audit_at`; file evidence outranks activity claims; PRESENT beats ABSENT on ties; once PII-linked, a resource stays linked even after later anonymization ("resource continuity").
4. One consolidated `code/ingest/build.py` instead of five parser modules; `system_activity.csv` is ingested directly; a targeted `parse_pdf()` handles the two PDFs that are cited evidence.
5. `account_linker.py` resolves every case's `account_service` id and, where real evidence supports it, a retained `security_service` audit record — via direct identity link -> same-day activity-batch matching -> zero-padded fallback, never guessing.
6. `planner.finalize()` only sets NOT_APPLICABLE from intent classification, never from an empty step list.
7. LLM (Gemini Flash-Lite via `google-genai`, thinking off) is scoped to request-intent classification only (3-label, batched 25/call, disk-cached). Screenshot parsing exists (`code/ingest/image_parser.py`) but is not wired into the committed pipeline (see D8-D10). Caching + a token ledger live in `code/llm.py`; `tools/usage_report.py` turns the ledger into `code/evaluation/usage_report.md`.
8. Determinism/reproducibility was weighted over a small, unconfirmed F1 gain from screenshot merging — see D10.

## Status checklist
- [x] RUN1 Cards 0-7: full pipeline, sample eval 0.750/0.529/0.062 -> 0.812/0.706/0.156
- [x] RUN2 Groups A/B/C: account_linker.py, field-extraction fixes, resource-continuity overlay, category-aware states, PDF parsing, NOT_APPLICABLE reasons printed
- [x] Gemini intent: 3-label scheme (DELETE_REQUEST/DELETION_VERIFICATION/OTHER_SERVICE) on `gemini-flash-lite-latest`, thinking off, batched/cached; sample-split gate enforces 0 NOT_APPLICABLE; full run: 10 NOT_APPLICABLE, all via CLASSIFY_REQUEST
- [x] Screenshot parsing: built, works, tried twice, found non-reproducible, not merged (D8-D10)
- [x] Parallel-session incident: discovered, owner stopped the old session, reconciled (nothing lost, everything verified before keeping)
- [x] Error audit: validate.py passes, clean-shell reproduce sequence confirmed, secret scan clean, custom cases 3/3 pass
- [x] Pipeline visualizer: `tools/viz/export_stats.py` + `tools/viz/index.html`, verified with Playwright (0 console errors, node click + case search both work)
- [x] Final packaging: `code/README.md`, `submission/` (code.zip, output.csv, chat_transcript.txt, SUBMISSION_CHECKLIST.md, INTERVIEW_PREP.md), tagged `v1-final`

## Current eval scores
Sample (32 cases, `dataset/sample_output.csv`): status accuracy 0.812, sequence accuracy 0.156, step precision/recall/F1 0.807/0.627/0.706.
Full run (518 cases): no gold answers exist for this split (by design); `output.csv` passes `code/validate.py`'s contract checks. Distribution: COMPLETE=211, INCOMPLETE=297, NOT_APPLICABLE=10.

## Rules for whoever continues
- Never submit to HackerRank. Submission starts the owner's interview; owner submits.
- Keep `log.txt` (repo root, beside AGENTS.md) honest and complete per AGENTS.md section 5. `tool=` and `model=` must be exact, non-placeholder values on every entry.
- Never open `dataset/evidence/` files or large CSVs with a Read-style tool; inspect via small scripts with capped printed output, full output to `build/`.
- Only keep a change if a sample-eval re-run shows it helps AND reproduces on a second run (owner's rule, sharpened after the screenshot-merge non-determinism finding) — log every attempt, including reverted ones, in docs/EVAL_LOG.md and docs/DECISIONS.md.
- `.env` is real-secret territory — never commit it, never print its contents; `.env.example` documents the one variable it needs (`GEMINI_API_KEY`).
- Before starting work, check `Get-CimInstance Win32_Process` (or equivalent) for any stray process pointing into this project folder — there was a real incident this session of an old session never stopping and racing a new one.
