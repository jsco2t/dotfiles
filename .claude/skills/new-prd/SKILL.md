---
name: new-prd
description: "Create a Product Requirements Document (product-scope) or Project Requirements Document (project-scope) with fully identified deliverables. Researches context from Jira, GitHub, Confluence, files, or free-text, then collaborates with the user to define what exactly needs to be delivered. Outputs a single PRD file with traceable requirements-to-deliverables mapping."
argument-hint: "<output-file-path> <context: description, URLs, Jira/GitHub issue links, or file paths>"
---

# New PRD Skill

## Atlassian access (Jira & Confluence) — load on demand

If — and only if — this task needs Jira or Confluence, use the local Atlassian toolkit.
Read its usage doc once, then use it: `~/.local/bin/atlassian-toolkit/README.md`. Do not
read it when the task has no Jira/Confluence work. Commands are on `PATH`: `jira ...`
(issues, search, projects), `confluence ...` (pages, search), `atlassian search "..."` (both).

You are creating a requirements document with **fully identified deliverables**. This is different from a feature plan or an engineering spec — the output is a single document that defines *what* needs to be delivered, *for whom*, *why*, and *how you know each piece is done*.

The document's scope determines its framing:

- **PRODUCT scope** — creating something new. The PRD covers the full product vision, users, problem space, and complete deliverable set.
- **PROJECT scope** — a feature change or addition to an existing product. The PRD inherits context from the parent product and focuses on what changes, what stays the same, backward compatibility, and migration.

**The deliverables section is the core differentiator.** A requirement describes behavior. A deliverable is a thing that gets handed over — an endpoint, a binary, a CLI subcommand, a migration, a config key, a doc page, a dashboard. The skill is done when every Must-Have requirement maps to at least one deliverable, and every deliverable has acceptance criteria. If Q&A can't get there, the residue goes into Open Questions with a loud warning — do not quietly emit a thin document.

**This is a collaborative process.** The user provides initial context, and you research, ask informed questions, and iterate until the PRD is comprehensive. Do not rubber-stamp thin context into a document — your questions and research are the value.

## Input

The user has provided the following context:

$ARGUMENTS

You need two inputs. If either is missing, use AskUserQuestion to ask:

1. **Output file path** — where to write the PRD. Example: `./docs/prd.md` or `/Users/jscott/Developer/sources/personal/notebook/projects/my-project/prd.md`
2. **Initial context** — a description of what needs to be built, links to existing documents (Jira issues, GitHub issues, Confluence pages, local files), or free-text. This is the seed — you will expand it through research and Q&A.

---

## Phase 1: Research the Initial Context

Before asking questions, do your homework. Your questions should be informed, not generic.

### Step 1.1: Parse Provided Context

Identify all resources in the initial context:

- **Jira Issues**: URLs or issue keys (e.g., `FUZZ-1234`) — fetch using the Atlassian toolkit (`jira issue get <key>`)
- **Confluence Pages**: URLs — fetch using the Atlassian toolkit (`confluence page get <url>`)
- **GitHub Issues/PRs**: URLs or `owner/repo#number` — fetch using `gh issue view <number> --repo <owner>/<repo>`. If `gh` fails (TLS error, auth issue), ask the user to paste the issue body rather than aborting.
- **File paths**: Read local files
- **URLs**: Fetch using WebFetch or WebSearch
- **Free-text**: Parse for product concepts, user types, goals, constraints

### Step 1.2: External Research (if applicable)

If the context references technologies, standards, or existing products:

- Use WebSearch to gather current information
- Use Context7 MCP tools for library/framework documentation if relevant
- Look for prior art, established patterns, or industry standards

### Step 1.3: Codebase Research (if applicable)

If the project relates to an existing codebase (check the current working directory or any repo paths mentioned):

- Explore existing related functionality
- Identify current capabilities and gaps
- Understand existing architecture patterns
- Note existing user-facing behaviors that will be affected

### Step 1.4: Synthesize Research

Produce an internal summary identifying:

