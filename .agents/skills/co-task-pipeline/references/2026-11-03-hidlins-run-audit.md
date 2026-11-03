# Hidlins pipeline audit, 2026-11-03

## Finding

The pipeline optimized for a frozen, exhaustively evidenced contract and default serial
execution. It imposed that structure on exploratory review-and-repair work, where repair
files, tests and commands become known only after review. This produced expensive planning,
bookkeeping-driven environment changes, repeated verification, and unnecessary approval waits.
It also did substantive repair work; the elapsed time cannot all be attributed to overhead.

Only `co-task-pipeline` was modified. The prior workflow and sessions were read without
advancing their helpers. Hidlins source and other skills were not modified. This audit does
not independently reassess the application bugs or claim a measured speedup for the revision.

## Evidence and timing

Read-only sources:

- Workflow: `/home/suser/Developer/sources/personal/projects/hidlins/pipelines/2026-11-01-in-depth-component-review-and-bugfix`.
  Relevant files: `request.md`, `scope.json`, `plan-overview.md`, `plan.json`, `research.md`,
  `cycle-ledger.md`, repair/checkpoint amendments and `.tp/state.json`.
- Main session: `/home/suser/.codex/sessions/2026/11/01/rollout-2026-11-01T22-44-35-01a19949-3aac-76f0-b7ad-d95ea74b417d.jsonl`.
  Guardian approval sessions on November 1–2 were distinguished from task agents; they were
  not useful research/review delegation.
- Codex skill/helper/snapshot/tests in this directory; read-only comparisons with
  `.claude/skills/task-pipeline/` and `.config/opencode/tools/task-pipeline/` in this repository.

The preserved original request is broader than the later shorthand: exactly three cycles
per component, test-forward repairs, commits, licensing/dependency/performance constraints,
and a final whole-codebase security review. That exact request matters: early termination
after a clean pass would not have fulfilled the original three-cycle instruction.

| Observed milestone, UTC | Evidence |
| --- | --- |
| November 1, 22:57–23:12 | Request to initial concrete plan: about 14 minutes; source unchanged. |
| 23:26–November 2, 00:14 | Baseline task: about 48 minutes, with cache/drift repairs and refreshed checks. |
| 00:14:43–00:59:22 | First actual component source review: about 45 minutes; ten reported qualifying findings. |
| 00:59–02:16 | About 76 minutes with no session records while a repair/policy amendment awaited approval. |
| 02:25–15:54 | About 13 hours 29 minutes with no session records after the lint-correction approval question. |
| 15:54–20:06 | Repairs, native verification, integration and the cycle commit, then the requested halt. |

The main session spans about 21 hours 8 minutes. Subtracting only the two largest gaps
leaves about 6 hours 23 minutes of remaining recorded span. This is a rough activity window,
not measured compute/working time; it includes other waits and tool execution. The long
lint-related gap is an avoidable blocking mechanism, not evidence of 13 hours of computation.
At halt, only C01 cycle 1 had closed. The recorded commit changed 27 files with 3,497 inserted
and 332 removed lines; a ten-finding repair batch was much more than a read-only review.

## Causes and corrective changes

### 1. Zero agents became the recommended contract for an independent-review workload

The old skill recommended `max_agents: 0` and self review by default. The scope, confirmed
with “Confirmed,” retained that choice; research explicitly scheduled all applicable nine
code-review perspectives in the main session. No task/review subagents were launched. The
agent then correctly obeyed a restrictive contract it had recommended poorly.

Revision: choose allowance from the workload, distinguish one writer from parallel readers,
and enforce one owner of reviewer fanout. Respect runtime slots and approved limits. Do not
automatically use all available agents or claim parallelism makes dependent repairs faster.
Keep useful model/brief selection from the existing delegation reference.

### 2. The plan multiplied machinery before findings existed

Research produced 19 areas, an exhaustive census of 811 non-vendored files, and dependency
inventories. The initial plan created 118 tasks: 57 reviews, 57 separate verify/commit
checkpoints, baseline, security work and final integration. Nine repair tasks were then
inserted for the first review. The final plan was 375,416 bytes, with 127 tasks and 62 named
checks. These are observed artifacts; the census and some additional policy were agent
choices subsequently approved, not explicit requests to inventory every file/hash.

Revision: research ends when coherent work units can be planned. One review/fix cycle is
normally one task, with shared policy referenced once. Explicitly approved adaptive tasks
can add concrete repair files/checks and a test-first strategy without new tasks or invented
approval. Outcomes, criteria, roots, existing checks and dependencies cannot be rewritten
through this mechanism. Larger/multi-batch repairs still need a concrete plan where necessary.

### 3. Checkpointing mistook build caches for source

