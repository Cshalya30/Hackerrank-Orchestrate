# CONTEXT: handoff — paste into any AI to continue

Last updated: 2026-10-25T09:50+05:30, by Claude Code (Sonnet 5), autonomous session (RUN2 + Gemini integration).

## HANDOFF SUMMARY (read this first)
- What works: full pipeline runs end to end, LLM-backed. `output.csv` exists at
  repo root, 518 rows, passes `code/validate.py`. Distribution:
  COMPLETE=210, INCOMPLETE=298, NOT_APPLICABLE=10.
- Scores (32 public samples vs `dataset/sample_output.csv`): status accuracy
  **0.844**, step F1 **0.720** (precision 0.812 / recall 0.648), sequence
  accuracy **0.156**. Started this session at 0.812/0.706/0.156 (see
  `docs/EVAL_LOG.md` for every intermediate run, kept and reverted).
- `GEMINI_API_KEY` is configured (`.env`, never printed/logged). Both LLM
  consumers are live: `code/intent.py` (3-label DELETE_REQUEST /
  DELETION_VERIFICATION / OTHER_SERVICE classification, batched/cached) and
  `code/ingest/image_parser.py` (screenshot evidence -> observations).
- Top known risks (ranked by likely score impact):
  1. **2 of 11 screenshots still unparsed** (`evidence_46`, `evidence_60`) —
     hit the Gemini free tier's 20-requests/day cap, not a bug. Re-run
     `code/ingest/image_parser.py` once the quota resets (cached results for
     the other 9 are reused for free) to pick these up.
  2. **157 full-run cases have no resolvable `account_service` id** even
     after `account_linker.py`'s batch-matching/fallback chain — a real
     coverage gap, not a bug; several of these accounts have zero evidence
     anywhere in the corpus (confirmed via direct lookup).
  3. **SUPPORT_ATTACHMENT vs SUPPORT_MESSAGE** still not reliably
     distinguished beyond the two PDF-backed cases wired in RUN2 Group B5.
- Next actions, in priority order:
  1. Once the Gemini daily quota resets, re-run `code/ingest/image_parser.py`
     for `evidence_46`/`evidence_60` and re-check sample F1 before trusting
     the full 11/11 screenshot set (see `docs/DECISIONS.md` D9 — the 9/11
     partial merge helped, the earlier 11/11 attempt (D8) hurt; this may not
     be a coincidence, so verify rather than assume more is better).
  2. Investigate the 157 unresolved `account_service` ids — check whether any
     are reachable via the 2 still-unparsed screenshots.
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
1. Evaluation artifacts go under `code/evaluation/`, not root `evaluation/` — README.md overrides the original SPEC draft.
2. Evidence-first: parse the shared corpus once into `build/observations.jsonl`; per-case logic is deterministic except the two Gemini calls below.
3. Point-in-time state at `audit_at`; file evidence outranks activity claims; PRESENT beats ABSENT on ties; once PII-linked, a resource stays linked even after later anonymization ("resource continuity").
4. One consolidated `code/ingest/build.py` instead of five parser modules; `system_activity.csv` is ingested directly; a targeted `parse_pdf()` handles the two PDFs that are cited evidence (support attachment, audit record retention extract).
5. `account_linker.py` resolves every case's `account_service` id and, where real evidence supports it, a retained `security_service` audit record — via direct identity link -> same-day activity-batch matching -> zero-padded fallback, in that priority order, never guessing.
6. `planner.finalize()` only sets NOT_APPLICABLE from intent classification, never from an empty step list.
7. LLM (Gemini Flash-Lite via the `google-genai` SDK, `gemini-flash-latest` model) is scoped to: request-intent classification (3-label, batched 25/call, disk-cached) and screenshot parsing (vision, one call per PNG, disk-cached). Everything else stays deterministic. Caching + a token ledger (`build/llm_ledger.jsonl`) live in `code/llm.py`; `tools/usage_report.py` turns the ledger into `code/evaluation/usage_report.md`.

## Status checklist
- [x] RUN1 Cards 0-7: full pipeline, sample eval 0.750/0.529/0.062 -> 0.812/0.706/0.156 (see prior EVAL_LOG rows)
- [x] RUN2 Group A: `account_linker.py` (direct link / same-day batch / zero-padded fallback) + audit-record wiring
- [x] RUN2 Group B: service_resource_export field-extraction fixes, resource-continuity overlay, category-aware log/activity default states, B5 PDF parsing (support attachment + audit record)
- [x] RUN2 Group C: NOT_APPLICABLE cases are printed with their reason (see full-run output; 10 cases, all via the CLASSIFY_REQUEST override)
- [x] Gemini step 1: `.env` wired via `python-dotenv`, `llm.py` smoke-tested (cache + ledger work) on the new `google-genai` SDK (the old `google-generativeai` package and `gemini-2.0-flash` model are both deprecated/retired)
- [x] Gemini step 2: `intent.py` on the LLM path (3-label, batched, cached); sample run shows 0/32 texts differ from the keyword fallback, full run shows 4/375 differ (all already forced NON_DELETION-equivalent by the CLASSIFY_REQUEST override, so no net effect either way) — kept per the integration instructions
- [x] Gemini step 3: `image_parser.py` run; 9/11 screenshots parsed (22 observations), 2 blocked on a 429 daily-quota limit (not a bug)
- [x] Gemini step 4: full run regenerated (518 rows, `output.csv`), `code/validate.py` passes, `usage_report.md` regenerated from the real ledger (32 calls, 44195 tokens, ~$0.006 at list price)
- [x] Gemini step 5: results logged in `docs/EVAL_LOG.md`; `docs/DECISIONS.md` D9 records the image-parser re-attempt (kept, unlike the earlier D8 revert)

## Current eval scores
Sample (32 cases, `dataset/sample_output.csv`): status accuracy 0.844, sequence accuracy 0.156, step precision/recall/F1 0.812/0.648/0.720.
Full run (518 cases): no gold answers exist for this split (by design); `output.csv` passes `code/validate.py`'s contract checks. Distribution: COMPLETE=210, INCOMPLETE=298, NOT_APPLICABLE=10.

## Blocked
- **Gemini free-tier daily quota (20 req/day) is exhausted** as of this session — blocks re-parsing `evidence_46`/`evidence_60` until it resets (~12-13h after the quota hit, or sooner on a paid key). Everything else (intent classification, the other 9 screenshots, the full run) completed inside the quota.
- **Not attempted, not blocked, just deprioritized under the time budget:** a `tools/make_zip.py` / documented zip command for final submission packaging (README.md already gives the exact `Compress-Archive` command — no blocker, just not run since this isn't submission time).

## Rules for whoever continues
- Never submit to HackerRank. Submission starts the owner's interview; owner submits.
- Keep `log.txt` (repo root, beside AGENTS.md) honest and complete per AGENTS.md section 5. `tool=` and `model=` must be exact, non-placeholder values on every entry.
- Never open `dataset/evidence/` files or large CSVs with a Read-style tool; inspect via small scripts with capped printed output, full output to `build/`.
- Only keep a change if a sample-eval re-run shows it helps (owner's rule) — log every attempt, including reverted ones, in docs/EVAL_LOG.md and docs/DECISIONS.md.
- `.env` is real-secret territory — never commit it, never print its contents; `.env.example` documents the one variable it needs (`GEMINI_API_KEY`).
