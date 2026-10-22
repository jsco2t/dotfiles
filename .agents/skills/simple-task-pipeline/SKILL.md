---
name: simple-task-pipeline
description: >-
  Plan, obtain human approval, and execute substantial work through a persistent task pipeline
  for code, docs, knowledge bases, tutorials, research, or project work. Use to start, resume,
  halt, or inspect a pipeline entirely in the main agent's context, without subagents.
---

# Simple Task Pipeline

Perform the entire workflow in the **main agent's context**: scope, research, planning,
tests, implementation, review, fixes, and delivery. **Never launch or resume subagents or
delegate work.** Apply other skills' relevant instructions and review lenses yourself;
if they require delegation, perform the equivalent work directly.

This skill works across agent hosts, including OpenCode. It requires a shell and Python 3;
Git supports repository inspection. Optional issue surveys need the corresponding CLI.
Use whatever file, shell, and question tools the host provides. If there is no question
tool, ask directly and wait for required decisions. No host-specific agent API, session
identifier, scheduler, or Codex facility is needed.

Use the helper bundled with this actual skill directory, whether installed or in a repo:

```bash
python3 "<actual-skill-dir>/scripts/tp.py" -w "<workflow-dir>" <command>
```

`tp` below abbreviates that invocation; resolve the script path from this `SKILL.md` and
spell out the absolute path in shell calls. Read [references/helper.md](references/helper.md)
for command syntax, result files, recovery, and correction paths. `tp --help` and command
`--help` describe the installed CLI. `init`, `schema`, `roster`, and `check-docs` can run
without `-w`. Run `tp next` after transitions and finish the complete approved work.

## Invocation

The host may expose this skill using `/`, `$`, `@`, or another invocation syntax. Interpret
the arguments after `simple-task-pipeline` as follows; quote paths containing spaces:

| Arguments | Action |
| --- | --- |
| `<planning-location> <request>` | Create a new workflow beneath the supplied location. |
| `resume <workflow-dir>` | Recover saved progress and continue unfinished work. |
| `halt` or `hault` | Preserve and halt the active workflow. |
| `status <workflow-dir>` | Report saved status without advancing work, then stop. |

Ask for a missing planning location, request, or workflow directory. For halt, use the
active workflow; ask which one only if the target is unknown or ambiguous. A new workflow
uses `tp init`; resuming **never** calls `init`, repeats completed stages, or replaces a draft.
A mid-run “status?” asks for a progress update: report `tp digest`, then continue working.

## Persistent contract and estimates

Keep the workflow folder at the supplied planning location, independent of the workspaces
where deliverables live. It stores the verbatim request, scope, plan, decisions, research,
briefs, results, snapshots, check logs, review findings, and halt records. These saved
artifacts, rather than conversation memory or an agent session id, allow recovery.

Only the helper writes `.tp/`, `decisions.md`, and `noticed.md`. Write scope, plan,
step results, and deliverables as directed. Do not edit internal state to bypass a refusal.
The helper reads version-1 state with an `in_flight` object, including older workflows.
Incompatible formats, including `co-task-pipeline` state, must remain untouched; explain
the mismatch and ask about migration instead of reinitializing or switching helpers.

Scope confirmation and concrete plan approval are human decisions. Record the actual
words in `--answer` or `--feedback`; never infer approval from silence or from a resume
instruction. Reuse answers already given. Explain the needed decision and link the rendered
contract. Pending required decisions prevent dependent work.

Provide **estimated minutes for each major stage and the total pipeline**, first at scope
and updated when the plan makes the work clearer. Use `estimates` in scope/plan with the
stage keys `scope`, `research`, `planning`, `execution`, `review`, and `closeout`. Task
`estimate_min` and research `--minutes` are estimates too. The helper derives execution
and review estimates from the concrete plan. Include tests in the execution estimate and
final checks in closeout. The helper preserves unknown stages in older workflows as
“not estimated”; fill them when useful without restarting or reopening approved scope
solely for missing timing metadata.

