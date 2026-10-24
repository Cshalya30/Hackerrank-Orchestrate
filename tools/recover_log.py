"""Recover log.txt entries missed during Run 2 (session ran from the wrong cwd).

Reads the Claude Code session .jsonl for the misplaced session, extracts each
user prompt (verbatim, secrets redacted) and, per assistant turn, the tool
actions taken plus a short summary, and prints AGENTS.md section-5.2-shaped
entries to stdout (nothing is written to log.txt by this script -- the
caller reviews and appends). Only counts are printed to the console during
extraction, never raw content, per the owner's instruction.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SESSION_FILE = Path(
    r"C:\Users\Chirantan\.claude\projects\D--Users-Chirantan-Documents-Competitions---5th-Sem-EY---Cafta-CaseComp-2026-gcpl-treasury-command\419feeed-535a-42e8-9038-2a4fb4a0960d.jsonl"
)

# Only recover the window after the last genuinely-logged Run 1 entry
# (log.txt's "step 8" entry is timestamped 2026-10-24T22:25:00+05:30 ==
# 2026-10-24T16:55:00Z) through end of session.
WINDOW_START_UTC = "2026-10-24T16:55:00"

SECRET_PATTERNS = [
    re.compile(r"(GEMINI_API_KEY\s*=\s*)\S+", re.IGNORECASE),
    re.compile(r"(AIza[0-9A-Za-z_\-]{20,})"),
]


def redact(text: str) -> str:
    out = text
    for pat in SECRET_PATTERNS:
        out = pat.sub(lambda m: m.group(1) + "[REDACTED]" if m.lastindex else "[REDACTED]", out)
    return out


def load_entries(path: Path) -> list[dict]:
    entries = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def text_of_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""


def tool_calls_of(content) -> list[tuple[str, dict]]:
    calls = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                calls.append((block.get("name", "?"), block.get("input", {})))
    return calls


def summarize_tool_call(name: str, inp: dict) -> str:
    if name in ("Edit", "Write"):
        return f"{name} {inp.get('file_path', '?')}"
    if name == "Bash":
        cmd = inp.get("command", "")
        return f"Bash: {cmd[:120]}"
    if name == "Read":
        return f"Read {inp.get('file_path', '?')}"
    if name == "Glob":
        return f"Glob {inp.get('pattern', '?')}"
    if name == "Grep":
        return f"Grep {inp.get('pattern', '?')}"
    return name


def main() -> None:
    if not SESSION_FILE.exists():
        print(f"ERROR: session file not found: {SESSION_FILE}", file=sys.stderr)
        sys.exit(1)

    entries = load_entries(SESSION_FILE)
    print(f"loaded {len(entries)} raw session lines")

    turns: list[dict] = []
    current_user_text: str | None = None
    current_user_ts: str | None = None
    pending_actions: list[str] = []
    pending_summary_fragments: list[str] = []

    def flush_turn(end_ts: str | None):
        nonlocal current_user_text, current_user_ts, pending_actions, pending_summary_fragments
        if current_user_text is not None:
            turns.append(
                {
                    "ts": current_user_ts,
                    "user_text": current_user_text,
                    "actions": list(pending_actions),
                    "summary_fragments": list(pending_summary_fragments),
                }
            )
        current_user_text = None
        current_user_ts = None
        pending_actions = []
        pending_summary_fragments = []

    for e in entries:
        ts = e.get("timestamp", "")
        if ts and ts < WINDOW_START_UTC:
            continue
        etype = e.get("type")
        msg = e.get("message", {})
        role = msg.get("role")

        if etype == "user" and role == "user":
            content = msg.get("content")
            text = text_of_content(content)
            if text.strip():
                flush_turn(ts)
                current_user_text = redact(text.strip())
                current_user_ts = ts
        elif etype == "assistant" and role == "assistant":
            content = msg.get("content")
            text = text_of_content(content)
            if text.strip():
                pending_summary_fragments.append(text.strip())
            for name, inp in tool_calls_of(content):
                pending_actions.append(summarize_tool_call(name, inp))

    flush_turn(None)

    print(f"recovered {len(turns)} user-turn windows in range [{WINDOW_START_UTC}Z, end]")
    total_actions = sum(len(t["actions"]) for t in turns)
    print(f"total tool actions captured: {total_actions}")

    out_path = Path(__file__).resolve().parent.parent / "build" / "recovered_log_entries.txt"
    out_path.parent.mkdir(exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for t in turns:
            ts_local = t["ts"] or "unknown"
            title = (t["user_text"][:70] + "...") if len(t["user_text"]) > 70 else t["user_text"]
            title = title.replace("\n", " ")
            f.write(f"## [{ts_local}] {title}\n\n")
            f.write("User Prompt (verbatim, secrets redacted):\n")
            f.write(t["user_text"] + "\n\n")
            f.write("Agent Response Summary:\n")
            summary = " ".join(t["summary_fragments"])[:800] or "(tool-only turn; see actions below)"
            f.write(summary + "\n\n")
            f.write("Actions:\n")
            if t["actions"]:
                for a in t["actions"]:
                    f.write(f"* {a}\n")
            else:
                f.write("* (none captured)\n")
            f.write("\nContext:\n")
            f.write("tool=Claude Code\n")
            f.write("model=claude-sonnet-5\n")
            f.write("branch=main\n")
            f.write(r"repo_root=D:\Users\Chirantan\Documents\Competitions - 5th Sem\Hackerrank orchestrate\project" + "\n")
            f.write("worktree=main\n")
            f.write("parent_agent=none\n")
            f.write("recovered=true\n\n")

    print(f"wrote reconstructed entries to {out_path}")


if __name__ == "__main__":
    main()
