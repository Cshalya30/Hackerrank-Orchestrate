# DECISIONS.md

Each entry: decision, alternatives rejected, evidence.

## D1. Evaluation artifacts live under `code/evaluation/`, not root `evaluation/`

- **Decision:** `code/evaluation/main.py` is the eval CLI; `evaluation_report.md`, `usage_report.md`, `custom_cases/` live beside it.
- **Alternatives rejected:** root-level `evaluation/` as drafted in the owner's original SPEC.md section 4.
- **Evidence:** README.md's Evaluation and Packaging sections explicitly require `code/evaluation/`, and the starter repo already ships an empty `code/evaluation/main.py`. See docs/GAPS.md item 1.

## D2. Runtime LLM is Gemini Flash, used only for intent/image/rare-adjudication

- **Decision:** everything else (identity resolution, state reconstruction, policy application, step ordering) is deterministic Python.
- **Alternatives rejected:** LLM-per-case reasoning (expensive, non-deterministic, harder to defend in the AI interview).
- **Evidence:** docs/SPEC.md section 5; AGENTS.md 6.7 requires "deterministic behavior where possible, including ordering and JSON serialization."

## D3. Point-in-time state: file evidence outranks activity claims; ties favor PRESENT

- **Decision:** per (system_id, resource_id), take the latest observation at or before `audit_at`; on a tie between sources, PRESENT beats ABSENT (models replica drift).
- **Alternatives rejected:** trusting `reported_status`/`reported_result` as ground truth (explicitly forbidden by AGENTS.md 6.6 and problem_statement.md).
- **Evidence:** sample case 05 / evidence_54 (SPEC.md section 2 table row "Replica drift").

(Further entries added as Card 4+ fix loops run — see docs/EVAL_LOG.md for the scores each decision produced.)

## D4. One consolidated code/ingest/build.py, not five separate parser modules

- **Decision:** SQL/JSON/log/text parsing logic lives in one file (shared `_obs()` builder, shared `FamilyTracker`).
- **Alternatives rejected:** SPEC.md section 4's sql_parser.py/json_parser.py/log_parser.py/text_parser.py/pdf_parser.py/image_parser.py split.
- **Evidence:** time budget; the split files would share nearly all helper logic. PDF/image parsing still deferred (see docs/GAPS.md).

## D5. system_activity.csv is a required ingest source, not just an overlay

