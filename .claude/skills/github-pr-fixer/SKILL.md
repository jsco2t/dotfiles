---
name: github-pr-fixer
description: Triage PR review-bot comments (including GitHub Copilot threads), investigate broader PR pipeline failures such as failing CI checks, workflow failures, and merge conflicts with the base branch (rebase, careful conflict resolution, impacted-area tests, force push), refute non-issues, fix valid issues, verify the combined changes, and update the PR. Use for review-bot feedback, Copilot review comments, CI failures, or merge conflicts on a pull request.
---

# GitHub PR Fixer

Investigates any failure or feedback in a pull request's pipeline — review-bot comments, failing CI checks, workflow failures, and merge conflicts with the base branch — fixes what is real, and updates the PR. Copilot review threads are one covered input, matched by author.

## Inputs

- PR URL or number; if omitted, discover the PR for the current branch.
- Optional caller-provided thread list, check results, repository context, or limits such as triage-only, no-push, or no-rebase.

### GitHub access (load on demand)

Uses the local GitHub toolkit (`ghtk`, stdlib-only, works in-sandbox). Full reference: `~/.local/bin/github-toolkit/README.md` (read only when needed). **Below, `ghtk` is shorthand for `python3 "$HOME/.local/bin/github-toolkit/ghtk"`** — invoke it by that explicit path.

| Command | Purpose |
|---------|---------|
| `ghtk pr get [PR]` | Resolve URL, number, or current branch (JSON includes `baseRef`) |
| `ghtk pr threads PR [--author-substr copilot] [--unresolved-only]` | Fetch review threads (filter by author, e.g. Copilot's) |
| `ghtk pr reply THREAD --body "..."` (or `--body-file PATH`) | Reply to a thread |
| `ghtk pr resolve THREAD` | Resolve a thread |
| `ghtk pr checks PR [--failing-only] [--logs]` | Fetch checks and failed-job logs |

All emit JSON with `--json`.

## Requirements and Skill Boundaries

- Confirm the PR before changing code or posting replies. Never guess.
- Work on the PR branch and verify the checked-out branch before editing.
- Read the referenced code and surrounding control flow before classifying a comment.
- Ground public replies in specific technical evidence. Keep them concise and professional.
- Batch all valid fixes and CI repairs, then run one quality pipeline over the combined diff.
- Do not resolve a valid-issue thread until its fix is pushed. A refuted non-issue may be resolved after replying.
- Rebasing rewrites PR-branch history. Pushing a rebased branch is a force push: use `--force-with-lease`, never bare `--force`, and treat it as a visible external action like any push. Never force-push over remote commits the local branch does not contain.
- Respect caller limits. In triage-only mode, do not edit, reply, resolve, commit, or push.
- Treat replies, resolutions, commits, and pushes as visible external actions. Perform them only when the user's request authorizes fixing/updating the PR; otherwise present the proposed actions and request confirmation.
- When delegated, honor supplied PR metadata and decisions, avoid repeated discovery, and return machine-scannable status plus blockers to the caller.

## Core Skill Process

### 1. Resolve the PR and gather work

Run `ghtk pr get`. If resolution fails, stop and request a URL or number. Check out the PR branch (`gh pr checkout PR`, a local git operation) when fixes are authorized.

Fetch unresolved review threads and failing checks in parallel. To limit threads to one bot's comments (for example Copilot's), filter by author:

```bash
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr threads PR --author-substr copilot --unresolved-only
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr checks PR --failing-only --logs
```

Omit `--author-substr` to gather review-bot threads from all authors.

#### Detect merge conflicts

Also check for conflicts with the base branch. GitHub's mergeable state can lag behind the branches, so test locally. Let `$BASE` be the PR's base branch (`ghtk pr get PR --json`, field `baseRef`) and `$BRANCH` the PR's head branch:

```bash
git fetch origin
git merge-tree --write-tree "origin/$BASE" "origin/$BRANCH"
```

Exit code `0` means a clean merge; `1` means conflicts, with the conflicted files listed in the output. On git older than 2.38, use `git merge --no-commit --no-ff "origin/$BASE"` instead and `git merge --abort` immediately afterward. Record whether conflicts were found and which files conflict.

If there are no threads, no failing checks, and no conflicts, report that the PR is clean and stop.

### 2. Rebase onto the base branch and resolve conflicts

When step 1 found conflicts, rebase before triaging or fixing anything else: later fixes then sit on a clean base, and one push delivers everything. If there were no conflicts, skip to step 3.

