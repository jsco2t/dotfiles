---
name: project-context
description: Load and synthesize context from an engineering feature documentation folder created by new-eng-feature or eng-feature-followup. Use to orient a conversation or delegated task around project scope, design, status, decisions, tasks, and open items.
---

# Project Context

## Inputs

- Root `index.md` path or its containing directory.
- Optional focus such as a task ID, subsystem, blocker, verification area, or status question.
- Optional caller-provided documents or already-resolved context.

Append `index.md` when given a directory. Request a path only when it cannot be inferred from the request or caller context.

## Requirements and Skill Boundaries

- Read and synthesize; do not edit project documents.
- Discover document paths from indexes instead of assuming filenames.
- Read all core documents that exist. Missing documents are normal in an incomplete pipeline.
- Do not read every per-task or verification file by default. Load detail selected by the focus.
- Keep the orientation brief while retaining the full context for later turns or the delegating caller.
- Do not invent next steps. Report current state and wait for the next request.
- When delegated, return structured context, relevant document paths, decisions, blockers, and missing inputs without re-asking questions the caller already answered.

## Core Skill Process

### 1. Read the root index

Extract feature metadata, repository and tracker links, documentation structure, pipeline outputs, counts, status, and decision log. Resolve linked paths relative to the root index directory.

### 2. Read child indexes

Read every child index linked from the root. Collect its document table, cross-references, and task tracking table. Record missing and empty areas without treating them as errors.

### 3. Read core documents

When listed and present, read these documents fully:

- implementation plan, including requirements, boundaries, gaps, decisions, and test plan;
- design document, including architecture, contracts, data/API design, errors, and sequence;
- consolidated follow-ups, including blockers, assumptions, deferred items, and risks;
- high-level task plan and canonical task status.

Do not infer existence from conventional names; use index links.

### 4. Apply the focus

- For a task ID, locate and read its task document.
- For a subsystem, emphasize its plan/design sections.
- For status or blockers, prioritize task tracking and open items.
- For verification or research, read only the relevant indexed documents.

If the requested target does not exist, say what was searched and what is missing.

### 5. Synthesize the orientation

Reconcile the indexes with document content. Note stale counts, broken links, or conflicting status rather than silently choosing one.

## Output Formatting

```markdown
## Project Context: [Feature]

- **Status:** [status]
- **Tracker:** [links]
- **Repository:** [path]

### Scope

[What the feature does and why]

### Architecture

[Key design and integration approach]

### Current State

- **Documents:** [count/state]
- **Tasks:** [complete/total and effort]
- **Open items:** [count and character]

### Key Decisions

- [decision]

### Open Items Requiring Attention

- [blocker/question/risk]

### Focus: [directive]

[Focused context, when requested]

### Context Problems

- [broken link, missing file, stale index, or conflict]
```

Omit optional empty sections. Distinguish expected pipeline incompleteness from actual problems. Include exact paths for missing or conflicting artifacts.
