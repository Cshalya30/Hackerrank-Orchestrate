"""Three custom evaluation cases (owner-required, problem_statement.md
"Evaluation" section / AGENTS.md 6.8). Each builds a small synthetic
observation set directly (not drawn from dataset/) and asserts the planner
produces the right decision, isolating one mechanism at a time.

Run: python code/evaluation/custom_cases/test_custom_cases.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import intent  # noqa: E402
import planner  # noqa: E402
from resolve import matches_identity, latest_state_per_resource  # noqa: E402


def case_1_not_applicable():
    """A request that explicitly asks to keep the account is NOT_APPLICABLE,
    even though it mentions removing something (a common export's details)."""
    text = "Please export my order history and email it to me, but leave my account and profile exactly as they are."
    decision, _ = intent.classify_case(text, classify_request_override=False)
    assert decision == "OTHER_SERVICE", f"expected OTHER_SERVICE, got {decision}"
    assert decision not in intent.DELETION_LABELS
    print("PASS case_1_not_applicable:", decision)


def case_2_old_identifier_match():
    """A resource only carries the user's OLD (pre-change) email hash should
    still match via identity.py's historical identifier set."""
    idset = {
        "user_id": "user_99", "emails": {"new.email@example.com"},
        "phones": set(), "hashes": {"OLD_HASH_123"}, "names": set(),
    }
    obs = {
        "file_id": "evidence_99", "observed_at": "2026-01-01T00:00:00Z",
        "system_id": "analytics_platform", "resource_id": "analytics_0001",
        "category": "ANALYTICS_PROFILE", "state": "IDENTIFIABLE",
        "pii": {"email": None, "name": None, "phone": None, "email_hash": "OLD_HASH_123"},
        "user_refs": [], "attrs": {}, "source": "test",
    }
    assert matches_identity(obs, idset), "expected old email_hash to match the identifier set"
    status, raw_steps = planner.build_steps({(obs["system_id"], obs["resource_id"]): obs})
    assert status == "INCOMPLETE"
    assert any(s["operation"] == "ANONYMIZE_RECORD" for s in raw_steps)
    print("PASS case_2_old_identifier_match: matched via historical hash, planned ANONYMIZE_RECORD")


def case_3_resurrection_after_deletion():
    """A resource deleted at T1, then resurrected by a later successful
    SYNC/RESTORE activity claim at T2 > T1 with no later file evidence,
    must resolve PRESENT at an audit_at between T2 and any later check —
    this is the 'ghost data' scenario the whole challenge is about."""
    deleted_obs = {
        "file_id": "evidence_10", "observed_at": "2026-01-01T00:00:00Z",
        "system_id": "search_service", "resource_id": "search_9001",
        "category": "SEARCH_INDEX_ENTRY", "state": "ABSENT",
        "pii": {"email": "ghost@example.com", "name": None, "phone": None, "email_hash": None},
        "user_refs": [], "attrs": {}, "source": "test",
    }
    resurrected_obs = {
        "file_id": "activity_2002", "observed_at": "2026-01-05T00:00:00Z",
        "system_id": "search_service", "resource_id": "search_9001",
        "category": "SEARCH_INDEX_ENTRY", "state": "PRESENT",
        "pii": {"email": "ghost@example.com", "name": None, "phone": None, "email_hash": None},
        "user_refs": [], "attrs": {"claim": True, "event_type": "RESTORE_BACKUP"}, "source": "test",
    }
    resolved = latest_state_per_resource([deleted_obs, resurrected_obs], audit_at="2026-01-10T00:00:00Z")
    key = ("search_service", "search_9001")
    assert resolved[key]["state"] == "PRESENT", f"expected resurrection to win, got {resolved[key]['state']}"
    status, raw_steps = planner.build_steps(resolved)
    assert status == "INCOMPLETE"
    assert any(s["operation"] == "REPORT_REMAINING_RECORD" for s in raw_steps)
    print("PASS case_3_resurrection_after_deletion: later activity correctly overrides the earlier file-proven deletion")


if __name__ == "__main__":
    case_1_not_applicable()
    case_2_old_identifier_match()
    case_3_resurrection_after_deletion()
    print("\nall 3 custom cases passed")
