---
name: new-drd
description: "Create a single Delivery Requirements Document for scoped work: research the problem, clarify solution boundaries, define traceable deliverables with acceptance criteria, and build a requirements-to-deliverables coverage matrix. Use for delivery requirements rather than a full product PRD."
---

# New Delivery Requirements Document

Require an output location and initial context: description, issue/page links,
local files, or free text. Ask only for missing inputs. A directory implies
`drd.md`; honor an explicitly named file. Produce one document, not a workspace.

Research supplied sources before Q&A. Use
[atlassian-toolkit](~/.agents/skills/atlassian-toolkit/SKILL.md) for Jira/Confluence
and [github-toolkit](~/.agents/skills/github-toolkit/SKILL.md) for GitHub. Read
local context and relevant source behavior; verify current technical facts with
primary documentation. Disclose inaccessible sources and establish whether their
missing content blocks drafting. Separate facts, assumptions, gaps, and choices.

Determine scope: **Product** for standalone work, **Project** for a change to an
existing system. Project scope includes existing behavior, planned changes,
preserved behavior, compatibility, and migration. Explain and clarify genuinely
ambiguous scope without re-asking settled decisions.

Ask focused, grouped questions about uncovered gaps: problem/current state,
solution shape, goals/exclusions, functional and non-functional requirements,
deliverables, acceptance, cross-deliverable done gates, constraints, dependencies,
sequencing, and risks. For Project scope include compatibility and parent-system
constraints. Exclude business justification, personas, and adoption metrics unless
the user changes the requested artifact. Summarize decisions for correction.
After three unresolved rounds, document blockers prominently rather than
continuing indefinitely or claiming readiness.

Read [references/drd-template.md](references/drd-template.md) when drafting.
Preserve the template's requirement (`FR-`, `NFR-`) and deliverable (`D-`) IDs,
sections, and coverage matrix. Omit Existing Context for Product scope.

- Every Must requirement maps to a concrete deliverable; every deliverable has
  observable acceptance criteria. Include non-functional requirements in coverage
  when they require delivered artifacts or verification gates.
- Distinguish behaviors from artifacts. Include migrations as deliverables when
  compatibility needs them. Keep operator procedures with their deliverable.
- Definition of Done contains cross-deliverable gates; do not duplicate each
  deliverable's acceptance criteria there.
- Explain the solution's shape without code or file-level implementation plans.
- State explicit non-goals, deferred scope, and artifacts not delivered.
- Unknowns belong in Open Questions, not placeholders. Flag unmapped Must
  requirements, unsupported deliverables, missing acceptance, and blocking questions.
- Use the user's language, complete sentences, and concise prose. Lead with what
  ships and the problem it closes. Use current Mountain timestamps: `-06:00` in
  MDT, `-07:00` in MST. Record choices, rationale, and alternatives in the decision log.

Present the concrete draft for review; incorporate feedback. Mark Approved only
after explicit approval, and update Last Updated. User product choices govern
scope and priorities; a conflicting research fact stays identified as such rather
than being rewritten as an established fact. Report file path and readiness gaps.

For a full product workspace use
[new-project](~/.agents/skills/new-project/SKILL.md).
