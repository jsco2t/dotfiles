---
name: composite-goreviewer
description: "Review local Go changes through nine perspectives covering API compatibility, architecture, conventions, hardening, integration, language idioms, observability, security, and correctness. Report only; use the corresponding reviewomatic skill for GitHub workflows."
---

# Composite Go Reviewer

Accept a diff, paths, commit/range, branch, staged or unstaged changes, plus optional
`--confidence=N` and `--max-agents=N`. Default to unstaged `git diff` when no scope
is supplied. State the exact scope; do not silently include other changes.
Review only: do not edit files or post comments.

Read applicable `AGENTS.md`, the diff, affected code, relevant callers and tests,
and representative siblings. Establish runtime versions and project conventions.
Read [references/review-lenses.md](references/review-lenses.md) and select the
lenses implicated by the change. Apply every selected lens fully and report which
perspectives ran, including those with no findings.

Do not demand tools or frameworks absent from the project. Recommend newer
language features only when supported and when they remove a concrete defect or
meaningful complexity. Investigate actual authorization and cleanup boundaries
instead of assuming a particular layering. Verify suspected bugs through source
or a focused, isolated check; leave the user's files untouched.

If delegation is available and permitted, assign independent passes to subagents,
grouping related concerns so they share context. Respect `--max-agents=N` (default
ceiling 6), the runtime's available slots, and any caller limit; `0` means no
delegation. Each agent reviews directly without re-delegating and returns evidence,
impact, location, fix, confidence, and the perspectives covered. Otherwise perform
the same passes yourself. Do not drop coverage to fit the agent budget.

Useful groups are security/hardening, correctness/language, API/architecture,
observability/operability, and conventions/integration. Split or combine according
to the change; the ceiling is not a target.

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

Distinguish introduced defects, pre-existing defects whose impact increases,
unchanged pre-existing issues, latent issues with a named trigger, test gaps,
weak tests, and cosmetic issues.

Related skills:
- [comp-goreviewomatic](~/.agents/skills/comp-goreviewomatic/SKILL.md)
- [test-reviewer](~/.agents/skills/test-reviewer/SKILL.md)
- [doc-reviewer](~/.agents/skills/doc-reviewer/SKILL.md)
