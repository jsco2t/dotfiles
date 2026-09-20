---
name: new-eng-feature
description: Orchestrate end-to-end engineering feature planning by running eng-plan-creator, eng-design-creator, eng-test-planning, eng-task-planning, and eng-verification-creator in strict sequence while maintaining a structured documentation workspace. Use for new features that need research, design, test planning, tasks, and manual verification, directly or from a delegated project pipeline.
---

# New Engineering Feature

## Inputs

- **Output directory:** feature documentation root.
- **Specification sources:** at least one Jira/Confluence reference, local file, or equivalent supplied specification.
- **Code repository:** target repository path; omit only when the current working directory is the target repository.
- Optional fixed feature name/slug, output decisions, approvals, or prior context from a caller.

Ask only for missing or materially ambiguous inputs. Honor all caller-supplied paths and decisions. Do not re-ask questions answered in context. In delegated execution, return pipeline status, artifacts, and unresolved user decisions to the caller.

## Requirements and Skill Boundaries

- Run these available skills in strict order, completing and validating each output before continuing:
  1. `eng-plan-creator`
  2. `eng-design-creator`
  3. `eng-test-planning`
  4. `eng-task-planning`
  5. `eng-verification-creator`
- Invoke each skill through the current skill/delegation mechanism after reading its instructions. Pass explicit paths, upstream artifacts, relevant decisions, and output requirements.
- Route genuinely unresolved questions and approval gates from `eng-plan-creator`, `eng-design-creator`, or `eng-verification-creator` to the direct user or delegating caller. Never fabricate answers. Do not pause for information already supplied.
- Do not run pipeline phases in parallel. Later phases depend on earlier artifacts.
- Maintain indexes and cross-document organization yourself; subskills need not know the workspace layout.
- Use ISO 8601 timestamps with the local Mountain offset. Preserve numeric ordering in verification folders.
- Do not silently skip a failed phase. Retry correctable failures; otherwise stop, report the blocker, and state which downstream phases remain incomplete. Create a skip placeholder only if the user/caller explicitly directs the pipeline to continue without that phase.
- If an output lands elsewhere, move it to the required path only when doing so is safe, update internal links, and report the move.

## Core Skill Process

### 1. Initialize the workspace

Validate inputs, derive the feature name and stable slug, and create:

```text
<output-directory>/
├── index.md
├── plans/
│   └── index.md
├── tasks/
│   └── index.md
├── research/
│   └── index.md
├── reviews/
│   └── index.md
├── follow-ups/
│   └── index.md
└── verifications/
    └── index.md
```

Use this root index:

```markdown
# [Feature Name] — Engineering Documentation

**Feature:** [Feature name]
**Jira:** [Epic key(s) and links]
**Repository:** [Code repository path]
**Created:** [ISO 8601 timestamp with Mountain offset]
**Status:** In Progress

---

## Documentation Structure

| Folder                                     | Purpose                                                                 | Index                                            |
| ------------------------------------------ | ----------------------------------------------------------------------- | ------------------------------------------------ |
| [`plans/`](plans/index.md)                 | Implementation plan, design document, and test strategy                 | [plans/index.md](plans/index.md)                 |
| [`tasks/`](tasks/index.md)                 | Implementation task breakdown with estimates and dependencies           | [tasks/index.md](tasks/index.md)                 |
| [`research/`](research/index.md)           | Ancillary research and background documents                             | [research/index.md](research/index.md)           |
| [`reviews/`](reviews/index.md)             | Review reports generated later in the development cycle                 | [reviews/index.md](reviews/index.md)             |
| [`follow-ups/`](follow-ups/index.md)       | Open questions and items requiring future resolution                    | [follow-ups/index.md](follow-ups/index.md)       |
| [`verifications/`](verifications/index.md) | Manual verification test documents                                      | [verifications/index.md](verifications/index.md) |
```

Use this base child index:

```markdown
# [Folder Name] Index

**Parent:** [../index.md](../index.md)
**Last Updated:** [ISO 8601 timestamp with Mountain offset]

---

| Document | Description | Created |
| -------- | ----------- | ------- |
```

Use this specialized `tasks/index.md`:

```markdown
# Tasks Index

**Parent:** [../index.md](../index.md)
**Last Updated:** [ISO 8601 timestamp with Mountain offset]

---

## Documents

| Document | Description | Created |
| -------- | ----------- | ------- |

## Task Tracking

_Populated after task planning is complete._

| Task ID | Task Name | Phase | Estimate | Dependencies | Completed |
| ------- | --------- | ----- | -------- | ------------ | --------- |
```

Tell a direct user what was created, the slug, and which phases may require decisions. For delegated runs, return the same progress to the caller.

### 2. Create the implementation plan

Run `eng-plan-creator` with all spec sources, repository context, existing decisions, and this fixed output requirement:

```text
Save the engineering implementation plan to <output-directory>/plans/implementation-plan.md. Do not ask for an output location. Title it "Engineering Implementation Plan: [Feature Name]".
```

Verify the file. Add this row to `plans/index.md`:

```markdown
| [`implementation-plan.md`](implementation-plan.md) | Engineering implementation plan — feature overview, requirements, codebase impact, gaps, and high-level approach | [timestamp] |
```

Move any useful ancillary research produced by the skill into `research/`, fix links, and index it. Record the plan path for downstream phases.

### 3. Create the design

Run `eng-design-creator` with the plan path, repository context, prior answers, and:

