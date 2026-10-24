"""Contract checks on an output.csv. Fails loudly (non-zero exit, printed reasons).

Run: python code/validate.py [path/to/output.csv] [--expect-rows N] [--case-ids path/to/requests.csv]
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REQUIRED_FIELDS = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}
PHASE_ORDER = ["FINDING", "REMEDIATION", "VERIFICATION"]
OPERATION_ORDER = {
    "FINDING": ["REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII", "REPORT_ACTIVE_DATA_FLOW", "REPORT_RESTORE_RISK"],
    "REMEDIATION": ["DISABLE_DATA_FLOW", "BLOCK_RESTORE", "DELETE_RECORD", "REDACT_RECORD", "ANONYMIZE_RECORD"],
    "VERIFICATION": [
        "VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT", "VERIFY_RECORD_REDACTED",
        "VERIFY_RECORD_ANONYMIZED", "VERIFY_DATA_FLOW_DISABLED", "VERIFY_RESTORE_BLOCKED",
    ],
}
OPERATION_STATE = {
    "REPORT_REMAINING_RECORD": "PRESENT", "REPORT_EXPOSED_PII": "PRESENT",
    "REPORT_ACTIVE_DATA_FLOW": "ACTIVE", "REPORT_RESTORE_RISK": "ACTIVE",
    "DISABLE_DATA_FLOW": "DISABLED", "BLOCK_RESTORE": "BLOCKED", "DELETE_RECORD": "ABSENT",
    "REDACT_RECORD": "REDACTED", "ANONYMIZE_RECORD": "ANONYMIZED",
    "VERIFY_RECORD_ABSENT": "ABSENT", "VERIFY_RECORD_PRESENT": "PRESENT",
    "VERIFY_RECORD_REDACTED": "REDACTED", "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED",
    "VERIFY_DATA_FLOW_DISABLED": "DISABLED", "VERIFY_RESTORE_BLOCKED": "BLOCKED",
}
STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}


def _op_index(phase: str, operation: str) -> int:
    try:
        return OPERATION_ORDER[phase].index(operation)
    except (KeyError, ValueError):
        return -1


def validate_rows(rows: list[dict], expect_rows: int | None, expect_case_ids: set[str] | None) -> list[str]:
    errors: list[str] = []
    case_ids = [r["case_id"] for r in rows]

    if expect_rows is not None and len(rows) != expect_rows:
        errors.append(f"row count {len(rows)} != expected {expect_rows}")

    if case_ids != sorted(case_ids):
        errors.append("rows are not sorted by case_id")

    if len(set(case_ids)) != len(case_ids):
        errors.append("duplicate case_id values present")

    if expect_case_ids is not None:
        missing = expect_case_ids - set(case_ids)
        extra = set(case_ids) - expect_case_ids
        if missing:
            errors.append(f"missing {len(missing)} case_id(s), e.g. {sorted(missing)[:5]}")
        if extra:
            errors.append(f"{len(extra)} unexpected case_id(s), e.g. {sorted(extra)[:5]}")

    for row in rows:
        cid = row["case_id"]
        status = row["deletion_status"]
        if status not in STATUSES:
            errors.append(f"{cid}: invalid deletion_status {status!r}")

        try:
            steps = json.loads(row["steps_json"])
        except json.JSONDecodeError as exc:
            errors.append(f"{cid}: steps_json is not valid JSON ({exc})")
            continue

        if not isinstance(steps, list):
            errors.append(f"{cid}: steps_json is not a JSON array")
            continue

        if status == "NOT_APPLICABLE":
            if steps != []:
                errors.append(f"{cid}: NOT_APPLICABLE must have steps_json == []")
            continue

        # Note: a COMPLETE case with zero steps (no evidence of any remaining
        # data was found at all) is unusual but not forbidden by the output
        # contract, so this is not flagged as an error.

        last_phase_idx = -1
        last_op_idx = -1
        last_key = ("", "")
        for i, step in enumerate(steps, start=1):
            if set(step.keys()) != REQUIRED_FIELDS:
                errors.append(f"{cid} step {i}: field set {sorted(step.keys())} != {sorted(REQUIRED_FIELDS)}")
                continue
            if step["step_no"] != i:
                errors.append(f"{cid} step {i}: step_no={step['step_no']}, expected {i}")

            phase = step["phase"]
            op = step["operation"]
            if phase not in PHASE_ORDER:
                errors.append(f"{cid} step {i}: invalid phase {phase!r}")
                continue
            if op not in OPERATION_STATE:
                errors.append(f"{cid} step {i}: invalid operation {op!r}")
                continue
            if OPERATION_STATE[op] != step["state"]:
                errors.append(f"{cid} step {i}: operation {op} requires state {OPERATION_STATE[op]}, got {step['state']}")

            phase_idx = PHASE_ORDER.index(phase)
            if phase_idx < last_phase_idx:
                errors.append(f"{cid} step {i}: phase {phase} appears out of order")
            op_idx = _op_index(phase, op)
            key = (step["system_id"], step["resource_id"])
            if phase_idx == last_phase_idx:
                if op_idx < last_op_idx:
                    errors.append(f"{cid} step {i}: operation order violated within phase {phase}")
                elif op_idx == last_op_idx and key < last_key:
                    errors.append(f"{cid} step {i}: system_id/resource_id order violated")
            last_phase_idx, last_op_idx, last_key = phase_idx, op_idx, key

            evidence_id = step["evidence_id"]
            is_finding = phase == "FINDING"
            is_complete_verification = phase == "VERIFICATION" and status == "COMPLETE"
            must_cite = is_finding or is_complete_verification
            if must_cite and not evidence_id:
                errors.append(f"{cid} step {i}: {phase} step on {status} case must cite evidence_id")
            if not must_cite and evidence_id:
                errors.append(f"{cid} step {i}: proposed {phase.lower()} step must use empty evidence_id, got {evidence_id!r}")

    return errors


def load_rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != ["case_id", "deletion_status", "steps_json"]:
            raise SystemExit(f"bad header: {reader.fieldnames}")
        return list(reader)


def main() -> int:
    args = sys.argv[1:]
    out_path = Path(args[0]) if args and not args[0].startswith("--") else Path(__file__).resolve().parent.parent / "output.csv"

    expect_rows = None
    expect_case_ids = None
    if "--expect-rows" in args:
        expect_rows = int(args[args.index("--expect-rows") + 1])
    if "--case-ids" in args:
        case_ids_path = Path(args[args.index("--case-ids") + 1])
        with open(case_ids_path, newline="", encoding="utf-8") as f:
            expect_case_ids = {r["case_id"] for r in csv.DictReader(f)}
        if expect_rows is None:
            expect_rows = len(expect_case_ids)

    rows = load_rows(out_path)
    errors = validate_rows(rows, expect_rows, expect_case_ids)

    if errors:
        print(f"VALIDATION FAILED: {len(errors)} error(s) in {out_path}")
        for e in errors[:60]:
            print(" -", e)
        if len(errors) > 60:
            print(f" ... and {len(errors) - 60} more")
        return 1

    print(f"VALIDATION PASSED: {out_path} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
