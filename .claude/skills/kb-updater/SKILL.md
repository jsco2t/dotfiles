---
name: kb-updater
description: "Validate and refresh an existing knowledge base against current source, repair stale claims, maintain index.md navigation, repair documents that follow older naming conventions, and propose clearly needed coverage additions. Use for KB upkeep rather than initial authoring."
---

# Knowledge Base Updater

Accept a KB path, optional source path, and `--max-agents=N`. If source is omitted,
use the current repository root; otherwise ask for the source. State resolved
paths. An empty or one-document KB needs initial authoring: use the related
knowledge-discovery or kb workflow according to the requested outcome.

The kb-utilities toolkit ships in the dotfiles repository at `.local/bin/kb-utilities/`,
with the entrypoint symlink `.local/bin/kbutil`. Invoke `kbutil` directly when
`.local/bin` is on the PATH, otherwise `python3 <dotfiles-repo>/.local/bin/kbutil`.
Its subcommands route to sibling scripts in `.local/bin/kb-utilities/`
(`.local/bin/kb-utilities/kbutil:50-55`).

## Investigate

1. Date the KB with `git -C <kb> log -1 --format=%cI -- .`, or the most recent
   Markdown modification time. This date bounds gap discovery only.
2. Inventory documents, directory depth, indexes, links, and source references.
   Identify flat versus indexed structure and preserve established conventions.
3. Validate every existing document against current source regardless of document
   age. Check paths, symbols, keys, commands, examples, and behavioral claims.
   Record failed claims with the document, evidence, current truth, and confidence.
4. For code claims, follow actual entry points and call chains; a matching symbol
   name is insufficient proof of behavior. Use
   [code-sleuth](../code-sleuth/SKILL.md) for substantial tracing.
5. Review source changes since the KB date for new behavior, APIs, configuration,
   or cohesive subsystems without coverage. Include current uncommitted changes;
   when source history or timestamps cannot bound the window, disclose that and
   inspect relevant current source. Exclude the KB itself when inside the source
   repository. Filter generated/vendor noise, pure renames, and refactors with no
   reader-visible change. Small changes with no new surface are usually not gaps,
   but size alone must not hide a meaningful behavior change.

If delegation is available and permitted, assign independent passes to subagents,
grouping related concerns so they share context. Respect `--max-agents=N` (default
ceiling 6), the runtime's available slots, and any caller limit; `0` means no
delegation. Each agent reviews directly without re-delegating and returns evidence,
impact, location, fix, confidence, and the perspectives covered. Otherwise perform
the same passes yourself. Do not drop coverage to fit the agent budget.

## Conventions repair pass

An old-convention document is a Markdown file that carries any of the older
`<8-char ID>_<snake_case>.md` habits: an ID filename prefix, a filename stem that
does not match its title, a title that is not normalized, or a missing or invalid
`id` frontmatter field (`.local/bin/kb-utilities/migrate_kb.py:6-21`). Repair these
before editing content, so later renames do not invalidate your work.

Every document must carry a valid `id` frontmatter field: an 8-character
lowercase Crockford Base32 value, written as the first frontmatter field
(`.local/bin/kb-utilities/kb_common.py`). The repair tools keep an existing valid
id as-is and mint a new one with the recovered notebook generator when the field
is missing or invalid.

1. Survey without writing anything: `kbutil check <kb-directory>` reports every
   non-conforming document and the reason (`.local/bin/kb-utilities/kbutil:207-209`).
2. Dry run first: `kbutil fix <kb-directory>` prints the rename and title-fix plan
   as a table and writes nothing, including no mapping file — the default run is a
   dry run and the script has no `--dry-run` flag (`.local/bin/kb-utilities/migrate_kb.py:22-36`).
3. Review the plan, then apply after review:
   `kbutil fix <kb-directory> --apply --mapping-out <renames.json>`. The fix renames
   each file to the normalized form of its title (lowercase kebab-case, at most 42
   characters, no ID prefix), rewrites the title to its normalized form, mints an
   `id` when the field is missing or invalid (an existing valid id is kept),
   preserves every other field, the tags, and the body, and
   never overwrites a target (`.local/bin/kb-utilities/migrate_kb.py:15-38`).
