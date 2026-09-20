---
name: new-bug
description: Research a reported bug and create a focused, test-forward fix plan with indexed task documents. Use for bug descriptions, issue links, or delegated planning where the output must include code-grounded root cause analysis and tests that close the escaped-validation gap.
---

# New Bug

## Inputs

- **Planning root:** an existing project/feature `index.md`, or a directory where a `bugs/` folder can be created.
- **Bug context:** issue links or keys, local files, and/or observed-versus-expected behavior.
- Optional repository path, output folder name, pre-supplied decisions, or research from a caller.

Require the planning root and bug context. If a path lacks an index, use or create `bugs/` beneath that path. Ask only when the root is ambiguous or required context cannot be discovered. In delegated execution, honor supplied paths and decisions and return artifacts, status, and blockers to the caller.

## Requirements and Skill Boundaries

- Produce only `index.md`, `plan.md`, `tasks/index.md`, task files, and required parent-index updates. Do not create research, design, review, follow-up, or verification trees; the bug plan is the design.
- Ground every code claim in specific file paths and current line numbers. Do not guess at root cause.
- The Test Gap Assessment and explicit test tasks are mandatory. Every fix task must have corresponding automated coverage.
- Prefer the smallest correct production change and thorough regression coverage. Investigate systemic variants and callers before calling a fix localized.
- Keep each task at 1.5 days or less. Put implementation before dependent test tasks, and require the relevant full test suite in the final test task.
- Preserve project rules, especially additive-only API/proto changes where applicable.
- Verify repository artifact naming and schemas from generators/configuration and recent examples before naming changelog entries, migrations, fixtures, or generated files. Never invent a path from memory.
- Use ISO 8601 timestamps with the local Mountain offset.
- Jira/Confluence enrichment is optional when the textual report and codebase are sufficient. Report unavailable access.

## Core Skill Process

### 1. Classify context and initialize

Classify an index as:

- **project-level:** its directory contains `prd.md` and/or `features/`;
- **feature-level:** its directory contains `plans/` and/or `tasks/` and no `prd.md`;
- **ambiguous:** neither pattern; ask for confirmation.

Extract the tracker ID and a three-to-five-word dash-case slug. Match sibling naming. Name the folder `{TRACKER-ID}-{short-description}` when an ID exists, otherwise `{short-description}`. Create:

```text
<parent-directory>/
└── bugs/
    └── <bug-folder-name>/
        ├── index.md
        ├── plan.md
        └── tasks/
            └── index.md
```

Use these initial schemas:

```markdown
# [Bug ID]: [Short Title] — Bug Fix Documentation

**Bug:** [Title]
**Jira:** [Link or "N/A"]
**Repository:** [Repository path]
**Created:** [ISO 8601 timestamp with Mountain offset]
**Status:** Planning

---

## Documentation Structure

| Document                   | Purpose                                                    |
| -------------------------- | ---------------------------------------------------------- |
| [`plan.md`](plan.md)       | Root cause analysis, fix strategy, and test gap assessment |
| [`tasks/`](tasks/index.md) | Implementation task breakdown with test-forward approach   |

---

## Summary

| Metric           | Value                             |
| ---------------- | --------------------------------- |
| Total Tasks      | [count]                           |
| Estimated Effort | [total] days                      |
| Root Cause       | [1-sentence summary]              |
| Test Gap         | [Missing automated validation]    |
```

```markdown
# Tasks Index

**Parent:** [../index.md](../index.md)
**Last Updated:** [ISO 8601 timestamp with Mountain offset]

---

## Documents

| Document | Description | Created |
| -------- | ----------- | ------- |

## Task Tracking

| Task ID | Task Name | Estimate | Dependencies | Completed |
| ------- | --------- | -------- | ------------ | --------- |
```

### 2. Research the bug

Gather the issue description, acceptance criteria, comments, linked specifications, duplicates, priority, and reproduction steps when accessible. Establish observed behavior, expected behavior, and reproduction conditions.

Trace the code from entry point to failure. Identify the exact incorrect condition, ordering, validation, state transition, or contract; shared patterns; dependent callers; and API/proto impact. Inspect existing tests to explain why they missed the problem and identify the precise tests and helpers that would have caught it. Determine the minimal fix, alternatives, trade-offs, and every affected file.

