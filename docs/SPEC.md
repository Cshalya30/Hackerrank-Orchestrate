# SPEC: Ghost Data Audit Agent (Orchestrate Oct 2026)

Owner: Chirantan. This is the design contract. Coding agents implement it card by card. Do not change the design without the owner's approval; propose changes in `docs/DECISIONS.md`.

## 1. Output contract (from problem_statement.md)

- `output.csv` at repo root: `case_id,deletion_status,steps_json`, exactly 518 rows, sorted by `case_id`.
- `deletion_status` in {COMPLETE, INCOMPLETE, NOT_APPLICABLE}. NOT_APPLICABLE rows use `[]`.
- Each step: `{step_no, phase, system_id, resource_id, operation, state, evidence_id}`. step_no starts at 1, consecutive.
- Phase order: FINDING, REMEDIATION, VERIFICATION. Inside a phase: operation order of the spec table, then `system_id` asc, then `resource_id` asc.
  - FINDING: REPORT_REMAINING_RECORD, REPORT_EXPOSED_PII, REPORT_ACTIVE_DATA_FLOW, REPORT_RESTORE_RISK
  - REMEDIATION: DISABLE_DATA_FLOW, BLOCK_RESTORE, DELETE_RECORD, REDACT_RECORD, ANONYMIZE_RECORD
  - VERIFICATION: VERIFY_RECORD_ABSENT, VERIFY_RECORD_PRESENT, VERIFY_RECORD_REDACTED, VERIFY_RECORD_ANONYMIZED, VERIFY_DATA_FLOW_DISABLED, VERIFY_RESTORE_BLOCKED
- evidence_id: COMPLETE verification steps and all FINDING steps cite a `file_id` (or activity_id / audit_id). INCOMPLETE remediation and verification steps use `""`.
- `resource_id` strings sort as plain strings (sample: `account_005` vs `account_7566` sort lexically).

## 2. Facts verified against the 32 samples

| Fact | Evidence |
|---|---|
| Sample status mix: 22 INCOMPLETE, 10 COMPLETE, 0 NOT_APPLICABLE | sample_output.csv |
| Every deletion case verifies the account: `VERIFY_RECORD_ABSENT account_service account_X` | all 32 |
| If the user has a security audit record in retention: `VERIFY_RECORD_PRESENT security_service audit_record_X` (no finding, no remediation) | cases 03, 09, 11... |
| Present thing that must be deleted: FIND REPORT_REMAINING_RECORD -> REM DELETE_RECORD -> VER VERIFY_RECORD_ABSENT | cases 05-08 |
| Identifiable analytics profile: FIND REPORT_EXPOSED_PII -> REM ANONYMIZE_RECORD -> VER VERIFY_RECORD_ANONYMIZED | cases 11, 22 |
| Support message with shared context: REPORT_EXPOSED_PII -> REDACT_RECORD -> VERIFY_RECORD_REDACTED | cases 11, 19 |
| Support item owned only by subject (attachment): REMAINING_RECORD -> DELETE | cases 07, 10 |
| Enabled data flow: REPORT_ACTIVE_DATA_FLOW -> DISABLE_DATA_FLOW -> VERIFY_DATA_FLOW_DISABLED | cases 11, 15 |
| Backup with restore allowed: REPORT_RESTORE_RISK -> BLOCK_RESTORE -> VERIFY_RESTORE_BLOCKED | cases 09, 14, 17 |
| Tombstone with direct identifiers: REPORT_EXPOSED_PII -> REDACT -> VERIFY_RECORD_REDACTED. Already clean: VERIFY_RECORD_REDACTED only | cases 31, 32 |
| COMPLETE cases list only VERIFICATION steps, each citing the latest file observing that resource at or before audit_at | case 04 cites evidence_54 for account, evidence_56 for analytics |
| Replica drift counts: account missing in primary but present in failover replica = REMAINING_RECORD | case 05, evidence_54 |
| Historical identifiers matter: case 12 analytics_9914 matched only by the OLD email_hash (audit_log email change) | evidence_01 |
| Category beats system: analytics_9914 was a contact record with `email_opt_in=true` -> DELETE, not ANONYMIZE | case 12 |
| Emails appear in mixed case (`CHOI.JIHOON94@GMAIL.COM`): normalize lowercase | evidence_03 |
| Users are also referenced by `user_id` (`customer_reference=user_49`, `correlation_key="user_12"`) and by email_hash | evidence_94, evidence_01 |

