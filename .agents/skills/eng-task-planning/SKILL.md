---
name: eng-task-planning
description: Convert an approved engineering plan, design, and test plan into multiple implementation task documents plus a dependency-aware task overview. Use for detailed task decomposition, estimates, critical-path analysis, parallel work planning, and updating an existing feature task set. Supports direct requests and delegated/chained workflows.
---

# Engineering Task Planning

Turn approved feature documentation into small, actionable task documents that a team can implement safely and in parallel.

## Inputs

Accept:

- Engineering research/implementation plan path.
- Engineering design path and approval state.
- Test plan, usually appended to the engineering plan.
- Optional feature or task index path.
- Optional Jira/Confluence links and caller-provided requirements, decisions, estimates, naming, or output directory.

When given an index, use it to locate the current planning documents and task directory. When delegated, honor caller-provided paths, decisions, sequencing constraints, and output conventions. Do not repeat answered questions.

Default output is a `tasks/` directory beside the feature documentation. Use `<feature-name>-task-overview.md` plus numbered task documents named `<NN>-<feature-area>-tasks.md`.

## Requirements and Skill Boundaries

- Create task plans; do not implement code.
- Require an approved design for decisions that materially affect task boundaries. If the design is draft, return `approval-needed` unless the caller explicitly authorizes provisional planning.
- Create multiple focused task documents. Never put the entire implementation into one monolithic document.
- Keep each implementable task between 0.5 and 3.0 human-developer days, estimated in 0.5-day increments. Combine smaller work; split larger work.
- Include implementation and its directly related unit tests in the same task estimate. Separate only genuinely independent integration, verification, documentation, or infrastructure work.
- Make every dependency explicit and acyclic. Do not claim parallelism when tasks modify the same contract or files without coordination.
- Optimize for useful parallel work by three or more developers when the feature supports it; do not invent artificial lanes.
- Trace task acceptance criteria to the approved plan, design, test plan, or source requirement.
- Verify affected paths and symbols in the current codebase.
- Preserve existing task IDs and links when extending an existing plan unless renumbering is explicitly requested.
- Update existing task indexes and overview documents when present.
- Follow `AGENTS.md`; use `CLAUDE.md` only as legacy repository guidance when relevant.
- A delegated invocation must return structured completion, approval-needed, or blocker status.

## Core Skill Process

### 1. Load authoritative context

Read the engineering plan, approved design, appended test plan, feature index, and existing task documents. If Jira or Confluence links contain newer requirements or decisions, use the available Atlassian connector to check them and report any drift.

Extract requirements, acceptance criteria, design decisions, implementation sequence, file impact, test cases, risks, gaps, and dependencies.

### 2. Verify the current codebase

Confirm affected files, packages, interfaces, migrations, APIs, and existing tests still exist and match the documents. Identify natural boundaries around modules, contracts, schemas, integration points, and independently testable behavior.

### 3. Build a dependency graph

Define tasks in this general order where applicable:

1. Contracts, schemas, migrations, and shared foundations.
2. Independent core components.
3. Integration and end-to-end wiring.
4. Cross-cutting validation, documentation, and release work.

For each task record prerequisites, dependents, parallel peers, files, acceptance criteria, test work, and estimate. Detect cycles and file/contention risks. Mark the critical path.

### 4. Group tasks into documents

Group closely related tasks or tasks sharing one implementation context. Each document should be independently assignable and contain enough context for `$task-worker` (or an equivalent invocation mechanism) to execute without rediscovering the feature.

Use sequential two-digit filenames. When updating existing tasks, add or revise the minimum necessary documents and preserve stable references.

### 5. Create the overview

Create or update a single overview that lists every task document, dependency order, parallel lanes, critical path, risks, and open questions. Ensure estimates in individual documents, tables, and totals agree.

### 6. Reconcile indexes and validate

If `tasks/index.md` exists, update it with every task document and the overview. If the feature root index contains a tasks row, update only that row unless an orchestrator has explicitly reserved root-index reconciliation for itself.

Validate:

- No task exceeds 3.0 days or falls below 0.5 days.
- Every requirement and planned test is owned by at least one task.
- Dependencies are explicit, valid, and acyclic.
- Parallel groups are plausible.
- Critical-path and total estimates are consistent.
- Existing task links and identifiers remain valid.

