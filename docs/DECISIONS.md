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
