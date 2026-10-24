# EVAL_LOG.md

One line per eval run against `dataset/sample_output.csv` (32 cases). Format:

`time | change | status_accuracy | step_F1 | sequence_accuracy`

| time | change | status accuracy | step F1 | sequence accuracy |
|---|---|---|---|---|
| 2026-10-24T20:52+05:30 | sample_output.csv vs itself (sanity check of eval.py) | 1.000 | 1.000 | 1.000 |
| 2026-10-24T21:40+05:30 | first Card 4 run: identity+state+policy+planner, no fixes | 0.531 | 0.529 | 0.062 |
| 2026-10-24T21:48+05:30 | fix: finalize() no longer infers NOT_APPLICABLE from empty steps (was mislabeling 6 genuine DELETION cases with unresolved evidence) | 0.750 | 0.529 | 0.062 |