The old snapshot implementation recursively walked workspaces using a short hard-coded
exclude list. The session reported about 29 GB of SDK/Gradle/Flutter caches under additional
paths. Builds changed ignored metadata, which invalidated check fingerprints. The pipeline
investigated its helper, relocated caches with symlinks, amended the contract, and reran
baselines. `.tp/state.json` ultimately occupied 44,807,971 bytes, including a large original
cache-containing baseline and an amendment listing adopted changes. This is direct evidence
of bookkeeping intruding into product/environment work.

Revision: opt-in `snapshot: git` uses Git's tracked/nonignored-untracked census. Tracked
ignored files and explicit task files still count; cache churn does not. Non-Git and legacy
workflows retain `walk`; mode changes require scope approval. No cache relocation is needed.
Meaningful ignored source needs explicit declaration, and submodules need separate workspaces.

### 4. A semantic-equivalent lint correction became a human gate

`t119-checkpoint-correction.md` asked permission to change `Permissions::from_mode(0)` to
`Permissions::from_mode(0o0)`. The numeric value, six cases and assertions were unchanged,
but whole-file test hashes were immutable. The proposed recovery restored old production,
replayed red/green, and required an amendment. The 02:25 question was followed by the long
gap above; two amendments then processed the correction and adoption of partial edits.

Revision: an approved adaptive task permits documented mechanical test correction after a
current passing check. Save original pinned test copies/logs, preserve prior checkpoint
history, inspect equivalence and update hashes. Semantic changes and weaker tests still
require approval. The helper validates evidence structure, not semantic equivalence itself.

### 5. Broad verification was repeated at repair granularity

History records 187 helper check executions. Examples: `rust-check`, `ignored-tests` and
`vault-performance` each ran 15 times; `interop-vault` ran 13 times. There were 34 baseline
commands before the first review. Check-event durations sum to about 71.7 minutes; that
aggregate is not total pipeline time and excludes commands run outside the helper.
Some repetitions were justified by changing source or failing checks, particularly the
Android recovery work; counts alone cannot prove every repeat was wasteful.

Revision: select affected checks deliberately, establish baselines once, integrate coherent
repair batches, and reuse current logs. Broad checks belong at appropriate integration/final
boundaries unless source changes, failures or stricter repository rules justify more. No
weakened license, security, performance, or regression acceptance is authorized by this policy.

### 6. Long contexts and no throughput correction amplified costs

The main log has 494 top-level tool calls, including 460 `exec` orchestration calls, and three
compactions. Its final cumulative token event reports 116,354,996 input tokens, including
114,356,480 cached input tokens, and 636,793 output tokens (419,147 reasoning output tokens
included in that output total). These are repeated inference-context counts, not unique
request text, a billing estimate, or measurements collected by the pipeline helper. They
show substantial repeated context processing but do not isolate the cost of individual rules.

The approved scope recorded no effort estimate (`estimate_minutes` was null), despite the
known 57-review count. The first source review took about 45 minutes: at that rate, 57 passes
would consume about 43 hours before repairs. That is an illustration, not a forecast across
unequal components; it shows why a throughput reassessment was necessary before continuing
the same approach. The workflow supplied no useful expectation correction.

Revision: an initial estimate with explicit unknowns, compact task retrieval with read-only `show`, bounded briefs, batched independent
reads, one saved coverage/evidence record, and reuse of completed review coverage at final
integration. Forecast again after the first complete unit, separating review, repair,
verification and waits. Do not let “estimates never cap work” mean ignoring deteriorating
throughput; change execution without silently changing deliverables.

## Comparison limits

Claude's pipeline already supports scoped research/dispatch, a standing fix-task allowance,
scoped test commands and manager-origin amendments within that allowance. OpenCode's helper
exposes mechanical `amend --reason`, `widen`, and test-baseline recovery. Those are useful
design comparisons. This audit did not benchmark their runs, and does not establish that
their full runtime behavior or guardrails should be copied into Codex. No compared files
were changed.

## Validation and remaining limits

The helper's existing 48 behavioral tests passed before implementation. Added regression
coverage exercises Git cache/source boundaries, adaptive refinement through red/green and
final delivery, refusal of unauthorized contract changes, mechanical correction evidence,
and compact read-only task retrieval. All 61 tests passed after the changes, and
`git diff --check` passed. Run the complete suite with:

```bash
python3 -B -m unittest discover -s .agents/skills/co-task-pipeline/tests -v
```

These tests validate workflow behavior. They cannot prove that an agent chooses a useful
component decomposition, correctly judges a defect or mechanical equivalence, or completes
a future many-hour run faster. Validate that operationally on the first complete unit of
the next authorized run. Do not resume or rewrite this historical Hidlins workflow as part
of this skill repair; its saved contract still governs it.
