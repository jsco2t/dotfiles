# Project Templates

Use established formats when creating the corresponding artifact. Replace example instructions with actual content.

## Root Index

```markdown
# [Project Name] — Project Documentation

**Project:** [Project name]
**Jira:** [Epic key(s) and links, if available]
**Created:** [ISO 8601 timestamp with current Mountain offset, e.g., 2026-04-29T10:00:00-06:00]
**Status:** Draft

---

## Documentation Structure

| Folder                                       | Purpose                                                                       | Index                                              |
| -------------------------------------------- | ----------------------------------------------------------------------------- | -------------------------------------------------- |
| [`prd.md`](prd.md)                           | Product Requirements Document — the product specification                     | —                                                  |
| [`documents/`](documents/index.md)           | Supplementary documents, research, and reference materials                    | [documents/index.md](documents/index.md)           |
| [`features/`](features/index.md)             | Feature plans (`new-quick-feature`, `new-drd`)                                | [features/index.md](features/index.md)             |
| [`kb/`](kb/index.md)                         | Knowledge base — domain knowledge, glossaries, and reference docs             | [kb/index.md](kb/index.md)                         |
| [`verifications/`](verifications/index.md)   | User scenarios — acceptance-level verification of product behavior            | [verifications/index.md](verifications/index.md)   |
```

## Child Index

```markdown
# [Folder Name] Index

**Parent:** [../index.md](../index.md)
**Last Updated:** [ISO 8601 timestamp with current Mountain offset]

---

| Document | Description | Created |
| -------- | ----------- | ------- |
```

## Features Index

```markdown
# Features Index

**Parent:** [../index.md](../index.md)
**Last Updated:** [ISO 8601 timestamp with current Mountain offset]

---

This folder contains feature plans. Each subdirectory is a self-contained feature documentation tree with its own index.

| Feature | Slug | Jira | Status | Index |
| ------- | ---- | ---- | ------ | ----- |

_No features planned yet. Use `new-quick-feature <this folder> <spec links or description>` for a small feature, or `new-drd <feature-directory>/drd.md <spec links>` for a larger unit of work._
```

## PRD

```markdown
# Product Requirements Document: [Project Name]

**Version:** 1.0
**Author:** [User name if known, otherwise "Product Team"]
**Created:** [ISO 8601 timestamp with current Mountain offset]
**Last Updated:** [ISO 8601 timestamp with current Mountain offset]
**Status:** Draft
**Jira:** [Epic key(s) and links, if available]

---

## 1. Executive Summary

[2-3 paragraph summary: what the product is, why it exists, who it's for, and the high-level approach]

---

## 2. Problem Statement

### 2.1 Problem Description

[Clear articulation of the problem being solved]

### 2.2 Current State

[What exists today and why it's insufficient]

### 2.3 Impact of Not Acting

[What happens if this product is not built]

---

## 3. Users and Personas

### 3.1 Primary Users

[For each user type: role, technical level, primary goals, typical workflows]

### 3.2 Secondary Users

[Users who interact with the product indirectly or occasionally]

### 3.3 Stakeholders

[Non-users who have requirements or influence: ops, legal, finance, etc.]

---

## 4. Goals and Non-Goals

### 4.1 Goals

[Numbered list of what this product MUST achieve]

### 4.2 Non-Goals

[Explicit list of what this product will NOT do — scope boundaries]

### 4.3 Future Considerations

[Things that are out of scope for v1 but may be addressed later]

---

## 5. Success Metrics

| Metric | Target | Measurement Method |
| ------ | ------ | ------------------ |
| [Metric name] | [Quantifiable target] | [How to measure] |

---

## 6. Functional Requirements

### 6.1 [Requirement Area 1]

| ID | Requirement | Priority | Notes |
| -- | ----------- | -------- | ----- |
| FR-001 | [Requirement description] | Must Have / Should Have / Nice to Have | [Context] |

### 6.2 [Requirement Area 2]

[Repeat for each functional area]

---

## 7. Non-Functional Requirements

| ID | Category | Requirement | Target |
| -- | -------- | ----------- | ------ |
| NFR-001 | Performance | [Requirement] | [Measurable target] |
| NFR-002 | Security | [Requirement] | [Standard or target] |
| NFR-003 | Scalability | [Requirement] | [Target] |

---

## 8. Constraints and Dependencies

### 8.1 Technical Constraints

[Technology, platform, compatibility requirements]

### 8.2 Business Constraints

[Timeline, budget, team, regulatory]

### 8.3 Dependencies

| Dependency | Type | Impact if Unavailable |
| ---------- | ---- | --------------------- |
| [Dependency] | Hard / Soft | [What happens without it] |

---

## 9. User Workflows

### 9.1 [Workflow Name]

**Actor:** [User type]
**Trigger:** [What initiates the workflow]
**Preconditions:** [What must be true before starting]

1. [Step 1]
2. [Step 2]
3. [Step 3]

**Postconditions:** [What is true after completion]
**Error Cases:** [What can go wrong and expected behavior]

[Repeat for each major workflow]

---

## 10. Phasing and Milestones

### 10.1 Phase Breakdown

| Phase | Scope | Target | Key Deliverables |
| ----- | ----- | ------ | ---------------- |
| Phase 1 | [Scope] | [Date or relative] | [Deliverables] |

### 10.2 MVP Definition

[What constitutes the minimum viable product — the smallest useful subset]

---

## 11. Risks and Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
| - | ---- | ---------- | ------ | ---------- |
| 1 | [Risk] | High/Med/Low | High/Med/Low | [Strategy] |

---

## 12. Open Questions

| # | Question | Owner | Impact | Target Resolution Date |
| - | -------- | ----- | ------ | ---------------------- |
| 1 | [Question] | [Who should answer] | [What it blocks] | [When] |

---

## 13. Glossary

| Term | Definition |
| ---- | ---------- |
| [Term] | [Definition in context of this product] |

---

## Appendix

### A. References

[All source documents, Jira links, Confluence pages, external resources used]

### B. Related Projects

[Other projects or features that interact with or depend on this one]

### C. Decision Log

| # | Decision | Date | Rationale | Alternatives Considered |
| - | -------- | ---- | --------- | ----------------------- |
| 1 | [Decision] | [Date] | [Why] | [What else was considered] |
```

