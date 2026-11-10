---
name: co-task-pipeline
description: >-
  Scope and deliver substantial work through a persistent Codex task pipeline. Resolve
  material questions, write a detailed readable plan, obtain independent plan review,
  then implement without human scope or plan approval. Supports start, resume, halt,
  and status; one writer with bounded research/review delegation.
---

# Codex task pipeline

The human supplies a unit of work. Restate the requested result in your own words, resolve
material ambiguities with them, investigate enough to make a detailed delivery plan, review
that plan independently, and deliver it. Scoping and implementation are the two phases.
**There is no human scope-confirmation or plan-approval gate.** Do not ask whether to proceed
with work already requested. Clarification is for missing requirements, never ceremony.

The main session owns scope, integration and implementation. This skill permits up to three
read-only research/review children within host capacity; the ceiling is not a target. Use
one independent plan reviewer. Delegate other bounded questions only when they save useful
work. No nested fanout or parallel writers. Choose SOL/TERRA per the
[delegation policy](references/delegation.md); use fresh, narrow briefs and reuse the reviewer
for repair inspection within the same unit when its context remains useful.

## Invocation

| Invocation | Action |
| --- | --- |
| `$co-task-pipeline <planning-location> <request>` | Start beneath that location. |
| `$co-task-pipeline resume <workflow-dir>` | Recover and continue saved work. |
| `$co-task-pipeline halt` or `hault` | Preserve and halt the active run. |
| `$co-task-pipeline status <workflow-dir>` | Report saved progress without advancing. |

Ask for a missing request/location or genuinely ambiguous active run. Use the helper bundled
with the actual skill directory; never assume its deployed path or use another agent’s helper.
Read [references/helper.md](references/helper.md) before advancing state. `tp` below means:

```sh
python3 "<actual-skill-dir>/scripts/tp.py" -w "<workflow-dir>" <command>
```

## Scoping

1. **Understand the request.** Briefly state the outcome, boundaries and constraints in
   ordinary language. Preserve the full request verbatim; initialize with `tp init
   <planning-location> --title <title> --request-file <file>`. Supply `--author-agent-id`
   when the host exposes your identity. Read repository instructions and existing edits.
   Do not wait for a confirmation response when the request is already clear.
2. **Investigate to a planning decision.** Map relevant behavior, dependencies, tests and
   delivery destinations. Reuse existing reports and evidence. Stop when you can specify
   the delivery tasks; do not perform a full audit merely to plan one. Ask material product,
   policy, destination or scope questions during scoping, bundling related unknowns. Continue
   independent investigation while waiting. Resolve every known material question before
   implementation; record actual answers and their consequences once. Routine implementation
   choices belong to you. Record a genuine question with `block`, then `resolve` when answered.
3. **Settle the scope.** Write `scope.json` with requested deliverables, workspaces,
   constraints/non-goals and a requirements ledger covering every distinct outcome, format,
   destination and constraint. Compare that ledger with `request.md`. Use `snapshot: git` for
   Git workspaces. For reference documents, set `monitor` to the specific files/directories
   needed; never monitor whole historical pipeline archives incidentally. Full-workspace
   monitoring remains appropriate for production write roots. Bounded monitoring detects
   drift only in that boundary, plus task files and declared check inputs. Run `scope settle`
   yourself; no invented operator answer. No human sign-off is needed.
4. **Write the detailed plan.** Write `plan.json`, then `plan check` to produce **readable
   Markdown in `plan.md`**, with the delivery sequence, per-unit task breakdown, dependencies,
   concrete files (or adaptive finding-driven paths), objective acceptance criteria and
   verification commands. Use one task per coherent deliverable/component cycle; keep review,
   repair, relevant tests and an authorized commit together when they form one unit. Do not
   create tasks per lens or checkpoint. Use `adaptive: true` for finding-driven work. Keep
   common policy in one place. Link requirement IDs to tasks and verify full request coverage.
   Plan external delivery when requested; a draft alone does not fulfill publication.
5. **Independently review and reconcile.** Give a read-only reviewer the original request,
   settled decisions, rendered plan, source evidence and the exact `plan check` revision.
   Reserve an `agent` assignment with `role: review, purpose: plan`, attach its actual host
   identity, and finish it only after validating its evidence. Require requirement coverage,
   feasible verification, missing work, unnecessary work and unresolved issues. Fix confirmed
   problems; changed request/scope/plan requires review of the new revision. Use `plan accept
   --agent A1` only for the completed accepted review with no unresolved issues. Enter
   implementation immediately. **Do not ask the human to approve the plan.** If independent
   review is unavailable, report that concrete capability gap; do not label self-review independent.

The internal legacy `PLANNING` state is part of scoping, not a separate research phase.
For substantive work, give an estimate with assumptions; unknown repair costs stay unknown.
Estimates inform reassessment, never a time limit or reason to omit requested work.

## Implementation

Use `plan.md` and the current task packet to keep delivery on track. `next` identifies the
ready task or missing gate; `packet T01` supplies its requirements/constraints without dumping
history. Read relevant paged evidence only when needed. Preserve the user’s existing work.

- Start the task, implement all its criteria, verify, and record `done` with evidence for
  every criterion. A mid-run status question means report progress and keep working.
- Refine finding-driven details with `refine`, `widen` or incremental `repair` steps before
  editing newly named files. These are manager decisions inside existing outcomes, not new
  human approval requests. Prefer one coherent regression batch over a separate ceremony per
  assertion. Preserve explicitly requested iteration counts, reviewer skills and thresholds.
