# Validation results, 2026-11-03

## Repository follow-up, 2026-11-04

The complete regression suite passes **108 tests** (92 before this follow-up), and scoped
`git diff --check` passes. New behavioral tests reproduced the amendment/pin loss, unrelated
review invalidation, discarded current checks, unavailable individual cancellation, oversized
packet retrieval and cross-component context reuse before their corresponding changes.

Coverage now includes retained repair evidence through reopening/amendment, running-repair
continuation after approved adoption, explicit archived test supersession with mandatory
replacement verification, pin protection across tasks, scoped review dependencies including
ignored literal files and newly created sources, safe check reuse, worker cancellation races,
fresh/continued reviewer identity rules and complete read-only packet pagination.

The new `recovery-cycle` evaluation is covered by scripted helper execution through three
test-first repairs, a real saved halt/resume, evaluator-owned concurrent edit, approved scope
amendment and independently graded completion. Its grader rejects lost archived checkpoints.
This is **scripted regression coverage**, not a new actual-agent performance evaluation.

Read-only reconstruction of the historical November 3 run's T04 context produces a 14,057-byte
packet (previously 18,879), within the default 16,000-byte limit; details are explicitly paged,
and complete task/constraints remain in context. No historical workflow was advanced or edited.
No production speedup or token-cost reduction is claimed. All changes are confined to this
repository's `co-task-pipeline`; no deployed skill or other agent's files were changed.

## Earlier actual-agent validation

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
