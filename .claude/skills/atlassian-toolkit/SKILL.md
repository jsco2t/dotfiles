---
name: atlassian-toolkit
description: Interact with Jira or Confluence on ciqinc.atlassian.net — search/read/create/edit issues, JQL, comments, transitions, change history, worklogs (log/list time), projects, users, and Confluence pages. Use whenever a task needs Jira tickets or Confluence content.
---

# Atlassian toolkit (Jira + Confluence CLI)

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

## Writing descriptions and comments: plain text or raw ADF — never wiki markup

The CLI wraps `--description` and comment text into ADF **paragraphs only** (`text_to_adf` in
`~/.local/bin/atlassian-toolkit/atlassian`). It parses **neither markdown nor Jira wiki markup**:
text written as `h2. Heading`, `{{mono}}`, `*bold*`, or `- bullets` is stored and displayed
literally, markup and all. Confluence page bodies (`--body`) are wrapped the same way.

- **Flat text is fine**: pass plain text via `--description -`; blank lines become paragraph
  breaks, single newlines become hard breaks. Write section labels and bullets as plain lines.
- **Rich formatting on comments and Confluence bodies**: those writes now accept `--adf` —
  the body/stdin is a raw ADF JSON document passed verbatim:

  ```bash
  jira issue comment KUB-123 "$(cat body.json)" --adf
  jira issue comment KUB-123 "edited text" --id 229518 --adf   # same flag when editing
  confluence create --space ENG --title "Design" --body - --adf
  confluence update 123 --body "$(cat page.json)" --adf
  confluence comment 123 "$(cat body.json)" --adf
  ```
- **Rich formatting (headings, bullet lists, inline code, links, bold) requires a real ADF
  document**. Descriptions: pass it via `--field`, which JSON-decodes its value and overrides
  `--description`; comments and Confluence bodies: pass it via `--adf` (above):

  ```bash
  python3 - <<'PY' > /tmp/desc.json
  import json
  doc = {"type": "doc", "version": 1, "content": [
      {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Overview"}]},
      {"type": "paragraph", "content": [
          {"type": "text", "text": "uses "},
          {"type": "text", "text": "actions/checkout@v7", "marks": [{"type": "code"}]}]},
      {"type": "bulletList", "content": [
          {"type": "listItem", "content": [{"type": "paragraph", "content": [
              {"type": "text", "text": ".github/workflows/backport.yaml:41",
               "marks": [{"type": "code"}]}]}]}]},
  ]}
  print(json.dumps(doc))
  PY
  jira issue create --project KUB --type Bug --parent KUB-364 --summary "..." \
    --field description="$(cat /tmp/desc.json)"
  jira issue edit KUB-123 --field description="$(cat /tmp/desc.json)"   # same for edits
  ```

  Node shapes: `heading` (`attrs.level`), `paragraph`, `bulletList`→`listItem`→`paragraph`,
  `hardBreak` for a line break inside a paragraph; text nodes take
  `"marks": [{"type": "code"|"strong"|{"type":"link","attrs":{"href":...}}}]`.
- **Verify rich writes against the raw field** — round-tripping through
  `jira issue get --description` flattens ADF to text (`## Overview`, backticks), which is
  normal; the proof is in the stored nodes:

  ```bash
  jira issue get KUB-123 --raw --fields description
  ```

  That must show a `doc` with `heading`/`bulletList` nodes and no literal `h2.` or `{{` inside
  any text node. If you see markup strings in text nodes, the write was malformed — rewrite it.

Example of a correctly formatted issue: [KUB-378](https://ciqinc.atlassian.net/browse/KUB-378).
