---
name: project-context
description: Load engineering project context from a /new-eng-feature documentation folder. Reads the root index, child indexes, implementation plan, design document, follow-ups, and task overview to build a full understanding of the project. Use when starting work on a feature that has an existing engineering documentation folder, or when you need to orient yourself before a task.
argument-hint: "<path to root index.md> [optional focus directive or additional context]"
---

# Project Context Loader

You are loading engineering project context from a documentation folder created by the `/new-eng-feature` pipeline (or `/eng-feature-followup`). Your job is to **read and internalize** the project's plans, design, status, and open items so that subsequent work in this conversation is fully informed.

This is a context-loading skill, not a document-producing skill. You read, synthesize, and present a brief orientation — then you're ready for whatever the user asks next.

## Input

$ARGUMENTS

You need one required input and accept one optional input:

1. **Root index path** (required) — absolute path to the project's root `index.md` file. Example: `/Users/jscott/Developer/sources/personal/notebook/projects/fuzzball/features/FUZZ-6787-storage-mig/index.md`
2. **Focus directive** (optional) — additional context that narrows or redirects the orientation. Examples:
   - `"focus on database changes"`
   - `"I'm working on task T4.4"`
   - `"summarize current blockers"`
   - `"I need to understand the design decisions"`
   - A Jira ticket key, file path, or any other contextual hint

If the root index path is missing, use AskUserQuestion to request it. If the path points to a directory rather than a file, append `/index.md` automatically.

---

## Phase 1: Read the Root Index

### Step 1.1: Load and Parse Root Index

Read the root `index.md` file. Extract:

- **Feature name and metadata** — Jira links, repository path, status, creation date
- **Documentation Structure table** — the list of subfolder indexes and their purposes. Parse every link in this table to discover child index paths. Do NOT hardcode folder names — use what the index says exists.
- **Pipeline Summary table** — which skills have run and their primary outputs. This tells you what documents exist and their locations.
- **Totals and status** — document count, task count, open follow-ups, estimated effort
- **Key Decision Log** — if present, these are resolved design decisions that inform all downstream work

Record all document paths discovered from the root index. These are relative paths — resolve them against the root index's directory.

### Step 1.2: Determine the Project Root Directory

Derive the project root directory from the root index path (its parent directory). All subsequent paths are relative to this directory.

---

## Phase 2: Read All Child Index Files

### Step 2.1: Load Each Subfolder Index

For every subfolder index discovered in Phase 1 (typically `plans/index.md`, `tasks/index.md`, `research/index.md`, `follow-ups/index.md`, `verifications/index.md`), read the index file.

From each child index, extract:

- **Document table** — every document listed with its description and creation date
- **Cross-references** — any Reference Links sections that point to other documents
- **Task Tracking table** — if present (typically in `tasks/index.md`), this is the canonical status tracker with completion checkboxes

Note which child indexes exist and which are empty or missing. Not every project has every folder populated — an empty `research/` index or a missing `verifications/` folder is normal for early-stage projects. Note what's absent without treating it as an error.

---

## Phase 3: Read Core Documents

These documents are always read when they exist. Discover their paths from the index files — do not assume filenames.

### Step 3.1: Implementation Plan

Read the implementation plan (typically found in `plans/`). This is the most comprehensive document — it contains:

- Feature overview and requirements
- Codebase impact assessment
- Gap analysis and open questions
- Design decision log (if `/eng-design-creator` has run)
- Test plan (if `/eng-test-planning` has run)

Read the full document.

### Step 3.2: Design Document

Read the design document (typically found in `plans/`). This contains:

- Architectural decisions and rationale
- Component and interface design
- Data model and API design
- Error handling strategy
- Implementation sequence

Read the full document.

### Step 3.3: Follow-Up Items

Read the follow-ups document (typically `follow-ups/open-items.md` or similar). This contains:

- Open questions needing answers
- Assumptions that need validation
- Deferred items
- Unresolved risks

This is critical context — open items directly affect what work can proceed and what's blocked.

### Step 3.4: Task Overview

Read the high-level task plan document (typically found in `tasks/`). This provides:

- Phase breakdown and parallelism map
- Critical path and time estimates
- Risk assessment
- Dependencies between tasks

Do NOT read individual per-task files by default. They are detailed implementation guides for specific tasks — only read them if the focus directive points at a specific task.

---

## Phase 4: Apply Focus Directive (if provided)

If the user provided optional context or a focus directive, use it to guide additional reading:

- **Specific task reference** (e.g., "task T4.4", "T2.1") — read that task's individual document from the `tasks/` folder. Use the tasks index to find the correct filename.
- **Topic focus** (e.g., "database changes", "CLI design") — identify which sections of the plan and design are most relevant. Note these for emphasis in the summary.
- **Status query** (e.g., "current blockers", "what's left") — emphasize the task tracking table completion state and open follow-up items.
- **Verification focus** — read the verifications README and relevant verification documents.
- **Research focus** — read any research documents listed in the research index.

If the focus directive references a specific document or task that doesn't exist, note this clearly in the summary.

---

## Phase 5: Present Orientation Summary

After reading all documents, present a concise orientation summary to the user. This should be scannable — the user has the full documents available and doesn't need them repeated.

Structure the summary as:

```
## Project Context: [Feature Name]

**Status:** [from root index]
**Jira:** [links]
**Repository:** [path]

### Scope
[2-3 sentences: what this feature does and why it exists]

### Architecture
[2-3 sentences: the key design decisions and architectural approach]

### Current State
- **Documents:** [count] across [folders]
- **Tasks:** [completed]/[total] ([estimated effort])
- **Open Items:** [count] ([brief characterization — e.g., "mostly resolve-at-task-start; 3 need PM input"])

### Key Decisions
[Bullet list of the most important resolved decisions — these shape all implementation work]

### Open Items Requiring Attention
[Bullet list of the highest-priority unresolved items — blockers first, then questions, then risks]
```

Omit sections that don't apply to the project's current state. An early-stage project that only ran `/eng-plan-creator` won't have tasks, follow-ups, or a design document — adapt the summary to what actually exists rather than rendering empty sections.

If a focus directive was provided, add a focused section:

```
### Focus: [directive]
[Relevant details from the focused reading — task status, relevant design sections, specific blockers, etc.]
```

---

## Important Guidelines

1. **Don't hardcode document names.** The pipeline creates documents with predictable-but-not-guaranteed names. Always discover paths from the index files. If an index references `implementation-plan.md`, read that. If it references `plan-v2.md`, read that instead.

2. **Graceful handling of missing content.** Projects at different stages will have different documents. A project that only ran `/eng-plan-creator` will have a plan but no design, tasks, or verifications. Note what exists and what doesn't — don't error on absence.

3. **Don't produce a new document.** This skill loads context into the conversation. The summary goes in your response to the user, not into a file.

4. **Don't propose next actions.** Present the orientation and wait for the user to tell you what they want to do. The user invoked this skill to get context, not to get a work plan.

5. **Internalize, don't just summarize.** The point of reading these documents is that your subsequent responses in this conversation are informed by the full project context. The summary is for the user's benefit — but you should retain the details (architecture, data models, API designs, naming conventions, open questions) for use in whatever comes next.

6. **Read fully, summarize briefly.** Read every core document end-to-end. But the orientation summary should be concise — the user can read the documents themselves. Your value is synthesis and readiness, not repetition.
