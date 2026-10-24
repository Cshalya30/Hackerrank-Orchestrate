# CONTEXT: handoff — paste into any AI to continue

Last updated: 2026-10-24T22:20+05:30, by Claude Code (Sonnet 5), autonomous session.

## HANDOFF SUMMARY (read this first)
- What works: full pipeline runs end to end. `output.csv` exists at repo root,
  518 rows, passes `code/validate.py` (contract-valid: sort order, step
  numbering/ordering, evidence-citation rules, operation/state consistency).
  Distribution: COMPLETE=304, INCOMPLETE=208, NOT_APPLICABLE=6.
- Scores (32 public samples vs `dataset/sample_output.csv`): status accuracy
  **0.750**, step F1 **0.529** (precision 0.880 / recall 0.378), sequence
  accuracy **0.062**. Full numbers + 4 logged failure->fix pairs in
  `code/evaluation/evaluation_report.md`.
- Top known risks (ranked by likely score impact):
  1. **PDF/PNG evidence unparsed** (4 PDF, 11 PNG) — needs `GEMINI_API_KEY` for
     images; PDFs are parseable now (pypdf installed) but no parser is wired
     up yet. Primary suspected cause of the ~10% coverage gap and most of the
     0.378 recall loss.
  2. **SUPPORT_ATTACHMENT vs SUPPORT_MESSAGE** not reliably distinguished —
     `support_records` rows all share the same `support_` resource prefix with
     no field indicating "owned only by subject" vs "shared context".
  3. **Some accounts have zero evidence anywhere** (e.g. sample `case_01`'s
     `account_001`) — likely only provable via the skipped PDF/PNG evidence.
  4. **Deterministic intent fallback won't generalize** beyond the phrasing
     patterns already coded into `NON_DELETION_HINTS` — an LLM key removes
     this ceiling entirely.
- Next actions, in priority order:
  1. Get a `GEMINI_API_KEY` into `.env`, then write `code/ingest/image_parser.py`
     (vision call -> the observation schema in docs/SPEC.md 4.1, validated,
     cached) and a `pdf_parser.py` pass over the 4 PDFs — re-run
     `code/ingest/build.py`, check `build/coverage.txt` for the jump.
  2. Re-point `code/intent.py` at the real LLM path (batches of 25 distinct
     `request_text` strings) once the key exists; keep the deterministic
     fallback as the no-key path, not a replaced one.
  3. Investigate the SUPPORT_ATTACHMENT/SUPPORT_MESSAGE ambiguity by profiling
     `message_excerpt` content for multi-party language ("agent", "order",
     a second name) vs. single-subject content.
  4. Re-run the sample eval after each fix and append a row to
     `docs/EVAL_LOG.md`; only keep a change that improves step F1 or status
     accuracy (owner's rule — revert and note anything that doesn't help).

