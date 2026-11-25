---
name: co-task-pipeline
description: >-
  Plan and deliver substantial work through a persistent Codex pipeline, with independent
  plan review, one implementation writer, test-forward repairs and resumable evidence.
  Supports start, resume, halt and status without human scope or plan approval.
---

# Codex task pipeline

Turn the requested work into a reviewed plan, then deliver it. The main session owns scope,
implementation and integration. Resolve material requirements with the user; settle routine
engineering and pipeline mechanics yourself. **No human scope, plan or completion approval
gate applies to new runs.** Existing authorization still governs external effects.

## Start and plan

Invocation: `$co-task-pipeline <planning-location> <request>`, `resume <workflow-dir>`,
`halt` (also `hault`), or `status <workflow-dir>`. Ask only for a missing request/location
or a genuinely ambiguous active run. Use this skill's actual directory, never another client's
helper. Read [helper.md](references/helper.md) for schemas and command details. Here `tp` means:

```sh
python3 "<actual-skill-dir>/scripts/tp.py" -w "<workflow-dir>" <command>
```

1. State the requested outcome and boundaries briefly. Read repository instructions and
   existing edits. Preserve the complete request with `init <location> --title <title>
   --request-file <file>`; supply the actual author identity when exposed.
2. Investigate until you can describe the delivery units and verification. Reuse existing
   evidence; planning does not require a full audit. Bundle material questions about requested
   behavior, destination or authority. Continue independent investigation while awaiting answers.
   Record genuine questions with `block` and actual answers with `resolve`; use saved evidence
   to resolve questions already settled by the request. Never invent a user answer.
3. Write `scope.json`: deliverables, every requested outcome/constraint as a requirement,
   workspaces and non-goals. Compare it against `request.md`. Use Git snapshots for Git roots;
   bound reference-document monitoring to relevant sources rather than historical archives.
   Keep whole-workspace monitoring where production drift detection matters. Run `scope settle`.
4. Write `plan.json`, then `plan check` to render readable `plan.md`. One task should complete
   a coherent deliverable/component cycle, including review, fixes, tests and an authorized
   commit when appropriate. Map every requirement to tasks with objective criteria, actual
   dependencies and concrete files. Unknown findings can use `adaptive: true`; ordinary tasks
   can also refine details and repair defects. Include requested external delivery.
5. Obtain one independent read-only plan review of the exact request, decisions, rendered plan,
   source assumptions and revision. Read [delegation.md](references/delegation.md) when assigning
   a reviewer. Validate and reconcile findings; review material revisions with the same reviewer
   when useful. Record an accepted return with `unresolved: []`, then `plan accept --agent <id>`.
   Begin implementation immediately. A capability gap is not an independent self-review.

Give an estimate with assumptions for substantial work. Reassess from observed progress;
estimates never limit requested scope or justify stopping.

## Deliver

Consult the plan and current task packet; do not repeatedly dump full state/history.
`start T01` → implement and inspect → `done T01 --verify --result-file -` is the normal loop.
The completion call runs missing/stale task checks once and returns the next action. Run
focused checks separately when their output is needed to guide a fix. Acceptance evidence
must address every criterion. A status question means report progress and continue working.

- Select meaningful verification: `red-green` for new behavior/bugs, `characterization` for
  preserved behavior, `existing` for adequate coverage, `manual` when automation adds no value.
  Exercise fixtures before pinning; compiler/import/setup failures are not behavioral red.
- Use `refine` for necessary paths/checks or stronger verification, `widen` for paths alone,
  and `repair` for additional test-first findings inside the same task. These are same-scope
  manager actions, including on ordinary tasks. Do not create a task or approval round per assertion.
- Fix your mistakes. Before a pin, correct and rerun directly. For changed pinned tests,
  preserve old evidence, verify that earlier regression coverage survives, and follow
  [execution.md](references/execution.md). Shared test files may evolve across tasks/repairs;
  do not create artificial files to satisfy a hash lock. Never weaken behavior to manufacture green.
- Correct same-scope scheduling or runner mistakes with `amend --by manager --reason ...`.
  Existing check replacements need a focused independent review of preserved obligations.
  Finish repairs before revalidating affected completed work; stale checks do not erase delivery.
