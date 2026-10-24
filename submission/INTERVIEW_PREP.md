# Interview Prep — Ghost Data Audit

Real numbers only, pulled from `code/evaluation/evaluation_report.md` and
`code/evaluation/usage_report.md` at final-run time.

## 60-second pitch

"Ghost Data Still Exists" asks for a deletion-audit agent over 518 requests
and a 94-file multi-system evidence corpus. I built it evidence-first: parse
the entire shared corpus once into a flat observation log, resolve each
user's full identity footprint (current and historical emails, hashes,
phones), reconstruct what each resource's state actually was at the
audit timestamp — file evidence outranks activity claims, which are just
claims — then apply the 15 deletion rules deterministically to produce an
ordered finding/remediation/verification plan. The only LLM call in the
whole pipeline is request-intent classification, because that's the one
genuinely open-ended, multilingual task; everything else is deterministic
Python so a judge re-running my exact commands gets my exact output every
time. Final sample scores: 0.812 status accuracy, 0.706 step F1.

## Architecture walkthrough (6 bullets, file::function)

1. `code/intent.py::classify_case` — LLM (Gemini Flash-Lite, thinking off,
   batched/cached) labels each request DELETE_REQUEST / DELETION_VERIFICATION
   / OTHER_SERVICE; only OTHER_SERVICE short-circuits to NOT_APPLICABLE.
2. `code/resolve.py::IdentityIndex.resolve_user` — maps the request's email
   to a user_id and the complete historical identifier set via
   `user_identities.csv` + `user_audit_log.csv`.
3. `code/ingest/build.py::main` — parses all 94 evidence files (SQL, JSON,
   logs, `system_activity.csv` claims) once into `build/observations.jsonl`;
   this never runs per-case, it's a shared corpus-wide pass.
4. `code/resolve.py::latest_state_per_resource` — for every resource linked
   to the user, takes the latest observation at or before `audit_at`; file
   evidence beats activity claims, PRESENT beats ABSENT on an exact tie.
5. `code/account_linker.py::AccountLinker.account_for` — resolves the
   account_service id every case needs via a priority chain (direct link ->
   catalog link -> same-day batch order -> zero-padded fallback), never
   guessing.
6. `code/planner.py::build_steps / finalize` — turns resolved states into
   the ordered FINDING -> REMEDIATION -> VERIFICATION list and the case's
   final status.

## One answer each

**Architecture.** Evidence-first and mostly deterministic by design: the
corpus is parsed once, shared across all 518 cases, and per-case logic is
pure lookups and rule application — the only non-determinism is scoped to
one LLM call for intent, which I chose deliberately over an LLM-per-case
"let the model figure it out" approach because I needed to defend every
output as rule-derived, not model-vibes-derived.

**Safety/failure modes.** Untrusted-data discipline throughout: evidence
file contents and screenshot text are explicitly prompted as DATA ONLY,
never instructions, and every LLM-returned resource_id is regex-validated
before being trusted. The biggest actual failure mode I hit was quieter:
a planner bug that silently collapsed "zero resources found" into
NOT_APPLICABLE, which looks like correct behavior until you check it against
a gold set with zero NOT_APPLICABLE cases.

**Code familiarity.** I can walk any case through the pipeline live via
`tools/viz/index.html` — click a case, see its resolved identity, which
account-linking rule fired, every resource's state and evidence citation,
and the final step timeline with phase chips.

**Evaluation.** Status/step/field/sequence accuracy against the 32 public
samples, logged in `docs/EVAL_LOG.md` for every single attempt — including
ones I reverted — so the history of what helped and what didn't is
auditable, not just the final number.

**Production monitoring.** The token ledger (`build/llm_ledger.jsonl`) is
the pattern I'd extend: every LLM call logged with cache status and token
counts. In production I'd add the same structured logging around every
deterministic stage's input/output counts (which `tools/viz/export_stats.py`
already surfaces for the pipeline as a whole) plus alerting on coverage
regressions — if the % of resolved (system_id, resource_id) pairs drops
between runs, something upstream changed.

**Novelty.** The "resource continuity" rule: once any observation links a
resource to a user by PII, every later observation of that same resource
stays linked even after the PII is anonymized/redacted — otherwise a
successfully-anonymized analytics record would look unlinked and get
silently skipped instead of verified. Found this by tracing a gold case
where the only surviving link was the user's *old* email hash sitting in a
log's correlation_key field.

## Failure stories (what actually broke and how it got fixed)

1. **Wrong cwd + log recovery.** A session ran from the wrong repository
   entirely for part of RUN2, so none of that work got logged live. Built
   `tools/recover_log.py` to extract the missed entries from Claude Code's
   own session transcript and append them to `log.txt` with original
   timestamps, marked `recovered=true`.
2. **Parallel-session race.** That same misplaced session never actually
   stopped — it kept running and committing in the background while a new
   session worked on the same repo. Caught it (stray background processes,
   files changing without my edits), paused, had the owner confirm and stop
   it, then verified every one of its claims against the current code
   before keeping any of it.
3. **LLM intent mislabel -> 3-label fix.** The first intent classifier was
   binary (DELETION/NON_DELETION) and misread "please verify my deletion
   completed" follow-ups. Fixed by adding a third label,
   DELETION_VERIFICATION, that still routes through the full audit pipeline
   instead of being treated as a non-deletion request.
