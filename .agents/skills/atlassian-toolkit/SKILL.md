---
name: atlassian-toolkit
description: "Use the local Atlassian CLI to search, read, create, and update Jira issues and Confluence pages on ciqinc.atlassian.net, including comments, transitions, history, and worklogs. Load command details only when needed."
---

# Atlassian Toolkit

The local stdlib CLI has three aliases: `jira`, `confluence`, and `atlassian`.
Use the installed command when available; otherwise invoke
`python3 "$HOME/.local/bin/atlassian-toolkit/atlassian" <command>` and consult its
help for routing. Check availability rather than assuming sandbox or network access.
Read `~/.local/bin/atlassian-toolkit/README.md` only for the commands needed.
Every command supports `--help`; `atlassian doctor` diagnoses connectivity/auth.
Do not print credentials. Perform writes only within the user's authorized scope.

Common starting points:

```bash
jira me
jira search '<JQL>' --limit 20
jira issue get <KEY> --description --comments
jira issue history <KEY> --field status
jira issue worklogs <KEY>
confluence page <id-or-url> --full
atlassian search '<text>'
```

Add `--json` for the toolkit's sanitized schema; `--raw` returns API data.
Confirm flags with command help before unfamiliar writes.

## Formatting writes

Text descriptions, comments, and Confluence bodies become ADF paragraphs. The CLI
does not parse Markdown or Jira wiki markup: `h2.`, `{{mono}}`, or Markdown syntax
will display literally. Use plain text, or supply a real Atlassian Document Format
(ADF) JSON document for rich text.

- Descriptions: `--description -` reads plain text from stdin. For rich text,
  `--field description='<ADF JSON>'` JSON-decodes the value and overrides text.
- Comments and Confluence bodies: `--adf` passes raw ADF JSON. Check command help
  for stdin or file support; keep authored text in a file rather than constructing
  multiline shell arguments.
- Comment edits use `--id <comment-id>`. Worklog writes use
  `jira issue worklog <KEY> "2h" [--started <ISO-time>]`.

ADF document shape:

```json
{"type":"doc","version":1,"content":[
  {"type":"heading","attrs":{"level":2},"content":[{"type":"text","text":"Overview"}]},
  {"type":"paragraph","content":[
    {"type":"text","text":"command","marks":[{"type":"code"}]},
    {"type":"text","text":" reference","marks":[{"type":"link","attrs":{"href":"https://example.com"}}]}
  ]}
]}
```

Lists use `bulletList` → `listItem` → `paragraph`; text marks include `code`,
`strong`, and `link`. Use `hardBreak` for a line break in a paragraph.
Verify rich writes against the stored raw nodes, for example
`jira issue get <KEY> --raw --fields description`. The flattened text view is
not proof that rich formatting was preserved. Report the affected issue/page link.
