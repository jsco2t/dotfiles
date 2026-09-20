---
name: new-drd
description: "Create a Delivery Requirements Document (DRD) -- a lean, delivery-focused requirements doc for a scoped unit of work that will be implemented (often by an AI agent via /feature-workflow). Researches context from Jira, GitHub, Confluence, files, or free-text, then runs a probing Q&A to pin down the problem, the solution, and a traceable set of deliverables with completion criteria. Outputs a single file with a requirements-to-deliverables coverage matrix. Deliberately omits PRD fluff -- target-user personas, business justification, user scenarios -- in favor of what it takes to land the work."
argument-hint: "<output-file-path> <context: description, URLs, Jira/GitHub issue links, or file paths>"
---

# New DRD Skill

## Atlassian access (Jira & Confluence) — load on demand

If — and only if — this task needs Jira or Confluence, use the local Atlassian toolkit.
Read its usage doc once, then use it: `~/.local/bin/atlassian-toolkit/README.md`. Do not
read it when the task has no Jira/Confluence work. Commands are on `PATH`: `jira ...`
(issues, search, projects), `confluence ...` (pages, search), `atlassian search "..."` (both).

You are creating a **Delivery Requirements Document (DRD)** — a lean requirements document for a scoped **unit of work** that will be implemented, often by an AI agent via `/feature-workflow`. This is **not** a full product PRD. It deliberately omits target-user personas, business justification, and user scenarios outside the problem being solved. It captures exactly what a builder needs — the **problem**, the **solution**, the **specific deliverables**, and **how you know each one is done** — and nothing whose only job is to sell the work.

The document's scope determines its framing:

- **PRODUCT scope** — the unit of work stands alone; nothing exists yet to attach to. No existing-system context applies.
- **PROJECT scope** — the unit of work changes or extends an existing system. It inherits that system's context and states what changes, what stays the same, and what breaks.

**The deliverables section is the core.** A requirement describes behavior. A deliverable is a thing that gets handed over — an endpoint, a binary, a CLI subcommand, a migration, a config key, a doc page, a CI job. The skill is done when every Must-Have requirement maps to at least one deliverable, and every deliverable has acceptance criteria. If Q&A can't get there, the residue goes into Open Questions with a loud warning — do not quietly emit a thin document.

**This is a collaborative process.** The user provides initial context, and you research, ask informed questions, and iterate until the deliverables are pinned down. Do not rubber-stamp thin context into a document — your questions and research are the value.

## Input

The user has provided the following context:

$ARGUMENTS

You need two inputs. If either is missing, use AskUserQuestion to ask:

1. **Output location** — where to write the DRD. **Default the filename to `drd.md`:** if the user gives a directory, or omits the filename, write `drd.md` in that location; only use a different filename when the user explicitly names one. Examples: `./docs/drd.md`, or a directory like `/Users/jscott/Developer/sources/personal/notebook/projects/my-project/` → `.../my-project/drd.md`.
2. **Initial context** — a description of what needs to be built, links to existing documents (Jira issues, GitHub issues, Confluence pages, local files), or free-text. This is the seed — you will expand it through research and Q&A.

---

## Phase 1: Research the Initial Context

Before asking questions, do your homework. Your questions should be informed, not generic.

### Step 1.1: Parse Provided Context

Identify all resources in the initial context:

- **Jira Issues**: URLs or issue keys (e.g., `FUZZ-1234`) — fetch using the Atlassian toolkit (`jira issue get <key>`)
- **Confluence Pages**: URLs — fetch using the Atlassian toolkit (`confluence page get <url>`)
- **GitHub Issues/PRs**: URLs or `owner/repo#number` — fetch using `ghtk issue get <number> --repo <owner>/<repo>` (the local GitHub toolkit; stdlib, works in-sandbox; reference: `~/.local/bin/github-toolkit/README.md`). If `ghtk` fails (auth issue), ask the user to paste the issue body rather than aborting.
- **File paths**: Read local files
- **URLs**: Fetch using WebFetch or WebSearch
- **Free-text**: Parse for the problem, the proposed solution, requirements, and constraints

