---
name: update-project
description: Update an existing product project's PRD, product-level user scenarios, supplementary documents, knowledge base, indexes, and changelog from changed requirements or new context. Use for revisions to a new-project workspace, directly or as a delegated step; identify affected engineering features but leave their contents to eng-feature-followup.
---

# Update Project

## Inputs

- **Project directory:** existing project documentation root.
- **Updated context:** Jira/Confluence links, local files, free text, stakeholder feedback, changed requirements, or answers to PRD open questions.
- Optional pre-approved change scope, decisions, repository context, or output constraints from a caller.

Require the project directory and at least one source of updated context. Honor supplied decisions and paths; do not repeat resolved questions. When delegated, return status, changed artifacts, and follow-up needs to the caller.

## Requirements and Skill Boundaries

- Update only project-level artifacts: `prd.md`, `verifications/`, `documents/`, `kb/`, root and child indexes, and `documents/changelog.md`.
- Never edit content inside `features/`. Read its index only to identify feature plans that may need `eng-feature-followup`.
- Require `prd.md`. If it is missing, stop and recommend `new-project`; do not reconstruct it in update mode.
- Preserve unaffected content and settled decisions. Ask only about ambiguous deltas or conflicts.
- Never renumber existing `FR-XXX`, `NFR-XXX`, or `US-XXX` identifiers. Assign new items the next available number. Mark removed requirements and scenarios as descoped; do not silently delete them.
- Append to the Decision Log and changelog. Preserve prior history.
- All Must Have requirements must remain covered by user scenarios.
- Do not delete supporting documents unless explicitly requested; mark obsolete material superseded.
- Use ISO 8601 timestamps with the local Mountain offset.
- If external sources cannot be fetched, report the gap and continue only when supplied context is sufficient.

## Core Skill Process

### 1. Assess the current project

Validate the directory and inspect:

- `index.md` and `prd.md`;
- all verification documents and `verifications/index.md`;
- `documents/index.md`, `kb/index.md`, and `features/index.md`;
- existing `documents/changelog.md`.

Record the project name and slug, current requirements and scenario IDs, open questions, decisions, feature list, document counts, and completion state. Missing optional directories or indexes may be created when needed.

### 2. Analyze the delta

Read every supplied source. Fetch linked Jira or Confluence content with the available connector. Classify each change as new, changed, removed/descoped, or resolved. Identify new questions and conflicts with current goals, non-goals, requirements, or constraints.

Create or prepend a changelog entry at `<project-directory>/documents/changelog.md` using this schema:

```markdown
# Project Change Log

**Project:** [Project name]
**Jira:** [Epic key(s)]

---

## [ISO 8601 timestamp with Mountain offset] — Project Update

### Change Context

[What triggered this update.]

### Sources

- [Each source, or "user-provided text"]

### Change Summary

| # | Type | Description | PRD Sections Affected |
| - | ---- | ----------- | --------------------- |
| 1 | New / Changed / Removed / Resolved | [Change] | [Sections] |

### Documents Updated

_Populated as each phase completes._

| Phase | Document | Change Type | Summary |
| ----- | -------- | ----------- | ------- |
```

For a direct user, summarize the current state, identified delta, affected PRD sections, and potentially affected features. For delegated execution, pass this progress to the caller.

### 3. Resolve only delta ambiguities

Ask targeted questions only when changes have multiple interpretations, conflict with existing scope, or leave material downstream impact unclear. Reference the affected requirement or PRD section. Limit to two rounds; unresolved issues become Open Questions.

Before editing, state the proposed scope: sections to change, new IDs, items to descope, questions resolved, and questions added. Obtain confirmation unless the caller already supplied approved scope or explicitly delegated an autonomous update.

### 4. Update the PRD

Edit `<project-directory>/prd.md` surgically:

1. Increment the version and update `Last Updated` and status.
2. Revise affected goals, non-goals, requirements, workflows, constraints, risks, and other sections.
3. Allocate new FR/NFR IDs without changing existing IDs.
4. Move resolved questions to Appendix C, add new open questions, and retain continuing ones.
5. Append decisions and rationale to the Decision Log.
6. Preserve unchanged text.

Add a concise PRD row to the changelog, for example:

```markdown
| 1 - PRD | `prd.md` | Updated | Added FR-015 through FR-018, resolved OQ-3 and OQ-5, and descoped NFR-007 |
```

### 5. Update user scenarios

Compare the revised PRD with all verification documents:

- add scenarios for new requirements using the next `US-XXX` IDs;
- revise scenarios for changed requirements;
- mark removed scenarios `~~Descoped~~` or move them to a `Descoped Scenarios` section;
- update PRD references, steps, expected outcomes, acceptance criteria, and the coverage matrix;
- verify 100% coverage of Must Have requirements.

Add verification changes to the changelog.

### 6. Update supporting material

Review `documents/` and `kb/` for affected comparisons, constraints, terminology, or reference content. Update relevant artifacts and create new ones only when the new context warrants a separate document. Mark superseded documents clearly. Update the changelog after this pass.

### 7. Finalize history and indexes

Complete the changelog entry with:

```markdown
### Impact Summary

- **Requirements:** [count new] new, [count changed] changed, [count removed] removed
- **Open questions:** [count resolved] resolved, [count new] new, [count continuing] continuing
- **User scenarios:** [count added] added, [count revised] revised, [count removed] removed
- **Supplementary docs:** [count updated] updated, [count created] created
- **KB entries:** [count updated] updated, [count created] created

### Features Potentially Affected

_The following features in `features/` may need updates via `eng-feature-followup`:_

| Feature | Reason | Urgency |
| ------- | ------ | ------- |
| [Feature name/slug] | [Relevant PRD changes] | High/Medium/Low |
```

Omit the feature table only when no feature plans exist. Ensure every document appears in the appropriate index, update timestamps and counts, add `documents/changelog.md` to its index, and verify links.

Add or update this root section:

```markdown
---

## Revision History

| Date | Type | Summary | Change Log |
| ---- | ---- | ------- | ---------- |
| [original date] | Initial | Created via `new-project` | — |
| [today's date] | Update | [Summary] | [`documents/changelog.md`](documents/changelog.md) |
```

## Output Formatting

Preserve the existing document schemas and formatting. Keep changelog entries concise, traceable, and ordered newest first.

Report completion with:

- updated and created artifact paths with one-line changes;
- requirement totals and priority breakdown;
- resolved, new, and continuing open-question counts;
- Must Have verification coverage;
- features that need `eng-feature-followup`, with reason and urgency;
- recommended next steps.

Report problems under `Problems`, each with `Issue`, `Impact`, and `Next action`. Missing `prd.md`, inaccessible required update sources, unresolved scope approval, or incomplete Must Have coverage are blockers. Missing optional artifacts, unavailable enrichment, and feature-level staleness are non-blocking but must be recorded.
