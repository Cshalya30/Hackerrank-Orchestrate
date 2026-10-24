"""Run 2, Group A: guarantee every deletion case gets its account_service
verification, using the priority order the owner's advisor traced from the
32 gold samples (docs/SPEC.md H-series + the RUN2 instructions):

  (a) an observation whose identifiers match the user AND resource_id starts
      with account_ (this also covers (b), LINK_RESOURCE_IDENTITY, since
      those are ingested as ordinary observations);
  (c) batch matching: find the day a deletion_worker DELETE_RECORD activity
      processed one of this user's OTHER evidence-linked resources; take
      that day's unlinked account_service DELETE_RECORD activities in
      event_time order and zip them against that day's unlinked requests
      (both splits combined) in requested_at order;
  (d) account_{user_number:03d} fallback, only for user_01..user_10 (gold
      uses this even when the id appears in no evidence file).

Also resolves the retained security_service audit_record for a user (A3),
and account-absence-by-omission evidence (A5): when an account_id has zero
direct observations, cite the latest account_service snapshot file at or
before audit_at instead of leaving it unresolved.

Writes one trace file per case to build/traces/<case_id>.json recording
which rule fired. This module computes linkage globally across BOTH
request files, since the batch-matching rule needs the full pool.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from config import SAMPLE_REQUESTS_CSV, DELETION_REQUESTS_CSV, SYSTEM_ACTIVITY_CSV, EVIDENCE_FILES_CSV, BUILD_DIR
from resolve import IdentityIndex, load_observations, candidate_observations

TRACE_DIR = BUILD_DIR / "traces"
OTHER_SYSTEMS = {"support_platform", "search_service", "analytics_platform", "integration_service", "backup_service", "identity_service"}


def _load_requests() -> list[dict]:
    requests = []
    for path in (SAMPLE_REQUESTS_CSV, DELETION_REQUESTS_CSV):
        with open(path, newline="", encoding="utf-8") as f:
            requests.extend(list(csv.DictReader(f)))
    return requests


class AccountLinker:
    def __init__(self, identity_index: IdentityIndex, all_obs: list[dict]):
        self.identity_index = identity_index
        self.all_obs = all_obs
        self.account_resolution: dict[str, tuple[str | None, str]] = {}
        self.audit_resolution: dict[str, str | None] = {}
        self.account_snapshot_files: list[tuple[str, str]] = []  # (file_id, captured_at), sorted
        self._build()

    def _build(self) -> None:
        requests = _load_requests()

        with open(SYSTEM_ACTIVITY_CSV, newline="", encoding="utf-8") as f:
            activity_rows = list(csv.DictReader(f))
        account_delete_rows = [r for r in activity_rows if r["event_type"] == "DELETE_RECORD" and r["target_system"] == "account_service"]
        activity_by_rid: dict[str, list[dict]] = defaultdict(list)
        for r in activity_rows:
            activity_by_rid[r["resource_id"]].append(r)

        with open(EVIDENCE_FILES_CSV, newline="", encoding="utf-8") as f:
            captured_at_by_file = {r["file_id"]: r["captured_at"] for r in csv.DictReader(f)}

        # Only genuine account_service SNAPSHOT dumps count as omission proof
        # (a full table/export covering many accounts) — a single log line
        # mentioning one account_ id is not evidence that any OTHER account
        # is absent from it, so logs/pipe-text/activity sources are excluded.
        SNAPSHOT_SOURCE_PREFIXES = ("sql:", "sql_json:", "json_snapshot:", "json_service_export:")
        account_file_ids = {
            o["file_id"] for o in self.all_obs
            if o.get("category") == "USER_PROFILE" and o.get("system_id") == "account_service"
            and o.get("file_id") and str(o.get("source", "")).startswith(SNAPSHOT_SOURCE_PREFIXES)
        }
        self.account_snapshot_files = sorted(
            ((fid, captured_at_by_file.get(fid, "")) for fid in account_file_ids if captured_at_by_file.get(fid)),
            key=lambda t: t[1],
        )

        case_info: dict[str, dict] = {}
        directly_linked_accounts: set[str] = set()

        for req in requests:
            case_id = req["case_id"]
            email = req["email"]
            user_id = self.identity_index.resolve_user(email)
            idset = self.identity_index.identifier_set(user_id) if user_id else {
                "user_id": user_id, "emails": {email.strip().lower()}, "phones": set(), "hashes": set(), "names": set(),
            }
            candidates = candidate_observations(self.all_obs, idset)
            account_candidates = sorted({
                o["resource_id"] for o in candidates
                if o["system_id"] == "account_service" and o["resource_id"].startswith("account_")
            })
            direct_account = account_candidates[0] if account_candidates else None
            if direct_account:
                directly_linked_accounts.add(direct_account)

            other_resource_ids = sorted({o["resource_id"] for o in candidates if o["system_id"] in OTHER_SYSTEMS})

            audit_candidates = [o for o in candidates if o["system_id"] == "security_service" and o["resource_id"].startswith("audit_record_")]
            audit_id = audit_candidates[0]["resource_id"] if audit_candidates else None

            case_info[case_id] = {
                "req": req, "user_id": user_id, "direct_account": direct_account,
                "other_resource_ids": other_resource_ids, "audit_id": audit_id,
            }
            self.audit_resolution[case_id] = audit_id

        # rule (c): batch-day grouping for cases with no direct account link
        day_groups: dict[str, list[str]] = defaultdict(list)
        for case_id, info in case_info.items():
            if info["direct_account"]:
                continue
            day = None
            for rid in info["other_resource_ids"]:
                acts = sorted(activity_by_rid.get(rid, []), key=lambda a: a["event_time"])
                if acts:
                    day = acts[0]["event_time"][:10]
                    break
            if day:
                day_groups[day].append(case_id)

        resolved: dict[str, tuple[str, str]] = {
            cid: (info["direct_account"], "a_or_b") for cid, info in case_info.items() if info["direct_account"]
        }

        for day, case_ids in day_groups.items():
            day_accounts = sorted(
                (r for r in account_delete_rows if r["event_time"].startswith(day) and r["resource_id"] not in directly_linked_accounts),
                key=lambda r: r["event_time"],
            )
            day_cases = sorted(case_ids, key=lambda cid: case_info[cid]["req"]["requested_at"])
            for acc_row, cid in zip(day_accounts, day_cases):
                resolved[cid] = (acc_row["resource_id"], "c_batch")
                directly_linked_accounts.add(acc_row["resource_id"])

        # rule (d): zero-padded fallback, users 01-10 only
        for case_id, info in case_info.items():
            if case_id in resolved:
                continue
            uid = info["user_id"]
            if uid and uid.startswith("user_"):
                try:
                    num = int(uid.split("_", 1)[1])
                except ValueError:
                    num = None
                if num and 1 <= num <= 10:
                    resolved[case_id] = (f"account_{num:03d}", "d_fallback")

        self.account_resolution = {
            cid: resolved.get(cid, (None, "unresolved")) for cid in case_info
        }

        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        for case_id, info in case_info.items():
            account_id, rule = self.account_resolution[case_id]
            trace = {
                "case_id": case_id, "user_id": info["user_id"],
                "account_id": account_id, "account_rule": rule,
                "audit_record_id": info["audit_id"],
                "other_resource_ids": info["other_resource_ids"],
            }
            (TRACE_DIR / f"{case_id}.json").write_text(json.dumps(trace, indent=2), encoding="utf-8")

    def account_for(self, case_id: str) -> tuple[str | None, str]:
        return self.account_resolution.get(case_id, (None, "unresolved"))

    def audit_record_for(self, case_id: str) -> str | None:
        return self.audit_resolution.get(case_id)

    def account_state(self, account_id: str, audit_at: str) -> dict:
        """The account's resolved observation, or (A5) an omission-proof
        ABSENT citing the latest account_service snapshot file <= audit_at.

        File-based observations (real evidence) always outrank activity
        claims; a bare claim never outranks the omission proof either — a
        claim about one resource is weaker than "this resource is absent
        from the dump that covers it" (see RUN2 Group A notes)."""
        own = [o for o in self.all_obs if o["resource_id"] == account_id and o["system_id"] == "account_service" and o["observed_at"] <= audit_at]
        file_based = [o for o in own if not (o.get("attrs") or {}).get("claim")]
        if file_based:
            is_absent = lambda o: o["state"] == "ABSENT"
            return max(file_based, key=lambda o: (o["observed_at"], 0 if is_absent(o) else 1))

        best_file = None
        for file_id, captured_at in self.account_snapshot_files:
            if captured_at <= audit_at:
                best_file = file_id
        if best_file:
            return {
                "file_id": best_file, "observed_at": audit_at, "system_id": "account_service",
                "resource_id": account_id, "category": "USER_PROFILE", "state": "ABSENT",
                "pii": {}, "user_refs": [], "attrs": {"proof": "omission"}, "source": "omission",
            }

        # last resort: a bare activity claim is weaker evidence than omission
        # proof, but it beats leaving the mandatory account step uncited.
        if own:
            return max(own, key=lambda o: o["observed_at"])
        return {
            "file_id": "", "observed_at": audit_at, "system_id": "account_service",
            "resource_id": account_id, "category": "USER_PROFILE", "state": "ABSENT",
            "pii": {}, "user_refs": [], "attrs": {"proof": "unresolved"}, "source": "unresolved",
        }
