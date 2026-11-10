# Hidlins task-pipeline execution audit

The largest evidenced delays came from human approval gates around ordinary test mistakes
and repeated task invalidation. Check caching alone would have recovered only a small fraction
of these runs. The revised Codex pipeline therefore changes ownership of scoping, planning,
repair and revalidation, as well as reducing bookkeeping and artifact overhead.

This audit reads the supplied runs without changing them. Implementation is confined to
`.agents/skills/co-task-pipeline` in the dotfiles repository. No deployment, system changes,
OpenCode/Claude edits or historical-run cleanup is included.

## Sources and measurement limits

The source directories supplied by the human are:

- Apple continuation: `/Users/jason/Developer/sources/personal/projects/hidlins/pipelines/2026-11-10-apple-review-repairs-and-final-integration-conti`.
- Linux component run: `/Users/jason/Developer/sources/personal/projects/hidlins/pipelines/2026-11-04-component-reviews-and-integration-regression-rep`.

Evidence comes from each run’s `.tp/state.json`, `.tp/telemetry.jsonl`, request, scope, plan,
research/reconciliation notes, representative amendment proposals and check logs. The Apple
run also has `metrics.json` and final `report.md`. The Linux copy remains `EXECUTING`; its
124.34-hour span ends at the preserved handoff, not a verified completion. This is a review of
saved execution evidence, not a full conversation/token transcript or a fresh hidlins code audit.

| Saved metric | Linux component run | Apple continuation |
| --- | ---: | ---: |
| Preserved wall span | 124.34 hours, incomplete handoff | 15.37 hours, complete |
| Automatic waiting category | 46.82 hours | 9.68 hours |
| Check executions / distinct names | 2,248 / 336 | 245 / 53 |
| Sum of recorded check spans | 6.81 hours | 2.44 hours |
| Helper telemetry calls | 3,407 | 415 |
| Non-`check` helper elapsed sum | 1.89 hours | 15.5 minutes |
| Task acceptance events / accepted task IDs | 77 / 18 | 18 / 5 |
| Repair records | 159: 139 done, 20 superseded | 20: 17 done, 3 superseded |
| Research/review agent records | 132: 30 research, 102 review | 13: 6 research, 7 review |
| Explicit check reuse events | 25 | 0 |
| State JSON size | 115.6 MB | 36.0 MB |
| Checkpoint paths | 37,089 | 41,789 |
| All artifact files / total bytes | 12,917 / 258.8 MB | 1,155 / 83.6 MB |

All sizes use decimal MB. Phase bins and check/helper/agent durations overlap: do not add them
or call them measured active compute. Waiting labels do not establish that all independent
work stopped. Linux includes unclassified/halted time. Tokens were not recorded; Apple’s
metrics explicitly have `usage: null`. Agent counts are workload counts, not proof of waste.

## Findings and resulting changes

### 1. Ordinary fixture mistakes became overnight human decisions

Apple’s `test-correction-SYNC.md` records a prematurely pinned compiler failure followed by a
one-line namespace correction: `common::SyncTestEnv` to `common::sync_env::SyncTestEnv`. Cases
and assertions stayed the same; neither compiler failure was behavioral red. The question
interval in state history runs from `2026-11-10T06:02:47.699235Z` to `15:35:09.042053Z`:
**572.4 minutes**, nearly 62% of that run’s entire wall span.

Linux’s `amendment-T14-F1-build-ownership/proposal.md` records another frozen fixture/build
correction. Its largest decision interval runs from November 7 at `04:27:36Z` to November 8
at `16:15:47Z`: **35 hours 48 minutes**. Other recorded gates include 333.4 minutes for the
T19 verification package, 184.3 minutes for cache descriptor mocks and 87.6 minutes for the
SAF peer-probe correction. Some independent work continued during gates.

The old skill explicitly required human approval for a defective pinned strategy and exempted
only mechanical formatting/lint fixes. That distinction made imports, runner configuration
and honest test mistakes unnecessarily expensive.

