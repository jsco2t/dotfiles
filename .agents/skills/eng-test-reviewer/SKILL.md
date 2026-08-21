---
name: eng-test-reviewer
description: Reviews tests for value, reliability, architecture, maintainability, regression coverage, data integrity, security boundaries, interface boundaries, thread safety, idiomatic Go, and readability using configurable effort weights. Use for focused test review of local changes, paths, commits, PR diffs, or completed task-plan work before merge.
---

# Engineering Test Reviewer

Treat test code as production code. Prefer tests that protect meaningful behavior, fail deterministically, and remain easy to understand and change.

## Inputs

Accept:

- A change description such as a commit range or caller-provided PR diff.
- A file or directory path.
- A task index whose completed items identify changed files.
- Caller-provided test files, production code, scope, project guidance, or effort weights.
- No input, in which case discover changed tests locally.

When invoked by another skill or agent, use the supplied scope and context. Do not ask again for resolved inputs.

With no scope:

1. Inspect unstaged and staged changes for tests.
2. If none exist, inspect `git diff HEAD~1 HEAD`.
3. If no changed tests are found, report that and stop.

## Requirements and Skill Boundaries

- Review only; do not edit tests or production code.
- Always read the production behavior under test. A test cannot be judged in isolation.
- Read applicable `AGENTS.md`; treat `CLAUDE.md` only as legacy repository guidance.
- Load default weights from `weights.md` in the same directory as this `SKILL.md`. Never assume a home-directory installation path.
- Caller-provided weights override the bundled file.
- All seven focus areas must exist. Fill missing areas with 0 and warn.
- Weights must be non-negative and total 100. If the positive total differs from 100, normalize proportionally and warn. If the total is 0, use the fallback defaults.
- Report the active weights and their source before the review.
- A zero-weight focus area is intentionally skipped; the five core responsibilities always apply.
- Do not invent findings. A clean test review is valid.
- Return actionable results to the direct user or delegating caller.

Fallback weights, matching the bundled configuration:

| Focus area | Effort |
| --- | ---: |
| Regression Tests | 15 |
| Data Access and Integrity Tests | 25 |
| Security Boundaries | 20 |
| Functional/Interface Boundaries | 20 |
| Thread Safety | 10 |
| Idiomatic Code | 5 |
| Readability | 5 |

## Core Skill Process

### 1. Resolve scope and weights

Gather test changes, related production code, relevant issue or task context, and repository conventions. Parse the bundled relative `weights.md` unless the caller supplied weights. Validate, normalize if needed, and show the resulting table.

### 2. Review core test quality

Apply every core responsibility at full depth:

1. **Value**
   - Find tautological or redundant tests.
   - Check critical paths, edge cases, invariants, and behavior contracts.

2. **Reliability**
   - Find uncontrolled time, randomness, filesystem ordering, network calls, shared state, races, and test-order dependence.
   - Avoid brittle assertions on incidental messages, ordering, timing, or exact floating-point values.

3. **Test architecture**
   - Prefer unit tests for isolated behavior, integration tests for real boundaries, and end-to-end tests for system assembly.
   - Flag tests at an unnecessarily expensive or ineffective level.

4. **Code quality**
   - Check clear arrange-act-assert flow, focused actions and assertions, minimal fixtures, correct cleanup, and behavior-oriented assertions.
   - Allow small amounts of repetition when abstraction would obscure intent.

5. **Maintenance burden**
   - Find over-mocking, fragile snapshots or golden files, opaque helpers, and oversized fixture data.

### 3. Review weighted focus areas

Use each weight to set investigation depth and reporting threshold:

- 20% or more: trace paths and boundaries thoroughly; threshold 65.
- 10–19%: targeted review; threshold 75.
- 1–9%: quick scan; threshold 85.
- 0%: skip.

Review:

1. **Regression Tests**
   - Verify bug fixes have a minimal test that reproduces the original failure and would catch reintroduction.

2. **Data Access and Integrity Tests**
   - Check creation defaults and constraints, authorized and unauthorized access, precise updates, deletion and cascades, soft-delete behavior, transactions, partial failures, and concurrent modification.

3. **Security Boundaries**
   - Check unauthenticated and unauthorized failures, malformed or hostile input, secret leakage, tenant/resource isolation, and privilege escalation.

4. **Functional/Interface Boundaries**
   - Check exported API contracts, gRPC/HTTP requests and responses, serialization, adapters, integration seams, and error propagation without internal leakage.

5. **Thread Safety**
   - Check concurrent access, race-detector coverage where applicable, cancellation, deadlocks, worker/goroutine lifecycle, channel behavior, and synchronization primitives.

6. **Idiomatic Code**
   - For Go, check table-driven tests, `t.Run`, `t.Helper`, `t.Cleanup`, `errors.Is`/`errors.As`, descriptive names, and standard `testing` patterns.
   - For other languages, apply the equivalent project-established testing idioms. Do not impose Go patterns.

7. **Readability**
   - Check that names state scenario and outcome, setup/action/assertion are easy to identify, noise is low, and comments explain why complex cases matter.

### 4. Delegate when useful

If subagents are available and delegation is allowed, divide non-overlapping core responsibilities and active focus areas among parallel agents. Give each the tests, production code, project context, weight, and threshold. Instruct agents to review only, not re-delegate, and return evidence, file/line, category, impact, fix, and confidence.

If delegation is unavailable, perform every active area directly. The result must not depend on subagent availability.

### 5. Validate and consolidate

Trace coverage claims to production branches and contracts. Remove speculative, preference-only, pre-existing, or duplicate findings.

Use this confidence guide:

- 90–100: actively harmful test, untested critical path, or severe suite-trust problem.
- 75–89: verified issue that materially affects quality.
- 65–74: notable issue shown only for high-effort focus areas.
- Below the applicable threshold: omit.

Core responsibilities always use a threshold of 75.

## Output Formatting

Start with:

- Scope and input source.
- Active weights and their source.
- A two- or three-sentence overall health assessment.

Group findings:

- **Critical**: confidence 90–100.
- **Important**: confidence 75–89.
- **Notable**: confidence 65–74, only from focus areas weighted at 20% or more.

For each finding include:

- Confidence and core/focus category.
- File path and line.
- Evidence and why it matters.
- A concrete fix or test case to add.

End with counts by severity, the focus areas with the most findings, and the highest-impact improvement. If nothing meets its threshold, state that the tests are solid within the reviewed scope.

For failures, state:

1. What failed, including weight parsing or scope discovery.
2. Which fallback was used.
3. What was reviewed successfully.
4. Whether the result is partial.
5. The exact input or action needed to continue.
