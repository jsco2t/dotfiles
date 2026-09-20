---
name: feature-summarizer
description: Create a concise executive one-pager from feature research, design, and task-planning documents. Use for stakeholder updates, onboarding, or quick feature reference, whether requested directly or delegated by another skill.
---

# Feature Summarizer

## Inputs

- A feature research document path, a directory containing feature documents, or equivalent supplied context.
- Optional companion design and task-plan paths.
- Optional output path or naming instructions from the caller.

Treat supplied paths, decisions, and context as authoritative. Do not ask for information already provided. If no research document or equivalent source can be found, report the missing input and ask for its path.

## Requirements and Skill Boundaries

- Require a research document or equivalent source. Design and task documents are optional.
- When given a directory, look for `*-research.md`, `implementation-plan.md`, `*-design.md`, `design.md`, `*-tasks.md`, and `task-plan.md`.
- Read every relevant source before writing. Use the research document for goals and requirements, the design for decisions and risks, and the task plan for estimates and sequencing.
- If sources reference Jira or Confluence and the relevant connector is available, fetch only context needed to confirm current status or recent decisions. If unavailable, use the local sources and note that current external status was not verified.
- Do not invent missing design decisions, test strategy, estimates, or status. Omit unsupported sections as directed by the template.
- Keep the body near 500 words. Link to detail instead of repeating it.
- Support direct and delegated execution. Honor a caller-supplied output path and return the artifact path and status to the caller.

## Core Skill Process

1. Locate and read the research source and all available companion documents.
2. Extract:
   - goals, users, requirements, acceptance criteria, gaps, and recommendations from research;
   - the chosen architecture, important decisions and rationale, test approach, risks, and mitigations from design;
   - effort, phase count, critical path, and team-size guidance from task planning.
3. Verify referenced external status only when it materially affects the summary.
4. Determine feature name, planning status, source links, and output path. Unless the caller supplied a path, save beside the research document as `<feature-name>-summary.md`.
5. Write the document using the exact schema below.
6. Check that links resolve, claims are supported, and the summary is brief and readable.

### Document Schema

```markdown
# [Feature Name] — Summary

**Date:** [Date]
**Status:** [Research | Design Complete | Planning Complete | In Progress]
**Source:** [Relative path to research doc] | [Relative path to design doc]
**Jira:** [Issue key(s) if available]

---

## Problem

[2-3 sentences. What problem does this feature solve? Why does it matter? Who benefits?]

## Solution

[3-5 sentences. Explain the approach for a technical manager or adjacent team member. Avoid file-level implementation detail.]

## Key Decisions

| Decision | Chosen Approach | Why |
|----------|----------------|-----|
| [Decision 1] | [What we chose] | [One-line rationale] |
| [Decision 2] | [What we chose] | [One-line rationale] |
| [Decision 3] | [What we chose] | [One-line rationale] |

*Detailed trade-off analysis is in the [design document](relative-path).*

## What Changes

- **[Area 1]** — [What changes and why]
- **[Area 2]** — [What changes and why]
- **[Area 3]** — [What changes and why]

## Test Approach

[2-3 sentences covering unit/integration emphasis, special infrastructure, and coverage intent.]

## Risks & Open Items

| Item | Type | Impact |
|------|------|--------|
| [Item 1] | Risk / Open Question | [Brief description] |
| [Item 2] | Risk / Open Question | [Brief description] |

## Effort Estimate

[Summarize effort, critical path, and recommended team size. If no task plan exists, state: "Task planning not yet completed — see research document for scope indicators."]

---

*Full details: [Research](relative-path) | [Design](relative-path) | [Tasks](relative-path)*
```

Omit `Key Decisions` and `Test Approach` when no design source supports them. Omit unavailable links from metadata and the footer.

## Output Formatting

Write a scannable Markdown one-pager with short paragraphs, bullets, and compact tables. Use plain language and define unavoidable project-specific terms.

After writing, return:

- the output path;
- the planning status represented;
- which research, design, and task sources were used;
- the full summary when the direct user asked to review it, or a concise artifact/status handoff when delegated.

Report problems under `Problems` with the affected source, impact, and next action. Distinguish blocking missing research from non-blocking gaps such as absent design, task planning, or external-status access.
