---
name: new-project
description: "Create a new product/project with a collaborative PRD (Product Requirements Document). Sets up a structured documentation folder with PRD, user scenarios, knowledge base, supplementary documents, and a features folder for future /new-eng-feature runs. Interactively researches and questions the user to build a comprehensive product specification."
argument-hint: "<output directory> <initial context: description, URLs, file paths, or free-text>"
---

# New Project Skill

You are creating a new product/project workspace with a comprehensive Product Requirements Document (PRD). Unlike `/new-eng-feature` which produces engineering-level implementation plans, this skill operates at the **product level** — defining what to build, for whom, why, and what success looks like.

Your primary output is a PRD. Your secondary outputs are user-scenario verifications, supplementary documents, and a knowledge base seed. The `features/` folder you create is a container for future `/new-eng-feature` runs — you do NOT populate it.

**This is a collaborative process.** The user provides initial context, and you research, ask informed questions, and iterate with them until the PRD is comprehensive. Do not rubber-stamp thin context into a document — your questions and research are the value.

## Input

The user has provided the following context:

$ARGUMENTS

You need two inputs. If either is missing, use AskUserQuestion to ask:

1. **Output directory** — where to create the project documentation folder. Example: `/Users/jscott/Developer/sources/personal/notebook/projects/fuzzball/projects/my-project`
2. **Initial context** — a description of the product/project, links to existing documents (Jira, Confluence, files), or free-text explaining what needs to be built. This is the seed — you will expand it through research and Q&A.

---

## Phase 0: Initialize Folder Structure

### Step 0.1: Validate Inputs

- Confirm the output directory path. Create it if it does not exist.
- Confirm initial context was provided.
- Determine a **project slug** for use in file naming. Derive from the project name, Jira epic key if available, or ask the user to confirm if ambiguous.

### Step 0.2: Create Folder Structure

Create the following directory tree inside the output directory:

```
<output-directory>/
├── index.md
├── prd.md
├── documents/
│   └── index.md
├── features/
│   └── index.md
├── kb/
│   └── index.md
└── verifications/
    └── index.md
```

### Step 0.3: Create Initial Index Files

**Root `index.md`:**

```markdown
# [Project Name] — Project Documentation

**Project:** [Project name]
**Jira:** [Epic key(s) and links, if available]
**Created:** [ISO 8601 timestamp with MST offset, e.g., 2026-04-29T10:00:00-06:00]
**Status:** Draft

---

## Documentation Structure

| Folder                                       | Purpose                                                                       | Index                                              |
| -------------------------------------------- | ----------------------------------------------------------------------------- | -------------------------------------------------- |
| [`prd.md`](prd.md)                           | Product Requirements Document — the product specification                     | —                                                  |
| [`documents/`](documents/index.md)           | Supplementary documents, research, and reference materials                    | [documents/index.md](documents/index.md)           |
| [`features/`](features/index.md)             | Engineering feature plans created by `/new-eng-feature`                        | [features/index.md](features/index.md)             |
| [`kb/`](kb/index.md)                         | Knowledge base — domain knowledge, glossaries, and reference docs             | [kb/index.md](kb/index.md)                         |
| [`verifications/`](verifications/index.md)   | User scenarios — acceptance-level verification of product behavior            | [verifications/index.md](verifications/index.md)   |
```

**Each subfolder `index.md`** starts with a header linking to the parent:

```markdown
# [Folder Name] Index

**Parent:** [../index.md](../index.md)
**Last Updated:** [ISO 8601 timestamp with MST offset]

---

| Document | Description | Created |
| -------- | ----------- | ------- |
```

**`features/index.md`** uses a specialized format:

```markdown
# Features Index

**Parent:** [../index.md](../index.md)
**Last Updated:** [ISO 8601 timestamp with MST offset]

---

This folder contains engineering feature plans created by `/new-eng-feature` runs. Each subdirectory is a self-contained feature documentation tree with its own index.

| Feature | Slug | Jira | Status | Index |
| ------- | ---- | ---- | ------ | ----- |

_No features planned yet. Use `/new-eng-feature <feature-directory> <spec links>` to create one._
```

### Step 0.4: Inform the User

Tell the user:

- What folder structure was created
- What the project slug is
- That you are about to research their initial context and then ask questions to build out the PRD
- That this is a collaborative process — their input on requirements, scope, and priorities shapes the document

---

## Phase 1: Research the Initial Context

Before asking questions, do your homework. The user's questions should be informed, not generic.

