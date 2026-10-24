"""Regenerates code/evaluation/usage_report.md from build/llm_ledger.jsonl
(the append-only ledger code/llm.py writes one line per call to).

Run after the final full-dataset run: python tools/usage_report.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))
from config import LLM_LEDGER_JSONL, REPO_ROOT  # noqa: E402

# Gemini Flash list price (per docs, USD per 1M tokens) used only to produce
# an estimate; actual billing may differ by tier/region.
PRICE_PER_1M_INPUT_USD = 0.075
PRICE_PER_1M_OUTPUT_USD = 0.30

OUT_PATH = REPO_ROOT / "code" / "evaluation" / "usage_report.md"


def main() -> int:
    if not LLM_LEDGER_JSONL.exists():
        OUT_PATH.write_text(_zero_call_report(), encoding="utf-8")
        print(f"no ledger found -> wrote zero-call report to {OUT_PATH}")
        return 0

    entries = [json.loads(l) for l in LLM_LEDGER_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]

    by_model = defaultdict(lambda: {"calls": 0, "cached": 0, "input_tokens": 0, "output_tokens": 0})
    for e in entries:
        m = by_model[e["model"]]
        m["calls"] += 1
        m["cached"] += int(e.get("cached", False))
        m["input_tokens"] += e.get("input_tokens", 0)
        m["output_tokens"] += e.get("output_tokens", 0)

    total_calls = sum(m["calls"] for m in by_model.values())
    total_cached = sum(m["cached"] for m in by_model.values())
    total_input = sum(m["input_tokens"] for m in by_model.values())
    total_output = sum(m["output_tokens"] for m in by_model.values())
    total_tokens = total_input + total_output
    total_cost = (total_input / 1e6) * PRICE_PER_1M_INPUT_USD + (total_output / 1e6) * PRICE_PER_1M_OUTPUT_USD

    lines = [
        "# Usage Report — final full-dataset run that produced `output.csv`",
        "",
        f"Provider: Google Gemini. {total_calls} total calls ({total_cached} served from the disk "
        f"cache at build/llm_cache/ with 0 marginal tokens), {total_input} input tokens, "
        f"{total_output} output tokens, {total_tokens} total tokens.",
        "",
        "| Model | Calls | Cached | Input tokens | Output tokens | Total tokens | Est. cost (USD, list price) |",
        "|---|---|---|---|---|---|---|",
    ]
    for model, m in by_model.items():
        cost = (m["input_tokens"] / 1e6) * PRICE_PER_1M_INPUT_USD + (m["output_tokens"] / 1e6) * PRICE_PER_1M_OUTPUT_USD
        lines.append(
            f"| {model} | {m['calls']} | {m['cached']} | {m['input_tokens']} | {m['output_tokens']} | "
            f"{m['input_tokens'] + m['output_tokens']} | ${cost:.6f} |"
        )
    lines.append(f"| **Overall** | **{total_calls}** | **{total_cached}** | **{total_input}** | **{total_output}** | **{total_tokens}** | **${total_cost:.6f}** |")

    n_requests = 518  # full dataset
    lines += [
        "",
        f"Average per request (of {n_requests} full-dataset requests): "
        f"{total_tokens / n_requests:.1f} tokens, ${total_cost / n_requests:.8f}.",
        "",
        "## What each call is for",
        "",
        "- **Intent classification** (`code/intent.py`): one batch call per 25 distinct "
        "`request_text` strings, across both `sample_deletion_requests.csv` and "
        "`deletion_requests.csv` combined. Cached per batch by prompt hash, so a "
        "re-run of the same split makes 0 new calls.",
        "- **Screenshot parsing** (`code/ingest/image_parser.py`): one call per PNG "
        "evidence file (11 total), cached by (prompt + image hash).",
        "",
        "Price basis: Gemini Flash list pricing "
        f"(${PRICE_PER_1M_INPUT_USD}/1M input tokens, ${PRICE_PER_1M_OUTPUT_USD}/1M output "
        "tokens) as of this session; actual cost may differ by plan/region. "
        "`output_tokens` includes the model's internal reasoning (\"thoughts\") tokens, "
        "which this model bills as output.",
    ]

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT_PATH} ({total_calls} calls, {total_tokens} tokens, ${total_cost:.6f})")
    return 0


def _zero_call_report() -> str:
    return (
        "# Usage Report — final full-dataset run that produced `output.csv`\n\n"
        "## Summary: zero LLM calls in this run\n\n"
        "No build/llm_ledger.jsonl exists, confirming zero calls were made "
        "(GEMINI_API_KEY not configured, or code/ingest/build.py and "
        "code/main.py were not run with it set).\n\n"
        "| Model provider | Model | Calls | Input tokens | Output tokens | Total tokens | Cost |\n"
        "|---|---|---|---|---|---|---|\n"
        "| — | — | 0 | 0 | 0 | 0 | $0.00 |\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
