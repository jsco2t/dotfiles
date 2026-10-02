# DRD Template

Fill this structure from verified context and decisions; remove drafting instructions.

```markdown
# Delivery Requirements Document: [Unit of Work Name]

**Scope:** Product | Project
**Status:** Draft
**Author:** [User name if known, otherwise omit]
**Created:** [ISO 8601 timestamp with current Mountain offset]
**Last Updated:** [ISO 8601 timestamp with current Mountain offset]
**References:** [Jira/GitHub/Confluence links, source files]

---

## 1. Summary

[One short paragraph. Lead with WHAT ships, then the one-line WHY — the problem it closes.
No vision, no business case, no audience framing. A reader must know what this delivers from
the first sentence.]

---

## 2. Problem

### 2.1 Problem

[What is wrong or missing today, stated once, plainly — the gap this work closes. Not why it
matters to the business.]

### 2.2 Current State

[What exists today in the affected area and why it is insufficient. Be concrete — name the
systems, commands, files, or behaviors involved.]

---

## 2A. Existing Context  *(PROJECT scope only — omit for PRODUCT scope)*

### 2A.1 System Being Changed

[The existing system this work lives in. Link to its docs/repo. One or two sentences.]

### 2A.2 Current Behavior

[What the system does today in the area this work touches. Name the endpoints, commands, jobs,
or workflows that exist.]

### 2A.3 What Changes

[Explicit list of existing behaviors that will be modified or added.]

### 2A.4 What Does NOT Change

[Explicit list of existing behaviors deliberately preserved. Prevents scope creep and guards
against regressions.]

### 2A.5 Backward Compatibility

[What breaks, if anything; the migration path; any deprecation. If the work is purely additive,
say so in one line.]

---

## 3. Solution Approach

[The chosen solution at a WHAT level — the shape of the answer, enough for a builder to
understand the approach and for the deliverables below to make sense. Name the mechanism reused
or introduced, the pattern followed, and the boundary of the approach. Keep implementation
detail — file-level changes, code — out; that is the builder's job.]

---

## 4. Scope

### 4.1 Goals

[Numbered list of what this work must achieve. Objective-level.]

### 4.2 Non-Goals

[Explicit list of what this work will NOT do. As important as the goals — every scope boundary
goes here.]

### 4.3 Deferred

[Out of scope for this unit of work but a likely follow-on. Names what NOT to build now.]

---

## 5. Requirements

### 5.1 Functional Requirements

| ID | Requirement | Priority | Notes |
| -- | ----------- | -------- | ----- |
| FR-001 | [Specific, testable requirement] | Must / Should / Nice | [Context] |

### 5.2 Non-Functional Requirements

| ID | Category | Requirement | Target |
| -- | -------- | ----------- | ------ |
| NFR-001 | Performance / Security / … | [Requirement] | [Measurable target] |

---

## 6. Deliverables

### 6.1 Deliverable Inventory

| ID | Deliverable | Type | Description | Satisfies | Acceptance Criteria |
| -- | ----------- | ---- | ----------- | --------- | ------------------- |
| D-001 | [Name] | API / CLI / Config / Migration / Doc / CI / Binary / Library | [What it is. If it needs an operator procedure to be usable — a build/publish sequence, a migration run order — state it here.] | FR-001, FR-003 | [How you know THIS one is done] |

### 6.2 Not Deliverables

[Explicit list of artifacts this work does NOT produce — the deliverable-level counterpart to
non-goals. E.g. "No UI in this unit", "No public API docs yet".]

### 6.3 Coverage Matrix

| Requirement | Priority | Deliverable(s) | Status |
| ----------- | -------- | -------------- | ------ |
| FR-001 | Must | D-001 | Covered |
| FR-003 | Should | — | ⚠ Gap |

**Gaps:** [Any Must-Have requirement with no deliverable — these block implementation.]
**Unlinked Deliverables:** [Any deliverable satisfying no requirement — potential scope creep.]

---

## 7. Definition of Done

The unit of work is done when **all** per-deliverable acceptance criteria in §6.1 pass **and**
the unit-of-work-level gates below — the ones no single deliverable owns — are met:

- [ ] [Integration / end-to-end gate]
- [ ] [Verification gate — e.g. passes on every target platform/environment]
- [ ] [Documentation / handover gate]
- [ ] [Release / rollout gate, if any]

Do not restate per-deliverable criteria here — they live in §6.1 and are all required. This
section captures only what falls between or across deliverables.

---

## 8. Constraints and Dependencies

### 8.1 Technical Constraints

[Technology, platform, compatibility, or convention limits that bound the solution. Real
constraints on landing the work only.]

### 8.2 Dependencies

| Dependency | Type | Impact if Unavailable |
| ---------- | ---- | --------------------- |
| [Dependency] | Hard / Soft | [What is blocked without it] |

---

## 9. Sequencing

[The order deliverables should land, and the smallest first slice that is useful and verifiable.
Include only if sequencing matters — if everything can land together, say so in one line.]

| Step | Deliverables | Rationale |
| ---- | ------------ | --------- |
| 1 | D-001 | [Why first] |

---

## 10. Risks and Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
| - | ---- | ---------- | ------ | ---------- |
| 1 | [Delivery risk — what could stop the work landing] | High/Med/Low | High/Med/Low | [Strategy] |

---

## 11. Open Questions

| # | Question | Blocks | Owner |
| - | -------- | ------ | ----- |
| 1 | [Unresolved question] | [What it blocks] | [Who answers] |

⚠ **If any Must-Have requirement lacks a deliverable, or any question above blocks
implementation, this DRD is not ready for implementation.** Say so plainly.

---

## Appendix

### A. References

[Source documents, Jira/GitHub/Confluence links, files consulted.]

### B. Decision Log

| # | Decision | Rationale | Alternatives Considered |
| - | -------- | --------- | ----------------------- |
| 1 | [Decision made during Q&A] | [Why] | [What was rejected] |

### C. Glossary  *(optional)*

| Term | Definition |
| ---- | ---------- |
| [Term] | [Definition in the context of this work] |
```