### Step 1.1: Parse Provided Context

Identify all resources in the initial context:

- **Jira Issues**: URLs or issue keys — fetch using Atlassian MCP tools
- **Confluence Pages**: URLs — fetch using Atlassian MCP tools
- **File paths**: Read local files
- **Free-text**: Parse for product concepts, user types, goals, constraints

### Step 1.2: External Research (if applicable)

If the context references technologies, markets, standards, or competitor products:

- Use WebSearch to gather current information
- Use Context7 MCP tools for library/framework documentation if relevant
- Look for prior art, industry standards, or established patterns

### Step 1.3: Codebase Research (if applicable)

If the project relates to an existing codebase (check the current working directory or any repo paths mentioned):

- Explore existing related functionality
- Identify current capabilities and gaps
- Understand existing architecture patterns
- Note existing user-facing behaviors that the new product will interact with or replace

### Step 1.4: Synthesize Research

Produce an internal summary of what you've learned. Identify:

- What is **well-defined** in the initial context
- What is **implied but not stated** (assumptions you're making)
- What is **missing entirely** (gaps that must be filled for a complete PRD)
- What has **multiple valid approaches** (decisions the user needs to make)

---

## Phase 2: Collaborative Q&A

This phase is the heart of the skill. Ask informed, specific questions that fill PRD gaps. Do NOT ask generic template questions — every question should be grounded in your research.

### Step 2.1: Prepare Questions

Organize your questions into these PRD categories. Only include categories where you actually have gaps — skip categories where the context already provides clear answers:

1. **Problem & Motivation**: What problem does this solve? Why now? What happens if we don't build it?
2. **Users & Personas**: Who are the target users? What are their roles, skills, and contexts?
3. **Goals & Non-Goals**: What is explicitly in scope? What is explicitly out of scope?
4. **Success Metrics**: How do we know this succeeded? What are the measurable outcomes?
5. **Functional Requirements**: What must the system do? What are the core workflows?
6. **Non-Functional Requirements**: Performance, security, scalability, compliance, accessibility constraints?
7. **Constraints & Dependencies**: What external factors limit the solution space? (timeline, budget, team, technology, regulatory)
8. **Prior Art & Context**: What exists today? What has been tried before? What can we learn from competitors or adjacent systems?
9. **Risks & Open Questions**: What could go wrong? What don't we know yet?

### Step 2.2: Ask Questions

Use AskUserQuestion to present your questions. **Cluster related questions together** — do not drip them one at a time. Group into 2-4 batches maximum.

For each question:
- State what you already know from research (so the user doesn't repeat themselves)
- Explain why this information matters for the PRD
- Suggest a default or option when you can (reduce cognitive load)

**Example format:**

```
Based on my research, I've identified several areas that need your input to build a complete PRD.

## Users & Scope

1. **Target users** — The context mentions "cluster administrators" and "end users." Are there other user types? For each, what's their technical skill level and primary workflow?

2. **Scope boundary** — The context describes both a CLI and a web UI. Is one the primary interface for v1, or are both required from day one?

## Requirements Clarification

3. **Authentication model** — The existing system uses Keycloak. Should this product integrate with existing auth, or does it need its own auth system? (I noticed FUZZ-6351 is exploring local users as an alternative.)

4. **Data retention** — The context mentions audit logs. Is there a compliance requirement driving retention period, or is this an internal preference?
```

### Step 2.3: Iterate if Needed

If the user's answers reveal new gaps or raise new questions, ask a follow-up round. Limit to **3 rounds maximum** — after that, document remaining unknowns as open questions in the PRD rather than continuing to ask.

After each round, briefly summarize what you've captured so far so the user can correct misunderstandings early.

---

## Phase 3: Draft the PRD

### Step 3.1: Write the PRD

Create the PRD at `<output-directory>/prd.md` with the following structure:

```markdown
# Product Requirements Document: [Project Name]

**Version:** 1.0
**Author:** [User name if known, otherwise "Product Team"]
**Created:** [ISO 8601 timestamp with MST offset]
**Last Updated:** [ISO 8601 timestamp with MST offset]
**Status:** Draft
**Jira:** [Epic key(s) and links, if available]

---

## 1. Executive Summary

[2-3 paragraph summary: what the product is, why it exists, who it's for, and the high-level approach]

---

## 2. Problem Statement

### 2.1 Problem Description

[Clear articulation of the problem being solved]

### 2.2 Current State

[What exists today and why it's insufficient]

### 2.3 Impact of Not Acting

[What happens if this product is not built]

---

## 3. Users and Personas

### 3.1 Primary Users

[For each user type: role, technical level, primary goals, typical workflows]

### 3.2 Secondary Users

[Users who interact with the product indirectly or occasionally]

### 3.3 Stakeholders

[Non-users who have requirements or influence: ops, legal, finance, etc.]

---

## 4. Goals and Non-Goals

### 4.1 Goals

[Numbered list of what this product MUST achieve]

### 4.2 Non-Goals

[Explicit list of what this product will NOT do — scope boundaries]

### 4.3 Future Considerations

[Things that are out of scope for v1 but may be addressed later]

---

## 5. Success Metrics

| Metric | Target | Measurement Method |
| ------ | ------ | ------------------ |
| [Metric name] | [Quantifiable target] | [How to measure] |

---

## 6. Functional Requirements

### 6.1 [Requirement Area 1]

| ID | Requirement | Priority | Notes |
| -- | ----------- | -------- | ----- |
| FR-001 | [Requirement description] | Must Have / Should Have / Nice to Have | [Context] |

### 6.2 [Requirement Area 2]

[Repeat for each functional area]

---

## 7. Non-Functional Requirements

| ID | Category | Requirement | Target |
| -- | -------- | ----------- | ------ |
| NFR-001 | Performance | [Requirement] | [Measurable target] |
| NFR-002 | Security | [Requirement] | [Standard or target] |
| NFR-003 | Scalability | [Requirement] | [Target] |

---

## 8. Constraints and Dependencies

### 8.1 Technical Constraints

[Technology, platform, compatibility requirements]

### 8.2 Business Constraints

[Timeline, budget, team, regulatory]

### 8.3 Dependencies

| Dependency | Type | Impact if Unavailable |
| ---------- | ---- | --------------------- |
| [Dependency] | Hard / Soft | [What happens without it] |

---

## 9. User Workflows

### 9.1 [Workflow Name]

**Actor:** [User type]
**Trigger:** [What initiates the workflow]
**Preconditions:** [What must be true before starting]

1. [Step 1]
2. [Step 2]
3. [Step 3]

**Postconditions:** [What is true after completion]
**Error Cases:** [What can go wrong and expected behavior]

[Repeat for each major workflow]

---

## 10. Phasing and Milestones

### 10.1 Phase Breakdown

| Phase | Scope | Target | Key Deliverables |
| ----- | ----- | ------ | ---------------- |
| Phase 1 | [Scope] | [Date or relative] | [Deliverables] |

### 10.2 MVP Definition

[What constitutes the minimum viable product — the smallest useful subset]

---

## 11. Risks and Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
| - | ---- | ---------- | ------ | ---------- |
| 1 | [Risk] | High/Med/Low | High/Med/Low | [Strategy] |

---

## 12. Open Questions

| # | Question | Owner | Impact | Target Resolution Date |
| - | -------- | ----- | ------ | ---------------------- |
| 1 | [Question] | [Who should answer] | [What it blocks] | [When] |

---

## 13. Glossary

| Term | Definition |
| ---- | ---------- |
| [Term] | [Definition in context of this product] |

---

## Appendix

### A. References

[All source documents, Jira links, Confluence pages, external resources used]

### B. Related Projects

[Other projects or features that interact with or depend on this one]

### C. Decision Log

| # | Decision | Date | Rationale | Alternatives Considered |
| - | -------- | ---- | --------- | ----------------------- |
| 1 | [Decision] | [Date] | [Why] | [What else was considered] |
```

**Rules for writing the PRD:**

- Every section must contain substance from the research and Q&A — no placeholder text like "[TBD]" or "[To be determined]". If information is truly unknown, move it to Open Questions.
- Requirements MUST be specific and testable. "The system should be fast" is not a requirement. "API responses complete within 200ms at P95 under 100 concurrent users" is.
- Non-goals are as important as goals. Every scope boundary the user defined goes here.
- The Decision Log captures choices made during Q&A — what was decided and why, including what was considered but rejected.
- Use the user's language and terminology, not generic PM jargon.

### Step 3.2: User Review and Approval

Present the PRD to the user for review. Use AskUserQuestion:

```
I've drafted the PRD based on our research and discussion. Please review `prd.md` and let me know:

1. Are there any requirements that are missing or incorrect?
2. Do the priorities (Must Have / Should Have / Nice to Have) reflect your intent?
3. Are the scope boundaries (Goals vs Non-Goals) drawn correctly?
4. Any sections that need more detail or correction?

I'll revise based on your feedback before proceeding to user scenarios.
```

Incorporate feedback and revise. Iterate up to 2 more times if the user has substantial changes.

---

## Phase 4: Generate User Scenario Verifications

These are **product-level acceptance scenarios** — not engineering API/CLI tests. They describe what a user should be able to do once the system is fully implemented, written from the user's perspective.

### Step 4.1: Extract Scenarios from PRD

For each user workflow in Section 9 and each functional requirement in Section 6, derive user scenarios:

- **Happy path**: The workflow completes successfully
- **Key error cases**: The most important failure modes
- **Edge cases**: Boundary conditions called out in requirements

### Step 4.2: Write Verification Documents

Create one or more documents in `<output-directory>/verifications/`. Organize by user type or workflow area.

Each verification document follows this structure:

```markdown
# User Scenarios: [Area Name]

**PRD:** [../prd.md](../prd.md)
**Created:** [ISO 8601 timestamp with MST offset]

---

## US-001: [Scenario Title]

**User:** [Persona from PRD Section 3]
**PRD Reference:** [FR-XXX, Workflow 9.X]
**Priority:** [Must Have / Should Have / Nice to Have — matches the requirement priority]

### Scenario

[Narrative description of what the user does, written in second person ("You...") or third person ("The admin...")]

### Preconditions

- [What must be true before this scenario starts]

### Steps

1. [User action — described at the product level, not CLI/API level]
2. [Next action]
3. [Next action]

### Expected Outcome

- [Observable result from the user's perspective]
- [State change that should be visible]

### Acceptance Criteria

- [ ] [Specific, checkable criterion]
- [ ] [Another criterion]

---
```

**Rules for user scenarios:**

- Write from the **user's perspective**, not the developer's. "The admin creates a new organization" not "POST /v4/organizations with body {...}".
- Every Must Have requirement MUST have at least one scenario.
- Include both success and failure scenarios for critical workflows.
- Reference PRD requirement IDs (FR-XXX) so scenarios are traceable to requirements.
- These are NOT engineering test cases — they do not contain shell commands, API calls, or implementation details. They describe **what should work**, not **how to test it**.

### Step 4.3: Create Verification Coverage Matrix

Add a coverage matrix to the end of the main verification document (or as a separate `coverage-matrix.md` if there are multiple verification files):

```markdown
## Coverage Matrix

| PRD Requirement | Priority | Scenario(s) | Status |
| --------------- | -------- | ----------- | ------ |
| FR-001 | Must Have | US-001, US-003 | Covered |
| FR-002 | Must Have | US-005 | Covered |
| FR-003 | Should Have | — | Not Yet Covered |
```

All Must Have requirements must show "Covered" status.

---

## Phase 5: Seed Supplementary Documents

If your research in Phase 1 produced substantial reference material that supports the PRD, create documents in `<output-directory>/documents/`.

### When to Create Documents

Create a supplementary document when:

- Research uncovered a technology comparison or evaluation relevant to the product
- Competitive analysis or market research was performed
- A complex constraint or dependency needs detailed explanation beyond what fits in the PRD
- Meeting notes, stakeholder interviews, or decision records exist
- A referenced specification or standard needs a summary

### When NOT to Create Documents

Do not create a document when:

- The information fits cleanly in the PRD itself (put it there instead)
- The information is generic and not specific to this project
- The information is better served as a knowledge base entry (put it in `kb/` instead)

### Document Format

Supplementary documents have no rigid structure — use whatever format best serves the content. Each should include:

```markdown
# [Document Title]

**Related PRD Sections:** [List which PRD sections this supports]
**Created:** [ISO 8601 timestamp with MST offset]

---

[Content]
```

---

## Phase 6: Seed Knowledge Base

If your research or the Q&A process surfaced domain knowledge that will be referenced repeatedly during feature implementation, create entries in `<output-directory>/kb/`.

### When to Create KB Entries

Create a KB entry when:

- A domain concept needs definition and context beyond the PRD glossary
- A technology or protocol is central to the product and developers need a primer
- An architectural pattern or design principle will guide multiple features
- Historical context or institutional knowledge informs product decisions

### KB Entry Format

```markdown
# [Topic Title]

**Category:** [Domain Concept / Technology Primer / Architecture Pattern / Reference]
**Created:** [ISO 8601 timestamp with MST offset]
**Related PRD Sections:** [List relevant PRD sections]

---

[Content — concise, factual, actionable. Written so a new team member can get up to speed.]
```

### Guidance

- Keep entries focused — one topic per document
- Write for a reader who is new to the project
- Include links to authoritative external sources
- These entries will grow over time as features are planned and built

---

## Phase 7: Finalize All Index Files

### Step 7.1: Update All Index Files

Re-read every `index.md` file and ensure every document that exists in each folder is listed.

**Update `documents/index.md`** — add a row for each document created in Phase 5.

**Update `kb/index.md`** — add a row for each KB entry created in Phase 6.

**Update `verifications/index.md`** — add a row for each verification document created in Phase 4. Include the coverage matrix reference.

**`features/index.md`** — should remain empty (no features planned yet). Verify it has the correct placeholder text.

### Step 7.2: Update Root Index

Add a summary section to the root `index.md`:

```markdown
---

## Project Summary

| Section | Status | Document Count |
| ------- | ------ | -------------- |
| PRD | [Draft/Approved] | 1 |
| Documents | [count or "None"] | [count] |
| Features | Not Started | 0 |
| Knowledge Base | [count or "None"] | [count] |
| Verifications | Draft | [count] |

**Total User Scenarios:** [count from verifications]
**Must-Have Requirements:** [count from PRD]
**Open Questions:** [count from PRD Section 12]

---

## Next Steps

1. Review and approve the PRD
2. Resolve open questions in PRD Section 12
3. Use `/new-eng-feature <features/feature-slug> <spec links>` to begin engineering planning for individual features
```

### Step 7.3: Verify All Links

Ensure:
- All relative links in index files point to existing files
- All timestamps are ISO 8601 with MST offset
- The root index points to all child indexes
- Every child index points back to the parent

### Step 7.4: Present Summary to User

After all phases are complete, present a final summary:

1. List all documents created with their paths
2. Highlight the number of user scenarios and their coverage of Must Have requirements
3. Note any open questions that need resolution
4. List the knowledge base entries created
5. Suggest next steps (typically: review PRD, resolve open questions, then `/new-eng-feature` for individual features)

---

## Error Handling

### If MCP Tools Are Unavailable

- If the initial context includes Jira/Confluence URLs but MCP tools fail, inform the user and ask whether to proceed with only the textual context provided, or to abort and fix MCP connectivity first.

### If the User Provides Very Thin Context

- Do not produce a thin PRD. Ask more questions. Use your research to identify what's missing and ask informed questions.
- If after 3 rounds of Q&A the PRD still has significant gaps, document them prominently in Open Questions and warn the user that the PRD needs more input before engineering planning should begin.

### If the User Disagrees with a Research Finding

- The user's product judgment overrides your research. Update the PRD to reflect their decision and document the research finding in the Decision Log (Appendix C) so the context is preserved.

---

## Important Guidelines

1. **This is product-level, not engineering-level.** The PRD describes WHAT to build and WHY. HOW to build it is the domain of `/new-eng-feature`, which the user will run inside `features/` later. Do not include codebase impact analysis, file-level changes, or implementation details in the PRD.

2. **Q&A is the primary value.** A PRD generated from thin context without informed questions is worse than no PRD. Your research should surface questions the user hasn't thought of. Every question should demonstrate that you've done your homework.

3. **User scenarios are product-level, not test-level.** Verifications describe what a user should be able to do, not how a developer should test it. No shell commands, no API calls, no test fixtures.

4. **The `features/` folder is a container.** Do not populate it. Its index explicitly states it will be filled by `/new-eng-feature` runs. This is the bridge between product planning and engineering planning.

5. **Timestamps in MST.** All timestamps in index files must use ISO 8601 format with MST offset: `YYYY-MM-DDTHH:MM:SS-06:00` (or `-07:00` during MDT). Use the current time when creating each document.

6. **Index files are your responsibility.** After creating each document, update the relevant index. Every file must be discoverable through the index chain from the root.

7. **Respect the user's terminology.** The PRD should use the language of the user's domain, not generic PM vocabulary. If the user says "provisioner," don't rewrite it as "resource provider."

8. **The Decision Log matters.** Every choice made during Q&A — especially where alternatives were considered — belongs in Appendix C. This prevents future "why did we decide this?" conversations.

9. **KB entries are seeds, not comprehensive docs.** Write enough to orient a newcomer. The KB will grow organically as features are planned and implemented.

10. **Scope boundary with /update-project.** This skill creates new projects. `/update-project` handles revisions. They share the same folder structure and PRD format, but `/update-project` reads existing artifacts first and produces incremental changes with a changelog.