4. **404 parser bug.** `service_resource_export` rows carry a `status_code`
   field (404 = the record is gone) that the first ingest pass never
   checked, so absent accounts looked present. One of several silent
   parser bugs found by tracing gold cases step by step rather than trusting
   aggregate scores alone.
5. **Reverted image merge (D7/D8/D9/D10).** Screenshot (vision-LLM) parsing
   works and is fully built, but two separate attempts to merge its output
   moved the sample score in opposite directions on different runs. Traced
   it to the vision model returning a different row count for the same
   cached image across separate calls. Reverted both times in favor of a
   reproducible pipeline — happy to explain the full trace if asked, it's
   a good example of "a number going up once isn't evidence."

## Honest limitations

- Screenshot/PDF-adjacent coverage gaps remain: 157 full-run cases have no
  resolvable account_service id, and a handful of accounts/audit records
  have zero evidence anywhere in the corpus.
- The deterministic intent fallback (used when no `GEMINI_API_KEY` is set)
  only catches non-deletion phrasing it's been explicitly shown.
- SUPPORT_ATTACHMENT vs. SUPPORT_MESSAGE disambiguation only has two
  PDF-backed special cases wired in, not a general solution.
- Sequence accuracy (0.156) is the real stress-test metric — most misses
  are a case with the right status and most steps right, failing exact-match
  on one or two resources.

## 10 hard questions, 2-3 sentence answers

1. **Why not an LLM-per-case agent instead of deterministic rules?**
   Defensibility and reproducibility — a judge re-running my commands should
   get my exact `output.csv`, and I need to be able to point at the rule
   that produced each step, not a model's reasoning trace.

2. **How do you know your account-resolution rule isn't just guessing?**
   It's a strict priority chain (direct evidence link -> catalog link ->
   same-day batch order -> zero-padded fallback) and every case's resolution
   is traced to `build/traces/<case_id>.json`, so I can show exactly which
   rule fired for any case.

3. **What happens if two files disagree about a resource's state?**
   Point-in-time rule: the latest observation at or before `audit_at` wins;
   file evidence outranks activity claims; an exact-timestamp tie favors
   PRESENT (replica drift, the safer assumption).

4. **Why did the image-parsing merge get reverted twice?**
   Because its effect on the score wasn't reproducible — the vision model
   extracted a different number of rows from the same cached image on
   different runs, so I couldn't trust whether a score change came from the
   data or from LLM noise.

5. **How do you prevent prompt injection from the evidence corpus?**
   Every LLM prompt that touches corpus content (screenshot text, request
   text) explicitly instructs the model to treat it as data only, and every
   structured field it returns (resource_id especially) is regex-validated
   before being trusted, not executed or interpreted as instructions.

6. **What's your test coverage story?**
   Three custom synthetic cases isolating specific mechanisms (NOT_APPLICABLE
   despite deletion-adjacent wording, historical-identifier matching, and
   resurrection-after-deletion), plus the 32-case public sample eval, plus
   `validate.py`'s structural contract checks on every full run.

7. **How would this scale to 10x the evidence volume?**
   The ingest pass is already a single linear scan producing a flat
   observation log, so it scales roughly linearly; the per-case resolution
   is a dict lookup, not a corpus re-scan, so the main cost growth would be
   ingest time and LLM batch count, both of which are already batched/cached.

8. **What would you add with more time?**
   Determinism-check the screenshot parser (repeat calls, diff output)
   before re-attempting the merge, and build a general SUPPORT_ATTACHMENT
   vs. SUPPORT_MESSAGE classifier instead of the two hardcoded PDF cases.

9. **How did you catch the parallel-session race?**
   Files I hadn't touched kept changing between my own edits, and a process
   list check showed two `image_parser.py` processes still running from an
   old session — I stopped, verified rather than assumed, and only kept
   what reproduced under the current code.

10. **Why is step F1 (0.706) lower than step precision (0.807) alone would
    suggest?**
    Recall is the gap — some true steps are missed because the underlying
    resource was never linked to the user by any parsed evidence (the
    coverage gap), not because the planner reasoned incorrectly about
    resources it did resolve.

## 90-second visualizer demo script

1. "This is the same pipeline from the README, but you can watch a case
   move through it." Open `tools/viz/index.html` (`python -m http.server
   8765 -d tools/viz`).
2. Point at the stat marquee: "These are the real numbers from my last
   validated run — status accuracy, step F1, sequence accuracy, the status
   distribution across all 518 cases, and total LLM cost."
3. Click the Intent node in the canvas: "This is the only LLM call in the
   whole system — here's what it's for, and its exact token/cost usage."
4. Click through Evidence Ingest -> Point-in-time State -> Policy -> Planner:
   "Everything after intent is deterministic Python — same input, same
   output, every time."
5. Pick a case and hit **Trace case**: "Here's one case end to end — which
   user it resolved to, which rule found their account, every
   resource with its state and evidence citation, and the final step
   timeline in the drawer."
6. Close with: "Every one of these came from a real file in `build/`, there's
   nothing hand-written in this view."
