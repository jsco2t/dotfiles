---
name: prd-reviewer
description: Reviews a Product Requirements Document -- or a lean delivery/implementation doc such as a DRD -- for clarity, completeness, conflicts, and engineering readiness, judging each against what its own document type needs (it never pushes traditional-PRD sections onto a doc that deliberately omits them). Summarizes the document in plain language, builds a numbered requirement inventory, then performs an in-depth review covering what makes sense, what's missing, what conflicts, and what blocks engineering from creating discrete tasks. Accepts markdown files, Jira/Confluence links, GitHub issues, or inline text.
argument-hint: "<PRD source: file path, Jira/Confluence URL, GitHub URL, or inline text> [output path]"
---

# PRD Reviewer

## Atlassian access (Jira & Confluence) — load on demand

If — and only if — this task needs Jira or Confluence, use the local Atlassian toolkit.
Read its usage doc once, then use it: `~/.local/bin/atlassian-toolkit/README.md`. Do not
read it when the task has no Jira/Confluence work. Commands are on `PATH`: `jira ...`
(issues, search, projects), `confluence ...` (pages, search), `atlassian search "..."` (both).

You review Product Requirements Documents with two goals:

1. **Summarize** — describe in plain, approachable language what the PRD is about and what the hard requirements are.
2. **Review** — perform an in-depth, comprehensive analysis of the PRD's quality, completeness, and engineering readiness.

The backbone of both outputs is a **numbered requirement inventory** (R1..Rn) that everything else references.

**This skill is read-only.** Do not write comments to Jira, edit Confluence pages, transition issues, create follow-up tickets, or modify any source material. Queries only.

**Document-type awareness.** This skill reviews any requirements document — a full Product Requirements Document, or a lean delivery/implementation doc (e.g. a **Delivery Requirements Document, DRD**) that deliberately scopes down to problem, solution, deliverables, and completion criteria. Judge the document against **what its own type needs**, not a fixed PRD checklist. A delivery/DRD-style doc intentionally omits target-user personas, business justification, market/adoption metrics, and user scenarios — **never report their absence as a gap, and never recommend adding them.** For such a doc, "complete" means the deliverables, acceptance criteria, constraints, and dependencies needed to implement the work are present and traceable. Detect the type from the document itself (its title, e.g. "Delivery Requirements Document"; whether it centers on a deliverable inventory and definition of done rather than personas and success metrics) — when unsure, ask the user which kind of document this is before reporting missing-section gaps.

## Input

The user has provided the following:

$ARGUMENTS

If no arguments were provided, use AskUserQuestion to ask:
- "Where is the PRD? Provide a file path, Jira/Confluence URL, GitHub issue URL, or paste the PRD text directly."

If an output file path was provided (second argument), write the review to that file. Otherwise, output the review directly in the conversation.

---

## Phase 0: Source Acquisition

Identify the source type and gather the PRD content.

### Markdown File / Document

Read the file. If it references other documents (links, file paths), read those too — they are likely supplementary context.

### Jira / Confluence

Use the local Atlassian toolkit (usage: `~/.local/bin/atlassian-toolkit/README.md`) to gather the PRD and its full context. All commands here are read-only. **Traverse exactly this set, then stop:**

1. **Root issue/page** — fetch it (`jira issue get <KEY> --description --comments` or `confluence page <id|url>`)
2. **Epic parent** — if the root is a story/task, fetch its parent epic
3. **Epic children** — fetch all children of the epic (`jira search 'parent = <epic-key>'`, or `jira search '"Epic Link" = <epic-key>'`)
4. **Linked Confluence pages** — `jira issue links <KEY>` on the root issue and its epic
5. **Confluence descendants** — `confluence descendants <id|url>` on any linked Confluence pages (one level of descendants)
6. **Comments** — read comments on the root issue and epic (`--comments` on `jira issue get`, or `jira issue comments <KEY>`)

**Stop rule**: one hop beyond the epic's children. Do not recursively traverse linked issues beyond the immediate epic family. If a linked item references further documents, note them in the source manifest but do not fetch them.

### GitHub Issue / PR

Use `ghtk issue get <number>` or `ghtk pr get <number>` to fetch the content (the local GitHub toolkit; stdlib, works in-sandbox; reference: `~/.local/bin/github-toolkit/README.md`). Check for linked issues, referenced PRs, and project board context. Read any referenced markdown files in the repository.

