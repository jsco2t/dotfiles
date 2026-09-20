---
name: eng-feature-followup
description: Propagate changed requirements or resolved questions through an existing engineering feature workspace by rerunning eng-plan-creator, eng-design-creator, eng-test-planning, eng-task-planning, and eng-verification-creator in strict update sequence. Use for direct or delegated updates that must preserve history, task completion, stable IDs, indexes, and a detailed changelog.
---

# Engineering Feature Follow-Up

## Inputs

- **Feature documentation directory:** root of an existing engineering feature workspace.
- **Updated context:** Jira/Confluence sources, local files, free text, or resolved questions describing the delta.
- **Code repository:** target repository path; optional only when the current working directory or existing root index identifies it unambiguously.
- Optional approved change scope, decisions, output constraints, or prior analysis from a caller.

Require the feature directory and at least one source of changed context. Ask only for missing or materially ambiguous information. Honor supplied decisions and never repeat answered questions. When delegated, return phase status, artifacts, deltas, and blockers to the caller.

## Requirements and Skill Boundaries

- Run these available skills in strict order, validating each output before continuing:
  1. `eng-plan-creator`
  2. `eng-design-creator`
  3. `eng-test-planning`
  4. `eng-task-planning`
  5. `eng-verification-creator`
- Invoke each through the current skill/delegation mechanism after reading its instructions. Pass existing documents, the change summary, settled decisions, repository context, and fixed output paths.
- Require `plans/implementation-plan.md`; if missing, stop and recommend `new-eng-feature` or request the correct path.
- If `plans/design.md` is missing, run `eng-design-creator` in creation mode within its normal pipeline position and record that it was created. Missing task, verification, or follow-up artifacts may also be created in their normal phases.
- Preserve unchanged content, task IDs, completed-task markers, decisions, and resolved-item history. Mark removed work descoped rather than erasing its audit trail.
- Route only genuinely unresolved questions and approvals to the user or delegating caller. Never answer product or design choices by assumption.
- Do not run phases in parallel and do not silently skip a failed phase.
- Use ISO 8601 timestamps with the local Mountain offset. Preserve numeric verification ordering and correct relative links.

## Core Skill Process

### 1. Assess current state and create the change summary

Validate the feature directory and repository. Read:

- root and child indexes;
- `plans/implementation-plan.md` and `plans/design.md` when present;
- `tasks/task-plan.md` and current `tasks/index.md` completion markers;
- `follow-ups/open-items.md` and `follow-ups/changelog.md`;
- existing verification documents.

Extract feature identity, source references, repository, current requirements, design decisions, tasks, effort, open items, and existing pipeline status.

Read every updated source and fetch Jira/Confluence content with available connectors. Classify the delta as new, changed, removed/descoped, resolved, or newly uncertain. Create or prepend `<doc-directory>/follow-ups/changelog.md` using:

```markdown
# Change Log

**Feature:** [Feature name]
**Jira:** [Epic key(s)]

---

## [ISO 8601 timestamp with Mountain offset] — Follow-Up Update

### Change Context

[What triggered this update.]

### Sources

- [Each source, or "user-provided text"]

### Change Summary

| # | Type | Description | Affects |
|---|------|-------------|---------|
| 1 | New / Changed / Removed / Resolved | [Change] | [Documents/phases] |

### Documents Updated

_Populated as each phase completes._

| Phase | Document | Change Type | Summary |
|-------|----------|-------------|---------|
```

Tell a direct user what exists, the delta, likely high-impact documents, and which phases may need decisions. For delegated work, pass this status to the caller.

### 2. Update the implementation plan

Run `eng-plan-creator` with all update sources, repository context, the current plan, and the Change Summary. Instruct it to:

- treat this as an update;
- preserve unaffected sections;
- mark new or changed content clearly;
- revisit code impact only where the delta requires it;
- resolve answered gaps, add new gaps, and retain continuing questions;
- overwrite `<doc-directory>/plans/implementation-plan.md`.

Allow unresolved requirements questions to reach the user/caller. Verify the plan and spot-check preservation. Update the existing `plans/index.md` row without duplicating it, and add a Phase 1 changelog row.

### 3. Update or create the design