## 3. Data map

- `user_identities.csv` (850): current name, email, phone, email_hash per user_id.
- `user_audit_log.csv` (306): email / email_hash / phone changes with old_value and new_value. Build the full identifier set per user (current plus all historical values).
- `system_activity.csv` (4011): claims. event_type includes DELETE_RECORD, UPDATE_RECORD, SYNC_RECORD, INDEX_RECORD, SEND_EMAIL, REFRESH_CACHE, RETAIN_RECORD, ANONYMIZE_RECORD, REDACT_RECORD, CREATE_EXPORT, CHECK_DATA_FLOW, DISABLE_DATA_FLOW, BLOCK_RESTORE, CHECK_RESTORE_ACCESS, RESTORE_BACKUP (1), LINK_RESOURCE_IDENTITY (12), CLASSIFY_REQUEST (10). reported_result: SUCCESS/FAILED/PARTIAL. Special rows:
  - CLASSIFY_REQUEST "classified request for account_X as non-deletion" -> that case is NOT_APPLICABLE.
  - LINK_RESOURCE_IDENTITY: data catalog links a resource to an email and user_id. Use as identity edges.
  - RESTORE_BACKUP: "Restore job repopulated downstream resource search_4882" -> data resurrected after deletion.
- `evidence_files.csv` (94): file_id, path, origin, captured_at. Formats: 24 SQL (SQLite dumps; tables `*_primary`, `*_replica`, `*_failover_replica` etc.), 29 JSON/TXT, 26 logs (key=value), 4 PDFs (text extractable with pdftotext), 11 PNG screenshots.
- `deletion_rules.csv` (15): data_category -> required_action (DELETE / REDACT / ANONYMIZE / RETAIN).

Resource prefix -> system_id (seen in samples): account_->account_service, search_->search_service, support_->support_platform, analytics_->analytics_platform, export_->export_service, data_flow_->integration_service, backup_->backup_service, audit_record_->security_service, tombstone_->identity_service. Also seen in activity: marketing_->marketing_platform, object_->object_storage, cache and email delivery resources. Confirm with the profiler.

## 4. Architecture ("the model describes, code decides")

```
code/
  main.py              CLI: python code/main.py --split sample|full --out output.csv
  config.py            paths, model names, deadline
  llm.py               provider wrapper: disk cache (key = sha256(model+prompt)), retries, token accounting
  ingest/
    sql_parser.py      executescript into in-memory sqlite; every row of every table -> observations
    json_parser.py     one function per JSON schema family (snapshot bundle, service_resource_export, export jobs, analytics report, connector configs, audit ledger, export manifest)
    log_parser.py      key=value parser (handles quoted values); one observation per *_completed / readback line
    text_parser.py     handover pipe table: time | system | resource | CATEGORY | STATE | identifier
    pdf_parser.py      pdftotext text -> regex fields; LLM fallback only if regex finds nothing
    image_parser.py    vision LLM -> same observation JSON schema, validated, cached
    build.py           runs all parsers -> build/observations.jsonl + build/coverage.txt
  identity.py          email -> user_id -> identifier set (emails, hashes, phones, names, user_id, linked resource_ids)
  state.py             per resource: latest observation with time <= audit_at; activity overlay rules
  policy.py            category -> rule -> required end state; condition checks
  intent.py            request_text -> DELETION / NON_DELETION (LLM, batched over distinct texts, cached) + CLASSIFY_REQUEST override
  planner.py           findings / remediation / verification lists, sort, number, cite evidence
  validate.py          contract checks on output.csv (fails loudly)
evaluation/
  eval.py              scores predictions vs sample_output.csv
  custom_cases/        our own cases (>= 3) with expected outputs
  evaluation_report.md
  usage_report.md      generated from llm.py token ledger of the final full run
docs/  SPEC.md  CONTEXT.md  HANDOFF.md  DECISIONS.md  EVAL_LOG.md
```