**Estimates never constrain the work.** No time boxes, maximum task durations, planning
deadlines, or required early submission. Continue until criteria are satisfied or a real
blocker needs a decision. Split work for coherent scope, dependencies, or manageable context,
never to fit an arbitrary duration. Legacy `budget_minutes`, `--budget`, and `budget extend`
are compatibility spellings for advisory estimates. Any older brief that calls timing a
hard box or says to stop when time runs out is superseded by this rule. Recorded minutes
are elapsed step time, subject to idle/stall corrections, not measured model billing.

## Scope, research, and planning

1. Preserve the complete request verbatim in a file. Run `tp init <planning-location>
   --title <title> --request-file <file>`, and use the printed workflow directory thereafter.
   Inspect applicable repository instructions, relevant sources, and existing edits.
2. Survey only what helps establish scope: `tp survey <repo> --name <workspace>`, optionally
   `tp survey-issue jira:KEY-123` or `gh:owner/repo#123`. A clear request may need no research.
3. Draft `scope.json` from `tp schema scope`: deliverables, destinations, read/write workspaces,
   constraints, non-goals, estimates, conventions, and review method. Select work roles using
   `tp roster suggest --kinds <kinds>`. Catalog labels in `participants` and `agent` fields name
   **roles you perform**, never separate workers. Retain appropriate author, tests, research,
   and review roles. Choose `review: none|final|per-task|both`; code always needs review before
   acceptance even when there is no separate review step. Run `tp scope check`, present/link
   `scope.md`, obtain confirmation, then `tp scope confirm --answer <response>`.
4. Research what is needed for an accurate plan, sequentially. Add an item with `tp research
   add R1 --agent <research-role> --purpose map|requirements|investigate --questions-file <file>
   --done-when <criterion> --minutes <estimate>`. Each has at most three questions of at most
   40 words. Map/requirements items establish planning facts rather than author deliverables;
   use investigate to trace a named behavior. There is no duration cap. Dispatch one item,
   read its brief, investigate, write its result JSON, fact-check the evidence, then `tp record R1`.
   Decide every reported follow-up: pursue with another item using `--from R1.F1`, or dismiss
   it with a reason. Reuse saved results rather than surveying or researching them again.
5. Write `plan.json` using `tp schema plan`: coherent tasks, actual dependencies, deliverable
   coverage, objective acceptance criteria, precise relative write paths, sources, estimates,
   and named checks. List shared instruction files in plan `conventions` as `wf:<file>` or
   `<workspace>:<file>`; they freeze with the plan and reach every brief. `research:R1` cites a recorded research result. Paths must stay inside
   write workspaces; avoid whole-workspace catch-alls and generated trees. Sequential tasks
   may share files; add dependencies when one task actually requires another's output.
   `docs` is a built-in task check; `docs-all` is a built-in final check. Define repository
   commands in `checks`; there is no implicit `code` check.
6. Code is test-forward: set `test_cmd`, `tests_paths`, and `test_mode: red|pin`. Red proves
   missing behavior before production changes; pin characterizes existing behavior first.
   Tests-only deliverables use pin. Research and planning specify work without implementing it.
   With final review, split large task sets into `review_batches` for manageable review context;
   every task belongs to one batch. Perform all review lenses yourself, sequentially.
7. Run `tp plan check`, repair validation errors in the existing draft, and `tp plan submit`.
   Present a concise outline, stage and total estimates, review method, and open decisions
   with a link to `plan.md`. Obtain approval, then `tp approve --answer <response>`, or record
   requested revisions using `tp revise --feedback <response>`. Never discard existing research,
   answers, or accepted work because a draft needs correction.

## Execute and verify

Loop on `tp next`, completing each local step before starting another:

- **Dispatch/fix/review:** `tp dispatch <id>` writes one brief and marks it in flight. Read it
  and perform the step yourself. The helper refuses a second active step. For code, tests-only
  comes first: observe the intended red or pinned green, write and record that result, then
  implement in the separate implementation step. A broken fixture or missing tool is not a
  meaningful red result. Preserve pinned tests; a defective strategy needs a recorded decision.
- **In flight:** inspect the existing brief, partial result, and workspace edits. Continue the
  current step; do not dispatch it again. There is no background worker to wait for.
