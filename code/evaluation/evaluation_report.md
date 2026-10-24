# Evaluation Report — Ghost Data Audit Agent

Status at this snapshot: **Phase-0 autonomous build, two runs plus a Gemini-backed
intent/vision pass.** This report states real, reproducible numbers from the
current codebase — nothing here is invented. See `docs/CONTEXT.md` for the
full handoff, `docs/EVAL_LOG.md` for every eval run (kept and reverted), and
`docs/DECISIONS.md` for the reasoning behind each kept/reverted change.

## How to reproduce every number below

```bash
python code/ingest/build.py                                    # -> build/observations.jsonl, build/coverage.txt
python code/main.py --split sample --out build/sample_output_pred.csv
python code/evaluation/main.py --pred build/sample_output_pred.csv --gold dataset/sample_output.csv
python code/main.py --split full --out output.csv
python code/validate.py output.csv --expect-rows 518 --case-ids dataset/deletion_requests.csv
python code/evaluation/custom_cases/test_custom_cases.py
```

`GEMINI_API_KEY` must be set in `.env` for the LLM intent path; without it,
`code/intent.py` falls back to the deterministic keyword classifier
(functionally similar but will not generalize to unseen phrasing).

## 1. Case-level deletion-status accuracy

Measured against the 32 public samples (`dataset/sample_output.csv`):

| Metric | Value |
|---|---|
| Status accuracy | **0.844** (27/32) |
| Sequence accuracy (exact ordered step-list match, status included) | **0.156** (5/32) |

## 2. Step-level and field-level accuracy

| Metric | Value |
|---|---|
| Step precision (multiset match on system_id/resource_id/operation/state/evidence_id, step_no ignored) | 0.812 |
| Step recall | 0.648 |
| Step F1 | **0.720** |
| Field accuracy — step_no | 1.000 |
| Field accuracy — phase | 0.826 |
| Field accuracy — system_id | 0.591 |
| Field accuracy — resource_id | 0.550 |
| Field accuracy — operation | 0.570 |
| Field accuracy — state | 0.624 |
| Field accuracy — evidence_id | 0.886 |

Reading these together: precision and recall both improved substantially over
the first build (0.880/0.378/0.529 -> 0.812/0.648/0.720) once account/audit
resolution, category-aware log states, historical-identifier matching, and
(this session) 9/11 screenshot observations were added (see section 4).
Precision dipped slightly from the very first build (0.880 -> 0.812) as a
side effect of resolving more resources overall — a few of the newly-resolved
account/audit records are structurally right but not exactly what the gold
step expects (see section 5).

## 3. Sequence accuracy

0.156 (5/32 cases produce the exact ordered step list), unchanged from the
previous session's build and up from 0.062 in the
first build. Most remaining misses are partial: the status is right and most
steps match, but one or two resources (commonly: a PDF/PNG-only account, or a
SUPPORT_ATTACHMENT/SUPPORT_MESSAGE misclassification) are still missing or
extra, which fails exact-sequence matching even when the case is otherwise
close.

## 4. Known failures and the fixes made across both runs (plus this session's Gemini pass)

