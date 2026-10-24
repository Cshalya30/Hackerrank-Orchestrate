# Ghost Data Audit — README

A deletion-audit pipeline for HackerRank Orchestrate "Ghost Data Still
Exists": for each of 518 data-deletion requests, decide
COMPLETE / INCOMPLETE / NOT_APPLICABLE and output an ordered
FINDING -> REMEDIATION -> VERIFICATION step list with evidence citations.

## Setup

```bash
cd code/..          # repo root
python -m venv .venv
.venv/Scripts/activate        # Windows; use .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env          # add GEMINI_API_KEY (optional, see below)
```

## Run

```bash
python code/ingest/build.py                                    # -> build/observations.jsonl, build/coverage.txt
python code/main.py --split sample --out build/sample_output_pred.csv
python code/evaluation/main.py --pred build/sample_output_pred.csv --gold dataset/sample_output.csv
python code/main.py --split full --out output.csv
python code/validate.py output.csv --expect-rows 518 --case-ids dataset/deletion_requests.csv
python code/evaluation/custom_cases/test_custom_cases.py
```

`GEMINI_API_KEY` is optional: without it, `code/intent.py` falls back to a
deterministic multilingual-keyword classifier (functionally similar, but
won't generalize to unseen phrasing). With it, intent classification runs on
Gemini Flash-Lite (thinking off), batched and disk-cached.

## Architecture

```
Deletion Requests (CSV)
        |
   Intent (LLM)         code/intent.py            — DELETE_REQUEST / DELETION_VERIFICATION / OTHER_SERVICE
        |
  Identity Resolution    code/resolve.py           — email -> user_id -> full historical identifier set
        |
  Evidence Ingest        code/ingest/build.py      — 94-file corpus -> build/observations.jsonl (once, deterministic)
        |
  Point-in-time State    code/resolve.py           — latest observation at/before audit_at, per resource
        |
  Policy / Account Rules code/account_linker.py    — account_service resolution priority chain
        |
  Planner                code/planner.py           — FINDING -> REMEDIATION -> VERIFICATION step list + status
        |
  Validator               code/validate.py          — contract checks on output.csv
        |
  output.csv
```

Open `tools/viz/index.html` (see below) for an interactive version of this
diagram with per-case traces.

## Where the LLM is used, and why

Gemini Flash-Lite (`gemini-flash-lite-latest`, thinking off) is used for
exactly one thing: **intent classification** (`code/intent.py`), batched 25
distinct `request_text` strings per call, disk-cached by prompt hash. This is
the one genuinely open-ended, multilingual natural-language task in the
pipeline (the request text appears in at least 6 languages and includes
subtle "verify my deletion" follow-ups that a keyword list can't generalize
to). Everything else — identity resolution, evidence parsing, state
reconstruction, policy application, step ordering — is deterministic Python,
by design: AGENTS.md requires deterministic behavior where possible, and a
judge re-running these exact commands should get the exact same `output.csv`
every time.

A second LLM use, screenshot (PNG evidence) parsing via Gemini vision
(`code/ingest/image_parser.py`), was built and works, but is **not** part of
the committed pipeline: two separate attempts to merge its output moved
sample F1 in opposite directions on different runs, and tracing it down
showed the vision model's per-call row extraction is not fully deterministic
for the same cached image. Given that AGENTS.md's determinism requirement,
it was left out rather than shipped as a coin flip — see
`docs/DECISIONS.md` D8/D9/D10 for the full trace.

## Evaluation and reports

- `code/evaluation/evaluation_report.md` — status/step/field/sequence
  accuracy, the fix history, and known gaps.
- `code/evaluation/usage_report.md` — LLM calls, tokens, and estimated cost.
- `code/evaluation/custom_cases/test_custom_cases.py` — 3 synthetic cases,
  run directly (no pytest needed).
- `docs/EVAL_LOG.md` — every eval run, kept or reverted, with scores.
- `docs/DECISIONS.md` — the reasoning behind every kept/reverted change.

## Pipeline visualizer

```bash
python -m http.server 8765 -d tools/viz
# open http://localhost:8765
```

A single self-contained page (no build step, no external requests): a
left-to-right flow diagram of the 9 pipeline stages (click a node for its
file/function, counts, and — for the intent node — LLM usage), and a
searchable case explorer that renders any case's resolved identity, account
rule, resources, and step timeline. Regenerate `tools/viz/pipeline.json`
after any pipeline change with:

```bash
python tools/viz/export_stats.py
```
