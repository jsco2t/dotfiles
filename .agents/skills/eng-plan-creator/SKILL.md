---
name: eng-plan-creator
description: Research a feature and create a high-level engineering specification and implementation plan from a feature description, Jira or Confluence sources, and codebase evidence. Use for feature research, gap analysis, code impact assessment, technology primers, and the planning stage before detailed design or task decomposition. Supports direct requests and delegated/chained workflows.
---

# Engineering Plan Creator

Create a concise, source-grounded engineering specification that explains the feature, its technical context, codebase impact, gaps, risks, and recommended implementation direction.

## Inputs

Accept any combination of:

- Feature description.
- Jira issue URLs or keys.
- Confluence URLs.
- Existing research, requirements, or project-index paths.
- Output path or output directory.
- Decisions, constraints, and context supplied by a caller.

When invoked by another skill or agent, treat caller-provided paths, decisions, and constraints as authoritative. Do not repeat questions the caller has already answered. If the output path is not explicit, follow the caller's directory convention or place the document at `docs/research/<feature-name>-research.md`. Ask only when no safe location can be inferred.

## Requirements and Skill Boundaries

- Research and plan; do not implement the feature.
- Treat Jira and Confluence as specification sources when available, but report conflicts rather than silently choosing between them.
- Ground codebase claims in concrete files, symbols, tests, or configuration.
- Cite external sources and local code locations close to the claims they support.
- Use current primary documentation for important technologies. Prefer official documentation and available documentation connectors; browse only when needed.
- Preserve uncertainty. Distinguish facts, reasonable inferences, assumptions, and unresolved questions.
- Keep primers focused on concepts needed for this feature; do not produce generic tutorials.
- Follow repository guidance in `AGENTS.md`. Treat `CLAUDE.md` as legacy repository guidance only when present and relevant.
- If required sources or connectors are unavailable, continue with the supplied documents and codebase where possible, then disclose the reduced confidence.
- A delegated invocation must return a structured completion or blocker status to its caller.

## Core Skill Process

### 1. Resolve scope and sources

Identify the feature, output location, and all supplied sources. Recognize Jira URLs/keys, Confluence pages, plain-text requirements, local files, and project indexes. Read linked local documents fully before researching further.

### 2. Gather specification evidence

When Atlassian sources are available, use the available Atlassian connector to retrieve:

- Jira descriptions, acceptance criteria, comments, linked issues, subtasks, epics, and remote links.
- Confluence page content, relevant descendants, linked requirements, decisions, and designs.
- Related issues or pages needed to resolve terminology and historical decisions.

Record source titles/keys and links for later citation. Do not claim direct verification when a source could not be fetched.

### 3. Analyze the codebase

Use direct repository searches and file inspection to establish:

- Current architecture and conventions.
- Similar implementations and reusable patterns.
- Likely files, packages, functions, APIs, schemas, and configuration affected.
- Integration points, dependencies, migration concerns, and test surfaces.
- Existing repository guidance and relevant build/test commands.

Verify paths and symbols against the current checkout. Do not copy stale file lists from planning documents without checking them.

### 4. Research critical technologies

For unfamiliar or version-sensitive technologies, consult current primary documentation. Capture only:

- The concepts required to understand the proposed change.
- Relevant features, constraints, and compatibility concerns.
- Direct links to authoritative references.

### 5. Synthesize the plan

Map requirements to the current system, identify gaps, and recommend a high-level implementation approach. Include delivery dependencies, risk areas, assumptions, and concrete next steps. The plan should be detailed enough for `$eng-design-creator` and `$eng-task-planning` (or an equivalent invocation mechanism) to consume without redoing basic research.

### 6. Validate before writing

Confirm that:

- Every stated requirement and acceptance criterion has a source.
- Proposed code changes refer to real paths or are clearly marked as new.
- Conflicts, missing information, and assumptions are visible.
- The recommendations address the identified gaps and risks.

Write the document to the resolved path. Preserve unrelated existing content if updating a document.

## Output Formatting

Create a Markdown document using this structure:

```markdown
# Engineering Specification: [Feature Name]

**Research Date:** [Date]
**Source Issues:** [Jira issues or None]
**Source Documents:** [Confluence/local documents or None]

---

## Executive Summary

[Purpose, key findings, and implementation roadmap in 2-3 paragraphs]

## 1. Feature Overview

### 1.1 Goals and Objectives

[What the feature must accomplish]

### 1.2 User Stories / Requirements

[Sourced requirements]

### 1.3 Acceptance Criteria

[Specific definition of done]

### 1.4 Delivery Requirements

[Milestones, dependencies, compatibility, and rollout constraints]

## 2. Technical Context

### 2.1 Technologies Involved

[Relevant technologies, frameworks, and protocols]

### 2.2 Architecture Considerations

[How the feature fits the current architecture]

### 2.3 Integration Points

[Systems, APIs, and services involved]

## 3. Technology Primers

### 3.1 [Technology Name]

**What it is:** [Brief description]

**Key Concepts:**

- [Concept]

**Relevant Features:**

- [Feature and why it matters]

**Resources:**

- [Official documentation]

## 4. Codebase Impact Analysis

### 4.1 Files Requiring Modification

| File Path | Change Type | Description |
| --- | --- | --- |
| `path/to/file.go` | Modify | [Change] |

### 4.2 Functions/Components Affected

- `package.Function()` - [Impact]

### 4.3 Database/Schema Changes

[Changes or Not applicable]

### 4.4 API Changes

[Changes or Not applicable]

### 4.5 Testing Considerations

[Required test levels and critical behaviors]

## 5. Gaps and Open Questions

### 5.1 Missing Information

| # | Gap | Impact | Suggested Resolution |
| --- | --- | --- | --- |
| 1 | [Missing information] | [Impact] | [Owner or source] |

### 5.2 Open Questions

1. **[Question]**
   - Context: [Why it matters]
   - Suggested owner: [Likely owner]

### 5.3 Assumptions Made

- [Assumption and validation needed]

## 6. Recommendations

### 6.1 Implementation Approach

[Recommended high-level approach]

### 6.2 Risk Areas

[Risks and mitigations]

### 6.3 Suggested Next Steps

1. [Next step]

## Appendix

### A. Raw Notes

[Useful supporting notes only]

### B. Related Links

[All referenced URLs]
```

Report completion with:

- `Status`: `complete`, `partial`, or `blocked`.
- `Output`: written document path.
- `Sources`: Jira issues, Confluence pages, local documents, and primary references used.
- `Key findings`: brief summary.
- `Open questions`: unresolved decisions.
- `Problems`: unavailable sources, conflicts, invalid paths, or other limitations; use `None` when empty.
- `Next skill`: usually `$eng-design-creator` when the plan is ready.

For a blocking problem, do not fabricate missing information. State the exact blocker, evidence gathered, work completed, and the minimum input or access needed to continue. In delegated use, return this status to the caller rather than starting an unrelated workflow.
