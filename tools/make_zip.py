"""Builds submission/code.zip: code/, evaluation reports (nested under
code/), tools/ (including the viz), docs/, root README.md, requirements.txt,
.env.example. Excludes .venv, .env, build/, __pycache__, dataset/, output.csv,
and any nested archive. Also runs a basic secret scan over the zip contents.

Run: python tools/make_zip.py
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_ZIP = REPO_ROOT / "submission" / "code.zip"

INCLUDE_DIRS = ["code", "tools", "docs"]
INCLUDE_FILES = ["README.md", "requirements.txt", ".env.example"]

EXCLUDE_DIR_NAMES = {".venv", "venv", "__pycache__", "dataset", ".git", "submission"}
EXCLUDE_SUFFIXES = {".zip", ".tar", ".gz", ".tgz", ".7z", ".rar"}
EXCLUDE_EXACT_NAMES = {".env"}

SECRET_RE = re.compile(r"AIza[0-9A-Za-z_\-]{20,}|\b[A-Za-z0-9_]{35,}\b")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def should_skip(path: Path) -> bool:
    if path.name in EXCLUDE_EXACT_NAMES:
        return True
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return True
    for part in path.parts:
        if part in EXCLUDE_DIR_NAMES:
            return True
    return False


def iter_files() -> list[Path]:
    files = []
    for rel in INCLUDE_DIRS:
        base = REPO_ROOT / rel
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file() and not should_skip(p.relative_to(REPO_ROOT)):
                files.append(p)
    for rel in INCLUDE_FILES:
        p = REPO_ROOT / rel
        if p.exists():
            files.append(p)
    return files


def secret_scan(files: list[Path]) -> list[str]:
    hits = []
    text_suffixes = {".py", ".md", ".txt", ".json", ".html", ".csv", ".example", ""}
    for p in files:
        if p.suffix.lower() not in text_suffixes and p.name != ".env.example":
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in SECRET_RE.finditer(text):
            token = m.group(0)
            if UUID_RE.match(token):
                continue  # a UUID (session id, file id, etc.), not a secret
            if "GEMINI_API_KEY=" in text[max(0, m.start() - 20):m.start()] and p.name == ".env.example":
                continue  # the placeholder line in .env.example itself
            hits.append(f"{p.relative_to(REPO_ROOT)}: {token[:12]}...")
    return hits


def main() -> int:
    files = iter_files()
    if not files:
        print("ERROR: no files matched -- check INCLUDE_DIRS/INCLUDE_FILES", file=sys.stderr)
        return 1

    hits = secret_scan(files)
    if hits:
        print("SECRET SCAN FAILED -- possible secrets found, zip NOT written:", file=sys.stderr)
        for h in hits:
            print(f"  {h}", file=sys.stderr)
        return 1

    OUT_ZIP.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, arcname=str(p.relative_to(REPO_ROOT)))

    print(f"wrote {OUT_ZIP} ({len(files)} files, secret scan clean)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
