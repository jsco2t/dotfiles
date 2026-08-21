---
name: new-project
description: Create a new product/project documentation workspace and collaboratively develop a comprehensive PRD, product-level user scenarios, supplementary research, and a knowledge-base seed. Use for new product planning from descriptions, Jira/Confluence links, files, or delegated pipeline context; leave engineering feature planning to new-eng-feature.
---

# New Project

## Inputs

- **Output directory:** root directory for the project documentation.
- **Initial context:** product description, Jira/Confluence links, local files, or free text.
- Optional pre-supplied project name, slug, repository context, output decisions, or prior research.

Both required inputs must be present. Ask a concise question only for missing or materially ambiguous information. In delegated execution, honor supplied paths, context, and decisions; do not repeat answered questions. Return status and artifact paths to the caller.

## Requirements and Skill Boundaries

- Work at the product level: define what to build, for whom, why, scope, and success. Do not add file-level implementation design or code changes.
- The primary artifact is `prd.md`. Also create product-level user-scenario verifications and, only when useful, supplementary documents and KB entries.
- Create `features/` as an empty container for later `new-eng-feature` runs. Do not populate it.
- Research before asking questions. Questions must address real gaps found in supplied sources, current systems, and domain research.
- Ask related questions in two to four batches, with no more than three rounds. Summarize captured decisions after each round. Record remaining uncertainty as open questions.
- Do not invent requirements or decisions. If external sources cannot be accessed, distinguish verified facts from supplied or inferred context and ask whether missing source content is blocking.
- Use the user's terminology. Requirements must be specific and testable; every Must Have functional requirement must map to at least one user scenario.
- Use ISO 8601 timestamps with the local Mountain offset (`-06:00` during MDT, `-07:00` during MST).
- Maintain every index and relative link. Do not create empty supplementary or KB documents.
- After drafting the PRD, obtain user approval before generating final user scenarios unless the caller explicitly supplied approval or delegated a non-interactive run with settled requirements.

## Core Skill Process

### 1. Initialize the workspace

Validate the directory and context, derive a stable project slug, and create:

```text
<output-directory>/
├── index.md
├── prd.md
├── documents/
│   └── index.md
├── features/
│   └── index.md
├── kb/
│   └── index.md
└── verifications/
    └── index.md
```

Use this root index:

```markdown
# [Project Name] — Project Documentation

**Project:** [Project name]
**Jira:** [Epic key(s) and links, if available]
**Created:** [ISO 8601 timestamp with Mountain offset]
**Status:** Draft

---

## Documentation Structure

| Folder                                       | Purpose                                                                       | Index                                              |
| -------------------------------------------- | ----------------------------------------------------------------------------- | -------------------------------------------------- |
| [`prd.md`](prd.md)                           | Product Requirements Document — the product specification                    | —                                                  |
| [`documents/`](documents/index.md)           | Supplementary documents, research, and reference materials                   | [documents/index.md](documents/index.md)           |
| [`features/`](features/index.md)             | Engineering feature plans created by `new-eng-feature`                       | [features/index.md](features/index.md)             |
| [`kb/`](kb/index.md)                         | Knowledge base — domain knowledge, glossaries, and reference docs            | [kb/index.md](kb/index.md)                         |
| [`verifications/`](verifications/index.md)   | User scenarios — acceptance-level verification of product behavior           | [verifications/index.md](verifications/index.md)   |
```

Use this base subfolder index:

```markdown
# [Folder Name] Index

**Parent:** [../index.md](../index.md)
**Last Updated:** [ISO 8601 timestamp with Mountain offset]

---

| Document | Description | Created |
| -------- | ----------- | ------- |
```

Use this specialized `features/index.md`:

```markdown
# Features Index

**Parent:** [../index.md](../index.md)
**Last Updated:** [ISO 8601 timestamp with Mountain offset]

---

This folder contains engineering feature plans created by `new-eng-feature`. Each subdirectory is a self-contained feature documentation tree with its own index.

| Feature | Slug | Jira | Status | Index |
| ------- | ---- | ---- | ------ | ----- |

_No features planned yet. Use `new-eng-feature <feature-directory> <spec links>` to create one._
```

