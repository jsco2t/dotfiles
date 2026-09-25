---
name: github-toolkit
description: Interact with GitHub — pull requests (diff, files, review threads, inline comments, reviews, CI checks, queue scan), issues, commits→PRs, PR creation, and GitHub Actions workflows (list, inspect runs, and trigger a workflow_dispatch) — via a stdlib-only CLI that works inside the sandbox. Use whenever a task needs GitHub PRs, issues, reviews, CI, or running/inspecting Actions workflows. Triggering a workflow requires explicit user approval.
---

# GitHub toolkit (`ghtk`)

This machine has a stdlib-only GitHub CLI on `PATH`: **`ghtk`**. It talks to `api.github.com`
directly (not the `gh` binary), so it works **inside the sandbox** — no `dangerouslyDisableSandbox`.
Compact, token-cheap output by default.

**Read the full reference only when you actually need it** —
`~/.local/bin/github-toolkit/README.md` has the complete command table, flags, and auth.
Common starting points (`<ref>` = PR URL, number, `#number`, or omit for the current branch;
`--repo owner/repo` targets any repo, or a URL carries its own):

- `ghtk pr get <ref>` — resolve a PR to number/url/branch/state/headSha
- `ghtk pr diff <ref> [--name-only]` — unified diff (or just the changed-file list)
- `ghtk pr threads <ref> --unresolved-only [--mine-only --marker '<!-- x -->']` — review threads
- `ghtk pr checks <ref> [--failing-only] [--logs]` — CI (check-runs + commit statuses)
- `ghtk pr scan [--drop-drafts --drop-human-reviewed --drop-ci-failing]` — review-ready PR queue
- `ghtk issue get <ref>` — issue/PR body and comments
- `ghtk commit prs <sha>` — PRs that introduced a commit
- `ghtk workflow list` · `ghtk workflow runs <wf>` — list Actions workflows / a workflow's recent runs
- `ghtk doctor` — diagnose token / TLS / connectivity

Writes (`pr comment`, `pr reply`, `pr resolve`, `pr create`, `workflow run`) exist too, and each
takes `--dry-run` to print the exact request without sending it. Add `--json` to any command for
machine-readable output the toolkit owns.

**Triggering a workflow requires explicit user approval.** `ghtk workflow run <wf> --ref <ref>`
fires a real `workflow_dispatch` event (a build, release, or deploy) — **never** dispatch one on
your own initiative. Always: `--dry-run` first → show the user the exact request → get their
explicit approval → only then re-run without `--dry-run`. `--ref` (branch/tag/SHA) is required;
pass inputs with `-f KEY=VALUE` (repeatable) or `--input-file`. Read-only `workflow list` /
`workflow runs` need no approval.

Every group/command supports `--help`. Auth is automatic if `gh` is logged in; otherwise
`ghtk auth login` (or set `GITHUB_TOKEN`).
