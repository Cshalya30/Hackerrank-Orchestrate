# EVAL_LOG.md

One line per eval run against `dataset/sample_output.csv` (32 cases). Format:

`time | change | status_accuracy | step_F1 | sequence_accuracy`

| time | change | status accuracy | step F1 | sequence accuracy |
|---|---|---|---|---|
| 2026-10-24T20:52+05:30 | sample_output.csv vs itself (sanity check of eval.py) | 1.000 | 1.000 | 1.000 |
| 2026-10-24T21:40+05:30 | first Card 4 run: identity+state+policy+planner, no fixes | 0.531 | 0.529 | 0.062 |
| 2026-10-24T21:48+05:30 | fix: finalize() no longer infers NOT_APPLICABLE from empty steps (was mislabeling 6 genuine DELETION cases with unresolved evidence) | 0.750 | 0.529 | 0.062 |
| 2026-10-25T00:15+05:30 | RUN2 Group A: account_linker.py (A1/A2/A5), audit record A3 wiring | 0.750 | 0.497 | 0.156 |
| 2026-10-25T00:30+05:30 | fix: service_resource_export status_code (404->ABSENT), subject_reference/requester_email/hits.documents field extraction, resource-continuity overlay (once linked, always linked across PII loss) | 0.750 | 0.646 | 0.156 |
| 2026-10-25T01:00+05:30 | fix: category-aware default state for log/activity sources (DATA_FLOW/BACKUP/ANALYTICS/etc no longer default to generic PRESENT), user_refs now also matched against email_hash/email (case_12's old-hash-in-correlation_key), B3 contact-lookup -> MARKETING_PROFILE | 0.812 | 0.694 | 0.156 |
| 2026-10-25T01:15+05:30 | B5: wired pdf_parser for evidence_58 (support_001 attachment) and security_retention_extract (audit_record) | 0.812 | 0.706 | 0.156 |
