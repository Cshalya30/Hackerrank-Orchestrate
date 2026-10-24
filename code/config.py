"""Paths and constants shared across the pipeline. No dataset content lives here."""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = REPO_ROOT / "dataset"
EVIDENCE_DIR = DATASET_DIR / "evidence"
BUILD_DIR = REPO_ROOT / "build"
DOCS_DIR = REPO_ROOT / "docs"

DELETION_REQUESTS_CSV = DATASET_DIR / "deletion_requests.csv"
SAMPLE_REQUESTS_CSV = DATASET_DIR / "sample_deletion_requests.csv"
SAMPLE_OUTPUT_CSV = DATASET_DIR / "sample_output.csv"
USER_IDENTITIES_CSV = DATASET_DIR / "user_identities.csv"
USER_AUDIT_LOG_CSV = DATASET_DIR / "user_audit_log.csv"
SYSTEM_ACTIVITY_CSV = DATASET_DIR / "system_activity.csv"
DELETION_RULES_CSV = DATASET_DIR / "deletion_rules.csv"
EVIDENCE_FILES_CSV = DATASET_DIR / "evidence_files.csv"

OBSERVATIONS_JSONL = BUILD_DIR / "observations.jsonl"
COVERAGE_TXT = BUILD_DIR / "coverage.txt"
EVIDENCE_PROFILE_TXT = BUILD_DIR / "evidence_profile.txt"
LLM_CACHE_DIR = BUILD_DIR / "llm_cache"
LLM_LEDGER_JSONL = BUILD_DIR / "llm_ledger.jsonl"

OUTPUT_CSV = REPO_ROOT / "output.csv"

# Runtime model for the few LLM-backed steps (intent classification, image
# parsing, rare adjudication). See docs/SPEC.md section 5.
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

EXPECTED_FULL_ROWS = 518
EXPECTED_SAMPLE_ROWS = 32

PHASE_ORDER = ["FINDING", "REMEDIATION", "VERIFICATION"]

OPERATION_ORDER = {
    "FINDING": [
        "REPORT_REMAINING_RECORD",
        "REPORT_EXPOSED_PII",
        "REPORT_ACTIVE_DATA_FLOW",
        "REPORT_RESTORE_RISK",
    ],
    "REMEDIATION": [
        "DISABLE_DATA_FLOW",
        "BLOCK_RESTORE",
        "DELETE_RECORD",
        "REDACT_RECORD",
        "ANONYMIZE_RECORD",
    ],
    "VERIFICATION": [
        "VERIFY_RECORD_ABSENT",
        "VERIFY_RECORD_PRESENT",
        "VERIFY_RECORD_REDACTED",
        "VERIFY_RECORD_ANONYMIZED",
        "VERIFY_DATA_FLOW_DISABLED",
        "VERIFY_RESTORE_BLOCKED",
    ],
}

BUILD_DIR.mkdir(exist_ok=True)
