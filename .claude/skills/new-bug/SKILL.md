---
name: new-bug
description: "Create a structured bug fix plan with test-forward task breakdown. Researches the codebase to understand the root cause, produces a fix plan, and generates tasks that always include test coverage improvements. Bugs indicate missing automated validation — every bug fix must close that gap."
argument-hint: "<root index file path> <bug description, Jira links, or file paths>"
---

# New Bug Skill

You are creating a structured bug fix plan for a reported issue. You research the codebase to understand the root cause, produce a fix plan, and break the work into tasks that are **test-forward** — every bug is evidence that automated validation was insufficient, and the fix must close that gap.

This skill produces a focused, lightweight documentation set: an index, a plan, and task files. Unlike `/new-eng-feature`, there is no design document, verification suite, or multi-skill pipeline. Bugs are smaller scope — the plan IS the design.

## Input

The user has provided the following context:

$ARGUMENTS

You need two inputs. If either is missing, use AskUserQuestion to ask:

1. **Root index file** — absolute path to either:
   - A **project-level** root `index.md` (sibling to `prd.md`, has a `features/` subfolder)
   - A **feature-level** root `index.md` (sibling to `plans/`, `tasks/`, has no `prd.md`)
   - **No root index**: The supplied path has no index file. In this case create a (or use existing)
     `bugs/` folder. Perform the bug fix planning based on the second parameter and the current
     source code.

   The `bugs/` folder will be created at the same level as this index file.

2. **Bug description** — what the issue is. May include:
   - Jira issue keys or URLs (e.g., `FUZZ-6904`, `https://ciqinc.atlassian.net/browse/FUZZ-6904`)
   - Confluence page URLs
   - Local file paths with additional context
   - Free-text description of the observed vs expected behavior

---

## Phase 0: Determine Context and Create Folder Structure

### Step 0.1: Validate and Classify the Root Index

Read the root index file. Determine its type:

- **Project-level**: the index file's directory contains `prd.md` and/or a `features/` subdirectory
- **Feature-level**: the index file's directory contains `plans/` and/or `tasks/` subdirectories, but no `prd.md`
- **Ambiguous**: neither pattern matches — ask the user to confirm via AskUserQuestion

Record the **parent directory** of the index file — this is where the `bugs/` folder will be created.

### Step 0.2: Extract Bug Identity

From the user's bug description, extract:

- **Bug tracker ID** (if present): Jira key like `FUZZ-6904`, GitHub issue number, etc.
- **Short description**: a dash-cased slug summarizing the problem (3-5 words max)

Construct the bug folder name:

- With tracker ID: `{BUG-ID}-{short-description}` (e.g., `FUZZ-6904-ephemeral-permission-fix`)
- Without tracker ID: `{short-description}` (e.g., `volume-delete-race-condition`)

Use UPPERCASE for the tracker prefix, lowercase-dash-case for the description. Match the naming convention used by the existing project (check sibling folders for precedent).

### Step 0.3: Create Folder Structure

Create the following inside the parent directory:

```
<parent-directory>/
└── bugs/
    └── <bug-folder-name>/
        ├── index.md
        ├── plan.md
        └── tasks/
            └── index.md
```

If the `bugs/` directory already exists, do not recreate it — add the new bug folder alongside any existing ones.

### Step 0.4: Create Initial Index Files

**Bug `index.md`:**

