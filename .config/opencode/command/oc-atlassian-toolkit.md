---
description: >-
  Interact with Jira or Confluence on ciqinc.atlassian.net — search/read/create/edit issues, JQL,
  comments, transitions, change history, worklogs (log/list time), projects, users, and Confluence
  pages. Use /oc-atlassian-toolkit when the task needs Jira tickets or Confluence content.
---

# Atlassian toolkit (Jira + Confluence CLI)

Do the following task using the Atlassian toolkit CLI. The task:

$ARGUMENTS

If `$ARGUMENTS` is empty, ask what the user wants to do with Jira or Confluence before running
anything.

## The tool

This machine has a stdlib-only CLI on `PATH`, three aliases for one tool:
`jira`, `confluence`, `atlassian`. Compact, token-cheap output by default.

**Read the full reference only when you actually need it** —
`~/.local/bin/atlassian-toolkit/README.md` has the complete command table,
flags, and auth. Common starting points:

- `jira me` — authenticated identity (+ accountId)
- `jira search '<JQL>' --limit 20` — search issues
- `jira issue get <KEY> --description --comments` — one issue
- `jira issue comment <KEY> "<text>"` — add a comment (`--id <id>` edits an existing one; `jira issue comment-delete <KEY> <id>` removes it)
- `jira issue history <KEY> --field status` — change history, oldest first (omit `--field` for every field)
- `jira issue worklog <KEY> "2h" [--started <ISO time>]` — log time, default now (`jira issue worklogs <KEY>` lists the newest entries)
- `confluence page <id|url>` — fetch a page (`--full` for the whole body)
- `atlassian search "<text>"` — Jira + Confluence together
- `atlassian doctor` — diagnose auth/TLS/connectivity

For machine-readable output, add `--json` — a sanitized, schema-controlled shape the toolkit
owns (`{"schema":1,"issues":[…]}` for `search`; add `--comments` for comment history). `--raw`
returns the unfiltered Jira API response. Schema details are in the README.

Every group/command supports `--help`. One-time auth: `atlassian auth login`.

## Rules

- Prefer a single `jira`/`confluence`/`atlassian` Bash call per lookup; add `--json` when the
  result will be parsed or reused.
- Writes (comments, edits, transitions, worklogs) change real tickets: show what you are about to
  write and get the user's confirmation first, unless the task text already explicitly approves it.
- If auth or connectivity fails, run `atlassian doctor` and report the result answer-first.

## Writing descriptions, comments, and page bodies: plain text or raw ADF — never wiki markup

`--description`, comment text, and Confluence `--body` are wrapped into ADF **paragraphs only**.
The CLI parses **neither markdown nor Jira wiki markup**: `h2. Heading`, `{{mono}}`, `*bold*`,
`- bullets` are stored and displayed literally.

- Flat text: pass plain text; blank lines separate paragraphs, single newlines become hard breaks.
- Rich formatting (headings, bullets, inline code, links, bold): build an ADF document and pass it
  via `--field description="$(cat desc.json)"` on `issue create`/`issue edit` (JSON-decoded;
  overrides `--description`), or via `--adf` on `issue comment`, `issue worklog --comment`, and
  `confluence create/update/comment` (the body/stdin is then the ADF JSON document verbatim).
  Shapes: `heading` (with `attrs.level`), `paragraph`, `bulletList`→`listItem`→`paragraph`,
  `hardBreak`, and text nodes with `"marks": [{"type": "code"}]` (also `strong`, `{"type":"link","attrs":{"href":...}}`).
- Verify rich writes with `jira issue get <KEY> --raw --fields description`: it must show a `doc`
  with `heading`/`bulletList` nodes and no literal `h2.` or `{{` inside text nodes. Markup strings
  in text nodes mean the write was malformed — rewrite it.
- Reference issue formatted this way: [KUB-378](https://ciqinc.atlassian.net/browse/KUB-378).
