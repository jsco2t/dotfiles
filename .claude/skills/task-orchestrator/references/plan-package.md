# The plan package

Stage 1 always produces the same package in the workflow directory. `orch validate`
enforces everything marked **(validated)**; the project-manager's plan audit judges the
rest. Nothing is copied into `state.json` by hand — the CLI reads task metadata and
acceptance criteria straight from the task documents.

## Directory layout

```
<location>/<YYYY-MM-DD>-<slug>/
  index.md              roadmap — GENERATED (orch render); start here
  status.md             detailed status — GENERATED
  request.md            the request, verbatim                         (frozen)
  plan.md               the plan                                      (frozen)
  architecture.md       architecture guidance, when warranted         (frozen)
  gate.json             workspaces + quality-gate commands            (frozen)
  decisions.md          clarifications + human decisions (append-only, via orch)
  tasks/
    index.md            every task by loop, with status — GENERATED
    T001-<slug>.md      one document per task                         (frozen)
  research/
    index.md            GENERATED
    NN-research-<topic>.<agent>.md
  reviews/plan/         plan-stage reports (plan reviews, PM audits) + briefs/
  runs/T001/
    index.md            the task's run history — GENERATED
    a1/                 attempt 1: NN-<stage>-r<round>.<agent>.md reports, briefs/,
                        changes.patch, changed-files.txt, scan.md, evidence/, gate/
    resolution.orchestrator.md   (only if the task exhausts its attempts)
  loops/L01/            loop entry/exit reports, loop diff, loop gate logs
  final/                whole-package diff, reviews, verification, acceptance
  .orch/                state.json + ledger.jsonl — CLI/hook-owned, never edited
```

"Frozen" files are hashed at approval; any later edit forces PLAN_CHANGE_REQUIRED and
hooks refuse edits to them.

## plan.md

Level-2 headings, in this order (numbering like `## 3. Approach` is fine). Every required
section must exist and be non-empty **(validated)**.

| Section | Contents |
| --- | --- |
| `## Objective` | The complete outcome, in the user's terms. |
| `## Requirements` | Every requirement as `- R1: <requirement>` — derived from the request (and tickets), one line each. This is the traceability anchor. **(validated: ≥1)** |
| `## Current state` | How things work today, **every claim with file:line (or URL/ticket) evidence** from research. "Probably in the validation logic" is not acceptable. |
| `## Approach` | The strategy, grounded in the evidence. Alternatives considered and why rejected. |
| `## Architectural decisions` | Decisions every task must respect (or a pointer to `architecture.md`). |
| `## Architectural review` | Whether architecture-reviewer (plan mode) ran, its key findings and how they were incorporated — or why it was skipped. An unrecorded skip is a planning gap. |
| `## Loop plan` | The orchestration loops: which tasks run in each loop and why that order. |
| `## Quality gate` | The gate.json commands per workspace and why they are the right ones. If a class of check does not exist in a repo, say so — never invent one. |
| `## Test strategy` | Required with code/test tasks **(validated)**. Includes the **test gap assessment**: what tests exist for the affected paths, what is missing, what would prove each requirement. |
| `## Test plan` | Required with code/test tasks **(validated)**. Appended by test-planner (`/eng-test-planning`). |
| `## Risks` | Material technical and delivery risks, with mitigations. |
| `## Out of scope` | Explicit boundaries. A requirement not covered by any task must be listed here by id (e.g. "R7 — deferred at the user's request"), where the human will see it at approval **(validated)**. |
| `## Final acceptance criteria` | Package-level criteria as `- [ ] FAC1: <objective criterion> — Verified by: <how>` **(validated: ≥1)**. |
| `## Open questions` | Every unresolved question as `- [ ] Q1: <question> — <context and impact>`. When answered: `- [x] Q1: ... — Resolution: <answer>` **(validated: approval blocked while any is unchecked; a checked one needs `Resolution:`)**. Write `None.` if there are none. |

### Planning rules (non-negotiable)

1. **Evidence for every claim** about existing code, systems, or documents: `path:line`,
   URL, ticket key, or command output. Unverifiable claims are open questions.
2. **Verify artifact naming conventions** (changelog entries, migrations, generated code,
   doc filenames, KB folder conventions) by reading the generator or recent examples. A
   wrong path in the plan propagates into the work.
