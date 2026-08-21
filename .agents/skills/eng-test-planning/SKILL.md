---
name: eng-test-planning
description: Analyze an engineering plan and companion design, study current repository test patterns, and append a concrete, unit-first test plan with requirement coverage, test cases, exclusions, infrastructure, and implementation order. Use before task decomposition or implementation when a feature needs a rigorous test strategy. Supports direct requests and delegated/chained workflows.
---

# Engineering Test Planning

Create the smallest reliable set of tests that gives confidence in the planned feature. Every proposed test must protect a meaningful behavior or regression.

## Inputs

Accept:

- Path to an engineering research/implementation plan.
- Optional feature index path used to locate the plan, design, and task documents.
- Optional design document, Jira/Confluence links, requirements, or caller-supplied context.
- Optional output instructions. By default, append the plan to the engineering plan document.

When delegated, honor supplied paths, decisions, and constraints. Do not repeat questions already answered by the caller. Read the latest document state immediately before editing.

## Requirements and Skill Boundaries

- Plan tests; do not implement production or test code.
- Prefer unit tests because they are faster and more isolated. Require integration or end-to-end tests only when a real boundary cannot be proven with unit tests.
- Every included test needs a concrete behavior, regression, or risk justification. Coverage percentage alone is not a justification.
- Every excluded behavior needs a reason.
- Design deterministic tests. Avoid timing, live network, shared-state, or external-service dependencies unless the plan also controls them reliably.
- Require cleanup for resources, goroutines, database rows, files, environment changes, and global state created by tests.
- Treat test code as production-quality code: simple, idiomatic, readable, and maintainable.
- Follow existing repository test frameworks and patterns. Do not introduce a new assertion, mock, fixture, or test framework without an explicit need.
- Trace tests to requirements and acceptance criteria. Identify uncovered or untestable requirements.
- Follow `AGENTS.md`; use `CLAUDE.md` only as legacy repository guidance when relevant.
- If implementation details are too uncertain for concrete test cases, report the gap rather than inventing APIs.
- A delegated invocation must return structured completion or blocker status.

## Core Skill Process

### 1. Locate and read planning context

Resolve the engineering plan. If given an index, use it to find the implementation plan, design, tasks, and expected output location. Read the plan fully and load relevant companion documents in the same feature directory, especially `<feature-name>-design.md` and existing task documents.

Extract requirements, acceptance criteria, affected code, architectural boundaries, failure modes, integration points, and existing testing guidance.

### 2. Study existing repository tests

Inspect tests around the affected code and similar features. Record:

- File placement, package naming, and naming conventions.
- Table-driven and subtest patterns.
- Assertion libraries and error-checking style.
- Dependency-control and mock conventions.
- Database, fixture, factory, and cleanup patterns.
- Shared test helpers and local integration environments.
- Native commands used to run focused and broader suites.

Reference representative files. Verify that proposed helpers and mock types do not already exist.

### 3. Map requirements to behaviors

For every requirement or acceptance criterion, identify:

1. Observable behavior.
2. Component or boundary under test.
3. Lowest reliable test level.
4. Regression or risk protected.
5. Existing coverage, if any.

Record gaps where a requirement cannot be tested with the current design. Suggest a design seam only when it materially improves testability.

### 4. Design concrete test cases

For unit tests, specify the function or method, inputs, outputs, errors, meaningful boundaries, controlled dependencies, and table rows or scenario categories.

For integration tests, explain why unit coverage is insufficient, define which components are real or controlled, and specify deterministic setup and teardown. Do not propose redundant integration coverage.