## Who and what
- Chirantan, solo entrant, HackerRank Orchestrate October 2026, "Ghost Data Still Exists".
- Owner-supplied deadline: 2026-10-25T18:00:00+05:30 (not in repo; AGENTS.md says Oct deadline isn't configured there — owner instruction takes precedence, see docs/GAPS.md item 4).
- Repo root: `D:\Users\Chirantan\Documents\Competitions - 5th Sem\Hackerrank orchestrate\project` (cloned from `github.com/interviewstreet/hackerrank-orchestrate-october26`).
- Never submit to HackerRank from this session or any continuation — the owner submits personally; submission starts their interview.

## Problem in one paragraph
518 data-deletion requests. For each, decide COMPLETE / INCOMPLETE / NOT_APPLICABLE and output an ordered JSON list of FINDING / REMEDIATION / VERIFICATION steps over (system_id, resource_id) with evidence citations. Evidence: 94 files (24 SQL dumps, 28 JSON + 1 TXT, 26 logs, 4 PDFs, 11 screenshots) plus identities (850), identity change log (306), 4011 activity claims, 15 deletion rules. 32 solved samples (0 NOT_APPLICABLE, 22 INCOMPLETE, 10 COMPLETE).

## Key decisions (full detail in docs/DECISIONS.md)
1. Evaluation artifacts go under `code/evaluation/`, not root `evaluation/` — README.md overrides the original SPEC draft.
2. Evidence-first: parse the shared corpus once into `build/observations.jsonl`; per-case logic is deterministic.
3. Point-in-time state at `audit_at`; file evidence outranks activity claims; PRESENT beats ABSENT on ties.
4. One consolidated `code/ingest/build.py` instead of five parser modules; `system_activity.csv` is ingested directly (LINK_RESOURCE_IDENTITY, DELETE_RECORD, RESTORE_BACKUP), not treated as a pure post-hoc overlay.
5. `planner.finalize()` only sets NOT_APPLICABLE from intent classification, never from an empty step list — a DELETION case with zero resolved resources is COMPLETE with `[]`, which is "no evidence found," not "never asked."
6. LLM (Gemini Flash) is scoped to: request-intent classification, screenshot parsing, rare adjudication. No key is configured this session, so intent.py runs its deterministic fallback and image parsing hasn't been written yet.

## Status checklist
- [x] Repo cloned, AGENTS.md / README.md / problem_statement.md read in full
- [x] docs/SPEC.md (verbatim + README-deviation note), docs/GAPS.md, docs/DECISIONS.md, docs/EVAL_LOG.md created
- [x] Card 0: code/config.py, code/llm.py (cache+ledger+retries), .env.example, .gitignore, requirements.txt, venv created, deps installed
- [x] Card 1: code/evaluation/main.py (eval) + code/validate.py — proved 100% on sample_output vs itself
- [x] Card 2: tools/profile_evidence.py -> build/evidence_profile.txt (all 94 files profiled)
- [x] Card 3: code/ingest/build.py -> build/observations.jsonl (11881 obs), coverage 90.1% vs sample_output.csv
- [x] Card 4: code/resolve.py (identity+state) + code/planner.py (policy+planner) -> sample run -> eval (0.750 status acc, 0.529 step F1)
- [x] Card 5: code/intent.py deterministic fallback wired in; image_parser.py NOT written (blocked on GEMINI_API_KEY) — see Blocked
- [x] Card 6: full run -> output.csv (518 rows, validated), usage_report.md (honest 0-call baseline); zip script NOT written — see Blocked
- [x] Card 7: 1 fix loop on Card 4 (NOT_APPLICABLE bug) + 1 fix loop on Card 5/6 (intent hints); 3 custom cases written and passing; evaluation_report.md written with real numbers

## Current eval scores
Sample (32 cases, `dataset/sample_output.csv`): status accuracy 0.750, sequence accuracy 0.062, step precision/recall/F1 0.880/0.378/0.529, field accuracies in `code/evaluation/evaluation_report.md`.
Full run (518 cases): no gold answers exist for this split (by design); `output.csv` passes `code/validate.py`'s contract checks. Distribution: COMPLETE=304, INCOMPLETE=208, NOT_APPLICABLE=6.
Coverage: 90.1% of (system_id, resource_id) pairs required by `dataset/sample_output.csv` appear in `build/observations.jsonl` (`build/coverage.txt` lists the 11 misses).

## Blocked
- **No GEMINI_API_KEY.** Blocks: real LLM intent classification (deterministic fallback is in place and reasonably tuned — see docs/EVAL_LOG.md — but will not generalize to unseen non-deletion phrasing), and all image/screenshot parsing (11 PNGs, 0% parsed). Not blocking further work — just means the owner needs to supply a key and an agent needs to write `code/ingest/image_parser.py` next.
- **Not attempted, not blocked, just deprioritized under the time budget:** PDF parsing (pypdf is installed and works — see docs/GAPS.md item 6 verification — just not wired into `code/ingest/build.py` yet), a `tools/make_zip.py` / documented zip command for final submission packaging (README.md already gives the exact `Compress-Archive` command — no blocker, just not run since this isn't submission time).

## Rules for whoever continues
- Never submit to HackerRank. Submission starts the owner's interview; owner submits.
- Keep `log.txt` (repo root, beside AGENTS.md) honest and complete per AGENTS.md section 5. `tool=` and `model=` must be exact, non-placeholder values on every entry.
- Never open `dataset/evidence/` files or large CSVs with a Read-style tool; inspect via small scripts with capped printed output, full output to `build/`.
- Only keep a change if a sample-eval re-run shows it helps (owner's rule) — log every attempt, including reverted ones, in docs/EVAL_LOG.md and docs/DECISIONS.md.
- `.env` is real-secret territory — never commit it, never print its contents; `.env.example` documents the one variable it needs (`GEMINI_API_KEY`).
