---
name: new-backport
description: "Create backport PRs by cherry-picking commits onto a release branch. Analyzes file-level dependencies to group commits into minimal, conflict-free PRs. Accepts multiple hashes, sorts topologically, skips already-backported commits, and suggests prerequisite commits on conflict. Use --single-pr to skip grouping. Works with any git repo using semver-style release branches."
argument-hint: "<commit-hash> [commit-hash...] [target-branch] [--single-pr]"
---

# New Backport

You are creating one or more backport pull requests. You cherry-pick commits onto a release
branch and open PRs for review. When given multiple commits, you analyze file-level dependencies
to group them into the minimum number of PRs that avoid conflicts.

## Input

The user has provided the following:

$ARGUMENTS

You need up to three inputs. Gather what's missing using AskUserQuestion.

1. **Commit hashes** — one or more commits to backport (full or short hash). These are commits on
   `main` (or another source branch) that should be cherry-picked onto the release branch. The
   last argument that looks like a branch name (matches a known remote branch) is treated as the
   target — everything else is a commit hash.
2. **Target release branch** — the release branch to backport onto (e.g., `v4.0.x`). If not
   provided, you will discover and propose one.
3. **`--single-pr` flag** (optional) — if present, skip dependency analysis and batch all commits
   into a single PR. Useful when the user knows the commits are related and wants one reviewable
   unit.

---

## Phase 1: Validate Environment

### Step 1.1: Record Current Branch

Save the user's current branch so we can return to it at the end:

```
git rev-parse --abbrev-ref HEAD
```

### Step 1.2: Check Working Tree

Run `git status --porcelain` to ensure the working tree is clean. If there are uncommitted
changes, **stop** and tell the user:

> Your working tree has uncommitted changes. Please commit or stash them before running a backport.

Do not proceed until the tree is clean.

### Step 1.3: Fetch Latest

Run `git fetch origin` to ensure we have the latest remote state.

---

## Phase 2: Resolve Inputs

### Step 2.1: Resolve and Validate All Commits

For **each** user-provided hash, resolve to the full 40-character SHA:

```
git rev-parse <hash>
```

If any hash fails to resolve (ambiguous or nonexistent), **stop** and report which hash is
invalid. Do not proceed with partial input.

Also retrieve each commit's subject line:

```
git log --oneline -1 <full-hash>
```

Display a summary table of all resolved commits before continuing so the user can confirm.

### Step 2.2: Extract Metadata from Each Commit

For each commit, extract:

1. **Issue key** — Jira-style pattern: `[A-Z]+-[0-9]+` (e.g., `FUZZ-7740`). Collect all unique
   issue keys across the batch.

2. **Original PR number** — trailing `(#NNN)` in the subject. Also try the GitHub API:

```
gh api repos/{owner}/{repo}/commits/{full-hash}/pulls --jq '.[0].number'
```

If the API fails, fall back to the regex match. Unknown PR numbers are acceptable.

3. **Clean subject** — the commit subject with any trailing ` (#NNN)` removed.

4. **Commit body** — for use in the PR description:

```
git show -s --format=%b {full-hash}
```

### Step 2.3: Discover Release Branches

List remote release branches sorted by version (descending):

```
git branch -r --list 'origin/v*' --sort=-version:refname | sed 's|  origin/||' | grep -E '^v[0-9]+\.[0-9]+\.x$'
```

If no branches match, try a broader search:

```
git branch -r --sort=-version:refname | sed 's|  origin/||' | grep -E '^(v|release[/-])[0-9]'
```

If still nothing, ask the user to specify the target branch manually.

### Step 2.4: Select Target Branch

If the user already specified a target branch, validate it exists:

```
git ls-remote --heads origin <target>
```

If not specified, present the discovered release branches using AskUserQuestion. Propose the
**most recent** release branch as the recommended option. Show up to 4 branches.

### Step 2.5: Filter Already-Backported Commits

For each resolved commit, check whether it is already on the target branch:

```
git merge-base --is-ancestor <full-hash> origin/<target>
```

If a commit is already an ancestor of the target branch, **skip it** and inform the user:

> Skipping `<short-hash>` — already present on `<target>`.

If ALL commits are already on the target, stop:

> All provided commits are already on `<target>`. Nothing to backport.

### Step 2.6: Sort Commits in Topological Order

The commits must be cherry-picked in the order they appear on their source branch (typically
`main`). To determine this order, filter `main`'s commit history to just the input hashes:

```
git log --format='%H' --topo-order --reverse origin/main | grep -Ff <(printf '%s\n' <full-hash-1> <full-hash-2> ...)
```

This outputs the commits in the order they were applied to `main`, which is the correct
cherry-pick order. Use the **full 40-character SHAs** from Step 2.1 for exact matching.

