---
name: kb
description: Create one or more standalone Markdown knowledge-base articles from supplied material or prior conversation and write them to an explicitly supplied output location. Use when the user asks to capture a topic as KB entries; applies the kb-utilities naming, title, frontmatter, and git-provenance conventions through the kbutil toolkit.
---

# Knowledge Base Articles

Turn source material into durable reference documentation rather than a transcript or chat summary. Preserve useful technical detail while making each article independently understandable and easy to retrieve later.

## Require both inputs

The invocation has this structure:

```text
<output location> <kb topic>
```

Both values are mandatory.

- The output location is the directory or Markdown file where the article should be created. Resolve relative locations from the directory where the skill was invoked.
- The topic may be pasted content, notes, a named subject, or a clear reference to something discussed earlier in the conversation.

If either value is missing, ask the user for the missing value and wait before creating anything. Do not default the output location to the current directory, and do not invent a topic from unrelated context. When a reference such as "this" could identify more than one prior subject, ask which subject the user means.

Treat a location ending in `.md` as a requested single output file. Otherwise treat it as a directory, creating it when necessary. If a topic should clearly become multiple articles but the user supplied a file path, keep it as one coherent article or ask for a directory; never create unrequested sibling files beside an explicit file.

## Use the available source material

When the topic refers to the current conversation, incorporate the relevant conclusions, examples, corrections, and code traces already established. For example, after an `explain-this` session, turn the resulting code understanding into a stable reference without requiring the user to paste the discussion again.

Inspect referenced local material when needed to make the article accurate. Complete partial ideas when the missing connection is supported by the available evidence. Do not fabricate commands, behavior, or rationale; call out a genuine uncertainty or ask a focused question when it would materially affect correctness.

## Decide article boundaries

Use judgment to produce one or more articles. Give each article one primary retrieval intent: the question or task for which someone would search later.

Split the material when it contains independently useful concepts, unrelated procedures, distinct systems, or sections likely to evolve separately. Keep it together when the sections form one workflow, rely heavily on the same setup, or would become repetitive and fragmentary if separated. Prefer a small number of substantial entries over many thin ones.

For every article:

- choose a specific, descriptive title;
- open with the purpose and the situation in which the information is useful;
- organize the content with clear headings and concise, actionable prose;
- preserve important prerequisites, commands, examples, expected results, caveats, and failure modes;
- use fenced code blocks with accurate language identifiers;
- include a table of contents only when the article is long enough to benefit from one;
- retain useful source links or provenance when they are available.

Avoid chat artifacts, repeated conclusions, generic filler, and unexplained references to "above" or "earlier." A reader should not need the original conversation to use the article.

## Naming and title rules

A document is named after its title; no ID prefix is ever minted.

- **Filename stem.** The stem is the title normalized: lowercased, apostrophes dropped entirely, every other non-alphanumeric character turned into a space, whitespace collapsed and trimmed, then spaces replaced with dashes and the stem truncated to at most 42 characters at a dash boundary (`.local/bin/kb-utilities/kb_common.py:39`, `.local/bin/kb-utilities/kb_common.py:46-89`). A name collision appends a numeric suffix such as `-2`, sized so the whole stem stays within the cap (`.local/bin/kb-utilities/kb_common.py:74-89`).
- **Frontmatter title.** The title is the normalized text with spaces kept: lowercase, no special characters, no length cap (`.local/bin/kb-utilities/new_doc.py:84-87`). It matches the filename stem with dashes as spaces only when the title was short enough that the stem was never truncated; a truncated stem is shorter than the title (`.local/bin/kb-utilities/kb_common.py:92-94`).

Do not hand-derive these forms when a tool derives them for you; the authoring workflow below does.

## Author articles with kbutil

The kb-utilities toolkit ships in the dotfiles repository at `.local/bin/kb-utilities/`, with the entrypoint symlink `.local/bin/kbutil` (`.local/bin/kb-utilities/kbutil:1-31`). Invoke `kbutil` directly when `.local/bin` is on the PATH, otherwise `python3 <dotfiles-repo>/.local/bin/kbutil`. Always pass explicit file and directory arguments; never point a toolkit command at a directory you did not create when only one document was requested.

### Article about a git repository

A git-related article is one whose subject is a specific git repository, local or remote. Create it with `kbutil new`, which requires the referenced repository explicitly (`--repo`; `.local/bin/kb-utilities/kbutil:165-175`):

```bash
kbutil new "<Article Title>" --dir <output-directory> --tags <comma-separated-tags> \
    --repo <repository-path-or-url> [--commit <sha>] [--last-validated YYYY-MM-DD]
```

The command creates `<output-directory>/<normalized-stem>.md` with `createdate`, `title`, and `tags` frontmatter (`.local/bin/kb-utilities/new_doc.py:67-100`) and derives the git provenance fields the referenced repository can provide (`.local/bin/kb-utilities/git_fields.py:167-190`):

- `source_commit` — the full 40-hex sha the article is based on: HEAD of the referenced repository, or `--commit` resolved to its full sha (`.local/bin/kb-utilities/git_fields.py:123-138`).
- `last_validated` — the `YYYY-MM-DD` date the article was validated against the repository; `--last-validated` when given, otherwise today (`.local/bin/kb-utilities/git_fields.py:141-153`).
- `git_repo` — the referenced repository's HTTPS URL, with any `user:token@` or `token@` userinfo stripped, so credentials never reach the document (`.local/bin/kb-utilities/git_fields.py:69-104`).

These fields describe the repository the article references, never the notebook or knowledge base the article lives in. They are derived only from the repository you name with `--repo`; a local path means the fields come from that repository's clone, and a remote URL that is not a local path is recorded as the credential-free HTTPS `git_repo` with no `source_commit` (`.local/bin/kb-utilities/kbutil:22-28`). If the topic names no repository, the article is not git-related: use the plain workflow below.

### Article not about a git repository

`kbutil new` always requires a referenced repository, so create the file yourself and let the toolkit add the frontmatter:

1. Write the article body to `<output-directory>/<normalized-stem>.md`, applying the naming rules above by hand.
2. Run the cleanup tool on that file only:

   ```bash
   kbutil clean <absolute-path-to-the-new-file>
   ```

   This adds id-free frontmatter (`createdate` with a `-07:00` offset, `title` derived from the filename stem, a tags block) to a document without one, and normalizes and suggests tags in a document that already has frontmatter (`.local/bin/kb-utilities/doc_fix.py:164-180`, `.local/bin/kb-utilities/doc_fix.py:388-410`). Tags stay within a ten-tag maximum (`.local/bin/kb-utilities/doc_fix.py:331`).

## Verify what the tools produced

After the tools finish, verify each new document rather than trusting command output alone:

- the filename stem follows the naming rules, with no ID prefix;
- the frontmatter title is the normalized, lowercase, space-separated title without a length cap; it matches the stem with dashes as spaces only when the stem was never truncated;
- `createdate`, `title`, and `tags` are present and valid;
- git-related articles carry the git fields their referenced repository provides
  (`source_commit`, `last_validated`, `git_repo`), and `git_repo` shows no
  userinfo or credential;
- the Markdown body is complete and any inter-article links use the final filenames or stems.

A rename or creation never overwrites an existing file; a collision receives a numeric suffix (`.local/bin/kb-utilities/new_doc.py:49-64`). If a suffix appeared, confirm it preserves the user's intent.

## Report the result

List every final article path and title. For git-related articles, include the referenced repository and the `source_commit` recorded. When the topic was split, briefly state the boundary used so the user can judge whether the grouping is useful. Do not commit or push the new documents unless the user separately requests it.
