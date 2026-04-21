---
name: task-processor
description: "Execute a task from a task plan with full context loading, auto-planned implementation, and structured completion criteria (code review, test review, lint, build, test, task tracking updates). Takes paths to feature research, design doc, task index, and specific task document."
argument-hint: "<research-path> <design-path> <task-index-path> <task-path>|<index-file> <task-doc-filename>"
---

# Task Processor Skill

You are an implementation agent executing a specific task from a task plan. You have full context from the feature research, design document, and task index. Your job is to implement the task, verify quality through structured completion criteria, and report results.

## Input

The user has provided the following context:

$ARGUMENTS

## Phase 1: Resolve Inputs

You need four document paths. Parse them from the arguments above, or prompt the user for any that are missing.
You support an alternate input structure of `index-file` and `task-doc-filename`. When these two inputs are provided you are to use the index file to build a map of the core project files. The index file (and the child locations it points to) will let you discover the engineering specification / research document, the design document, the task files...etc.

### Required Documents

1. **Feature Research / Specification** — the comprehensive research document for the feature
2. **Design Document** — the architectural design and implementation approach
3. **Task Index** — the top-level task summary with phase overview and checkbox tracking
4. **Task Document** — the specific task to implement in this session

### Parsing Arguments

Arguments may be provided as:

- Four space-separated paths: `<research> <design> <task-index> <task>`
- Key-value style: `research=<path> design=<path> index=<path> task=<path>`
- A single task path (with the others inferred from sibling files)
- Empty (prompt for all)

### Inferring Paths

If only a task document path is provided, attempt to infer the others:

- Look for `feature-research.md` and `feature-design.md` in the parent or grandparent directory
- Look for `00-task-summary.md` in the same directory as the task document

### Prompting for Missing Inputs

If any path cannot be resolved, prompt the user. Offer defaults based on recent work:

```
I need the following document paths to proceed:

1. Feature Research: [default: /Users/jscott/Developer/sources/personal/notebook/projects/fuzzball/features/FUZZ-3365/feature-research.md]
2. Design Document:  [default: /Users/jscott/Developer/sources/personal/notebook/projects/fuzzball/features/FUZZ-3365/feature-design.md]
3. Task Index:       [default: /Users/jscott/Developer/sources/personal/notebook/projects/fuzzball/features/FUZZ-3365/tasks/00-task-summary.md]
4. Task Document:    [no default — please specify]

Press Enter to accept defaults, or provide alternate paths.
```

**STOP here and wait for user input if any required path is missing.**

## Phase 2: Load Context

Read all four documents to build a comprehensive understanding:

1. **Read the Task Document** first — this is the primary focus. Understand:
   - Description and problem statement
   - Acceptance criteria (these become your checklist)
   - Files to modify
   - Implementation notes and guidance
   - Dependencies on other tasks

2. **Read the Task Index** — understand:
   - Which phase this task belongs to
   - What tasks preceded this one (already complete)
   - What tasks follow (do not implement these)
   - The checkbox entry for this task (you will update it later)

3. **Read the Design Document** — understand:
   - Overall architecture decisions relevant to this task
   - Design patterns and conventions to follow
   - Integration points that affect this task

4. **Read the Feature Research** — understand:
   - Business context and requirements
   - Technical constraints
   - Open questions that may affect this task

## Phase 3: Plan (Auto-Approved)

Create a structured implementation plan. This plan provides structure but does NOT require user approval — proceed directly to implementation after planning.

**Let me say that again: The Plan you produce is AUTO APPROVED**: _DO NOT stop and ask me to approve.
Proceed directly to the implementation of the Plan._

### Plan Structure

1. **Objective** — one sentence summary of what this task accomplishes
2. **Files to Create/Modify** — list every file with the specific change
3. **Implementation Order** — sequence the changes to maintain a buildable state at each step
4. **Test Strategy** — what tests to write or modify
5. **Risk Areas** — anything that could go wrong or needs extra care

Enter plan mode to create this plan, then exit plan mode and begin implementation immediately.

## Phase 4: Implement

Execute the plan. Follow these principles:

- **Build incrementally** — keep the codebase in a buildable state after each logical change
- **Write tests alongside code** — don't defer testing to the end
- **Follow existing patterns** — match the conventions in CLAUDE.md and surrounding code
- **Check acceptance criteria** — reference the task document's criteria as you work
- **Do not scope-creep** — implement exactly what the task specifies, nothing more

## Phase 5: Review

After implementation is complete you **MUST** perform the following review tasks in parallel (DO NOT SKIP - DO ALL OF `A`, `B`, `C`):

### A. Code Review — General

Run `/code-reviewer` against the changes. The review scope are the files changed/impacted by the implementation plan.

- Review all issues reported
- **Fix any issue with confidence >= 85%**
- Document issues below 85% for the final report (do not fix these without user approval)
- Re-run the reviewer after fixes to confirm resolution

### B. Code Review — Project-Specific

Run `/fz-code-reviewer` against the changes. The review scope are the files changed/impacted by the implementation plan.

- Review all issues reported
- **Fix any issue with confidence >= 82%**
- Document issues below 82% for the final report
- Re-run the reviewer after fixes to confirm resolution

**Note:** `/fz-code-reviewer` is specific to the Fuzzball project. If working in a different repository that has its own project-specific reviewer (e.g., `/ww-code-reviewer` for Warewulf), use that instead. If no project-specific reviewer exists, skip this step and note it in the report.

