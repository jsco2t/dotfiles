---
name: comp-reviewomatic
description: Multi-language code review for local changes and GitHub PRs using nine focused perspectives. Use to review code, post inline PR comments, resolve this skill's prior comments, or scan for review-ready PRs in Go, Rust, TypeScript, JavaScript, or Python projects.
---

# Composite Review-O-Matic

Run precise, evidence-based reviews with constructive language. Apply only concerns relevant to the detected language, stack, and project conventions.

## Inputs

Accept:

- `mode`: `local`, `review`, `resolve`, or `scan`.
- `scope`: paths, a diff, a commit or range, or a local scope such as branch, staged, or unstaged changes.
- `pr-ref`: PR URL, number, or `#number`; omit to discover from the current branch.
- `--auto-comment`: post all reportable PR findings without a second selection step.
- `--confidence=N`: reporting threshold; default 80.
- Caller-provided repository context, conventions, diff-visible lines, prior findings, or authorization.

Infer mode when omitted: use `review` for an explicit PR reference and `local` otherwise. Ask only when the request is genuinely ambiguous. In delegated or chained use, accept resolved inputs and prior authorization without asking again.

For local mode without a scope, prefer branch changes against `main` (or `origin/main`). If that is unavailable or empty, inspect staged and unstaged changes. Report a clean scope instead of guessing.

## Requirements and Skill Boundaries

- Review only. Do not edit source files.
- GitHub comment posting, replies, and thread resolution are external mutations. Require explicit user or caller authorization unless `--auto-comment` or equivalent delegated authorization is present.
- In PR modes, anchor inline findings to added or modified diff lines. Read surrounding source before judging the line.
- Resolve only threads containing `<!-- comp-reviewomatic -->`.
- Read applicable `AGENTS.md` files. Treat `CLAUDE.md` only as legacy repository guidance when present.
- Project rules override generic preferences. Enforce tools and patterns the project actually uses.
- Verify language-version support before recommending newer language features.
- Report only findings at or above the active threshold. It is valid to find none.
- Keep PR-visible language constructive, specific, and free of judgments about the author.
- When invoked by another skill, return the complete report and any mutation results to the caller.

### Bundled PR helpers

Resolve the directory containing this `SKILL.md` and use its scripts directly. Do not assume a home-directory installation path.

| Script | Purpose |
| --- | --- |
| `pr_discover.py` | Discover a PR from a reference or current branch |
| `pr_threads.py` | Fetch review threads |
| `pr_comment.py` | Post a batch of inline comments |
| `pr_reply.py` | Reply to a thread; supports `--body-file` |
| `pr_resolve.py` | Resolve a thread |
| `pr_scan.py` | Find review-ready PRs |

All helpers require only Python 3 and emit JSON:

```bash
python3 "<skill-dir>/pr_discover.py" [PR_REF]
python3 "<skill-dir>/pr_threads.py" PR_NUMBER --unresolved-only --mine-only --include-outdated
python3 "<skill-dir>/pr_comment.py" PR_NUMBER --comments-file /path/to/comments.json
python3 "<skill-dir>/pr_reply.py" THREAD_ID "reply"
python3 "<skill-dir>/pr_resolve.py" THREAD_ID
python3 "<skill-dir>/pr_scan.py"
```

## Core Skill Process

### 1. Gather the review scope

For local review, use the supplied scope. Common commands are:

```bash
git diff main...HEAD
git diff
git diff --cached
git diff main...HEAD -- path/to/file
```

For `review` or `resolve`:

1. Run `pr_discover.py`; save PR number, repository, branch, title, and URL.
2. Fetch the current diff with `gh pr diff PR_NUMBER`.
3. For `resolve`, fetch unresolved owned threads with `--mine-only --include-outdated`.

For `scan`:

1. Run `pr_scan.py`.
2. Keep PRs that are not drafts, have no human review, and have no failing CI checks.
3. Present PR number, title, author, files, and CI state.
4. Review candidates one at a time. Ask before each PR unless the caller explicitly authorized processing the queue.

### 2. Establish context

Read project guidance and enough surrounding and sibling code to understand local patterns. Detect languages, frameworks, runtime versions, and public interfaces.

In PR review and scan modes, build the set of diff-visible `(file, line)` positions. A finding may discuss broader impact, but its inline-comment anchor must be in that set.

### 3. Apply the reviewer perspectives

Use the following nine perspectives. Each finding must name one perspective and one concern.

1. **API Design & Schema Guardian**
   - Released API, CLI, configuration, database, CRD, and serialization compatibility.
   - Immutable field identifiers for protobuf, Avro, Thrift, and similar formats.
   - Clear domain naming, correct field placement, and consistent contracts.

