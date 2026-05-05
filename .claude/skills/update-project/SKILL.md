---
name: update-project
description: "Update an existing product/project's PRD and documentation based on new context, changed requirements, or resolved questions. Peer to /new-project — reads existing project artifacts, collaboratively refines the PRD, updates user scenarios and supplementary docs, and produces a changelog. Does NOT propagate into features/ — use /eng-feature-followup for that."
argument-hint: "<project directory> <updated context: description, URLs, file paths, or free-text describing changes>"
---

# Update Project Skill

You are orchestrating an **update pass** on an existing product/project created by `/new-project` (or an equivalent manual process). The user has new context — changed requirements, answered questions, new constraints, stakeholder feedback, or scope adjustments — and you need to propagate those changes through the project documentation.

**Scope boundary:** This skill updates project-level documents only: the PRD, user scenarios (verifications), supplementary documents, and knowledge base. It does NOT propagate changes into `features/` subdirectories — those contain engineering-level docs managed by `/eng-feature-followup`. After completing an update, you will identify which features (if any) may be affected so the user can run `/eng-feature-followup` on them.

## Input

The user has provided the following context:

$ARGUMENTS

You need two inputs. If either is missing, use AskUserQuestion to ask:

1. **Project directory** — the root directory of the existing project documentation (created by `/new-project` or equivalent). This directory should contain `prd.md`, `documents/`, `features/`, `kb/`, and `verifications/` with their respective index files. Example: `/Users/jscott/Developer/sources/personal/notebook/projects/fuzzball/projects/my-project`
2. **Updated context** — what changed. This can be any combination of:
   - Jira issue keys/URLs with updated specifications
   - Confluence page URLs with revised requirements
   - Local file paths to updated spec documents
   - Free-text description of changes, additions, or corrections
   - Answers to open questions from the PRD
   - At least one source of updated context is required.

---

## Phase 0: Assess Current State and Prepare for Updates

### Step 0.1: Validate Inputs

- Confirm the project directory exists and contains the expected structure.
- Check for the existence of key documents:
  - `prd.md`
  - `documents/index.md`
  - `features/index.md`
  - `kb/index.md`
  - `verifications/index.md`
- Note which documents exist and which are missing. Missing documents are not an error — the update will create them if needed.
- Confirm at least one source of updated context was provided.

### Step 0.2: Read Existing Documents

Read the following documents to understand the current project state:

1. **Root `index.md`** — for project name, status, document counts
2. **`prd.md`** — the full PRD. Pay special attention to:
   - Section 4 (Goals and Non-Goals) — scope boundaries
   - Section 6 (Functional Requirements) — requirement IDs and priorities
   - Section 12 (Open Questions) — which may now be answered
   - Appendix C (Decision Log) — established decisions
3. **`verifications/index.md`** and all verification documents — current user scenarios
4. **`documents/index.md`** — what supplementary docs exist
5. **`kb/index.md`** — what KB entries exist
6. **`features/index.md`** — what engineering features exist (for impact assessment)

Extract:
- The **project name** and **project slug**
- The current **requirement IDs** (FR-XXX, NFR-XXX) — needed to maintain numbering continuity
- The current **user scenario IDs** (US-XXX) — same reason
- The list of **open questions** — to check if the update resolves any
- The list of **features** — to assess which may be affected by changes

### Step 0.3: Analyze the Updated Context

Read and analyze all the updated context the user provided:

- If **Jira URLs** are provided, fetch the updated issues using Atlassian MCP tools.
- If **Confluence URLs** are provided, fetch the updated pages.
- If **file paths** are provided, read the files.
- If **free-text** is provided, parse the described changes.

Produce a **Change Summary** that captures:
- What requirements are **new** (not in the current PRD)
- What requirements have **changed** (different from current PRD)
- What requirements have been **removed** or descoped
- What open questions are now **resolved** by the new context
- What new questions or concerns have been **introduced**

### Step 0.4: Create or Append to the Changelog

Create (or append to) a changelog file at `<project-directory>/documents/changelog.md`.

**New changelog file structure:**

```markdown
# Project Change Log

**Project:** [Project name]
**Jira:** [Epic key(s)]

---

## [ISO 8601 timestamp with MST offset] — Project Update

### Change Context

[Summarize the updated context the user provided — what triggered this update]

### Sources

- [List each Jira URL, Confluence URL, file path, or "user-provided text" that was input]

### Change Summary

| # | Type | Description | PRD Sections Affected |
| - | ---- | ----------- | --------------------- |
| 1 | New / Changed / Removed / Resolved | [What changed] | [Which PRD sections need updates] |

### Documents Updated

_Populated as each phase completes._

| Phase | Document | Change Type | Summary |
| ----- | -------- | ----------- | ------- |
```