If a commit is not on `origin/main` (e.g., it's on a feature branch), fall back to sorting by
commit date:

```
git log --format='%H' --no-walk --date-order --reverse <hash1> <hash2> ...
```

---

## Phase 3: Analyze Dependencies and Group Commits

**Skip this entire phase if `--single-pr` was specified.** When skipped, treat all commits as a
single group and proceed directly to Phase 4.

When there is only **one commit** after filtering, skip this phase (there is nothing to group).

### Step 3.1: Build the File-Overlap Graph

For each commit in the topologically sorted list, get the files it touches:

```
git diff-tree --no-commit-id --name-only -r <full-hash>
```

Then compute pairwise file overlap: two commits are **connected** if they share at least one
modified file AND the earlier commit precedes the later commit in topological order.

### Step 3.2: Find Connected Components

Walk the overlap graph to find connected components. Two commits are in the same group if they
are **transitively** linked by file overlap — even if they don't directly share files.

Algorithm:
1. Start with each commit in its own group.
2. For each pair of commits that share a file, merge their groups (union-find).
3. The resulting groups are the connected components.

### Step 3.3: Order Groups and Commits Within Groups

- **Within each group**: commits are already in topological order from Step 2.6. Preserve that
  order.
- **Between groups**: order groups by the topological position of their **earliest** commit.
  Groups whose commits come first on `main` are processed first, since later groups may depend
  on changes that were on the release branch before (even if not in this batch).

### Step 3.4: Present Groups to the User

Display the proposed grouping and ask for confirmation. Format:

> **Dependency analysis found N group(s):**
>
> **PR 1** — `backport/{target}-{identifier}` (N commits)
> - `{short-hash}` {clean-subject}
> - `{short-hash}` {clean-subject}
>
> **PR 2** — `backport/{target}-{identifier}` (N commits)
> - `{short-hash}` {clean-subject}
>
> Shall I proceed with this grouping?

Use AskUserQuestion with options:
- **Proceed with grouping** (Recommended) — create separate PRs for each group
- **Single PR instead** — batch all commits into one PR (equivalent to `--single-pr`)

If the user selects "Single PR instead", merge all groups into one and proceed.

---

## Phase 4: Create Backport Branches and PRs

Process each group sequentially. For each group, perform Steps 4.1 through 4.7. After each
group completes successfully, return to the user's original branch before starting the next
group.

### Step 4.1: Determine Branch Name

Construct the branch name using this pattern:

```
backport/{target}-{identifier}
```

Where `{identifier}` is determined by:

- **Single commit, has issue key**: lowercased issue key → `backport/v4.0.x-fuzz-7740`
- **Multiple commits, all share one issue key**: that key → `backport/v4.0.x-fuzz-7450`
- **Multiple commits, mixed or no keys**: short hash of the first commit in the group →
  `backport/v4.0.x-batch-71ac0a5`
- **No issue key at all**: short hash → `backport/v4.0.x-71ac0a5`

### Step 4.2: Create the Branch

Branch from the target release branch:

```
git checkout -b {branch-name} origin/{target}
```

### Step 4.3: Cherry-Pick the Commits

Cherry-pick each commit in the group **in topological order** with the `-x` flag:

```
git cherry-pick -x <hash-1>
git cherry-pick -x <hash-2>
...
```

The `-x` flag appends `(cherry picked from commit ...)` to each commit message.

**If a cherry-pick succeeds**, move to the next commit.

**If a cherry-pick results in an empty commit** (the change is already present via a prior
cherry-pick or merge), skip it:

```
git cherry-pick --skip
```

Inform the user: `Skipping <short-hash> — change already present on branch.`

**If a cherry-pick has conflicts**, follow the procedure in Step 4.4.

### Step 4.4: Handling Conflicts

When a cherry-pick conflicts:

1. Run `git diff --name-only --diff-filter=U` to list conflicted files.

2. **Suggest prerequisite commits.** For each conflicted file, find commits on `main` between the
   target branch and the conflicting commit that touch the same file:

```
git log --oneline origin/{target}..{conflicting-hash}^ -- <conflicted-file>
```

Present these as suggestions:

> Cherry-pick of `{short-hash}` onto `{target}` has conflicts in:
> - `path/to/file1.go`
> - `path/to/file2.go`
>
> These commits on `main` also touch the conflicted files and may need to be included:
> - `abc1234` FUZZ-XXXX: Did something to file1.go
> - `def5678` FUZZ-YYYY: Refactored file2.go
>
> You can abort and retry with the additional commits:
> ```
> git cherry-pick --abort
> git checkout {original-branch}
> git branch -D {branch-name}
> /new-backport <all-hashes-including-prerequisites> {target}
> ```

3. **Also provide a manual completion recipe** for users who want to resolve conflicts themselves.
   This recipe must account for the batch state — which commits have been applied, which is
   mid-conflict, and which remain:

> Or, to resolve manually and complete the backport:
> ```
> # 1. Resolve conflicts in your editor, then:
> git add .
> git cherry-pick --continue
>
> # 2. Apply remaining commits (if any):
> git cherry-pick -x <remaining-hash-1>
> git cherry-pick -x <remaining-hash-2>
>
> # 3. Push and create the PR:
> git push -u origin {branch-name}
> gh pr create --base {target} --head {branch-name} \
>   --title "{pr-title}" \
>   --body "Backport of {commit-summary} to {target}."
>
> # 4. Return to your previous branch:
> git checkout {original-branch}
> ```

Substitute all placeholders with actual values. Include only the **remaining** commits that
haven't been cherry-picked yet. Do **not** attempt to auto-resolve conflicts.

**Stop processing the current group.** If there are remaining groups that have not been
processed, inform the user:

> **Note:** {N} additional backport group(s) were not processed due to the conflict above.
> After resolving, you can backport the remaining commits separately:
> ```
> /new-backport <remaining-group-hashes> {target}
> ```

List the commit hashes for each remaining group so the user can resume easily.

### Step 4.5: Push the Branch

```
git push -u origin {branch-name}
```

### Step 4.6: Construct PR Details

**PR Title:**

For a single commit:
```
[{target}] {clean-subject}
```

For multiple commits with a shared issue key:
```
[{target}] {ISSUE-KEY}: Backport N commits
```

For multiple commits without a shared key:
```
[{target}] Backport N commits
```

**PR Body:**

For a **single commit** — if the original PR number is known:
```
Backport of #{orig-pr-number} (`{short-hash}`). {brief-description}

Note: clean cherry-pick.
```

If the original PR number is unknown:
```
Backport of `{short-hash}` to `{target}`. {brief-description}

Note: clean cherry-pick.
```

For `{brief-description}`: use the commit body if it provides a useful summary. If the commit
body is empty, write a one-sentence summary derived from the subject. Keep it concise.

For **multiple commits**:
```
Backport of N commits to `{target}`.

## Commits
- `{short-hash-1}` {clean-subject-1} (#{pr-number-1})
- `{short-hash-2}` {clean-subject-2} (#{pr-number-2})
...

Note: clean cherry-picks, all applied without conflicts.
```

Omit the `(#NNN)` for commits where the PR number is unknown.

The `(cherry picked from commit ...)` trailer is already in each cherry-picked commit message
(added by `-x`), so do **not** duplicate it in the PR body.

### Step 4.7: Create the PR and Return to Original Branch

```
gh pr create \
  --base {target} \
  --head {branch-name} \
  --title "{pr-title}" \
  --body "{pr-body}"
```

Use a HEREDOC for the body. If `gh` is not available or fails, output the command for the user
to run manually.

After creating the PR, return to the user's original branch before starting the next group:

```
git checkout {original-branch}
```

---

## Phase 5: Final Report

After all groups have been processed, present a summary:

> **Backport complete.** Created N PR(s) targeting `{target}`:
>
> 1. PR-URL — `{branch-name}` (N commits)
> 2. PR-URL — `{branch-name}` (N commits)
> ...

If any groups failed due to conflicts, include them in the summary with their status.

---

## Error Handling

- **Invalid or ambiguous hash**: Stop, report which hash failed `rev-parse`.
- **Commit not found**: Stop, tell the user.
- **Target branch doesn't exist**: Stop, show available release branches.
- **Dirty working tree**: Stop, tell the user to commit or stash.
- **All commits already on target**: Stop, inform the user.
- **Cherry-pick conflicts**: Suggest prerequisites, provide manual recipe, report remaining
  unprocessed groups, stop.
- **Empty cherry-pick**: Skip with a message, continue to next commit.
- **`gh` CLI unavailable**: Output the PR creation command for manual execution.
- **Push fails**: Report the error, suggest the user push manually.

## Important Notes

- Always resolve short hashes to full SHAs before any filtering or comparison.
- Never force-push or use `--force` flags.
- Never modify cherry-picked commit messages beyond what `git cherry-pick -x` adds.
- Always return the user to their original branch between groups and when done.
- The release branch detection is pattern-based, not hardcoded to any specific project.
- The dependency analysis uses file-level overlap only. It may occasionally over-group (two
  commits that touch the same file in unrelated sections) but will not under-group in ways that
  cause conflicts. The worst case is "groups slightly larger than strictly necessary."