### Inline Text

Work with whatever was provided. Note in the review that context may be limited since there are no linked documents to cross-reference.

### Source Manifest

After acquisition, emit a manifest before proceeding:

```
### Source Manifest
**Read:**
- [list every document, issue, page that was fetched — with titles and keys]

**Referenced but not read:**
- [list items that were linked/mentioned but not fetched — with reason: out of scope, permission denied, dead link, etc.]
```

If the manifest shows significant unread references, warn that the review may be based on incomplete context.

---

## Phase 1: Requirement Extraction

### 1.1 Requirement Extraction Methodology

Before presenting the inventory, explain how you identified and organized requirements. Cover four topics in short subsections:

1. **How requirements were identified.** Name the types of source text that produce requirements (explicit behavioral statements, acceptance criteria, imperative specs like CLI command blocks or UI region tables). Give one concrete example of each type mapping to a requirement ID. State what is *not* extracted (motivation, rationale, architectural commentary).

2. **How requirements were classified.** Explain the MUST / SHOULD / UNCLEAR framework you applied internally to assess the PRD's language. Note which classifications dominated and why (e.g., the author wrote in imperative voice with acceptance criteria, so nearly everything is MUST). This classification informs the review analysis but does not appear as a per-requirement label in the inventory.

3. **How requirements were traced.** Explain the citation format, how dual-source requirements are handled (primary + secondary citation), and how complementary detail from multiple documents is merged into a single requirement.

