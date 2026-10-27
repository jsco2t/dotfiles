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

### GitHub access (load on demand)

Uses the local GitHub toolkit (`ghtk`, stdlib-only, works in-sandbox — no sandbox bypass needed). Full reference: `~/.local/bin/github-toolkit/README.md` (read only when needed). **Below, `ghtk` is shorthand for `python3 "$HOME/.local/bin/github-toolkit/ghtk"`** — invoke it by that explicit path (do not assume it is on `PATH`). Add `--json` to any command for machine-readable output.

```bash
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr get [PR_REF]
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr threads PR_NUMBER --unresolved-only --mine-only --marker '<!-- comp-reviewomatic -->' --include-outdated
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr comment PR_NUMBER --comments-file /path/to/comments.json --marker '<!-- comp-reviewomatic -->'
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr reply THREAD_ID --body "reply"
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr resolve THREAD_ID
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr scan --drop-drafts --drop-human-reviewed --drop-ci-failing
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

1. Run `ghtk pr get`; save PR number, repository, branch, title, and URL.
2. Fetch the current diff with `ghtk pr diff PR_NUMBER`.
3. For `resolve`, fetch unresolved owned threads with `ghtk pr threads PR_NUMBER --unresolved-only --mine-only --marker '<!-- comp-reviewomatic -->' --include-outdated`.

For `scan`:

1. Run `ghtk pr scan --drop-drafts --drop-human-reviewed --drop-ci-failing`.
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

Also check test changes for determinism and meaningful coverage. For a dedicated deep test review, chain `test-reviewer`; for a dedicated documentation review, chain `doc-reviewomatic` in local mode. Do this only when requested by the caller.

### 4. Delegate when useful

If subagents are available and delegation is allowed, fan out — but pack the perspectives and share the setup work:

1. **Write one review brief first.** In a scratch location outside the repository (or under `$TMPDIR`), save the full diff as `change.diff` and write `brief.md`: the scope and how it was gathered; the changed files; the detected stack and language versions; the project guidance (`AGENTS.md` text or its paths); the active threshold; the paths of `change.diff` and `baseline.txt` (next step); and, in PR modes, the diff-visible `(file, line)` set with the anchoring rule. Every sub-agent reads this one brief; no prompt repeats the context.
2. **Run the baseline checks once, in the background.** When the reviewed code is checked out locally, start the project's own test and vet/lint commands for the changed packages once, in the background, writing all output to `baseline.txt` and ending it with the line `== baseline done (exit <code>) ==`. Launch the reviewers without waiting for it; sub-agents read that file instead of each re-running the suite. Skip this when the code is not checked out locally.
3. **Pack the perspectives into at most 3 sub-agents — never one per perspective.** A sub-agent's cost is set by how much code it explores, not by how many lenses it applies; every extra agent re-explores the same code. Default grouping (instantiate a group only when the change selected at least one of its perspectives; never split a perspective across code areas into extra sub-agents):
   1. **Correctness & Language** — Systems Correctness Analyst + Language Specialist.
   2. **Security, Hardening & Design** — Security & Data Protection Reviewer + Infrastructure Hardening Specialist + API Design & Schema Guardian + Architecture & Abstraction Guardian.
   3. **Operability & Conventions** — Observability & Operability Reviewer + Convention & Documentation Steward + Integration & Deployment Reviewer.

   A caller-supplied agent limit replaces the 3 and packs harder; it never drops a perspective. This caps threads, not coverage: never drop a perspective, blur two into one vaguer pass, or shortchange one inside a shared thread.
4. **Give each sub-agent the brief plus its perspectives.** Prefer a dedicated read-only review sub-agent when the host defines one. Each sub-agent runs every perspective it owns as its own full pass — co-location shares context; it never blends lenses — and returns one report: a list grouped by perspective, naming every perspective it owned, including any that found nothing (`<perspective>: no issues found`). Tell each to review only, not re-delegate, and to work lean: batch independent reads and searches into one turn, read each file region once rather than re-reading, read `baseline.txt` instead of re-running the suite, and put any targeted throwaway test under `$TMPDIR`, never in the repository.
5. **Report only what consolidation can use.** With threshold N, a sub-agent writes a full finding (file and line, perspective and concern, evidence and impact, a concrete language-appropriate fix, confidence 0–100) at confidence ≥ N−10; a one-line near miss (`path:line`, confidence, one sentence) at N−20 to N−11; nothing lower.

If subagents are unavailable, execute the same perspectives directly, grouped in the same order. Never reduce review quality merely because delegation is unavailable.

### 5. Validate and consolidate

Verify every candidate against current source and project rules. Remove pre-existing, speculative, stylistic, and out-of-scope issues. Merge duplicate findings by location and cause. Near misses are context, not findings: promote one only when another perspective flagged the same issue or your own verification raises it to the threshold.

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

Post the file with `ghtk pr comment PR_NUMBER --comments-file <file> --marker '<!-- comp-reviewomatic -->'`. Each comment must explain why the issue matters and give a concrete fix. The `--marker` value `<!-- comp-reviewomatic -->` is prefixed to every comment body so this skill can later find and resolve its own threads.

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
