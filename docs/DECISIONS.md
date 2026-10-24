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
