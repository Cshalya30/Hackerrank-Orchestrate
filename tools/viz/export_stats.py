"""Reads build artifacts (observations.jsonl, traces/, llm_ledger.jsonl,
output.csv, sample eval) and writes tools/viz/pipeline.json for the
pipeline visualizer (index.html in this folder).

Run: python tools/viz/export_stats.py
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
sys.path.insert(0, str(REPO_ROOT / "code"))
from config import (  # noqa: E402
    OBSERVATIONS_JSONL, LLM_LEDGER_JSONL, OUTPUT_CSV, BUILD_DIR,
    SAMPLE_REQUESTS_CSV, SAMPLE_OUTPUT_CSV, DELETION_REQUESTS_CSV,
)

TRACES_DIR = BUILD_DIR / "traces"
OUT_PATH = HERE / "pipeline.json"


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_nodes_edges(observations: list[dict], output_rows: list[dict], llm_entries: list[dict]) -> tuple[list[dict], list[dict]]:
    # "source" is a fine-grained per-file tag (e.g. "json_snapshot:search_service:customer_search_documents");
    # bucket by its coarse category prefix (before the first ':') for a readable breakdown.
    by_source = Counter(o.get("source", "unknown").split(":", 1)[0] for o in observations)
    n_requests_full = len(_read_csv(DELETION_REQUESTS_CSV))
    n_requests_sample = len(_read_csv(SAMPLE_REQUESTS_CSV))
    status_counts = Counter(r["deletion_status"] for r in output_rows)
    llm_calls = len(llm_entries)
    llm_tokens = sum(e.get("input_tokens", 0) + e.get("output_tokens", 0) for e in llm_entries)

    nodes = [
        {"id": "requests", "label": "Deletion Requests", "kind": "Data",
         "file": "dataset/deletion_requests.csv", "function": "-",
         "count_in": None, "count_out": n_requests_full + n_requests_sample,
         "desc": "518 full-run requests + 32 public samples. Each has case_id, email, audit_at, request_text."},
        {"id": "intent", "label": "Intent (LLM)", "kind": "LLM",
         "file": "code/intent.py", "function": "classify_case",
         "count_in": n_requests_full + n_requests_sample, "count_out": llm_calls,
         "desc": "Classifies request_text into DELETE_REQUEST / DELETION_VERIFICATION / OTHER_SERVICE "
                 "via batched, cached Gemini Flash-Lite calls (thinking off); a deterministic keyword "
                 "fallback covers the no-API-key case. Only OTHER_SERVICE maps to NOT_APPLICABLE.",
         "llm_calls": llm_calls, "llm_tokens": llm_tokens},
        {"id": "identity", "label": "Identity Resolution", "kind": "Deterministic",
         "file": "code/resolve.py", "function": "IdentityIndex.resolve_user",
         "count_in": n_requests_full + n_requests_sample, "count_out": None,
         "desc": "Maps a request's email to a user_id and the full historical identifier set "
                 "(current + historical emails, hashes, phones, names) via user_identities.csv "
                 "and user_audit_log.csv."},
        {"id": "ingest", "label": "Evidence Ingest", "kind": "Deterministic",
         "file": "code/ingest/build.py", "function": "main",
         "count_in": 94, "count_out": len(observations),
         "desc": "Parses the 94-file evidence corpus (SQL dumps, JSON, logs, system_activity.csv "
                 "claims) once into observations.jsonl. PDF/PNG evidence is parsed by separate "
                 "scripts not wired into this step (see docs/DECISIONS.md D8-D10).",
         "by_source": dict(by_source)},
        {"id": "state", "label": "Point-in-time State", "kind": "Deterministic",
         "file": "code/resolve.py", "function": "latest_state_per_resource",
         "count_in": len(observations), "count_out": None,
         "desc": "For each (system_id, resource_id) linked to a user, takes the latest observation "
                 "at or before audit_at. File evidence outranks activity claims; PRESENT beats ABSENT "
                 "on an exact-timestamp tie (replica drift)."},
        {"id": "policy", "label": "Policy / Account Rules", "kind": "Deterministic",
         "file": "code/account_linker.py", "function": "AccountLinker.account_for",
         "count_in": None, "count_out": None,
         "desc": "Resolves the account_service resource for every case via a priority chain: "
                 "direct evidence link -> catalog link -> same-day deletion_worker batch order -> "
                 "zero-padded user-number fallback."},
        {"id": "planner", "label": "Planner", "kind": "Deterministic",
         "file": "code/planner.py", "function": "build_steps / finalize",
         "count_in": None, "count_out": len(output_rows),
         "desc": "Turns resolved resource states into an ordered FINDING -> REMEDIATION -> "
                 "VERIFICATION step list and derives the case's COMPLETE/INCOMPLETE/NOT_APPLICABLE status."},
        {"id": "validator", "label": "Validator", "kind": "Validation",
         "file": "code/validate.py", "function": "main",
         "count_in": len(output_rows), "count_out": len(output_rows),
         "desc": "Checks output.csv's contract: row count, sort order, step numbering/ordering, "
                 "evidence-citation rules, operation/state consistency."},
        {"id": "output", "label": "output.csv", "kind": "Data",
         "file": "output.csv", "function": "-",
         "count_in": len(output_rows), "count_out": None,
         "desc": "Final submission artifact: case_id, deletion_status, steps_json.",
         "status_counts": dict(status_counts)},
    ]

    edges = [
        {"from": "requests", "to": "intent", "count": n_requests_full + n_requests_sample},
        {"from": "intent", "to": "identity", "count": n_requests_full + n_requests_sample},
        {"from": "ingest", "to": "state", "count": len(observations)},
        {"from": "identity", "to": "state", "count": None},
        {"from": "state", "to": "policy", "count": None},
        {"from": "policy", "to": "planner", "count": None},
        {"from": "planner", "to": "validator", "count": len(output_rows)},
        {"from": "validator", "to": "output", "count": len(output_rows)},
    ]
    return nodes, edges


def build_cases(output_rows: list[dict]) -> list[dict]:
    cases = []
    for row in output_rows:
        case_id = row["case_id"]
        steps = json.loads(row["steps_json"]) if row["steps_json"] else []
        trace_path = TRACES_DIR / f"{case_id}.json"
        trace = json.loads(trace_path.read_text(encoding="utf-8")) if trace_path.exists() else {}

        resources = {}
        for s in steps:
            key = (s["system_id"], s["resource_id"])
            resources.setdefault(key, {
                "system_id": s["system_id"], "resource_id": s["resource_id"],
                "state": s["state"], "evidence_id": s.get("evidence_id") or None,
                "operations": [],
            })
            resources[key]["operations"].append(s["operation"])
            resources[key]["state"] = s["state"]

        cases.append({
            "case_id": case_id,
            "status": row["deletion_status"],
            "user_id": trace.get("user_id"),
            "account_id": trace.get("account_id"),
            "account_rule": trace.get("account_rule"),
            "audit_record_id": trace.get("audit_record_id"),
            "resources": list(resources.values()),
            "steps": steps,
        })
    return cases


def build_metrics(llm_entries: list[dict]) -> dict:
    sample_pred_path = BUILD_DIR / "sample_output_pred.csv"
    metrics: dict = {}
    if sample_pred_path.exists() and SAMPLE_OUTPUT_CSV.exists():
        sys.path.insert(0, str(REPO_ROOT / "code" / "evaluation"))
        import eval as eval_mod  # noqa: E402  (code/evaluation/eval.py)
        pred = eval_mod.load(sample_pred_path)
        gold = eval_mod.load(SAMPLE_OUTPUT_CSV)
        result = eval_mod.score(pred, gold)
        metrics["status_accuracy"] = result["status_accuracy"]
        metrics["sequence_accuracy"] = result["sequence_accuracy"]
        metrics["step_precision"] = result["step_precision"]
        metrics["step_recall"] = result["step_recall"]
        metrics["step_f1"] = result["step_f1"]

    llm_cost = sum(
        (e.get("input_tokens", 0) / 1e6) * 0.075 + (e.get("output_tokens", 0) / 1e6) * 0.30
        for e in llm_entries
    )
    metrics["llm_calls"] = len(llm_entries)
    metrics["llm_tokens"] = sum(e.get("input_tokens", 0) + e.get("output_tokens", 0) for e in llm_entries)
    metrics["llm_cost_usd"] = round(llm_cost, 6)
    return metrics


def main() -> int:
    observations = _read_jsonl(OBSERVATIONS_JSONL)
    output_rows = _read_csv(OUTPUT_CSV)
    llm_entries = _read_jsonl(LLM_LEDGER_JSONL)

    nodes, edges = build_nodes_edges(observations, output_rows, llm_entries)
    cases = build_cases(output_rows)
    metrics = build_metrics(llm_entries)
    status_counts = Counter(r["deletion_status"] for r in output_rows)

    pipeline = {
        "generated_from": {
            "observations": len(observations),
            "output_rows": len(output_rows),
            "llm_calls": len(llm_entries),
        },
        "metrics": metrics,
        "status_counts": dict(status_counts),
        "nodes": nodes,
        "edges": edges,
        "cases": cases,
    }

    OUT_PATH.write_text(json.dumps(pipeline, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT_PATH} ({len(cases)} cases, {len(nodes)} nodes, {len(edges)} edges)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
