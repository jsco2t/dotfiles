---
name: co-task-pipeline
description: >-
  Plan, obtain operator approval, and execute substantial work through a persistent task
  pipeline for code, docs, knowledge bases, tutorials, research, or project work. Use to
  start a task-pipeline or resume, halt, or inspect an existing Codex pipeline. The main
  session integrates and writes, with bounded research/review delegation where it improves throughput.
---

# Codex task pipeline

Deliver the complete request with proportionate planning, verification, and bookkeeping.
The main session owns scope, integration, and implementation; use one writer and choose
bounded research/review delegation when it saves useful work. Preserve requested outcomes,
confidence thresholds, named skills, and iteration counts exactly. Ask about material
uncertainty; resolve routine implementation details within existing authorization.

The operator gives this skill standing permission to use **up to three research/review
subagents**. Put `max_agents: 3` in new scopes unless the operator sets a lower limit; this
is a ceiling, not a target. Respect lower host capacity and do not ask permission per child.
The core thread chooses **SOL or TERRA for each assignment**, records why, and validates the
result. TERRA suits bounded extraction and straightforward analysis; SOL suits ambiguous,
cross-component, architecture, concurrency/security, or difficult synthesis work. See the
delegation reference for concrete models, effort, fallback and escalation. One writer remains
the default; this permission does not enable nested fanout or parallel implementation.

## Operating discipline

- Research to the planning decision. Identify boundaries, dependencies, and useful checks;
  stop once the units can be planned. Do not perform the actual reviews or build exhaustive
  file/hash/dependency inventories during mapping unless the request needs them.
- Plan units of delivered work: one coherent area, article, or review/fix cycle per task.
  Keep review, repair, relevant verification, and an authorized commit in one cycle when
  they form one requested unit. Do not create a task per perspective or checkpoint. Record
  common policy once and reference it instead of copying large matrices into every task.
- Propose `adaptive: true` at plan approval for tasks whose repair files/checks depend on
  findings. Concrete details then use `refine`, without another approval for each defect
  already covered by the approved task. Outcomes and acceptance criteria stay fixed.
- Prefer focused task checks and one integrated gate per meaningful batch; honor stricter
  repository/operator rules. A no-regression constraint does not itself require every
  platform/build/performance suite after every small edit. Establish needed baselines once,
  measure affected hot paths, and run required final gates. Record capability gaps early;
  do not invent passes or build a new harness to satisfy an agent-invented matrix.
- Batch independent searches/reads and reuse saved conclusions, reports and current logs.
  Read named downstream skills once and forward their resolved inputs. Helper state commands
  serialize: parallel `tp check` processes do not accelerate checks. Avoid concurrent builds
  sharing mutable outputs. Use `show T01` for one task and plain `status` for progress;
  do not dump entire plans, state, or fingerprint maps into context by habit.
- At plan approval, resolve warnings about reusable checks without scoped `inputs`: declare
  complete source, runner, configuration, dependency and environment inputs, or explain why
  whole-workspace freshness is necessary. Retain valid evidence through bookkeeping changes;
  never narrow inputs simply to avoid a rerun.
- After the first complete unit, compare actual review, repair, verification, and waiting
  costs with remaining units. If progress stalls or two updates repeat the same blocker,
  diagnose duplicate work, gates, environment, or an oversized unit and adjust execution.
  Report a revised forecast and material blockers. Estimates never excuse missing work,
  early termination, or an unapproved reduction in scope.
- Admit an added activity only when it serves a requested outcome or a demonstrated blocker.
  Tie repairs to existing acceptance criteria and agent assignments to requirements. Record
  unrelated findings once. A curious discovery alone does not expand the work.
- Phase wall spans are measured automatically at existing helper boundaries; refine with
  `activity begin/end` only when useful. Inspect `metrics` at unit boundaries and use
  `usage --file` only for actual host measurements. Helper call receipts,
  check runs/reuse and agent records are automatic; full model/tool counts are not. Keep
  main-thread spans separate from overlapping helper/check/agent durations and operator waits.