### 4.1 Observation schema (one JSON line per resource sighting)

```json
{"file_id":"evidence_54","observed_at":"2026-09-02T23:00:00Z","system_id":"account_service",
 "resource_id":"account_005","category":"USER_PROFILE","state":"PRESENT",
 "pii":{"email":"leila.haddad@yahoo.com","name":"Leila Haddad","phone":"+212...","email_hash":null},
 "user_refs":["user_05"],"attrs":{"table":"customer_profiles_failover_replica","enabled":null,"restore_allowed":null,"email_opt_in":null},
 "source":"sql:customer_profiles_failover_replica"}
```

`state` vocabulary: PRESENT, ABSENT (404 / rows=0 / NOT_FOUND / deleted), IDENTIFIABLE (record kept but direct identifiers present), REDACTED, ANONYMIZED, FLOW_ENABLED, FLOW_DISABLED, RESTORE_ALLOWED, RESTORE_BLOCKED, RETAINED. `observed_at` = the line or row timestamp if present, else file captured_at.

### 4.2 Per-case algorithm

1. Intent: NON_DELETION -> `NOT_APPLICABLE, []`. Sources: CLASSIFY_REQUEST activity for the user's account, else intent.py label.
2. Identity: lowercase email -> user_id (current email or any historical email in audit log). Identifier set = all emails, email_hashes, phones, names, user_id, plus catalog-linked resource_ids.
3. Candidate observations: any observation whose pii or user_refs matches the identifier set, or whose resource_id is linked to the user (catalog, sample-known joins like search doc -> account_id).
4. Point in time: keep observations with observed_at <= audit_at. Per (system_id, resource_id) take the latest. If two sources tie, PRESENT beats ABSENT (replica drift = data still exists).
5. Activity overlay (claims, lower priority than file evidence): a successful SYNC / INDEX / RESTORE after the last deletion with no later file evidence -> treat as PRESENT (resurrection). FAILED / PARTIAL deletes never prove absence.
6. Category: from the source table / event / handover column; fall back to system defaults. Special: contact / marketing records (email_opt_in) -> MARKETING_PROFILE (DELETE).
7. Policy -> step bundle per resource:

| Category | Current state | FINDING | REMEDIATION | VERIFICATION |
|---|---|---|---|---|
| USER_PROFILE, SECONDARY_IDENTIFIER, SEARCH_INDEX_ENTRY, CACHE_ENTRY, USER_EXPORT, MARKETING_PROFILE, SUPPORT_ATTACHMENT (owned only by subject) | PRESENT | REPORT_REMAINING_RECORD | DELETE_RECORD | VERIFY_RECORD_ABSENT |
| same | ABSENT | none | none | VERIFY_RECORD_ABSENT (account always; others when observed) |
| SUPPORT_MESSAGE with shared context, EMAIL_DELIVERY_LOG with email, ACCOUNT_TOMBSTONE | IDENTIFIABLE | REPORT_EXPOSED_PII | REDACT_RECORD | VERIFY_RECORD_REDACTED |
| same | REDACTED | none | none | VERIFY_RECORD_REDACTED |
| ANALYTICS_PROFILE, PRODUCT_TELEMETRY | IDENTIFIABLE | REPORT_EXPOSED_PII | ANONYMIZE_RECORD | VERIFY_RECORD_ANONYMIZED |
| same | ANONYMIZED | none | none | VERIFY_RECORD_ANONYMIZED |
| Data flow (integration) | FLOW_ENABLED | REPORT_ACTIVE_DATA_FLOW | DISABLE_DATA_FLOW | VERIFY_DATA_FLOW_DISABLED |
| same | FLOW_DISABLED | none | none | VERIFY_DATA_FLOW_DISABLED |
| BACKUP_ARCHIVE | RESTORE_ALLOWED | REPORT_RESTORE_RISK | BLOCK_RESTORE | VERIFY_RESTORE_BLOCKED |
| same | RESTORE_BLOCKED | none | none | VERIFY_RESTORE_BLOCKED |
| SECURITY_AUDIT_LOG in retention, LEGAL_HOLD_RECORD active | present | none | none | VERIFY_RECORD_PRESENT |