**Change:** no human scope/plan approval in new runs. Resolve known material questions during
scoping; write a detailed readable plan and independently review its exact revision. The
agent fixes honest test mistakes autonomously. Before pinning, correct fixture/setup errors
directly. After pinning, preserve old copies/logs and use focused independent correction review.
Retain genuine unchanged proof or execute corrected tests against a trustworthy isolated
pre-fix baseline using the helper’s durable worker. A compiler failure never becomes claimed
behavioral red. No human permission is needed for the same-contract repair.

### 2. Amendment invalidation repeatedly erased completion and blocked repair order

Linux accepted T01–T06 six times each. This was not six independent source reviews: earlier
reports were reused. `amendment-T07-revalidation-order/proposal.md` explains a dependency trap:
replacing T07’s defective KDF fixture reopened prior shared-file tasks and dependents. T07
needed T06 acceptance, while T06’s package suite needed the unfinished T07 repair. A dependency
amendment was required just to proceed. `amendment-T19-verification-package/proposal.md` records
a recurrence requiring temporary removal/restoration of all 17 T19 prerequisites.

Apple accepted T01–T04 three times each and T05 six times. The helper’s old amendment logic
reset affected task completion and recursively reset completed dependents even when the real
obligation was to rerun affected checks.

**Change:** separate delivery evidence from verification freshness. Same-scope manager
amendments preserve accepted tasks and mark affected tasks and transitive dependents dirty.
Complete actual pending/running repairs first; then revalidate affected checks once at a
coherent boundary. Actual defects reopen their owner. Existing check-command changes receive
independent review of preserved obligations; changed outcomes and adoption of other actors’
edits still require a real human decision. Final integration review remains required.

### 3. Final integration discovered platform fixture failures serially

Apple ran `integrated-final` six times, totaling **25.6 minutes** of recorded check span, with
five explicit T05 reopenings. `reconciliation.md` describes successive fixture failures:
external `true` absent from isolated PATH, Linux `/bin/true` assumptions, macOS `/dev/null`
returning ENODEV, `/var` versus `/private/var` equality, sync imports and Rustdoc issues. These
were real portability defects. The notes say broader workspace tests switched to
`--no-fail-fast` only after several failures.

**Change:** where integration/platform testing is requested, run an early bounded diagnostic
sweep that collects independent failures together. Repair a coherent batch, run focused
checks while repairing, and retain the strict final gate. Do not add unrelated platform,
performance or licensing projects to satisfy an agent-invented matrix.

### 4. Infrastructure retries needed earlier diagnosis

Linux contains 16 `android-saf-api36` executions with the same name/argv/source fingerprint
between November 9 `03:18:29Z` and `05:28:47Z`: 15 failures then success. Representative
`checks/check-5208411816794287.log` and `check-8bb99de2164b421b.log` show passing instrumentation
cases followed by `focus-window=other`, `wakefulness=unknown`, and instrumentation exit 255.
Identical source fingerprints do not prove identical emulator state or that every retry was
unnecessary.

**Change:** after two unchanged failures, diagnose fixture/infrastructure readiness and record
the concrete diagnosis/change before retrying. The agent owns demonstrated in-scope recovery;
no new human gate is needed. Required unavailable verification remains unfinished. There is
no automatic “pass,” speculative global installation, or unlimited blind retry loop.

### 5. Broad snapshots and copied checkpoints inflated state and artifacts

Both runs monitor the entire project-documentation workspace using `walk`, alongside the
production Git workspace. That brings historical pipeline evidence into drift/checkpoint
bookkeeping. The helper loads and rewrites full state repeatedly. A superseded unfinished
Linux repair retained a **5.35 MB** `before` snapshot; Apple repairs retained several **6.4 MB**
snapshot copies. Linux task data occupies about 65.7 MB, evidence history 12.5 MB, and
baseline/checkpoint another 10.7 MB. Apple’s fingerprint cache is another 13.6 MB.