For component review/repair work, also read [references/review-loops.md](references/review-loops.md).
For evaluating skill changes and comparing complete runs, see [evals/README.md](evals/README.md).

## Invocation and subcommands

Use the skill name `$co-task-pipeline` followed by one of these forms. Paths containing
spaces must be quoted; treat the remaining request as the operator's complete request.

| Invocation | Action |
| --- | --- |
| `$co-task-pipeline <planning-location> <request>` | Start a new pipeline under the supplied location. |
| `$co-task-pipeline resume <workflow-dir>` | Inspect saved state and continue unfinished work. |
| `$co-task-pipeline halt` | Preserve and halt the active pipeline. |
| `$co-task-pipeline hault` | Alias for `halt`. |
| `$co-task-pipeline status <workflow-dir>` | Report saved status without advancing work. |

For example:

```text
$co-task-pipeline ./planning Add pagination to the existing search endpoint.
$co-task-pipeline resume ./planning/2026-10-20-search-pagination
$co-task-pipeline halt
$co-task-pipeline hault
$co-task-pipeline status ./planning/2026-10-20-search-pagination
```

For a new run, ask if the planning location or request is missing. For `resume` and
`status`, ask for a missing workflow directory. For `halt`/`hault`, use the active
workflow; ask which workflow if none is established or the target is ambiguous. These
are skill-level modes: a new run calls the helper's `init`, not a nonexistent `start`
subcommand for creating workflows. The helper's `start T01` starts an approved task.

## Helper and contract

Read [references/helper.md](references/helper.md) before creating or advancing a workflow.
Use the helper bundled with this actual skill directory, whether deployed or in a repo:

```bash
python3 "<actual-skill-dir>/scripts/tp.py" -w "<workflow-dir>" next
```

`tp` below abbreviates that Python invocation; spell out the actual path in tool calls.
`init` and `schema` do not need `-w`. Use `tp next` at decision boundaries or when the next
step is uncertain; deterministic sequences such as check → done → next can share one tool
call, stopping on any failure. Use `tp schema scope|plan|refine|test-update|result|review|closeout` for the relevant
JSON example, replacing example values with the actual contract and evidence.

The operator confirms scope and then approves the concrete plan. Record their actual
words in `--answer`; never invent approval or treat silence as consent. These gates
are required by this workflow: explain which concrete decision is needed and link the
rendered contract when asking. Use an available question tool where suitable, otherwise
ask directly. Pending required decisions prevent dependent work.

The approved contract fixes deliverables, workspaces, write paths, acceptance criteria,
checks, review method, and agent allowance. Do not change requested outcomes without explicit
operator approval. Adding a concrete file needed by an existing task uses the bounded `widen`
operation below; it does not change outcomes or acceptance criteria. Helper validation supports
judgment; it cannot prove evidence is true or grant filesystem, network, or external-service permissions.

## Start, scope, research, and plan

1. Preserve the complete request verbatim in a file, then run `tp init <planning-location>
   --title <title> --request-file <file>`. Use the printed workflow directory thereafter.
   Inspect applicable repository instructions, relevant sources, and existing edits.
2. Do a small, focused survey in the main session. Define deliverables and destinations,
   read/write workspaces, constraints, non-goals, review method, and agent allowance in
   `scope.json`. Include a `requirements` ledger: map every distinct requested outcome,
   format, destination, and constraint from the full request to deliverable IDs. Preserve
   explicit technologies and execution requirements; a mock, outline, draft, or partial
   implementation cannot replace a requested working deliverable. Compare the ledger against
   `request.md` before confirmation. Select `snapshot: git` for Git workspaces to exclude
   ignored caches while retaining tracked and untracked source; use `walk` for other
   workspaces. Name submodules as separate workspaces. Choose agent allowance for this
   workload within the standing allowance of three; do not automatically recommend zero
   for independent multi-area research/reviews.
   Self final review and delegated component reviews can coexist.
   Code and tests require review. For substantial runs, include an effort estimate and
   assumptions, distinguishing known work/iteration counts from unknown repair cost.
   Estimates report effort; they never cap or omit work.
