---
name: comp-goreviewomatic
description: Go-focused code review using nine specialized perspectives. Use to review local Go changes or GitHub PRs, post inline review comments, resolve this skill's prior comments, or scan for review-ready PRs; includes Go API, protobuf, concurrency, testing, security, architecture, and operability checks.
---

# Composite Go Review-O-Matic

Run precise, evidence-based Go reviews. Apply project conventions and the Go version declared in `go.mod`; do not confuse stylistic preference with correctness.

## Inputs

Accept:

- `mode`: `local`, `review`, `resolve`, or `scan`.
- `scope`: paths, a diff, commit or range, or branch/staged/unstaged changes.
- `pr-ref`: PR URL, number, or `#number`; omit to discover from the current branch.
- `--auto-comment`: post every finding at or above threshold without another selection step.
- `--confidence=N`: reporting threshold; default 80.
- Caller-provided diffs, project context, diff-visible lines, prior findings, or authorization.

Infer `review` from an explicit PR reference and `local` otherwise. Ask only if the request remains ambiguous. In delegated use, trust the caller's resolved scope and authorization.

For local mode without a scope, prefer `git diff main...HEAD` or `origin/main...HEAD`; then inspect staged and unstaged changes. Report a clean scope rather than inventing one.

## Requirements and Skill Boundaries

- Review only; never edit source.
- Posting, replying, and resolving on GitHub are mutations. Require explicit authorization unless `--auto-comment` or delegated authorization already grants it.
- Anchor PR inline findings to added or modified diff lines, while reading surrounding code for context.
- Resolve only threads containing `<!-- comp-goreviewomatic -->`.
- Read applicable `AGENTS.md`; treat `CLAUDE.md` only as legacy repository guidance.
- Enforce the project's actual conventions and supported Go version.
- Report only findings at or above the active confidence threshold. A clean review is valid.
- Keep PR comments respectful, specific, and educational.
- Return the full result to a delegating skill or agent.

### GitHub access (load on demand)

Uses the local GitHub toolkit (`ghtk`, stdlib-only, works in-sandbox — no sandbox bypass needed). Full reference: `~/.local/bin/github-toolkit/README.md` (read only when needed). **Below, `ghtk` is shorthand for `python3 "$HOME/.local/bin/github-toolkit/ghtk"`** — invoke it by that explicit path. Add `--json` for machine-readable output.

```bash
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr get [PR_REF]
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr threads PR_NUMBER --unresolved-only --mine-only --marker '<!-- comp-goreviewomatic -->' --include-outdated
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr comment PR_NUMBER --comments-file /path/to/comments.json --marker '<!-- comp-goreviewomatic -->'
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr reply THREAD_ID --body "reply"
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr resolve THREAD_ID
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr scan --drop-drafts --drop-human-reviewed --drop-ci-failing
```

## Core Skill Process

### 1. Gather scope

For local review, use the supplied scope. Common commands:

```bash
git diff main...HEAD
git diff
git diff --cached
git diff main...HEAD -- path/to/file.go
```

For `review` or `resolve`, discover the PR (`ghtk pr get`), record its metadata, and fetch `ghtk pr diff PR_NUMBER`. In resolve mode also fetch owned unresolved threads with `ghtk pr threads PR_NUMBER --unresolved-only --mine-only --marker '<!-- comp-goreviewomatic -->' --include-outdated`.

For `scan`, run `ghtk pr scan --drop-drafts --drop-human-reviewed --drop-ci-failing`. Keep non-draft PRs with no human review and no failing CI checks. Present each candidate and changed file list, then review one at a time. Ask before each PR unless the caller authorized the queue.

### 2. Establish Go context

Read repository guidance, `go.mod`, surrounding implementations, interfaces, generated-code boundaries, tests, and deployment configuration relevant to the change. For PR modes, collect all diff-visible `(file, line)` positions for inline anchors.

### 3. Apply nine perspectives

1. **API Design & Schema Guardian**
   - Never renumber released protobuf fields or reuse reserved identifiers.
   - Check additive compatibility for APIs, CLI flags, configuration, CRDs, and persisted enums.
   - Check field placement, naming semantics, read APIs with side effects, and validation at trust boundaries.