Tell a direct user what was created, the chosen slug, and that researched questions will follow. For delegated runs, return this progress to the caller without pausing unless input is needed.

### 2. Research and identify gaps

Read all supplied files. Fetch Jira or Confluence sources with the available connector. Research current technologies, standards, markets, or competitors on the web when relevant. If an existing codebase is in scope, inspect related behavior, capabilities, gaps, and architectural constraints without turning the PRD into an engineering plan.

Classify findings as:

- defined facts;
- assumptions implied by the context;
- missing information;
- decisions with multiple viable options.

### 3. Run focused product Q&A

Ask only about uncovered gaps in: problem and urgency; users; goals and non-goals; measurable success; functional and non-functional requirements; constraints and dependencies; prior art; risks; and open questions. State what is already known, why the question matters, and a sensible default when one exists.

### 4. Draft and approve the PRD

Write `<output-directory>/prd.md` with this exact section structure:

```markdown
# Product Requirements Document: [Project Name]

**Version:** 1.0
**Author:** [User name if known, otherwise "Product Team"]
**Created:** [ISO 8601 timestamp with Mountain offset]
**Last Updated:** [ISO 8601 timestamp with Mountain offset]
**Status:** Draft
**Jira:** [Epic key(s) and links, if available]

---

## 1. Executive Summary

[What the product is, why it exists, who it serves, and the high-level approach.]

## 2. Problem Statement

### 2.1 Problem Description

[Problem being solved.]

### 2.2 Current State

[What exists and why it is insufficient.]

### 2.3 Impact of Not Acting

[Consequences of not building it.]

## 3. Users and Personas

### 3.1 Primary Users

[Role, technical level, goals, and workflows for each primary user.]

### 3.2 Secondary Users

[Indirect or occasional users.]

### 3.3 Stakeholders

[Non-user stakeholders such as operations, legal, or finance.]

## 4. Goals and Non-Goals

### 4.1 Goals

[Numbered list of required outcomes.]

### 4.2 Non-Goals

[Explicit scope boundaries.]

### 4.3 Future Considerations

[Potential later work excluded from v1.]

## 5. Success Metrics

| Metric | Target | Measurement Method |
| ------ | ------ | ------------------ |
| [Metric] | [Quantifiable target] | [How to measure] |

## 6. Functional Requirements

### 6.1 [Requirement Area]

| ID | Requirement | Priority | Notes |
| -- | ----------- | -------- | ----- |
| FR-001 | [Testable requirement] | Must Have / Should Have / Nice to Have | [Context] |

## 7. Non-Functional Requirements

| ID | Category | Requirement | Target |
| -- | -------- | ----------- | ------ |
| NFR-001 | [Category] | [Requirement] | [Measurable target] |

## 8. Constraints and Dependencies

### 8.1 Technical Constraints

[Platform, technology, and compatibility constraints.]

### 8.2 Business Constraints

[Timeline, budget, team, and regulatory constraints.]

### 8.3 Dependencies

| Dependency | Type | Impact if Unavailable |
| ---------- | ---- | --------------------- |
| [Dependency] | Hard / Soft | [Impact] |

## 9. User Workflows

### 9.1 [Workflow Name]

**Actor:** [User type]
**Trigger:** [Trigger]
**Preconditions:** [Preconditions]

1. [Step]
2. [Step]
3. [Step]

**Postconditions:** [Resulting state]
**Error Cases:** [Failures and expected behavior]

## 10. Phasing and Milestones

### 10.1 Phase Breakdown

| Phase | Scope | Target | Key Deliverables |
| ----- | ----- | ------ | ---------------- |
| Phase 1 | [Scope] | [Date or relative target] | [Deliverables] |

### 10.2 MVP Definition

[Smallest useful product subset.]

## 11. Risks and Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
| - | ---- | ---------- | ------ | ---------- |
| 1 | [Risk] | High/Med/Low | High/Med/Low | [Strategy] |

## 12. Open Questions

| # | Question | Owner | Impact | Target Resolution Date |
| - | -------- | ----- | ------ | ---------------------- |
| 1 | [Question] | [Owner] | [What it blocks] | [Target] |

## 13. Glossary

| Term | Definition |
| ---- | ---------- |
| [Term] | [Project-specific definition] |

## Appendix

### A. References

[Sources used.]

### B. Related Projects

[Interacting or dependent projects.]

### C. Decision Log

| # | Decision | Date | Rationale | Alternatives Considered |
| - | -------- | ---- | --------- | ----------------------- |
| 1 | [Decision] | [Date] | [Why] | [Alternatives] |
```