3. **Objective acceptance criteria only.** Each is a boolean an independent verifier can
   check by running a command, a test, or reading a specific place. Never "works well",
   "is clean", "is improved".
4. **Test-forward for software.** Every behavior change has a test that is written first
   and fails first. Bugs indicate missing automated validation: every bug fix includes the
   regression test that reproduces it.
5. **Tasks ≤ 1.5 days** of estimated effort **(validated)**. Smaller tasks have clearer
   criteria and less room for partial completion.
6. **Trace every requirement** to at least one task (`requirements` in task metadata) or to
   `## Out of scope` **(validated)**. Never quietly shrink what the request asked for.
7. **Surface every open question.** Ambiguous requirements, conflicting patterns, missing
   external context, API design choices with multiple valid answers, performance/security/UX
   trade-offs, unstated compatibility needs. Unresolved questions force deviations later.

## architecture.md (when warranted)

Write it when the work creates or changes structure: a new subsystem, package, interface,
or abstraction layer; cross-layer changes; a new structural dependency; data-model/schema
changes with multiple consumers; changes spanning 3+ packages; or content architecture for
a large document set (information architecture, audience, navigation). Contents: context
and constraints, the decisions (each with rationale and rejected alternatives), component
/ document boundaries and responsibilities, data and control flow, invariants tasks must
preserve, and how the design will be tested.

## gate.json

```json
{
  "schema": 1,
  "workspaces": {
    "code": {
      "path": "/abs/path/to/repo",
      "standard": ["make lint", "go test ./..."],
      "final": ["make lint", "go test -race ./..."],
      "snapshot_exclude": ["coverage.out"],
      "notes": "Commands from CLAUDE.md / CI; why each is here."
    },
    "docs": {"path": "/abs/path/to/notebook/projects/x", "standard": [], "final": [], "notes": "..."}
  }
}
```

- `standard` runs for every task and at every loop close; `final` runs at the end (falls
  back to `standard`). Code/test workspaces must have standard commands **(validated)**.
- Discover commands in this order: CLAUDE.md → README/CONTRIBUTING → CI workflows →
  Makefile / magefiles / justfile / package scripts → language defaults (last resort).
  Mirror CI. Commands must pass at baseline; readiness proves it.
- Commands run under `bash -o pipefail`; do not pipe to `tail`/`head` to hide output.
- `snapshot_exclude`: build artifacts a gate run creates that are not ignored by
  `.gitignore` (the CLI refuses evidence when a run changes the workspace). Common
  artifacts (`__pycache__/`, `coverage.out`, `node_modules/`, …) are excluded by default.

## Task documents — `tasks/T###-<slug>.md`

File name `T` + 3+ digits + `-` + lowercase slug **(validated)**. Template:

````markdown
# T003 — <Title>

```json task
{
  "id": "T003",
  "title": "<Title>",
  "type": "code",
  "loop": 1,
  "depends_on": ["T001"],
  "requirements": ["R1", "R2"],
  "workspace": "code",
  "authors": ["test-author", "code-author"],
  "reviewers": ["code-reviewer", "test-reviewer", "architecture-reviewer"],
  "test_forward": "red-green",
  "test_forward_justification": "",
  "estimated_days": 1.0,
  "expected_paths": ["internal/scheduler/"],
  "validation": {
    "red_green": ["go test ./internal/scheduler/ -run '^TestBackpressure'"],
    "task": ["go test ./internal/scheduler/...", "go vet ./internal/scheduler/..."]
  },
  "parallel_safe": false,
  "external_writes": false
}
```

## Goal
One coherent result.

## Context
Why this task exists; how it fits the package; relevant evidence (file:line).

## Scope
### In scope
Concrete work owned by this task.
### Out of scope
Related work this task must not do.

## Requirements
Specific requirements and constraints (architecture decisions to respect, conventions,
compatibility).

## Acceptance criteria
- [ ] AC1: <objective, checkable criterion> — Verified by: test `TestBackpressure_RejectsWhenFull`
- [ ] AC2: <criterion> — Verified by: command `go test ./internal/scheduler/...` passes
- [ ] AC3: <criterion> — Verified by: inspection of `internal/scheduler/queue.go` (<what to look for>)

