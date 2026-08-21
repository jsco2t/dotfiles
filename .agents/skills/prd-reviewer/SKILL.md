---
name: prd-reviewer
description: Review a Product Requirements Document for clarity, completeness, conflicts, traceability, and engineering readiness. Use with local documents, Jira or Confluence content, GitHub issues or PRs, or inline text when a requirement inventory and actionable readiness assessment are needed.
---

# PRD Reviewer

## Inputs

- PRD source: file path, Jira or Confluence URL/key, GitHub URL/number, or inline text.
- Optional output path.
- Optional caller-provided source bundle, scope, or resolved decisions.

If the source is missing and cannot be inferred, request it. Write to the supplied output path; otherwise respond in the conversation.

## Requirements and Skill Boundaries

- Stay read-only with respect to source systems. Do not edit source documents, post comments, transition issues, or create tickets.
- Build one numbered requirement inventory (`R1`…`Rn`) and reference it throughout the review.
- Trace every requirement and finding to a source location.
- State the engineering consequence of every gap, conflict, or blocker.
- Report conflicts only when two cited statements demonstrably disagree.
- Do not rewrite the PRD. Explain what the owner must decide, define, or add.
- Include specific strengths so the author knows what to preserve.
- Distinguish incomplete context from defects in the PRD.
- When delegated, reuse fetched sources and caller decisions. Return the artifact path, readiness verdict, top blockers, and source-access problems.

## Core Skill Process

### 1. Acquire bounded source context

- **Local document:** Read it and directly referenced supporting documents.
- **Jira/Confluence:** Read the root issue/page, its parent epic when applicable, the epic's immediate children, linked Confluence pages, one descendant level, and root/epic comments. Stop after this boundary.
- **GitHub:** Read the issue or PR, directly linked issues, and referenced repository documents.
- **Inline text:** Review it as supplied and flag the limited context.

Create a source manifest listing everything read and everything referenced but unread, with reasons such as boundary, access failure, or dead link. Warn when missing sources could change the conclusions.

### 2. Extract requirements

Explain briefly:

1. which explicit behavior, acceptance criteria, and imperative specifications became requirements;
2. how MUST, SHOULD, and UNCLEAR language informed interpretation;
3. how complementary sources were merged and cited;
4. how requirements were grouped and split.

Group the inventory by the PRD's topic structure. Use one independently testable behavior per entry:

```markdown
### [Topic]

- **R1.** [Testable requirement]
  — *source:line or document § section*
```

Do not turn rationale or architecture commentary into requirements. Split behaviors only when they could ship independently.

### 3. Summarize scope

Explain in plain language, within two or three short paragraphs, the problem, audience, proposed outcome, and user-visible change. Then list explicit in-scope, out-of-scope, and ambiguous items.

### 4. Review four dimensions

#### What makes sense

Identify clear requirements, strong constraints, usable acceptance criteria, sound scope decisions, and internally consistent groups. Explain why each strength helps delivery.

#### What is missing

Check user and failure flows, non-functional requirements, data models, API contracts, migration/rollback, prioritization, personas, terminology, and placeholders. Report only gaps with a concrete engineering consequence.

```markdown
#### Gap: [title]

*Affects: R3, R7*

[What engineering cannot decide, estimate, implement, or test and why.]

**What's needed:** [specific missing decision or definition]
```

#### What conflicts

Show both cited sides of each contradiction and explain the implementation impact.

```markdown
#### Conflict: [title]

[Impact]

- **Location A:** [statement and citation]
- **Location B:** [incompatible statement and citation]

**Resolution needed:** [decision required]
```

#### What blocks discrete tasks

Attempt to name implementation tasks and testable done conditions for every requirement. Classify each as `Ready`, `Partial`, or `Blocked`.

| Requirement | Status | Task or blocker summary |
|-------------|--------|-------------------------|

Expand only partial and blocked entries, stating what would unblock them. Count each status and prioritize blockers that unlock the most work.

### 5. Decide readiness

State whether engineering can create discrete tasks now. If not, identify the three highest-impact corrections.

## Output Formatting

```markdown
# PRD Review: [Title]

**Reviewed:** [date]
**Source:** [source]

## Source Manifest

## Requirement Extraction Methodology

## Requirement Inventory

## Part 1: Summary

### What This PRD Is About

### Scope Boundaries

## Part 2: Comprehensive Review

### What Makes Sense

### What Is Missing

### What Conflicts

### What Blocks Engineering

## Verdict
```

Omit no required review dimension, but state “No demonstrated conflicts found” when appropriate. Report unread sources, permission failures, weak citations, and uncertain interpretations with their impact on confidence.