2. **Architecture & Abstraction Guardian**
   - Layer violations, unnecessary coupling, and ripple-effect dependencies.
   - Indirection, wrappers, interfaces, or generics without a current payoff.
   - Paginated client-side filtering, duplicated logic likely to diverge, and out-of-scope changes.

3. **Convention & Documentation Steward**
   - Established framework, naming, import, file-placement, and documentation conventions.
   - Dead or commented-out code, stale comments, invalid examples, and missing changelog entries when required.

4. **Infrastructure Hardening Specialist**
   - Secret handling, resource cleanup, transactions, configuration/build synchronization, dependency safety, and deployment robustness.

5. **Integration & Deployment Reviewer**
   - Realistic integration topology, deploy-time configuration, payload and wire-size limits, migrations, and boundary validation.

6. **Language Specialist**
   - Idioms that improve correctness or maintainability, supported modern features, standard-library use, and error-handling conventions.
   - Do not report stylistic modernization without concrete benefit.

7. **Observability & Operability Reviewer**
   - Swallowed errors, missing diagnostics on new paths, inconsistent log levels or fields, duplicate logs, and sensitive data exposure.
   - Follow existing logging, metrics, and tracing systems.

8. **Security & Data Protection Reviewer**
   - Injection, SSRF, path traversal, unsafe deserialization, authentication and authorization gaps, privacy leaks, crypto misuse, and failure-open behavior.

9. **Systems Correctness Analyst**
   - Logic, nil/null handling, edge cases, lifecycle leaks, concurrency correctness, misleading errors, redundant conditions, and whether bug fixes address root causes.

Also check test changes for determinism and meaningful coverage. For a dedicated deep test review, chain `eng-test-reviewer`; for a dedicated documentation review, chain `doc-reviewomatic` in local mode. Do this only when requested by the caller.

### 4. Delegate when useful

If subagents are available and delegation is allowed, assign non-overlapping perspectives in parallel. Give each agent the complete scope, relevant source context, project guidance, detected stack, active threshold, and PR line constraints. Instruct each to review only, not re-delegate, and return:

- File and line.
- Perspective and concern.
- Evidence and impact.
- Concrete, language-appropriate fix.
- Confidence from 0–100.

If subagents are unavailable, execute the same perspectives directly. Never reduce review quality merely because delegation is unavailable.

### 5. Validate and consolidate

Verify every candidate against current source and project rules. Remove pre-existing, speculative, stylistic, and out-of-scope issues. Merge duplicate findings by location and cause.

Use this confidence scale:

- 90–100: certain, high-impact defect.
- 80–89: verified issue likely to matter in practice.
- 70–79: contextual issue; omit unless the caller lowered the threshold.
- Below 70: omit.

### 6. Post comments in `review` or `scan`

After showing the report, post only the findings authorized by the user or caller. If `--auto-comment` is set, post all findings at or above threshold.

Write a temporary JSON array:

```json
[{"path":"file.go","line":42,"body":"comment text"}]
```

Post the file with `pr_comment.py`. Each comment must explain why the issue matters and give a concrete fix. The helper adds `<!-- comp-reviewomatic -->`.

### 7. Resolve owned comments in `resolve`

For each unresolved owned thread:

1. Read current code and replies.
2. Classify it as `Addressed`, `Addressed differently`, `Declined with rationale`, or `Still open`.
3. Present the classification and proposed actions.
4. After authorization, resolve addressed threads; acknowledge alternate fixes or reasoned declines before resolving.
5. Leave unresolved issues open.

Never resolve a thread without the skill marker.

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
- **Reviewer:** [perspective]
- **Category:** [concern]
- **Issue:** [evidence and impact]
- **Suggestion:** [specific fix]

### Important
[same fields]

### Summary
- **Total findings:** N
- **Critical:** N
- **Important:** N
- **Perspectives applied:** [...]
```

If no finding meets the threshold, say: `No issues found above the confidence threshold.`

### Mutation reports

After posting, report the PR, count, review URL when available, and each posted file/line/category/confidence.

After resolution, report threads reviewed, resolved, replied to, left open, and any failures.

### Problems and partial results

For any failure, state:

1. The failed operation and exact error.
2. What was completed successfully.
3. Whether the review or mutation result is partial.
4. The safe next action.

If discovery fails, request a PR URL or number. If scanning returns none, report that no review-ready PRs were found. Continue past a per-thread resolution failure and list it in the final report; do not continue after a failure that makes the review scope unreliable.