If the changelog already exists, prepend a new `## [timestamp] — Project Update` section after the header but before previous entries.

### Step 0.5: Inform the User

Tell the user:

- What existing documents were found and their current state
- A summary of the changes you identified from their input
- Which PRD sections are likely to need the most revision
- Which features (if any) in `features/` may be affected by these changes — flag these for later `/eng-feature-followup` runs
- That you may ask clarifying questions about how to incorporate the changes

---

## Phase 1: Collaborative Q&A on Changes

Unlike `/new-project` which starts from scratch, this Q&A is focused on the **delta** — how the changes affect the existing PRD.

### Step 1.1: Identify Ambiguities

Review the Change Summary and identify:

- Changes that have multiple valid interpretations
- New requirements that create tension with existing requirements or non-goals
- Removed requirements that may have downstream implications
- Resolved questions whose answers create new design decisions

### Step 1.2: Ask Targeted Questions

If ambiguities exist, use AskUserQuestion to resolve them. Keep this focused:

- Only ask about the **changes**, not about settled requirements
- Reference specific PRD sections and requirement IDs
- Frame questions in terms of the **delta** — "This new requirement FR-NEW conflicts with non-goal NG-3. Should we revise the non-goal or constrain the requirement?"

If the changes are unambiguous, skip this phase and proceed to Phase 2.

### Step 1.3: Confirm Scope of Update

Before modifying the PRD, confirm with the user:

```
Based on the changes and our discussion, here's what I plan to update:

- **PRD sections to modify:** [list]
- **New requirements to add:** [list with proposed IDs]
- **Requirements to remove or descope:** [list]
- **Open questions to resolve:** [list]
- **New open questions to add:** [list]

Shall I proceed with these updates?
```

---

## Phase 2: Update the PRD

### Step 2.1: Revise the PRD

Update `<project-directory>/prd.md` incorporating all changes:

1. **Update metadata** — bump version (1.0 → 1.1), update Last Updated timestamp, update Status if appropriate
2. **Revise affected sections** — modify requirements, goals, constraints as determined in Phase 1
3. **Maintain numbering** — new requirements get the next available FR-XXX / NFR-XXX number. Do NOT renumber existing requirements.
4. **Update Open Questions** — remove resolved questions (move to Decision Log), add new questions
5. **Update Decision Log** — add entries for decisions made during this update, including what changed and why
6. **Preserve unchanged content** — do not rewrite sections unaffected by the changes

### Step 2.2: Update Changelog

Add the PRD update to the changelog's "Documents Updated" table:

```markdown
| 1 - PRD | `prd.md` | Updated | [Brief summary: e.g., "Added FR-015 through FR-018, resolved OQ-3 and OQ-5, descoped NFR-007"] |
```

---

## Phase 3: Update User Scenario Verifications

### Step 3.1: Assess Impact on Scenarios

Compare the updated PRD against existing verification documents:

- **New requirements** → need new scenarios
- **Changed requirements** → existing scenarios may need revision
- **Removed requirements** → scenarios referencing them should be removed or marked descoped
- **Resolved questions** → may unlock scenarios that were previously incomplete

### Step 3.2: Update Verification Documents

For each affected verification document:

1. **Add new scenarios** for new requirements. Use the next available US-XXX number.
2. **Revise scenarios** whose underlying requirements changed. Update the PRD Reference, steps, expected outcomes, and acceptance criteria.
3. **Remove or mark descoped** scenarios for removed requirements. Do not silently delete — add a `~~Descoped~~` marker or move to a "Descoped Scenarios" section at the bottom.
4. **Update the Coverage Matrix** to reflect the current state.

All Must Have requirements must show "Covered" status in the coverage matrix.

### Step 3.3: Update Changelog

Add the verification update to the changelog.

---

## Phase 4: Update Supplementary Documents and Knowledge Base

### Step 4.1: Assess Impact on Documents

Check if the changes affect any existing supplementary documents in `documents/` or KB entries in `kb/`:

- Does a technology comparison need updating because a constraint changed?
- Does a domain concept in `kb/` need revision because terminology or scope shifted?
- Should new supplementary documents or KB entries be created based on the new context?

