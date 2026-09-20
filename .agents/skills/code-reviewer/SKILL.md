---
name: code-reviewer
description: Compatibility entry point for high-confidence local code review. Use when asked to review code, diffs, files, commits, or working-tree changes for bugs, security, compatibility, concurrency, observability, quality, tests, documentation accuracy, and project conventions; delegates the review to comp-reviewomatic in local mode.
---

# Code Reviewer

Use `comp-reviewomatic` in local mode as the canonical implementation of this review. This skill preserves the simpler `code-reviewer` entry point for users and chained workflows.

## Inputs

Accept a caller-provided diff, file list, directory, commit, commit range, review description, confidence threshold, or no explicit scope.

- Pass all supplied scope and context to `comp-reviewomatic`.
- Set mode to `local`, even when the input came from a PR diff supplied by the caller; this adapter never posts or resolves GitHub comments.
- Preserve a supplied confidence threshold. Otherwise use 80.
- If no scope is supplied, let `comp-reviewomatic` apply its local-scope defaults.
- In delegated use, do not re-ask questions already resolved by the caller.

## Requirements and Skill Boundaries

- This is review-only. Do not edit code or mutate GitHub state.
- Invoke `comp-reviewomatic` in local mode; do not reimplement or recursively invoke `code-reviewer`.
- Review applicable code, tests, configuration, build files, migrations, and documentation in the selected change.
- Read applicable `AGENTS.md` guidance. Treat `CLAUDE.md` as legacy repository guidance when present.
- Ground findings in the source and surrounding context.
- It is valid to report no findings. Do not invent issues to appear productive.
- Return actionable results to the direct user or delegating caller.

## Core Skill Process

1. Resolve the requested scope without changing it.
2. Run `comp-reviewomatic` in `local` mode with that scope and threshold.
3. Ensure the review covers applicable concerns: compatibility and schema safety, security, bugs, concurrency, error handling, observability, data integrity, project conventions, dead code, idiomatic language use, build/configuration consistency, test quality, and documentation accuracy.
4. Preserve the canonical review's evidence, confidence scores, line references, and fix suggestions.
5. Deduplicate findings if the caller supplied additional review results.

If `comp-reviewomatic` cannot be invoked, report the dependency failure and stop. Do not silently substitute a weaker ad hoc review.

## Output Formatting

Return the `comp-reviewomatic` local-mode report:

- Scope and confidence threshold.
- Findings grouped as **Critical** (90–100) and **Important** (80–89, or the caller's threshold).
- For each finding: file and line, category, evidence, impact, confidence, and concrete fix.
- Summary counts and a direct clean-review statement when no findings survive.

For failures, state what could not run, any scope that was gathered successfully, whether the result is partial, and the exact action needed to continue.