For every case, include a Go-style test name when this is a Go repository (otherwise use the repository's naming convention), value justification, expected behavior, and required infrastructure.

### 5. Plan supporting infrastructure

Reuse existing helpers and fixtures first. Add a helper only when multiple tests benefit. Record new mocks, fixtures, factories, embedded databases, or shared utilities with their consumers and cleanup behavior.

### 6. Validate and append

Before editing, reread the current plan and determine the next top-level section number. Append the template below without rewriting unrelated content. Confirm:

- Every requirement maps to a test, existing coverage, explicit exclusion, or open question.
- Every integration test has a unit-test insufficiency justification.
- All tests can run deterministically and clean up.
- Names, files, helpers, and commands match the current repository.
- The implementation order respects production-code and fixture dependencies.

## Output Formatting

Append this section to the engineering plan, using its next section number as `[N]`:

````markdown
---

## [N]. Test Plan

**Test Planning Date:** [Date]
**Principles:** Unit-first · Self-cleaning · Value-justified · Reliable · Production-quality

### [N].1 Existing Test Patterns

[Patterns followed, with representative file references]

**Assertion Library:** [Current project choice]

**Dependency-Control Strategy:** [Interfaces, fakes, mocks, real implementations]

**Test Helpers:** [Existing helpers to reuse]

### [N].2 Requirement Coverage

| Requirement / Criterion | Behavior | Planned Test or Existing Coverage | Gap |
| --- | --- | --- | --- |
| [Requirement] | [Observable behavior] | [Test or path] | None / [Gap] |

### [N].3 Test Cases - Unit Tests

#### [N].3.1 [Component/Package]

**File:** `path/to/component_test.go`

**Component Under Test:** `package.Component`

| Test Name | Verifies | Value Justification | Approach |
| --- | --- | --- | --- |
| `TestComponent_Method_HappyPath` | [Behavior] | [Regression/risk] | [Table/direct] |

**Controlled Dependencies:**

- `InterfaceName` - [Why and how it is controlled]

**Table-Driven Shape** (when useful):

```go
tests := []struct {
    name    string
    input   InputType
    want    OutputType
    wantErr bool
}{
    // [Scenario categories]
}
```

**Setup/Teardown Notes:** [Lifecycle requirements]

### [N].4 Test Cases - Integration Tests

#### [N].4.1 [Scenario]

**Justification:** [Why unit tests cannot prove this]

**Scope:** [Real and controlled components]

**File:** `path/to/integration_test.go`

| Test Name | Verifies | Value Justification | Setup Requirements |
| --- | --- | --- | --- |
| `TestIntegration_Scenario` | [Behavior] | [Regression/risk] | [Infrastructure] |

**Cleanup Requirements:** [Exact cleanup]

### [N].5 Test Infrastructure

#### New Mock or Fake Implementations

| Interface | Package | Used By | Exists Today? |
| --- | --- | --- | --- |
| `InterfaceName` | `package/path` | [Tests] | No - create / Yes - reuse |

#### New Test Helpers

| Helper | Purpose | Used By | Why It Should Be Shared |
| --- | --- | --- | --- |
| `helperName()` | [Purpose] | [Tests] | [Justification] |

#### Test Fixtures

| Fixture | Description | Used By | Cleanup |
| --- | --- | --- | --- |
| [Fixture] | [Data] | [Tests] | [Cleanup] |

### [N].6 Tests Explicitly Not Included

| Behavior / Component | Reason Not Tested |
| --- | --- |
| [Behavior] | [Existing coverage, no logic, unreliable assertion, or other concrete reason] |

### [N].7 Test Implementation Sequence

1. **[First]** - [Reason and dependency]
2. **[Second]** - [Dependency]

### [N].8 Open Questions and Testability Gaps

1. **[Question or gap]** - Affects: [tests/requirements]. Resolution: [needed input or design change].
````

Report to the user or caller with:

- `Status`: `complete`, `partial`, or `blocked`.
- `Updated document`: path and appended section number.
- `Coverage`: requirements mapped, existing coverage reused, and explicit exclusions.
- `Key test decisions`: unit/integration split and major infrastructure choices.
- `Open questions`: unresolved testability or behavior questions.
- `Problems`: invalid paths, conflicting plans, missing implementation detail, or unavailable sources; use `None` when empty.
- `Next skill`: usually `$eng-task-planning` when the test plan is ready.

For a blocker, preserve the plan unchanged unless a clearly valid partial section can be written. State the exact blocker, evidence gathered, completed work, and minimum input needed. When test code is later implemented, use `$eng-test-reviewer` (or equivalent available invocation mechanism) for the specialized test review.