If root cause remains unknown, stop before writing a definitive plan. Report evidence, candidate paths, and the additional reproduction or domain context needed.

### 3. Write `plan.md`

Use this exact structure:

```markdown
# Bug Fix Plan: [Bug ID] — [Short Title]

**Bug:** [Jira link or title]
**Author:** [User name if known]
**Created:** [ISO 8601 timestamp with Mountain offset]
**Status:** Planning

---

## 1. Problem Statement

### 1.1 Observed Behavior

[Concrete behavior.]

### 1.2 Expected Behavior

[Correct behavior.]

### 1.3 Reproduction

[Steps or conditions.]

## 2. Root Cause Analysis

### 2.1 Code Path

[Execution trace with files and line numbers.]

### 2.2 Root Cause

[Exact incorrect logic and why it fails. Include copy-pasteable current and corrected snippets.]

### 2.3 Blast Radius

[Shared paths, dependent callers, and API/proto implications.]

## 3. Fix Strategy

### 3.1 Proposed Fix

[Minimal correct change with paths, lines, and copy-pasteable before/after snippets.]

### 3.2 Alternative Approaches

[Alternatives and trade-offs, or why no meaningful alternative exists.]

### 3.3 Files Changed

| File | Change |
| ---- | ------ |
| [path] | [Change] |

## 4. Test Gap Assessment

### 4.1 Existing Test Coverage

[Existing test files and functions.]

### 4.2 Why Existing Tests Didn't Catch This

[Specific missing scenario, assertion, fixture, or invalid mock boundary.]

### 4.3 Tests That Would Have Caught This

[Concrete test names, inputs, and assertions.]

### 4.4 Test Plan

| # | Test Case | What It Validates | Type |
| - | --------- | ----------------- | ---- |
| 1 | [Test name] | [Validation] | New / Modified |

## 5. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| [Risk] | H/M/L | H/M/L | [Strategy] |

## 6. Open Questions

| # | Question | Affects | Owner |
| - | -------- | ------- | ----- |
```

### 4. Create task files

Create one file per logical phase as `tasks/01-{description}.md`, `02-{description}.md`, and so on. Use:

```markdown
# Phase N: [Phase Title]

**Effort:** [total]d ([count] tasks)
**Dependencies:** [Prerequisites]
**Plan Reference:** [plan.md §N]

---

## Summary

[Phase outcome.]

---

## Tasks

### TN.1: [Task Title]

**Estimate:** [N]d
**Dependencies:** [Task IDs or "None"]

**Description:**
[Exact work with paths, current lines, and code changes.]

**Acceptance Criteria:**

- [ ] [Verifiable criterion]
- [ ] [Verifiable criterion]

**Files:**

- [Every file to create or modify]
```

Specify test files, test function names that match repository conventions, cases, assertions, and reusable helpers. Add a systemic coverage task when the escaped bug exposes a broader pattern.

### 5. Finalize indexes

Fill the bug summary, set status to `Planning Complete`, list all task files and tasks in `tasks/index.md`, and add the bug to `bugs/index.md`. If absent, create:

```markdown
# Bugs Index

**Parent:** [../index.md](../index.md)
**Last Updated:** [ISO 8601 timestamp with Mountain offset]

---

| Bug                    | Status            | Effort | Index                       |
| ---------------------- | ----------------- | ------ | --------------------------- |
| [Bug ID — Short Title] | Planning Complete | [N]d   | [link](bug-folder/index.md) |
```

When an original root index exists, add `bugs/` to its documentation table using its existing column structure. Do not force a schema that does not fit; make the smallest consistent index edit.

## Output Formatting

Use concise, evidence-backed Markdown. Keep code snippets complete enough to implement, but avoid duplicating large source regions.

Report completion with:

- bug folder and artifact paths;
- root cause and fix strategy;
- missing-test explanation and new coverage;
- task count, effort, dependencies, and critical path;
- open questions and API/proto risk.

Report problems under `Problems`, each with `Issue`, `Evidence`, `Impact`, and `Next action`. An unknown root cause, ambiguous planning root, or required breaking API/proto change blocks a definitive plan. Missing external enrichment is non-blocking when code and supplied context establish the bug.
