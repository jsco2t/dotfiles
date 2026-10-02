---
name: knowledge-discovery
description: "Analyze an existing Markdown corpus for topic clusters, emerging branches, valuable isolates, and coverage gaps; propose useful additions, research selected topics, review drafts, and save grounded documents."
---

# Knowledge Discovery

Accept a document directory and optional `--max-agents=N`. Ask for a missing
directory; offer plausible nonhidden document folders when helpful.

Run the bundled stdlib analyzer:

```bash
python3 ~/.agents/skills/knowledge-discovery/analyze_corpus.py <directory>
```

It emits JSON containing clusters, new topic branches, high-value isolates,
cluster gaps, and tag frequency. These are metadata heuristics, not factual
conclusions. Read representative documents and candidate neighbors before
claiming a gap; an empty corpus is not enough to infer useful topics.

Summarize the corpus, then propose a manageable numbered list grouped by cluster,
new branch, or isolate. Each item names a title, rationale, destination, and
related existing documents. Focus on the next useful explanation, prerequisite,
practical guide, troubleshooting topic, or bridge. Do not manufacture a quota.
Wait for topic selection unless the user has already specified the topics or
authorized the selection. Continue only the selected research and writing.

Research from current authoritative sources, verify technical syntax and version
constraints, and cite sources in the document. For codebase topics, trace source
behavior. Prepare concise, complete drafts that define unfamiliar terms and
include runnable examples where useful.

If delegation is available and permitted, assign independent passes to subagents,
grouping related concerns so they share context. Respect `--max-agents=N` (default
ceiling 6), the runtime's available slots, and any caller limit; `0` means no
delegation. Each agent reviews directly without re-delegating and returns evidence,
impact, location, fix, confidence, and the perspectives covered. Otherwise perform
the same passes yourself. Do not drop coverage to fit the agent budget.

Review each draft with [doc-reviewer](~/.agents/skills/doc-reviewer/SKILL.md),
then address verified findings and check factual grounding, clarity, and beginner
accessibility. Save into the agreed corpus using its existing naming, frontmatter,
tagging, and index conventions.

For a Git repository named `notebook`, consult
[kb](~/.agents/skills/kb/SKILL.md) for metadata and run its bundled helpers at
`~/.agents/skills/kb/scripts/fix_kb_ids.py` and
`~/.agents/skills/kb/scripts/doc_fix.py` against each newly created file only.
Use `--no-rename` for `projects/` outputs when that is their naming convention.
Follow notebook's fixed `-07:00` timestamp convention there; elsewhere use the
target's metadata rules and local timezone. Do not require notebook tools for
unrelated repositories. Repair links after renames and update cross-links/indexes.

Report analysis highlights, selected topics, final document paths/IDs, validation,
connections, and any researched topic withheld for insufficient evidence.