- **Record:** write the JSON at the brief's exact result path, inspect the source/diff and check
  output, then `tp record <id>` without `--agent-id`. Existing fleet-era ids are bookkeeping;
  never fabricate them or reconnect an agent session. Malformed results need correction, not
  redispatch. The helper checks paths, tests, and configured checks.
- **Check:** fact-check the printed sample or `tp sample <id>`, review code and tests, then
  `tp accept <id> --note <evidence>` or `tp reject <id> --reason <finding>`. Rejections route
  into fix rounds. Time alone cannot reject or complete work.
- **Triage:** inspect `tp show <review-id> --part blocking`, verify findings against source,
  then `tp triage <review-id> --accept-all` or dismiss/assign specific findings. Fixes go to
  owning tasks, followed by verification of the fixes. Reviews do not edit deliverables.
- **Human decision:** preserve partial work and ask the specific unresolved question. Use
  `tp exception --summary <question>` for a workflow blocker, adding `--task <id>` for a task
  blocker. Record the response with the appropriate `tp resolve` action. Consult saved scope,
  plan, and decisions first; do not repeat settled questions. Use `tp revise --scope` when
  confirmed scope changes, and present the changed contract for approval.
- **Mechanical correction:** `tp widen` grows a task's write set and `tp amend` records allowed
  plan corrections; see the helper reference. These cannot silently change deliverables or
  acceptance criteria. Respect filesystem and service permissions independently of plan gates.
- **Unrelated discovery:** `tp note <finding-and-consequence>`. If a criterion depends on it,
  resolve that dependency now rather than claiming completion with required work deferred.
- **Progress:** share concise findings and `tp digest` after meaningful completed work. Keep
  working until a required human decision, explicit halt, or verified completion.

If known environment breakage affects final checks, `tp baseline` records it before work
starts. Inspect failures: a baseline is evidence of pre-existing breakage, not permission
to hide a regression. Use `record --credit`, `record --dead-minutes`, or `tp clock` when
correcting elapsed-time reports; none changes acceptance gates.

## Closeout and delivery

After all tasks, perform the approved review method on the combined changes, including
untracked files and pre-existing edits. Identify this honestly as self-review. Check
correctness, test quality, and documentation claims. Route blocking findings through triage,
fixes, verification, and acceptance before completion.

When `tp next` says closeout, `tp closeout` lists noticed items. Classify each using
`--item N --class deferred|followup|observation --note <issue-and-consequence>`. Render the
batched decision with `tp closeout --ask`, ask the human, and record it with `tp closeout
--decide --answer <response>`. Required criteria cannot be deferred without an approved
contract change. If no noticed items require a decision, follow the helper directly to final.

Run `tp final` for final checks and `report.md`. Report delivered work, verification,
self-review, and approved deferrals with a link to that report. Commit, push, deployment,
and external writes need authorization for those actions.

## Halt, resume, and status

- **Halt/hault:** stop starting work, interrupt active shell commands where supported, and
  preserve partial files. Run `tp halt --reason <human-words>`. It writes `halt.json` immediately,
  including unfinished steps and their artifact paths. No step needs to finish or pretend
  success before halt. Report the saved workflow location and stop.
- **Resume:** run `tp status`, then **always** `tp resume --answer <resume-instruction>`, whether
  the prior session halted cleanly or vanished. `--json` supplies structured recovery context.
  Read the saved request, scope, plan/draft, decisions, completed research, pending questions,
  current briefs and results; inspect workspace edits. Use the returned checkpoints to continue
  in-flight research, tests, implementation, fixes, or review **without redispatching** or
  deleting existing results. A result already on disk may only need validation and recording.
  If planning stopped with a draft, repair/validate that draft and submit it. If approval is
  pending, ask for it; resume supplies no approval. Preserve accepted tasks and review rounds.
  Run `tp next` and finish remaining work. If a task truly cannot continue safely, `tp lost`
  records the loss for a deliberate retry; ordinary context loss does not require this.
- **Status:** run only `tp status` or `tp status --json`, report phase, progress, pending decisions,
  checkpoints, and drift, then stop. It does not write state or advance the workflow.

Never initialize over a saved workflow, manually reconstruct `.tp/`, or restart from scope
because the conversation was lost. If artifacts are missing or incompatible, report the
specific evidence and resolve that issue while preserving everything that remains.
