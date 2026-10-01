# atlassian toolkit

A streamlined CLI for Atlassian Cloud (Jira + Confluence), for humans and Claude skills.
One self-contained Python script, stdlib-only. Compact output by default to keep token
cost low. Run `<group> <command> --help` for details on any command.

Three entry points, all on `PATH` (same tool):

- `jira ...` — issues, search, projects, users
- `confluence ...` — pages, search
- `atlassian ...` — everything, plus cross-product `atlassian search`

## For skills (read this first)

- Only read this file / use the toolkit **when the task actually needs Jira or Confluence.** Load on demand.
- Default output is compact text. Add `--json` to parse a result; `--raw` returns the full
  Jira API JSON. Prefer the default; fetch only what you need (`--fields`, `--limit`) to save tokens.
- Confluence page bodies are **truncated by default**; pass `--full` when you truly need the whole page.
- Exit codes: `0` ok · `1` usage · `2` auth · `3` not found · `4` API error · `5` network/TLS.
- If a command fails with a **network error only inside a sandbox**, re-run it with the
  sandbox disabled. TLS/CA is handled automatically otherwise (no setup needed).
- A write (`worklog`, `comment`, `create`, …) that fails with "may already have been applied" is not retried
  automatically. Check first (e.g. `jira issue worklogs <KEY>`) before re-running, or it may be recorded twice.

## Auth (one-time, human)

```
atlassian auth login        # prompts for site, email, API token (input hidden)
atlassian auth status       # show current identity
```

One API token covers both Jira and Confluence. Create it at
https://id.atlassian.com/manage-profile/security/api-tokens . Saved to
`~/.config/atlassian-toolkit/auth.json` (chmod 600). Env vars override
the file: `ATLASSIAN_SITE`, `ATLASSIAN_EMAIL`, `ATLASSIAN_API_TOKEN`.

## Jira

| Command | Purpose | Example |
| --- | --- | --- |
| `jira me` | Authenticated user (+ accountId) | `jira me` |
| `jira search <JQL>` | Search issues | `jira search 'project = FUZZ AND statusCategory != Done' --limit 20` |
| `jira issue get <KEY>` | Show one issue | `jira issue get FUZZ-1234 --description --comments` |
| `jira issue create` | Create an issue | `jira issue create --project FUZZ --type Task --summary "..." --description -` |
| `jira issue edit <KEY>` | Edit fields / labels | `jira issue edit FUZZ-1234 --summary "..." --add-label triage` |
| `jira issue comment <KEY> <text>` | Add a comment, or edit one with `--id <id>` (`-` = stdin) | `jira issue comment FUZZ-1234 "Done."`  ·  `… "Fixed typo." --id 90210` |
| `jira issue comment-delete <KEY> <id>` | Delete a comment — **permanent** | `jira issue comment-delete FUZZ-1234 90210` |
| `jira issue comments <KEY>` | List comments — the newest 20 (`--limit N`), shown oldest→newest; comment ids shown here | `jira issue comments FUZZ-1234` |
| `jira issue transition <KEY> [name]` | Apply/list transitions | `jira issue transition FUZZ-1234 "In Review"` |
| `jira issue history <KEY>` | Change history, oldest first (`--field` = one field, by name or id; long values shown as sizes, `--full` for text) | `jira issue history FUZZ-1234 --field status` |
| `jira issue worklog <KEY> <time>` | Log time (Jira duration: `1d 4h`, `3h 30m`); `--started` ISO time, default now | `jira issue worklog FUZZ-1234 "1d 4h" --started 2026-09-17T09:00` |
| `jira issue worklogs <KEY>` | List logged time — the newest 50 (`--limit N`), shown oldest→newest; worklog ids shown here | `jira issue worklogs FUZZ-1234` |
| `jira issue links <KEY>` | Remote links (e.g. linked Confluence pages) | `jira issue links FUZZ-1234` |
| `jira project list` | List visible projects | `jira project list --search fuzz` |
| `jira project types <KEY>` | Issue types for a project | `jira project types FUZZ` |
| `jira user <query>` | Look up a user's accountId | `jira user "jane"` |

## Confluence

| Command | Purpose | Example |
| --- | --- | --- |
| `confluence page <id\|url>` | Fetch page content (truncated; `--full` for all) | `confluence page 12345`  ·  `confluence page https://…/wiki/…/pages/12345/Title` |
| `confluence descendants <id\|url>` | List child pages (one level) | `confluence descendants 12345` |
| `confluence search <text>` | Search content (CQL with `--cql`) | `confluence search "storage v4"`  ·  `confluence search 'type=page AND space=ENG' --cql` |
| `confluence create` | Create a page (`--body -` = stdin) | `confluence create --space ENG --title "Design" --body -` |
| `confluence update <id>` | Update a page (title and/or body) | `confluence update 12345 --title "Design v2"` |
| `confluence comment <id> <text>` | Add a footer comment (`-` = stdin) | `confluence comment 12345 "Reviewed."` |

## Cross-product & diagnostics

