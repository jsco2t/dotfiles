---
name: eng-feature-followup
description: Processes updated specifications or changed requirements through the full engineering planning pipeline, updating existing feature documentation. Peer to /new-eng-feature — accepts a feature documentation directory and new context (Jira updates, textual changes, or file-based specs), then sequentially re-runs /eng-plan-creator, /eng-design-creator, /eng-test-planning, /eng-task-planning, and /eng-verification-creator in update mode — revising documents, maintaining indexes, and producing a change log.
argument-hint: "<feature documentation directory> <updated context: Jira URLs, text description, or file paths describing changes>"
---

# Engineering Feature Follow-Up Skill

You are orchestrating an **update pass** through the complete engineering planning pipeline for an existing feature. A previous `/new-eng-feature` run (or equivalent manual process) produced a set of feature documentation. Now the specifications have changed, new requirements have emerged, or gaps from the original planning need to be addressed.

Your job is to take the **updated context** the user provides and propagate those changes through the same five-skill pipeline used by `/new-eng-feature` — but this time each skill operates in **update mode**, revising existing documents rather than creating them from scratch.

**You MUST run the skills in this exact order:**

1. `/eng-plan-creator` — revises the implementation plan
2. `/eng-design-creator` — revises the design document
3. `/eng-test-planning` — revises the test plan
4. `/eng-task-planning` — revises the task breakdown
5. `/eng-verification-creator` — revises the verification documents

**Each skill must fully complete before the next one starts.** Skills 1 and 2 will ask the user interactive questions — these MUST flow through to the user. Do not skip, defer, or answer on behalf of the user.

## Input

The user has provided the following context:

$ARGUMENTS

You need three inputs. If any are missing, use AskUserQuestion to ask:

1. **Feature documentation directory** — the root directory of the existing feature documentation (created by a prior `/new-eng-feature` run or equivalent). This directory should contain `plans/`, `tasks/`, `follow-ups/`, `verifications/`, and `research/` subdirectories with their respective documents and index files. Example: `/Users/jscott/Developer/sources/personal/notebook/projects/fuzzball/features/FUZZ-XXXX`
2. **Updated context** — what changed. This can be any combination of:
   - Jira issue keys/URLs with updated specifications
   - Confluence page URLs with revised requirements
   - Local file paths to updated spec documents
   - Free-text description of changes, additions, or corrections
   - At least one source of updated context is required.
3. **Code repository path** — the repository where the code changes will happen. If you are already inside the target repo (check the current working directory), this is optional.

---

## Phase 0: Assess Current State and Prepare for Updates

Before invoking any skill, understand the existing documentation and the scope of change.

### Step 0.1: Validate Inputs

- Confirm the feature documentation directory exists and contains the expected structure.
- Check for the existence of key documents:
  - `plans/implementation-plan.md`
  - `plans/design.md`
  - `tasks/task-plan.md`
  - `verifications/` (directory with content)
  - `follow-ups/open-items.md`
- Note which documents exist and which are missing. Missing documents are not an error — the pipeline will create them. But their absence affects how you frame arguments to each skill.
- Confirm at least one source of updated context was provided.
- Confirm the code repository is accessible.

### Step 0.2: Read Existing Documents

Read the following documents to understand the current planning state:

1. **Root `index.md`** — for feature name, Jira keys, repository path, and pipeline summary
2. **`plans/implementation-plan.md`** — for current requirements, gaps, and approach
3. **`plans/design.md`** — for current architectural decisions and rationale
4. **`tasks/task-plan.md`** — for current task breakdown and estimates
5. **`follow-ups/open-items.md`** — for currently open questions and deferred items

Extract from these documents:
- The **feature name** and **feature slug** (for file naming consistency)
- The **Jira epic key(s)** and any referenced Jira/Confluence sources
- The **repository path**
- A summary of the **current state** of planning (what's been decided, what's open)

### Step 0.3: Analyze the Updated Context

Read and analyze all the updated context the user provided:

- If **Jira URLs** are provided, fetch the updated issues using Atlassian MCP tools and compare with what's referenced in the existing documents.
- If **Confluence URLs** are provided, fetch the updated pages.
- If **file paths** are provided, read the files.
- If **free-text** is provided, parse the described changes.

Produce a concise **Change Summary** that captures:
- What requirements are **new** (not in the original spec)
- What requirements have **changed** (different from original spec)
- What requirements have been **removed** or descoped
- What open questions or gaps from the original planning are now **resolved**
- What new questions or concerns have been **introduced**

