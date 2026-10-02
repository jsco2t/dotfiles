---
name: kb-updater
description: "Validate and refresh an existing knowledge base against current source, repair stale claims, maintain index.md navigation, and propose clearly needed coverage additions. Use for KB upkeep rather than initial authoring."
---

# Knowledge Base Updater

Accept a KB path, optional source path, and `--max-agents=N`. If source is omitted,
use the current repository root; otherwise ask for the source. State resolved
paths. An empty or one-document KB needs initial authoring: use the related
knowledge-discovery or kb workflow according to the requested outcome.

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
   [code-sleuth](~/.agents/skills/code-sleuth/SKILL.md) for substantial tracing.
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

## Prepare and apply changes

Prepare a numbered proposal grouped into factual corrections, navigation changes,
and new documents. Show corrected claims or reviewable draft text, target paths,
and supporting evidence. A gap proposal names the topic, source area, rationale,
and existing documents it complements. If the user's request already authorizes
the action, apply within that scope; otherwise obtain selection after preparing
the concrete drafts. Broad new topics or structural changes need settled scope.

Reverify relevant source before applying targeted edits. Preserve custom prose.
For each new document, investigate the subsystem first, read the source, then
write concise teaching prose. Reference stable symbols such as
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
- [knowledge-discovery](~/.agents/skills/knowledge-discovery/SKILL.md)
- [kb](~/.agents/skills/kb/SKILL.md)