| Command | Purpose | Example |
| --- | --- | --- |
| `atlassian search <text>` | Search Jira issues + Confluence pages together | `atlassian search "job pagination"` |
| `atlassian doctor` | Check TLS, config, Jira + Confluence connectivity | `atlassian doctor` |

## Common flags

- `--json` — sanitized, schema-controlled output (see [JSON output schema](#json-output-schema)); `--raw` — the full, unfiltered Jira API response.
- `--comments` — include comments in `search` / `issue get` `--json` (and `--raw`) output.
- `--limit N` / `--fields a,b,c` — bound result size and fields. `issue comments` / `issue worklogs` keep the
  newest N (shown oldest→newest) and note on stderr when older entries were left out.
- `--full` — untruncated Confluence body; on `issue history`, long values (e.g. description edits) in full.
- `--help` — on every group and command.
- Text inputs (`--description`, comment body) accept a literal string or `-` to read stdin.
  Body-carrying write commands (`issue comment`, `issue worklog --comment`, `confluence
  create/update/comment`) also take `--adf`: the text/stdin is then a raw ADF JSON document
  (`{"type": "doc", "version": 1, "content": [...]}`) passed through verbatim — for headings,
  bullet lists, and code marks that plain text wrapping cannot express. Plain text (no `--adf`)
  wraps into ADF paragraphs only, and neither markdown nor Jira wiki markup is parsed, so `h2.`
  or `{{…}}` would be stored literally. On `issue create`/`issue edit`, rich descriptions can
  also go through `--field description=<ADF JSON>`.
- `--field KEY=VALUE` (repeatable, `issue create`/`edit`) sets any raw Jira field; value is
  JSON-decoded when possible (e.g. `--field 'priority={"name":"High"}'`). On `issue history`, `--field NAME`
  is a filter instead: one field, by name or id (`status`, `"Fix Version"`, `customfield_10016`).

## JSON output schema

`--json` emits a stable, sanitized shape the toolkit owns (not the raw REST payload — that's
`--raw`). `jira search --json` wraps results as `{"schema":1,"issues":[...]}`; `jira issue get
--json` returns one issue object. Per issue:

| Field | Notes |
| --- | --- |
| `key` `type` `summary` `status` `priority` | strings |
| `statusCategory` | `To Do` \| `In Progress` \| `Done` — bucket on this, not `status` |
| `assignee` | display name, or `null` |
| `updated` | `YYYY-MM-DD` |
| `parent` | `{key, type, status}`, when the issue has one |
| `comments` | `[{author, created, text}]` — only with `--comments`; ADF flattened, oldest→newest |

`issue get --json` also includes `reporter`, `labels`, and `description` (with `--description`).
`issue history --json` → `[{created, author, field, from, to}]` (values never shortened); `issue worklogs --json` →
`[{id, author, started, timeSpent, timeSpentSeconds}]` (timestamps are full Jira ISO strings).
`--comments` on `search` embeds comments from the search response, which may be a subset on
very high-comment issues; `jira issue comments <KEY> --limit N` lists the newest N (default 20), oldest→newest.

## Troubleshooting

- `atlassian doctor` reports Python, CA certificate count, saved site/email, and whether Jira
  and Confluence are reachable. Run it first when something is off.
- `atlassian doctor --fix-ca` rebuilds the CA bundle if TLS starts failing.
- Auth errors (`exit 2`): re-check `atlassian auth status`; the API token may be expired.

## Maintainer notes

- Auth is API-token Basic auth (one token, both products). The claude.ai Atlassian connector
  uses hosted OAuth a CLI cannot reuse, so this tool uses API tokens.
- Jira writes use REST v3 and wrap plain text into ADF (v3 rejects plain strings for
  description/comment). If a Jira instance rejects an ADF write, the fallback is REST v2.
- Retries: `api_request` retries 429, 5xx, and network errors for GET/PUT/DELETE, but a POST only on 429 or a
  connect/send failure — re-sending a POST whose reply was lost would duplicate the write (worklog, comment,
  issue). Read-only POSTs (JQL search) pass `idempotent=True`.
- Confluence reads use REST v2 (`body-format=atlas_doc_format`, reusing the ADF renderer;
  falling back to `storage`/XHTML for legacy pages); search uses v1 `/wiki/rest/api/search` (CQL).
- Confluence writes use REST v2: create/update `/wiki/api/v2/pages` (update fetches the current
  version and increments it; title-only edits preserve the existing body) and `/wiki/api/v2/footer-comments`;
  text is wrapped as ADF like Jira writes.
- TLS: some Python builds ship an empty CA store (notably the macOS python.org build). The tool
  resolves a CA bundle at runtime — env override → Python's own system store → certifi → cached →
  macOS keychain export / known Linux distro bundles (`/etc/ssl/certs/ca-certificates.crt` on Debian,
  `/etc/pki/tls/certs/ca-bundle.crt` on Rocky/RHEL, etc.). On a normal Debian/Rocky host Python already
  has the system store, so it just works; a stripped image without `ca-certificates` needs that package
  installed (or certifi, or `ATLASSIAN_CA_BUNDLE`) — `atlassian doctor` prints the exact fix.
- One executable (`atlassian-toolkit/atlassian`); `jira` and `confluence` are argv[0] aliases.