## User Scenario

```markdown
# User Scenarios: [Area Name]

**PRD:** [../prd.md](../prd.md)
**Created:** [ISO 8601 timestamp with current Mountain offset]

---

## US-001: [Scenario Title]

**User:** [Persona from PRD Section 3]
**PRD Reference:** [FR-XXX, Workflow 9.X]
**Priority:** [Must Have / Should Have / Nice to Have — matches the requirement priority]

### Scenario

[Narrative description of what the user does, written in second person ("You...") or third person ("The admin...")]

### Preconditions

- [What must be true before this scenario starts]

### Steps

1. [User action — described at the product level, not CLI/API level]
2. [Next action]
3. [Next action]

### Expected Outcome

- [Observable result from the user's perspective]
- [State change that should be visible]

### Acceptance Criteria

- [ ] [Specific, checkable criterion]
- [ ] [Another criterion]

---
```

## Scenario Coverage Matrix

```markdown
## Coverage Matrix

| PRD Requirement | Priority | Scenario(s) | Status |
| --------------- | -------- | ----------- | ------ |
| FR-001 | Must Have | US-001, US-003 | Covered |
| FR-002 | Must Have | US-005 | Covered |
| FR-003 | Should Have | — | Not Yet Covered |
```

## Supplementary Document

```markdown
# [Document Title]

**Related PRD Sections:** [List which PRD sections this supports]
**Created:** [ISO 8601 timestamp with current Mountain offset]

---

[Content]
```

## KB Seed

```markdown
# [Topic Title]

**Category:** [Domain Concept / Technology Primer / Architecture Pattern / Reference]
**Created:** [ISO 8601 timestamp with current Mountain offset]
**Related PRD Sections:** [List relevant PRD sections]

---

[Content — concise, factual, actionable. Written so a new team member can get up to speed.]
```

## Project Summary

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

**Total User Scenarios:** [count from verifications]
**Must-Have Requirements:** [count from PRD]
**Open Questions:** [count from PRD Section 12]

---

## Next Steps

1. Review and approve the PRD
2. Resolve open questions in PRD Section 12
3. Plan individual features inside `features/`: `new-quick-feature` for small features, `new-drd` for larger units of work
```
