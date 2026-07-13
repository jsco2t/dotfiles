---
name: new-quick-feature
description: "Create a structured feature implementation plan with test-forward task breakdown. Researches the codebase to understand the problem space, research the feature request, produces an implementation plan, and generates tasks that always include test coverage improvements."
argument-hint: "<path: where to create the feature folder> <feature description, Jira links, or file paths>"
---

# New Quick Feature Skill

This skill represents a simplified feature implementation pipeline. You are creating a structured plan for a simple feature task. You research the codebase to understand the problem space, you research the requested feature, you produce an implementation plan, and break the work into tasks that are **test-forward**.

This skill produces a focused, lightweight documentation set: an index, a plan, and task files. Unlike `/new-eng-feature`, there is no design document, verification suite, or multi-skill pipeline. The goal here is to run through a simplified pipeline for small feature requests, in this case the plan IS the design.

## Input

The user has provided the following context:

$ARGUMENTS

You need two inputs. If either is missing, use AskUserQuestion to ask:

1. **File path** — absolute path: This will be the location where you create a **subfolder** which
   contains all the planning docs created by this skill.

2. **Feature description** — what the issue is. May include:
   - Jira issue keys or URLs (e.g., `FUZZ-6904`, `https://ciqinc.atlassian.net/browse/FUZZ-6904`)
   - Confluence page URLs
   - Local file paths with additional context
   - Free-text description of the observed vs expected behavior

---

## Phase 0: Determine Context and Create Folder Structure

### Step 0.1: Validate the file path

- **Verify**: Verify the users selected folder location exists. This will be the **parent** folder
  for where the newly created feature docs will live. If the path does not exist use AskUserQuestion
  to get the correct path.

### Step 0.2: Extract Feature Identity

From the user's feature description, extract:

- **Feature tracker ID** (if present): Jira key like `FUZZ-6904`, GitHub issue number, etc.
- **Short description**: a dash-cased slug summarizing the problem (3-5 words max)

Construct the feature folder name:

- With tracker ID: `{FEATURE-ID}-{short-description}` (e.g., `FUZZ-6904-ephemeral-permission-fix`)
- Without tracker ID: `{short-description}` (e.g., `volume-delete-race-condition`)

Use UPPERCASE for the tracker prefix, lowercase-dash-case for the description. Match the naming convention used by the existing project (check sibling folders for precedent).

### Step 0.3: Create Folder Structure

Create the following inside the parent directory:

```
<parent-directory>/
└── <feature-folder-name>/
     ├── index.md
     ├── plan.md
     └── tasks/
         └── index.md
```

### Step 0.4: Create Initial Index Files

**Feature `index.md`:**

```markdown
# [Feature ID]: [Short Title] — Feature Implementation Documentation

**Feature:** [Title from Jira or user description]
**Jira:** [Link if available, otherwise "N/A"]
**Repository:** [Path to code repository — derive from current working directory or project context]
**Created:** [ISO 8601 timestamp with MST offset]
**Status:** Planning

---

## Documentation Structure

| Document                   | Purpose                                                    |
| -------------------------- | ---------------------------------------------------------- |
| [`plan.md`](plan.md)       | Implementation plan, fix strategy, and test gap assessment |
| [`tasks/`](tasks/index.md) | Implementation task breakdown with test-forward approach   |

---

## Summary

| Metric           | Value                             |
| ---------------- | --------------------------------- |
| Total Tasks      | [count]                           |
| Estimated Effort | [total] days                      |
| Test Gap         | [What automated test was missing] |
```

**Tasks `index.md`:**

```markdown
# Tasks Index

**Parent:** [../index.md](../index.md)
**Last Updated:** [ISO 8601 timestamp with MST offset]

---

## Documents

| Document | Description | Created |
| -------- | ----------- | ------- |

## Task Tracking

| Task ID | Task Name | Estimate | Dependencies | Completed |
| ------- | --------- | -------- | ------------ | --------- |
```