- For requested component review cycles, use [review-loops.md](references/review-loops.md).
  Preserve exact requested iteration counts, reviewer skills, thresholds and review scope.

## Resolve problems without exporting pipeline work to the user

A helper refusal is a diagnosis to investigate, not automatically a human decision.
Read its message, current task/operation and relevant saved evidence. Use the narrow recovery
path and continue. Do not repeatedly retry an unchanged failure, hand-edit internal state,
restart a workflow, or ask the user to authorize an agent's own repair.

| Situation | Owner and response |
| --- | --- |
| Wrong path, missing test fixture, runner mistake, additional necessary file, stale check, reviewed shared-suite evolution | Agent: correct/refine/amend, preserve proof, verify and continue. |
| Interrupted check or handoff | Agent: recover saved receipts; reconcile unknown outcomes before retry. |
| Unrelated finding | Agent: record one optional observation with `note`; do not create a user follow-up obligation. |
| Uncertain observed behavior | Agent: inspect source/tests or use bounded research; uncertainty alone is not a scope decision. |
| Missing requirement, incompatible requested outcomes, new workspace/service authority, required removal/weakening of an outcome | User: show the concrete decision, evidence and consequences; continue independent work. |
| Host permission or genuinely unavailable capability needed for required work | Follow the host's permission mechanism or report the exact missing capability, without claiming completion. |

If a late material question changes the work, update the affected scope/plan and independently
review material revisions. Avoid knowingly implementing an unresolved requirement.

## Keep coordination proportional

Use at most three read-only children within host capacity, with no nested fanout or parallel
writers. Independent plan review is required; other assignments must justify their setup cost.
Reuse a reviewer for focused repair inspection within the same unit. Do not add reviews merely
because a checkpoint exists. Keep source stable while it is being reviewed.

Run focused checks during fixes and one meaningful integration gate per batch. Establish
baselines once. Reuse stable current evidence with complete source/test/config/dependency and
environment inputs; external-state checks stay uncached. After two unchanged infrastructure
failures, diagnose the environment and use `--retry-reason` for an actual change/diagnosis.
Avoid speculative harnesses, installations or unrequested verification matrices.
Set explicit `timeout_seconds` for long integration checks from observed baseline runtime;
the default is five minutes. A timeout is inconclusive, never proof of a product defect.
For this skill's regression suite, use the isolated parallel runner in [helper.md](references/helper.md).

Batch independent reads; serialize mutations. Use stdin JSON and `batch` for already-known
transitions, never predicted evidence or agent identities. Read relevant references only when
needed. At a completed unit or stall, remove duplicated reviews, checks, reads and bookkeeping.
Report delivered units and remaining work. Helper wall spans overlap; unmeasured tokens stay unknown.

## Finish and recover

Finish remaining work and affected verification; review the result against the original request
and requirement ledger. Reuse component coverage and current logs; inspect fixes and integration
gaps, preserving any separately requested full-system review. Record `review`, fix confirmed
in-scope findings, and `final`. Report delivered work, verification and limitations with
`report.md`. No human completion approval is needed.
When scope requests independent final review, reserve `purpose: final` after verification,
collect the actual reviewer, and name both its assignment (`agent`) and host identity
(`agent_id`) in `review`. The assignment covers the whole monitored source and every
requirement; changed source or request/plan revisions need a current review. See [delegation.md](references/delegation.md).

Keep human artifacts at the root: request, scope, readable plan, optional compact research,
report and metrics. Put evidence/drafts/scratch under `.tp/`; logs under `checks/`. Use JSON
for machine payloads and Markdown for prose. Do not duplicate every handoff into several files,
discard proof, clean historical runs, or touch another client's state.

On an actual halt, stop new work, interrupt owned agents, preserve partial artifacts and
record `halt`. On resume, inspect status, request, plan, decisions and partial edits; recover
receipts before replaying anything. Continue missing work from the existing checkpoint.
Status mode is read-only. Legacy contracts retain their original authority; do not fabricate
old approval or silently migrate a run. Ordinary recovery problems do not end an active task.
