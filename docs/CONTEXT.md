# CONTEXT: handoff — paste into any AI to continue

Last updated: 2026-10-24T20:40+05:30, by Claude Code (Sonnet 5), autonomous session.

## HANDOFF SUMMARY (read this first)
- What works: repo cloned, skeleton in place, SPEC/GAPS/DECISIONS docs written, venv created with deps installed. No parsers, eval, or output yet.
- Scores: none yet (Card 1/4 not done).
- Top known risks: none hit yet; see "Blocked" below once populated.
- Next actions: Card 1 (eval.py + validate.py), then Card 2 (evidence profiler), then Card 3 (parsers).

## Who and what
- Chirantan, solo entrant, HackerRank Orchestrate October 2026, "Ghost Data Still Exists".
- Owner-supplied deadline: 2026-10-25T18:00:00+05:30 (not in repo; AGENTS.md says Oct deadline isn't configured there — owner instruction takes precedence, see docs/GAPS.md item 4).
- Repo root: `D:\Users\Chirantan\Documents\Competitions - 5th Sem\Hackerrank orchestrate\project` (cloned from `github.com/interviewstreet/hackerrank-orchestrate-october26`).

## Problem in one paragraph
518 data-deletion requests. For each, decide COMPLETE / INCOMPLETE / NOT_APPLICABLE and output an ordered JSON list of FINDING / REMEDIATION / VERIFICATION steps over (system_id, resource_id) with evidence citations. Evidence: 94 files (24 SQL dumps, 28 JSON + 1 TXT, 26 logs, 4 PDFs, 11 screenshots) plus identities (850), identity change log (306), 4011 activity claims, 15 deletion rules. 32 solved samples (0 NOT_APPLICABLE, 22 INCOMPLETE, 10 COMPLETE).

## Key decisions (full detail in docs/DECISIONS.md)
1. Evaluation artifacts go under `code/evaluation/`, not root `evaluation/` — README.md overrides the original SPEC draft.
2. Evidence-first: parse the shared corpus once into `build/observations.jsonl`; per-case logic is deterministic.
3. Point-in-time state at `audit_at`; file evidence outranks activity claims; PRESENT beats ABSENT on ties.
4. LLM (Gemini Flash) used only for: request-intent classification, screenshot parsing, rare adjudication. Everything else deterministic.

## Status checklist
- [x] Repo cloned, AGENTS.md / README.md / problem_statement.md read in full
- [x] docs/SPEC.md (verbatim + README-deviation note), docs/GAPS.md, docs/DECISIONS.md, docs/EVAL_LOG.md created
- [x] Card 0: code/config.py, code/llm.py (cache+ledger+retries), .env.example, .gitignore, requirements.txt, venv created, deps installed
- [x] Card 1: code/evaluation/main.py (eval) + code/validate.py — proved 100% on sample_output vs itself
- [ ] Card 2: tools/profile_evidence.py -> build/evidence_profile.txt
- [ ] Card 3: ingest parsers -> build/observations.jsonl + build/coverage.txt
- [ ] Card 4: identity.py, state.py, policy.py, planner.py -> sample run -> eval
- [ ] Card 5: intent.py + image_parser.py
- [ ] Card 6: full run -> output.csv, validate, usage_report, zip script
- [ ] Card 7: eval-driven fixes, custom cases, evaluation_report

## Current eval scores
sample_output vs itself: status_accuracy=1.000, sequence_accuracy=1.000, step_F1=1.000, all field accuracies=1.000 (self-check only; real pipeline not run yet).

## Blocked
Nothing yet.

## Rules for whoever continues
- Never submit to HackerRank. Submission starts the owner's interview; owner submits.
- Keep `log.txt` (repo root, beside AGENTS.md) honest and complete per AGENTS.md section 5. `tool=` and `model=` must be exact, non-placeholder values on every entry.
- Never open `dataset/evidence/` files or large CSVs with a Read-style tool; inspect via small scripts with capped printed output, full output to `build/`.
- No GEMINI_API_KEY is configured yet (no `.env` present) — intent.py must use its deterministic multilingual-keyword fallback + CLASSIFY_REQUEST override until the owner adds a key.