---

## Phase 1: Research the Feature Request

Before writing the plan, do thorough research. The plan must be grounded in code evidence, not speculation.

### Step 1.1: Gather External Context (if links provided)

If the feature description includes Jira or Confluence links:

- Fetch the Jira issue for full description, acceptance criteria, comments, and linked issues
- Fetch any linked Confluence pages for spec context
- Check for related/duplicate issues
- Note the reporter, priority, and any reproduction steps in the ticket

If MCP tools are unavailable, inform the user and proceed with the textual description.

### Step 1.2: Evaluate Understanding

From the feature description and any fetched context, establish:

- **Observed behavior**: what the state is today
- **Expected behavior**: what the desired state is
- **Reproduction conditions**: any requirements to exercise the feature (pre-existing state...etc)

### Step 1.3: Codebase Investigation

This is the core research step. Use the codebase to determine where the feature should be implemented.

1. **Find the relevant code paths** — use Grep, Explore agents, or direct file reads to locate:
   - The function(s) where the feature change needs to happen
   - The call chain involved with the feature
   - Any related error handling or validation logic

2. **Identify how to fix the feature request** — trace the execution to find:
   - The specific line(s) or condition(s) that are involved in the feature fix
   - Where the current logic needs to change (wrong condition, missing check, incorrect ordering, etc.)
   - Whether this change is localized to a single area of the codebase or systemic

3. **Assess the blast radius** — determine:
   - What other code paths share the same pattern (do we need to re-evaluate where to implement the change?)
   - What callers depend on the existing behavior (will implementing this feature break something?)
   - Whether proto/API changes are needed (additive only per project rules)

4. **Find the test gap** — this is critical. Determine:
   - What existing tests cover this code path (if any)
   - What test changes need to happen
   - What existing test patterns and helpers are available for the new tests

### Step 1.4: Identify the Implementation Strategy

Based on the investigation, determine:

- **The minimal correct fix** — the smallest change that resolves the feature request
- **Alternative approaches** — if there are multiple valid fixes, note them with trade-offs
- **Files that need to change** — list every file with the specific changes needed

---

## Phase 2: Write the Plan

Create `plan.md` inside the feature folder.

### Plan Structure

```markdown
# Implementation Plan: [Feature ID] — [Short Title]

**Feature:** [Jira link or title]
**Author:** [User name if known]
**Created:** [ISO 8601 timestamp with MST offset]
**Status:** Planning

---

## 1. Problem Statement

### 1.1 Observed Behavior

[What currently happens]

### 1.2 Expected Behavior

[What needs to be implemented to deliver the desired behavior]

### 1.3 Reproduction

[Steps or conditions to leverage the feature]

---

## 2. Implementation Analysis

### 2.1 Code Path

[Trace the execution from entry point to feature change location. Reference specific files and line numbers.]

### 2.2 Root Cause

[The current logic — what line(s), what condition, why it needs to change. Include a code snippet showing the change that needs to happen.]

### 2.3 Blast Radius

[Other code paths sharing the same pattern, callers that depend on current behavior, API/proto implications]

---

## 3. Fix Strategy

### 3.1 Proposed Fix

[The minimal correct change. Include before/after code snippets with file paths and line numbers.]

### 3.2 Alternative Approaches

[Other ways to fix it, with trade-offs. If only one approach makes sense, say so and why.]

### 3.3 Files Changed

| File   | Change                  |
| ------ | ----------------------- |
| [path] | [Description of change] |

---

## 4. Test Gap Assessment

This section is **mandatory**.

### 4.1 Existing Test Coverage

[What tests exist for this code path today. Reference test file(s) and specific test function names.]

### 4.2 Adjusted/Improved/Changed Test Coverage

[What test changes need to happen to fully test this feature change.]

### 4.3 Test Plan

| # | Test Case   | What It Validates | Type           |
| - | ----------- | ----------------- | -------------- |
| 1 | [Test name] | [What it checks]  | New / Modified |

---

## 5. Risk Assessment

| Risk   | Likelihood | Impact  | Mitigation |
| ------ | ---------- | ------- | ---------- |
| [Risk] | [H/M/L]    | [H/M/L] | [Strategy] |

---

## 6. Open Questions

| # | Question | Affects | Owner |
| - | -------- | ------- | ----- |
```

