# github toolkit (`ghtk`)

A streamlined CLI for GitHub (pull requests, issues, reviews, CI), for humans and skills.
One self-contained Python script, **stdlib-only**, on `PATH` as `ghtk`. Compact output by
default to keep token cost low. Run `ghtk <group> <command> --help` for details on any command.

**Sandbox-friendly by design.** `ghtk` talks to `api.github.com` with `urllib` (not the `gh`
CLI), so it works *inside* the Claude Code sandbox — no `dangerouslyDisableSandbox` needed.
(The old per-skill scripts shelled out to `gh`, whose Go TLS stack fails under the sandbox;
that is the "strange TLS error" this tool removes.)

## For skills (read this first)

- Only read this file / use the toolkit **when the task actually needs GitHub.** Load on demand.
- Default output is compact text. Add `--json` to parse a result. Fetch only what you need
  (`--repo`, `--limit`, `--name-only`) to save tokens.
- **`--repo owner/repo`** (alias `-R`) targets any repo and works in *any position*. Without it,
  the repo is the current git checkout's `origin` remote. A PR/issue **URL** carries its own
  owner/repo, so it needs neither `--repo` nor a checkout.
- **`<ref>`** for `pr` commands is a PR URL, a number, `#number`, or omitted (auto-discovered
  from the current git branch).
- Exit codes: `0` ok · `1` usage · `2` auth · `3` not found · `4` API error · `5` network/TLS.
- **Writes are safe to rehearse:** `pr comment`, `pr reply`, `pr resolve`, and `pr create` all
  take `--dry-run`, which prints the exact request (method, URL, JSON body) and sends nothing.
- If a command ever fails with a **network error only inside a sandbox**, re-run it with the
  sandbox disabled — but this should not happen; TLS/CA is handled automatically.

## Auth

No setup needed if `gh` is already logged in. Token precedence:
`GITHUB_TOKEN` / `GH_TOKEN` env → `gh auth token` → `~/.config/github-toolkit/auth.json`.
Sent as `Authorization: Bearer`. For a machine without `gh`:

```
ghtk auth login            # prompts for a token (hidden), or --token-stdin
ghtk auth status           # show login + token source
ghtk doctor                # TLS CA count, token, api.github.com reachability
```

A saved token goes to `~/.config/github-toolkit/auth.json` (chmod 600).

## Pull requests

`<ref>` = PR URL | number | `#number` | omitted (current branch). All accept `--repo`/`--json`.

| Command | Purpose | Example |
| --- | --- | --- |
| `ghtk pr get [ref]` | Resolve a PR to number/url/branch/state/headSha | `ghtk pr get 123` · `ghtk pr get https://github.com/o/r/pull/123` |
| `ghtk pr diff [ref]` | Unified diff; `--name-only` for the file list | `ghtk pr diff 123` · `ghtk pr diff 123 --name-only` |
| `ghtk pr files [ref]` | Changed files with add/del stats | `ghtk pr files 123 --json` |
| `ghtk pr threads [ref]` | Review threads (GraphQL) | `ghtk pr threads 123 --unresolved-only --mine-only --marker '<!-- x -->'` |
| `ghtk pr reviews [ref]` | Reviews with author + human/bot type | `ghtk pr reviews 123` |
| `ghtk pr checks [ref]` | CI: check-runs **and** commit statuses | `ghtk pr checks 123 --failing-only --logs` |
| `ghtk pr scan` | Open PR queue with composable filters | `ghtk pr scan --drop-drafts --drop-human-reviewed --drop-ci-failing` |
| `ghtk pr comment [ref]` | Post batched inline review comments (WRITE) | `ghtk pr comment 123 --comments-file c.json --marker '<!-- x -->' --dry-run` |
| `ghtk pr reply <thread-id>` | Reply to a review thread (WRITE) | `ghtk pr reply PRRT_xxx --body "thanks" --dry-run` |
| `ghtk pr resolve <thread-id>` | Resolve a review thread (WRITE) | `ghtk pr resolve PRRT_xxx --dry-run` |
| `ghtk pr create` | Create a pull request (WRITE) | `ghtk pr create --base main --head feat --title "..." --body-file b.md` |

**Threads filters:** `--unresolved-only`, `--include-outdated` (outdated threads are dropped by
default), `--mine-only --marker <M>` (threads whose comments contain the marker), `--author-substr
<S>` (threads whose *first* comment author login contains `<S>`, e.g. `copilot`). Each thread's
`id` is what `pr reply`/`pr resolve` take.