3. Ask about unresolved requirements and present the concrete scope. Run `tp scope check`,
   show/link `scope.md`, obtain confirmation, then `tp scope confirm --answer <response>`.
   Reuse decisions already supplied; do not repeatedly ask the same clarification.
4. Research only what is needed to make an accurate plan. Record reusable conclusions,
   source evidence, operator decisions, and unresolved follow-ups once in `research.md`
   inside the workflow directory. A clear request may need no additional research.
   Before considering delegation, read [references/delegation.md](references/delegation.md).
   Use only approved bounded research or review roles, within `max_agents` and runtime
   capabilities. The core thread selects SOL or TERRA per assignment using that reference;
   reserve the assignment and its rationale before spawning, then attach its actual identity.
   Keep implementation in the main session with one running task.
5. Write `plan.json` with coherent tasks, dependencies, individual relative write files,
   deliverable coverage, each task's `requirements` IDs, objective acceptance criteria, and
   named checks. Adaptive tasks may start with empty paths and manual review evidence;
   refine to concrete regression files/checks before production edits. Every request
   requirement needs explicit task coverage, including several
   requirements sharing one deliverable. Follow repository conventions. Give each check a
   focused command; set `reuse: true` only when unchanged
   declared workspace contents and a stable environment make its earlier pass reusable.
   Network, time-sensitive, or external-state checks should run each time. Choose verification
   deliberately: `red-green` for new behavior or bug regressions; `characterization` to pin
   behavior before changing its implementation;
   `existing` when current tests adequately cover the change; `manual` for evidence that
   automated checks cannot usefully establish. Explain the choice in each task.
   For scoped reuse, declare each check's `inputs` by workspace and optional environment
   variable names; include its scripts, shared configuration and dependency/lock inputs.
   Missing declarations use the conservative whole-workspace default. Never narrow inputs
   just to retain a pass. Code changed during a check makes that run unstable either way.
   If external delivery is requested, plan an authored draft and a separate integration task
   that transports the reviewed content and records read-back evidence. Review the draft
   before publishing; helper final review still covers the complete delivered outcome.
   Reuse explicit authorization already given for that action; ask only if it is missing or
   the action materially changes. A local draft does not fulfill a requested publication.
6. Run `tp plan check`, present a concise outline and link `plan.md`, then obtain approval
   before `tp approve --answer <response>`. Planning inspects and specifies work; it does
   not implement deliverables. Never copy unsupported Claude/OpenCode helper commands.

## Execute and verify

Loop on `tp next` until completion or an operator decision is needed:

- **Start/continue:** Run `tp start T01` for a ready task. For a running task, inspect partial
  edits and continue from its checkpoint. Implement its complete acceptance criteria within
  its approved paths, preserving pre-existing work.
  Load `tp packet T01` instead of the entire history/plan. It contains outcomes, constraints,
  current checks, repair/operation status and authority links. Narrow an oversized assignment;
  do not drop material constraints to fit a context budget.
  The context packet links paged `checks`, `repairs`, `decisions` and `evidence` sections.
  Fetch relevant sections with `packet T01 --section repairs --offset 0`, following
  `next_offset` until the needed evidence is covered. Full constraints and task authority
  remain in the context packet; read linked decisions before dependent changes.
- **Incremental repairs:** A running adaptive task can contain successive bounded steps:
  `tp repair start T01 --file <repair.json>`, add its regressions, `tp repair test T01 --id F1
  --stage red --note <observed-failure>`, implement, `tp check <name>`, then `tp repair done T01
  --id F1 --file <result.json>`. Use `pin` for characterization. Each step names its criterion,
  files, focused checks and test-first strategy. Keep previous regressions pinned; prefer a
  separate regression file per new step. Later defects get their own step without restarting
  the task or asking again about already-approved outcomes. Final task checks cover all steps.
