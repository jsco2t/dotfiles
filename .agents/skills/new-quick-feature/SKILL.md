---
name: new-quick-feature
description: Research a small feature and create a focused implementation plan with indexed, test-forward tasks. Use when a full new-eng-feature design and verification pipeline would be excessive, including direct requests and delegated planning with pre-supplied paths or decisions.
---

# New Quick Feature

## Inputs

- **Parent directory:** existing directory in which to create the feature subfolder.
- **Feature context:** issue links or keys, local files, and/or a description of current and desired behavior.
- Optional repository path, fixed feature slug, output decisions, or prior research from a caller.

Require the parent directory and feature context. Ask only for missing or materially ambiguous input. Honor pre-supplied paths and decisions and return artifacts, status, and blockers when delegated.

## Requirements and Skill Boundaries

- Use this lightweight workflow only for small, well-bounded features. For work needing explicit architecture decisions, a broad test strategy, or manual verification planning, recommend `new-eng-feature`.
- Produce only `index.md`, `plan.md`, `tasks/index.md`, task files, and the parent features index update. Do not create research, review, follow-up, verification, or separate design documents; the implementation plan is the design.
- Ground all code claims in current file paths and line numbers. Do not guess implementation details.
- A concrete Test Gap Assessment and explicit test tasks are mandatory.
- Prefer the smallest complete implementation. Investigate related paths, callers, compatibility, and systemic implications.
- Keep each task at 1.5 days or less. Put implementation before dependent test tasks and require the relevant full test suite in the final test task.
- Follow project rules, including additive-only API/proto evolution where applicable.
- Verify artifact names and schemas from repository generators/configuration and recent examples before referencing changelog entries, migrations, fixtures, or generated files.
- Use ISO 8601 timestamps with the local Mountain offset.

## Core Skill Process

### 1. Initialize the feature folder

Validate the parent directory. Extract a tracker ID and three-to-five-word dash-case slug, matching sibling conventions. Name the folder `{TRACKER-ID}-{short-description}` when an ID exists, otherwise `{short-description}`. Create:

```text
<parent-directory>/
└── <feature-folder-name>/
    ├── index.md
    ├── plan.md
    └── tasks/
        └── index.md
```

Use these initial schemas:

```markdown
# [Feature ID]: [Short Title] — Feature Implementation Documentation

**Feature:** [Title]
**Jira:** [Link or "N/A"]
**Repository:** [Repository path]
**Created:** [ISO 8601 timestamp with Mountain offset]
**Status:** Planning

---

## Documentation Structure

| Document                   | Purpose                                                    |
| -------------------------- | ---------------------------------------------------------- |
| [`plan.md`](plan.md)       | Implementation plan, strategy, and test gap assessment     |
| [`tasks/`](tasks/index.md) | Implementation task breakdown with test-forward approach   |

---

## Summary

| Metric           | Value                          |
| ---------------- | ------------------------------ |
| Total Tasks      | [count]                        |
| Estimated Effort | [total] days                   |
| Test Gap         | [Required coverage improvement] |
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

### 2. Research the request

Read every supplied source. Fetch issue/spec content with available connectors when useful. Establish current behavior, desired behavior, scope, acceptance criteria, and prerequisites.

Trace relevant entry points, call chains, validation, error handling, and state transitions. Identify the exact implementation locations, shared patterns, dependent callers, compatibility impact, API/proto implications, existing tests, needed test changes, reusable helpers, and every affected file. Compare viable implementation approaches and select the smallest complete one.

If the implementation cannot be determined from evidence, stop before presenting a definitive plan and report what additional specification or code context is required.

### 3. Write `plan.md`

Use this exact structure:

```markdown
# Implementation Plan: [Feature ID] — [Short Title]

**Feature:** [Jira link or title]
**Author:** [User name if known]
**Created:** [ISO 8601 timestamp with Mountain offset]
**Status:** Planning

---

## 1. Problem Statement

### 1.1 Observed Behavior

[Current behavior.]

### 1.2 Expected Behavior

[Desired behavior.]

### 1.3 Reproduction

[Conditions needed to exercise the feature.]

## 2. Implementation Analysis

### 2.1 Code Path

[Trace with files and line numbers.]

### 2.2 Current Logic and Change Point

[What exists, why it must change, and copy-pasteable representative snippets.]

### 2.3 Blast Radius

[Shared paths, dependent callers, and API/proto implications.]

## 3. Implementation Strategy

### 3.1 Proposed Change

[Minimal complete implementation with paths, lines, and copy-pasteable before/after snippets where useful.]

### 3.2 Alternative Approaches

[Alternatives and trade-offs, or why no meaningful alternative exists.]

### 3.3 Files Changed

| File | Change |
| ---- | ------ |
| [path] | [Change] |

## 4. Test Gap Assessment

### 4.1 Existing Test Coverage

[Existing test files and functions.]

### 4.2 Adjusted/Improved/Changed Test Coverage

[Required coverage changes and why.]

### 4.3 Test Plan

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
[Exact work with paths, current lines, and changes.]

**Acceptance Criteria:**

- [ ] [Verifiable criterion]
- [ ] [Verifiable criterion]

**Files:**

- [Every file to create or modify]
```

Every implementation task requires a corresponding test task. Specify test paths, function names that follow repository conventions, cases, assertions, and helpers. Add broader coverage work when the feature exposes a systemic gap.

### 5. Finalize indexes

Fill the feature summary, set status to `Planning Complete`, and list every task file and task in `tasks/index.md`. Add the feature to an existing `features/index.md`; if absent, create:

```markdown
# Features Index

**Last Updated:** [ISO 8601 timestamp with Mountain offset]

---

| Feature                    | Status            | Effort | Index                           |
| -------------------------- | ----------------- | ------ | ------------------------------- |
| [Feature ID — Short Title] | Planning Complete | [N]d   | [link](feature-folder/index.md) |
```

## Output Formatting

Use concise, implementation-ready Markdown. Include enough code context to remove ambiguity without copying large source regions.

Report completion with:

- feature folder and artifact paths;
- implementation strategy and affected files;
- test strategy and coverage changes;
- task count, effort, dependencies, and critical path;
- open questions and API/proto risk.

Report problems under `Problems`, each with `Issue`, `Evidence`, `Impact`, and `Next action`. An indeterminate implementation, ambiguous output location, oversized scope that needs `new-eng-feature`, or required breaking API/proto change blocks a definitive quick plan. Missing external enrichment is non-blocking when local evidence and supplied context are sufficient.