The roots also contain hundreds of brief/result/refine/checkpoint/diff files, often duplicating
information already held by the helper. Apple’s plan Markdown is a 31.6 KB JSON fence; Linux’s
is 263.3 KB. Renaming machine data as Markdown did not create a usable human plan.

**Change:** explicitly bound reference-document monitoring to needed paths. Production roots
remain fully monitored by default. Task files and declared check inputs are always included,
including ignored glob matches. Unmonitored paths are outside drift detection; this limitation
is explicit. New workflows store immutable compressed checkpoint maps once in one private
SQLite object store and refer to them from small JSON state. Existing legacy states remain
unchanged. Payloads use stdin, deterministic steps can be batched, packets need not be saved,
and supporting evidence/drafts/scratch have named private locations. Plan Markdown is rendered
as real task descriptions, acceptance criteria, dependencies, files and verification commands.

### 6. Exact passing-check duplication was a secondary cost

Exact duplicate stable passing checks with the same name, argv and source fingerprint account
for **56 extra executions / 4.5 minutes** on Linux and **5 / 2.5 minutes** on Apple. Across
passing and failing groups, there are 113 and 17 extra same-fingerprint executions, including
necessary reds and environment retries. None of these totals establishes that every repeated
run was redundant.

**Change:** retain complete scoped input/environment fingerprints and current passing-log reuse.
Give reviewers existing check logs and retained coverage before rerunning. Do not narrow inputs
or waive failures to manufacture savings. Avoid claiming check caching is the main speedup.

There is positive evidence of already-efficient review reuse: Apple’s `reconciliation.md`
preserves 18 original source reviews and one whole-codebase review, then records focused
repair inspections. The changes preserve that discipline instead of simply reducing reviewer
count and losing requested coverage.

## Latest OpenCode comparison

Reviewed repository commit `550c466` (`task-pipeline: single-source with the Claude variant and
cut round-trip overhead`) and its actual helper changes. Useful ideas adopted here:

- OpenCode `scripts/pipeline/run.py`’s `cmd_advance` reduces record/dispatch round trips. Codex
  now offers sequential stdin batches with durable per-step saves, first-failure stop and next
  action output. It retains one main writer and never pretends to spawn agents itself.
- OpenCode review dispatch supplies relevant existing check logs and scopes repair verification.
  Codex final/task packets now expose saved check evidence, and its guidance keeps unaffected
  component coverage while checking fixes/integration.
- Bounded review batches and relevant verification fit the new delivery units and diagnostic
  sweeps; no new task per lens or human gate per finding.

Not copied: multi-writer sibling-red scheduling (Codex has one writer), OpenCode-specific SQLite
model-context telemetry, or fused red/green acceptance based only on regexes over agent-written
logs. Codex’s observed checks, stable-source fingerprints, preserved test pins and durable
worker recovery are stronger evidence and remain in place.

## Verification and remaining limits

The implementation plan is [efficiency-plan.md](efficiency-plan.md). Independent read-only
agents audited the runs/OpenCode change and reviewed the plan and runtime; confirmed findings
were reconciled with targeted regressions. Runtime tests cover autonomous plan acceptance,
review freshness/open questions, readable Markdown/stdin, batch partial failure, bounded/ignored
input monitoring, honest test corrections with real baseline execution, dirty verification,
retry diagnosis, compact storage and legacy behavior. Final validation results are recorded in
the implementation plan when checks finish.

These checks demonstrate behavior, not a measured future speedup. Comparable real runs are
needed to quantify latency or tokens saved. We can identify the historical approval traps and
remove their cause; we cannot honestly promise a numerical speedup from scripted tests.

Historical run cleanup and changes to hidlins, Claude/OpenCode, global settings or deployment
are outside this change and were left untouched. No separate product side quest was opened.