- Choose `red-green` for new behavior/bugs, `characterization` to preserve behavior, `existing`
  when tests already cover the change, or `manual` for evidence unsuitable for automation.
  Do not invent tests for trivial reversible edits. A compiler/import/setup failure is **not**
  behavioral red. Check fixture readiness before pinning; inspect actual failure output.
- **Fix your own mistakes.** Repair fixture imports, paths, build setup, incorrect expectations
  or other honest test errors without human approval. Before a pin, just correct and rerun.
  After a pin, use the [test-correction procedure](references/execution.md): preserve original
  copies/logs, get a focused independent review, retain valid unchanged regression proof or
  execute corrected tests on an isolated pre-fix baseline, then record the correction after
  current green. Never weaken the requested behavior, delete coverage, skip tests or change
  expectations merely to make faulty production look successful. Repairing a test is normal
  engineering, not a human policy exception. Inability to prove a regression is unfinished
  verification, not permission to fabricate success.
- Same-scope scheduling/runner corrections use `amend --by manager --reason ...`. Existing
  check-command changes also need a focused independent `purpose: amendment` review; no
  human approval. Requested outcomes/criteria stay fixed, existing pins remain, and concurrent
  edits are never silently adopted. Completed dependent tasks retain delivery evidence while
  affected verification becomes dirty; finish repairs before revalidating those checks.
- New material ambiguity discovered during implementation returns the affected work to
  scoping: isolate the exact decision, continue independent work, clarify, update the readable
  plan and review material changes. Never knowingly start implementation with open questions.
  Changed requested outcomes or workspace authority still require the human’s actual decision.

For component reviews, also read [references/review-loops.md](references/review-loops.md).

## Efficiency and recovery

- Run focused checks while repairing and one meaningful integrated gate per batch. Establish
  necessary baselines once. Use an early non-mutating diagnostic sweep to discover platform
  failures together where useful (`--no-fail-fast` or independent suites); retain the strict
  final gate. Do not rebuild unrelated platforms or repeat benchmarks/licensing audits per fix.
- Reuse stable passing checks with complete scoped `inputs`, including runners, tests, shared
  config, lockfiles, dependencies and relevant environment variables. External-state checks
  remain uncached. Inspect saved logs before rerunning. Do not narrow inputs to preserve a pass.
- After two unchanged infrastructure failures, diagnose readiness/environment rather than
  blindly retrying. Repair demonstrated in-scope causes using existing tools; `--retry-reason`
  records the actual diagnosis/change. Avoid global installs, speculative new harnesses or
  product redesign merely to satisfy an agent-invented verification matrix.
- `next` and other advancing boundaries reconcile completed worker receipts automatically.
  Inspect running/unknown checks; cancel only their recorded worker when necessary. Retry only
  missing verification. Never replay an unknown commit/publication or infer a pass from silence.
- Use stdin JSON (`--file -` / `--result-file -`) for small structured payloads. Batch independent
  reads; serialize state mutations. `batch --file -` runs deterministic transitions in order,
  saves each success, stops at failure and returns the next action. It cannot launch agents or
  make implementation decisions. Do not alternate status/next/full-state dumps after every call.
- After the first delivery unit, and whenever progress stalls, compare review, repair, checks,
  waiting and bookkeeping costs. Remove duplicated activity or fix the blocker. Report delivered
  units and remaining work, with revised estimates when warranted. Metrics are boundary wall
  spans; overlapping durations are not additive and unmeasured tokens stay unknown.

## Scope and artifacts

Admit work only if it serves a requested outcome or removes a demonstrated blocker. Tie a
repair to an existing acceptance criterion. A curiosity or opportunistic improvement does not
expand the job. Record a worthwhile unrelated finding once with `note`; report it at delivery
as an optional observation, without asking the human to accept a follow-up obligation. Required
work cannot be relabeled out of scope to finish early.

Keep the root to `request.md`, `scope.json`, `scope.md`, `plan.json`, `plan.md`, an optional
compact `research.md`, final `report.md`/`metrics.json`, and requested deliverables. Put durable
supporting evidence in `.tp/evidence/`, draft contracts in `.tp/drafts/`, scratch in
`.tp/scratch/` or the system temporary directory. Check logs live in `checks/`; internal state,
checkpoint objects, original files, pins and receipts live in `.tp/`. Do not save a JSON brief,
packet, result, duplicate report and diff for the same handoff. The helper already preserves
structured evidence. Remove only scratch you created when no longer needed; never discard
proof, saved pins or another actor’s files. Do not clean historical runs as an incidental action.

**Never put JSON in a `.md` file.** JSON uses `.json` (or stdin); Markdown contains prose,
headings, lists and meaningful code examples. `plan.md` is the human implementation document,
not a JSON dump hidden inside a fence.

## Finish, halt and resume

After implementation, run affected dirty verification and final checks; review the complete
result against the original request and every requirement. Reuse completed component reviews,
current logs and unchanged coverage. Review changed fixes and integration gaps; preserve any
separately requested full-system review. Validate code and test quality or document claims.
Record `review`, fix validated in-scope findings, and finish with `final`. No human completion
approval is needed. Report delivered work, verification, limitations and worthwhile unrelated
observations, linking `report.md`. External effects still need actual user authorization.

On `halt`/`hault`, stop assigning/starting work, interrupt active agents through host tools,
preserve partial artifacts and record the halt. Stop only on an actual halt request, not elapsed
time or an ordinary recovery issue. On resume, inspect status, request, readable plan, pending
questions and partial edits; merge receipts before replaying anything. Resume the current task
and its checkpoints. Legacy saved contracts stay compatible with their original gates; do not
silently grant them new authority, modify another client’s state, or fabricate old approval.
Status mode remains read-only.