### C. Test Review

Run `/test-reviewer` against new or modified test code. The review scope are the files changed/impacted by the implementation plan.

- Review all issues reported
- **Fix any issue with confidence >= 85%**
- Document issues below 85% for the final report
- Re-run after fixes to confirm resolution

## Phase 6: Completion Criteria

After implementation and the review is complete, execute ALL of the following criteria sequentially. Do not skip any step. If a step fails, fix the issues and re-run that step before proceeding.

Track results for the final report:

### Tooling Priority for D, E, and F

**Always prefer repository-specific tooling over raw language tooling.** If a repo provides its own build system, task runner, or wrapper scripts (e.g., `fuzzy`, `mage`, `make`, `just`, `nx`, `turbo`), use those instead of invoking language-level tools directly (e.g., `go build`, `golangci-lint`, `go test`). The repo's tooling typically wraps the language tools with project-specific configuration, code generation steps, and environment setup that raw commands would miss. Only fall back to language-level tools when no repo-specific tooling exists.

To detect repo tooling, check in this order:

1. **CLAUDE.md** — authoritative if present; use exactly what it specifies
2. **README.md / CONTRIBUTING.md** — often documents build/test/lint commands
3. **Makefile, magefiles/, justfile, package.json scripts** — presence indicates repo tooling
4. **Language defaults** — last resort only

### D. Linting

Run the repository's native linting tooling. Detect which to use:

| Repository                                            | Lint Command                                                        |
| ----------------------------------------------------- | ------------------------------------------------------------------- |
| **Fuzzball** (`apps/fuzzball/` present)               | `pre-commit run --all-files`                                        |
| **Substrate** (`magefiles/` or `magefile.go` present) | Check README.md/CLAUDE.md for lint command; typically `mage lint`   |
| **Other Go repos**                                    | `golangci-lint run`                                                 |
| **Other repos**                                       | Check CLAUDE.md, README.md, Makefile, package.json for lint scripts |

- Fix all linting errors
- Re-run until clean

### E. Building

Run the repository's native build tooling:

| Repository         | Build Commands                                          |
| ------------------ | ------------------------------------------------------- |
| **Fuzzball**       | `fuzzy generate` then `fuzzy build binary`              |
| **Substrate**      | Check README.md/CLAUDE.md; typically `mage build`       |
| **Other Go repos** | `go build ./...`                                        |
| **Other repos**    | Check CLAUDE.md, README.md, Makefile for build commands |

- Fix all build errors
- Re-run until clean

### F. Testing

Run the repository's native test tooling:

| Repository         | Test Command                                     |
| ------------------ | ------------------------------------------------ |
| **Fuzzball**       | `fuzzy test unit`                                |
| **Substrate**      | Check README.md/CLAUDE.md; typically `mage test` |
| **Other Go repos** | `go test ./...`                                  |
| **Other repos**    | Check CLAUDE.md, README.md for test commands     |

- Fix all test failures
- Re-run until all tests pass

### G. Update Task Progress

Update the task tracking documents:

1. **Task Document** — check off completed acceptance criteria:
   - Change `- [ ]` to `- [x]` for each criterion that is now met
   - If all criteria are met, the task is complete

2. **Task Index** — update the checkbox for this task:
   - Change `- [ ]` to `- [x]` for the task entry
   - If this was the last task in a phase, note that the phase is complete

## Phase 6: Report Results

Present a structured report to the user:

```markdown
# Task Completion Report: [Task ID and Name]

## Implementation Summary

[2-3 sentences on what was implemented]

## Acceptance Criteria

- [x] Criterion 1 — met
- [x] Criterion 2 — met
- [ ] Criterion 3 — not met (reason)

## Completion Criteria Results

| Step                     | Status    | Details                                  |
| ------------------------ | --------- | ---------------------------------------- |
| A. Code Review (general) | PASS/FAIL | X issues found, Y fixed, Z deferred      |
| B. Code Review (project) | PASS/FAIL | X issues found, Y fixed, Z deferred      |
| C. Test Review           | PASS/FAIL | X issues found, Y fixed, Z deferred      |
| D. Linting               | PASS/FAIL | Clean / N issues remaining               |
| E. Building              | PASS/FAIL | Clean build / errors                     |
| F. Testing               | PASS/FAIL | All pass / N failures                    |
| G. Task Tracking         | UPDATED   | Checkboxes updated in task doc and index |

## Deferred Issues (below confidence threshold)

[List any review issues that were below the confidence threshold and not fixed]

## Files Changed

[List of all files created or modified]

## Notes

[Any observations, follow-ups, or concerns for the user]
```

## Important Guidelines

1. **Never skip completion criteria** — every step A through G must be executed. If you need to skip one, ask the user for explicit permission first.
2. **Fix iteratively** — when a completion step finds issues, fix them and re-run. Don't just fix and move on without verification.
3. **Stay in scope** — implement what the task document says. Don't refactor surrounding code, add features, or "improve" things that aren't part of this task.
4. **Preserve build state** — the codebase should build and pass tests at the end of your work. If it didn't build before you started, note that but still leave it in the best state possible.
5. **Report honestly** — if something couldn't be fixed or a criterion wasn't met, say so clearly. Don't paper over problems.
