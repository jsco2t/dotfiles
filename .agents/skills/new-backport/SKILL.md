---
name: new-backport
description: "Create backport PRs by cherry-picking one or more commits onto a release branch, preserving provenance, grouping related changes, checking prerequisites, and reporting conflicts. Supports --single-pr and explicit target branches."
---

# New Backport

Accept commit hashes, an optional target release branch, and `--single-pr`.
Resolve missing commits or target before dependent work. A request to create
backport PRs authorizes preparing branches, pushing them, and opening PRs within
the requested scope; a planning-only request does not.

## Establish inputs

Record the original branch or detached HEAD and inspect working-tree/index state.
Prefer isolated worktrees so unrelated user changes need not be stashed or moved.
If isolation is unavailable, a dirty tree blocks checkout/cherry-pick; explain
the concrete obstacle. Fetch the chosen remote and resolve all inputs with
`git rev-parse --verify '<hash>^{commit}'`; stop on an invalid/ambiguous input.
Detect the repository's actual source branch rather than hardcoding `main`.
Merge commits require an explicitly justified mainline; do not guess `-m`.

Read subjects/bodies, issue keys, and original PR references. Use
[github-toolkit](~/.agents/skills/github-toolkit/SKILL.md) for commit-to-PR lookup.
Unknown original PR numbers are acceptable. Discover semver-style branches such
as `v4.0.x` or `release/...`, validate a supplied target, or ask the user to choose.
Do not select a release branch merely because it sorts newest.

Skip commits already ancestral to the target. Also check patch equivalence for
prior cherry-picks, verifying individual matches instead of assuming every
different SHA is new. If all changes are present, stop with that result.
Sort input commits by ancestry/topology on the actual source history. For unrelated
histories, establish a valid order from dependency evidence; dates alone do not
prove an order.

## Group and prepare

Unless `--single-pr` or one commit remains, group transitively overlapping files
as an initial heuristic. Inspect semantic dependencies across files/packages and
combine groups that need each other. File-disjoint commits can still depend on
each other; overlap does not guarantee correctness or conflict freedom.
Present the intended grouping and clarify only a material unresolved choice.

For each group, create a fresh branch/worktree from the target. Use
`backport/<target>-<issue-key-or-first-short-sha>` (with a batch identifier for
mixed commits); validate the ref and avoid overwriting existing branches.
Apply commits in the established order with `git cherry-pick -x`. Preserve
messages except for the provenance trailer. Skip an empty cherry-pick only after
confirming its change is already present.

Run relevant repository checks and inspect the full resulting diff against the
target. Do not publish an unverified or unexpectedly expanded backport silently.

## Conflicts

Do not auto-resolve conflicts. Report the current commit, conflicted paths,
applied and remaining commits, worktree/branch, and later groups not processed.
Inspect intervening history on those paths for possible prerequisites; present
them as candidates rather than automatically adding them to scope.
Supply a concrete manual recipe using only the conflicted paths with `git add`,
`git cherry-pick --continue`, remaining `-x` picks, checks, push, and PR creation.
Also explain how to abort. Do not delete a branch or discard conflict work.
Stop processing further groups until the conflict is resolved.

## Publish and report

Prepare title/body before publication, using the repository's PR template.
Titles name the target and resulting behavior; the body explains the changes,
original commits/PR links, deviations, and actual validation. Claim clean picks
only when true. Use a file or structured argument for multiline bodies.
Push the new branch without force and create a PR with the target as base and
backport branch as head via the GitHub toolkit. If publication fails, retain
prepared work and report the exact state and resumable next step.

Leave the original checkout intact with worktrees; if you switched it, restore
the original branch/HEAD when no operation is in progress. Report PR links,
branches, target, included/skipped commits, checks, conflicts, and unpublished work.
