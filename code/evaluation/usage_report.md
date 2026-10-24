# Usage Report — final full-dataset run that produced `output.csv`

## Summary: zero LLM calls in this run

`GEMINI_API_KEY` is **not configured** in this session (no `.env` file has been
created — only `.env.example` is committed, per the `.env`-is-gitignored rule
in `AGENTS.md` section 4.4). `code/llm.py` raises `LLMUnavailable` whenever a
caller tries to use it without a key; both call sites that are designed to use
an LLM degrade to a deterministic path instead:

- **`code/intent.py`** (request-intent classification): uses its keyword-based
  deterministic fallback, as explicitly authorized in `docs/SPEC.md` section 6
  step 6 for exactly this situation.
- **`code/ingest/build.py`** image parsing (the 11 PNG screenshots): not yet
  implemented at all (see `docs/GAPS.md`) — these files are simply skipped and
  counted in the ingest summary (`skipped: png=11`), contributing zero
  observations rather than a fabricated one.

| Model provider | Model | Calls | Input tokens | Output tokens | Total tokens | Cost |
|---|---|---|---|---|---|---|
| — | — | 0 | 0 | 0 | 0 | $0.00 |

Per-request average: 0 tokens, $0.00 (0 calls / 518 requests).

`build/llm_ledger.jsonl` (the file `code/llm.py` appends one line to per call,
read by this report) does not exist after this run, confirming zero calls —
not an omission.

## What changes once `GEMINI_API_KEY` is supplied

1. `code/intent.py` would batch the 375 distinct `request_text` strings (25 per
   batch, per `docs/SPEC.md` section 5) through Gemini Flash instead of the
   keyword fallback, with disk caching in `build/llm_cache/` so a re-run never
   re-pays for an already-classified text.
2. An `ingest/image_parser.py` (not yet written) would turn the 11 screenshots
   into observations through a vision call, also cached.
3. This report would then be regenerated from the real `build/llm_ledger.jsonl`
   with actual per-model token and cost totals — the table above is the
   accurate zero-call baseline, not a placeholder to be hand-edited later.
