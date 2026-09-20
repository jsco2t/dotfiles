---
name: eng-design-creator
description: Turn an engineering research or implementation plan into an approved architecture and design document with explicit trade-offs, codebase-grounded component design, test strategy, risks, and implementation sequence. Use after eng-plan-creator or when a feature needs architectural decisions before task planning. Supports direct requests and delegated/chained workflows.
---

# Engineering Design Creator

Define how a planned feature should be implemented. Bridge the high-level engineering plan and detailed task planning without implementing the feature.

## Inputs

Accept:

- Path to the engineering research or implementation plan.
- Optional project or feature index path.
- Optional Jira/Confluence links and companion documents.
- Optional output path; otherwise write `<feature-name>-design.md` beside the research document.
- Caller-provided design decisions, constraints, approval state, and review instructions.

When delegated, honor caller-provided paths and decisions. Do not ask questions already answered in the supplied context. If the caller explicitly records approval, treat the design as approved; otherwise preserve the approval gate described below.

## Requirements and Skill Boundaries

- Produce architectural design, not implementation code or task documents.
- Trace every design decision to a requirement, constraint, codebase pattern, or measured need.
- Prefer simple, idiomatic designs that fit the current repository.
- Use modern language features only when supported by the repository's toolchain and compatibility requirements.
- Design for testability through clear boundaries and controlled dependencies; avoid introducing interfaces solely for speculative flexibility.
- Treat build, lint, test, migration, observability, and failure behavior as design concerns.
- Follow `AGENTS.md`; use `CLAUDE.md` only as legacy repository guidance when relevant.
- Do not update the source research document until the design is approved by the user or delegating caller.
- When source documents conflict, stop the affected decision and report the conflict instead of silently resolving it.
- A delegated invocation must return structured completion, approval-needed, or blocker status.

## Core Skill Process

### 1. Load the feature context

Resolve and read the research/implementation plan fully. If given an index, use it to locate the plan, design location, and related documents. Extract requirements, acceptance criteria, technical context, code impact, gaps, assumptions, and recommendations.

Fetch referenced Jira or Confluence sources with the available Atlassian connector when they contain decisions not fully captured locally. If no plan can be found and no safe path can be inferred, request the missing path.

### 2. Perform architectural codebase analysis

Verify the plan against current code. Inspect:

- Existing architectural and package boundaries.
- Similar features and dominant patterns.
- Interfaces, dependency construction, and extension points.
- Related data flow and serialization boundaries.
- Error creation, wrapping, reporting, and observability.
- Configuration, feature flags, migrations, and compatibility patterns.
- Existing test organization, fixtures, helpers, and integration environments.

Use direct repository searches and file reads. Cite concrete paths and symbols.

### 3. Resolve design decisions

For each material decision:

1. State the decision and why it matters.
2. Present at least two viable options when alternatives genuinely exist.
3. Compare complexity, maintainability, testability, compatibility, performance, and operational impact.
4. Recommend one option with evidence.
5. Classify it as agent-resolvable or requiring stakeholder input.

Ask only about decisions with meaningful product, UX, operational, or architectural trade-offs. Group related questions. When interactive input is unavailable, record the recommended option as provisional and return `approval-needed` rather than inventing a decision.

### 4. Design the test strategy

Specify:

- Unit boundaries, behaviors, edge cases, and dependency-control strategy.
- Integration boundaries that cannot be proven by unit tests.
- Reusable test helpers, fixtures, databases, or local environments.
- Regression coverage for each acceptance criterion and failure mode.
- Reliability and cleanup requirements.

Follow current repository test patterns. Do not mandate a library or mocking style the project does not use.

### 5. Write and validate the design

Create the design document using the required template. Validate that interfaces and files are plausible in the current checkout, all important decisions have rationale, the implementation sequence is dependency-aware, and open items are explicit.

### 6. Obtain approval and reconcile research

Present the design's key decisions, risks, and open items. Ask the direct user for approval unless approval was already supplied by the delegating caller.

On approval only, update the research document:

- Section 2.2: chosen architecture.
- Section 4.5: test strategy summary.
- Section 6.1: approved implementation approach.
- Section 6.3: link to the design as the first next step.
- Add Section 7 using the approval block below.

If changes are requested, revise the design and repeat approval. Do not describe an unapproved design as approved.

## Output Formatting

Create the design document with this structure:

````markdown
# Feature Design: [Feature Name]

**Design Date:** [Date]
**Based On:** [Research document path]
**Source Issues:** [Jira issues or None]
**Status:** Draft | Approved

---

## Executive Summary

[Design approach, key decisions, and direction in 2-3 paragraphs]

## 1. Design Context

### 1.1 Requirements Summary

[Requirements this design satisfies]

### 1.2 Constraints

[Technical, business, compatibility, and operational constraints]

### 1.3 Existing Patterns

[Relevant codebase patterns with file references]

## 2. Architectural Design

### 2.1 High-Level Architecture

[Components, relationships, and data flow; include an ASCII diagram only when useful]

### 2.2 Component Design

#### 2.2.1 [Component Name]

**Responsibility:** [Responsibility]

**Package:** [Location]

**Key Interfaces:**

```go
// [Interface purpose]
type [InterfaceName] interface {
    [Method signatures]
}
```

**Dependencies:**

- [Dependency and construction/injection approach]

### 2.3 Data Model

[Schema, protobuf, or data structure changes]

### 2.4 API Design

[External and internal API changes]

### 2.5 Error Handling and Observability

[Creation, wrapping, propagation, user surface, logs, and metrics]

### 2.6 Configuration and Rollout

[Options, defaults, loading, feature flags, migrations, and rollback]

## 3. Design Decisions

### 3.1 [Decision Title]

**Context:** [Why this decision exists]

| Option | Pros | Cons | Complexity |
| --- | --- | --- | --- |
| A: [Name] | [Pros] | [Cons] | Low/Med/High |
| B: [Name] | [Pros] | [Cons] | Low/Med/High |

**Decision:** [Chosen or Provisional option]

**Rationale:** [Evidence and trade-offs]

## 4. Test Strategy

### 4.1 Test Philosophy

[Overall approach]

### 4.2 Unit Tests

| Component | Test Focus | Controlled Dependencies | Approach |
| --- | --- | --- | --- |
| [Component] | [Behavior] | [Dependencies] | [Pattern] |

### 4.3 Integration Tests

[Scenarios and why unit tests are insufficient]

### 4.4 Test Infrastructure

[Helpers, fixtures, databases, or environments]

### 4.5 Coverage Goals

[Critical paths and acceptance criteria, not an arbitrary percentage]

## 5. Implementation Sequence

1. **[Step]** - [Reason and dependencies]

## 6. Risk Assessment

### 6.1 Technical Risks

| Risk | Impact | Likelihood | Mitigation |
| --- | --- | --- | --- |
| [Risk] | High/Med/Low | High/Med/Low | [Mitigation] |

### 6.2 Design Assumptions

- [Assumption and validation]

## 7. Open Items

1. [Item, impact, owner, and resolution condition]
````

After approval, append this block to the research document:

```markdown
---

## 7. Design Document

**Design Date:** [Date]
**Design Document:** [Relative path]
**Status:** Approved

### Key Design Decisions

- [Decision]: [Chosen approach]

### Test Strategy Summary

[1-2 paragraph summary]
```

Report to the user or caller with:

- `Status`: `complete`, `approval-needed`, `partial`, or `blocked`.
- `Design`: document path and current Draft/Approved state.
- `Research update`: updated path, `not updated (awaiting approval)`, or `not applicable`.
- `Decisions`: chosen and provisional decisions.
- `Open items`: unresolved questions.
- `Problems`: conflicts, missing sources, invalid paths, or unavailable connectors; use `None` when empty.
- `Next skill`: `$eng-test-planning` or `$eng-task-planning` after approval, as directed by the workflow.

For a blocker, state the exact missing input or conflict, evidence collected, completed work, and the minimum action needed to continue. Do not broaden scope or implement code.
