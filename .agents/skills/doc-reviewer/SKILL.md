---
name: doc-reviewer
description: "Review documents or a documentation set for factual accuracy, clarity, completeness, consistency, logical splits, and missing companion coverage. Verify claims against source and report evidence-based findings without editing; use doc-reviewomatic for GitHub review workflows."
---

# Documentation Reviewer

Accept a file, directory, or documentation changeset/branch. Ask for missing scope.
For a file, focus findings on that file while reading peers for context. For a
directory, review each document and the set. For a diff, distinguish introduced
and pre-existing problems. Do not change documents.

Read applicable `AGENTS.md`, scoped documents and relevant peers, then the source
that establishes their claims. Check code, configurations, command help, process
definitions, and authoritative documentation rather than relying on fluent prose.
Use current primary sources for technical facts that need external verification.
Disclose inaccessible sources without claiming the text is wrong merely because
it could not be verified.

Review these dimensions:

- Truth and accuracy: behavior, paths, symbols, examples, commands, versions, configuration, links.
- Clarity: ambiguity, unexplained terminology, unstated assumptions, and missing reasoning steps.
- Usability: headings, reading order, prerequisites, critical guidance, and appropriate tables or diagrams.
- Completeness: necessary examples, limitations, failure handling, and prerequisite coverage.
- Information architecture: meaningful seams, duplicated material, audience or purpose mismatches.
- Set coverage: overview/index, discoverable reading order, missing companion documents.
- Consistency: terminology, claims, formatting, and established house style.

Recommend splits only when reader needs justify them, naming the resulting
documents and cross-links. Avoid style-only findings without reader impact.

If delegation is available and permitted, assign independent passes to subagents,
grouping related concerns so they share context. Respect `--max-agents=N` (default
ceiling 6), the runtime's available slots, and any caller limit; `0` means no
delegation. Each agent reviews directly without re-delegating and returns evidence,
impact, location, fix, confidence, and the perspectives covered. Otherwise perform
the same passes yourself. Do not drop coverage to fit the agent budget.

Report only findings with confidence at least 80, unless the caller supplies a
different threshold. A clean review is valid. Deduplicate overlapping findings.
Keep severity separate from confidence: severity measures impact, confidence
measures evidential certainty. Order by severity, then confidence.

Start with the scope and material limitations. For each finding use:

```text
### N. <concrete consequence>
Severity: <Critical | Important> | Confidence: <0-100> | State: <precise state>
Location: <file:line or section>

Issue: <what goes wrong, for whom, and the evidence>
Fix: <specific correction or decision>
Reviewers: <perspective(s)>
```

For whole-file reviews, omit diff provenance. Do not equate a suspected issue
with a verified defect. End with the report;
explain, save, re-run, or fix only as requested.

Use states `Wrong — this change`, `Wrong — pre-existing`, `Missing`, `Unclear`,
`Structure`, or `Cosmetic`; use `Wrong` without provenance for whole documents.
Anchor each issue to its document section or line and cite the source that proves
it. Include useful replacement prose. Report set-level missing documents with
their purpose; do not duplicate them as both findings and a gap list.

Related skill:
- [doc-reviewomatic](~/.agents/skills/doc-reviewomatic/SKILL.md)