### Step 4.2: Update or Create Documents

- **Update** existing documents that are affected by the changes
- **Create** new documents if the update surfaced substantial new reference material
- **Do NOT delete** existing documents unless the user explicitly requests it — mark them as superseded instead

### Step 4.3: Update Changelog

Add document and KB updates to the changelog.

---

## Phase 5: Finalize

### Step 5.1: Complete the Changelog Entry

Ensure the changelog entry's "Documents Updated" table is fully populated. Add an impact summary:

```markdown
### Impact Summary

- **Requirements:** [count new] new, [count changed] changed, [count removed] removed
- **Open questions:** [count resolved] resolved, [count new] new, [count continuing] continuing
- **User scenarios:** [count added] added, [count revised] revised, [count removed] removed
- **Supplementary docs:** [count updated] updated, [count created] created
- **KB entries:** [count updated] updated, [count created] created

### Features Potentially Affected

_The following features in `features/` may need updates via `/eng-feature-followup`:_

| Feature | Reason | Urgency |
| ------- | ------ | ------- |
| [Feature name/slug] | [Which PRD changes affect it] | [High/Medium/Low] |

_If no features exist yet, this section can be omitted._
```

### Step 5.2: Update All Index Files

Re-read every `index.md` and ensure:

- Every document that exists in each folder is listed
- Timestamps are updated where documents were modified
- The changelog is listed in `documents/index.md`
- All links are correct relative paths

### Step 5.3: Update Root Index

Update the root `index.md`:

1. Update the Status field (e.g., "Updated [date]")
2. Update document counts
3. Add or update a **Revision History** section:

```markdown
---

## Revision History

| Date | Type | Summary | Change Log |
| ---- | ---- | ------- | ---------- |
| [original date] | Initial | Created via /new-project | — |
| [today's date] | Update | [Brief summary of what changed] | [`documents/changelog.md`](documents/changelog.md) |
```

### Step 5.4: Present Summary to User

After all phases are complete, present a final summary:

1. List all documents that were updated with a brief description of what changed
2. List any new documents created
3. Report the current state of requirements (total, by priority)
4. Report the current state of open questions (resolved, new, continuing)
5. Report verification coverage (Must Have coverage percentage)
6. **Flag features that need `/eng-feature-followup`** — this is critical. If engineering features exist in `features/` that reference changed requirements, call them out explicitly with the specific changes that affect them.
7. Suggest next steps

---

## Error Handling

### If the PRD Is Missing

The PRD is the core document. If `prd.md` doesn't exist:

- Ask the user if they want to run `/new-project` instead to create the project from scratch.
- Do not attempt to create a PRD from scratch in update mode.

### If the Update Context Is Ambiguous

- Ask questions. Do not guess at the user's intent for product-level decisions.
- If after 2 rounds of Q&A the intent is still unclear, document the ambiguity as a new open question in the PRD.

### If MCP Tools Are Unavailable

- If the updated context includes Jira/Confluence URLs but MCP tools fail, inform the user and ask whether to proceed with only the textual context provided, or to abort and fix MCP connectivity first.

---

## Important Guidelines

1. **Scope boundary is project-level.** This skill updates the PRD, user scenarios, documents, and KB. It does NOT touch anything inside `features/`. Feature-level updates are the domain of `/eng-feature-followup`.

2. **Flag affected features.** The most important output beyond the PRD update is the list of features that may be stale. The user needs this to know which `/eng-feature-followup` runs to schedule.

3. **Maintain numbering continuity.** Never renumber existing FR-XXX, NFR-XXX, or US-XXX IDs. New items get the next available number. Removed items are marked descoped, not deleted and renumbered.

4. **The changelog is your audit trail.** Every change must be traceable through the changelog. Update it after every phase.

5. **Don't re-litigate settled decisions.** If a requirement or decision is unchanged, preserve it as-is. Only present questions about things that are actually affected by the update.

6. **Q&A is focused, not exhaustive.** Unlike `/new-project` which asks broad questions to fill a blank PRD, `/update-project` asks narrow questions about the specific changes. Respect the user's time.

7. **Timestamps in MST.** All timestamps must use ISO 8601 format with MST offset.

8. **Preserve the Decision Log.** Append to Appendix C — never overwrite or remove existing decisions. New decisions from this update get added with today's date.

9. **Descoped ≠ deleted.** Removed requirements and scenarios should be marked as descoped with a note about why, not silently deleted. This preserves the decision trail.