### Step 0.4: Create the Change Log Entry

Create (or append to) a change log file at `<doc-directory>/follow-ups/changelog.md`. If this is the first followup, create the file with a header. If it already exists, prepend a new entry.

**New changelog file structure:**

```markdown
# Change Log

**Feature:** [Feature name]
**Jira:** [Epic key(s)]

---

## [ISO 8601 timestamp with MST offset] — Follow-Up Update

### Change Context

[Summarize the updated context the user provided — what triggered this update]

### Sources

- [List each Jira URL, Confluence URL, file path, or "user-provided text" that was input]

### Change Summary

| # | Type | Description | Affects |
|---|------|-------------|---------|
| 1 | New / Changed / Removed / Resolved | [What changed] | [Which documents will need updates] |

### Documents Updated

_Populated as each phase completes._

| Phase | Document | Change Type | Summary |
|-------|----------|-------------|---------|
```

**Appending to existing changelog:**

Add a new `## [timestamp] — Follow-Up Update` section at the top of the entries (after the header but before previous entries), following the same structure.

### Step 0.5: Inform the User

Tell the user:

- What existing documents were found and their current state
- A summary of the changes you identified from their input
- That you are about to begin the update pipeline
- That `/eng-plan-creator` and `/eng-design-creator` will ask them interactive questions about how to incorporate the changes
- Which documents are likely to see the most significant revisions based on the change summary

---

## Phase 1: Update Implementation Plan (`/eng-plan-creator`)

### Step 1.1: Prepare Arguments

Build the arguments string for `/eng-plan-creator`. This is the critical framing step — the skill needs to understand it is **updating** an existing plan, not creating one from scratch.

The arguments must include:

1. All updated spec links the user provided (Jira URLs, Confluence URLs, file paths)
2. The path to the existing implementation plan as baseline context
3. An explicit instruction to update the existing document
4. The change summary from Phase 0

Format the arguments as:

```
<updated spec links provided by user>

IMPORTANT CONTEXT — UPDATE MODE:
This is an UPDATE to an existing implementation plan, not a new feature research task. An existing engineering implementation plan already exists at <doc-directory>/plans/implementation-plan.md — read it first to understand the current state of planning.

The following changes need to be incorporated:
<paste the Change Summary table from Phase 0>

Your task:
1. Read the existing implementation plan thoroughly
2. Research the updated specifications (Jira, Confluence, files provided above)
3. Analyze the codebase for any impact from the changes
4. Produce an UPDATED implementation plan that incorporates the new/changed requirements
5. Preserve unchanged sections — do not rewrite content that has not been affected by the updates
6. Clearly mark NEW or CHANGED content so reviewers can identify what was modified
7. Update the Gaps and Open Questions sections — resolve items that the new context answers, add new items that the changes introduce

IMPORTANT OUTPUT INSTRUCTIONS: Save the updated document to <doc-directory>/plans/implementation-plan.md — overwrite the existing file. Title it "Engineering Implementation Plan: [Feature Name] (Updated [date])".
```

### Step 1.2: Invoke the Skill

Use the Skill tool to invoke `/eng-plan-creator` with the prepared arguments.

**This skill will ask the user questions** about how to interpret the updated specifications or resolve ambiguities introduced by the changes. Let all Q&A flow through naturally — do not intercept or answer on behalf of the user.

### Step 1.3: Post-Skill Housekeeping

After `/eng-plan-creator` completes:

1. **Verify the output file exists** at `<doc-directory>/plans/implementation-plan.md`. If the skill saved it elsewhere, move it to the correct location.

2. **Update `plans/index.md`** — update the implementation plan entry to reflect the revision:

   ```markdown
   | [`implementation-plan.md`](implementation-plan.md) | Engineering implementation plan — updated [timestamp] to incorporate [brief change description] | [original timestamp] |
   ```

   (Update the existing row's description, don't add a duplicate row.)

3. **Update the changelog** — add the Phase 1 row to the "Documents Updated" table:

   ```markdown
   | 1 - Plan | `plans/implementation-plan.md` | Updated | [Brief summary of what changed in the plan] |
   ```

4. **Record the updated plan path:**
   ```
   PLAN_PATH=<doc-directory>/plans/implementation-plan.md
   ```

---

## Phase 2: Update Design Document (`/eng-design-creator`)

### Step 2.1: Prepare Arguments

Build the arguments string for `/eng-design-creator` with update framing:

```
<doc-directory>/plans/implementation-plan.md

IMPORTANT CONTEXT — UPDATE MODE:
This is an UPDATE to an existing design document, not a new design task. An existing design document already exists at <doc-directory>/plans/design.md — read it first to understand the current architectural decisions and rationale.

The implementation plan at the path above has just been updated to incorporate the following changes:
<paste the Change Summary table from Phase 0>

Your task:
1. Read both the UPDATED implementation plan and the EXISTING design document
2. Determine which design decisions are affected by the requirements changes
3. For affected decisions: re-evaluate the options considering the new context, present updated trade-offs to the user
4. For unaffected decisions: preserve them as-is — do not re-litigate settled decisions
5. Update component designs, data models, API designs, and test strategy as needed
6. Add or update risk assessments for any new or changed requirements

IMPORTANT OUTPUT INSTRUCTIONS: Save the updated design document to <doc-directory>/plans/design.md — overwrite the existing file.
```

### Step 2.2: Invoke the Skill

Use the Skill tool to invoke `/eng-design-creator` with the prepared arguments.

**This skill WILL ask the user interactive questions** about how specification changes affect design decisions. Only decisions that are impacted by the changes should be re-presented — the skill should NOT re-ask about decisions that are unaffected.

Let the approval step proceed naturally.

### Step 2.3: Post-Skill Housekeeping

After `/eng-design-creator` completes:

1. **Verify the output file exists** at `<doc-directory>/plans/design.md`.

2. **Update `plans/index.md`** — update the design document entry:

   ```markdown
   | [`design.md`](design.md) | Engineering design document — updated [timestamp] to reflect [brief change description] | [original timestamp] |
   ```

3. **Update the changelog** — add the Phase 2 row.

4. **Record the updated design path:**
   ```
   DESIGN_PATH=<doc-directory>/plans/design.md
   ```

---

## Phase 3: Update Test Planning (`/eng-test-planning`)

### Step 3.1: Prepare Arguments

Build the arguments string for `/eng-test-planning`:

```
<doc-directory>/plans/implementation-plan.md

IMPORTANT CONTEXT — UPDATE MODE:
The implementation plan and design document at this location have just been updated to incorporate specification changes. The existing test plan section in the implementation plan may need revision to cover new or changed requirements. Review the existing test plan section, identify what needs to change based on the updated requirements and design, and revise accordingly. Preserve test cases for unchanged functionality.
```

### Step 3.2: Invoke the Skill

Use the Skill tool to invoke `/eng-test-planning` with the prepared arguments.

### Step 3.3: Post-Skill Housekeeping

After `/eng-test-planning` completes:

1. **Verify the test plan section was updated** in `implementation-plan.md`.

2. **Update `plans/index.md`** — update the note about the test strategy:

   ```markdown
   | [`implementation-plan.md`](implementation-plan.md) | Engineering implementation plan — test strategy updated [timestamp] | [original timestamp] |
   ```

3. **Update the changelog** — add the Phase 3 row.

---

## Phase 4: Update Task Planning (`/eng-task-planning`)

### Step 4.1: Prepare Arguments

Build the arguments string for `/eng-task-planning`:

```
<doc-directory>/plans/implementation-plan.md

IMPORTANT CONTEXT — UPDATE MODE:
This is an UPDATE to an existing task plan. An existing task plan already exists at <doc-directory>/tasks/task-plan.md — read it first to understand the current task breakdown, estimates, and dependencies.

The implementation plan and design document have just been updated to incorporate specification changes. Your task:
1. Read the EXISTING task plan to understand current task breakdown
2. Read the UPDATED implementation plan and design to understand what changed
3. Produce an UPDATED task plan that accounts for the changes:
   - Add new tasks for new requirements
   - Modify existing tasks whose scope has changed
   - Remove or mark as descoped tasks for removed requirements
   - Re-evaluate estimates where scope has changed
   - Re-evaluate dependencies where task relationships have changed
4. Preserve task IDs for unchanged tasks where possible to maintain traceability

The design document is located at <doc-directory>/plans/design.md.

IMPORTANT OUTPUT INSTRUCTIONS: Save the updated task plan to <doc-directory>/tasks/task-plan.md — overwrite the existing file.
```

### Step 4.2: Invoke the Skill

Use the Skill tool to invoke `/eng-task-planning` with the prepared arguments.

### Step 4.3: Post-Skill Housekeeping

After `/eng-task-planning` completes:

1. **Verify the output file exists** at `<doc-directory>/tasks/task-plan.md`.

2. **Update `tasks/index.md`** — update the task plan entry and **re-populate the Task Tracking table** by extracting all tasks from the updated task plan. Replace the previous tracking table entirely with the new task list:

   ```markdown
   | Task ID | Task Name | Phase | Estimate | Dependencies | Completed |
   |---------|-----------|-------|----------|--------------|-----------|
   | T1.1 | [Task Name] | Foundation | 1.0d | None | [ ] |
   ```

   For tasks that existed in the previous tracking table AND still exist in the updated plan, **preserve their Completed status**. Read the old `tasks/index.md` before overwriting to capture existing completion states.

3. **Update the changelog** — add the Phase 4 row.

---

## Phase 5: Update Verification Planning (`/eng-verification-creator`)

### Step 5.1: Prepare Arguments

Build the arguments string for `/eng-verification-creator`:

```
<doc-directory>/plans/implementation-plan.md <doc-directory>/plans/design.md <doc-directory>/verifications

IMPORTANT CONTEXT — UPDATE MODE:
The implementation plan and design document have been updated to incorporate specification changes. Existing verification documents are already present in the output directory. Your task:
1. Read the updated plan and design to understand what changed
2. Review the existing verification documents to understand current coverage
3. Update, add, or remove verification tests to match the updated requirements
4. Ensure the Spec Coverage Matrix reflects 100% coverage of the UPDATED specifications
5. Preserve existing verifications for unchanged functionality — do not rewrite tests that are still valid
```

### Step 5.2: Invoke the Skill

Use the Skill tool to invoke `/eng-verification-creator` with the prepared arguments.

Let the approval Q&A flow through to the user.

### Step 5.3: Post-Skill Housekeeping

After `/eng-verification-creator` completes:

1. **Discover all verification files** in `<doc-directory>/verifications/` using Glob.

2. **Update `verifications/index.md`** — rebuild the index to reflect the current set of verification documents. Follow the same structure as `/new-eng-feature` Phase 5.3 (README link, environment folder listings with numeric ordering).

3. **Update the changelog** — add the Phase 5 row.

---

## Phase 6: Update Follow-Ups

After all five skills have completed, refresh the open items tracking.

### Step 6.1: Scan for Open Items

Read through all updated documents in `plans/` and `tasks/` looking for:

- **"Open Questions"** sections
- **"Gaps"** or **"Missing Information"** sections
- **"Assumptions Made"** sections
- **"Risk Assessment"** sections with unresolved risks
- **"Open Items"** sections from the design document
- Any items explicitly marked as deferred, TBD, or "pending research"

### Step 6.2: Update Open Items Document

Read the existing `<doc-directory>/follow-ups/open-items.md` to understand the previous open items.

Create an updated version that:

1. **Preserves resolved items** — items from the previous version that are now resolved by the updated context should be moved to a new "Resolved Items" section at the bottom with a note about what resolved them
2. **Updates continuing items** — items that are still open but have new context should be updated
3. **Adds new items** — new open questions, assumptions, deferred items, and risks from the updated documents
4. **Removes stale items** — items that no longer apply due to descoped requirements

Add a **"Resolved Items"** section if one doesn't exist:

```markdown
---

## Resolved Items

_Previously open items that have been resolved._

| # | Item | Original Source | Resolved By | Resolution Date |
|---|------|-----------------|-------------|-----------------|
| 1 | [Item] | [Source doc] | [What resolved it — e.g., "Updated spec FUZZ-1234"] | [timestamp] |
```

### Step 6.3: Update Follow-Ups Index

Update `<doc-directory>/follow-ups/index.md` to include entries for both `open-items.md` and `changelog.md`:

```markdown
| [`open-items.md`](open-items.md) | Consolidated open questions, assumptions, deferred items, and unresolved risks — updated [timestamp] | [original timestamp] |
| [`changelog.md`](changelog.md) | Change log tracking all follow-up updates to feature documentation | [timestamp of first entry] |
```

---

## Phase 7: Finalize the Change Log and All Index Files

### Step 7.1: Complete the Change Log Entry

Go back to the changelog entry created in Phase 0.4 and ensure the "Documents Updated" table is fully populated with entries from all 5 phases. Add a final summary row:

```markdown
### Impact Summary

- **Requirements changes:** [count new / changed / removed]
- **Design decisions revisited:** [count]
- **Tasks added/modified/removed:** [added / modified / removed]
- **Verification tests added/modified/removed:** [added / modified / removed]
- **Open items:** [count resolved] resolved, [count new] new, [count continuing] continuing
```