### Step 1.2: External Research (if applicable)

If the context references technologies, standards, or existing products:

- Use WebSearch to gather current information
- Use Context7 MCP tools for library/framework documentation if relevant
- Look for prior art, established patterns, or industry standards

### Step 1.3: Codebase Research (if applicable)

If the work relates to an existing codebase (check the current working directory or any repo paths mentioned):

- Explore existing related functionality
- Identify current capabilities and gaps
- Understand existing architecture patterns
- Note existing behaviors that will be affected

### Step 1.4: Synthesize Research

Produce an internal summary identifying:

- What is **well-defined** in the initial context
- What is **implied but not stated** (assumptions you're making)
- What is **missing entirely** (gaps that must be filled)
- What has **multiple valid approaches** (decisions the user needs to make)

---

## Phase 2: Determine Scope

Based on your research, determine whether the unit of work **stands alone** (PRODUCT scope) or **changes an existing system** (PROJECT scope).

### Decision Criteria

| Signal | Scope |
|--------|-------|
| Building something that does not exist yet | PRODUCT |
| No existing system to attach to | PRODUCT |
| Adding to or extending an existing system | PROJECT |
| Changing behavior in an existing system | PROJECT |
| Rewriting a subsystem of an existing system | PROJECT (usually) |

The only difference the scope makes: **PROJECT scope includes an Existing-Context section** (current behavior, what changes, what stays, backward compatibility); PRODUCT scope omits it. Both produce the same lean, delivery-focused document.

### Ambiguous Cases — Ask the User

Some situations are genuinely ambiguous. When you detect one of these, state your assessment with evidence and confirm via AskUserQuestion:

- Work against a system that has **no existing requirements doc** — is this defining the system or just this change?
- Work spanning **two or more existing systems** — which is the parent?
- A **full rewrite** of an existing subsystem — new standalone work, or a change within the current system?

State the detected scope, explain your reasoning, and let the user confirm or override.

---

## Phase 3: Collaborative Q&A

Ask informed, specific questions that fill gaps. Do NOT ask generic template questions — every question should be grounded in your research. **This is the most valuable part of the skill; the leaner output does not mean a leaner Q&A.** The deliverable and done-criteria questions now carry the whole document — ask as many specific questions as it takes to pin them down.

### Step 3.1: Prepare Questions

Organize questions by these categories. **Only include categories where you have gaps** — skip categories where the context already provides clear answers:

**For both PRODUCT and PROJECT scope:**

1. **Problem & Current State**: What is wrong or missing today? What exists now, and why is it insufficient? (State the problem — not why it matters to the business.)
2. **Solution Shape**: What is the approach at a *what* level? What alternatives were considered and why is this one chosen? What is the boundary of the approach?
3. **Goals & Non-Goals**: What is explicitly in scope? What is explicitly out? What is deferred to a follow-on?
4. **Functional Requirements**: What must the system do? Which behaviors are Must vs Should vs Nice?
5. **Non-Functional Requirements**: Performance, security, scalability, compliance?
6. **Deliverables**: What artifacts get handed over? (APIs, CLIs, config, docs, migrations, CI jobs, binaries.) Does any deliverable need an operator procedure to be usable — a build/publish sequence, a migration run order?
7. **Definition of Done**: Beyond each deliverable's own acceptance, what unit-of-work-level gates must pass? (Integration/smoke tests, verification on all targets, docs published, CI green.)
8. **Constraints & Dependencies**: What limits the solution space? What must exist for this to land?
9. **Risks & Open Questions**: What could stop the work from landing? What don't we know yet?

**Additional for PROJECT scope:**

10. **What Changes / What Stays**: Which existing behaviors change? Which are deliberately unchanged?
11. **Backward Compatibility**: What breaks? What migration path or deprecation is needed?
12. **Parent-System Constraints**: What architectural or convention decisions in the existing system bound this work?

Do **not** ask about target-user personas, business justification, adoption/usage KPIs, or stakeholders — those are out of scope for a DRD.

### Step 3.2: Ask Questions

Use AskUserQuestion to present questions. **Cluster related questions together** — do not drip them one at a time. Group into 2-4 batches maximum.

For each question:
- State what you already know from research (so the user doesn't repeat themselves)
- Explain why this information matters for the deliverables or the done-state
- Suggest a default or option when you can (reduce cognitive load)

### Step 3.3: Iterate if Needed

If answers reveal new gaps, ask a follow-up round. The skill's exit condition is **not** a round count — it is:

> Every Must-Have requirement maps to at least one deliverable, and every deliverable has acceptance criteria.

If you cannot reach that state after 3 rounds of Q&A, document the remaining gaps prominently in Open Questions with a clear warning that the DRD is incomplete and should not proceed to implementation until resolved.

After each round, briefly summarize what you've captured so far so the user can correct misunderstandings early.

---

## Phase 4: Draft the DRD

### Step 4.1: Write the Document

Write the DRD to the output file path, using the template below. The **2A. Existing Context** section applies to PROJECT scope only — omit it entirely for PRODUCT scope.

```markdown
# Delivery Requirements Document: [Unit of Work Name]

**Scope:** Product | Project
**Status:** Draft
**Author:** [User name if known, otherwise omit]
**Created:** [ISO 8601 timestamp with MST offset]
**Last Updated:** [ISO 8601 timestamp with MST offset]
**References:** [Jira/GitHub/Confluence links, source files]

---

## 1. Summary

[One short paragraph. Lead with WHAT ships, then the one-line WHY — the problem it closes.
No vision, no business case, no audience framing. A reader must know what this delivers from
the first sentence.]

---

## 2. Problem

### 2.1 Problem

[What is wrong or missing today, stated once, plainly — the gap this work closes. Not why it
matters to the business.]

### 2.2 Current State

[What exists today in the affected area and why it is insufficient. Be concrete — name the
systems, commands, files, or behaviors involved.]

---

## 2A. Existing Context  *(PROJECT scope only — omit for PRODUCT scope)*

### 2A.1 System Being Changed

[The existing system this work lives in. Link to its docs/repo. One or two sentences.]

### 2A.2 Current Behavior

[What the system does today in the area this work touches. Name the endpoints, commands, jobs,
or workflows that exist.]

### 2A.3 What Changes

[Explicit list of existing behaviors that will be modified or added.]

### 2A.4 What Does NOT Change

[Explicit list of existing behaviors deliberately preserved. Prevents scope creep and guards
against regressions.]

### 2A.5 Backward Compatibility

[What breaks, if anything; the migration path; any deprecation. If the work is purely additive,
say so in one line.]

---

## 3. Solution Approach

[The chosen solution at a WHAT level — the shape of the answer, enough for a builder to
understand the approach and for the deliverables below to make sense. Name the mechanism reused
or introduced, the pattern followed, and the boundary of the approach. Keep implementation
detail — file-level changes, code — out; that is the builder's job.]

---

## 4. Scope

### 4.1 Goals

[Numbered list of what this work must achieve. Objective-level.]

### 4.2 Non-Goals

[Explicit list of what this work will NOT do. As important as the goals — every scope boundary
goes here.]

### 4.3 Deferred

[Out of scope for this unit of work but a likely follow-on. Names what NOT to build now.]

---

## 5. Requirements

### 5.1 Functional Requirements

| ID | Requirement | Priority | Notes |
| -- | ----------- | -------- | ----- |
| FR-001 | [Specific, testable requirement] | Must / Should / Nice | [Context] |

### 5.2 Non-Functional Requirements

| ID | Category | Requirement | Target |
| -- | -------- | ----------- | ------ |
| NFR-001 | Performance / Security / … | [Requirement] | [Measurable target] |

---

## 6. Deliverables

### 6.1 Deliverable Inventory

| ID | Deliverable | Type | Description | Satisfies | Acceptance Criteria |
| -- | ----------- | ---- | ----------- | --------- | ------------------- |
| D-001 | [Name] | API / CLI / Config / Migration / Doc / CI / Binary / Library | [What it is. If it needs an operator procedure to be usable — a build/publish sequence, a migration run order — state it here.] | FR-001, FR-003 | [How you know THIS one is done] |

### 6.2 Not Deliverables

[Explicit list of artifacts this work does NOT produce — the deliverable-level counterpart to
non-goals. E.g. "No UI in this unit", "No public API docs yet".]

### 6.3 Coverage Matrix

| Requirement | Priority | Deliverable(s) | Status |
| ----------- | -------- | -------------- | ------ |
| FR-001 | Must | D-001 | Covered |
| FR-003 | Should | — | ⚠ Gap |

**Gaps:** [Any Must-Have requirement with no deliverable — these block implementation.]
**Unlinked Deliverables:** [Any deliverable satisfying no requirement — potential scope creep.]

---

## 7. Definition of Done

The unit of work is done when **all** per-deliverable acceptance criteria in §6.1 pass **and**
the unit-of-work-level gates below — the ones no single deliverable owns — are met:

- [ ] [Integration / end-to-end gate]
- [ ] [Verification gate — e.g. passes on every target platform/environment]
- [ ] [Documentation / handover gate]
- [ ] [Release / rollout gate, if any]

Do not restate per-deliverable criteria here — they live in §6.1 and are all required. This
section captures only what falls between or across deliverables.

---

## 8. Constraints and Dependencies

### 8.1 Technical Constraints

[Technology, platform, compatibility, or convention limits that bound the solution. Real
constraints on landing the work only.]

### 8.2 Dependencies

| Dependency | Type | Impact if Unavailable |
| ---------- | ---- | --------------------- |
| [Dependency] | Hard / Soft | [What is blocked without it] |

---

## 9. Sequencing

[The order deliverables should land, and the smallest first slice that is useful and verifiable.
Include only if sequencing matters — if everything can land together, say so in one line.]

| Step | Deliverables | Rationale |
| ---- | ------------ | --------- |
| 1 | D-001 | [Why first] |

---

## 10. Risks and Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
| - | ---- | ---------- | ------ | ---------- |
| 1 | [Delivery risk — what could stop the work landing] | High/Med/Low | High/Med/Low | [Strategy] |

---

## 11. Open Questions

| # | Question | Blocks | Owner |
| - | -------- | ------ | ----- |
| 1 | [Unresolved question] | [What it blocks] | [Who answers] |

⚠ **If any Must-Have requirement lacks a deliverable, or any question above blocks
implementation, this DRD is not ready for `/feature-workflow`.** Say so plainly.

---

## Appendix

### A. References

[Source documents, Jira/GitHub/Confluence links, files consulted.]

### B. Decision Log

| # | Decision | Rationale | Alternatives Considered |
| - | -------- | --------- | ----------------------- |
| 1 | [Decision made during Q&A] | [Why] | [What was rejected] |

### C. Glossary  *(optional)*

| Term | Definition |
| ---- | ---------- |
| [Term] | [Definition in the context of this work] |
```

**PROJECT scope** additionally: give any backward-compatibility transition its own `Migration`-type deliverable in §6.1, and cover the migration path in §2A.5.

### Writing Style (answer-first)

Write the DRD to be read fast and acted on, not to persuade.

- **Lead with the point.** Each section — and each requirement and deliverable — opens with what it is, and where it applies its done-state, before any elaboration. The Summary's first sentence names what ships.
- **Don't sell the work.** No business justification, no "impact of not acting," no audience or persona framing. State the problem once, plainly, then move to the solution and the deliverables. We are doing the work; the document does not need to argue for it.
- **Complete sentences, plain language.** Use the user's domain terms, not generic PM vocabulary. Introduce an unfamiliar term the first time it appears.
- **Requirements are specific and testable.** "The system should be fast" is not a requirement. "API responses complete within 200ms at P95 under 100 concurrent users" is.
- **Tables only for uniform short values** — the requirement, deliverable, coverage, dependency, risk, and decision grids. If a cell wants a full clause, it wanted to be prose; put it in the deliverable description, not the table.
- **Scope boundaries are first-class.** Non-Goals and Not-Deliverables get the same care as goals and deliverables.
- **No placeholder text.** Every section carries substance from research and Q&A — no "[TBD]". Unknowns go to Open Questions.
- **Operator procedures live with their deliverable.** If a deliverable needs a procedure to be usable — a build/publish sequence, a migration run order — put it in that deliverable's description or acceptance criteria, never in a separate workflow section.
- **The Coverage Matrix in §6.3 must be complete.** Every Must-Have requirement maps to at least one deliverable. Flag gaps loudly.

---

## Phase 5: User Review

Present the DRD to the user for review:

- Are there requirements that are missing or incorrect?
- Do the priorities (Must / Should / Nice) reflect your intent?
- Are the scope boundaries (Goals vs Non-Goals, Deliverables vs Not-Deliverables) drawn correctly?
- Does the coverage matrix have gaps that need resolution?
- Is the Definition of Done complete — would passing every gate mean the work is truly landed?

Incorporate feedback and revise. Iterate up to 2 more times if the user has substantial changes.

After final approval, update the Status field from "Draft" to "Approved" and update the Last Updated timestamp.

---

## Error Handling

### If Atlassian Is Unavailable

If the context includes Jira/Confluence references but the toolkit fails, inform the user and ask whether to proceed with only the textual context, or to abort and fix connectivity first.

### If GitHub Access Fails

If `ghtk issue get` fails (auth issues), ask the user to paste the issue body rather than aborting. Do not silently skip referenced GitHub issues.

### If the User Provides Very Thin Context

Do not produce a thin DRD. Ask more questions. Use your research to identify what's missing and ask informed questions. If after 3 rounds of Q&A the coverage matrix still has significant gaps, document them prominently in Open Questions and warn the user that the DRD needs more input before implementation should begin.

### If the User Disagrees with a Research Finding

The user's judgment overrides your research. Update the DRD to reflect their decision and document the research finding in the Decision Log so the context is preserved.

---

## Important Guidelines

1. **Deliverables are the core.** A DRD without traceable deliverables is a wish list. Every Must-Have requirement must resolve to at least one concrete artifact someone can build, ship, and verify. The coverage matrix is the proof.

2. **Q&A is the primary value.** A DRD generated from thin context without informed questions is worse than no DRD. Your research should surface questions the user hasn't thought of. Trimming the output does not trim the questioning — the deliverable and done-criteria questions now carry the whole document.

3. **This is a delivery doc, not a PRD.** No target-user personas, no business justification, no user scenarios outside the problem being solved, no adoption metrics. If a section would only sell the work or describe who benefits, cut it. Keep the problem, the solution, the deliverables, and the done-state.

4. **Delivery-level, not engineering-level.** The DRD says WHAT to build and the SHAPE of the solution (§3) — not the file-level HOW. Do not include code, file-by-file change lists, or implementation detail; that is the builder's domain (e.g. `/feature-workflow`).

5. **PRODUCT vs PROJECT is a content difference.** Scope drives the title's framing and whether the Existing-Context section (2A) applies. A PROJECT-scope DRD needs current-behavior, what-changes/what-stays, and backward-compatibility; a PRODUCT-scope one does not.

6. **"Not Deliverables" matters.** The artifact-level counterpart to non-goals. If the team will argue about whether a UI or a migration script is in scope, this section settles it before implementation starts.

7. **Definition of Done is derived, not duplicated.** §7 states only the unit-of-work-level gates that no single deliverable owns. Per-deliverable acceptance criteria live in §6.1 and are all required. One claim, one home.

8. **Timestamps in MST.** Use ISO 8601 with MST offset: `YYYY-MM-DDTHH:MM:SS-06:00` (or `-07:00` during MDT).

9. **Respect the user's terminology.** Use the language of their domain, not generic PM vocabulary.

10. **The Decision Log matters.** Every choice made during Q&A — especially where alternatives were considered — belongs in the appendix. This prevents future "why did we decide this?" conversations.

11. **Single file output.** This skill produces one document at the specified path. It does not create folder structures, index files, or supplementary documents. If the user needs a full project workspace with knowledge base and verification scenarios, they should use `/new-project` instead.
