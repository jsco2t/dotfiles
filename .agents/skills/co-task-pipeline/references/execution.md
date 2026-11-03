# Measured, incremental and recoverable execution

Read the sections relevant to the current operation. Use the bundled helper; `tp` here is
the absolute Python invocation defined in helper.md. These mechanisms support the approved
request; they do not authorize new outcomes or external side effects.

## Progress and overhead

```text
tp -w <workflow> activity begin research --label "Map component boundaries"
tp -w <workflow> activity end --evidence "research.md contains the bounded map"
tp -w <workflow> metrics
tp -w <workflow> usage --file <observed-usage.json>
```

Main-thread phase wall spans are automatic at existing scope/plan, task/repair, check,
decision and resume boundaries, without extra tool calls. Categories are research,
implementation, verification, bookkeeping and waiting. They measure time between declared
workflow boundaries, including idle time inside that phase, not CPU-active work. Only one main
span is active; delegated work is tracked separately. Use explicit begin/end to refine a
meaningful phase, not per tool call; begin can replace an automatic span. `block` switches to
waiting, scope/plan checks mark approval wait, and halt/final close the active span. Check
recovery closes its span at the worker's actual end time, so lost-parent gaps are not labeled
check execution. Covered/unclassified wall time is reported. Do not invent spans retroactively.

The helper automatically appends receipts for **mutating helper invocations**, including failed
ones, under `.tp/telemetry.jsonl`. Read-only status/show/packet/metrics preserve their read-only
contract and are not counted. Worker check durations and check-reuse events are automatic.
Agent assignment durations run from reservation to settlement and may include scheduling wait.
Question-to-answer/amend intervals separately give recorded operator wait; scope/plan waits
also appear in the main waiting spans. No CPU-active or complete tool-time inference is made.

`metrics` returns compact JSON. `final` also saves metrics.json alongside report.md. Task and
requirement counts reflect accepted saved state, not a fresh independent artifact audit.
Compare completed requested units and accepted quality against time/cost, not task/artifact count.
Main activity, helper, checks, agents and operator-wait durations can overlap: never add them
as though they were exclusive categories or claim a percentage from overlapping clocks.

`schema usage` shows an import with unique source ID and actual provenance. Measurements may
include input/cached-input/output tokens, tool calls and repeated reads. A cumulative update
replaces the same source ID, preventing double counting repeat imports. Ensure different
sources do not overlap (e.g. main totals already including children). Missing values remain
unmeasured; the helper does not estimate model usage or monetary cost. Retain requested and
runtime-reported model settings separately. Use actual host exports for full tool/context data.

## Incremental repair steps

Keep one top-level task per delivered unit/cycle. With an approved `adaptive: true` task,
unknown defects can become successive small repair steps without a new task contract:

```text
tp schema repair
tp -w <workflow> repair start T01 --file <repair-F1.json>
tp -w <workflow> repair test T01 --id F1 --stage red --note <actual-behavior-failure>
tp -w <workflow> check unit
tp schema repair-result
tp -w <workflow> repair done T01 --id F1 --file <repair-F1-result.json>
```

Repair JSON names an ID, demonstrated finding/blocker reason, existing acceptance `criteria`
(1-based), concrete `paths`, check definitions, and red-green/characterization `verification`.
It appends needed paths/checks to the task, never replaces existing commands/outcomes, captures
original files and checks drift before adoption. Characterization uses `--stage pin`.
The top-level cycle can keep manual verification for its review/closure evidence while each
repair has its own test-first gate. Do not use manual cycle verification to bypass a repair.

Start one step, add and inspect its regressions, checkpoint the intended failure before its
production edits, implement, check green, inspect the diff, then record concrete result
evidence. A missing tool, compile error or broken fixture is not a valid behavioral red.
All previous pins remain immutable; use a distinct regression module/file for a new step
when adding assertions would change an earlier pin. Narrow production files may overlap
between successive repairs. New outcomes or semantic test corrections still need approval.

`test-update T01 --repair F1 --file <mechanical-correction.json>` applies the documented
equivalence-only correction gate to a repair pin. It retains original copies and evidence.
Every step must close before task done. Task completion checks every repair's final tests
on final current contents, so a later repair cannot leave an earlier regression broken.
Partial work, repair checkpoints, logs and original copies survive halt/resume.