- **Discovered repair details:** On an approved adaptive task, run `tp refine T01 --file
  <refinement.json> --reason <finding-and-need>` before editing newly named files. It adds
  paths/checks and can establish test-first verification without another approval. It cannot
  change outcomes, workspaces, existing checks, dependencies or an already pinned strategy.
  Neither refine nor widen may silently adopt unexpected edits. Keep review notes in the
  workflow so writing them does not count as production edits before a red checkpoint.
- **Test first:** For `red-green`, write the planned tests and run `tp test T01 --stage red
  --note <why-the-failure-proves-missing-behavior>` before production edits. For
  `characterization`, use `--stage pin` to record passing tests before implementation.
  Inspect the output: a missing tool or broken fixture does not prove the intended behavior.
  Add a step's regressions before its production edits. Preserve pinned tests; a
  defective strategy needs an operator-approved amendment.
- **Mechanical test correction:** On an adaptive task, a formatting/lint-only correction
  with unchanged values, cases and assertions uses `tp test-update T01 --file
  <correction.json>` after its verification check passes on the corrected current contents.
  Compare original pinned copies, explain equivalence, retain the original red/pin log, and
  inspect the diff. Do not restore production just to replay an equivalent test. Weaker
  assertions, changed expectations, removed cases or changed strategy need an approved amendment.
  For repair pins, add `--repair F1`; original copies/logs remain inspectable.
- **Check/done:** Run task checks with `tp check <name>`, inspect the change and results, and
  write a result JSON with evidence for every acceptance criterion. Run `tp done T01
  --result-file <file>` only when that evidence proves completion and required checks pass
  on current contents. An opted-in `reuse` check skips an identical prior pass; use
  `tp check <name> --force` when environment or other untracked inputs changed. Test failures
  and unexpected drift remain unresolved work.
- **Owned check recovery:** If a check hangs, inspect its operation/log and run
  `tp cancel-check --id <check-operation-id> --reason <observed-problem>`, then `tp recover`.
  Cancellation preserves the running task and approval. Inspect the interrupted receipt,
  repair the in-scope cause, then retry only the missing check. Do not halt the whole workflow
  for routine recovery or signal arbitrary processes. A dead worker still requires
  reconciliation; cancellation is a request, never a fabricated failure/pass.
- **Missing file for existing work:** Before editing it, run `tp widen T01 --path <file>
  --deliverable D1 --reason <why-existing-criteria-need-it>`. Add only concrete files in the
  task's existing writable workspace, honoring constraints and non-goals. Reopen a completed
  task first. This needs no extra approval; it preserves scope, criteria, test pins, and
  partial work, records manager provenance, retains current check evidence and invalidates
  final review. It cannot adopt
  unexpected edits. A new outcome/workspace, a changed existing check command, a new check
  on a nonadaptive task, or a weaker criterion still needs an approved amendment.
- **Unknown or changed contract:** Use `tp block --question <specific-question>`, ask the
  operator, and preserve partial work. First consult scope, plan, research, and decision
  history: if they already settle the question, continue without asking. If a block already
  exists, use `tp resolve --by manager --answer <settled-answer> --evidence <saved-decision>`;
  never present this as new operator approval. Use `tp resolve --answer <response>` for an
  actual operator clarification that leaves the contract unchanged. For changes, prepare
  draft scope/plan files, show their effects, obtain approval, then use `tp amend` as described
  in the helper reference. Never bypass `refine`/`widen`, weaken criteria, or adopt another actor's edits silently.
  Amendments and reopening retain repair checkpoints, logs, results and prior attempts;
  reuse that evidence instead of manufacturing replacement reds or manually editing state.
  Replacing pinned tests requires an explicitly approved `amend --supersede-tests T01[:F1]`;
  scope/adoption approval alone does not authorize dropping a regression. Original evidence
  remains archived and a superseded repair must be replaced with the approved verification.
