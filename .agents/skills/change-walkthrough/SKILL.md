---
name: change-walkthrough
description: Explain a code change interactively, one logical section at a time, while tracking questions and action items. Use for PR, commit, branch, staged, uncommitted, or file-based walkthroughs where the user controls the pace.
---

# Change Walkthrough

## Inputs

Accept any of the following:

- PR number or URL
- commit or commit range
- branch name
- file paths
- `staged` or `uncommitted`
- caller-provided diff, change summary, or repository context

With no explicit scope, prefer staged changes, then the current branch against its detected base branch, then unstaged changes. If no changes exist, report that and request a scope.

## Requirements and Skill Boundaries

- Read every changed file relevant to a claim before explaining it.
- Group by functional concern, not directory layout.
- Teach the codebase-specific behavior and design; do not dwell on basic language syntax unless asked.
- Keep snippets focused, normally 10–30 lines, with file and line references.
- Present exactly one walkthrough section per turn. Stop after the roadmap and after every section until the user continues.
- Preserve action items and open questions across turns.
- When delegated, use the supplied scope and context without re-discovery, but retain the pager behavior unless the caller explicitly requests a non-interactive summary.
- Do not turn the walkthrough into a code review unless the user asks. You may identify notable risks as “things to notice,” not adjudicated findings.

## Core Skill Process

### 1. Resolve and inspect the change

Resolve explicit input first. For a PR, inspect both its description and diff. For a commit range or branch, inspect its log and diff. Detect the repository's base branch instead of assuming `main`.

Collect intent from commit messages, PR text, issue references, and nearby tests. Note additions, modifications, deletions, and renames.

### 2. Build the roadmap

Create 3–7 logical sections for a typical change. Put foundations first, then implementation, tests, and configuration or wiring. A small change may need fewer sections.

Present:

```markdown
## Change Walkthrough Roadmap

**Source:** [scope, commit/file counts]
**Overview:** [what the change accomplishes]

### Sections

1. **[Title]** — [purpose] ([N files])
2. **[Title]** — [purpose] ([N files])

Action items will be tracked as we go.

Ready to begin with Section 1?
```

Stop and wait.

### 3. Walk through one section

For each section, explain:

1. Context and purpose.
2. What changed and why.
3. Connections to earlier or later sections.
4. Important design choices, edge cases, compatibility concerns, or reusable patterns.

End with:

```markdown
**Section [N] of [Total] complete.**

- Any questions about this section?
- Anything to record as an action item?
- Ready for Section [N+1]: [Title]?
```

Answer questions in the current section, record action items with their source section, and support skip/back navigation. Stop until the user continues.

### 4. Close the walkthrough

After the final section and user questions, summarize the change, design decisions, action items, and unresolved questions.

## Output Formatting

Use this final shape:

```markdown
## Walkthrough Complete

**Reviewed:** [source]
**Coverage:** [sections and files]

### Change Overview

- [major change]

### Key Design Decisions

- [decision and rationale]

### Action Items

| # | Action item | Source section |
|---|-------------|----------------|
| 1 | [item] | [section] |

### Open Questions

- [question]
```

Omit empty optional sections, but state explicitly when no action items were recorded. If the scope cannot be resolved or a file cannot be read, identify the exact problem and its effect on the walkthrough.