```markdown
# [Bug ID]: [Short Title] — Bug Fix Documentation

**Bug:** [Title from Jira or user description]
**Jira:** [Link if available, otherwise "N/A"]
**Repository:** [Path to code repository — derive from current working directory or project context]
**Created:** [ISO 8601 timestamp with MST offset]
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

## Phase 1: Research the Bug

Before writing the plan, do thorough research. The plan must be grounded in code evidence, not speculation.

### Step 1.1: Gather External Context (if links provided)

If the bug description includes Jira or Confluence links:

- Fetch the Jira issue for full description, acceptance criteria, comments, and linked issues
- Fetch any linked Confluence pages for spec context
- Check for related/duplicate issues
- Note the reporter, priority, and any reproduction steps in the ticket

If MCP tools are unavailable, inform the user and proceed with the textual description.

### Step 1.2: Reproduce Understanding

From the bug description and any fetched context, establish:

- **Observed behavior**: what actually happens
- **Expected behavior**: what should happen
- **Reproduction conditions**: when/how this manifests (specific inputs, states, configurations)

### Step 1.3: Codebase Investigation

This is the core research step. Use the codebase to find the root cause.

1. **Find the relevant code paths** — use Grep, Explore agents, or direct file reads to locate:
   - The function(s) where the bug manifests
   - The call chain leading to the buggy behavior
   - Any related error handling or validation logic

2. **Identify the root cause** — trace the execution to find:
   - The specific line(s) or condition(s) that produce the wrong behavior
   - Why the current logic is incorrect (wrong condition, missing check, incorrect ordering, etc.)
   - Whether this is a localized bug or a systemic pattern

3. **Assess the blast radius** — determine:
   - What other code paths share the same pattern (could the same bug exist elsewhere?)
   - What callers depend on the buggy behavior (will fixing it break something?)
   - Whether proto/API changes are needed (additive only per project rules)

4. **Find the test gap** — this is critical. Determine:
   - What existing tests cover this code path (if any)
   - Why those tests didn't catch this bug (wrong assertions? missing scenario? mocked incorrectly?)
   - What test case(s) would have caught it
   - What existing test patterns and helpers are available for the new tests

### Step 1.4: Identify the Fix Strategy

Based on the investigation, determine:

- **The minimal correct fix** — the smallest change that resolves the bug
- **Alternative approaches** — if there are multiple valid fixes, note them with trade-offs
- **Files that need to change** — list every file with the specific changes needed

---

## Phase 2: Write the Plan

Create `plan.md` inside the bug folder.

### Plan Structure

```markdown
# Bug Fix Plan: [Bug ID] — [Short Title]

**Bug:** [Jira link or title]
**Author:** [User name if known]
**Created:** [ISO 8601 timestamp with MST offset]
**Status:** Planning

---

## 1. Problem Statement

### 1.1 Observed Behavior

[What actually happens — concrete, reproducible description]

### 1.2 Expected Behavior

[What should happen per the spec or correct logic]

### 1.3 Reproduction

[Steps or conditions to reproduce. Reference specific configs, inputs, or states.]

---

## 2. Root Cause Analysis

### 2.1 Code Path

[Trace the execution from entry point to the bug. Reference specific files and line numbers.]

### 2.2 Root Cause

