---
name: task-worker
description: Implement one task from an engineering task plan, load its indexed project context, verify the changes through code and test review plus repository-native checks, and update task tracking. Use for direct task execution or as a delegated worker in a chained engineering workflow.
---

# Task Worker

## Inputs

- Project or task index path.
- Task document path, filename, or task ID.
- Optional caller-provided project context, constraints, prior task results, or verification commands.

Resolve relative documents through the supplied indexes. A root feature index or task index is acceptable. Ask only when the target task or required source of truth cannot be identified safely.

## Requirements and Skill Boundaries

- Treat the task document's acceptance criteria, feature plan, and design as the source of truth.
- Implement only the selected task. Do not absorb later tasks or unrelated cleanup.
- Honor completed prerequisite work and caller-provided decisions.
- Plan briefly, then continue without waiting for plan approval unless a material design choice, missing authority, or destructive action requires the user.
- Add or update tests with the implementation when the behavior warrants automated coverage.
- Prefer `AGENTS.md`, repository wrappers, CI commands, and documented tooling; use `CLAUDE.md` only as legacy repository guidance.
- Do not mark acceptance criteria or the task complete unless verified.
- Support delegated execution: return concise status, changed artifacts, review/check results, and blockers to the caller.

## Core Skill Process

### 1. Resolve and load context

Read in this order:

1. selected task document: objective, acceptance criteria, files, implementation notes, dependencies;
2. task index: phase, prerequisites, later work, and tracking entry;
3. implementation plan/specification: requirements, boundaries, constraints, and gaps;
4. design document: architecture, patterns, interfaces, and integration points.

Use index links to discover documents. If a prerequisite is incomplete and blocks safe implementation, stop and report it.

### 2. Plan the task

Record:

- objective;
- files to create or modify;
- implementation order;
- test strategy;
- risk areas and assumptions.

Proceed directly when the plan stays within the approved task.

### 3. Implement

- Match surrounding code and project instructions.
- Keep changes incremental and scoped.
- Check each acceptance criterion while working.
- Preserve existing user changes and avoid unrelated formatting or refactors.
- Test focused behavior during implementation when practical.

### 4. Review

Run independent reviews after implementation; they may run in parallel when available:

1. Invoke `comp-reviewomatic` in local mode over the implementation diff. Validate its findings, fix verified high-confidence issues, and re-review affected areas.
2. Invoke `eng-test-reviewer` over new or modified tests. Fix verified high-confidence issues and re-review affected tests.
3. Invoke `doc-reviewomatic` in local mode when user-facing or engineering documentation changed. Fix verified high-confidence issues and re-review affected documents.

Record unverified, low-confidence, or out-of-scope findings without changing code solely to satisfy them.

### 5. Verify

Discover repository commands in this order:

1. `AGENTS.md` and current project instructions;
2. CI workflows;
3. README/CONTRIBUTING;
4. Make, Mage, Just, Task, package scripts, or other wrappers;
5. language defaults.

Run the required lint, build, and test phases. Re-run a failed phase after fixing in-scope causes. Do not silently skip unavailable checks; state the lost coverage. Distinguish failures introduced by this task from confirmed pre-existing failures.

### 6. Update tracking

Check off only acceptance criteria demonstrated by the implementation and verification. Mark the task complete in its index only when every required criterion passes. If documentation changed concurrently, re-read before patching to preserve other updates.

### 7. Finish or stop

Complete when the scoped implementation, required reviews, checks, and tracking are done. Stop with a blocker when required inputs, permissions, dependencies, or unresolved design choices prevent safe progress.

## Output Formatting

```markdown
# Task Completion Report: [Task ID — Name]

## Implementation Summary

[Outcome]

## Acceptance Criteria

- [x] [verified criterion]
- [ ] [unmet criterion] — [reason]

## Completion Results

| Step | Status | Details |
|------|--------|---------|
| Code review | PASS/FAIL/SKIPPED | [result] |
| Test review | PASS/FAIL/SKIPPED | [result] |
| Documentation review | PASS/FAIL/SKIPPED | [result] |
| Lint | PASS/FAIL/SKIPPED | [command/result] |
| Build | PASS/FAIL/SKIPPED | [command/result] |
| Tests | PASS/FAIL/SKIPPED | [command/result] |
| Task tracking | UPDATED/NOT UPDATED | [reason] |

## Deferred Findings

- [finding, confidence, and reason deferred]

## Files Changed

- `[path]` — [change]

## Problems and Blockers

- [problem, impact, evidence, and required next step]
```

Never claim completion when a required criterion or check is unresolved. A skipped check is incomplete verification, not a pass.