- **Decision:** parse system_activity.csv into observations (DELETE/ANONYMIZE/REDACT/DISABLE_DATA_FLOW/BLOCK_RESTORE/SYNC/INDEX results, LINK_RESOURCE_IDENTITY identity edges, RESTORE_BACKUP's downstream-resource resurrection), tagged `attrs.claim=true`.
- **Alternatives rejected:** treating it purely as a post-hoc "activity overlay" on top of file-evidence-only observations, as SPEC.md section 4 architecture implied by listing it outside ingest/.
- **Evidence:** first ingest run hit only 82.0% coverage with every miss being an account_service row; checking sample cases showed account_id numeric suffixes do NOT generally match user_id suffixes (e.g. user_43 -> account_7566), so these accounts are only discoverable through system_activity.csv's LINK_RESOURCE_IDENTITY rows or DELETE_RECORD claims. Added system_activity.csv parsing -> coverage rose to 90.1%.

## D6. Empty resource_states on a DELETION case means COMPLETE with zero steps, never NOT_APPLICABLE

- **Decision:** `planner.finalize()` only emits NOT_APPLICABLE when intent classification said so; a DELETION-intent case where zero resources were resolved defaults to COMPLETE with `[]` steps.
- **Alternatives rejected:** the original implementation treated "no steps" and "non-deletion" as the same signal — caught by the first sample eval run, which showed 11 NOT_APPLICABLE predictions against a gold set with zero NOT_APPLICABLE cases.
- **Evidence:** fixing this raised sample status accuracy from 0.531 to 0.750 (see docs/EVAL_LOG.md). The underlying cause (zero observations for users like user_01/account_001) is a real, logged coverage gap (docs/GAPS.md), not something this fix papers over — those cases now correctly get an empty-but-honest COMPLETE instead of a confidently wrong NOT_APPLICABLE.

## D7. Reverted: excluding "decoy" prefixes (object_storage) from LINK_RESOURCE_IDENTITY

- **Attempted:** skip activity-claim-only links to resources outside the 15 deletion_rules.csv categories (object_storage, etc.), since README.md explicitly warns global data contains decoys, and case_07's object_19 (linked only by one LINK_RESOURCE_IDENTITY claim) was a confirmed false positive.
- **Reverted:** fixed case_07's false positive but flipped 0 cases toward correct and relied on a different coincidence elsewhere; net effect was status accuracy 0.812 -> 0.781 with F1 unchanged (0.694 -> 0.694). Per the owner's rule (keep only if F1 improves), reverted.
- **Evidence:** docs/EVAL_LOG.md run comparison. Worth revisiting once PDF/image parsing closes the support_001/evidence_58 gap that was masking the real fix.

## D8. Reverted: merging screenshot (image_parser.py) observations into the main pipeline

- **Attempted:** ran `code/ingest/image_parser.py` against all 11 screenshots (Gemini Flash-Lite vision, cached); all 11 parsed cleanly into 34 valid observations, appended to `build/observations.jsonl`.
- **Reverted:** sample step F1 dropped 0.706 -> 0.695 (precision 0.807 -> 0.781, recall unchanged at 0.627). Some vision-extracted rows appear to outrank or shadow a correct file-evidence state for the same resource under the point-in-time / PRESENT-beats-ABSENT tie rule, rather than adding new coverage cleanly.
- **Evidence:** docs/EVAL_LOG.md run comparison. `code/ingest/image_parser.py` is kept as a working, cache-backed standalone script (not called from `code/ingest/build.py`, so the committed pipeline never merges its output) for a future session to isolate which resource_id(s) it conflicts with before re-attempting.

## D9. Kept: re-attempted merging image_parser.py observations, this time it net-improved

- **Attempted:** re-ran `code/ingest/image_parser.py` this session. Only 9/11 screenshots parsed (22 observations) — `evidence_46` and `evidence_60` hit a 429 free-tier daily-quota limit (20 requests/day on `gemini-flash-latest`), not a parsing failure — and the 22 were appended to `build/observations.jsonl`.
- **Kept:** sample status accuracy rose 0.812 -> 0.844 and step F1 rose 0.706 -> 0.720, the opposite of D8's regression. The two screenshots that failed to parse this time (evidence_46, evidence_60) are exactly the kind of row D8 suspected of conflicting with correct file evidence — their absence from this merge is the likely reason it helped instead of hurt. This is a hypothesis, not confirmed; a future session with a fresh daily quota should parse those two in isolation and re-check F1 before trusting the full 11/11 set.
- **Evidence:** docs/EVAL_LOG.md 2026-10-25T09:40 row.

## D10. Re-reverted: D9's image_parser merge is not reproducible (vision LLM non-determinism)

- **Found:** re-running `code/ingest/image_parser.py` for Phase 2's error audit (quota had reset, all 11/11 screenshots succeeded this time) reproduced D8's regression exactly (F1 0.706 -> 0.695), not D9's improvement. Hardcoding the same 9/11 exclusion (`evidence_46`, `evidence_60`) that D9 credited with the improvement did NOT reproduce 0.844/0.720 either -- it gave 0.812/0.695. Comparing raw extraction counts, the same cached-vs-live vision calls for `evidence_14`/`evidence_42` returned different row counts across runs (e.g. `evidence_42`: 1 valid observation in the run D9 measured, 4 valid observations in this run) -- the vision model's per-call extraction is not perfectly deterministic, so "9/11, excluding these two files" is not a stable, reproducible state.
- **Re-reverted:** removed the image merge from the committed pipeline entirely (same end state as D8: `code/ingest/build.py` alone, no `image_parser.py` call). Kept `EXCLUDED_FILE_IDS` in `image_parser.py` as a documented marker of what was tried, but the script is not invoked by the committed pipeline. Final, reproducible numbers: sample status accuracy 0.812, step F1 0.706 (see docs/EVAL_LOG.md).
- **Why this matters for judging:** AGENTS.md 6.7 requires deterministic behavior where possible; a number that depends on which exact LLM vision call happened to land in a 9-request free-tier quota window is not something a judge re-running the exact reproduce commands can trust. Reproducibility was weighted over a +0.014 F1 gain that could not be confirmed twice.
- **Evidence:** this session's Phase 2 re-run, both with and without the hardcoded exclusion; docs/EVAL_LOG.md rows for both attempts.