## Check inputs and safe reuse

```json
{
  "argv": ["python3", "-B", "-m", "unittest", "discover"],
  "workspace": "app",
  "reuse": true,
  "inputs": {
    "app": ["src/", "tests/", "pyproject.toml", "requirements.lock"],
    "shared": ["build-config.json"]
  },
  "environment": ["FEATURE_MODE"]
}
```

`inputs` maps approved read/write workspace names to relative file, directory-prefix or glob
patterns. `**/` also matches zero directories. Check definition and selected environment values
participate in fingerprints; environment values are hashed rather than printed. Absence of a
declared input is meaningful: later creation/removal invalidates the pass. Literal files are
checkpointed even inside ignored/generated trees. Patterns otherwise select checkpointed
source: name meaningful ignored dependency files literally rather than relying on a glob to
walk caches. No .git/.tp or escaping patterns. Missing `inputs` retains legacy whole-workspace
freshness. `reuse` is still opt-in; unknown external/environment inputs require fresh execution.

Include the command's test runner/scripts, transitive source, build configuration, relevant
feature flags, dependency manifests and lockfiles. An incorrect declaration can reuse stale
evidence; keep whole-workspace defaults when uncertain. External/time-sensitive checks remain
uncached. Scoped passes survive unrelated docs edits and bounded refinement when their inputs
are unchanged. Any monitored source mutation during a check makes it unstable even if it was
outside the selected inputs; a command cannot mutate source and certify its own pass.

## Checks, cancellation and recovery

Checks now have durable operation intent, logs and worker receipts under `.tp/operations/`.
A detached standard-library worker executes only the approved command, enforces its timeout,
and writes its receipt atomically. The caller releases the bookkeeping lock while waiting.
`halt` can therefore save the halt and request cancellation promptly. The worker stops the
command process group, including ordinary grandchildren, and records an interrupted result.
Commands that deliberately detach out of that process group need explicit reconciliation.

```text
tp -w <workflow> status
tp -w <workflow> recover
tp -w <workflow> resume --answer <actual-resume-instruction>
tp -w <workflow> packet T01
```

`recover` merges receipts idempotently, checks the captured contract/source snapshot and
records actual exit status. A success is reusable only when current evidence is valid.
Worker evidence survives caller loss, so recovery does not rerun a completed check. A worker
without a receipt is still running or unknown. Inspect process records/logs; never infer that
silence means failure. For a dead worker with no receipt, stop/reconcile any recorded child
and use `operation finish --id <check-id>` with failed/cancelled status and concrete evidence.
Unknown checks cannot be marked passing by a prose receipt. No automatic exactly-once claim
is made across arbitrary crashes or external systems.

## Commit and delivery receipts

```text
tp -w <workflow> operation begin --id C1 --kind commit --task T01 --intent <exact-effect> --authority <existing-authorization>
tp schema operation-result
tp -w <workflow> operation finish --id C1 --file <read-back-result.json>
```

Kinds are commit and delivery. These commands record intent/outcome, never execute the action
or grant authorization. Read-back evidence names the exact commit, remote artifact, or delivery
result. An interrupted effect becomes unknown; inspect whether it already happened before any
retry. Resolve its actual completed/failed/cancelled status with evidence. Unresolved operations
prevent advancing/final completion. Publishing authority is separate from scope bookkeeping.

## Compact context and delegation

`packet T01` contains the task, requirement text, constraints/non-goals, workspace roots,
authority links, relevant check records, repair and unresolved-operation status. It avoids
file-hash maps and duplicated artifacts. `packet --agent A1` includes the reserved brief.
Default limit is 16,000 bytes; `--max-bytes` changes it. Essential context that exceeds the
limit is an error: narrow the assignment or deliberately use a justified larger packet,
never silently truncate requirements. Read linked decisions/research on demand.

Follow delegation.md to reserve, spawn, attach identity and validate/settle up to three
research/review children. Core-thread SOL/TERRA selection, actual identity and accepted useful
evidence are recorded. No nested fanout, blind acceptance, or unrecorded model fallback.
Each activity must serve an approved requirement or a demonstrated blocker; source-based
validation and the final original-request coverage check remain necessary.
