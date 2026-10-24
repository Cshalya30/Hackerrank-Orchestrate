"""Card 3: parse every evidence file into build/observations.jsonl.

One observation per resource sighting (see docs/SPEC.md 4.1). Snapshot-style
sources (SQL dumps, the two JSON "data store" families) are grouped into
per-table/collection "families"; a resource missing from a later family
snapshot that it appeared in earlier becomes a synthesized ABSENT
observation (this is how replica drift / real deletion is detected — see
docs/SPEC.md H1-H4 and the "Replica drift" row in section 2).

Everything here is deterministic string/structure parsing. No LLM calls.
Run: python code/ingest/build.py
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DATASET_DIR, EVIDENCE_FILES_CSV, OBSERVATIONS_JSONL, COVERAGE_TXT, SAMPLE_OUTPUT_CSV, SYSTEM_ACTIVITY_CSV  # noqa: E402
import taxonomy  # noqa: E402

KV_RE = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)')
RESOURCE_ID_RE = re.compile(r"^[a-z_]+_\d+$")
LINK_IDENTITY_RE = re.compile(r"to\s+([\w.+-]+@[\w.-]+)\s+and\s+(user_\d+)")
RESTORE_DOWNSTREAM_RE = re.compile(r"repopulated downstream resource\s+([a-z_]+_\d+)")


def _clean(v):
    if isinstance(v, str):
        v = v.strip('"')
    return v if v not in ("", "null", "None") else None


def _pii(email=None, name=None, phone=None, email_hash=None):
    return {
        "email": email.lower() if isinstance(email, str) else None,
        "name": name,
        "phone": phone,
        "email_hash": email_hash,
    }


def _obs(file_id, observed_at, system_id, resource_id, category, state, pii, user_refs, attrs, source, claim=False):
    attrs = dict(attrs or {})
    if claim:
        attrs["claim"] = True
    return {
        "file_id": file_id, "observed_at": observed_at, "system_id": system_id,
        "resource_id": resource_id, "category": category, "state": state,
        "pii": pii, "user_refs": [r for r in (user_refs or []) if r],
        "attrs": attrs, "source": source,
    }


class FamilyTracker:
    """Accumulates per-family (table/collection) snapshots so we can detect
    a resource disappearing between two snapshots of the same family."""

    def __init__(self):
        # family_key -> list of (snapshot_time, file_id, {resource_id: row_dict})
        self.snapshots: dict[str, list[tuple[str, str, dict]]] = {}

    def add_snapshot(self, family_key: str, snapshot_time: str, file_id: str, rows: dict[str, dict]):
        self.snapshots.setdefault(family_key, []).append((snapshot_time, file_id, rows))

    def resolve(self) -> list[dict]:
        observations = []
        for family_key, snaps in self.snapshots.items():
            snaps = sorted(snaps, key=lambda s: s[0])
            all_resource_ids: set[str] = set()
            for _, _, rows in snaps:
                all_resource_ids.update(rows.keys())

            seen_present = set()
            for snapshot_time, file_id, rows in snaps:
                for rid in all_resource_ids:
                    row = rows.get(rid)
                    if row is not None:
                        seen_present.add(rid)
                        observations.append(row["_make_obs"](file_id, snapshot_time, "PRESENT" if row.get("_present_state") is None else row["_present_state"]))
                    elif rid in seen_present:
                        # was present in an earlier snapshot of this family, missing now
                        last_row = next(r for _, _, rr in reversed(snaps) if (r := rr.get(rid)) is not None)
                        observations.append(last_row["_make_obs"](file_id, snapshot_time, "ABSENT"))
        return observations


def parse_sql(file_id: str, path: Path, captured_at: str, tracker: FamilyTracker) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(text)
    except sqlite3.Error:
        return
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]

    for table in tables:
        cols = [d[1] for d in conn.execute(f"PRAGMA table_info({table})")]
        if "resource_id" not in cols:
            continue
        rows = {}
        for raw in conn.execute(f"SELECT * FROM {table}"):
            row = dict(zip(cols, raw))
            rid = row.get("resource_id")
            if not rid:
                continue
            if "record_json" in row and row.get("record_json"):
                _ingest_generic_record(file_id, captured_at, table, row, tracker)
                continue
            category = taxonomy.TABLE_TO_CATEGORY.get(table, taxonomy.category_for_resource(rid))
            system_id = taxonomy.system_for_resource(rid)
            pii = _pii(
                email=_clean(row.get("email") or row.get("customer_email") or row.get("requester_email") or row.get("owner_email")),
                name=_clean(row.get("full_name") or row.get("display_name") or row.get("requester_name")),
                phone=_clean(row.get("phone") or row.get("owner_phone") or row.get("requester_phone")),
                email_hash=_clean(row.get("email_hash")),
            )
            user_refs = [_clean(row.get("user_id") or row.get("customer_reference") or row.get("subject_reference"))]
            row_time = _clean(row.get("updated_at")) or captured_at
            attrs = {"table": table}
            if row.get("source_resource_id"):
                attrs["source_resource_id"] = row["source_resource_id"]
            present_state = None
            if "restore_allowed" in row:
                present_state = "RESTORE_ALLOWED" if row.get("restore_allowed") else "RESTORE_BLOCKED"
                attrs["restore_allowed"] = bool(row.get("restore_allowed"))
            elif "enabled" in row:
                present_state = "FLOW_ENABLED" if row.get("enabled") else "FLOW_DISABLED"
                attrs["enabled"] = bool(row.get("enabled"))
            elif category in taxonomy.RETAINED_CATEGORIES:
                present_state = "RETAINED"
            elif category in ("SUPPORT_MESSAGE", "EMAIL_DELIVERY_LOG", "ACCOUNT_TOMBSTONE"):
                present_state = "IDENTIFIABLE" if any(pii.values()) else "REDACTED"
            elif category in ("ANALYTICS_PROFILE", "PRODUCT_TELEMETRY"):
                present_state = "IDENTIFIABLE" if any(pii.values()) else "ANONYMIZED"

            def make_obs(fid, t, state, _rid=rid, _sys=system_id, _cat=category, _pii=pii, _refs=user_refs, _attrs=attrs, _table=table, _row_time=row_time):
                return _obs(fid, _row_time if t == captured_at else t, _sys, _rid, _cat, state, _pii, _refs, _attrs, f"sql:{_table}")

            rows[rid] = {"_make_obs": make_obs, "_present_state": present_state}
        if rows:
            tracker.add_snapshot(table, captured_at, file_id, rows)
    conn.close()


def _ingest_generic_record(file_id, captured_at, table, row, tracker):
    rid_outer = row.get("resource_id")
    try:
        record = json.loads(row["record_json"])
    except (json.JSONDecodeError, TypeError):
        record = {}
    collection = row.get("collection_name")
    category = taxonomy.COLLECTION_TO_CATEGORY.get(collection, taxonomy.category_for_resource(rid_outer))
    rid = record.get("resource_id", rid_outer)
    system_id = taxonomy.system_for_resource(rid)
    pii = _pii(
        email=_clean(record.get("email")), name=_clean(record.get("full_name") or record.get("name")),
        phone=_clean(record.get("phone")), email_hash=_clean(record.get("email_hash")),
    )
    user_refs = [_clean(record.get("user_id") or record.get("customer_reference") or record.get("subject_reference"))]
    row_time = _clean(row.get("updated_at")) or captured_at
    attrs = {"table": table, "collection": collection}
    present_state = None
    if category in taxonomy.RETAINED_CATEGORIES:
        present_state = "RETAINED"
    elif category in ("SUPPORT_MESSAGE", "EMAIL_DELIVERY_LOG", "ACCOUNT_TOMBSTONE"):
        present_state = "IDENTIFIABLE" if any(pii.values()) else "REDACTED"
    elif category in ("ANALYTICS_PROFILE", "PRODUCT_TELEMETRY"):
        present_state = "IDENTIFIABLE" if any(pii.values()) else "ANONYMIZED"

    def make_obs(fid, t, state, _rid=rid, _sys=system_id, _cat=category, _pii=pii, _refs=user_refs, _attrs=attrs, _table=f"{table}:{collection}", _row_time=row_time):
        return _obs(fid, _row_time if t == captured_at else t, _sys, _rid, _cat, state, _pii, _refs, _attrs, f"sql_json:{_table}")

    family_key = f"{table}:{collection}"
    tracker.snapshots.setdefault(family_key, [])
    # merge into the latest in-progress snapshot for this (family, file)
    for snap in tracker.snapshots[family_key]:
        if snap[1] == file_id:
            snap[2][rid] = {"_make_obs": make_obs, "_present_state": present_state}
            return
    tracker.add_snapshot(family_key, captured_at, file_id, {rid: {"_make_obs": make_obs, "_present_state": present_state}})


def parse_json(file_id: str, path: Path, captured_at: str, tracker: FamilyTracker) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return

    if "snapshots" in data:  # family 1: snapshot bundle
        for snap in data.get("snapshots", []):
            data_store = snap.get("data_store", "unknown")
            collection = snap.get("collection", "unknown")
            family_key = f"{data_store}:{collection}"
            snap_time = snap.get("captured_at", captured_at)
            rows = {}
            for record in snap.get("records", []):
                rid = record.get("resource_id")
                if not rid:
                    continue
                category = taxonomy.COLLECTION_TO_CATEGORY.get(collection, taxonomy.category_for_resource(rid))
                system_id = taxonomy.system_for_resource(rid)
                pii = _pii(email=_clean(record.get("email")), name=_clean(record.get("full_name")), phone=_clean(record.get("phone")), email_hash=_clean(record.get("email_hash")))
                user_refs = [_clean(record.get("customer_reference") or record.get("user_id"))]
                attrs = {"data_store": data_store, "collection": collection, "account_status": record.get("account_status")}

                def make_obs(fid, t, state, _rid=rid, _sys=system_id, _cat=category, _pii=pii, _refs=user_refs, _attrs=attrs):
                    return _obs(fid, snap_time, _sys, _rid, _cat, state, _pii, _refs, _attrs, f"json_snapshot:{data_store}:{collection}")

                rows[rid] = {"_make_obs": make_obs, "_present_state": None}
            if rows:
                tracker.add_snapshot(family_key, snap_time, file_id, rows)

    elif "service_exports" in data:  # family 4: service_resource_export
        for system_id, lists in data.get("service_exports", {}).items():
            for list_key, entries in lists.items():
                category = taxonomy.SERVICE_EXPORT_LIST_TO_CATEGORY.get(list_key, "USER_PROFILE")
                family_key = f"{system_id}:{list_key}"
                rows = {}
                for entry in entries:
                    rid = entry.get("resource_id")
                    if not rid:
                        continue
                    profile = entry.get("profile", {}) if isinstance(entry.get("profile"), dict) else {}
                    # search_service.index_queries nests the matched identity under hits.documents[0]
                    doc = {}
                    hits = entry.get("hits")
                    if isinstance(hits, dict):
                        docs = hits.get("documents") or []
                        if docs and isinstance(docs[0], dict):
                            doc = docs[0]
                    pii = _pii(
                        email=_clean(entry.get("email") or entry.get("owner_email") or entry.get("customer_email")
                                      or entry.get("requester_email") or profile.get("email") or doc.get("email")),
                        name=_clean(entry.get("full_name") or entry.get("requester_name") or profile.get("full_name") or doc.get("display_name")),
                        phone=_clean(entry.get("phone") or entry.get("owner_phone") or entry.get("requester_phone") or profile.get("phone") or doc.get("phone")),
                        email_hash=_clean(entry.get("email_hash") or profile.get("email_hash") or doc.get("email_hash")),
                    )
                    user_refs = [_clean(
                        entry.get("customer_reference") or entry.get("subject_reference")
                        or profile.get("customer_reference") or doc.get("customer_reference")
                    )]
                    entry_time = entry.get("observed_at", captured_at)
                    status_code = entry.get("status_code")
                    present_state = None
                    if status_code is not None and int(status_code) >= 400:
                        present_state = "ABSENT"
                    elif "restore_allowed" in entry:
                        present_state = "RESTORE_ALLOWED" if entry.get("restore_allowed") else "RESTORE_BLOCKED"
                    elif "enabled" in entry:
                        present_state = "FLOW_ENABLED" if entry.get("enabled") else "FLOW_DISABLED"
                    elif category in ("ANALYTICS_PROFILE", "PRODUCT_TELEMETRY"):
                        present_state = "IDENTIFIABLE" if any(pii.values()) else "ANONYMIZED"
                    attrs = {"list_key": list_key}

                    def make_obs(fid, t, state, _rid=rid, _sys=system_id, _cat=category, _pii=pii, _refs=user_refs, _attrs=attrs, _etime=entry_time, _list_key=list_key):
                        return _obs(fid, _etime, _sys, _rid, _cat, state, _pii, _refs, _attrs, f"json_service_export:{_sys}:{_list_key}")

                    rows[rid] = {"_make_obs": make_obs, "_present_state": present_state}
                if rows:
                    tracker.add_snapshot(family_key, captured_at, file_id, rows)

    elif "collection" in data and "records" in data:  # family 3: analytics-style report
        collection = data.get("collection", "unknown")
        family_key = f"analytics_report:{collection}"
        rows = {}
        for record in data.get("records", []):
            rid = record.get("resource_id")
            if not rid:
                continue
            category = taxonomy.COLLECTION_TO_CATEGORY.get(collection, "ANALYTICS_PROFILE")
            system_id = taxonomy.system_for_resource(rid, fallback="analytics_platform")
            pii = _pii(email=_clean(record.get("email")), phone=_clean(record.get("phone")), email_hash=_clean(record.get("email_hash")))
            user_refs = [_clean(record.get("user_id"))]
            present_state = "IDENTIFIABLE" if any(pii.values()) else "ANONYMIZED"
            attrs = {"collection": collection}

            def make_obs(fid, t, state, _rid=rid, _sys=system_id, _cat=category, _pii=pii, _refs=user_refs, _attrs=attrs):
                return _obs(fid, data.get("captured_at", captured_at), _sys, _rid, _cat, state, _pii, _refs, _attrs, f"json_analytics:{collection}")

            rows[rid] = {"_make_obs": make_obs, "_present_state": present_state}
        if rows:
            tracker.add_snapshot(family_key, data.get("captured_at", captured_at), file_id, rows)

    elif "records" in data and "origin" in data:  # family 2: identity-catalog-style link records
        for record in data.get("records", []):
            rid = record.get("resource_id")
            if not rid:
                continue
            category = taxonomy.category_for_resource(rid)
            system_id = record.get("system") or taxonomy.system_for_resource(rid)
            subject_ref = _clean(record.get("subject_reference"))
            rec_time = record.get("recorded_at", captured_at)
            attrs = {"record_type": record.get("record_type"), "result": record.get("result")}
            obs = _obs(file_id, rec_time, system_id, rid, category, "PRESENT", _pii(), [subject_ref], attrs, "json_catalog:records")
            _append_direct(file_id, obs)


_DIRECT_OBS: list[dict] = []


def _append_direct(file_id: str, obs: dict) -> None:
    _DIRECT_OBS.append(obs)


CATEGORY_LOG_ACTIVE_STATE = {
    "DATA_FLOW": "FLOW_ENABLED",
    "BACKUP_ARCHIVE": "RESTORE_ALLOWED",
    "ANALYTICS_PROFILE": "IDENTIFIABLE",
    "PRODUCT_TELEMETRY": "IDENTIFIABLE",
    "SUPPORT_MESSAGE": "IDENTIFIABLE",
    "EMAIL_DELIVERY_LOG": "IDENTIFIABLE",
    "ACCOUNT_TOMBSTONE": "IDENTIFIABLE",
}


def parse_log(file_id: str, path: Path, captured_at: str) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = {k: _clean(v) for k, v in KV_RE.findall(line)}
        rid = fields.get("resource_id") or fields.get("resource")
        if not rid or not RESOURCE_ID_RE.match(rid):
            continue
        event = (fields.get("event") or fields.get("event_code") or "").lower()
        message = (fields.get("message") or "").lower()
        http_status = fields.get("http_status")
        marker_found = fields.get("marker_found")

        state = "PRESENT"
        if http_status == "404" or "not_found" in event or "not found" in message or marker_found == "false":
            state = "ABSENT"
        elif "deleted" in message or "deletion" in event:
            state = "ABSENT"

        category = taxonomy.category_for_resource(rid)
        if "cache" in event:
            category = "CACHE_ENTRY"
        elif "delivery" in event or "email" in event:
            category = "EMAIL_DELIVERY_LOG"
        elif "marketing" in event or "audience" in event or "contact" in event:
            # B3: analytics_platform contact-lookup records are marketing
            # contacts (REMAINING_RECORD -> DELETE), not an analytics
            # profile to anonymize (case_12 analytics_9914).
            category = "MARKETING_PROFILE"
        elif "telemetry" in event:
            category = "PRODUCT_TELEMETRY"

        # A log line proving a resource was actively read/queried is itself
        # proof of its "needs remediation" state for categories with a
        # binary state model — these sources never carry an explicit
        # enabled/identifiable flag the way a SQL/JSON snapshot row does.
        if state == "PRESENT":
            state = CATEGORY_LOG_ACTIVE_STATE.get(category, state)

        system_id = taxonomy.system_for_resource(rid)
        pii = _pii(email=fields.get("email") or fields.get("customer_email"), email_hash=fields.get("email_hash"))
        user_refs = [fields.get("customer_reference") or fields.get("correlation_key") or fields.get("lookup_key")]
        observed_at = fields.get("timestamp") or captured_at
        obs = _obs(file_id, observed_at, system_id, rid, category, state, pii, user_refs, {"event": event}, "log:kv")
        _append_direct(file_id, obs)


def parse_pipe_text(file_id: str, path: Path, captured_at: str) -> None:
    state_map = {"NOT_FOUND": "ABSENT", "FOUND": "PRESENT", "PRESENT": "PRESENT", "ABSENT": "ABSENT"}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip().lstrip("- ").strip()
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 6:
            continue
        time_, system_id, rid, category, raw_state, identifier = parts[:6]
        if not RESOURCE_ID_RE.match(rid):
            continue
        state = state_map.get(raw_state.upper(), raw_state.upper())
        pii = _pii(email=identifier if "@" in identifier else None)
        user_refs = [identifier if identifier.startswith("user_") else None]
        obs = _obs(file_id, time_, system_id, rid, category, state, pii, user_refs, {}, "text:pipe_table")
        _append_direct(file_id, obs)


ACTIVITY_STATE = {
    "DELETE_RECORD": "ABSENT", "RETAIN_RECORD": "RETAINED", "ANONYMIZE_RECORD": "ANONYMIZED",
    "REDACT_RECORD": "REDACTED", "DISABLE_DATA_FLOW": "FLOW_DISABLED", "BLOCK_RESTORE": "RESTORE_BLOCKED",
    "SYNC_RECORD": "PRESENT", "INDEX_RECORD": "PRESENT",
}
ACTIVITY_CATEGORY = {
    "CREATE_EXPORT": "USER_EXPORT", "CHECK_DATA_FLOW": "DATA_FLOW", "DISABLE_DATA_FLOW": "DATA_FLOW",
    "CHECK_RESTORE_ACCESS": "BACKUP_ARCHIVE", "BLOCK_RESTORE": "BACKUP_ARCHIVE", "REFRESH_CACHE": "CACHE_ENTRY",
    "SEND_EMAIL": "EMAIL_DELIVERY_LOG",
}


def parse_activity() -> None:
    """system_activity.csv: claims (lower priority than file evidence, see
    docs/SPEC.md section 5 activity overlay), plus identity-catalog links and
    the resurrection signal (RESTORE_BACKUP's downstream resource)."""
    with open(SYSTEM_ACTIVITY_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            event_type = row["event_type"]
            result = row["reported_result"]
            rid = row["resource_id"]
            details = row.get("details", "")
            activity_id = row["activity_id"]
            event_time = row["event_time"]

            if event_type == "CLASSIFY_REQUEST":
                if "non-deletion" in details.lower() and RESOURCE_ID_RE.match(rid):
                    obs = _obs(activity_id, event_time, taxonomy.system_for_resource(rid), rid,
                                "CLASSIFICATION", "NON_DELETION", _pii(), [], {"event_type": event_type}, f"activity:{activity_id}")
                    _append_direct(None, obs)
                continue

            if event_type == "LINK_RESOURCE_IDENTITY":
                m = LINK_IDENTITY_RE.search(details)
                if m and RESOURCE_ID_RE.match(rid):
                    email, user_id = m.group(1), m.group(2)
                    obs = _obs(activity_id, event_time, taxonomy.system_for_resource(rid), rid,
                                taxonomy.category_for_resource(rid), "PRESENT", _pii(email=email), [user_id],
                                {"event_type": event_type}, f"activity:{activity_id}", claim=True)
                    _append_direct(None, obs)
                continue

            if event_type == "RESTORE_BACKUP" and result == "SUCCESS":
                m = RESTORE_DOWNSTREAM_RE.search(details)
                if m:
                    downstream = m.group(1)
                    obs = _obs(activity_id, event_time, taxonomy.system_for_resource(downstream), downstream,
                                taxonomy.category_for_resource(downstream), "PRESENT", _pii(), [],
                                {"event_type": event_type, "resurrected_by": rid}, f"activity:{activity_id}", claim=True)
                    _append_direct(None, obs)
                continue

            if not RESOURCE_ID_RE.match(rid) or result != "SUCCESS":
                continue
            category = ACTIVITY_CATEGORY.get(event_type, taxonomy.category_for_resource(rid))
            state = ACTIVITY_STATE.get(event_type, CATEGORY_LOG_ACTIVE_STATE.get(category, "PRESENT"))
            obs = _obs(activity_id, event_time, row.get("target_system") or taxonomy.system_for_resource(rid), rid,
                        category, state, _pii(), [], {"event_type": event_type}, f"activity:{activity_id}", claim=True)
            _append_direct(None, obs)


def parse_pdf(file_id: str, path: Path, captured_at: str) -> None:
    """B5: wire the 4 PDFs. Each uses a distinct template, so this is
    targeted extraction (regex over pypdf's text), not a generic parser —
    there are only 4 files, and docs/GAPS.md item 8 already confirmed
    pypdf extracts them cleanly."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return
    try:
        reader = PdfReader(str(path))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:  # noqa: BLE001
        return

    # delivery_correction_attachment.pdf: a support attachment uploaded by
    # the customer themselves -> SUPPORT_ATTACHMENT, owned only by subject
    # (evidence_58 proves case_07's support_001).
    m = re.search(r"reference\s+\S+\s*/\s*(support_\d+)", text)
    if m:
        rid = m.group(1)
        email_m = re.search(r"[\w.+-]+@[\w.-]+", text)
        is_customer_upload = "uploader customer" in text.lower()
        pii = _pii(email=email_m.group(0) if email_m else None)
        category = "SUPPORT_ATTACHMENT" if is_customer_upload else "SUPPORT_MESSAGE"
        obs = _obs(file_id, captured_at, "support_platform", rid, category, "PRESENT", pii, [], {}, "pdf:support_attachment")
        _append_direct(file_id, obs)

    # security_retention_extract.pdf: a signed compliance-journal extract
    # naming one audit_record_* and its subject_reference directly.
    m = re.search(r"Event reference\s+(audit_record_\d+)", text)
    if m:
        rid = m.group(1)
        subj_m = re.search(r"subject reference\s+(user_\d+)", text)
        obs = _obs(file_id, captured_at, "security_service", rid, "SECURITY_AUDIT_LOG", "RETAINED",
                    _pii(), [subj_m.group(1)] if subj_m else [], {}, "pdf:compliance_journal")
        _append_direct(file_id, obs)


def main() -> int:
    with open(EVIDENCE_FILES_CSV, newline="", encoding="utf-8") as f:
        manifest = list(csv.DictReader(f))

    tracker = FamilyTracker()
    skipped = {"pdf": 0, "png": 0}
    for row in manifest:
        file_id, rel_path, captured_at = row["file_id"], row["file_path"], row["captured_at"]
        path = DATASET_DIR / rel_path
        ext = path.suffix.lower()
        if not path.exists():
            continue
        if ext == ".sql":
            parse_sql(file_id, path, captured_at, tracker)
        elif ext == ".json":
            parse_json(file_id, path, captured_at, tracker)
        elif ext == ".log":
            parse_log(file_id, path, captured_at)
        elif ext == ".txt":
            parse_pipe_text(file_id, path, captured_at)
        elif ext == ".pdf":
            parse_pdf(file_id, path, captured_at)
        elif ext == ".png":
            skipped["png"] += 1

    parse_activity()
    observations = tracker.resolve() + _DIRECT_OBS

    OBSERVATIONS_JSONL.parent.mkdir(exist_ok=True)
    with open(OBSERVATIONS_JSONL, "w", encoding="utf-8") as f:
        for obs in observations:
            f.write(json.dumps(obs, ensure_ascii=False) + "\n")

    # coverage check against sample_output.csv resource ids
    sample_resource_ids = set()
    with open(SAMPLE_OUTPUT_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for step in json.loads(r["steps_json"]):
                sample_resource_ids.add((step["system_id"], step["resource_id"]))

    observed_pairs = {(o["system_id"], o["resource_id"]) for o in observations}
    missing = sorted(sample_resource_ids - observed_pairs)
    coverage_pct = 100.0 * (len(sample_resource_ids) - len(missing)) / len(sample_resource_ids) if sample_resource_ids else 0.0

    with open(COVERAGE_TXT, "w", encoding="utf-8") as f:
        f.write(f"observations: {len(observations)}\n")
        f.write(f"distinct (system_id, resource_id) observed: {len(observed_pairs)}\n")
        f.write(f"sample_output.csv requires: {len(sample_resource_ids)}\n")
        f.write(f"coverage: {coverage_pct:.1f}%\n")
        f.write(f"missing ({len(missing)}):\n")
        for pair in missing:
            f.write(f"  {pair}\n")

    print(f"wrote {len(observations)} observations -> {OBSERVATIONS_JSONL}")
    print(f"coverage vs sample_output.csv: {coverage_pct:.1f}% ({len(missing)} missing)")
    print(f"skipped (no parser): pdf={skipped['pdf']} png={skipped['png']}")
    if missing:
        print("first 15 missing pairs:", missing[:15])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