- **Unrelated discovery:** Record `tp note <finding-and-consequence>`. Do not fix it in
  passing. If an acceptance criterion depends on it, resolve the dependency now rather
  than parking required work as a follow-up.
- **Effect receipts:** Before an authorized commit or external delivery, `tp operation begin`
  records the owning task, intent and existing authority. After execution, `operation finish`
  records actual status and read-back evidence. Following interruption, inspect the effect
  before any retry; the helper records receipts and never executes these actions itself.

Share progress in delivered units, findings closed, current activity and remaining work;
distinguish review time from repair and verification time. A mid-run “status?” means report progress
and continue. Estimates prompt reassessment when progress stalls; elapsed time alone
does not justify stopping, shrinking scope, or declaring success.

## Final review and delivery

After all tasks complete, follow `tp next` through final checks, review, closeout, and
`tp final`. Reuse completed review coverage and logs; inspect integration and remaining gaps
instead of restarting every unaffected review. Preserve any separately requested whole-system
review. Review the complete change against the approved criteria and original planned
file baselines, including relevant untracked files and pre-existing edits. Check correctness
and test quality, and verify document claims against sources. Use the approved self or
independent method; never silently substitute one for the other.
Compare the delivered artifacts against `request.md` and every requirement, not just the
plan's task list. Review JSON must include one `requirements` entry (`id`, concrete `evidence`)
per ledger item. Missing requested behavior is unfinished work even when every task passed.
Give reviewers the saved diff/baselines and current check logs once; they inspect sources
and evidence rather than rerunning passing suites without a concrete reason. On repair,
review the fixes and affected behavior, retaining coverage of the complete original request.

Record validated findings using `tp review --file <review.json>`. A `changes` verdict
reopens owning tasks and completed dependents. Repair in-scope defects, repeat affected
verification, and review the current artifacts again. Independent review records must
identify the actual reviewing agent.

Classify every noticed item with `tp closeout --file <decisions.json>`; deferrals or follow-up
obligations require the operator's decision in `--answer`. Required work can be deferred
only through an explicit contract amendment. Classify observations in one batch without a
question; present any actual deferrals together. Keep routine progress out of the noticed
items list. `tp final` validates completion gates and writes `report.md`; it does not run
checks on your behalf. Report what was delivered,
verification and review outcomes, and any approved deferrals, with a link to that report.
Do not claim token measurements the helper does not collect. Committing, pushing,
deploying, or mutating external services requires authorization for those actions.

## Halt, resume, and status

- **Halt/hault:** Stop starting work or assigning agents. Interrupt active commands where
  supported, preserve partial artifacts, and run `tp halt --reason <operator-words>`.
  Record any known interrupted handoff, report the saved workflow location, and stop.
  Honor an explicitly requested finish-current-unit boundary before halting.
  Helper-run checks receive cancellation through the worker and release the bookkeeping
  lock while running. Interrupt delegated agents with runtime tools and record their actual
  cancellation; a helper record cannot interrupt an agent on its own.
- **Resume:** Run `tp status` and inspect the request, approved contracts, pending question,
  and interrupted edits. If halted, run `tp resume --answer <operator-resume-instruction>`;
  otherwise continue with `tp next`. Resume grants no new scope or approval of a pending
  decision. Continue a running task from its checkpoint rather than blindly restarting it.
  Legacy contracts do not acquire adaptive permissions or Git snapshot mode automatically.
  Use `tp recover` to merge durable worker receipts first. If an operation is still running
  or unknown, inspect/wait/cancel/reconcile it; never infer failure and replay a possibly
  completed check, commit or delivery. Recovery is idempotent.
- **Status:** Run only `tp status` (or `tp status --json` for detail), report phase, task
  counts, pending decisions, and contract drift, then stop. This mode must not advance state.

State belongs to this Codex helper. If an existing Claude/OpenCode workflow is rejected as
incompatible, leave it untouched and ask about migration rather than rewriting it.
