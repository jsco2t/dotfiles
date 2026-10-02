---
name: reviewomatic
description: "Route local changes or GitHub PRs to doc-reviewomatic, comp-goreviewomatic, or comp-reviewomatic based on changed file types. Supports local, review, resolve, and scan modes; delegates analysis and PR-visible actions to the selected reviewers."
---

# Reviewomatic Router

Route reviews; do not independently assess file content or post, reply to, or
resolve GitHub comments. Read only paths/types and review ownership markers.

Accept `local|review|resolve|scan`, local scope or PR reference, `--auto-comment`,
`--confidence=N`, and `--max-agents=N`. Infer review from an explicit PR reference
and local otherwise. Honor settled mode, scope, authorization, and flags. Ask only
when an ambiguity materially changes routing.

Specialized reviewers:

- [doc-reviewomatic](~/.agents/skills/doc-reviewomatic/SKILL.md)
- [comp-goreviewomatic](~/.agents/skills/comp-goreviewomatic/SKILL.md)
- [comp-reviewomatic](~/.agents/skills/comp-reviewomatic/SKILL.md)

Use [github-toolkit](~/.agents/skills/github-toolkit/SKILL.md) for PR discovery,
file census, queue scanning, and thread reads. Downstream reviewers own writes.

## Survey and select

For local scope, use the supplied paths/range/staged/unstaged choice. When absent,
prefer branch changes against the repository's default branch, then staged and
unstaged changes if that comparison is unavailable or empty. Record exact commands
and path filters and pass them downstream. Use `git diff --name-only` and optional
`--numstat`; do not read file bodies. Stop on an empty census.

For PR review, resolve and retain owner/repository/number/URL, then use
`ghtk pr diff <ref> --name-only`. Pass an unambiguous URL or repository-qualified
reference downstream; a bare number can refer to the wrong current repository.

Classify code extensions before directory heuristics so `.go` or `.py` examples
inside `docs/` are not mistaken for prose:

- **Go:** `.go`, `go.mod`, `go.sum`, `.proto`.
- **Other supported code:** `.rs`, `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs`, `.py`.
- **Docs:** `.md`, `.mdx`, `.rst`, `.txt`, `.adoc`, `.asciidoc`, and remaining
  prose content in known documentation directories.
- **Neutral:** configuration, shell, Dockerfiles, SQL, CSS/HTML, lockfiles, and
  other files. These accompany the chosen reviewer; neutral-only uses the generalist.

Go-only code → comp-goreviewomatic. Any other supported language → comp-reviewomatic
(including Go in mixed changes). Docs-only → doc-reviewomatic. Code plus docs →
doc-reviewomatic and exactly one code reviewer. Never pair the two code reviewers.
An incidental side may be folded into the dominant review when its small scope is
clear from paths/statistics; do not infer a change is merely cosmetic without evidence.
For unfamiliar file types, establish what can be reviewed and clarify if necessary.
Announce the census and route.

## Dispatch

Read each selected `SKILL.md` at its path above and follow it with the resolved
inputs (there is no assumed Skill tool or `$ARGUMENTS` interpolation). Run two
reviewers sequentially. Forward mode, full scope, PR identity, confidence, and
posting authorization verbatim. Pass any agent limit as an explicit caller
constraint even if the downstream skill does not define that flag; respect runtime
slots and `0` as no delegation. For mixed changes, give disjoint doc/code scopes
and have the code reviewer skip the docs covered by doc-reviewomatic.
Return the downstream reports and mutation results, preserving authorship and markers.

## Resolve and scan

**Resolve:** skip the file census. Read all unresolved threads including outdated
ones (`ghtk pr threads <ref> --unresolved-only --include-outdated --json`), without
`--mine-only`. Inspect comment bodies for `<!-- comp-reviewomatic -->`,
`<!-- comp-goreviewomatic -->`, and `<!-- doc-reviewomatic -->`. Dispatch resolve
to each owning reviewer; zero owned threads means no dispatch. Three markers
legitimately require all three reviewers; the two-reviewer cap applies to new
reviews only. Each downstream reviewer resolves its own marked threads.

**Scan:** use `ghtk pr scan --drop-drafts --drop-human-reviewed --drop-ci-failing`.
Present candidates; process the authorized selection one PR at a time. Census
and route each PR, then dispatch **review** with its explicit identity, never scan.
Preserve existing queue authorization rather than asking per PR again.

Report empty scopes, discovery failures, inaccessible reviewers, or downstream
empty results clearly. Do not silently drop a flag, ownership marker, or file group.