**Scan filters** (all opt-in, composable): `--drop-drafts`, `--drop-human-reviewed`,
`--drop-ci-failing`, `--file-glob '<glob>'` (repeatable; keep PRs touching a matching file),
`--all-files-match` (with `--file-glob`, keep a PR only if *every* changed file matches — e.g.
doc-only PRs), `--limit N` (default 100; `0` = unbounded). Scan cost scales with the open-PR
count: each surviving PR costs a reviews call (`--drop-human-reviewed`) and CI calls
(`--drop-ci-failing`), so a full 100-PR queue is ~2 minutes.

**`pr comment` input** is a JSON array of `{path, line, body}` (optional `side`, `start_line`,
`start_side`). The `--marker` string is prefixed to every comment body so a later
`pr threads --mine-only --marker <same>` can find and `pr resolve` them. A comment on a line
outside the diff makes the batched review 422; the tool then re-posts each comment individually
and reports which could not be placed (`dropped_locations`).

## Issues & commits

| Command | Purpose | Example |
| --- | --- | --- |
| `ghtk issue get <ref>` | Issue (or PR) body, labels, `--comments` | `ghtk issue get 42 --comments` · `ghtk issue get https://github.com/o/r/issues/42` |
| `ghtk commit prs <sha>` | PRs that introduced a commit | `ghtk commit prs a1b2c3d` |

## Diagnostics

| Command | Purpose |
| --- | --- |
| `ghtk doctor` | Python, CA certificate count, token source, api.github.com reachability |
| `ghtk doctor --fix-ca` | Drop the cached CA bundle and rebuild it |

## Common flags

- `--repo owner/repo` (`-R`) — any repo, any position. `--json` — structured output. `--dry-run`
  — on writes, print the request and send nothing. `--help` — on every group and command.
- Text inputs (`--body`) accept a literal string or `-` for stdin; `--body-file` reads a file.

## Troubleshooting

- `ghtk doctor` first. CA count `0` means an empty trust store — install `ca-certificates`
  (Debian: `apt-get install -y ca-certificates`; Rocky/RHEL: `dnf install -y ca-certificates`),
  or `pip install certifi`, or set `GITHUB_CA_BUNDLE=/path/to/ca-bundle.crt`.
- Exit `2` (auth): the token is missing/expired or lacks a scope — check `ghtk auth status`.
- Exit `4` on a write with "must be part of the diff": the comment's line isn't in the PR diff;
  `pr comment` already retries valid comments individually and reports the dropped ones.

## Maintainer notes

- **HTTP is `urllib`, not `gh`.** Deliberate: `gh` is a Go binary whose macOS system-trust TLS
  verification fails under the Seatbelt sandbox (`x509: OSStatus -26276`). `urllib` honors
  `HTTP(S)_PROXY` and uses OpenSSL's file-based verifier, so with a real CA bundle it reaches
  `api.github.com` in-sandbox. `build_ssl_context()` (ported from the atlassian-toolkit) resolves
  a CA bundle at runtime: env (`GITHUB_CA_BUNDLE`/`SSL_CERT_FILE`) → Python store → certifi →
  cached → macOS keychain export → known Linux distro bundles. Works on macOS and Linux.
- **GraphQL** (`pr threads`/`reply`/`resolve`, and scan's human-review filter) returns errors
  *inside* HTTP 200; `graphql()` checks the `errors[]` array before unwrapping `data`.
- **`pr checks` queries two endpoints** — `/commits/{sha}/check-runs` *and* the legacy
  `/commits/{sha}/status` — and merges them. Querying only check-runs makes status-only CI look
  green, which would make scan's `--drop-ci-failing` pass everything.
- **`pr checks --logs`** fetches `/actions/jobs/{id}/logs`, which 302-redirects to signed blob
  storage. urllib would forward the `Authorization` header to the blob host (→ 401), so the tool
  follows that one redirect manually *without* auth. The CA context is attached to the opener
  (build_opener's default HTTPS handler would otherwise use the empty system store).
- **Pagination** follows REST `Link: rel="next"` and GraphQL cursors; `pr threads` marks
  `commentsTruncated` / `pr files` marks `truncated` rather than silently dropping data.
- Transient `IncompleteRead`/`RemoteDisconnected` on large responses are retried.
- **`--repo`/`-R` is stripped from argv before argparse** so it works in any position without
  colliding with a trailing optional PR `<ref>` positional.
- **Maintenance rule:** any change to a command, flag, or output shape must update this README and
  `~/.claude/skills/github-toolkit/SKILL.md`, both kept lean for token efficiency.