Preconditions — if any fails, stop and report instead of rebasing:

- `git status --porcelain` is empty. Never rebase a dirty worktree; commit, stash, or report leftover work first.
- `git log HEAD..origin/$BRANCH` is empty. If the remote PR branch has commits the local branch lacks, someone else pushed — ask before reconciling so a later force push cannot drop their work.

Rebase and resolve one replayed commit at a time:

```bash
git rebase "origin/$BASE"
```

- Read both sides of every conflict before editing: the `$BASE` side (what landed there — `git log "origin/$BASE" -- <file>`) and the PR side (the commit being replayed). Understand why each side changed.
- During a rebase, `--ours` is the base branch and `--theirs` is the PR commit — the reverse of merge intuition. Never resolve with a blanket `--ours` or `--theirs`.
- Keep both changes when they are independent. When they genuinely collide, decide deliberately which intent supersedes, and record the decision for the report.
- If a resolution needs a design or product call, or the conflicts are too tangled to resolve faithfully, run `git rebase --abort` (restores the pre-rebase state) and report.
- After resolving one commit's conflicts: `git add <files>`, then `git -c core.editor=true rebase --continue`.

If repository convention forbids rebasing (check `AGENTS.md` / CONTRIBUTING first), merge `origin/$BASE` into the PR branch instead and resolve the same conflicts with the same care.

When the rebase completes, confirm no conflict markers survive in the changed files (`git grep -nE '^(<<<<<<<|>>>>>>>)' -- <changed files>` returns nothing). A rebase is a code change: step 6's verification must cover the conflicted files, the files the PR changed, and the modules that own them — conflicts can merge textually yet still break semantics.

### 3. Triage each item

Read the referenced code, its callers or callees when relevant, tests, and project instructions (`AGENTS.md` first; `CLAUDE.md` only when a repository still uses it).

Classify each thread or failing check:

- `VALID`: a demonstrated correctness, security, reliability, or repository-convention issue.
- `NON-ISSUE`: the concern is already handled, misunderstands context, contradicts established behavior, concerns unchanged code without PR impact, or is only preference.
- `UNCERTAIN`: evidence is incomplete or reasonable interpretations differ.

Record thread ID, location, concern, classification, evidence, and proposed action. Present the triage before taking public or code-changing action unless the caller already authorized autonomous execution.

### 4. Handle non-issues

Reply with what the code does, why the concern does not apply, and the supporting code or convention. Then resolve the thread. Continue if resolution fails, but record the permission or API error.

### 5. Fix valid issues and checks

For each valid thread, optionally acknowledge it, implement the smallest correct fix, and leave the thread open. For each failing check, use its logs to find and fix the root cause. Do not alter unrelated code.

For uncertain items, report the evidence and ask for a decision only when the ambiguity materially changes the implementation.

### 6. Verify the combined diff

1. Invoke `comp-reviewomatic` in local mode over the files changed by this run. Fix verified high-confidence issues.
2. If tests changed, invoke `test-reviewer` on those tests. Fix verified high-confidence issues.
3. Run repository-native lint, build, and test commands. Prefer `AGENTS.md`, CI configuration, README/CONTRIBUTING, and build-system targets, in that order. Treat `CLAUDE.md` as legacy project guidance when present.
4. Re-run failing checks after fixes. Do not push known-broken changes.

If the verification command cannot be determined, report the missing information rather than silently skipping it.

### 7. Commit, push, and resolve

When authorized and changes exist:

- stage only files changed for this task;
- create a descriptive commit;
- push to the PR branch: `git push --force-with-lease` when the branch was rebased this run, a normal push otherwise — never bare `--force`;
- resolve valid-issue threads only after the push succeeds.

If no code changed, do not create an empty commit — but a completed rebase counts as a change even with no new commit: it still needs the force push so GitHub re-evaluates the merge. If a fix still fails verification after reasonable attempts, stop before pushing and report the blocker.

## Output Formatting

```markdown
# GitHub PR Fixer Report: PR #[number]

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

## Merge Conflicts

- **Detected:** [yes/no — local test merge against origin/<base>]
- **Rebase:** [completed / aborted + reason / not needed]
- **Conflicted files:** [paths or none]
- **Resolution notes:** [file → what was kept and why, for genuine collisions only]
- **Force push:** [yes/no, with --force-with-lease]

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

Never report success when a reply, resolution, rebase, push, or required check failed. Include the exact failed action, available error, impact, and next step.
