---
name: copilot-fixer
description: Triage GitHub Copilot review threads and failing PR checks, refute non-issues, fix valid issues, verify the combined changes, and update the PR. Use for Copilot review comments, PR review-bot feedback, or CI failures on a pull request.
---

# Copilot Fixer

## Inputs

- PR URL or number; if omitted, discover the PR for the current branch.
- Optional caller-provided thread list, check results, repository context, or limits such as triage-only or no-push.

Resolve bundled scripts with:

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/copilot-fixer"
```

| Script | Purpose | Usage |
|--------|---------|-------|
| `pr_discover.py` | Resolve URL, number, or current branch | `python3 "$SKILL_DIR/pr_discover.py" [PR]` |
| `pr_threads.py` | Fetch review threads | `python3 "$SKILL_DIR/pr_threads.py" PR [--copilot-only] [--unresolved-only]` |
| `pr_reply.py` | Reply to a thread | `python3 "$SKILL_DIR/pr_reply.py" THREAD BODY` |
| `pr_resolve.py` | Resolve a thread | `python3 "$SKILL_DIR/pr_resolve.py" THREAD` |
| `pr_checks.py` | Fetch checks and logs | `python3 "$SKILL_DIR/pr_checks.py" PR [--failing-only] [--logs]` |

All scripts use Python 3 standard library and emit JSON. `pr_reply.py` also accepts `--body-file PATH`.

## Requirements and Skill Boundaries

- Confirm the PR before changing code or posting replies. Never guess.
- Work on the PR branch and verify the checked-out branch before editing.
- Read the referenced code and surrounding control flow before classifying a comment.
- Ground public replies in specific technical evidence. Keep them concise and professional.
- Batch all valid fixes and CI repairs, then run one quality pipeline over the combined diff.
- Do not resolve a valid-issue thread until its fix is pushed. A refuted non-issue may be resolved after replying.
- Respect caller limits. In triage-only mode, do not edit, reply, resolve, commit, or push.
- Treat replies, resolutions, commits, and pushes as visible external actions. Perform them only when the user's request authorizes fixing/updating the PR; otherwise present the proposed actions and request confirmation.
- When delegated, honor supplied PR metadata and decisions, avoid repeated discovery, and return machine-scannable status plus blockers to the caller.

## Core Skill Process

### 1. Resolve the PR and gather work

Run `pr_discover.py`. If resolution fails, stop and request a URL or number. Check out the PR branch when fixes are authorized.

Fetch unresolved Copilot threads and failing checks in parallel:

```bash
python3 "$SKILL_DIR/pr_threads.py" PR --copilot-only --unresolved-only
python3 "$SKILL_DIR/pr_checks.py" PR --failing-only --logs
```

If neither exists, report that the PR is clean and stop.

### 2. Triage each thread

Read the referenced code, its callers or callees when relevant, tests, and project instructions (`AGENTS.md` first; `CLAUDE.md` only when a repository still uses it).

Classify each thread:

- `VALID`: a demonstrated correctness, security, reliability, or repository-convention issue.
- `NON-ISSUE`: the concern is already handled, misunderstands context, contradicts established behavior, concerns unchanged code without PR impact, or is only preference.
- `UNCERTAIN`: evidence is incomplete or reasonable interpretations differ.

Record thread ID, location, concern, classification, evidence, and proposed action. Present the triage before taking public or code-changing action unless the caller already authorized autonomous execution.

### 3. Handle non-issues

Reply with what the code does, why the concern does not apply, and the supporting code or convention. Then resolve the thread. Continue if resolution fails, but record the permission or API error.

### 4. Fix valid issues and checks

For each valid thread, optionally acknowledge it, implement the smallest correct fix, and leave the thread open. For each failing check, use its logs to find and fix the root cause. Do not alter unrelated code.

For uncertain items, report the evidence and ask for a decision only when the ambiguity materially changes the implementation.

### 5. Verify the combined diff

1. Invoke `comp-reviewomatic` in local mode over the files changed by this run. Fix verified high-confidence issues.
2. If tests changed, invoke `eng-test-reviewer` on those tests. Fix verified high-confidence issues.
3. Run repository-native lint, build, and test commands. Prefer `AGENTS.md`, CI configuration, README/CONTRIBUTING, and build-system targets, in that order. Treat `CLAUDE.md` as legacy project guidance when present.
4. Re-run failing checks after fixes. Do not push known-broken changes.

If the verification command cannot be determined, report the missing information rather than silently skipping it.

### 6. Commit, push, and resolve

When authorized and changes exist:

- stage only files changed for this task;
- create a descriptive commit;
- push to the PR branch;
- resolve valid-issue threads only after the push succeeds.

If no code changed, do not create an empty commit. If a fix still fails verification after reasonable attempts, stop before pushing and report the blocker.

## Output Formatting

```markdown
# Copilot Fixer Report: PR #[number]

## PR

- **Title:** [title]
- **Branch:** [branch]
- **URL:** [url]

## Comment Triage

| Location | Concern | Assessment | Action |
|----------|---------|------------|--------|
| `path:line` | [summary] | VALID/NON-ISSUE/UNCERTAIN | [action] |

## CI Failures

| Check | Result | Action |
|-------|--------|--------|

## Verification

| Step | Result | Details |
|------|--------|---------|
| Code review | PASS/FAIL/SKIPPED | [details] |
| Test review | PASS/FAIL/SKIPPED | [details] |
| Lint | PASS/FAIL/SKIPPED | [command/details] |
| Build | PASS/FAIL/SKIPPED | [command/details] |
| Test | PASS/FAIL/SKIPPED | [command/details] |

## Delivery

- **Commit:** [SHA or none]
- **Pushed:** [yes/no]
- **Threads unresolved:** [count and reasons]
- **Files changed:** [paths]

## Remaining Problems

- [blocker, uncertainty, failed action, or deferred issue]
```

Never report success when a reply, resolution, push, or required check failed. Include the exact failed action, available error, impact, and next step.