## Test plan
The specific tests to write first (code/test tasks — **validated**): name, what it asserts,
why it matters, test level. Copied/refined from plan.md's test plan.

## Validation
The commands above, and anything a verifier needs to reproduce them.

## Dependencies
Earlier task ids and what this task needs from them, or None.

## Risks / notes
Invariants, edge cases, traps.
````

### Metadata fields **(validated)**

| Field | Rule |
| --- | --- |
| `id` | Matches the file name. |
| `type` | One of the [task types](#task-types). |
| `loop` | ≥1; loops numbered contiguously from 1; dependencies never in a later loop. |
| `depends_on` | Existing task ids; no cycles. |
| `requirements` | ≥1 plan requirement id. |
| `workspace` | A workspace declared in gate.json. |
| `authors` | Exactly an allowed author sequence for the type. |
| `reviewers` | Must include the type's minimum reviewers; may add `architecture-reviewer`, `ux-reviewer`, `doc-reviewer`, `test-reviewer`. |
| `test_forward` | `red-green` (tests fail first, then pass), `characterization` (tests pin current behavior, pass before and after), or `not-applicable`. A code task may use `not-applicable` only with a real `test_forward_justification`. |
| `validation.red_green` | Required for red-green / characterization: the exact test commands the CLI runs for red/baseline/green evidence. Target the new tests specifically — a command that selects no tests proves nothing. |
| `validation.task` | Required for code/test tasks: the task-specific checks. |
| `estimated_days` | 0 < days ≤ 1.5. |
| `expected_paths` | Workspace-relative prefixes the task is expected to change. Changes outside them are flagged by the integrity scan for PM adjudication. Required for `parallel_safe`. |
| `parallel_safe` | Only for document-type tasks with disjoint `expected_paths`; lets them run concurrently in one loop. |
| `external_writes` | Only for `integration` tasks that write to Jira/Confluence/GitHub; forces dry-run → human confirmation → execute. |

Acceptance criteria use `- [ ] AC<n>: <text> — Verified by: <how>` (the `Verified by`
may also sit on the next indented line). Ids are unique within the task **(validated)**.

## Task types

| Type | Authors (in order) | Minimum reviewers | test_forward |
| --- | --- | --- | --- |
| `code` | test-author → code-author | code-reviewer, test-reviewer | red-green (default), characterization (refactors), not-applicable (justified) |
| `test` | test-author | test-reviewer, code-reviewer | characterization |
| `docs` | doc-author | doc-reviewer | not-applicable |
| `kb` | kb-author | doc-reviewer | not-applicable |
| `tutorial` | tutorial-author | doc-reviewer | not-applicable |
| `education` | education-author | doc-reviewer | not-applicable |
| `pm` | planning-author | doc-reviewer | not-applicable |
| `research` | codebase-researcher *or* domain-researcher → doc-author | doc-reviewer | not-applicable |
| `integration` | atlassian-liaison *or* github-liaison | — (PM stamp still required) | not-applicable |

Add `architecture-reviewer` to structurally significant code tasks and `ux-reviewer` to
tasks that change a UI, TUI, or CLI surface. Document gates for prose tasks belong in
gate.json (link checkers, markdown lint, `validate_tutorial.py`) when the workspace has them.

## Loop planning

- A loop is a set of tasks worked together, then closed with a loop-level gate and PM
  check before the next loop starts. Small work may be a single loop.
- Order loops so each builds on accepted work: foundations and interfaces first,
  consumers later, integration and documentation of the finished behavior last.
- Within a loop, writes are single-threaded unless tasks are `parallel_safe`. Put tasks
  that touch the same files in sequence via `depends_on`.
- Keep loops small enough that the loop-exit review can reason about the loop diff as a
  whole (roughly ≤ 6 tasks).

## Revisions

- **Before approval** (`/task-orchestrator revise ...`): the plan revision number
  increments; planning-author applies exactly the human's feedback; reviews and the PM
  audit re-run.
- **After DONE** (acceptance testing found issues): the iteration increments; accepted
  tasks and their documents stay untouched **(validated)**; new tasks continue the
  numbering and go in new loops.
- **After a deviation**: same as before approval; the interrupted task restarts with a new
  attempt once the revised plan is approved.
