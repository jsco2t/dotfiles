---
name: feature-summarizer
description: Distills feature research and design documents into a concise "one pager" executive summary. Covers the problem, solution approach, key decisions, and implementation highlights — suitable for stakeholders, team onboarding, or quick reference.
argument-hint: "<path to feature research document>"
---

# Feature Summarizer Skill

You are producing a concise "one pager" summary of a planned feature. Your goal is to distill comprehensive research and design documents into a clear, high-level overview that anyone can read in a few minutes.

## Input

The user has provided the following context:

$ARGUMENTS

## Process

### Step 1: Locate Source Documents

Identify the feature research document:

- **If a file path is provided**: Read the research document directly
- **If a directory is provided**: Look for `*-research.md` and `*-design.md` files in that directory
- **If a Jira/Confluence URL is provided**: Search for associated research documents
- **If neither**: Ask the user for the path to the feature research document

After finding the research document, check for companion documents in the same directory:
- `<feature-name>-design.md` — architectural/design document from `/feature-design-researcher`
- `<feature-name>-tasks.md` — task plan from `/feature-task-planning`

Read all available documents. The research doc is required; design and task docs are optional but enrich the summary.

### Step 2: Extract Key Information

From the **research document**, extract:
- Feature goals and objectives
- Core requirements and acceptance criteria
- Technologies involved
- Gaps and open questions
- Recommendations

From the **design document** (if available), extract:
- Chosen architectural approach
- Key design decisions and their rationale
- Test strategy summary
- Risks and mitigations

From the **task plan** (if available), extract:
- Total estimated effort
- Number of phases and critical path duration
- Team size recommendation

### Step 3: Fetch Additional Context (if needed)

If the source documents reference Jira issues or Confluence pages, fetch current status:
- Use `mcp__plugin_atlassian_atlassian__getJiraIssue` for issue status and priority
- Use `mcp__plugin_atlassian_atlassian__search` for any recent updates or decisions

This ensures the summary reflects the latest state, not just what was captured at research time.

### Step 4: Produce the One Pager

Write the summary following the output structure below. Save it alongside the source documents with the naming pattern `<feature-name>-summary.md`.

For example, if the research doc is at `docs/research/object-store-research.md`, save the summary at `docs/research/object-store-summary.md`.

### Step 5: Present to User

After writing the document, display the full summary content directly in the conversation so the user can review it immediately without opening a file.

## Output Document Structure

The one pager should be tight and scannable. Use short paragraphs, bullet points, and tables. Avoid repeating detail that lives in the research or design docs — link to them instead.

```markdown
# [Feature Name] — Summary

**Date:** [Date]
**Status:** [Research | Design Complete | Planning Complete | In Progress]
**Source:** [Relative path to research doc] | [Relative path to design doc]
**Jira:** [Issue key(s) if available]

---

## Problem

[2-3 sentences. What problem does this feature solve? Why does it matter? Who benefits?]

## Solution

[3-5 sentences. How do we plan to solve it? Describe the approach at a level a technical manager or adjacent team member would understand. No implementation details — just the shape of the solution.]

## Key Decisions

| Decision | Chosen Approach | Why |
|----------|----------------|-----|
| [Decision 1] | [What we chose] | [One-line rationale] |
| [Decision 2] | [What we chose] | [One-line rationale] |
| [Decision 3] | [What we chose] | [One-line rationale] |

*Detailed trade-off analysis is in the [design document](relative-path).*

## What Changes

[Bulleted list of the major areas of the codebase or system that are affected. Keep it high-level — package/service level, not individual files.]

- **[Area 1]** — [What changes and why]
- **[Area 2]** — [What changes and why]
- **[Area 3]** — [What changes and why]

## Test Approach

[2-3 sentences summarizing how we'll verify correctness. Mention unit vs. integration focus, any special infrastructure needed, and the general coverage philosophy.]

## Risks & Open Items

| Item | Type | Impact |
|------|------|--------|
| [Item 1] | Risk / Open Question | [Brief description] |
| [Item 2] | Risk / Open Question | [Brief description] |

## Effort Estimate

[If a task plan exists, summarize: total effort, critical path duration, recommended team size. If no task plan exists, state "Task planning not yet completed — see research document for scope indicators."]

---

*Full details: [Research](relative-path) | [Design](relative-path) | [Tasks](relative-path)*
```

## Important Guidelines

1. **Brevity is the point** — If the summary exceeds roughly one printed page (~500 words of body content), it's too long. Cut ruthlessly.
2. **Link, don't repeat** — Reference the detailed documents rather than restating their contents. The summary is an entry point, not a replacement.
3. **Use plain language** — Write for a technical audience that may not have context on this specific feature. Avoid jargon that isn't defined in the summary itself.
4. **Reflect current state** — If the Jira issue has moved on since research was done, note the current status. The summary should be accurate as of now.
5. **Highlight what matters** — Not every design decision needs to appear. Include only the ones that a reader would need to understand the approach. A good heuristic: if the decision would surprise someone, include it.
6. **Omit sections gracefully** — If no design document exists, omit "Key Decisions" and "Test Approach" rather than filling them with speculation. Note what documents are available at the top.
