"""Scores a predictions CSV against a gold-answer CSV (same output.csv shape).

Reusable: imported by main.py and by the fix loops in Card 4/7.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

STEP_FIELDS = ("system_id", "resource_id", "operation", "state", "evidence_id")


def load(path: Path) -> dict[str, dict[str, Any]]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = {}
        for r in csv.DictReader(f):
            rows[r["case_id"]] = {
                "deletion_status": r["deletion_status"],
                "steps": json.loads(r["steps_json"]),
            }
        return rows


def _step_tuple(step: dict) -> tuple:
    return tuple(step[k] for k in STEP_FIELDS)


def score(pred: dict[str, dict], gold: dict[str, dict]) -> dict[str, Any]:
    case_ids = sorted(gold.keys())
    n = len(case_ids)

    status_correct = 0
    seq_correct = 0
    tp = fp = fn = 0
    field_keys = ("step_no", "phase") + STEP_FIELDS
    field_correct = {k: 0 for k in field_keys}
    field_total = {k: 0 for k in field_keys}
    misses: list[dict] = []

    for cid in case_ids:
        g = gold.get(cid)
        p = pred.get(cid)
        if p is None:
            misses.append({"case_id": cid, "reason": "missing from predictions"})
            fn += len(g["steps"])
            continue

        status_ok = p["deletion_status"] == g["deletion_status"]
        status_correct += int(status_ok)

        g_steps = g["steps"]
        p_steps = p["steps"]

        g_tuples = [_step_tuple(s) for s in g_steps]
        p_tuples = [_step_tuple(s) for s in p_steps]

        g_remaining = list(g_tuples)
        case_tp = 0
        for t in p_tuples:
            if t in g_remaining:
                g_remaining.remove(t)
                case_tp += 1
        case_fp = len(p_tuples) - case_tp
        case_fn = len(g_remaining)
        tp += case_tp
        fp += case_fp
        fn += case_fn

        seq_ok = status_ok and p_steps == g_steps
        seq_correct += int(seq_ok)

        for i in range(min(len(g_steps), len(p_steps))):
            for key in field_keys:
                field_total[key] += 1
                if g_steps[i].get(key) == p_steps[i].get(key):
                    field_correct[key] += 1

        if not seq_ok:
            misses.append({
                "case_id": cid,
                "status_expected": g["deletion_status"], "status_got": p["deletion_status"],
                "step_count_expected": len(g_steps), "step_count_got": len(p_steps),
                "false_negatives": case_fn, "false_positives": case_fp,
            })

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "n_cases": n,
        "status_accuracy": status_correct / n if n else 0.0,
        "sequence_accuracy": seq_correct / n if n else 0.0,
        "step_precision": precision,
        "step_recall": recall,
        "step_f1": f1,
        "field_accuracy": {
            k: (field_correct[k] / field_total[k] if field_total[k] else 1.0) for k in field_keys
        },
        "misses": misses,
    }


def format_report(result: dict[str, Any]) -> str:
    lines = [
        f"cases: {result['n_cases']}",
        f"status accuracy: {result['status_accuracy']:.3f}",
        f"sequence accuracy: {result['sequence_accuracy']:.3f}",
        f"step precision/recall/F1: {result['step_precision']:.3f} / {result['step_recall']:.3f} / {result['step_f1']:.3f}",
        "field accuracy: " + ", ".join(f"{k}={v:.3f}" for k, v in result["field_accuracy"].items()),
        f"cases with misses: {len(result['misses'])}",
    ]
    return "\n".join(lines)
