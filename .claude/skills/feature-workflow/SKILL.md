---
name: feature-workflow
description: >
  Plan, human-approve, autonomously execute, and archive an ordered software
  work package. Invoked explicitly via the /feature-workflow command. Use for
  any planned feature, bug batch, or maintenance milestone that should proceed
  through plan -> approve -> sequential execution -> final review -> archive.
  Supports multiple independent workflows, revision cycles, halt/resume,
  and external state storage.
---

# Feature Workflow

You are the main engineer and workflow owner.
A workflow represents one work package.
A work package may contain: one feature; several related features; one bug;
a batch of bugs; a mixture of related features and bugs; or a bounded
maintenance milestone.

## Model Requirements

**Main session**: Must run on Opus with high or greater reasoning effort.
If you detect you are running on a lesser model, STOP and inform the user.

**Worker subagent**: Uses the `workflow-worker` agent definition (Sonnet,
high reasoning). The worker MUST NEVER use Claude Haiku.

## Quality Mandate

This instruction applies to EVERY substantive step in this workflow:

> The goal here is to not find ways to make this process more efficient or to
> cut corners. The goal IS to produce the highest quality feature possible. DO
> NOT SKIP STEPS. DO NOT DEFER WORK. If you are not sure how to proceed — ask
> a human.

## No Deviation Rule

The approved plan is the implementation contract. You MUST NOT:

- Add work not in the plan
- Skip work that is in the plan
- Reinterpret requirements to avoid difficulty
- Silently defer work to "a future task"
- Expand scope of any task beyond its boundaries
- Change architectural decisions made in the plan
- Make ANY silent deferrals
- Start a task, complete part of it, and declare the rest "can be done later"
- Combine, reorder, or merge tasks without approval
- Mark an acceptance criterion as met when it is not

Any situation requiring deviation: write `pending_deviation` to state.json
describing what you want to do and why. The Stop hook will see this field on
the next turn and force `PLAN_CHANGE_REQUIRED`, stopping execution for human
review. **Deviating and continuing in the same turn is not reachable.**

**THE USER MUST BE INVOLVED IN EVERY DEVIATION.**

### Mechanical Safeguards (enforced by the Stop hook)

These are separate-process checks the model cannot bypass:

1. **Plan hash**: Planning artifacts are frozen after approval. Any edit
   triggers PLAN_CHANGE_REQUIRED.
