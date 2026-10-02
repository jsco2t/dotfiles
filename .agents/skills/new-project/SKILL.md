---
name: new-project
description: "Create a product/project documentation workspace with a researched collaborative PRD, traceable product-level user scenarios, useful supplementary research, and a knowledge-base seed. Leaves features/ for later engineering planning; use update-project for revisions."
---

# New Project

Require an output directory and initial product context. Accept supplied name,
slug, repository context, prior research, and settled decisions. Ask only for
missing or consequentially ambiguous inputs. For an existing project with a PRD,
use [update-project](~/.agents/skills/update-project/SKILL.md) rather than
overwriting its workspace. Work at the product level: what, who, why, scope,
and success; leave code and file-level design to engineering planning.

## Initialize and research

Create `index.md`, `prd.md`, and child folders `documents/`, `features/`, `kb/`,
and `verifications/`, each with `index.md`. Derive a stable project slug.
Read [references/templates.md](references/templates.md) for index and artifact
formats. Leave `features/` empty apart from its index; it is reserved for
[new-eng-feature](~/.agents/skills/new-eng-feature/SKILL.md).

Read supplied files and linked requirements. Use
[atlassian-toolkit](~/.agents/skills/atlassian-toolkit/SKILL.md) for Jira/Confluence
and [github-toolkit](~/.agents/skills/github-toolkit/SKILL.md) for GitHub.
Research current technologies, standards, markets, or competitors when relevant.
For existing systems, inspect capabilities, gaps, constraints, and user behavior.
Separate verified facts, assumptions, missing information, and decisions.
Disclose inaccessible sources; ask for missing content if it blocks requirements.

## Clarify and draft

Ask related questions in manageable batches about actual gaps: problem,
motivation, users, goals/non-goals, measurable success, functional and non-functional
requirements, constraints, dependencies, prior art, risks, and unresolved choices.
State what research established and why the remaining decision matters. Summarize
captured decisions after each round. After three unresolved rounds, document
remaining unknowns rather than inventing answers.

Write `prd.md` using the template's section structure and stable requirement IDs.
Requirements are specific and testable. Preserve user terminology, boundaries,
priorities, and decision rationale. Use substantive researched content, not
placeholders; put unknowns in Open Questions. Use ISO 8601 timestamps with the
current Mountain offset (`-06:00` MDT, `-07:00` MST).

Present the completed draft for user review and incorporate corrections before
final scenarios, unless the caller already supplied approved requirements or
explicitly authorized a settled noninteractive draft. Status remains Draft until
the user approves it; record approval and Last Updated when it occurs.

## Complete the workspace

- Derive user scenarios from workflows and functional requirements, covering
  happy paths, critical failures, and stated boundaries. Each scenario has a
  stable `US-` ID, persona, requirement references, matching priority,
  preconditions, user actions, observable outcomes, and checkable acceptance.
- Write scenarios under `verifications/` by workflow or user type. Use user
  behavior rather than shell commands, API requests, or developer test fixtures.
- Maintain a requirement-to-scenario coverage matrix. Every Must functional
  requirement has at least one scenario; flag uncovered lower priorities.
- Add supplementary research to `documents/` only when it supports specific PRD
  decisions and needs more space than the PRD. Seed focused `kb/` articles only
  for reusable domain concepts, technology primers, or institutional context.
  Cite authoritative sources and link back to relevant PRD sections.
- Update every affected index, root summary counts/status, and next steps.
  Keep child-to-parent links and root-to-child links valid. Verify every artifact
  is discoverable and all internal links resolve. Do not create filler documents.

Report final paths, Must requirement coverage, scenarios, useful seed documents,
approval status, and open blockers. Suggest engineering planning only when the
product requirements are sufficiently settled.
