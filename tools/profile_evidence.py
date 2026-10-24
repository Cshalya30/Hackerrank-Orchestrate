"""Card 2: profile every evidence file's structure (tables/keys/event names).

Writes the full per-file profile to build/evidence_profile.txt and prints a
capped summary to stdout. Never prints raw record content containing PII;
only structural facts (table/column/key names, counts).

Run: python tools/profile_evidence.py
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))
from config import DATASET_DIR, EVIDENCE_DIR, EVIDENCE_FILES_CSV, EVIDENCE_PROFILE_TXT  # noqa: E402

CREATE_TABLE_RE = re.compile(r"CREATE TABLE\s+[\"'`]?(\w+)[\"'`]?\s*\(([^;]*?)\)\s*;", re.IGNORECASE | re.DOTALL)
KV_RE = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)')


def profile_sql(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    tables = {}
    for m in CREATE_TABLE_RE.finditer(text):
        name = m.group(1)
        cols = [c.strip().split()[0] for c in m.group(2).split(",") if c.strip()]
        tables[name] = cols

    row_counts = {}
    try:
        conn = sqlite3.connect(":memory:")
        conn.executescript(text)
        for name in tables:
            try:
                row_counts[name] = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            except sqlite3.Error:
                row_counts[name] = "?"
        conn.close()
    except sqlite3.Error as exc:
        return {"type": "sql", "tables": tables, "row_counts": row_counts, "exec_error": str(exc)}
    return {"type": "sql", "tables": tables, "row_counts": row_counts}


def profile_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        return {"type": "json", "parse_error": str(exc)}

    def top_shape(obj, depth=0):
        if depth > 2:
            return "..."
        if isinstance(obj, dict):
            return {k: top_shape(v, depth + 1) for k, v in list(obj.items())[:12]}
        if isinstance(obj, list):
            return [top_shape(obj[0], depth + 1)] if obj else []
        return type(obj).__name__

    return {"type": "json", "shape": top_shape(data)}


def profile_text(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            json.loads(stripped)
            return profile_json(path) | {"type": "json(.txt)"}
        except json.JSONDecodeError:
            pass
    lines = [l for l in text.splitlines() if l.strip()]
    pipe_lines = [l for l in lines if "|" in l]
    if len(pipe_lines) > len(lines) * 0.5:
        header_cols = [c.strip() for c in pipe_lines[0].split("|")]
        return {"type": "pipe_table(.txt)", "columns": header_cols, "rows": len(pipe_lines)}
    return {"type": "plain_text", "line_count": len(lines), "sample_line": lines[0] if lines else ""}


def profile_log(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [l for l in text.splitlines() if l.strip()]
    keys = Counter()
    event_values = Counter()
    for line in lines[:2000]:
        for k, v in KV_RE.findall(line):
            keys[k] += 1
            if k in ("event", "event_type", "action", "op"):
                event_values[v.strip('"')] += 1
    return {
        "type": "log(kv)", "line_count": len(lines),
        "top_keys": keys.most_common(15),
        "event_values": event_values.most_common(15),
    }


def profile_pdf(path: Path) -> dict:
    try:
        from pypdf import PdfReader
    except ImportError:
        return {"type": "pdf", "error": "pypdf not installed"}
    try:
        reader = PdfReader(str(path))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception as exc:  # noqa: BLE001
        return {"type": "pdf", "error": str(exc)}
    labels = re.findall(r"^([A-Za-z][A-Za-z _/-]{2,30}):", text, re.MULTILINE)
    return {"type": "pdf", "pages": len(reader.pages), "char_count": len(text), "field_labels": Counter(labels).most_common(20)}


def profile_png(path: Path) -> dict:
    return {"type": "png", "size_bytes": path.stat().st_size, "note": "requires vision LLM (image_parser.py, Card 5)"}


PROFILERS = {".sql": profile_sql, ".json": profile_json, ".txt": profile_text, ".log": profile_log, ".pdf": profile_pdf, ".png": profile_png}


def main() -> int:
    with open(EVIDENCE_FILES_CSV, newline="", encoding="utf-8") as f:
        manifest = list(csv.DictReader(f))

    type_counts = Counter()
    out_lines = []
    for row in manifest:
        file_id = row["file_id"]
        rel_path = row["file_path"]
        full_path = DATASET_DIR / rel_path
        ext = full_path.suffix.lower()
        profiler = PROFILERS.get(ext)
        if profiler is None or not full_path.exists():
            out_lines.append(f"{file_id} {rel_path}: SKIP (no profiler or missing file)")
            continue
        profile = profiler(full_path)
        type_counts[profile.get("type", ext)] += 1
        out_lines.append(f"=== {file_id} {rel_path} ===")
        out_lines.append(json.dumps(profile, ensure_ascii=False, indent=2, default=str))
        out_lines.append("")

    EVIDENCE_PROFILE_TXT.write_text("\n".join(out_lines), encoding="utf-8")

    print(f"Profiled {len(manifest)} evidence files -> {EVIDENCE_PROFILE_TXT}")
    for t, c in type_counts.most_common():
        print(f"  {t}: {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