- What is **well-defined** in the initial context
- What is **implied but not stated** (assumptions you're making)
- What is **missing entirely** (gaps that must be filled)
- What has **multiple valid approaches** (decisions the user needs to make)

---

## Phase 2: Determine Scope

Based on your research, determine whether this is PRODUCT scope or PROJECT scope.

### Decision Criteria

| Signal | Scope |
|--------|-------|
| Building something that does not exist yet | PRODUCT |
| No existing product to attach to | PRODUCT |
| Adding a feature to an existing product | PROJECT |
| Changing behavior in an existing system | PROJECT |
| Rewriting a subsystem of an existing product | PROJECT (usually) |

### Ambiguous Cases — Ask the User

Some situations are genuinely ambiguous. When you detect one of these, state your assessment with evidence and confirm via AskUserQuestion:

- A feature addition to a product that has **no existing PRD** — is this defining the product or just the feature?
- Work spanning **two or more existing products** — which is the parent?
- A **full rewrite** of an existing subsystem — is this a new product or a project within the current one?
- The context mentions both **new product vision** and **incremental changes** — which is the actual ask?

State the detected scope, explain your reasoning, and let the user confirm or override.

---

## Phase 3: Collaborative Q&A

Ask informed, specific questions that fill gaps. Do NOT ask generic template questions — every question should be grounded in your research.

### Step 3.1: Prepare Questions

Organize questions by these categories. **Only include categories where you have gaps** — skip categories where the context already provides clear answers:

**For both PRODUCT and PROJECT scope:**

1. **Problem & Motivation**: What problem does this solve? Why now? What happens if we don't build it?
2. **Users & Personas**: Who uses this? What are their roles, skills, contexts?
3. **Goals & Non-Goals**: What is explicitly in scope? What is explicitly out?
4. **Success Metrics**: How do we know this succeeded? Measurable outcomes?
5. **Functional Requirements**: What must the system do? Core workflows?
6. **Non-Functional Requirements**: Performance, security, scalability, compliance?
7. **Constraints & Dependencies**: What limits the solution space?
8. **Deliverables**: What artifacts get handed over? (APIs, CLIs, config, docs, migrations)
9. **Risks & Open Questions**: What could go wrong? What don't we know yet?

**Additional for PROJECT scope:**

10. **Existing Behavior**: What current behavior changes? What is explicitly unchanged?
11. **Backward Compatibility**: What breaks? What migration path is needed?
12. **Existing Product Constraints**: What architectural or product decisions in the parent product bound this work?
13. **Affected Users**: Which existing users are impacted and how?

### Step 3.2: Ask Questions

Use AskUserQuestion to present questions. **Cluster related questions together** — do not drip them one at a time. Group into 2-4 batches maximum.

For each question:
- State what you already know from research (so the user doesn't repeat themselves)
- Explain why this information matters for the PRD
- Suggest a default or option when you can (reduce cognitive load)

### Step 3.3: Iterate if Needed

If answers reveal new gaps, ask a follow-up round. The skill's exit condition is **not** a round count — it is:

> Every Must-Have requirement maps to at least one deliverable, and every deliverable has acceptance criteria.

If you cannot reach that state after 3 rounds of Q&A, document the remaining gaps prominently in Open Questions with a clear warning that the PRD is incomplete and should not proceed to engineering planning until resolved.

After each round, briefly summarize what you've captured so far so the user can correct misunderstandings early.

---

## Phase 4: Draft the PRD

### Step 4.1: Write the Document

Write the PRD to the output file path. The template adapts based on scope:

#### PRODUCT Scope Template

```markdown
# Product Requirements Document: [Product Name]

**Scope:** Product
**Version:** 1.0
**Author:** [User name if known, otherwise "Product Team"]
**Created:** [ISO 8601 timestamp with MST offset]
**Last Updated:** [ISO 8601 timestamp with MST offset]
**Status:** Draft
**References:** [Jira epic links, GitHub issue links, Confluence pages]

---

## 1. Executive Summary

[2-3 paragraphs: what the product is, why it exists, who it's for, high-level approach]

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

[For each: role, technical level, primary goals, typical workflows]

### 3.2 Secondary Users

[Users who interact indirectly or occasionally]

### 3.3 Stakeholders

[Non-users with requirements or influence]

---

## 4. Goals and Non-Goals

### 4.1 Goals

[Numbered list of what this product MUST achieve]

### 4.2 Non-Goals

[Explicit list of what this product will NOT do]

### 4.3 Future Considerations

[Out of scope for v1 but may be addressed later]

---

## 5. Success Metrics

| Metric | Target | Measurement Method |
| ------ | ------ | ------------------ |
| [Name] | [Quantifiable target] | [How to measure] |

---

## 6. Functional Requirements

### 6.1 [Requirement Area]

| ID | Requirement | Priority | Notes |
| -- | ----------- | -------- | ----- |
| FR-001 | [Specific, testable requirement] | Must Have / Should Have / Nice to Have | [Context] |

[Repeat for each functional area]

---

## 7. Non-Functional Requirements

| ID | Category | Requirement | Target |
| -- | -------- | ----------- | ------ |
| NFR-001 | Performance | [Requirement] | [Measurable target] |
| NFR-002 | Security | [Requirement] | [Standard or target] |

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
**Trigger:** [What initiates it]
**Preconditions:** [What must be true]

1. [Step]
2. [Step]

**Postconditions:** [What is true after]
**Error Cases:** [What can go wrong]

[Repeat for each major workflow]

---

## 10. Deliverables

### 10.1 Deliverable Inventory

| ID | Deliverable | Type | Description | Satisfies | Acceptance Criteria |
| -- | ----------- | ---- | ----------- | --------- | ------------------- |
| D-001 | [Name] | API / CLI / Config / Migration / Doc / UI / Binary / Library | [What it is] | FR-001, FR-003 | [How you know this one is done] |
| D-002 | [Name] | [Type] | [Description] | FR-002 | [Criteria] |

### 10.2 Not Deliverables

[Explicit list of artifacts this PRD does NOT produce — the deliverable-level counterpart to non-goals. Examples: "We are not shipping a UI for this", "No public API documentation in v1"]

### 10.3 Coverage Matrix

| Requirement | Priority | Deliverable(s) | Status |
| ----------- | -------- | --------------- | ------ |
| FR-001 | Must Have | D-001 | Covered |
| FR-002 | Must Have | D-002, D-003 | Covered |
| FR-003 | Should Have | — | ⚠ Gap |

**Gaps:** [List any Must-Have requirement with no deliverable — these block engineering planning]
**Unlinked Deliverables:** [List any deliverable that satisfies no requirement — potential scope creep]

---

## 11. Phasing and Milestones

| Phase | Scope | Target | Key Deliverables |
| ----- | ----- | ------ | ---------------- |
| Phase 1 | [Scope] | [Date or relative] | D-001, D-002 |

### MVP Definition

[The smallest subset of deliverables that constitutes a useful product]

---

## 12. Risks and Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
| - | ---- | ---------- | ------ | ---------- |
| 1 | [Risk] | High/Med/Low | High/Med/Low | [Strategy] |

---

## 13. Open Questions

| # | Question | Owner | Impact | Target Resolution |
| - | -------- | ----- | ------ | ----------------- |
| 1 | [Question] | [Who answers] | [What it blocks] | [When] |

---

## 14. Glossary

| Term | Definition |
| ---- | ---------- |
| [Term] | [Definition in context of this product] |

---

## Appendix

### A. References

[All source documents, Jira links, GitHub issues, Confluence pages, external resources]

### B. Decision Log

| # | Decision | Date | Rationale | Alternatives Considered |
| - | -------- | ---- | --------- | ----------------------- |
| 1 | [Decision] | [Date] | [Why] | [What else was considered] |
```

#### PROJECT Scope Template

Use the same template as PRODUCT scope with these modifications:

**Title line:** `# Project Requirements Document: [Project/Feature Name]`

**Scope line:** `**Scope:** Project`

**Add after Section 2 (Problem Statement):**

```markdown
---

## 2A. Existing Product Context

### 2A.1 Parent Product

[Name and brief description of the existing product this project lives within. Link to parent PRD if one exists.]

### 2A.2 Current Behavior

[What the system does today in the area this project affects. Be specific — name the endpoints, screens, CLI commands, or workflows that exist.]

### 2A.3 What Changes

[Explicit list of existing behaviors that will be modified]

### 2A.4 What Does NOT Change

[Explicit list of existing behaviors that are deliberately preserved. This prevents scope creep and protects against unintended regressions.]

### 2A.5 Backward Compatibility

[What breaks, if anything. What migration path is needed. What deprecation timeline applies.]

### 2A.6 Affected Existing Users

[Which current users are impacted by this change and how. Include both positive impacts (new capability) and negative ones (workflow changes, migration burden).]
```

**Section 3 (Users)** may be compressed if the parent product already established personas — reference the parent PRD and note only new or changed user interactions.

**Section 10 (Deliverables)** should include a `Migration` type for any deliverable that handles backward compatibility transitions.

### Writing Rules

- Every section must contain substance from research and Q&A — no placeholder text like "[TBD]". Unknown information goes to Open Questions.
- Requirements MUST be specific and testable. "The system should be fast" is not a requirement. "API responses complete within 200ms at P95 under 100 concurrent users" is.
- Non-goals and "Not Deliverables" are as important as goals. Every scope boundary goes here.
- The Decision Log captures choices made during Q&A — what was decided and why, including what was rejected.
- Use the user's language and terminology, not generic PM jargon.
- The Coverage Matrix in Section 10.3 must be complete. Every Must-Have requirement must map to at least one deliverable. Flag gaps loudly.

---

## Phase 5: User Review

Present the PRD to the user for review:

- Are there requirements that are missing or incorrect?
- Do the priorities (Must Have / Should Have / Nice to Have) reflect your intent?
- Are the scope boundaries (Goals vs Non-Goals, Deliverables vs Not Deliverables) drawn correctly?
- Does the coverage matrix have gaps that need resolution?

Incorporate feedback and revise. Iterate up to 2 more times if the user has substantial changes.

After final approval, update the Status field from "Draft" to "Approved" and update the Last Updated timestamp.

---

## Error Handling

### If Atlassian Is Unavailable

If the context includes Jira/Confluence references but the toolkit fails, inform the user and ask whether to proceed with only the textual context, or to abort and fix connectivity first.

### If GitHub CLI Fails

If `gh issue view` fails (TLS errors, auth issues), ask the user to paste the issue body rather than aborting. Do not silently skip referenced GitHub issues.

### If the User Provides Very Thin Context

Do not produce a thin PRD. Ask more questions. Use your research to identify what's missing and ask informed questions. If after 3 rounds of Q&A the PRD still has significant gaps in the coverage matrix, document them prominently in Open Questions and warn the user that the PRD needs more input before engineering planning should begin.

### If the User Disagrees with a Research Finding

The user's product judgment overrides your research. Update the PRD to reflect their decision and document the research finding in the Decision Log so the context is preserved.

---

## Important Guidelines

1. **Deliverables are the core.** A PRD without traceable deliverables is a wish list. Every Must-Have requirement must resolve to at least one concrete artifact someone can build, ship, and verify. The coverage matrix is the proof.

2. **Q&A is the primary value.** A PRD generated from thin context without informed questions is worse than no PRD. Your research should surface questions the user hasn't thought of.

3. **PRODUCT vs PROJECT is a content difference, not a filename difference.** The user supplies the output path. Scope drives the document title, framing, and which sections apply. A PROJECT-scope PRD needs backward compatibility, migration, and existing behavior sections that a PRODUCT-scope one doesn't.

4. **This is product-level, not engineering-level.** The PRD describes WHAT to build and WHY. HOW to build it is the domain of engineering planning skills. Do not include codebase impact analysis, file-level changes, or implementation details.

5. **"Not Deliverables" matters.** The artifact-level counterpart to non-goals. If the team will argue about whether a UI or a migration script is in scope, this section settles it before engineering starts.

6. **Timestamps in MST.** Use ISO 8601 with MST offset: `YYYY-MM-DDTHH:MM:SS-06:00` (or `-07:00` during MDT).

7. **Respect the user's terminology.** Use the language of their domain, not generic PM vocabulary.

8. **The Decision Log matters.** Every choice made during Q&A — especially where alternatives were considered — belongs in the appendix. This prevents future "why did we decide this?" conversations.

9. **Single file output.** This skill produces one document at the specified path. It does not create folder structures, index files, or supplementary documents. If the user needs a full project workspace with knowledge base and verification scenarios, they should use `/new-project` instead.
