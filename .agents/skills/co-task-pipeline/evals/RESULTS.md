# Validation results, 2026-11-03

All six follow-up improvements are implemented in this skill. This follows the initial
61-test Hidlins audit revision; the complete suite now passes **92 tests**.

```bash
python3 -B -m unittest discover -s .agents/skills/co-task-pipeline/tests -q
git diff --check -- .agents/skills/co-task-pipeline
```

The suite covers original contract gates plus scoped input/environment freshness, separate
repair checkpoints, halt/cancellation, caller-loss recovery without reexecution, unknown
effect reconciliation, three-child limits and model decisions, compact read-only packets,
automatic phase measurements, and evaluation grading/comparison failures.

Five actual-agent scenario types passed independent grading:

| Scenario | Observed result |
| --- | --- |
| Clean review | Correct source/tests unchanged; no invented defects; scoped check reused. |
| Incremental repairs | Three defects fixed sequentially in one task; separate genuine red/green evidence; retained regressions catch seeded mutants. |
| Research mapping | Requested call-path map correct; source and operator notes preserved. |
| Unavailable tool | Required command actually failed; evidence preserved and workflow blocked without false completion. |
| Halt/resume | Agent stopped after the failing test checkpoint; a separate real resume instruction completed the same task with its original pin. |

The final multi-repair run used a fresh context and a frozen copy whose contents and
permissions match the current skill runtime exactly. Explicit activity commands were
prohibited: helper boundaries automatically measured research, implementation, verification,
bookkeeping and waiting spans. It closed three repairs with six actual check executions and
one reused check. These are small-fixture observations, not a production speedup claim.

The main thread requested **TERRA / medium** for these bounded scenarios. Actual served
model/effort was not reported by the host and remains unreported. A SOL / high child built
the evaluation harness; observed host capacity permitted one child at a time. The skill's
standing ceiling is three, with core-thread SOL/TERRA selection per assignment and lower
runtime/operator limits honored.

One initial unavailable-tool prompt accidentally retained an unrelated unit-check instruction.
Actual execution exposed the contradiction; the fixture was corrected and rerun. The retained
result is for that corrected scenario. Scripted harness tests are never labeled actual-agent
runs. The comparison command was also exercised on two quality-passing multi-repair runs;
the small sample and unreported actual model settings do not establish comparative speed/cost.

Measured helper/check totals, phase spans, frozen revisions and actual agent identities are
saved in [results-2026-11-03.json](results-2026-11-03.json). Full model token totals and total
host tool-call counts were unavailable and remain unmeasured. Phase/helper/check durations
overlap; do not add them as exclusive costs. The harness and reproducible run instructions
are in [README.md](README.md).