```text
Save the design to <output-directory>/plans/design.md. Do not ask for an output location. The implementation plan is <output-directory>/plans/implementation-plan.md.
```

Allow unresolved trade-off questions and approval to reach the user/caller. Verify `design.md`, note any approved update the skill made to the implementation plan, and add:

```markdown
| [`design.md`](design.md) | Engineering design — architectural decisions, component design, data model, API design, and rationale | [timestamp] |
```

### 4. Append the test plan

Run `eng-test-planning` with `plans/implementation-plan.md`, the companion `plans/design.md`, repository context, and settled decisions. Verify that the implementation plan now contains the test-plan section. Update its existing index row rather than adding a duplicate:

```markdown
| [`implementation-plan.md`](implementation-plan.md) | Engineering implementation plan — includes appended test strategy (added [timestamp]) | [original timestamp] |
```

### 5. Create the task plan

Run `eng-task-planning` with the implementation plan, design path, repository context, and:

```text
Save the task plan to <output-directory>/tasks/task-plan.md. Do not save it in plans/ or ask for an output location.
```

Verify the file and add:

```markdown
| [`task-plan.md`](task-plan.md) | Implementation task plan with phases, estimates, dependencies, and parallel-work guidance | [timestamp] |
```

Populate the Task Tracking table from every phase and task, preserving plan order:

```markdown
| T1.1 | [Task Name] | Foundation | 1.0d | None | [ ] |
| T1.2 | [Task Name] | Foundation | 1.5d | T1.1 | [ ] |
```

Index any individual task documents created by the planning skill.

### 6. Create manual verifications

Run `eng-verification-creator` with:

```text
<output-directory>/plans/implementation-plan.md
<output-directory>/plans/design.md
<output-directory>/verifications
```

Pass repository context and existing approvals. After completion, discover all Markdown files recursively and rebuild `verifications/index.md` in numeric order:

```markdown
# Verifications Index

**Parent:** [../index.md](../index.md)
**Last Updated:** [timestamp]

---

| Document                 | Description                                                         | Created     |
| ------------------------ | ------------------------------------------------------------------- | ----------- |
| [`README.md`](README.md) | Verification suite overview, folder index, and spec coverage matrix | [timestamp] |

## Environment Folders

### [01-folder-name/](01-folder-name/)

| # | Document                                  | Description   | Created     |
| - | ----------------------------------------- | ------------- | ----------- |
| 1 | [`01-file.md`](01-folder-name/01-file.md) | [description] | [timestamp] |
```

### 7. Consolidate follow-ups

Scan plans and tasks for open questions, missing information, assumptions, unresolved risks, deferred work, TBDs, and pending research. Deduplicate and attribute each item in `follow-ups/open-items.md`:

```markdown
# Open Items and Follow-Ups

**Feature:** [Feature name]
**Extracted From:** Implementation plan, design document, task plan
**Created:** [ISO 8601 timestamp with Mountain offset]

---

## Open Questions

| # | Question | Source Document | Affects | Suggested Owner |
| - | -------- | --------------- | ------- | --------------- |
| 1 | [Question] | [Document and section] | [Impact] | [Owner] |

## Assumptions to Validate

| # | Assumption | Source Document | Risk if Wrong |
| - | ---------- | --------------- | ------------- |
| 1 | [Assumption] | [Source] | [Impact] |

## Deferred Items

| # | Item | Source Document | When to Address |
| - | ---- | --------------- | --------------- |
| 1 | [Item] | [Source] | [Trigger] |

## Unresolved Risks

| # | Risk | Source Document | Impact | Suggested Mitigation |
| - | ---- | --------------- | ------ | -------------------- |
| 1 | [Risk] | [Source] | [Impact] | [Mitigation] |
```

Add it to `follow-ups/index.md`.

### 8. Finalize the workspace

Verify every document is indexed, all links resolve, timestamps and counts are correct, numeric order is preserved, and Task Tracking includes every task. Add this root summary:

```markdown
---

## Pipeline Summary

| Phase | Skill                       | Status   | Primary Output                                                 |
| ----- | --------------------------- | -------- | -------------------------------------------------------------- |
| 1     | `eng-plan-creator`          | Complete | [`plans/implementation-plan.md`](plans/implementation-plan.md) |
| 2     | `eng-design-creator`        | Complete | [`plans/design.md`](plans/design.md)                           |
| 3     | `eng-test-planning`         | Complete | Test strategy appended to implementation plan                  |
| 4     | `eng-task-planning`         | Complete | [`tasks/task-plan.md`](tasks/task-plan.md)                     |
| 5     | `eng-verification-creator`  | Complete | [`verifications/README.md`](verifications/README.md)           |

**Total Documents:** [count]
**Open Follow-Up Items:** [count]
**Task Count:** [count]
**Estimated Effort:** [total] days
```

## Output Formatting

Preserve every subskill's required schema. Use relative links and consistent names throughout the workspace.

Report completion with:

- all created artifact paths;
- each pipeline phase and status;
- task phases, effort, and critical path;
- open follow-up count and highest-impact items;
- moved outputs, assumptions, or incomplete external context;
- recommended next steps.

Report problems under `Problems`, each with `Phase`, `Issue`, `Impact`, `Evidence`, and `Next action`. A missing implementation plan, unapproved required design decision, failed prerequisite skill, or inaccessible required spec is blocking. Optional external enrichment and ancillary research gaps are non-blocking if the primary specification remains sufficient.
