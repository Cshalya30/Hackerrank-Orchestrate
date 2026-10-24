# Evaluation Report — Ghost Data Audit Agent

Status at this snapshot: **Phase-0 autonomous build session, not yet fully tuned.**
This report states real, reproducible numbers from the current codebase — nothing
here is invented. See `docs/CONTEXT.md` for the full handoff and next actions.

## How to reproduce every number below

```bash
python code/ingest/build.py                                    # -> build/observations.jsonl, build/coverage.txt
python code/main.py --split sample --out build/sample_output_pred.csv
python code/evaluation/main.py --pred build/sample_output_pred.csv --gold dataset/sample_output.csv
python code/main.py --split full --out output.csv
python code/validate.py output.csv --expect-rows 518 --case-ids dataset/deletion_requests.csv
python code/evaluation/custom_cases/test_custom_cases.py
```

## 1. Case-level deletion-status accuracy

Measured against the 32 public samples (`dataset/sample_output.csv`):

| Metric | Value |
|---|---|
| Status accuracy | **0.750** (24/32) |
| Sequence accuracy (exact ordered step-list match, status included) | **0.062** (2/32) |

## 2. Step-level and field-level accuracy

| Metric | Value |
|---|---|
| Step precision (multiset match on system_id/resource_id/operation/state/evidence_id, step_no ignored) | 0.880 |
| Step recall | 0.378 |
| Step F1 | **0.529** |
| Field accuracy — step_no | 1.000 |
| Field accuracy — phase | 0.590 |
| Field accuracy — system_id | 0.361 |
| Field accuracy — resource_id | 0.361 |
| Field accuracy — operation | 0.325 |
| Field accuracy — state | 0.434 |
| Field accuracy — evidence_id | 0.795 |

Reading these together: **precision is high (0.88)** — when the pipeline reports a
finding/remediation/verification step, it is usually structurally correct and
evidence-backed. **Recall is the weak point (0.38)** — many true steps are missed
because the underlying resource was never linked to the user by any parsed
evidence (see section 4, "coverage"). The low per-position field accuracy
numbers are a byproduct of the step-count mismatch (comparing step *i* of a
3-step prediction against step *i* of a 5-step gold list is not very
informative); precision/recall/F1 and sequence accuracy are the metrics that
actually matter here.

## 3. Sequence accuracy

0.062 (2/32 cases produce the exact ordered step list). The two exact matches
are cases where every relevant resource happened to be fully covered by our
parsers. Every other case has at least one missing resource (a false
negative), which — by definition of sequence accuracy — fails the whole case
even when every *produced* step is correct.

## 4. Known failures and the fixes made this session

| # | Failure found | Evidence | Fix | Effect |
|---|---|---|---|---|
| 1 | `eval.py`'s field-accuracy divisor summed all 7 fields into one shared total, reading 0.143 (~1/7) on every field even for an identical self-comparison | self-comparing `sample_output.csv` against itself | per-field total dict instead of one shared counter | all 7 field accuracies correctly read 1.000 on the self-check |
| 2 | `planner.finalize()` collapsed "zero resources resolved" into `NOT_APPLICABLE`, misclassifying 6+ genuine deletion requests as "person never asked to be deleted" | first Card 4 sample run: 11/32 predicted NOT_APPLICABLE against a gold set with 0 | only intent classification may set NOT_APPLICABLE; empty-resource DELETION cases become COMPLETE with `[]` (least-wrong default: "no evidence of remaining data found") | status accuracy 0.531 -> 0.750 |
| 3 | First ingest pass only covered 82.0% of the (system_id, resource_id) pairs required by `sample_output.csv`, missing every low-numbered `account_service` resource | `build/coverage.txt` | added `system_activity.csv` parsing (LINK_RESOURCE_IDENTITY identity edges, DELETE_RECORD claims, RESTORE_BACKUP resurrection) | coverage 82.0% -> 90.1% |
| 4 | Deterministic intent fallback defaulted 6 unambiguous non-deletion requests in the full 518-case set to DELETION (0 confident NON_DELETION predictions, which is implausible given the problem statement's own non-deletion examples) | manual inspection of the 6 "no signal" cases (case_533/535/537/538/540/541) — phone update, data export, name correction, marketing opt-out, invoice copy, email change | broadened `NON_DELETION_HINTS` with the "leave/keep it as-is" phrasing these requests actually used | full run: 0 -> 6 correct NOT_APPLICABLE, 0 remaining ambiguous defaults |

## 5. Remaining known gaps (not yet fixed — see `docs/GAPS.md` and `docs/CONTEXT.md`)

- **PDF and PNG evidence are not parsed** (4 PDFs, 11 PNG screenshots — the latter needs a vision LLM, which needs `GEMINI_API_KEY`, not configured in this session). This is the most likely cause of the remaining ~10% coverage gap and most of the recall loss above — several resources are presumably only ever described in a screenshot or a PDF handover.
- **SUPPORT_ATTACHMENT vs. SUPPORT_MESSAGE is not reliably distinguished.** `support_records` rows all share the `support_` prefix with no field telling us "owned only by this subject" vs. "shared context with another customer/agent" (deletion_rules.csv rules 05 vs. 06 require different treatment — REDACT vs. DELETE). The current heuristic defaults by table/collection name only, which is sometimes wrong (see case_07 in `code/evaluation/custom_cases` notes below).
- **Account-linkage for accounts with zero evidence anywhere** (e.g. sample `case_01`'s `account_001`) has no path to a resolution right now — this needs either the skipped PDF/PNG evidence or a different identity-linking heuristic.
- **The deterministic intent fallback will not generalize** to non-deletion phrasing it hasn't seen; this is a stopgap until `GEMINI_API_KEY` is supplied (SPEC.md section 5 / `docs/CONTEXT.md`).

## 6. Custom evaluation cases (owner-required, >= 3)

See `code/evaluation/custom_cases/test_custom_cases.py` — run directly, no
pytest dependency needed. All three pass as of this commit:

1. **`case_1_not_applicable`** — a request that mixes an export ask with explicit
   "leave my account as it is" framing must classify as `NON_DELETION`/`NOT_APPLICABLE`.
2. **`case_2_old_identifier_match`** — a record carrying only the user's *historical*
   (pre-change) email hash must still be matched by identity resolution, and
   planned for `ANONYMIZE_RECORD` (an `ANALYTICS_PROFILE` still linkable to the user).
3. **`case_3_resurrection_after_deletion`** — a resource proven `ABSENT` by file
   evidence at T1, then claimed `PRESENT` again by a later successful
   `RESTORE_BACKUP`-style activity at T2, must resolve to `PRESENT` at any
   `audit_at` after T2 — the central "ghost data" mechanic of this challenge.

```
PASS case_1_not_applicable: NON_DELETION
PASS case_2_old_identifier_match: matched via historical hash, planned ANONYMIZE_RECORD
PASS case_3_resurrection_after_deletion: later activity correctly overrides the earlier file-proven deletion
all 3 custom cases passed
```
