---
name: co-task-pipeline
description: >-
  Plan, obtain operator approval, and execute substantial work through a persistent task
  pipeline for code, docs, knowledge bases, tutorials, research, or project work. Use to
  start a task-pipeline or resume, halt, or inspect an existing Codex pipeline. The main
  session implements tasks sequentially, with optional bounded research or review agents.
---

# Codex task pipeline

Own the work from scope through verified delivery. The main session researches, plans,
implements, and integrates; default to no subagents. Preserve the operator's requested
scope and ask when a material requirement or decision remains uncertain. Time and token
efficiency, accuracy, scope fidelity, and asking rather than guessing have equal priority.

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
call, stopping on any failure. Use `tp schema scope|plan|result|review|closeout` for the relevant
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
   `request.md` before confirmation. Recommend `max_agents: 0` and `review: self` by default.
   Code and tests require review. Estimates report effort; they never cap or omit work.
3. Ask about unresolved requirements and present the concrete scope. Run `tp scope check`,
   show/link `scope.md`, obtain confirmation, then `tp scope confirm --answer <response>`.
   Reuse decisions already supplied; do not repeatedly ask the same clarification.
4. Research only what is needed to make an accurate plan. Record reusable conclusions,
   source evidence, operator decisions, and unresolved follow-ups once in `research.md`
   inside the workflow directory. A clear request may need no additional research.
   Before considering delegation, read [references/delegation.md](references/delegation.md).
   Use only approved bounded research or review roles, within `max_agents` and runtime
   capabilities. Prefer GPT-6.1-Terra medium for evidence extraction and high for bounded
   behavioral research or review, following that reference's selection and fallback rules.
   Keep implementation in the main session with one running task.
5. Write `plan.json` with coherent tasks, dependencies, individual relative write files,
   deliverable coverage, each task's `requirements` IDs, objective acceptance criteria, and
   named checks. Every request requirement needs explicit task coverage, including several
   requirements sharing one deliverable. Follow repository conventions. Give each check a
   focused command; set `reuse: true` only when unchanged
   declared workspace contents and a stable environment make its earlier pass reusable.
   Network, time-sensitive, or external-state checks should run each time. Choose verification
   deliberately: `red-green` for new behavior or bug regressions; `characterization` to pin
   behavior before changing its implementation;
   `existing` when current tests adequately cover the change; `manual` for evidence that
   automated checks cannot usefully establish. Explain the choice in each task.
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
- **Test first:** For `red-green`, write the planned tests and run `tp test T01 --stage red
  --note <why-the-failure-proves-missing-behavior>` before production edits. For
  `characterization`, use `--stage pin` to record passing tests before implementation.
  Inspect the output: a missing tool or broken fixture does not prove the intended behavior.
  Preserve pinned tests; a defective strategy needs an operator-approved amendment.
- **Check/done:** Run task checks with `tp check <name>`, inspect the change and results, and
  write a result JSON with evidence for every acceptance criterion. Run `tp done T01
  --result-file <file>` only when that evidence proves completion and required checks pass
  on current contents. An opted-in `reuse` check skips an identical prior pass; use
  `tp check <name> --force` when environment or other untracked inputs changed. Test failures
  and unexpected drift remain unresolved work.
- **Missing file for existing work:** Before editing it, run `tp widen T01 --path <file>
  --deliverable D1 --reason <why-existing-criteria-need-it>`. Add only concrete files in the
  task's existing writable workspace, honoring constraints and non-goals. Reopen a completed
  task first. This needs no extra approval; it preserves scope, criteria, test pins, and
  partial work, records manager provenance, and invalidates checks/review. It cannot adopt
  unexpected edits. A new outcome, workspace, check command, or weaker criterion still
  needs an approved amendment.
- **Unknown or changed contract:** Use `tp block --question <specific-question>`, ask the
  operator, and preserve partial work. First consult scope, plan, research, and decision
  history: if they already settle the question, continue without asking. If a block already
  exists, use `tp resolve --by manager --answer <settled-answer> --evidence <saved-decision>`;
  never present this as new operator approval. Use `tp resolve --answer <response>` for an
  actual operator clarification that leaves the contract unchanged. For changes, prepare
  draft scope/plan files, show their effects, obtain approval, then use `tp amend` as described
  in the helper reference. Never bypass `widen`, weaken criteria, or adopt another actor's edits silently.
- **Unrelated discovery:** Record `tp note <finding-and-consequence>`. Do not fix it in
  passing. If an acceptance criterion depends on it, resolve the dependency now rather
  than parking required work as a follow-up.

Share concise progress and material findings. A mid-run “status?” means report progress
and continue. Estimates prompt reassessment when progress stalls; elapsed time alone
does not justify stopping, shrinking scope, or declaring success.

## Final review and delivery

After all tasks complete, follow `tp next` through final checks, review, closeout, and
`tp final`. Review the complete change against the approved criteria and original planned
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
- **Resume:** Run `tp status` and inspect the request, approved contracts, pending question,
  and interrupted edits. If halted, run `tp resume --answer <operator-resume-instruction>`;
  otherwise continue with `tp next`. Resume grants no new scope or approval of a pending
  decision. Continue a running task from its checkpoint rather than blindly restarting it.
- **Status:** Run only `tp status` (or `tp status --json` for detail), report phase, task
  counts, pending decisions, and contract drift, then stop. This mode must not advance state.

State belongs to this Codex helper. If an existing Claude/OpenCode workflow is rejected as
incompatible, leave it untouched and ask about migration rather than rewriting it.
