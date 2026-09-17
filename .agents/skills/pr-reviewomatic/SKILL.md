---
name: pr-reviewomatic
description: Three-perspective code review for local changes and GitHub PRs. Use to review code through API/systems, concurrency/architecture, and quality/correctness lenses; post inline PR comments; resolve this skill's prior comments; or scan for review-ready PRs.
---

# PR Review-O-Matic

Review code with high precision and constructive language. Keep the three perspectives distinct, but return one deduplicated report.

## Inputs

Accept:

- `mode`: `local`, `review`, `resolve`, or `scan`.
- `scope`: paths, diff, commit or range, branch changes, staged changes, or unstaged changes.
- `pr-ref`: PR URL, number, or `#number`; omit to discover from the current branch.
- `--auto-comment`: post all reportable findings without another selection step.
- `--confidence=N`: threshold; default 80.
- Caller-provided context, diff-visible lines, prior findings, or authorization.

Infer `review` from a PR reference and `local` otherwise. Ask only if ambiguity affects the result. When delegated, reuse the caller's scope and decisions without asking again.

In local mode with no scope, prefer branch changes against `main` or `origin/main`, then staged and unstaged changes. Report an empty scope plainly.

## Requirements and Skill Boundaries

- Review only; do not edit code.
- Posting, replying, and resolving on GitHub require explicit authorization unless `--auto-comment` or delegated authorization applies.
- Anchor inline PR findings to changed diff lines. Read surrounding code before judging them.
- Resolve only threads marked `<!-- pr-reviewomatic -->`.
- Read applicable `AGENTS.md`; treat `CLAUDE.md` only as legacy repository guidance.
- Project conventions override generic preferences.
- Report only findings at or above the active threshold. Do not manufacture findings.
- Keep PR-visible text respectful, educational, and specific.
- Return full results to the direct user or delegating caller.

### GitHub access (load on demand)

Uses the local GitHub toolkit (`ghtk`, stdlib-only, works in-sandbox — no sandbox bypass needed). Full reference: `~/.local/bin/github-toolkit/README.md` (read only when needed). **Below, `ghtk` is shorthand for `python3 "$HOME/.local/bin/github-toolkit/ghtk"`** — invoke it by that explicit path. Add `--json` for machine-readable output.

```bash
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr get [PR_REF]
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr threads PR_NUMBER --unresolved-only --mine-only --marker '<!-- pr-reviewomatic -->' --include-outdated
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr comment PR_NUMBER --comments-file /path/to/comments.json --marker '<!-- pr-reviewomatic -->'
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr reply THREAD_ID --body "reply"
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr resolve THREAD_ID
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr scan --drop-drafts --drop-human-reviewed --drop-ci-failing
```

## Core Skill Process

### 1. Gather scope

Use the supplied local scope. Common commands:

```bash
git diff main...HEAD
git diff
git diff --cached
git diff main...HEAD -- path/to/file
```

For `review` or `resolve`, discover the PR (`ghtk pr get`), record its metadata, and fetch `ghtk pr diff PR_NUMBER`. In resolve mode fetch owned unresolved threads with `ghtk pr threads PR_NUMBER --unresolved-only --mine-only --marker '<!-- pr-reviewomatic -->' --include-outdated`.

For `scan`, run `ghtk pr scan --drop-drafts --drop-human-reviewed --drop-ci-failing`. Present non-draft PRs with no human review and no failing CI checks. Review them one at a time, asking before each unless the caller authorized queue processing.

### 2. Establish context

Read repository guidance, changed files, surrounding code, relevant tests, and sibling patterns. Detect languages, frameworks, supported versions, public interfaces, and persisted data.

For PR review and scan, build the set of diff-visible `(file, line)` anchors.

### 3. Apply three perspectives

#### A. API & Systems

Review:

- Released API, schema, CLI, configuration, CRD, migration, and serialization compatibility.
- Additive evolution, immutable field identifiers, and older-client behavior.
- Configuration/build synchronization and dependency changes.
- Error propagation, useful non-duplicate logging, and operability.
- Naming consistency, dead code, stale comments, user-visible documentation, and changelog requirements.

#### B. Concurrency & Architecture

Review:

- Shared-state synchronization, collection iteration, lock coverage, goroutine/task lifecycle, and cancellation.
- Layer and component ownership, data flow, and validation placement.
- Transactions, stored-data integrity, and unauthenticated resource pressure.
- Unnecessary coupling or indirection, existing abstraction reuse, canonical file/config placement, and consistent naming.
- Preventive designs when they produce clearer and safer behavior than retries.

#### C. Quality & Correctness

Review:

- Project-guideline compliance.
- Logic, nil/null handling, races, leaks, security issues, performance regressions, and misleading errors.
- Silent failures, ignored errors, and unsafe fallback defaults.
- Duplicate literals, constants, redundant conditions, duplicated logic, and standard-library opportunities.
- Idiomatic language use supported by the project version.
- Test value, coverage, isolation, and determinism.
- Documentation commands and examples when docs are part of the change.

For a deeper general review, a caller may chain `comp-reviewomatic` in local mode. For dedicated tests use `eng-test-reviewer`; for docs use `doc-reviewomatic` in local mode. Do not invoke these unless the request includes the broader chained review.

### 4. Delegate and consolidate

If subagents are available and delegation is allowed, run one agent per perspective in parallel. Supply full scope, relevant source, project guidance, threshold, and PR line constraints. Tell agents to review only, not re-delegate, and return file/line, category, evidence, impact, fix, and confidence.

Otherwise run all three perspectives directly. Deduplicate findings by cause and location, verify them against current code, and remove pre-existing, speculative, or stylistic issues.

Confidence:

- 90–100: certain, high-impact issue.
- 80–89: verified issue likely to matter.
- 70–79: include only when the threshold was lowered.
- Below 70: omit.

### 5. Post authorized comments

In `review` or `scan`, show the report first. Post only authorized findings; `--auto-comment` authorizes all findings at or above threshold.

```json
[{"path":"file.go","line":42,"body":"comment text"}]
```

Run `ghtk pr comment PR_NUMBER --comments-file <file> --marker '<!-- pr-reviewomatic -->'`. Explain why the issue matters and provide a concrete fix. The `--marker` value `<!-- pr-reviewomatic -->` is prefixed to every comment body.

### 6. Resolve owned comments

Read current code and replies for each owned thread. Classify it as `Addressed`, `Addressed differently`, `Declined with rationale`, or `Still open`. Present proposed actions before mutation unless already authorized. Resolve addressed issues, acknowledge alternate fixes or reasoned declines before resolving, and leave open issues unresolved.

## Output Formatting

### Review report

```markdown
# Code Review Report

**Scope:** [scope]
**Threshold:** [N]

### Critical
### [Finding title]
- **File:** path:line
- **Confidence:** N
- **Reviewer:** [A, B, or C]
- **Category:** [concern]
- **Issue:** [evidence and impact]
- **Suggestion:** [specific fix]

### Important
[same fields]

### Summary
- **Total findings:** N
- **Critical:** N
- **Important:** N
- **Perspectives applied:** A, B, C
```

If no finding meets the threshold, say so directly.

After posting, report PR, count, review URL when available, and each posted file/line/category/confidence. After resolution, report reviewed, replied, resolved, left open, and failed counts.

For errors, report the failed operation and exact error, completed work, whether results are partial, and the safe next action. Ask for a PR reference if discovery fails; report empty scans plainly; continue past isolated thread failures and list them.