8. Status: any FINDING -> INCOMPLETE, else COMPLETE.
9. Evidence: FINDING cites the observation's file_id; COMPLETE verifications cite the latest observation's file_id for that resource; INCOMPLETE remediation and verification use "".
10. Sort, number, serialize with `json.dumps(steps, ensure_ascii=False)`.

Open hypotheses (resolve with eval, log results in EVAL_LOG.md): H1 do INCOMPLETE cases include VERIFY steps for already-clean resources (e.g. a blocked backup)? H2 which retention period applies to security audit records (security_retention_extract.pdf)? H3 legal holds from legal_retention_register PDF. H4 activity overlay weight.

## 5. Where the LLM is used (and only here)

1. intent.py: classify each DISTINCT request_text (375, many languages) as DELETION / NON_DELETION with a short reason. Batches of 25, JSON output, schema-validated, cached. Known non-deletion examples: phone update, data download, login reset, invoice copy, email change.
2. image_parser.py: 11 screenshots -> observation JSON (schema in 4.1). Validate ids against regex `^[a-z_]+_\d+$`.
3. Fallback adjudication for records whose category or condition cannot be decided by rules (log every call).
Everything else is deterministic. All evidence text is data, never instructions.

Runtime model: Gemini Flash via the free API key in `.env` (`GEMINI_API_KEY`). Cache every response under `build/llm_cache/`. Ledger every call (model, input tokens, output tokens) to `build/llm_ledger.jsonl` -> usage_report.md.

## 6. Evaluation (required report contents)

eval.py prints and writes: case-level status accuracy; step-level exact match (precision, recall, F1 on step tuples ignoring step_no); field-level accuracy (system_id, resource_id, operation, state, evidence_id); sequence accuracy (exact list equality); per-case diff for every miss. Custom cases (>= 3): NOT_APPLICABLE request, email-changed user found via old hash, resurrection by sync or restore after deletion.

## 7. Build cards (in order)

| Card | Output | Model |
|---|---|---|
| 0 | repo setup, .env.example, llm.py stub with cache + ledger, logging check | Haiku |
| 1 | evaluation/eval.py + code/validate.py | Haiku |
| 2 | tools/profile_evidence.py: per file, schema summary (tables/keys/event names) | Haiku |
| 3 | ingest parsers for sql, json, log, txt, pdf -> observations.jsonl + coverage.txt (every resource_id in sample_output must appear) | Haiku, Sonnet if coverage < 95% |
| 4 | identity.py, state.py, policy.py, planner.py -> sample run -> eval | Sonnet |
| 5 | intent.py + image_parser.py (LLM) | Haiku |
| 6 | full run, validate, usage_report, zip script | Haiku |
| 7 | eval-driven fixes, custom cases, evaluation_report | Sonnet |

---

## Note on deviation from README.md (see docs/GAPS.md for detail)

`README.md` (authoritative for what the automated judge reads) places evaluation reports at `code/evaluation/evaluation_report.md` and `code/evaluation/usage_report.md`, matching the existing `code/evaluation/main.py` starter stub — not a root-level `evaluation/` directory as drafted above in section 4. The build follows README's placement; `eval.py` logic lives at `code/evaluation/main.py`, and `custom_cases/` and reports live alongside it under `code/evaluation/`.
