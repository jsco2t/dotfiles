---
description: Use the local Atlassian CLI for Jira issues and links, parent hierarchy, and Confluence page reads and edits on ciqinc.atlassian.net.
---

Perform this task using the toolkit: $ARGUMENTS
If no task was supplied, ask what the user wants to do before running commands.

# Atlassian Toolkit

Use `jira`, `confluence`, and `atlassian` for Jira/Confluence activity on
ciqinc.atlassian.net. They are aliases for one stdlib CLI. Check availability;
if needed invoke `python3 "$HOME/.local/bin/atlassian-toolkit/atlassian" <group> ...`.
Load `~/.local/bin/atlassian-toolkit/README.md` only for the operation needed.
Every command supports `--help`; `atlassian doctor` diagnoses auth/connectivity.
Never print credentials. Write only within the user's authorized scope.

Common reads:

```bash
jira search '<JQL>' --limit 20
jira issue get <KEY> --description --comments
confluence page <id-or-url> --full
atlassian search '<text>'
```

Use `--json` for structured output. Jira reads with `--raw` return API data;
`confluence page <id-or-url> --raw [--body-format storage]` includes the body and
version needed for editing. The default page view flattens and truncates content.

## Update the page itself

Use `confluence update`, rather than a comment, when asked to edit page content.
Read the full page first. `--body`/`--body-file` **replace the entire body**;
retain unrelated content, macros, and formatting in the replacement file.

```bash
confluence page <id-or-url> --raw --body-format storage
confluence update <id-or-url> --body-file page.xml --storage --version <current-version>
```

`--storage` sends Confluence storage XHTML; `--adf` sends a real ADF JSON document.
They are mutually exclusive. Plain text (neither flag) becomes ADF paragraphs;
Markdown and Jira wiki markup are not parsed. `--body -` reads stdin.
`--title "New title"` alone preserves the stored body. Re-read the raw body after
saving to verify the change. On a version conflict, re-read and reconcile before
retrying. A failed write marked "may already have been applied" needs a read-back
before another attempt. Comment permission does not imply page-edit permission.

## Jira links and hierarchy

These are distinct operations; check `--help` for write flags:

- Issue relationships: `jira issue link-types` discovers names/IDs and inward/outward
  labels; `jira issue issue-links <KEY>` lists issue links with IDs and direction.
  `jira issue link <KEY> <OTHER> --type Blocks --dry-run` previews creation:
  default outward means KEY blocks OTHER; `--direction inward` reverses it.
  Drop `--dry-run` to create. To change type/direction, delete the selected link
  and create its replacement; Jira has no issue-link update endpoint.
- Delete issue links: `jira issue link-delete <KEY> <OTHER> --type Blocks --dry-run`.
  Add `--id <link-id>` if several links of that type join them. Drop `--dry-run`
  to delete. IDs must come from `issue issue-links`, not external links.
- External URLs/Confluence references: `jira issue links <KEY>` lists remote links.
  `jira issue remote-link <KEY> <URL> --title "Design"` creates one; `--id <id>`
  edits it while preserving metadata. `jira issue remote-link-delete <KEY> <id>`
  deletes one. All support `--dry-run`; deletion is permanent.
- Parent/epic hierarchy: `jira issue edit <KEY> --parent <PARENT>` or
  `--clear-parent`, subject to Jira's hierarchy rules. This is separate from links.

## Jira text writes

Descriptions use `--description -` for plain text, or
`--field description='<ADF JSON>'` for rich formatting. Comments and worklog
comments take `--adf` with body/stdin JSON. For example:
`jira issue comment <KEY> - --adf < comment.json`; add `--id <comment-id>` to edit.
Verify rich descriptions using `jira issue get <KEY> --raw --fields description`.
Report affected issue/page URLs after writes.