4. **Grouping and numbering.** Explain the numbering scheme (sequential within topic groups that match the PRD's own section structure) and the splitting rule (split only when testable behaviors could ship independently).

### 1.2 Requirement Inventory

This is the load-bearing artifact. Extract every requirement from the PRD and its associated documents into a numbered, structured list grouped by topic area.

**Format each requirement as:**

```markdown
- **R1.** [One testable sentence stating the requirement]
  — *Document § Section name*
```

Group requirements under `###` subheadings that match the PRD's own sections (e.g., "### CLI chat agent", "### Tool gating"). This preserves reading order within groups while making the inventory scannable by topic. When two source documents contribute to the same requirement, cite both:

```markdown
- **R22.** Opening the drawer pre-loads the resource as context, shown as removable chip
  — *PRD § Web interface, acceptance criteria; Scratch § Page context injection, acceptance criteria*
```

**Citation format:**

- For markdown files: `filename:L42` or `filename:L42-L48` for ranges
- For Confluence pages: use an abbreviated document name + `§` + section heading (e.g., `PRD § Tool gating, acceptance criteria`)
- For Jira issues: `FUZZ-1234 description` or `FUZZ-1234 § field name`

**Rules for the inventory:**

- **One requirement per entry.** If a sentence contains multiple requirements, split them — unless the testable behaviors are not independently implementable (see splitting rule below).
- **Testable.** Each requirement must be stated so an engineer could write a test for it. "The system should be fast" is not testable; "API response time must be < 200ms at p95" is.
- **Splitting rule.** Split when testable behaviors could ship independently. Keep together when they can't — e.g., "change takes effect on next turn with no restart" is one requirement because you can't deliver the first without the second.
- **Citation.** Every requirement traces back to a specific location in the source material. No requirement should be inferred without attribution.

### 1.3 Plain-Language Summary

Produce a summary that a non-technical stakeholder could read and understand in under 2 minutes.

2-3 paragraphs explaining:
- What problem is being solved and for whom
- What the proposed solution is at a high level
- What changes from the user's perspective

Use plain language. No jargon. No implementation details. A product manager, a designer, and an engineer should all understand this identically.

### 1.4 Scope Boundaries

Briefly state:
- What is explicitly in scope
- What is explicitly out of scope
- What is ambiguously scoped (mentioned but not committed to)

---

## Phase 2: Comprehensive Review

Review the PRD across four dimensions, each mapped to a specific question. Reference requirement IDs (R1, R2...) throughout.

### Writing Style for Findings

**Write findings in natural prose, not label:value pairs.** Each finding should read like a paragraph a colleague wrote — with headers for scannability, but sentences for substance. The reader should be able to skim headers to find relevant findings, then read the body without mentally reassembling fragments.

**Under each finding's `####` heading, put a metadata line, verbatim:** `Severity: <Blocker | Important | Minor> | Confidence: <0-100> | State: <Conflict | Blocks tasking | Ambiguous | Missing | Strength>`. Severity, Confidence, and State are the reader's decision inputs — always shown on that line, never omitted. The heading names the consequence; the metadata line comes next; the prose body follows.

- Lead with impact — what's broken or blocked — before presenting evidence
- Group evidence so the contradiction or gap is visually obvious
- Use headers (`####`) for individual findings so they're scannable
- Avoid dense blockquote walls — use whitespace, bold, and bullet grouping for structure
- Keep quotes short and contextual — excerpt the relevant clause, not the whole paragraph
- **Include line numbers.** Every citation must include the source file and line number(s) so the reader can jump directly to the relevant text. Format as `filename:L42` or `filename:L42-L48` for ranges. For Jira/Confluence sources where line numbers aren't available, reference the section heading and field name instead.

### 2.1 What Makes Sense

Start with what's working. Identify:

- Requirements that are clear, specific, and implementable as-written
- Good constraints that prevent scope creep
- Well-defined acceptance criteria
- Smart scoping decisions
- Requirements that align well with each other

This section builds trust in the review — if you only point out problems, the reader discounts everything. Be specific about what's strong and why.

### 2.2 What Is Missing

Identify gaps in the document. For each gap, name the **concrete engineering consequence** — a gap without a named consequence is taste, not a finding. **Judge "missing" against the document's type** (see *Document-type awareness* above): a lean delivery/DRD-style doc omits personas, business justification, and user scenarios by design — for it, a gap is a missing deliverable, acceptance criterion, constraint, or dependency that blocks implementation, not a missing PRD section.

Check for (skip any the document's type does not call for):

- **Undefined failure/edge behavior** — the happy path is described but error and edge cases are absent where the requirements imply them
- **Missing error handling** — what happens when things fail?
- **Absent non-functional requirements** — performance, scalability, security, observability, data retention, compliance
- **Missing data models** — entities referenced but never defined
- **Unspecified API contracts** — integrations mentioned but interfaces not described
- **Missing migration/rollback plans** — how to get from current state to new state, and back if needed
- **Absent prioritization** — no indication of what to build first or what can be cut
- **Missing user personas or scenarios** — *(full PRDs only)* who specifically uses this, and how? A delivery/DRD doc omits this by design — **do not flag it.**
- **Undefined terms** — domain concepts used without definition
- **TBD / placeholder sections** — content promised but not delivered

**Format each gap as a headed section with natural language — not label:value pairs:**

#### Gap: [short title]

*Affects: R3, R7*

[1-3 sentences in natural prose explaining what the PRD doesn't address and why that matters for engineering. Lead with the impact — what an engineer can't do, estimate, or decide — then describe the missing content. Write this so someone skimming headers can get the gist, then read the body for detail.]

**What's needed:** [Concrete suggestion for what the PRD author should add — specific enough to act on, not just "add more detail."]

### 2.3 What Conflicts

Identify contradictions, ambiguity, and internal inconsistencies. These deserve a **high confidence bar** — only report conflicts you can demonstrate by citing two specific locations in the source material that disagree.

Check for:

- **Contradictory requirements** — R5 says X, R12 says not-X
- **Ambiguous language** — requirements that could be interpreted multiple ways, where the interpretation materially changes the implementation
- **Scope contradictions** — something is listed as in-scope in one place and out-of-scope in another
- **Assumption conflicts** — different sections assume different things about the system, user, or environment
- **Priority conflicts** — a requirement is marked MUST in one place and optional in another
- **Terminology inconsistency** — the same concept called by different names, or the same name used for different concepts

**Format each conflict as a headed section — lead with the impact, then present the evidence grouped clearly:**

#### Conflict: [short title]

[1-2 sentences summarizing what contradicts what and why it matters for implementation. This is the first thing the reader sees — make it immediately clear what the problem is.]

**The PRD says this is in-scope:**
- **[Section/document name]** — "[relevant quote]"
- **[Section/document name]** — "[relevant quote]"

**But also says it's out-of-scope:**
- **[Section/document name]** — "[relevant quote or description]"

*Adapt the evidence grouping to fit the conflict. For contradictory requirements, use "Location A says / Location B says." For scope conflicts, group by in-scope vs out-of-scope. For terminology conflicts, show the different terms used. The grouping should make the contradiction visually obvious.*

**Resolution needed:** [What the PRD author must decide, and if the evidence leans one way, say so.]

### 2.4 What Blocks Engineering from Creating Discrete Tasks

This is the most important section. For each requirement in the inventory, attempt to decompose it:

- **Name the task(s)** it would produce
- **State a testable done-condition** for each task

If you cannot do either, that requirement is a **blocker**. State specifically what information is missing.

Use a summary table for the overview, then expand on each blocker below it:

| Requirement | Status | Summary |
|-------------|--------|---------|
| R1 | Ready | Implement endpoint X returning Y |
| R2 | Blocked | No acceptance criteria |
| R3 | Blocked | Undefined auth mechanism |
| R4 | Partial | No error behavior specified |

Then for each blocked or partially blocked requirement, expand with a short paragraph:

#### R2: [requirement title] — Blocked

The PRD states [what R2 says] but doesn't define what "done" looks like. An engineer could implement this in multiple ways that all technically satisfy the text. Without acceptance criteria, code review becomes a negotiation about intent rather than a check against spec.

**To unblock:** [what the PRD author needs to add]

*Keep each blocker expansion to 2-4 sentences. Requirements marked "Ready" don't need expansion — the table row is sufficient.*

After all blockers, summarize:

- **Ready for tasking**: [count] requirements can be decomposed into tasks today
- **Blocked**: [count] requirements need clarification before engineering can proceed
- **Partially blocked**: [count] requirements can be started but have open questions

List the top blockers in priority order — the ones that, if resolved, would unblock the most downstream work.

---

## Output Structure

If writing to a file, use this structure:

```markdown
# PRD Review: [PRD Title]

**Reviewed:** [date]
**Source:** [file path, Jira key, URL, or "inline text"]
**Reviewer:** Claude (PRD Reviewer Skill)

---

## Source Manifest
[what was read, what was referenced but not read]

---

## Requirement Extraction Methodology
[How requirements were identified, classified, traced, and grouped — see Phase 1.2]

## Requirement Inventory
[R1..Rn structured list grouped by topic area]

## Part 1: Summary

### What This PRD Is About
[plain-language summary]

### Scope Boundaries
[in/out/ambiguous]

---

## Part 2: Comprehensive Review

### What Makes Sense
[strengths]

### What Is Missing
[gaps with engineering consequences]

### What Conflicts
[contradictions with citations]

### What Blocks Engineering
[decomposition table + blocker summary]

---

## Verdict

[1-2 paragraph overall assessment: is this PRD ready for engineering to start tasking? If not, what are the top 3 things the author should fix first?]
```

If outputting to the conversation, use the same structure but skip the file metadata header.

---

## After the review: ask what to do

Whether you wrote to a file or the conversation, do not stop silently. First print a one-line index of the findings so the choice is never buried:

```text
1. [Blocker · 95 · Conflict] R5 and R12 disagree on whether guest checkout is in scope
2. [Important · 82 · Missing] No error behavior for R4; engineers can't define done
```

Then use **AskUserQuestion** to let the reader choose what to do:

- **Explain one in depth** — expand a single finding.
- **List the top blockers** — show the priority-ordered unblock list again.
- **Write the review to a file** — save the full review to a path.
- **Nothing further** — done.

---

## Rules

1. **Read-only.** Never write to Jira, Confluence, or GitHub. No comments, no edits, no transitions, no new issues. Query tools only.
2. **Cite everything.** Every finding references specific requirement IDs and source locations. No unattributed claims.
3. **Name consequences.** A gap or conflict without a named engineering consequence is not a finding — it's an opinion. Every finding in sections 2.2-2.4 must state what becomes impossible or ambiguous for the implementing engineer.
4. **Strengths matter.** Section 2.1 is not optional filler. If the PRD is well-written, say so specifically. A review that only criticizes teaches the author nothing about what to preserve.
5. **Do not rewrite the PRD.** Suggest what to add or clarify, but do not draft replacement language. The reviewer's job is to identify problems, not to author solutions — that's the PRD owner's domain expertise.
6. **Bound your confidence.** For conflicts and defects in what IS written, hold a high bar — cite both sides of the contradiction. For gaps in what ISN'T written, a lower bar is appropriate, but every gap must name its engineering consequence.
7. **Acknowledge incomplete context.** If the source manifest shows unread references, be transparent about what you might be missing. A review that silently rests on partial context while presenting as comprehensive is dishonest.
