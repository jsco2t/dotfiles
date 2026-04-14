---
name: new-eng-feature
description: End-to-end engineering feature planning orchestrator. Creates a structured documentation folder, then sequentially runs /eng-plan-creator, /eng-design-creator, /eng-test-planning, /eng-task-planning, and /eng-verification-creator — passing outputs forward as inputs, maintaining index files, and routing all interactive Q&A to the user.
argument-hint: "<output directory> <spec links: Jira/Confluence URLs or file paths> [--repo <path to code repo>]"
---

# New Engineering Feature Skill

You are orchestrating the complete engineering planning pipeline for a new feature. You will create a documentation folder structure, then run five specialized skills **in strict sequential order**, passing each skill's output forward as input to the next. You are the conductor — you set up context, invoke each skill, and maintain the connective tissue (index files, folder structure, follow-ups) between them.

**You MUST run the skills in this exact order:**

1. `/eng-plan-creator` — produces the implementation plan
2. `/eng-design-creator` — produces the design document
3. `/eng-test-planning` — appends a test plan to the implementation plan
4. `/eng-task-planning` — produces the task breakdown
5. `/eng-verification-creator` — produces manual verification documents

**Each skill must fully complete before the next one starts.** Skills 1 and 2 will ask the user interactive questions — these MUST flow through to the user. Do not skip, defer, or answer on behalf of the user.

## Input

The user has provided the following context:

$ARGUMENTS

You need three inputs. If any are missing, use AskUserQuestion to ask:

1. **Output directory** — where to create the feature documentation folder. Example: `/Users/jscott/Developer/sources/personal/notebook/projects/fuzzball/features/FUZZ-XXXX`
2. **Spec links** — Jira issue keys/URLs, Confluence page URLs, or local file paths that define the feature specification. At least one is required.
3. **Code repository path** — the repository where the eventual code changes will happen. If you are already inside the target repo (check the current working directory), this is optional. If the current directory is NOT the target repo, you must have this path.

---

## Phase 0: Initialize Folder Structure

Before invoking any skill, set up the workspace.

### Step 0.1: Validate Inputs

- Confirm the output directory path. Create it if it does not exist.
- Confirm at least one spec link was provided.
- Confirm the code repository is accessible (either the current directory or the provided `--repo` path).
- Determine a **feature slug** for use in file naming. Derive this from the Jira epic key if available (e.g., `FUZZ-3365`), or from the feature name if not. Ask the user to confirm the slug if it's ambiguous.

### Step 0.2: Create Folder Structure

Create the following directory tree inside the output directory:

```
<output-directory>/
├── index.md
├── plans/
│   └── index.md
├── tasks/
│   └── index.md
├── research/
│   └── index.md
├── follow-ups/
│   └── index.md
└── verifications/
    └── index.md
```

### Step 0.3: Create Initial Index Files

**Root `index.md`:**

```markdown
# [Feature Name] — Engineering Documentation

**Feature:** [Feature name]
**Jira:** [Epic key(s) and links]
**Repository:** [Path to code repository]
**Created:** [ISO 8601 timestamp with MST offset, e.g., 2026-04-14T11:30:00-06:00]
**Status:** In Progress

---

## Documentation Structure

| Folder | Purpose | Index |
|--------|---------|-------|
| [`plans/`](plans/index.md) | Implementation plan, design document, and test strategy | [plans/index.md](plans/index.md) |
| [`tasks/`](tasks/index.md) | Implementation task breakdown with estimates and dependencies | [tasks/index.md](tasks/index.md) |
| [`research/`](research/index.md) | Ancillary research and background documents | [research/index.md](research/index.md) |
| [`follow-ups/`](follow-ups/index.md) | Open questions and items requiring future resolution | [follow-ups/index.md](follow-ups/index.md) |
| [`verifications/`](verifications/index.md) | Manual verification test documents | [verifications/index.md](verifications/index.md) |
```

**Each subfolder `index.md`** starts as an empty index with the table header but no entries yet:

```markdown
# [Folder Name] Index

**Parent:** [../index.md](../index.md)
**Last Updated:** [ISO 8601 timestamp with MST offset]

---

| Document | Description | Created |
|----------|-------------|---------|
```

For the **`tasks/index.md`**, use an extended format with a completion checkbox:

```markdown
# Tasks Index

**Parent:** [../index.md](../index.md)
**Last Updated:** [ISO 8601 timestamp with MST offset]

---

## Documents

| Document | Description | Created |
|----------|-------------|---------|

## Task Tracking

_Populated after task planning is complete._

| Task ID | Task Name | Phase | Estimate | Dependencies | Completed |
|---------|-----------|-------|----------|--------------|-----------|
```

### Step 0.4: Inform the User

Tell the user:

- What folder structure was created
- What the feature slug is
- That you are about to begin the planning pipeline
- That `/eng-plan-creator` and `/eng-design-creator` will ask them interactive questions about requirements and design decisions

---

## Phase 1: Implementation Plan (`/eng-plan-creator`)

### Step 1.1: Prepare Arguments

Build the arguments string for `/eng-plan-creator`. The arguments must include:

1. All spec links the user provided (Jira URLs, Confluence URLs, file paths)
2. An explicit instruction to save the output document to: `<output-directory>/plans/implementation-plan.md`

Format the arguments as:

```
<spec links provided by user>

IMPORTANT OUTPUT INSTRUCTIONS: Save the research document to <output-directory>/plans/implementation-plan.md — do NOT ask where to save it, the path has been predetermined. Title the document "Engineering Implementation Plan: [Feature Name]".
```

### Step 1.2: Invoke the Skill

Use the Skill tool to invoke `/eng-plan-creator` with the prepared arguments.

**This skill will ask the user questions** if it encounters ambiguities in the spec or needs clarification. Let all Q&A flow through naturally — do not intercept or answer on behalf of the user.

### Step 1.3: Post-Skill Housekeeping

After `/eng-plan-creator` completes:

1. **Verify the output file exists** at `<output-directory>/plans/implementation-plan.md`. If the skill saved it elsewhere, move it to the correct location.

2. **Update `plans/index.md`** — add the implementation plan to the documents table:

   ```markdown
   | [`implementation-plan.md`](implementation-plan.md) | Engineering implementation plan — feature overview, requirements, codebase impact, gaps, and high-level approach | [timestamp] |
   ```

3. **Check for ancillary research files** — if the skill created any supplementary documents (background research, technology primers), move them to `research/` and update `research/index.md`.

4. **Record the implementation plan path** for use in subsequent phases:
   ```
   PLAN_PATH=<output-directory>/plans/implementation-plan.md
   ```

---

## Phase 2: Design Document (`/eng-design-creator`)

### Step 2.1: Prepare Arguments

Build the arguments string for `/eng-design-creator`. The arguments must include:

1. The path to the implementation plan: `$PLAN_PATH`
2. An explicit instruction to save the design document to: `<output-directory>/plans/design.md`

Format the arguments as:

```
<output-directory>/plans/implementation-plan.md

IMPORTANT OUTPUT INSTRUCTIONS: Save the design document to <output-directory>/plans/design.md — do NOT save it alongside the research document or ask where to save it, the path has been predetermined.
```

### Step 2.2: Invoke the Skill

Use the Skill tool to invoke `/eng-design-creator` with the prepared arguments.

**This skill WILL ask the user interactive questions** about design decisions, trade-offs, and architectural choices. These questions are critical to producing a design that reflects the user's intent. Let all Q&A flow through naturally.

The skill also has an approval step at the end — let the user approve or request changes to the design.

### Step 2.3: Post-Skill Housekeeping

After `/eng-design-creator` completes:

1. **Verify the output file exists** at `<output-directory>/plans/design.md`. If the skill saved it elsewhere, move it.

2. **Update `plans/index.md`** — add the design document:

   ```markdown
   | [`design.md`](design.md) | Engineering design document — architectural decisions, component design, data model, API design, and rationale | [timestamp] |
   ```

3. **Note:** `/eng-design-creator` may have updated the implementation plan (it adds a "Design Document" section upon approval). This is expected — the implementation plan at `$PLAN_PATH` may now be modified.

4. **Record the design doc path** for use in subsequent phases:
   ```
   DESIGN_PATH=<output-directory>/plans/design.md
   ```

---

## Phase 3: Test Planning (`/eng-test-planning`)

### Step 3.1: Prepare Arguments

Build the arguments string for `/eng-test-planning`:

```
<output-directory>/plans/implementation-plan.md
```

The skill will also look for the companion `design.md` in the same directory automatically.

### Step 3.2: Invoke the Skill

Use the Skill tool to invoke `/eng-test-planning` with the prepared arguments.

This skill typically has fewer interactive questions — it analyzes the plan and design, studies existing test patterns in the codebase, and appends a test plan section to the implementation plan.

### Step 3.3: Post-Skill Housekeeping

After `/eng-test-planning` completes:

1. **Verify the test plan was appended** to `implementation-plan.md`. Read the end of the file to confirm a new test plan section exists.

2. **Update `plans/index.md`** — add a note that the implementation plan now includes the test strategy:

   ```markdown
   | [`implementation-plan.md`](implementation-plan.md) | Engineering implementation plan — includes appended test strategy (added [timestamp]) | [original timestamp] |
   ```

   (Update the existing row's description, don't add a duplicate row.)

---

## Phase 4: Task Planning (`/eng-task-planning`)