[The specific incorrect logic — what line(s), what condition, why it's wrong. Include a code snippet showing the buggy code and the corrected version.]

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

This section is **mandatory**. A bug reaching this stage means automated validation failed.

### 4.1 Existing Test Coverage

[What tests exist for this code path today. Reference test file(s) and specific test function names.]

### 4.2 Why Existing Tests Didn't Catch This

[The specific gap: missing scenario, wrong assertion, overly broad mock, etc.]

### 4.3 Tests That Would Have Caught This

[Describe the specific test case(s) that, if they had existed, would have prevented this bug from shipping. Be concrete — name the test, the input, and the assertion.]

### 4.4 Test Plan

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
- The root cause must be grounded in a code trace, not speculation
- The Test Gap Assessment (§4) is not optional — skip it and the plan is incomplete
- Before/after code snippets must be copy-pasteable (correct indentation, full context)
- If the fix requires changes to multiple files, list ALL of them in §3.3

---

## Phase 3: Create Task Files

Break the fix into discrete, actionable tasks. Every bug fix produces at minimum two task categories:

1. **Fix tasks** — the code change(s) to resolve the bug
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

1. **Fix first, then test.** The fix task comes before its corresponding test task, with the test depending on the fix.

2. **Test tasks are never optional.** Every fix task must have a corresponding test task. If the fix is a 1-line change, the test task should still exist and may have MORE effort than the fix itself.

3. **Test tasks must specify:**
   - The test file to create or modify
   - Specific test function names (following existing patterns in the codebase)
   - What each test case validates
   - Which existing test helpers/patterns to reuse

4. **If the bug reveals a systemic gap**, add a dedicated "test coverage improvement" task that goes beyond just testing the specific fix — it should add coverage for the pattern that was missed.

5. **Keep tasks small.** Each task should be completable in ≤1.5 days. If a task is larger, split it.

6. **Include a "verify no regression" criterion** in the final test task's acceptance criteria — the full unit test suite must pass after all changes.

---

## Phase 4: Update All Index Files

### Step 4.1: Update the Bug Index

Update the bug's `index.md`:

- Fill in the Summary table (total tasks, estimated effort, root cause, test gap)
- Set status to "Planning Complete"

### Step 4.2: Update the Tasks Index

Populate `tasks/index.md` with:

- All task document files in the Documents table
- All individual tasks in the Task Tracking table (with checkboxes)

### Step 4.3: Update the Parent Bugs Index

If a `bugs/index.md` exists in the `bugs/` directory, add the new bug to it.

If no `bugs/index.md` exists, create one:

```markdown
# Bugs Index

**Parent:** [../index.md](../index.md)
**Last Updated:** [ISO 8601 timestamp with MST offset]

---

| Bug                    | Status            | Effort | Index                       |
| ---------------------- | ----------------- | ------ | --------------------------- |
| [Bug ID — Short Title] | Planning Complete | [N]d   | [link](bug-folder/index.md) |
```

### Step 4.4: Update the Root Index

Read the root index file (the one the user provided as input). Add or update a "Bugs" section:

- If a `## Bugs` section already exists, add a row
- If no bugs section exists, add one to the Documentation Structure table:

For **project-level** indexes, add to the Documentation Structure table:

```markdown
| [`bugs/`](bugs/index.md) | Bug fix documentation and task plans | [bugs/index.md](bugs/index.md) |
```

For **feature-level** indexes, add to the Documentation Structure table:

```markdown
| [`bugs/`](bugs/index.md) | Bug fix documentation and task plans | [bugs/index.md](bugs/index.md) |
```

If the Documentation Structure table doesn't have a column that fits, use AskUserQuestion to ask the user where to add the bugs reference.

---

## Phase 5: Present Summary

After all phases complete, present:

1. **Root cause** — 1-2 sentence summary
2. **Fix strategy** — what changes, how many files
3. **Test gap** — what was missing and what's being added
4. **Task summary** — count, effort, critical path
5. **Open questions** — anything blocking or uncertain

---

## Error Handling

### If the Root Cause Cannot Be Determined

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

1. **Test-forward is non-negotiable.** Every bug fix must include test improvements. A fix without tests is not a complete fix — it's a patch that will regress. The Test Gap Assessment in the plan and the test tasks in the breakdown are mandatory, not optional.

2. **Root cause over symptoms.** Don't plan a fix for the symptom. Trace to the actual root cause, even if it's deeper than expected. If the root cause spans multiple components, the plan should say so.

3. **Grounded in code, not speculation.** Every claim in the plan must reference a specific file and line. "Probably in the validation logic" is not acceptable. "In `provisioner_selection.go:217`, the condition checks `size != ""` but should check `volumeName == ""`" is.

4. **Minimal fix, maximal test.** The code change should be the smallest correct fix. The test change should be thorough — covering the specific bug, edge cases, and the pattern that was missed.

5. **Timestamps in MST.** All timestamps use ISO 8601 format with MST offset: `YYYY-MM-DDTHH:MM:SS-06:00`.

6. **Index files are your responsibility.** After creating documents, update every relevant index: the bug's own indexes, the bugs/ directory index, and the root index.

7. **Bug folder naming is permanent.** The folder name becomes the canonical identifier. Get it right: `{TRACKER-ID}-{short-description}` with the tracker ID if available.

8. **Don't create what wasn't asked for.** No `research/`, `reviews/`, `follow-ups/`, `verifications/`, or `design.md`. Bugs are focused. The plan IS the design. Extra structure is noise.
