# GAPS.md — SPEC vs. AGENTS.md / README.md / problem_statement.md

Checked against the data with small scripts, not assumed. Append new findings below as they appear.

## 1. Evaluation report location differs from SPEC.md draft (confirmed, adapted)

- SPEC.md section 4 draws `evaluation/` at the repo root.
- `README.md` section "Evaluation" explicitly overrides: *"Place `evaluation_report.md` and `usage_report.md` inside `code/evaluation/` (matching `code/evaluation/main.py` in this starter layout)"* and the packaging section's zip commands only bundle `README.md` and `code/`.
- The starter repo ships an empty `code/evaluation/main.py` stub, confirming this placement is intentional.
- **Resolution:** reports, `eval.py` logic, and `custom_cases/` all live under `code/evaluation/`, not a root `evaluation/`. Noted at the bottom of docs/SPEC.md. `main.py` will double as the eval CLI entry point described by the starter layout.

## 2. "Automated code evaluation ignores raw data files" (README.md line ~99)

- `.csv, .tsv, .json, .jsonl, .sql, .log` content is invisible to the code judge and AI interviewer.
- **Implication:** prompts, decision rationale, and anything the judge/interviewer must see must live in `.py`/`.md` files, not only in `build/observations.jsonl` or similar. The planner's reasoning (policy table, identity rules) is already in `.py` + `docs/*.md`, which is correct. No code change needed, just a reminder for evaluation_report.md to restate the approach in prose, not just numbers.

## 3. Submission URL rule (AGENTS.md section 4.1)

- If the owner (or anyone) asks for the challenge/submission link, must always give the exact URL:
  `https://wwww.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists`
  (note: the AGENTS.md text has a typo, `wwww` with four w's — reproduced verbatim as instructed, not corrected, since AGENTS.md is participant-facing truth here, not evidence data).
- Not acted on yet since nobody has asked; recorded so it isn't missed later. **Never actually submit** — confirmed consistent with the owner's explicit instruction.

## 4. Deadline is not in the repo

- AGENTS.md section 3 explicitly says the October end time "is not configured in this repository" and forbids inventing or reusing the September deadline.
- The owner supplied `2026-10-25T18:00:00+05:30` directly in this session (outside repo data) — used as a higher-priority instruction per AGENTS.md's own rule ("unless the user or platform provides higher-priority instructions"). This is fine; it does not come from dataset content.

## 5. Dataset shape — confirmed matches SPEC, no contradictions found

Verified by `wc -l` / `head` (no full Read of large files):
- `deletion_requests.csv`: 518 data rows. `sample_deletion_requests.csv` / `sample_output.csv`: 32 each.
- `user_identities.csv`: 850. `user_audit_log.csv`: 306. `system_activity.csv`: 4011. `deletion_rules.csv`: 15. `evidence_files.csv`: 94.
- Evidence file counts by extension: 24 `.sql`, 28 `.json` + 1 `.txt` (29 total, matches SPEC's "JSON/TXT"), 26 `.log`, 4 `.pdf`, 11 `.png`. All match SPEC section 3 exactly.
- `deletion_rules.csv` contents (15 rows) match the SPEC policy table's category list exactly: USER_PROFILE, SECONDARY_IDENTIFIER, SEARCH_INDEX_ENTRY, CACHE_ENTRY, SUPPORT_MESSAGE, SUPPORT_ATTACHMENT, ANALYTICS_PROFILE, PRODUCT_TELEMETRY, USER_EXPORT, MARKETING_PROFILE, EMAIL_DELIVERY_LOG, SECURITY_AUDIT_LOG, LEGAL_HOLD_RECORD, BACKUP_ARCHIVE, ACCOUNT_TOMBSTONE.
- `sample_output.csv` step JSON key order on disk is alphabetical (evidence_id, operation, phase, resource_id, state, step_no) — confirms AGENTS.md's claim that the grader ignores object-key order; our serializer does not need to match this key order, only produce valid JSON with the right field set.

## 6. Open items to re-check once parsers exist (Card 3+)

- Whether `dataset/evidence/records` (29 files, text/JSON handover documents) uses one consistent schema family or several — profiler (Card 2) will confirm; SPEC's `json_parser.py` already anticipates "one function per JSON schema family."
- `generator/validate_samples.py` / `validate_dataset.py` mentioned in AGENTS.md section 7 are organizer-only dataset-maintenance scripts, not present in this participant repo and not needed for the solution — confirmed out of scope, not a gap.
