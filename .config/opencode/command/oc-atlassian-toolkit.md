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