### Step 4.1: Prepare Arguments

Build the arguments string for `/eng-task-planning`. The arguments must include:

1. The path to the implementation plan
2. An explicit instruction to save the task plan to the `tasks/` directory

Format the arguments as:

```
<output-directory>/plans/implementation-plan.md

IMPORTANT OUTPUT INSTRUCTIONS: Save the task planning document to <output-directory>/tasks/task-plan.md — do NOT save it in the plans/ directory or alongside the research document. The design document is located at <output-directory>/plans/design.md.
```

### Step 4.2: Invoke the Skill

Use the Skill tool to invoke `/eng-task-planning` with the prepared arguments.

### Step 4.3: Post-Skill Housekeeping

After `/eng-task-planning` completes:

1. **Verify the output file exists** at `<output-directory>/tasks/task-plan.md`. If the skill saved it elsewhere, move it.

2. **Update `tasks/index.md`** — add the task plan to the documents table:

   ```markdown
   | [`task-plan.md`](task-plan.md) | Implementation task plan with phased breakdown, estimates, dependencies, and parallel work optimization | [timestamp] |
   ```

3. **Populate the Task Tracking table** in `tasks/index.md` by extracting task information from the task plan. Read the task plan and extract every task from the phase tables. For each task, add a row:

   ```markdown
   | T1.1 | [Task Name] | Foundation | 1.0d | None | [ ] |
   | T1.2 | [Task Name] | Foundation | 1.5d | T1.1 | [ ] |
   ```

   Include ALL tasks from all phases. Preserve the task ordering from the plan.

4. **Check for individual task documents** — if `/eng-task-planning` created separate per-task files, ensure they are in the `tasks/` directory and add each to the index.

---

## Phase 5: Verification Planning (`/eng-verification-creator`)

### Step 5.1: Prepare Arguments

Build the arguments string for `/eng-verification-creator`:

```
<output-directory>/plans/implementation-plan.md <output-directory>/plans/design.md <output-directory>/verifications
```

### Step 5.2: Invoke the Skill

Use the Skill tool to invoke `/eng-verification-creator` with the prepared arguments.

This skill may ask the user to approve the planned verification structure before writing documents. Let this Q&A flow through.

### Step 5.3: Post-Skill Housekeeping

After `/eng-verification-creator` completes:

1. **Discover all created files** in `<output-directory>/verifications/`. Use Glob to find all `.md` files recursively.

2. **Update `verifications/index.md`**. The verification skill creates its own `README.md` — the index.md should point to it and also list all environment folders and their contents.

   Structure the verifications index like this:

   ```markdown
   # Verifications Index

   **Parent:** [../index.md](../index.md)
   **Last Updated:** [timestamp]

   ---

   | Document | Description | Created |
   |----------|-------------|---------|
   | [`README.md`](README.md) | Verification suite overview, folder index, and spec coverage matrix | [timestamp] |

   ## Environment Folders

   [For each numbered folder, list its contents in order:]

   ### [01-folder-name/](01-folder-name/)

   | # | Document | Description | Created |
   |---|----------|-------------|---------|
   | 1 | [`01-file.md`](01-folder-name/01-file.md) | [description] | [timestamp] |
   | 2 | [`02-file.md`](01-folder-name/02-file.md) | [description] | [timestamp] |
   ```

   **Respect numeric ordering** — list folders and files in their numbered sequence.

---

## Phase 6: Extract Follow-Ups

After all five skills have completed, scan all generated documents for open questions, gaps, assumptions, and deferred items.

### Step 6.1: Scan for Open Items

Read through all documents in `plans/` and `tasks/` looking for:

- **"Open Questions"** sections (all skills produce these)
- **"Gaps"** or **"Missing Information"** sections
- **"Assumptions Made"** sections
- **"Risk Assessment"** sections with unresolved risks
- **"Open Items"** sections from the design document
- Any items explicitly marked as deferred, TBD, or "pending research"

### Step 6.2: Create Follow-Up Documents

Create a consolidated follow-up document at `<output-directory>/follow-ups/open-items.md`:

```markdown
# Open Items and Follow-Ups

**Feature:** [Feature name]
**Extracted From:** Implementation plan, design document, task plan
**Created:** [ISO 8601 timestamp with MST offset]

---

## Open Questions

_Questions that need answers before or during implementation._

| # | Question | Source Document | Affects | Suggested Owner |
|---|----------|-----------------|---------|-----------------|
| 1 | [Question text] | [plans/implementation-plan.md § Gaps] | [What it impacts] | [Who might know] |

---

## Assumptions to Validate

_Assumptions made during planning that should be confirmed._

| # | Assumption | Source Document | Risk if Wrong |
|---|-----------|-----------------|---------------|
| 1 | [Assumption] | [plans/design.md § Assumptions] | [Impact] |

---

## Deferred Items

_Work or decisions explicitly deferred to later._

| # | Item | Source Document | When to Address |
|---|------|-----------------|-----------------|
| 1 | [Item] | [Source] | [Trigger or timeline] |

---

## Unresolved Risks

_Risks identified during planning that lack mitigation._

| # | Risk | Source Document | Impact | Suggested Mitigation |
|---|------|-----------------|--------|----------------------|
| 1 | [Risk] | [Source] | [Impact level] | [Suggestion] |
```

