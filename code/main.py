"""Entry point: python code/main.py --split sample|full --out output.csv

Reads dataset/, resolves each case's identity and resource states from
build/observations.jsonl (run code/ingest/build.py first), plans the
findings/remediation/verification steps, and writes the output CSV.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import SAMPLE_REQUESTS_CSV, DELETION_REQUESTS_CSV, OUTPUT_CSV  # noqa: E402
import intent  # noqa: E402
import planner  # noqa: E402
from resolve import IdentityIndex, load_observations, candidate_observations, latest_state_per_resource, resource_link_overlay  # noqa: E402
from account_linker import AccountLinker  # noqa: E402


def run(requests_path: Path, out_path: Path) -> list[dict]:
    identity_index = IdentityIndex()
    all_obs = load_observations()
    linker = AccountLinker(identity_index, all_obs)

    classify_overrides = {
        o["resource_id"] for o in all_obs
        if o.get("category") == "CLASSIFICATION" and o.get("state") == "NON_DELETION"
    }
    unresolved_accounts = []

    rows_out = []
    with open(requests_path, newline="", encoding="utf-8") as f:
        requests = list(csv.DictReader(f))

    for req in requests:
        case_id = req["case_id"]
        email = req["email"]
        audit_at = req["audit_at"]
        request_text = req["request_text"]

        user_id = identity_index.resolve_user(email)
        idset = identity_index.identifier_set(user_id) if user_id else {
            "user_id": None, "emails": {email.strip().lower()}, "phones": set(), "hashes": set(), "names": set(),
        }

        candidates = candidate_observations(all_obs, idset)
        candidate_resource_ids = {o["resource_id"] for o in candidates}
        account_override = bool(classify_overrides & candidate_resource_ids)

        decision, _reason = intent.classify_case(request_text, account_override)

        if decision == "NON_DELETION":
            rows_out.append({"case_id": case_id, "deletion_status": "NOT_APPLICABLE", "steps_json": "[]"})
            continue

        linked = resource_link_overlay(all_obs, idset)
        linked_obs = [o for o in all_obs if (o["system_id"], o["resource_id"]) in linked]
        resource_states = latest_state_per_resource(candidates + linked_obs, audit_at)

        # Group A: every deletion case gets a guaranteed account_service
        # verification, resolved with the (a)/(b) -> (c) batch -> (d)
        # fallback priority order (see code/account_linker.py).
        account_id, account_rule = linker.account_for(case_id)
        if account_id:
            resource_states[("account_service", account_id)] = linker.account_state(account_id, audit_at)
        else:
            unresolved_accounts.append(case_id)

        # A3: a retained security_service audit record is verified PRESENT,
        # never a finding/remediation target — only when real evidence
        # resolves one for this user (never guessed).
        audit_id = linker.audit_record_for(case_id)
        if audit_id and ("security_service", audit_id) not in resource_states:
            audit_obs = next(
                (o for o in all_obs if o["resource_id"] == audit_id and o["system_id"] == "security_service" and o["observed_at"] <= audit_at),
                None,
            )
            if audit_obs:
                resource_states[("security_service", audit_id)] = audit_obs

        status, raw_steps = planner.build_steps(resource_states)
        status, steps_json = planner.finalize(status, raw_steps)
        rows_out.append({"case_id": case_id, "deletion_status": status, "steps_json": steps_json})

    rows_out.sort(key=lambda r: r["case_id"])

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"])
        writer.writeheader()
        writer.writerows(rows_out)

    if unresolved_accounts:
        print(f"WARNING: {len(unresolved_accounts)} case(s) have no resolvable account_service id: {unresolved_accounts[:10]}", file=sys.stderr)

    return rows_out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["sample", "full"], default="full")
    parser.add_argument("--out", default=str(OUTPUT_CSV))
    args = parser.parse_args()

    requests_path = SAMPLE_REQUESTS_CSV if args.split == "sample" else DELETION_REQUESTS_CSV
    out_path = Path(args.out)

    rows = run(requests_path, out_path)

    from collections import Counter
    dist = Counter(r["deletion_status"] for r in rows)
    print(f"wrote {len(rows)} rows -> {out_path}")
    print("status distribution:", dict(dist))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