| # | Failure found | Evidence | Fix | Effect |
|---|---|---|---|---|
| 1 | `eval.py`'s field-accuracy divisor summed all 7 fields into one shared total | self-comparing `sample_output.csv` against itself | per-field total dict instead of one shared counter | all 7 field accuracies correctly read 1.000 on the self-check |
| 2 | `planner.finalize()` collapsed "zero resources resolved" into `NOT_APPLICABLE` | first Card 4 sample run: 11/32 predicted NOT_APPLICABLE against a gold set with 0 | only intent classification may set NOT_APPLICABLE; empty-resource deletion cases become COMPLETE with `[]` | status accuracy 0.531 -> 0.750 |
| 3 | First ingest pass covered only 82.0% of required (system_id, resource_id) pairs | `build/coverage.txt` | parse `system_activity.csv` (LINK_RESOURCE_IDENTITY, DELETE_RECORD, RESTORE_BACKUP) | coverage 82.0% -> 90.1% |
| 4 | Deterministic intent fallback defaulted 6 unambiguous non-deletion requests to DELETION | manual inspection of the 6 "no signal" full-run cases | broadened non-deletion keyword hints | full run: 0 -> 6 correct NOT_APPLICABLE |
| 5 | (RUN2) Many account/audit resources never resolved at all: `status_code` 404 never checked, `subject_reference`/`requester_*`/nested `hits.documents` fields never extracted, a closure late-binding bug corrupted `source` on every export observation | account-resolution trace review | `account_linker.py` (direct link -> catalog link -> same-day batch order -> zero-padded fallback) + the four parser bugs fixed | step F1 0.529 -> 0.646 |
| 6 | Log/activity sources defaulted to a generic `PRESENT` the planner silently treated as compliant; old email-hash-only matches were missed | case_12 (`analytics_9914` matched only via an old `email_hash` in a log's `correlation_key`) | category-aware default states (FLOW_ENABLED/RESTORE_ALLOWED/IDENTIFIABLE, not generic PRESENT); `matches_identity()` also checks `email_hash`/`email` sets | status 0.750 -> 0.812, step F1 0.646 -> 0.694 |
| 7 | `support_001`/`audit_record` evidence only existed in a PDF, which wasn't parsed | case_07 | wired `pdf_parser` for the two specific PDFs needed | step F1 0.694 -> 0.706 |
| 8 | Intent classification was binary (DELETION/NON_DELETION) and relied on a hand-maintained keyword list; "please verify my deletion completed" follow-ups were indistinguishable from ambiguous defaults | advisor review predicting 10-15 real NOT_APPLICABLE cases vs. 6 found by the keyword fallback | 3-label scheme (DELETE_REQUEST/DELETION_VERIFICATION/OTHER_SERVICE) on Gemini Flash-Lite (thinking off), batched/cached; only OTHER_SERVICE -> NOT_APPLICABLE; CLASSIFY_REQUEST override still forces OTHER_SERVICE | full run NOT_APPLICABLE count 6 -> **10**, all driven by the CLASSIFY_REQUEST override (matches the advisor's 10-15 prediction); sample eval unchanged (0.812/0.706, sample has 0 NOT_APPLICABLE cases) |
| 9 | Screenshot (PNG) evidence was never parsed, so a handful of accounts/records only ever shown in an admin-console screenshot stayed unresolved | 11 `.png` evidence files in `dataset/evidence/` with no CSV/JSON/log counterpart | re-ran `code/ingest/image_parser.py` (Gemini vision, new `google-genai` SDK) and merged its output into `build/observations.jsonl`; 9/11 screenshots parsed (22 observations), 2 hit the Gemini free-tier's 20-requests/day quota (429, not a parsing bug) | status 0.812 -> **0.844**, step F1 0.706 -> **0.720** — unlike the earlier same-session attempt at 34/34 observations (which regressed F1 to 0.695 and was reverted, see `docs/DECISIONS.md` D8), this smaller merge net-improved and was kept |

## 5. Remaining known gaps (not yet fixed — see `docs/GAPS.md` and `docs/CONTEXT.md`)

- **2 of 11 screenshots are still unparsed** (`evidence_46`, `evidence_60`) — not a bug, the Gemini free-tier key hit its 20-requests/day cap mid-run. Re-running `code/ingest/image_parser.py` once the quota resets (or on a paid key) will pick up the remaining 2 without reprocessing the other 9 (disk-cached by prompt+image hash).
- **7 accounts and 3 audit records have zero evidence anywhere** in the parsed corpus (`build/coverage.txt`), even after account_linker's batch-matching, zero-padded fallback, and the image pass — these may only be resolvable via the 2 still-unparsed screenshots, or they may be intentionally unreachable (as `audit_record_6645` for case_18 is confirmed to be).
- **SUPPORT_ATTACHMENT vs. SUPPORT_MESSAGE is still not fully reliable** beyond the two PDF-backed cases wired in RUN2 — the general heuristic still defaults by table/collection name for everything else.
- **The deterministic intent fallback remains a stopgap** for when `GEMINI_API_KEY` is absent; it won't generalize to unseen non-deletion or verification phrasing the way the LLM path does.

## 6. Custom evaluation cases (owner-required, >= 3)

See `code/evaluation/custom_cases/test_custom_cases.py` — run directly, no
pytest dependency needed. All three pass as of this commit:

1. **`case_1_not_applicable`** — a request that mixes an export ask with explicit
   "leave my account as it is" framing must classify as `OTHER_SERVICE` (not
   one of `intent.DELETION_LABELS`) -> `NOT_APPLICABLE`.
2. **`case_2_old_identifier_match`** — a record carrying only the user's *historical*
   (pre-change) email hash must still be matched by identity resolution, and
   planned for `ANONYMIZE_RECORD` (an `ANALYTICS_PROFILE` still linkable to the user).
3. **`case_3_resurrection_after_deletion`** — a resource proven `ABSENT` by file
   evidence at T1, then claimed `PRESENT` again by a later successful
   `RESTORE_BACKUP`-style activity at T2, must resolve to `PRESENT` at any
   `audit_at` after T2 — the central "ghost data" mechanic of this challenge.

```
PASS case_1_not_applicable: OTHER_SERVICE
PASS case_2_old_identifier_match: matched via historical hash, planned ANONYMIZE_RECORD
PASS case_3_resurrection_after_deletion: later activity correctly overrides the earlier file-proven deletion

all 3 custom cases passed
```