4. Rewrite wikilinks so renames do not strand links: from the KB root (the tool
   scans the current working directory), run
   `kbutil links --mapping-file <renames.json>`; add `--dry-run` to preview
   (`.local/bin/kb-utilities/fix_wiki_links.py:9-18`). The mapping is the JSON
   array of `{"old", "new"}` basename pairs that `fix --mapping-out` wrote.
5. For documents whose filename or title still does not follow the naming rules
   but which `fix` did not plan, run `kbutil names <file-or-directory> --dry-run`
   first and apply after review: re-run the command without `--dry-run` to apply.
   To apply and emit the `{"old", "new"}` rename mapping for `kbutil links` in one
   step, run `kbutil names <file-or-directory> --json` — without `--dry-run` this
   applies the fixes and prints the mapping, it does not preview
   (`.local/bin/kb-utilities/fix_kb_ids.py:25-36`).

Report what the repair pass renamed or fixed and what the user approved before it
ran. Never run a repair over documents the user has not approved fixing.

## Refresh git provenance

The git frontmatter fields `source_commit`, `last_validated`, and `git_repo`
describe the specific repository a document references, never the repository the
knowledge base lives in; every tool that derives them requires that repository
explicitly and fails without it (`.local/bin/kb-utilities/kbutil:22-28`).

For each document whose subject repository has changed, refresh its provenance
against the referenced repository:

```bash
kbutil validate <document> --repo <referenced-repository-path-or-url> \
    [--last-validated YYYY-MM-DD]
```

This rewrites the git fields the referenced repository provides: `source_commit`
becomes the full sha of its HEAD, `last_validated` becomes the given date or
today, and `git_repo` becomes the credential-free HTTPS URL of its first
normalizing remote; everything else in the document is preserved
(`.local/bin/kb-utilities/kbutil:199-205`, `.local/bin/kb-utilities/git_fields.py:167-190`,
`.local/bin/kb-utilities/git_fields.py:235-249`). A referenced remote URL rather
than a local clone yields only `last_validated` and `git_repo`, because no local
clone exists to resolve a commit from (`.local/bin/kb-utilities/kbutil:60-84`).
Preview the derived fields for a
repository before writing them with `kbutil git-fields <repo>`
(`.local/bin/kb-utilities/kbutil:193-197`). When a document references a repository
but the correct validation date is unclear, ask rather than guessing.

## Prepare and apply changes

Prepare a numbered proposal grouped into factual corrections, navigation changes,
and new documents. Show corrected claims or reviewable draft text, target paths,
and supporting evidence. A gap proposal names the topic, source area, rationale,
and existing documents it complements. If the user's request already authorizes
the action, apply within that scope; otherwise obtain selection after preparing
the concrete drafts. Broad new topics or structural changes need settled scope.

Reverify relevant source before applying targeted edits. Preserve custom prose.
For each new document, investigate the subsystem first, read the source, then
write concise teaching prose; create new documents with the kb skill's `kbutil new`
and `kbutil clean` workflow. Reference stable symbols such as
`path/file.go::FunctionName`; avoid unsupported conjecture and fragile line-only
references. Record unresolved claims explicitly rather than silently endorsing them.

## Navigation

Where `index.md` navigation is the chosen convention, each directory index has a
title and short scope description, a `../index.md` parent link except at the root,
and document/subdirectory links with one-line descriptions. The root names the
KB subject and source of truth. Omit empty sections. Update lists and cross-links
when files move or are added, preserving established metadata and naming rules.

Verify relative links and report documents checked, corrections applied, indexes
updated, new documents, the gap window, and any deferred or unverified claims.

Related skills:
- [knowledge-discovery](../knowledge-discovery/SKILL.md)
- [kb](../kb/SKILL.md)