2. **Architecture & Abstraction Guardian**
   - Find cross-layer dependencies, package cycles, unnecessary coupling, and ripple-effect changes.
   - Flag interfaces, wrappers, factories, or indirection that provide no testability, substitution, or maintenance benefit.
   - Check pagination/filter placement and duplicated logic likely to diverge.

3. **Convention & Documentation Steward**
   - Enforce established file, import, naming, generated-code, and framework patterns.
   - Remove dead or commented-out code and stale comments.
   - Verify documentation examples, Hugo/Go templates, disclaimers, step order, and copy-paste usability.

4. **Infrastructure Hardening Specialist**
   - Check credentials, TLS, transactions, cleanup on every return path, dependency/build changes, capacity assumptions, and deploy-time configuration.

5. **Integration & Deployment Reviewer**
   - Check realistic integration topology, migrations, resource limits, byte/rune and wire-format math, configuration placement, and integration-test setup.

6. **Language Specialist**
   - Check error propagation and `errors.Is`/`errors.As`, nil/map/type-assertion handling, goroutine lifecycle, `context` use, cleanup, standard-library helpers, and generics.
   - Recommend features such as `log/slog`, `cmp`, `slices`, `maps`, range-over-function, or `iter` only when `go.mod` supports them and they provide concrete value.
   - Do not recommend `sync.Map` by default; verify that its workload fits the documented use cases better than a typed map plus mutex.

7. **Observability & Operability Reviewer**
   - Find discarded errors, unreachable or duplicate logging, missing diagnostics on new paths, inconsistent structured fields, and sensitive data in logs.

8. **Security & Data Protection Reviewer**
   - Check injection, SSRF, path traversal, authentication and authorization, secret exposure, privacy boundaries, cryptographic randomness, TLS validation, and failure-open behavior.

9. **Systems Correctness Analyst**
   - Verify bugs, boundary conditions, concurrency and lock coverage, resource leaks, misleading errors, redundant checks, and fixes that address root causes.
   - Confirm gomock and variadic behavior from generated interfaces or compilation rather than assumption.

Review tests for meaningful coverage and determinism. When a dedicated test review is requested, chain `eng-test-reviewer`. When a dedicated documentation review is requested, chain `doc-reviewomatic` in local mode.

### 4. Delegate when useful

If subagents are available and delegation is allowed, assign non-overlapping perspectives in parallel. Supply the full scope, relevant source, project guidance, Go version, confidence threshold, and PR line constraints. Tell each agent to review only, not re-delegate, and return file/line, perspective, concern, evidence, impact, fix, and confidence.

If delegation is unavailable, run the same review directly. Do not omit a perspective solely because no subagent is available.

### 5. Validate and consolidate

Verify candidates against current source, tests, generated artifacts, and project rules. Remove pre-existing, speculative, stylistic, and irrelevant issues. Merge duplicates.

Confidence:

- 90–100: certain, high-impact defect.
- 80–89: verified issue likely to matter.
- 70–79: include only if the caller lowered the threshold.
- Below 70: omit.

### 6. Post authorized comments

In `review` or `scan`, show the report first. Post only selected findings unless `--auto-comment` is active. Write:

```json
[{"path":"file.go","line":42,"body":"comment text"}]
```

Run `ghtk pr comment PR_NUMBER --comments-file <file> --marker '<!-- comp-goreviewomatic -->'`. Explain why each issue matters and give a concrete Go-appropriate fix. The `--marker` value `<!-- comp-goreviewomatic -->` is prefixed to every comment body.

### 7. Resolve owned comments

For each owned unresolved thread, read current code and replies. Classify it as `Addressed`, `Addressed differently`, `Declined with rationale`, or `Still open`. Present proposed actions before mutation unless already authorized. Resolve addressed threads; acknowledge alternate fixes or reasoned declines before resolving; leave open issues unresolved.

## Output Formatting

### Review report

```markdown
# Go Code Review Report

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

If no finding meets the threshold, say so directly.

For posted comments, report PR, count, review URL when available, and file/line/category/confidence. For resolved comments, report reviewed, replied, resolved, left open, and failed counts.

For failures, state the failed operation and error, completed work, whether the result is partial, and the safe next action. Request a PR reference if discovery fails; report an empty scan plainly; continue past individual thread failures but list each one.