**Rules for writing the plan:**

- Every claim about the code must reference a specific file and line number
- The implementation plan must be grounded in a code trace, not speculation
- The Test Gap Assessment (§4) is not optional — skip it and the plan is incomplete
- Before/after code snippets must be copy-pasteable (correct indentation, full context)
- If the fix requires changes to multiple files, list ALL of them in §3.3
- Whenever the plan names a project artifact path (changelog entry, release-notes file, migration, fixture, etc.), verify the project's actual naming convention before writing it down — see Important Guidelines #9. A wrong path in the plan propagates into the task doc and the implementation; once it's down on paper, the implementer copies it.

---

## Phase 3: Create Task Files

Break the fix into discrete, actionable tasks. Every implementation fix produces at minimum two task categories:

1. **Fix tasks** — the code change(s) to implement the feature
2. **Test tasks** — new or improved tests that close the test gap

### Task File Format

Create one file per logical phase in `tasks/`. Name files: `01-{description}.md`, `02-{description}.md`, etc.

```markdown
# Phase N: [Phase Title]

**Effort:** [total]d ([count] tasks)
**Dependencies:** [what must be done first]
**Plan Reference:** [plan.md §N]

---

## Summary

[1-2 sentences: what this phase accomplishes]

---

## Tasks

### TN.1: [Task Title]

**Estimate:** [N]d
**Dependencies:** [task IDs or "None"]

**Description:**
[What to do. Include specific file paths, line numbers, and code changes. Be precise enough that the implementation is unambiguous.]

**Acceptance Criteria:**

- [ ] [Specific, verifiable criterion]
- [ ] [Another criterion]

**Files:**

- [List every file to create or modify]
```

### Task Breakdown Rules

1. **Implement first, then test.** The fix/implementation task comes before its corresponding test task, with the test depending on the fix.

2. **Test tasks are never optional.** Every fix task must have a corresponding test task. If the fix is a 1-line change, the test task should still exist and may have MORE effort than the fix itself.

3. **Test tasks must specify:**
   - The test file to create or modify
   - Specific test function names (following existing patterns in the codebase)
   - What each test case validates
   - Which existing test helpers/patterns to reuse

4. **If the implementation reveals a systemic gap**, add a dedicated "test coverage improvement" task that goes beyond just testing the specific fix — it should add coverage for the pattern that was missed.

5. **Keep tasks small.** Each task should be completable in ≤1.5 days. If a task is larger, split it.

6. **Include a "verify no regression" criterion** in the final test task's acceptance criteria — the full unit test suite must pass after all changes.

---

## Phase 4: Update All Index Files

### Step 4.1: Update the Feature Index

Update the feature's `index.md`:

- Fill in the Summary table (total tasks, estimated effort, root cause, test gap)
- Set status to "Planning Complete"

### Step 4.2: Update the Tasks Index

Populate `tasks/index.md` with:

- All task document files in the Documents table
- All individual tasks in the Task Tracking table (with checkboxes)

### Step 4.3: Update the Parent Features Index

If a `features/index.md` exists in the `features/` directory, add the new feature to it.

If no `features/index.md` exists, create one:

```markdown
# Features Index

**Last Updated:** [ISO 8601 timestamp with MST offset]

---

| Feature                    | Status            | Effort | Index                           |
| -------------------------- | ----------------- | ------ | ------------------------------- |
| [Feature ID — Short Title] | Planning Complete | [N]d   | [link](feature-folder/index.md) |
```

---

## Phase 5: Present Summary

After all phases complete, present:

1. **Plan** — 1-2 sentence summary
2. **Implementation strategy** — what changes, how many files
3. **Test Plan** — summary test strategy
4. **Task summary** — count, effort, critical path
5. **Open questions** — anything blocking or uncertain

---

## Error Handling

### If the Implementation Plan Cannot Be Determined

Do not guess. Present what you found (partial traces, candidate locations) and ask the user for guidance via AskUserQuestion. Options:

- Provide more context or reproduction steps
- Point to a specific area of the code to investigate
- Proceed with the best-available hypothesis (clearly marked as such)

### If MCP Tools Are Unavailable

Inform the user and proceed with the textual description. Jira enrichment is valuable but not blocking — the codebase investigation is the primary research method.

### If the Fix Requires Proto/API Changes

Flag this prominently. Per project rules, proto changes must be additive. If the fix requires a breaking proto change, surface this as a risk and ask the user.

---

## Important Guidelines

1. **Test-forward is non-negotiable.** Every fix must include test improvements. A fix without tests is not a complete fix — it's a patch that will regress. The Test Gap Assessment in the plan and the test tasks in the breakdown are mandatory, not optional.

2. **Root cause over symptoms.** Don't plan a fix for the symptom. Trace to the actual root cause, even if it's deeper than expected. If the root cause spans multiple components, the plan should say so.

3. **Grounded in code, not speculation.** Every claim in the plan must reference a specific file and line. "Probably in the validation logic" is not acceptable. "In `provisioner_selection.go:217`, the condition checks `size != ""` but should check `volumeName == ""`" is.

4. **Minimal fix, maximal test.** The code change should be the smallest correct fix. The test change should be thorough — covering the specific feature, edge cases, and the pattern that was missed.

5. **Timestamps in MST.** All timestamps use ISO 8601 format with MST offset: `YYYY-MM-DDTHH:MM:SS-06:00`.

6. **Index files are your responsibility.** After creating documents, update every relevant index: the features's own indexes, the features/ directory index, and the root index.

7. **Feature folder naming is permanent.** The folder name becomes the canonical identifier. Get it right: `{TRACKER-ID}-{short-description}` with the tracker ID if available.

8. **Don't create what wasn't asked for.** No `research/`, `reviews/`, `follow-ups/`, `verifications/`, or `design.md`. The plan IS the design. Extra structure is noise.

9. **Verify repository conventions before naming artifacts.** When the plan references any repository artifact — changelog entries, release-notes files, database migrations, test fixtures, generated proto files, etc. — discover the actual project convention. Do not invent filenames from training-data memory; the cost of a wrong path in the plan is that it gets copied into the task doc and then into the working tree.

   **How to verify (cheap):**
   - Find the generator code that produces the artifact (e.g. for Fuzzball changelogs: `fuzzy/pkg/changelog/changelog.go` — the `Add()` function shows the exact filename format and the schema). Read what filename and schema it produces.
   - List a handful of recent examples in the canonical directory (`ls changelog/pending/`, `ls changelog/releases/<latest>/`, `ls database/migrations/`). The de-facto pattern is whatever the recent commits do.
   - Confirm your proposed name matches _exactly_ — same date format, no descriptive suffixes, no extra fields, no creative reordering.

   **Concrete failure mode (Fuzzball, FUZZ-7632):** a plan suggested `changelog/pending/20260612-fuzz-7632-volume-list-pagination.yaml`. The actual generator at `fuzzy/pkg/changelog/changelog.go:160-161` only ever produces `YYYYMMDD-fuzz-NNNN.yaml` with no descriptive suffix, and the schema is a fixed 4-field YAML (`issue`, `description`, `scope`, `type`) where `scope` and `type` must match values in `changelog/config.yaml`. The wrong filename made it into the task doc and would have shipped as a non-conforming artifact if not caught. A 30-second check of the generator code would have produced the right name on the first try.

   **When uncertain, ask the user.** A one-question clarification is cheaper than a wrong path that propagates through the documentation and the diff.
