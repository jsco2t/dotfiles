---
name: github-toolkit
description: "Use the local ghtk CLI for GitHub pull requests, diffs, review threads, comments, issues, commits, CI checks, queue scans, PR creation, and Actions workflow inspection or authorized dispatch."
---

# GitHub Toolkit

Use the installed stdlib CLI explicitly:
`python3 "$HOME/.local/bin/github-toolkit/ghtk" <command>`.
Below, `ghtk` means that command. Check availability and runtime permissions;
the CLI does not bypass network or filesystem restrictions. Read
`~/.local/bin/github-toolkit/README.md` only when command details are needed.
Every group supports `--help`; `ghtk doctor` diagnoses auth/TLS/connectivity.
Authentication uses the existing GitHub login or `GITHUB_TOKEN`; never expose it.

`<ref>` may be a URL, number, `#number`, or omitted for the current branch.
Use `--repo owner/repo` when needed. Add `--json` for machine-readable output.

```bash
ghtk pr get <ref>
ghtk pr diff <ref> --name-only
ghtk pr threads <ref> --unresolved-only
ghtk pr checks <ref> --failing-only --logs
ghtk pr scan --drop-drafts --drop-human-reviewed --drop-ci-failing
ghtk issue get <ref>
ghtk commit prs <sha>
ghtk workflow list
ghtk workflow runs <workflow>
```

Posting, replying, resolving, creating PRs, and workflow dispatch are writes;
perform only actions authorized by the user or an explicitly invoked workflow.
Use `--dry-run` to inspect requests where supported, and files for multiline
bodies or structured comment payloads. Verify supported flags with help.

Workflow dispatch requires explicit authorization covering the workflow, ref,
and inputs. Prepare `ghtk workflow run <workflow> --ref <ref> --dry-run` with
`-f KEY=VALUE` or `--input-file`; show the exact request before requesting any
missing approval. Existing explicit authorization need not be requested again.
Dispatch only after authorization; inspect the resulting run and report its link.