Run `eng-design-creator` with the updated plan, existing design when present, repository context, Change Summary, and settled decisions. Instruct it to re-evaluate only affected decisions; preserve unaffected rationale; revise components, data models, APIs, tests, and risks as needed; and write `<doc-directory>/plans/design.md`.

Route affected trade-offs and approval to the user/caller. Verify the output and preservation, update the existing design index row or create it, and add a Phase 2 changelog row.

### 4. Update the test plan

Run `eng-test-planning` with the updated implementation plan and companion design. Instruct it to revise the existing test section for new/changed requirements and retain valid coverage for unchanged behavior. Verify the plan was updated, revise the existing plan-index description rather than adding a duplicate, and add a Phase 3 changelog row.

### 5. Update the task plan

Before editing, capture all task IDs and `[x]` completion states from `tasks/index.md`. Run `eng-task-planning` with the updated plan, design, existing task plan when present, Change Summary, and this requirement:

```text
Update <doc-directory>/tasks/task-plan.md. Add tasks for new scope, modify affected tasks, mark removed work descoped, update estimates and dependencies, and preserve IDs for unchanged tasks wherever possible.
```

Verify the task plan. Rebuild Task Tracking from the new plan, carrying forward completion for still-existing task IDs. Never mark a new or materially changed task complete by inheritance. Update the task-plan index row and add a Phase 4 changelog row.

### 6. Update verifications

Run `eng-verification-creator` with the updated plan, design, current verification directory, and Change Summary. Instruct it to preserve valid tests, revise affected tests, add new coverage, retire removed coverage traceably, and restore 100% coverage of the updated specification.

After approval and generation, rediscover all Markdown files and rebuild `verifications/index.md` with the README first, then environment folders and files in numeric order. Add a Phase 5 changelog row.

### 7. Refresh follow-ups

Compare the old `follow-ups/open-items.md` with gaps, questions, assumptions, risks, deferred work, TBDs, and pending research in the updated plans and tasks:

- move answered items to `Resolved Items`;
- retain and update continuing items;
- add new items;
- mark no-longer-applicable items as closed by descoping rather than silently deleting them.

Use this resolved-items schema:

```markdown
## Resolved Items

_Previously open items that have been resolved._

| # | Item | Original Source | Resolved By | Resolution Date |
|---|------|-----------------|-------------|-----------------|
| 1 | [Item] | [Source] | [Updated source or decision] | [timestamp] |
```

Ensure `follow-ups/index.md` contains:

```markdown
| [`open-items.md`](open-items.md) | Consolidated open questions, assumptions, deferred items, and unresolved risks — updated [timestamp] | [original timestamp] |
| [`changelog.md`](changelog.md) | Change log tracking all follow-up updates to feature documentation | [first-entry timestamp] |
```

### 8. Finalize changelog and indexes

Complete the current changelog entry:

```markdown
### Impact Summary

- **Requirements changes:** [count new / changed / removed]
- **Design decisions revisited:** [count]
- **Tasks added/modified/removed:** [added / modified / removed]
- **Verification tests added/modified/removed:** [added / modified / removed]
- **Open items:** [count resolved] resolved, [count new] new, [count continuing] continuing
```

Verify every file is indexed, all links resolve, timestamps and counts are correct, verification ordering is numeric, task completion is preserved correctly, and the root summary reflects current effort and document counts.

Add or update:

```markdown
---

## Revision History

| Date | Type | Summary | Change Log |
|------|------|---------|------------|
| [original date] | Initial | Created via `new-eng-feature` pipeline | — |
| [today's date] | Follow-Up | [Summary] | [`follow-ups/changelog.md`](follow-ups/changelog.md) |
```

## Output Formatting

Preserve existing schemas, IDs, links, and historical content. Clearly label update-only changes where the source documents support such markers; do not litter unchanged text with change labels.

Report completion with:

- updated and newly created artifacts;
- phase-by-phase status;
- net requirements, task, effort, verification, and open-item changes;
- preserved completed tasks;
- assumptions, inaccessible context, or moved outputs;
- recommended next steps.

Report problems under `Problems`, each with `Phase`, `Issue`, `Impact`, `Evidence`, and `Next action`. A missing implementation plan, inaccessible required update source, unresolved required decision, or failed prerequisite phase is blocking. Missing optional prior artifacts and unavailable enrichment are non-blocking when the pipeline can recreate them from authoritative inputs.