### Step 7.2: Final Pass on All Index Files

Re-read every `index.md` file and verify:

- Every document that exists in the folder is listed in the index
- Timestamps are in ISO 8601 format with MST offset (e.g., `2026-04-14T11:30:00-06:00`)
- Numeric ordering is preserved in verifications
- The tasks index has the full task tracking table populated with preserved completion states
- All links are correct relative paths
- The root index.md is up to date

### Step 7.3: Update Root Index

Update the root `index.md` with:

1. A status change if appropriate (e.g., "Updated [date]")
2. An updated Pipeline Summary table showing the latest pass
3. Updated document counts and effort totals

Add or update a **"Revision History"** section in the root `index.md`:

```markdown
---

## Revision History

| Date | Type | Summary | Change Log |
|------|------|---------|------------|
| [original date] | Initial | Created via /new-eng-feature pipeline | — |
| [today's date] | Follow-Up | [Brief summary of what changed] | [`follow-ups/changelog.md`](follow-ups/changelog.md) |
```

### Step 7.4: Present Summary to User

After all phases are complete, present a final summary:

1. List all documents that were updated with a brief description of what changed in each
2. Highlight any NEW documents that were created (not just updated)
3. Summarize the net change in scope (tasks added/removed, effort delta)
4. Report the current state of open items (resolved, new, continuing)
5. If any skills encountered issues or had to make assumptions, flag them
6. Suggest next steps (typically: review the changelog, resolve new open questions, update task assignments)

---

## Error Handling

### If a Skill Fails or Produces Incomplete Output

- Do NOT skip the skill. Inform the user what went wrong.
- Ask the user whether to retry the skill, skip it and continue, or abort the pipeline.
- If skipping, note the skip in the changelog with the reason.

### If a Skill Overwrites Instead of Updating

- This is acceptable — the skills don't have native "diff mode." The orchestrator's job is to provide enough context in the arguments that the skill preserves what should be preserved.
- After each skill completes, spot-check that key unchanged sections were preserved. If critical content was lost, inform the user and ask whether to retry with stronger preservation instructions.

### If Existing Documents Are Missing

- If `plans/implementation-plan.md` is missing, the pipeline cannot proceed. Ask the user to either provide the path or run `/new-eng-feature` first.
- If `plans/design.md` is missing, skip Phase 2 (design update) and note in the changelog that a design document needs to be created separately.
- If `tasks/task-plan.md` is missing, Phase 4 will create it fresh — this is fine.
- If `verifications/` is empty, Phase 5 will create documents fresh — this is fine.
- If `follow-ups/open-items.md` is missing, Phase 6 will create it fresh — this is fine.

### If MCP Tools Are Unavailable

- If the updated context includes Jira/Confluence URLs but MCP tools fail, inform the user and ask whether to proceed with only the textual context provided, or to abort and fix MCP connectivity first.

---

## Important Guidelines

1. **Sequential execution is non-negotiable.** Each skill depends on the output of the previous one. Never run skills in parallel or out of order.

2. **Q&A must reach the user.** `/eng-plan-creator` and `/eng-design-creator` will ask about how to interpret the changes. These questions are critical. Never intercept, skip, or answer them yourself.

3. **The changelog is your responsibility.** Update it after every phase. It is the primary artifact that distinguishes a followup from a fresh run — it creates an audit trail of what changed and why.

4. **Preserve completion states.** When rebuilding the task tracking table in `tasks/index.md`, read the old table first and carry forward `[x]` completion markers for tasks that still exist in the updated plan.

5. **Preserve unchanged content.** The update framing in your arguments to each sub-skill explicitly asks them to preserve sections unaffected by the changes. If a skill rewrites everything anyway, that's acceptable — the content will be re-derived from the same sources. But the goal is surgical updates, not full rewrites.

6. **Timestamps in MST.** All timestamps in index files and the changelog must use ISO 8601 format with MST offset: `YYYY-MM-DDTHH:MM:SS-06:00` (or `-07:00` during MDT).

7. **The change summary is the thread.** The Change Summary produced in Phase 0.3 is passed to every sub-skill as context. It is the single source of truth for what triggered this update. Keep it accurate and concise.

8. **Resolved items are not deleted items.** When an open question from `open-items.md` gets answered by the updated context, move it to the "Resolved Items" section — don't delete it. This preserves the decision trail.