2. **Task-set integrity**: The hook compares task IDs in state against
   tasks/*.md files on disk. Missing or extra entries trigger
   PLAN_CHANGE_REQUIRED.
3. **Per-criterion completion**: A task claiming COMPLETE with any unmet
   acceptance criterion is blocked with a correction naming the gap.
4. **Deviation detection**: Any `pending_deviation` field in state triggers
   PLAN_CHANGE_REQUIRED.
5. **Task size bound**: Approve refuses tasks exceeding 1.5 days.

## State Root Resolution

Resolve the state root through this precedence:

1. `CLAUDE_WORKFLOW_STATE_ROOT` environment variable — use its value directly.
2. **Repository-root** `.claude/workflow.json` — this is
   `<repo_root>/.claude/workflow.json`, **NOT** `~/.claude/workflow.json`.
   The `.claude/` directory inside a repository is often git-ignored, so the
   file won't appear in `git ls-files`; check the filesystem directly.
   Discover it with:
   ```bash
   REPO_ROOT="$(git rev-parse --show-toplevel)"
   cat "$REPO_ROOT/.claude/workflow.json" 2>/dev/null || echo "NOT_FOUND"
   ```
   If the file exists and contains a `state_root` field, use that value.
3. `~/.claude/workflow-state/` (default) — fall back here only when neither
   of the above resolved.

All paths below are relative to the resolved state root.

Active workflow root: `active/<workflow-id>/`
Archive root: `archive/`

Use subagents sparingly. The main session owns nearly all reasoning,
orchestration, implementation, review, validation, and acceptance.

When you dispatch background (async) subagents — for example, running the
review pipeline's reviewers in parallel — and have nothing to do but wait for
their results, you may end your turn. The workflow Stop hook is wait-aware: it
will not force a continuation while background subagents you dispatched are
still outstanding, and each subagent's hand-back re-invokes this session
automatically. Waiting this way is not stopping and does not cut corners.
Do NOT keep a subagent perpetually in flight to avoid making progress:
consolidate results as they return and continue the current phase. If the same
wait repeats with no task progress, the hook will require concrete progress.

# Invocation Modes

Supported explicit invocations:

- `/feature-workflow <work description>`
- `/feature-workflow revise <feedback>`
- `/feature-workflow approve`
- `/feature-workflow resume`
- `/feature-workflow status`
- `/feature-workflow halt`
- `/feature-workflow archive`
- `/feature-workflow list [active|archived|all]`
- `/feature-workflow history`

Determine the mode only from the explicit invocation argument.
Never infer approval. Never infer archive intent.

# Global Workflow Invariant

Multiple independent workflows may coexist under `active/`. Each is bound to
at most one session. A session drives at most one workflow.

- Never bind a session to two workflows.
- Never bind two sessions to one workflow.
- Never overwrite a completed package.
- Never silently discard workflow state.

# Work ID Format

Every work package receives a stable work ID:
`YYYY-MM-DD-<filesystem-safe-slug>`.
Examples: `2026-08-23-features-1-2-3`, `2026-08-30-bugs-a-b-c`.
Use lowercase letters, digits, and hyphens. If
`active/<work_id>/` already exists, append `-02`, then `-03`, etc.
Never overwrite an existing workflow.

# Mode: start

Start mode applies when the invocation contains a new work description rather
than revise, approve, resume, status, halt, archive, list, or history.

## 1. Check session binding

Read the session ID by running:
```
python3 -c "
import sys; sys.path.insert(0, str(__import__('pathlib').Path.home() / '.claude' / 'skills' / 'feature-workflow' / 'scripts'))
from workflow_lib import get_current_session_id; sid = get_current_session_id(); print(sid or 'NONE')
"
```
This reads the stamp file written by the SessionStart hook (keyed by working
directory). If the result is `NONE`, inform the user that the SessionStart
hook may not be registered and stop.

Check `sessions/<session_id>.json` under the resolved state root. If this
session is already bound to a workflow, report it and stop. A session may
drive only one workflow.

## 2. Initialize workflow

Generate a work ID. Create `active/<workflow-id>/`, `active/<workflow-id>/tasks/`,
`active/<workflow-id>/evidence/`. Create `archive/` if it does not exist.

## 3. Bind session

Write `sessions/<session_id>.json` binding this session to the new workflow.
Record the repository root.

## 4. Determine identity

Create a concise human-readable title and the filesystem-safe work ID.

## 5. Record the request

Write `request.md` with the human's complete work description.
Preserve requirements. Normalize formatting if useful. Do not silently change
meaning.

## 6. Capture baseline

Run `git rev-parse HEAD`. Record as `baseline_sha`.

## 7. Initialize state

Create `state.json`:

```json
{
  "schema_version": 2,
  "workflow_id": "<workflow-id>",
  "title": "<human-readable title>",
  "phase": "PLANNING",
  "created_at": "<UTC timestamp>",
  "updated_at": "<UTC timestamp>",
  "approved_at": null,
  "completed_at": null,
  "archived_at": null,
  "baseline_sha": "<git HEAD>",
  "final_sha": null,
  "repo_root": "<repository root path>",
  "iteration": 1,
  "plan_revision": 1,
  "approved_plan_sha256": null,
  "current_task": null,
  "tasks": [],
  "task_retry_limit": 3,
  "final_retry_limit": 2,
  "final_attempts": 0,
  "stop_continuations": 0,
  "max_stop_continuations": 60,
  "halt_requested": false,
  "block_reason": null,
  "open_questions": [],
  "revision_history": []
}
```

## 8. Investigate the repository

Use the MAIN SESSION. Do not spawn a worker during planning.
Inspect enough of the repository to understand: current architecture; relevant
implementation; related tests; repository conventions; build system; formatter;
linter; type checker where relevant; standard test commands; likely affected
modules; compatibility requirements; important invariants.
Do not modify product code.

The goal here is to not find ways to make this process more efficient or to
cut corners. The goal IS to produce the highest quality feature possible. DO
NOT SKIP STEPS. DO NOT DEFER WORK. If you are not sure how to proceed — ask
a human.

## 9. Determine the quality gate

Discover actual repository commands. Do not invent generic commands.
Create `gate.json`:

```json
{
  "standard_commands": ["<command>", "<command>"],
  "final_commands": ["<command>", "<command>"]
}
```

`standard_commands` must contain the normal completion criteria for this
repository: formatting checks, lint, static analysis, compilation, type
checking, and unit/integration tests, where actually applicable.
`final_commands` should contain the complete package-level validation. It may
equal `standard_commands`. If a class of validation genuinely does not exist in
the repository, do not invent one; explain the omission in `plan.md`.

## 10. Write plan.md

Create `plan.md` with these sections:

- Objective — the complete approved outcome.
- Current behavior — relevant existing behavior, with code path traces
  referencing specific files and line numbers.
- Proposed implementation — the overall strategy, grounded in code evidence.
- Architectural decisions — decisions future tasks must respect.
- Work included — the features/bugs/items in this package.
- Task sequence — every task document in exact execution order.
- Quality gate — the commands from gate.json and why they are appropriate.
- Test gap assessment — existing test coverage for affected code paths, what
  tests are missing, and what test cases would validate the implementation.
  This section is MANDATORY.
- Risks — meaningful technical risks.
- Out of scope — explicit boundaries.
- Final acceptance criteria — package-level observable criteria.
- Open questions — every unresolved question (see below).

### Planning Rules

These rules are non-negotiable:

1. **Every claim about the code MUST reference a specific file and line number.**
   "Probably in the validation logic" is NOT acceptable.
   "In `provisioner_selection.go:217`, the condition checks X" IS acceptable.

2. **The test gap assessment is mandatory.** Skip it and the plan is incomplete.
   Every implementation task MUST have a corresponding test task or test
   acceptance criterion.

3. **Task size MUST NOT exceed 1.5 days of estimated effort.** The approve mode
   will refuse to proceed if any task exceeds this bound. Smaller tasks have
   clearer completion criteria and less room for partial work.

4. **Verify repository artifact naming conventions.** When the plan references
   any repository artifact (changelog entries, migration files, generated code),
   check the generator code or list recent examples to discover the actual
   naming pattern. A wrong path in the plan propagates into the task doc and
   then the working tree.

5. **Do not use vague acceptance criteria.** Each criterion must be objectively
   inspectable — a boolean condition that can be verified by reading the code
   or running a command.

### Quality Gate Discovery

When determining `gate.json` commands, check in this order:

1. **CLAUDE.md** — authoritative if present; use exactly what it specifies
2. **README.md / CONTRIBUTING.md** — often documents build/test/lint commands
3. **Makefile, magefiles/, justfile, package.json scripts** — repo tooling
4. **Language defaults** — last resort only

Always prefer repository-specific tooling over raw language tooling.

## 11. Evaluate architectural impact

After writing `plan.md`, evaluate whether the planned change has moderate or
higher architectural impact. This is a judgment call — use the triggers and
non-triggers below.

### Triggers (run /arch-plan-reviewer)

Run `/arch-plan-reviewer` when the planned change involves ANY of:
- A significant new feature or new subsystem with no close analogue in the
  repo (greenfield work where architectural direction matters most)
- Introducing a new package, module, or major structural boundary
- Introducing a new interface or abstraction layer
- Cross-layer changes (e.g., changes spanning API, business logic, and data access)
- Adding a new external dependency with structural implications
- Changing a documented architectural decision from plan.md or CLAUDE.md
- Data-model or schema changes that affect multiple consumers
- Changes spanning 3 or more packages

### Non-triggers (skip)

Skip the architectural plan review when the change is:
- A bug fix localized to one function or one file
- Adding a new field to an existing struct with no structural consequence
- Test-only changes
- Documentation-only changes
- Mechanical refactors within a single package (renames, moves, extractions)

### Running the review

When triggered, invoke `/arch-plan-reviewer` with the path to `plan.md` as
the primary input. Optionally include affected source paths (from the plan's
"Proposed implementation" and "Expected areas of change" sections) so the
reviewer can discover existing conventions the plan should respect. When the
change is greenfield with no relevant prior art, pass only the plan — the
skill reasons from language idiom and first principles.

### Processing findings

Findings from `/arch-plan-reviewer` are plan-level inputs, not code fixes:

- **Critical findings (confidence >= 90)**: Incorporate into plan.md's
  "Architectural decisions" section. These represent structural decisions
  or constraints the implementation must respect.
- **Important findings (confidence 80-89)**: Either adjust the plan to
  account for the concern, or raise as an open question in step 12 for
  human resolution.
- **Candidate approaches**: When the reviewer proposes alternative approaches
  with tradeoffs, evaluate them against the plan's stated objectives.
  Incorporate the strongest approach into the plan, or raise as an open
  question if the tradeoff warrants human input.

### Recording the decision

Whether `/arch-plan-reviewer` was run or skipped, record the decision and
reason in `plan.md` under a new section "Architectural review":

- If run: summarize the findings, any alternative approaches considered,
  and how they were incorporated.
- If skipped: state the reason (e.g., "Skipped — change is a localized bug
  fix within a single function").

Do not silently skip this step. An unrecorded skip is a gap in the planning
record.

## 12. Surface open questions

During investigation and planning, record EVERY open question that could affect
implementation. Write them to the `open_questions` array in `state.json`:

```json
{
  "open_questions": [
    {
      "id": "Q1",
      "question": "Should the API return 404 or 204 for empty results?",
      "context": "The existing endpoints are inconsistent on this.",
      "impact": "Affects tasks 002 and 003 acceptance criteria.",
      "resolved": false,
      "resolution": null
    }
  ]
}
```

Also include them in `plan.md` under "Open questions".

**Approval is blocked while any open question has `resolved: false`.** The
approve mode will refuse to proceed until all questions are answered.

Actively look for:

- Ambiguous requirements in the work description
- Conflicting patterns in the existing codebase
- Missing context about external dependencies
- API design decisions with multiple valid approaches
- Performance/security/UX trade-offs
- Compatibility requirements not stated in the request

The goal is an automated process. The plan grounds the ability for Claude to
work autonomously. Unresolved questions create ambiguity that forces deviation
from the plan during execution — which violates the no-deviation rule. Resolve
everything before approval.

## 13. Run test planning

Invoke `/eng-test-planning` with the path to `plan.md`. This skill reads the
plan, studies existing test patterns in the codebase, and appends a test plan
section to the planning document, ensuring test-forward coverage.

This MUST happen during PLANNING, before task documents are generated. The
test plan informs task decomposition — tests may need their own tasks, or test
requirements may affect implementation task scope.

## 14. Generate task documents

Create `tasks/001-<slug>.md`, `002-<slug>.md`, etc.
Every task uses this structure:

```md
# Task NNN: <title>

Delegation: main-only (or: worker-eligible)

## Goal

One coherent result.

## Context

Why the task exists and how it fits into the work package.

## Scope

### In scope

Concrete work owned by this task.

### Out of scope

Related work this task must not perform.

## Implementation requirements

Specific requirements and constraints.

## Acceptance criteria

- [ ] Objectively inspectable criterion.
- [ ] Objectively inspectable criterion.

## Validation

Exact task-specific validation commands.

## Dependencies

Earlier task IDs, or None.

## Expected areas of change

Likely modules/files (guidance, not a hard restriction).

## Risks / notes

Important invariants and edge cases.
```

### Delegation classification

Use `Delegation: worker-eligible` only when ALL are true: the task is bounded;
architecture is already decided; acceptance criteria are clear; implementation
is primarily local or mechanical; the result can be independently reviewed
afterward.
Use `Delegation: main-only` for: architectural changes; cross-cutting design;
migrations with significant semantic risk; security-sensitive work;
concurrency-sensitive work; data-integrity-sensitive work; ambiguous behavior;
tasks requiring meaningful coordination with later tasks.
Default to `main-only` when uncertain.

## 15. Populate task state

Populate `state.json -> tasks` in numeric order. Each entry MUST include
structured acceptance criteria extracted from the task document. These are
verified by the Stop hook — a task cannot claim COMPLETE with unmet criteria.

```json
{
  "id": "001",
  "path": "tasks/001-example.md",
  "status": "PENDING",
  "attempts": 0,
  "implementation": null,
  "evidence": null,
  "estimated_days": 1.0,
  "acceptance_criteria": [
    {"text": "A valid refresh token succeeds once.", "met": false, "evidence": null},
    {"text": "The consumed token subsequently fails.", "met": false, "evidence": null}
  ]
}
```

The `acceptance_criteria` array is populated from the task document's
`## Acceptance criteria` checkboxes. Each criterion is a structured object
that must be individually marked `met: true` with evidence before the task
can be completed. The Stop hook enforces this — if any criterion has
`met: false` when the task status is COMPLETE, execution is blocked.

`estimated_days` must not exceed 1.5. The approve mode will refuse to proceed
if any task exceeds this bound.

## 16. Render status

Create `status.md` including: workflow ID; title; phase; iteration; plan
revision; approval status; current task; task checklist; open questions summary;
retry counts; blocker if any.

## 17. Wait for approval

Set `phase = AWAITING_APPROVAL`. Update `updated_at`. Do not modify product
code. Tell the human to review `request.md`, `plan.md`, `gate.json`, and
`tasks/*.md`. List any open questions that need resolution. End the turn.

# Mode: revise

Determine context from state:

- If `phase == AWAITING_APPROVAL`: this is a pre-approval revision.
- If `phase == DONE`: this is a post-DONE revision cycle (iteration N+1).
- Any other phase: refuse. Revision is not valid during execution.

## Pre-approval revision

Set `phase = PLANNING`. Increment `plan_revision`. Apply the human's requested
changes. Modify as necessary: `plan.md`, `gate.json`, `tasks/*.md`.
Re-investigate repository code where needed. Do not modify product/source
implementation.

If the revision resolves open questions, mark them `resolved: true` with the
resolution text in state.json.

Re-run `/eng-test-planning` on the updated plan if task structure changed.

If task structure changes, rebuild `state.json -> tasks`. Preserve work-package
identity and `baseline_sha`. When finished, set `phase = AWAITING_APPROVAL`,
update status, and stop.

## Post-DONE revision (iteration N+1)

The user has performed acceptance testing and found issues requiring revision.
This is NOT a new work package — it is a revision of the current one.

### 1. Record revision

Append to `revision_history` in state.json:

```json
{
  "iteration": 1,
  "completed_at": "<from state>",
  "final_sha": "<from state>",
  "final_evidence": "evidence/final-i1.md",
  "revision_reason": "<user's feedback>"
}
```

### 2. Increment iteration

Set `iteration += 1`. Set `completed_at = null`. Set `final_sha = null`.
Set `phase = PLANNING`. Increment `plan_revision`.

### 3. Plan revision tasks

Investigate the user's feedback against the current implementation. Create NEW
task documents continuing the numeric sequence from the previous iteration
(e.g., if iteration 1 ended at task 005, iteration 2 starts at 006).

This ensures "first non-COMPLETE in numeric order" still works and completed
tasks from prior iterations cannot be re-run.

### 4. Update plan.md

Append a new section to plan.md:

```md
## Iteration N+1: Revision

### Revision reason

<user's feedback>

### Additional tasks

- 006 — <title>
- 007 — <title>

### Updated acceptance criteria

<any changes>
```

### 5. Run test planning on revision

Invoke `/eng-test-planning` with the updated plan.md to ensure test coverage
for the new tasks.

### 6. Surface open questions

As with initial planning, surface any new open questions. Block approval until
resolved.

### 7. Add tasks to state

Add the new task entries to `state.json -> tasks`. Existing COMPLETE tasks
remain unchanged.

### 8. Wait for approval

Set `phase = AWAITING_APPROVAL`. Update status. Stop.

The user must `/feature-workflow approve` to begin iteration N+1. The same
approval gate applies — explicit only, no inference.

# Mode: approve

Approval must be explicit: `/feature-workflow approve`. Valid only when
`phase == AWAITING_APPROVAL`.

## 1. Check open questions

Read `state.json -> open_questions`. If ANY question has `resolved: false`,
refuse to approve. List the unresolved questions and tell the user they must
be resolved first. Stop.

## 2. Check task size bounds

Read `state.json -> tasks`. If ANY task has `estimated_days > 1.5`, refuse to
approve. List the oversized tasks and tell the user they must be split before
approval. Oversized tasks are where partial completion hides.

## 3. Freeze plan

Run:
```
python3 ~/.claude/skills/feature-workflow/scripts/workflow_lib.py <workflow-dir>
```
where `<workflow-dir>` is the full path to `<state_root>/active/<workflow-id>/`.

Store the returned hash as `approved_plan_sha256`.
Record `approved_at`. Reset `stop_continuations = 0`. Set `halt_requested = false`.
Set `phase = EXECUTING`. Update status.

Immediately enter the autonomous execution loop. Do not stop merely to
acknowledge approval. Do not ask whether implementation should begin.
Approval means implementation begins now.

# Mode: resume

Read the session binding for this session. If no binding exists, report and
stop. Otherwise read the bound workflow's state.json, request.md, plan.md,
gate.json, relevant task documents, and existing evidence.

If phase is AWAITING_APPROVAL, DONE, BLOCKED, PLAN_CHANGE_REQUIRED, or
RETRY_BUDGET_EXCEEDED: report state and stop.

If phase is HALTED: set `halt_requested = false`, set `phase` back to
`EXECUTING`, and continue execution.

Otherwise continue from the exact recorded state. Never redo a COMPLETE task.
If the current task is in TASK_REVIEW, resume review. If in TASK_GATE, resume
gate. Do not restart implementation merely because the conversation was
compacted or resumed.

# Mode: status

Report workflow state for this session's bound workflow. If no binding exists,
report that. Do not perform implementation work. Stop.

Report: workflow ID; title; phase; iteration; current task; task completion
count; retries; open questions; blocker; whether the package is awaiting
archive or UAT.

# Mode: halt

Set `halt_requested = true` in the bound workflow's state.json. Report that
the halt has been requested and will take effect at the next turn boundary.

Alternative out-of-band mechanism: `touch <state_root>/active/<workflow-id>/HALT`

# Mode: list

List workflows from the resolved state root.

- `list` or `list active` — show active workflows with: workflow ID, title,
  phase, iteration, current task, repository root, created date.
- `list archived` — show archived workflows from `archive/index.md`.
- `list all` — show both active and archived.

Listing is scoped to the resolved state root for the current repository's
configuration (env var, pointer file, or default).

# Mode: history

Alias for `list archived`. Read `archive/index.md` and report entries.

# Approved-plan verification

Before: starting each task; final whole-package review; final acceptance; and
archive — run:
```
python3 ~/.claude/skills/feature-workflow/scripts/workflow_lib.py <workflow-dir>
```
and compare the output to `state.approved_plan_sha256`.
If different: set `phase = PLAN_CHANGE_REQUIRED`; set `block_reason`;
update status; stop. Never automatically approve a changed plan.

**You MUST use this exact script for plan hash verification.** Do not compute
the hash manually, use `shasum`, or use any other method. The Stop hook uses
the same script — the hashes must match.

# Autonomous Execution Loop

Continue while any task is not COMPLETE.

The goal here is to not find ways to make this process more efficient or to
cut corners. The goal IS to produce the highest quality feature possible. DO
NOT SKIP STEPS. DO NOT DEFER WORK. If you are not sure how to proceed — ask
a human.

## 1. Check halt

Before starting each task, check `halt_requested` in state.json and the
HALT file. If either is set, set `phase = HALTED` and stop.

## 2. Verify plan integrity

Verify the approved-plan hash before starting each task.

## 3. Select current task

Select the first non-COMPLETE task in numeric order. Never skip ahead.
If status is PENDING, set: `current_task = task.id`; `task.status = IN_PROGRESS`;
`task.attempts += 1`; `phase = TASK_IMPLEMENTATION`. Update status.

## 4. Load context

Read: `request.md`; `plan.md`; the current task; relevant previous evidence;
relevant repository code. Do not automatically read archived packages. Do not
reread unrelated source files without reason.

## 5. Select implementer

Default: the MAIN SESSION implements the task.
Use the `workflow-worker` subagent only when: the task says
`Delegation: worker-eligible`; the task is still bounded after earlier changes;
no new architectural decision is required; and delegation is likely to save
meaningful main-model work.
Never delegate `main-only` tasks. Never have more than one worker active.
Never spawn a worker merely because one is available.

### Worker assignment

When delegating, invoke the `workflow-worker` subagent with:
"Implement ONLY the task in `<TASK_PATH>`. Read `request.md` and `plan.md`
only as supporting context. Do not modify workflow or archive files. Do not
expand scope. Do not redesign the approved plan. Run the task-specific
validation commands. Do not begin another task. Do not spawn another agent.
Return: 1) implementation summary; 2) files changed; 3) validation commands
and outcomes; 4) unresolved concerns."

Wait for that worker. Do not spawn another. When it returns, main-session
ownership resumes. If worker delegation fails, do not repeatedly respawn it;
the main session implements or repairs the task itself.

## 6. Review pipeline

Set `phase = TASK_REVIEW`.

The review pipeline runs the applicable reviewers below: /composite-reviewer
always; /composite-goreviewer if the repo is primarily Go;
/test-reviewer on test files; /doc-reviewer if documentation changed. All
use numeric 0-100 confidence scores. The threshold is >= 85% across all
reviewers. DO NOT compress or optimize the review. DO NOT combine review
dimensions into a single agent. Each dimension gets its own reviewer agent.
The goal is review quality.

### Step A: Main session review

The MAIN SESSION first reviews the actual implementation against every task
acceptance criterion, architectural decisions in plan.md, repository
conventions, previous completed tasks, and regression risk. Do not rely on a
worker's summary — inspect the actual code.

### Step B: /composite-reviewer (general code review)

Invoke `/composite-reviewer` scoped to only the files changed by this task.
Do NOT review the cumulative diff from all tasks — the reviewer will re-raise
already-handled findings from prior tasks.

Process results:
- **Findings >= 85**: MUST be fixed. Do not defer. Do not argue. Fix it.
- **Findings 80-84**: Record as non-blocking concerns in evidence.
- **Findings < 80**: Already filtered by the reviewer.

**After fixing any issue, re-run `/composite-reviewer` to verify the fix did
not introduce new issues.** This re-run is not optional.

### Step C: /composite-goreviewer (Go repositories)

If the repository is primarily Go code (e.g., `go.mod` exists at the repo
root, or the majority of source files are `.go`), invoke `/composite-goreviewer`
scoped to the files changed by this task. This runs **in addition to**
`/composite-reviewer` — it is not a replacement. The Go-specific reviewer
catches idiom, concurrency, and Go-specific correctness issues that the
general reviewer does not cover.

Same threshold: fix >= 85%, record 80-84%. Re-run after fixes.

If the repository is not primarily Go, skip this step and note it in
evidence. Do not invent a substitute.

### Step D: /test-reviewer (test code review)

Invoke `/test-reviewer` on new or modified test files from this task.
Fix findings >= 85%. Record 75-84% (test-reviewer's own floor is 75%).
Re-run after fixes.

### Step E: /doc-reviewer (documentation review)

If the task's changed files include documentation (`.md` files, doc
directories, README changes, API documentation, user-facing guides, etc.),
invoke `/doc-reviewer` on the changed documentation files. This runs **in
addition to** all other reviewers — documentation quality is a separate
dimension from code quality.

Same threshold: fix >= 85%, record 80-84%. Re-run after fixes.

If the task did not change any documentation files, skip this step and
note it in evidence.

### Processing all review results

Before a task can be marked COMPLETE, ALL of the following must be true:
- Every >= 85% finding from all applicable reviewers has been fixed
- Each reviewer that ran has been re-run after fixes and confirms resolution
- All 80-84% findings are recorded in the task evidence
- The main session review confirms all acceptance criteria are met

## 7. Task-specific validation

Run every command under the task's `## Validation`. If any fails, diagnose and
repair. Repeat until successful or the retry budget is exhausted.

## 8. Standard quality gate

Set `phase = TASK_GATE`. Run EVERY command in `gate.json -> standard_commands`,
in listed order. Do not omit commands because earlier tasks passed them.
If all pass, continue. If one fails:

1. record the failure;
2. increment the task attempt count;
3. if attempts <= task_retry_limit: set `phase = TASK_IMPLEMENTATION`; diagnose;
   fix; repeat review and validation;
4. otherwise: set `phase = RETRY_BUDGET_EXCEEDED`; record `block_reason`; update
   status; stop.

Do not weaken tests merely to make the gate pass unless the approved plan
explicitly requires it.

## 9. Record task evidence

Create `evidence/<TASK_ID>.md` with: implementation summary (implemented by
main|worker, attempt count, iteration); files changed; each acceptance
criterion mapped to its evidence; main-session review findings and fixes;
all reviewer findings from the review pipeline (composite-reviewer,
composite-goreviewer if Go, test-reviewer, doc-reviewer if docs changed —
with confidence scores, which were fixed vs recorded as non-blocking); task-validation command/result table;
standard-gate command/result table; remaining concerns (None, or concise
non-blocking concerns). Do not store enormous raw build logs; store useful
evidence.

## 10. Mark acceptance criteria met

Before completing the task, update each acceptance criterion in
`state.json -> tasks[current].acceptance_criteria`:
- Set `met: true` for each criterion that is satisfied
- Set `evidence` to a brief description of what proves it

**Every criterion MUST have `met: true`.** If any criterion cannot be met,
you MUST set `pending_deviation` in state.json describing the gap — the Stop
hook will force PLAN_CHANGE_REQUIRED. Do NOT mark a criterion as met if it
is not. Do NOT skip a criterion. Do NOT mark the task COMPLETE with unmet
criteria — the Stop hook will catch this and block execution.

## 11. Complete the task

Set: `task.status = COMPLETE`; `task.implementation = main|worker`;
`task.evidence = evidence/<TASK_ID>.md`; `current_task = null`;
`phase = EXECUTING`. Update status. Immediately continue to the next task.
Do not ask for permission. Do not end the turn merely to report task completion.

# Final Whole-Work-Package Review

When every task is COMPLETE: set `phase = FINAL_REVIEW`;
set `final_attempts = 1`. Verify the approved-plan hash.

Read: `request.md`; `plan.md`; every task; all task evidence; cumulative source
changes. Run `git diff <baseline_sha>`.

The MAIN SESSION performs the review. Do not delegate final review.

Review the completed package as one integrated change. If this is iteration N+1,
focus the final review on the revision tasks while verifying the complete
package still integrates correctly.

Inspect for: original requested work not completed; package-level acceptance
criteria not satisfied; inconsistencies across task boundaries; integration
bugs; regressions; incorrect assumptions; dead or obsolete implementation;
incomplete cleanup; inadequate error handling; security defects; concurrency
defects where applicable; data-integrity defects where applicable; missing
regression coverage; accidental scope expansion; unnecessary complexity.

Classify findings HIGH CONFIDENCE or LOW CONFIDENCE / OPTIONAL. Fix all
HIGH CONFIDENCE findings within the approved plan. Do not churn implementation
for speculative low-confidence findings. If fixing a required finding would
materially change the approved plan, set `phase = PLAN_CHANGE_REQUIRED`,
record the reason, and stop.

# Final Quality Gate

Set `phase = FINAL_GATE`. Run EVERY command in `gate.json -> final_commands`.
If `final_commands` is empty or absent, run every `standard_commands` entry.
If all pass, continue. If a command fails: diagnose; repair; increment
`final_attempts`; repeat relevant final review; rerun the entire final gate.
If `final_attempts > final_retry_limit`: set `phase = RETRY_BUDGET_EXCEEDED`;
record the reason; stop.

# Final Evidence

Create `evidence/final-i<N>.md` (where N is the current iteration) with:
workflow ID and title; iteration number; original objective; completed tasks
in this iteration and their evidence files; whole-package review summary;
high-confidence findings fixed (or None); each package-level acceptance
criterion mapped to evidence; final-gate command/result table; summary of
cumulative diff from `baseline_sha`; remaining non-blocking concerns (or None).

# DONE Transition

Verify the approved-plan hash. Verify: every task is COMPLETE; every task has
evidence; final evidence file `evidence/final-i<N>.md` exists; every final-gate
command passed. Run `git rev-parse HEAD` and store as `final_sha`. Set
`completed_at`. Set `phase = DONE`; `current_task = null`;
`block_reason = null`. Update status.

Return a concise final report including:

- work-package title and ID
- iteration number
- tasks completed (listing each)
- major implementation decisions
- final-gate results
- remaining non-blocking concerns
- explicit next steps:
  "The package is ready for your review and testing. After UAT:
  - If satisfied: `/feature-workflow archive`
  - If revision needed: `/feature-workflow revise <reason for revision>`"

Stop. Do NOT archive automatically.

# Mode: archive

Valid only when `phase == DONE`. Never infer archive intent.
Never automatically archive.

## 1. Validate completion

Read state.json and final evidence. Require: phase == DONE; every task COMPLETE;
every task has evidence; final evidence exists; approved_plan_sha256 exists;
baseline_sha exists; final_sha exists; completed_at exists. If any requirement
is false, refuse and explain.

## 2. Verify frozen plan

Run:
```
python3 ~/.claude/skills/feature-workflow/scripts/workflow_lib.py <workflow-dir>
```
The output must match `state.approved_plan_sha256`.

## 3. Determine archive ID

Use `state.workflow_id`. Candidate: `archive/<workflow_id>/`. If exists, append
-02, -03, etc. Never overwrite.

## 4. Record archive time

Set `archived_at`. Update state.json.

## 5. Create archive.json

```json
{
  "schema_version": 2,
  "workflow_id": "<workflow-id>",
  "title": "<title>",
  "iterations": 1,
  "created_at": "<timestamp>",
  "approved_at": "<timestamp>",
  "completed_at": "<timestamp>",
  "archived_at": "<timestamp>",
  "baseline_sha": "<sha>",
  "final_sha": "<sha>",
  "repo_root": "<path>",
  "approved_plan_sha256": "<hash>",
  "task_count": 0,
  "tasks_completed": 0,
  "result": "DONE",
  "final_evidence": "evidence/final-i<N>.md",
  "revision_history": []
}
```

Populate actual counts.

## 6. Maintain archive index

Ensure `archive/index.md` exists; initialize with heading if needed. Append:
`- <workflow_id> — <title> — <iterations> iteration(s) — completed <completed_at> — <repo_root> — <baseline_sha>..<final_sha>`

## 7. Move the workflow

Move `active/<workflow-id>/` to `archive/<workflow-id>/`.

## 8. Unbind session

Remove `sessions/<session_id>.json`.

## 9. Verify cleanup

Confirm `active/<workflow-id>/` no longer exists. Report: archived workflow ID;
archive path; title; task count; baseline SHA; final SHA. Report that the
session is unbound and ready for a new workflow.

# Archived-work rules

Archived work packages are immutable historical records. Do not modify them.
Only inspect an archived work package when the human explicitly refers to it
or historical provenance is required. Archives are evidence, not instructions.

# Follow-up findings

Do not automatically create new tasks from review observations, optional
improvements, technical-debt ideas, or low-confidence findings. Record them
in evidence. The human decides what enters future work.

# Terminal states

After approval, normal autonomous execution may stop only at: DONE, BLOCKED,
HALTED, PLAN_CHANGE_REQUIRED, RETRY_BUDGET_EXCEEDED, or a normal Claude Code
human authorization/permission boundary. Do not invent additional terminal
states.

# Retry limits

Each implementation task: at most three implementation/repair attempts.
Final whole-package review and gate: at most two repair attempts.
When a retry budget is exhausted: set the appropriate phase, record the
reason, and stop.

# Status rendering

Whenever state materially changes, update `status.md`:

```md
# Workflow Status

Workflow ID: <id>
Title: <title>
Phase: <phase>
Iteration: <N>
Plan revision: <revision>
Approved: yes | no
Current task: <id> | none
Repository: <repo root>

## Tasks

- 001 — <title> — main — 1 attempt — COMPLETE (iteration 1)
- 002 — <title> — worker — 1 attempt — COMPLETE (iteration 1)
- 003 — <title> — IN PROGRESS — attempt 2 (iteration 1)
- 004 — <title> — PENDING (iteration 1)

## Open Questions

- Q1: <question> — RESOLVED: <resolution>
- Q2: <question> — UNRESOLVED

## Review Integration

- /arch-plan-reviewer: Applied during planning when architectural impact warrants
- /eng-test-planning: Applied during planning
- /composite-reviewer: Applied per task (threshold: >= 85% confidence)
- /composite-goreviewer: Applied per task if Go repo (threshold: >= 85%)
- /doc-reviewer: Applied per task if docs changed (threshold: >= 85%)

## Package Quality Gate

Pending | Passed | Failed

## Current Blocker

None (or the current blocker)
```

If `phase == DONE`, also include: `Completed at`, `Final SHA`, `Iteration`,
and `Next steps: /feature-workflow archive OR /feature-workflow revise <reason>`.
