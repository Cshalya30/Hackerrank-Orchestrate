"""identity.py + state.py combined (see docs/DECISIONS.md D4 for why files are
consolidated under time pressure): build each user's identifier set (current +
historical), load observations once, and resolve the latest state per
(system_id, resource_id) for a given case's identifier set and audit_at.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from config import USER_IDENTITIES_CSV, USER_AUDIT_LOG_CSV, OBSERVATIONS_JSONL


def _norm(v: str | None) -> str | None:
    if not v:
        return None
    return v.strip().lower()


class IdentityIndex:
    def __init__(self):
        self.by_user: dict[str, dict] = {}
        self.email_to_user: dict[str, str] = {}
        self._load()

    def _load(self):
        with open(USER_IDENTITIES_CSV, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                uid = r["user_id"]
                rec = self.by_user.setdefault(uid, {"emails": set(), "phones": set(), "hashes": set(), "names": set()})
                if r.get("email"):
                    rec["emails"].add(_norm(r["email"]))
                if r.get("phone"):
                    rec["phones"].add(r["phone"].strip())
                if r.get("email_hash"):
                    rec["hashes"].add(r["email_hash"].strip())
                if r.get("name"):
                    rec["names"].add(r["name"].strip())

        with open(USER_AUDIT_LOG_CSV, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                uid = r["user_id"]
                rec = self.by_user.setdefault(uid, {"emails": set(), "phones": set(), "hashes": set(), "names": set()})
                field, old, new = r["field_name"], r.get("old_value"), r.get("new_value")
                for val in (old, new):
                    if not val:
                        continue
                    if field == "email":
                        rec["emails"].add(_norm(val))
                    elif field == "phone":
                        rec["phones"].add(val.strip())
                    elif field == "email_hash":
                        rec["hashes"].add(val.strip())
                    elif field == "name":
                        rec["names"].add(val.strip())

        for uid, rec in self.by_user.items():
            for email in rec["emails"]:
                self.email_to_user[email] = uid

    def resolve_user(self, email: str) -> str | None:
        return self.email_to_user.get(_norm(email))

    def identifier_set(self, user_id: str) -> dict:
        rec = self.by_user.get(user_id, {"emails": set(), "phones": set(), "hashes": set(), "names": set()})
        return {
            "user_id": user_id,
            "emails": rec["emails"],
            "phones": rec["phones"],
            "hashes": rec["hashes"],
            "names": rec["names"],
        }


def load_observations() -> list[dict]:
    obs = []
    with open(OBSERVATIONS_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                obs.append(json.loads(line))
    return obs


def matches_identity(obs: dict, idset: dict) -> bool:
    pii = obs.get("pii") or {}
    if pii.get("email") and _norm(pii["email"]) in idset["emails"]:
        return True
    if pii.get("email_hash") and pii["email_hash"] in idset["hashes"]:
        return True
    if pii.get("phone") and pii["phone"] in idset["phones"]:
        return True
    for ref in obs.get("user_refs") or []:
        if ref == idset["user_id"]:
            return True
    return False


def candidate_observations(all_obs: list[dict], idset: dict) -> list[dict]:
    """PII/user_id matches, PLUS resource continuity: once a (system_id,
    resource_id) is linked by any observation's identifiers, every other
    observation of that SAME resource is included too — even one that has
    since lost its PII (e.g. an already-ANONYMIZED analytics record has no
    email left to match on, but it is still the same resource)."""
    direct = [o for o in all_obs if matches_identity(o, idset)]
    linked_keys = {(o["system_id"], o["resource_id"]) for o in direct}
    if not linked_keys:
        return direct
    direct_ids = {id(o) for o in direct}
    continuity = [
        o for o in all_obs
        if id(o) not in direct_ids and (o["system_id"], o["resource_id"]) in linked_keys
    ]
    return direct + continuity


def _priority_key(o: dict) -> tuple:
    is_claim = bool((o.get("attrs") or {}).get("claim"))
    is_absent = o.get("state") == "ABSENT"
    return (o["observed_at"], 0 if is_claim else 1, 0 if is_absent else 1)


def latest_state_per_resource(candidates: list[dict], audit_at: str) -> dict[tuple, dict]:
    """(system_id, resource_id) -> the winning observation at or before audit_at."""
    by_resource: dict[tuple, list[dict]] = {}
    for o in candidates:
        if o["observed_at"] <= audit_at:
            by_resource.setdefault((o["system_id"], o["resource_id"]), []).append(o)

    result = {}
    for key, obs_list in by_resource.items():
        result[key] = max(obs_list, key=_priority_key)
    return result


def resource_link_overlay(all_obs: list[dict], idset: dict) -> set[tuple]:
    """Resources not directly PII-matched but linked via a matched resource's
    attrs (e.g. search_documents.source_resource_id -> account_id), one hop."""
    direct = candidate_observations(all_obs, idset)
    direct_ids = {o["resource_id"] for o in direct}
    linked = set()
    for o in all_obs:
        src = (o.get("attrs") or {}).get("source_resource_id")
        if src and src in direct_ids:
            linked.add((o["system_id"], o["resource_id"]))
    return linked
