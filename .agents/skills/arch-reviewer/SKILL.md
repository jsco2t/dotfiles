---
name: arch-reviewer
description: Reviews code architecture for maintainability, testability, separation of concerns, dependency direction, pattern fit, unnecessary abstraction, and long-term durability. Use for architecture reviews of local changes, commits, ranges, files, directories, or delegated review scopes; do not use as a general bug, security, style, documentation, or test review.
---

# Architecture Reviewer

Review architecture pragmatically. Flag structure only when it creates a concrete cost: harder changes, poor testability, hidden coupling, fragile state, or avoidable cognitive load. It is valid to find no issues.

## Inputs

Accept:

- A file or directory path for whole-code review.
- A commit or commit range for diff review.
- Multiple file paths for whole-code review.
- A caller-provided diff, file list, baseline, project conventions, or review mode.
- No input, in which case infer the scope from the current repository.

When invoked by another skill or agent, use the supplied scope and context. Do not repeat discovery or ask questions already answered by the caller.

With no explicit scope:

1. If the current branch is not `main`, review `git diff main...HEAD`; use `origin/main` if local `main` is absent.
2. On `main`, review tracked changes with `git diff HEAD` and review untracked files as whole code.
3. If the working tree is clean, report that no reviewable scope was found and ask for a path, commit, or range.

## Requirements and Skill Boundaries

- Review only architecture and structure. Do not edit code.
- In diff mode, judge how changed code fits its surroundings. Read adjacent unchanged code, but anchor findings to the change or its direct impact.
- In whole-code mode, evaluate the supplied code as it exists.
- Read applicable `AGENTS.md` files first. Treat `CLAUDE.md` only as legacy repository guidance when present. Sample sibling code to learn established patterns.
- Do not reject a dominant, documented project pattern merely because another design is possible.
- Skip generated code, vendored dependencies, `testdata/`, fixtures, and golden files. Check generated-file headers when uncertain.
- If the scope exceeds about 40 relevant files, report the size and recommend narrower package-level reviews. Continue only when the caller already requested the broad scope or explicitly delegated it.
- Report only findings with confidence of at least 80/100.
- Every finding must identify a concrete cost. Preference without cost is not a finding.
- Route out-of-scope work as follows:
  - Bugs, security, compatibility, concurrency correctness, logging, and general code quality: `comp-reviewomatic` in local mode.
  - Documentation quality: `doc-reviewomatic` in local mode.
  - Test quality and coverage: `eng-test-reviewer`.
- Do not invoke those skills unless the caller requested a broader chained review. Otherwise, list out-of-scope observations briefly.

## Core Skill Process

### 1. Resolve scope and baseline

Determine diff or whole-code mode. Gather the relevant files, exclude generated material, read project guidance, and inspect enough sibling code to understand local conventions.

Detect the language and stack. Apply language-specific architecture norms only when they fit the project:

- Go: consumer-owned small interfaces, flat cohesive packages, explicit dependencies, intentional `internal/` boundaries, and no hidden `init` or `context.Value` dependency injection.
- Rust: traits driven by real polymorphism, deliberate visibility, and owned public boundaries where practical.
- TypeScript/JavaScript: composition over deep class/HOC hierarchies, restrained context use, and awareness of barrel-file coupling.
- Python: explicit control flow; use metaclasses, descriptors, hooks, ABCs, and protocols only when they provide demonstrated value.

### 2. Review architecture dimensions

Evaluate each applicable dimension:

1. **Separation of concerns**: Find cross-layer logic, mixed abstraction levels, and components with unrelated responsibilities.
2. **Testability**: Find hidden dependencies, global state, side-effecting constructors, and logic that requires full-system setup to test.
3. **Dependency direction and coupling**: Find upward dependencies, implementation leakage, cycles, and changes that require edits across unrelated packages.
4. **Over-abstraction**: Find single-purpose wrappers, speculative interfaces or generics, redundant factories, and deep delegation without behavior.
5. **Hidden control flow**: Find reflection wiring, import-time registration, service locators, behavior-heavy tags, in-process event buses, dependency smuggling, and invisible middleware mutation.
6. **Language fit**: Check that patterns match the detected language and supported version.
7. **Simplicity and durability**: Find accidental complexity, temporal coupling, framework-within-framework designs, and premature scale or extensibility.
8. **API shape**: Find leaked internals, god parameters, and inconsistent abstraction levels. Leave compatibility analysis to `comp-reviewomatic`.
9. **State ownership**: Find unclear owners, global mutable state, and duplicated sources of truth. Leave locking correctness to `comp-reviewomatic`.
10. **Composition and extension points**: Check that likely variants can be added cleanly, while rejecting speculative plugin systems and unused extension points.

### 3. Validate and consolidate

Trace each candidate finding through callers, dependencies, and tests. Discard findings that are pre-existing but unaffected in diff mode, established project conventions, speculative preferences, or unsupported assumptions.

If subagents are available and the caller permits delegation, review independent dimensions in parallel. Give each agent the scope, mode, project baseline, language context, and one or more non-overlapping dimensions. Instruct agents to review only and return evidence, confidence, concrete cost, and a fix direction. If delegation is unavailable, perform the same review directly. The result must not depend on subagents being available.

Deduplicate overlapping findings and retain the clearest evidence and highest justified confidence.

Confidence guide:

- 90–100: clear structural defect with immediate cost.
- 80–89: verified design problem with a concrete maintenance or testability cost.
- Below 80: omit.

## Output Formatting

Start with the scope and mode. Group findings by severity:

- **Critical**: confidence 90–100.
- **Important**: confidence 80–89.

For each finding include:

- Title and confidence.
- Architecture dimension.
- File path and line number.
- Evidence.
- Concrete cost.
- Language or project context when relevant.
- A specific improvement direction.

End with finding counts and any one-line out-of-scope observations. If nothing meets the threshold, say so directly and briefly name the structural qualities that are working well.

If scope discovery, repository access, or delegated review fails, state:

1. What failed.
2. What was successfully reviewed.
3. Whether the result is partial.
4. The exact input or action needed to continue.
