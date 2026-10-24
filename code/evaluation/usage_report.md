# Usage Report — final full-dataset run that produced `output.csv`

Provider: Google Gemini. 17 total calls (0 served from the disk cache at build/llm_cache/ with 0 marginal tokens), 32236 input tokens, 11844 output tokens, 44080 total tokens.

| Model | Calls | Cached | Input tokens | Output tokens | Total tokens | Est. cost (USD, list price) |
|---|---|---|---|---|---|---|
| gemini-flash-lite-latest | 17 | 0 | 32236 | 11844 | 44080 | $0.005971 |
| **Overall** | **17** | **0** | **32236** | **11844** | **44080** | **$0.005971** |

Average per request (of 518 full-dataset requests): 85.1 tokens, $0.00001153.

## What each call is for

- **Intent classification** (`code/intent.py`): one batch call per 25 distinct `request_text` strings, across both `sample_deletion_requests.csv` and `deletion_requests.csv` combined. Cached per batch by prompt hash, so a re-run of the same split makes 0 new calls.
- **Screenshot parsing** (`code/ingest/image_parser.py`): one call per PNG evidence file (11 total), cached by (prompt + image hash). Tried twice this session as an experiment (once merging all 11, once a 9/11 subset); neither was kept in the committed pipeline because its effect on sample F1 was not reproducible across runs -- see `docs/DECISIONS.md` D8/D9/D10. Those calls were real spend/usage but are excluded from the table above.

Price basis: approximate Gemini Flash-Lite list pricing ($0.075/1M input tokens, $0.3/1M output tokens), not re-verified against current published pricing this session; actual cost may differ by plan/region. `output_tokens` includes any model internal reasoning ("thoughts") tokens, which this model bills as output (thinking is off for this model/config, so this should normally be 0).

## Note on scope

This table is a frozen snapshot of the clean, final-sequence usage (sample-split
gate + full run, regenerated once in sequence against a cleared
`build/llm_ledger.jsonl`): 2 intent batches for the 32 sample cases + 15 for
the 375 distinct full-dataset request texts, 17 calls total -- the complete
and final LLM usage for the committed pipeline (image parsing is not part of
the committed pipeline; see above).