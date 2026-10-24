# Usage Report — final full-dataset run that produced `output.csv`

Provider: Google Gemini. 17 total calls (0 served from the disk cache at build/llm_cache/ with 0 marginal tokens), 32236 input tokens, 11959 output tokens, 44195 total tokens.

| Model | Calls | Cached | Input tokens | Output tokens | Total tokens | Est. cost (USD, list price) |
|---|---|---|---|---|---|---|
| gemini-flash-lite-latest | 17 | 0 | 32236 | 11959 | 44195 | $0.006005 |
| **Overall** | **17** | **0** | **32236** | **11959** | **44195** | **$0.006005** |

Average per request (of 518 full-dataset requests): 85.3 tokens, $0.00001159.

## What each call is for

- **Intent classification** (`code/intent.py`): one batch call per 25 distinct `request_text` strings, across both `sample_deletion_requests.csv` and `deletion_requests.csv` combined (2 batches for the 32 sample texts + 15 batches for the 375 full-dataset distinct texts = 17 calls). Cached per batch by prompt hash, so a re-run of the same split makes 0 new calls.
- **Screenshot parsing** (`code/ingest/image_parser.py`): one call per PNG evidence file (11 total), cached by (prompt + image hash). Run this session as an experiment; its output was NOT merged into the committed pipeline because it dropped sample step F1 (see docs/DECISIONS.md D8) -- those 11 calls were real spend/usage even though the result wasn't kept, and are excluded from the table above (see the note below).

Price basis: approximate Gemini Flash-Lite list pricing ($0.075/1M input tokens, $0.3/1M output tokens), not re-verified against current published pricing this session; actual cost may differ by plan/region. `output_tokens` includes any model internal reasoning ("thoughts") tokens, which this model bills as output (thinking is off for this model/config, so this should normally be 0).

## Note on scope and a live data-integrity issue

This table is a frozen snapshot of the clean, final-sequence usage (sample-split
gate + full run, regenerated once in sequence against a cleared
`build/llm_ledger.jsonl`): 2 intent batches for the 32 sample cases + 15 for
the 375 distinct full-dataset request texts, 17 calls total.

Two things are **not** in this table, and a third is an open problem the
owner needs to act on:

1. A separate `code/ingest/image_parser.py` run (11 calls, all on
   `gemini-flash-lite-latest`) was tried and reverted for a sample-F1
   regression -- see docs/DECISIONS.md D8.
2. Stray `gemini-flash-latest` ledger entries from an orphaned process left
   over from the earlier misplaced-cwd session (started before this
   session's model switch) were filtered out before generating this report.
3. **Still unresolved: `build/llm_ledger.jsonl` kept growing with new
   `cached: true` entries after this report was generated**, with PIDs 1844
   and 6104 (`.venv/Scripts/python.exe code/ingest/image_parser.py`,
   Windows) confirmed still running via `Get-Process`/`Get-CimInstance`.
   This session does not have permission to terminate processes. **The
   owner should kill PIDs 1844 and 6104 manually** (Task Manager, or
   `Stop-Process -Id 1844,6104 -Force` in PowerShell) before trusting any
   further regeneration of this report or the ledger file.