Do not leave placeholder text. Move genuine unknowns to Open Questions. Record Q&A decisions and rejected alternatives in the Decision Log. Present the draft for review; revise up to two additional times for substantial feedback.

### 5. Create product-level verifications

Derive happy paths, critical failures, and explicit edge cases from each workflow and functional requirement. Organize documents in `verifications/` by persona or workflow. Use this exact scenario schema:

```markdown
# User Scenarios: [Area Name]

**PRD:** [../prd.md](../prd.md)
**Created:** [ISO 8601 timestamp with Mountain offset]

---

## US-001: [Scenario Title]

**User:** [Persona]
**PRD Reference:** [FR-XXX, Workflow 9.X]
**Priority:** [Must Have / Should Have / Nice to Have]

### Scenario

[User-level narrative.]

### Preconditions

- [Precondition]

### Steps

1. [Product-level user action]
2. [Next action]

### Expected Outcome

- [Observable result]
- [Visible state change]

### Acceptance Criteria

- [ ] [Specific criterion]
- [ ] [Specific criterion]

---
```

Do not include commands, endpoints, fixtures, or implementation detail. Add this matrix to the main verification document, or create `coverage-matrix.md` when there are several files:

```markdown
## Coverage Matrix

| PRD Requirement | Priority | Scenario(s) | Status |
| --------------- | -------- | ----------- | ------ |
| FR-001 | Must Have | US-001, US-003 | Covered |
```

All Must Have rows must be `Covered` before completion.

### 6. Add useful supporting material

Create `documents/` entries only for substantial project-specific research such as comparisons, market findings, complex constraints, meeting records, or standards summaries. Each starts with:

```markdown
# [Document Title]

**Related PRD Sections:** [Sections]
**Created:** [ISO 8601 timestamp with Mountain offset]

---
```

Create `kb/` entries only for reusable domain concepts, technology primers, guiding patterns, or institutional context. Use:

```markdown
# [Topic Title]

**Category:** [Domain Concept / Technology Primer / Architecture Pattern / Reference]
**Created:** [ISO 8601 timestamp with Mountain offset]
**Related PRD Sections:** [Sections]

---

[Concise, factual, actionable content for a new team member.]
```

### 7. Finalize indexes and links

List every created document in its folder index. Keep `features/index.md` empty. Add this root summary:

```markdown
---

## Project Summary

| Section | Status | Document Count |
| ------- | ------ | -------------- |
| PRD | [Draft/Approved] | 1 |
| Documents | [count or "None"] | [count] |
| Features | Not Started | 0 |
| Knowledge Base | [count or "None"] | [count] |
| Verifications | Draft | [count] |

**Total User Scenarios:** [count]
**Must-Have Requirements:** [count]
**Open Questions:** [count]

---

## Next Steps

1. Review and approve the PRD
2. Resolve open questions in PRD Section 12
3. Use `new-eng-feature <features/feature-slug> <spec links>` for individual engineering features
```

Verify every relative link, timestamp, count, and parent link.

## Output Formatting

Produce Markdown artifacts exactly as specified. Keep prose direct and project-specific. Report completion with:

- all created paths;
- PRD status;
- total scenarios and Must Have coverage;
- open questions;
- created supplementary and KB entries;
- recommended next steps.

Report problems under `Problems`, each with `Issue`, `Impact`, and `Next action`. Treat missing output directory/context, inaccessible required sources, an unapproved PRD, and uncovered Must Have requirements as blockers. Treat unavailable optional research, deferred product decisions, and omitted optional documents as non-blocking and record them in the PRD or final handoff.
