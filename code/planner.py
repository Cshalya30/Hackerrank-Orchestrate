"""policy.py + planner.py combined (see docs/DECISIONS.md D4). Turns a
resolved {(system_id, resource_id): winning_observation} map into the
ordered, numbered, evidence-cited steps_json list.

Confirmed against dataset/sample_output.csv (not organizer-only truth):
ALL verification steps in an INCOMPLETE case use evidence_id="" — even for
resources that already comply and never got a finding (see docs/EVAL_LOG.md
/ docs/DECISIONS.md "H1"). Only a COMPLETE case's verification steps, and
every FINDING step in any case, cite real evidence.
"""
from __future__ import annotations

import json

from config import OPERATION_ORDER, PHASE_ORDER
import taxonomy

OP_STATE = {
    "REPORT_REMAINING_RECORD": "PRESENT", "REPORT_EXPOSED_PII": "PRESENT",
    "REPORT_ACTIVE_DATA_FLOW": "ACTIVE", "REPORT_RESTORE_RISK": "ACTIVE",
    "DISABLE_DATA_FLOW": "DISABLED", "BLOCK_RESTORE": "BLOCKED", "DELETE_RECORD": "ABSENT",
    "REDACT_RECORD": "REDACTED", "ANONYMIZE_RECORD": "ANONYMIZED",
    "VERIFY_RECORD_ABSENT": "ABSENT", "VERIFY_RECORD_PRESENT": "PRESENT",
    "VERIFY_RECORD_REDACTED": "REDACTED", "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED",
    "VERIFY_DATA_FLOW_DISABLED": "DISABLED", "VERIFY_RESTORE_BLOCKED": "BLOCKED",
}

NEEDS_WORK_STATES = {
    "USER_PROFILE", "SECONDARY_IDENTIFIER", "SEARCH_INDEX_ENTRY", "CACHE_ENTRY",
    "USER_EXPORT", "MARKETING_PROFILE", "SUPPORT_ATTACHMENT",
}


def _resource_steps(system_id: str, resource_id: str, obs: dict) -> list[dict]:
    """Returns [(finding_op_or_None, remediation_op_or_None, verify_op), evidence_file_id, is_noncompliant]."""
    category = obs["category"]
    state = obs["state"]
    file_id = obs["file_id"] or ""

    if category in taxonomy.RETAINED_CATEGORIES:
        return [(None, None, "VERIFY_RECORD_PRESENT")], file_id, False

    if category == "DATA_FLOW":
        if state == "FLOW_ENABLED":
            return [("REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW", "VERIFY_DATA_FLOW_DISABLED")], file_id, True
        return [(None, None, "VERIFY_DATA_FLOW_DISABLED")], file_id, False

    if category == "BACKUP_ARCHIVE":
        if state == "RESTORE_ALLOWED":
            return [("REPORT_RESTORE_RISK", "BLOCK_RESTORE", "VERIFY_RESTORE_BLOCKED")], file_id, True
        return [(None, None, "VERIFY_RESTORE_BLOCKED")], file_id, False

    if category in NEEDS_WORK_STATES:
        if state == "PRESENT":
            return [("REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT")], file_id, True
        return [(None, None, "VERIFY_RECORD_ABSENT")], file_id, False

    if category in ("SUPPORT_MESSAGE", "EMAIL_DELIVERY_LOG", "ACCOUNT_TOMBSTONE"):
        if state == "IDENTIFIABLE":
            return [("REPORT_EXPOSED_PII", "REDACT_RECORD", "VERIFY_RECORD_REDACTED")], file_id, True
        return [(None, None, "VERIFY_RECORD_REDACTED")], file_id, False

    if category in ("ANALYTICS_PROFILE", "PRODUCT_TELEMETRY"):
        if state == "IDENTIFIABLE":
            return [("REPORT_EXPOSED_PII", "ANONYMIZE_RECORD", "VERIFY_RECORD_ANONYMIZED")], file_id, True
        return [(None, None, "VERIFY_RECORD_ANONYMIZED")], file_id, False

    # unknown category: default to the DELETE family so we never silently drop a resource
    if state in ("PRESENT", "IDENTIFIABLE"):
        return [("REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT")], file_id, True
    return [(None, None, "VERIFY_RECORD_ABSENT")], file_id, False


def build_steps(resource_states: dict[tuple, dict]) -> tuple[str, list[dict]]:
    """Returns (deletion_status, unsorted raw step dicts without step_no)."""
    findings, remediations, verifications = [], [], []
    any_finding = False

    for (system_id, resource_id), obs in sorted(resource_states.items()):
        bundles, file_id, noncompliant = _resource_steps(system_id, resource_id, obs)
        any_finding = any_finding or noncompliant
        for finding_op, remediation_op, verify_op in bundles:
            if finding_op:
                findings.append({"phase": "FINDING", "system_id": system_id, "resource_id": resource_id,
                                  "operation": finding_op, "state": OP_STATE[finding_op], "evidence_id": file_id})
            if remediation_op:
                remediations.append({"phase": "REMEDIATION", "system_id": system_id, "resource_id": resource_id,
                                      "operation": remediation_op, "state": OP_STATE[remediation_op], "evidence_id": ""})
            verifications.append({"phase": "VERIFICATION", "system_id": system_id, "resource_id": resource_id,
                                   "operation": verify_op, "state": OP_STATE[verify_op], "evidence_id": file_id if not any_finding else ""})

    status = "INCOMPLETE" if any_finding else "COMPLETE"
    if any_finding:
        for v in verifications:
            v["evidence_id"] = ""
    return status, findings + remediations + verifications


def _sort_key(step: dict) -> tuple:
    phase_idx = PHASE_ORDER.index(step["phase"])
    op_idx = OPERATION_ORDER[step["phase"]].index(step["operation"])
    return (phase_idx, op_idx, step["system_id"], step["resource_id"])


def finalize(status: str, raw_steps: list[dict]) -> tuple[str, str]:
    # NOT_APPLICABLE is only set by intent classification (code/main.py), never
    # inferred here from an empty step list — a DELETION case with zero
    # resolved resources is "no evidence of remaining data found", i.e.
    # COMPLETE with no steps, not "the person never asked to be deleted".
    if status == "NOT_APPLICABLE":
        return "NOT_APPLICABLE", "[]"
    if not raw_steps:
        return "COMPLETE", "[]"
    ordered = sorted(raw_steps, key=_sort_key)
    for i, step in enumerate(ordered, start=1):
        step["step_no"] = i
    return status, json.dumps(ordered, ensure_ascii=False)