### Step 6.3: Update Follow-Ups Index

Update `<output-directory>/follow-ups/index.md`:

```markdown
| [`open-items.md`](open-items.md) | Consolidated open questions, assumptions, deferred items, and unresolved risks extracted from all planning documents | [timestamp] |
```

---

## Phase 7: Finalize All Index Files

### Step 7.1: Final Pass on All Index Files

Re-read every `index.md` file and verify:

- Every document that exists in the folder is listed in the index
- Timestamps are in ISO 8601 format with MST offset (e.g., `2026-04-14T11:30:00-06:00`)
- Numeric ordering is preserved (folders and files with numeric prefixes are listed in sequence)
- The tasks index has the full task tracking table populated
- All links are correct relative paths
- The root index.md points to all five child index files

### Step 7.2: Update Root Index

Add a summary section to the root `index.md` with document counts and status:

```markdown
---

## Pipeline Summary

| Phase | Skill | Status | Primary Output |
|-------|-------|--------|----------------|
| 1 | `/eng-plan-creator` | Complete | [`plans/implementation-plan.md`](plans/implementation-plan.md) |
| 2 | `/eng-design-creator` | Complete | [`plans/design.md`](plans/design.md) |
| 3 | `/eng-test-planning` | Complete | Test strategy appended to implementation plan |
| 4 | `/eng-task-planning` | Complete | [`tasks/task-plan.md`](tasks/task-plan.md) |
| 5 | `/eng-verification-creator` | Complete | [`verifications/README.md`](verifications/README.md) |

**Total Documents:** [count]
**Open Follow-Up Items:** [count from follow-ups/open-items.md]
**Task Count:** [total tasks from task plan]
**Estimated Effort:** [total from task plan] days
```

### Step 7.3: Present Summary to User

After all phases are complete, present a final summary:

1. List all documents created with their paths
2. Highlight the number of open follow-up items that need resolution
3. Summarize the task plan (phases, total effort, critical path)
4. Note if any skills encountered issues or gaps
5. Suggest next steps (typically: resolve open questions, then begin task implementation)

---

## Error Handling

### If a Skill Fails or Produces Incomplete Output

- Do NOT skip the skill. Inform the user what went wrong.
- Ask the user whether to retry the skill, skip it and continue, or abort the pipeline.
- If skipping, create a placeholder document explaining what was skipped and why, and add it to the relevant index.

### If a Skill Saves Output to the Wrong Location

- Move the file to the correct location.
- Update any internal cross-references within the document (e.g., relative links to other docs).
- Log what was moved so the user knows.

### If MCP Tools Are Unavailable

- `/eng-plan-creator` and `/eng-verification-creator` rely heavily on Jira/Confluence MCP tools.
- If MCP tools fail, inform the user and ask whether to proceed with only the information available in the provided file-based specs, or to abort and fix MCP connectivity first.

---

## Important Guidelines

1. **Sequential execution is non-negotiable.** Each skill depends on the output of the previous one. Never run skills in parallel or out of order.

2. **Q&A must reach the user.** `/eng-plan-creator` and `/eng-design-creator` ask the user important questions about requirements and design trade-offs. These questions shape the entire downstream pipeline. Never intercept, skip, or answer them yourself.

3. **Index files are your responsibility, not the sub-skills'.** After each skill completes, YOU must update the relevant index.md. The sub-skills don't know about the folder structure.

4. **Respect the output paths.** Each skill has default ideas about where to save files. Override these via the arguments you pass. If a skill ignores the override, move the file after it completes.

5. **Timestamps in MST.** All timestamps in index files must use ISO 8601 format with MST offset: `YYYY-MM-DDTHH:MM:SS-06:00` (or `-07:00` during MDT). Use the current time when creating each document.

6. **Numeric ordering matters.** The verifications folder uses numbered prefixes (01-, 02-, etc.). When listing these in index files, preserve the numeric order exactly.

7. **The follow-ups extraction is a synthesis step.** Don't just copy/paste — consolidate duplicates, normalize language, and attribute each item to its source document so it's traceable.

8. **The task index is richer than other indexes.** It includes the full task tracking table with completion checkboxes. This is intentional — it serves as the canonical task status tracker for partner AI processes.