If research is incomplete, mark affected work `Pending Research`, explain its dependency, and return `partial` or `approval-needed`. Do not turn unknown design work into fake implementation certainty.

## Output Formatting

The task directory should resemble:

```text
tasks/
├── index.md                         # update when present or required by the scaffold
├── <feature-name>-task-overview.md
├── 01-<feature-area>-tasks.md
├── 02-<feature-area>-tasks.md
└── ...
```

Use this structure for each task document:

```markdown
# Task Plan: [Feature Area]

**Planning Date:** [Date]
**Based On:** [Engineering plan and design links]
**Source Issues:** [Jira issues or None]
**Total Estimated Effort:** [Sum] days
**Recommended Team Size:** [Number]

## Executive Summary

[Scope, approach, and relationship to other task documents]

**Critical Path Contribution:** [Duration and dependencies]

## Epic Structure

### Epic: [Feature Name]

**Description:** [Brief description]

**Acceptance Criteria:**

- [ ] [Sourced criterion]

## Task Phases

### Phase 1: [Phase Name]

| Task ID | Task Name | Estimate | Dependencies | Parallel Group |
| --- | --- | --- | --- | --- |
| T1.1 | [Task] | X.X days | None | A |

## Detailed Task Descriptions

### T1.1: [Task Name]

**Estimate:** X.X days

**Dependencies:** None

**Parallel With:** [IDs or None]

**Assignable After:** [Condition]

**Requirement/Test References:** [Requirement IDs and test-plan cases]

**Description:**

[Concrete implementation scope]

**Acceptance Criteria:**

- [ ] [Specific, testable result]
- [ ] Focused tests pass.

**Files Likely Affected:**

- `path/to/file.go` - [Change]

**Verification:**

- [Focused build, lint, test, or manual verification command/behavior]

**Technical Notes:**

[Important design constraints and non-goals]
```

Use this structure for the overview:

````markdown
# Task Plan Overview: [Feature Name]

**Planning Date:** [Date]
**Based On:** [Engineering plan]
**Design:** [Approved design]
**Source Issues:** [Jira issues or None]
**Total Estimated Effort:** [Sum] days
**Critical Path Duration:** [Minimum duration]
**Recommended Team Size:** [Number]
**Realistic Duration:** [Duration with recommended team]

## Task Documents

| Document | Scope | Tasks | Effort |
| --- | --- | --- | --- |
| [01-area-tasks.md](./01-area-tasks.md) | [Scope] | T1.1-T1.N | X.X days |

## Parallel Work Visualization

```text
Week 1                         Week 2
Dev A: T1.1 ────────────────► T3.1
Dev B: T1.2 ──► T2.1 ──────► T3.1
Dev C: T1.3 ──► T2.2 ──────► T4.1
```

Arrows show dependency flow; vertical alignment shows parallel work.

## Dependency Graph

| Task | Blocked By | Blocks | Parallel With |
| --- | --- | --- | --- |
| T1.1 | None | T2.1 | T1.2 |

## Risk Assessment

### High-Risk Tasks

| Task | Risk | Mitigation |
| --- | --- | --- |
| T2.1 | [Risk] | [Mitigation] |

### Dependency Bottlenecks

| Task | Blocks | Recommendation |
| --- | --- | --- |
| T1.1 | T2.1, T2.2 | [Recommendation] |

## Requirement and Test Coverage

| Requirement / Planned Test | Owning Task(s) | Status |
| --- | --- | --- |
| [Reference] | [Task IDs] | Planned / Pending Research |

## Open Questions

1. **[Question]** - Affects: [Task IDs]. Owner/resolution: [Details].
````

Report to the user or caller with:

- `Status`: `complete`, `approval-needed`, `partial`, or `blocked`.
- `Outputs`: overview, task documents, and indexes changed.
- `Plan summary`: task count, effort, critical path, team size, and parallel lanes.
- `Coverage`: requirements and test-plan items mapped.
- `Open questions`: pending research or decisions and affected tasks.
- `Problems`: conflicts, stale/invalid paths, estimate uncertainty, or unavailable sources; use `None` when empty.
- `Next skill`: `$task-worker` for execution, usually starting with critical-path foundation tasks.

For a blocker, state the exact missing approval, source, or decision; list completed planning work; and name the minimum action needed to continue. Do not implement tasks as a workaround.
