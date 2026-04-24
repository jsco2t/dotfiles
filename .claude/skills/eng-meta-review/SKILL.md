---
name: eng-meta-review
description: Multi-agent parallel code review orchestrator. Launches specialized review sub-agents (spec compliance, dead code, simplification, security, deferred work, fuzzball-specific) in parallel, then consolidates, deduplicates, verifies findings, and produces a final review document. Use when you want high-confidence, in-depth review of code changes.
argument-hint: "<output directory for review document> [files or scope to review] [-- additional context]"
---

# Engineering Meta-Review Skill

You are orchestrating a comprehensive, multi-agent code review pipeline. You will launch multiple specialized reviewers **in parallel**, gather their findings, deduplicate, verify each finding, filter by confidence, and produce a consolidated review document.

## Critical Rules

1. **NEVER simplify the review process.** Run ALL reviewers. Gather ALL results. Verify and distill to the final report.
2. **Run the ENTIRE pipeline without stopping** (unless you need direct user input). No intermediate status reports between phases. One final report at the end.
3. **Do depth analysis** to confirm each finding is a real issue before including it.
4. **Honest reporting is paramount.** It is perfectly acceptable — and valuable — to report that no significant issues were found. NEVER manufacture findings to prove the utility of this process. Conversely, ALWAYS report real issues even if the user seems frustrated.

## Input

The user has provided the following context:

$ARGUMENTS

You need these inputs. If any are missing, use AskUserQuestion to ask:

1. **Output directory** — where to save the review document. This should be a folder that has (or will have) an `index.md` file. Typically a `reviews/` folder within a feature documentation structure.
2. **Review scope** (optional) — specific files, directories, or a diff range to review. If not provided, you will determine the scope automatically (see Phase 1).
3. **Additional context** (optional) — extra instructions, focus areas, or background the user wants to provide. This may include requests for additional review focus areas beyond the defaults.

---

## Phase 0: Determine Review Scope

### Step 0.1: Identify the Parent Branch

If the user did not specify what to review, determine the diff automatically:

1. Get the current branch name: `git rev-parse --abbrev-ref HEAD`
2. Determine the parent branch using these heuristics:
   - Parse the current branch name. If it follows a pattern like `feature-123-some-detail`, check if a branch named `feature-123` exists (`git branch --list 'feature-123'` and `git branch -r --list '*/feature-123'`).
   - If a candidate parent branch exists, verify it by checking `git merge-base`: the merge-base of the current branch and the candidate should show the candidate's commits are ancestral.
   - If no candidate parent branch is found, fall back to `main`.
   - **If you are not sure which branch is the parent, ask the user via AskUserQuestion.** Do not guess.

3. Record the parent branch for diff generation:
   ```
   PARENT_BRANCH=<determined parent>
   ```

### Step 0.2: Gather Changed Files

Generate the list of changed files:

```bash
git diff $PARENT_BRANCH...HEAD --name-only
```

Also generate the full diff for the reviewers:

```bash
git diff $PARENT_BRANCH...HEAD
```

If the diff is extremely large (more than ~5000 lines), consider breaking it into logical groups by directory or package for the reviewers. Each reviewer should still see the full scope relevant to their focus area.

### Step 0.3: Classify the Changes

- Determine if **any Go files** (`.go`) are in the changeset. If yes, the `fz-code-reviewer` agent will be included.
- Identify the primary languages and file types in the changeset.
- Note the packages/directories affected — this helps scope each reviewer's work.

### Step 0.4: Gather Project Context

Look for spec/planning context to give to the Spec Compliance reviewer:

1. The output directory should be within a feature documentation structure. Check for a root `index.md` in the parent directory of the output directory (e.g., if output is `reviews/`, check `../index.md`).
2. If found, read it to locate the implementation plan, design document, and any Jira/Confluence links.
3. Read any existing review documents in the output directory to understand what has previously been reviewed and discovered. This avoids re-reporting known issues.

Record what you find:
```
SPEC_CONTEXT=<paths to spec documents and/or Jira links, or "none found">
PRIOR_REVIEWS=<summary of prior findings, or "none">
```

---

## Phase 1: Launch Parallel Review Agents

Launch ALL of the following review agents **simultaneously in a single message** using the Agent tool. Each agent runs independently and reports back its findings.

### Pre-launch: Load Review Skill Content

Before constructing any agent prompts, read the following skill files and hold their content for embedding:

1. **Read** `/Users/jscott/.claude/skills/fz-code-reviewer/SKILL.md` — this is the Fuzzball-specific reviewer methodology. Its full content (reviewer profiles, all 16 review responsibility sections, confidence calibration) must be embedded verbatim in Agent 1's prompt.
2. **Read** `/Users/jscott/.claude/skills/code-reviewer/SKILL.md` — this is the general code reviewer methodology. Its core review responsibilities section must be embedded in Agents 2–6 (and any additional agents) so each subagent operates with the full reviewer discipline, not just a focus-area brief.

These reads are mandatory. Do not rely on memory or partial recall of these files.

**Every agent prompt MUST include:**
- The diff scope (changed files list and the actual diff content)
- The core review methodology from the relevant skill file (fz-code-reviewer for Agent 1, code-reviewer for Agents 2–6)
- Their specific focus area brief (which narrows the general methodology to their assigned concern)
- The output schema (see below)
- Prior review context: if prior reviews exist (from Phase 0.4), include a summary: "Prior review findings in this folder: [summary]. Do not re-report issues that have already been flagged and addressed."
- This scope boundary instruction: "Focus your review on what has changed and what the changes directly impact. Do NOT treat this as an opportunity to go bug-hunting through unrelated code. If you trace an impact to unchanged code, that is in scope. If code is simply nearby but unaffected, it is not."
- This honesty instruction: "It is acceptable to find no issues. It is unacceptable to report non-issues just to appear productive. If you find nothing significant, say so."
- This reporting threshold: "Report ALL findings with confidence >= 50. The orchestrator will handle final filtering. This lower threshold allows aggregate signal from multiple reviewers to be captured during consolidation."

### Required Output Schema for Each Agent

Each agent must structure its findings as a markdown list. For each finding:

```markdown
### Finding: [Short title]
- **Confidence:** [0-100]
- **Severity:** [critical | high | medium | low]
- **File:** [file_path:line_number]
- **Category:** [agent's focus area name]
- **Description:** [Clear description of the issue]
- **Why it matters:** [Impact explanation]
- **Suggested fix:** [Concrete recommendation]
```

If no issues are found, the agent must explicitly state: "No issues found within this focus area."

---

### Agent 1: Fuzzball-Specific Review (CONDITIONAL — Go code only)

**Only launch this agent if Go files are in the changeset.**

Use `subagent_type: "feature-dev:code-reviewer"`.

Embed the **full content** of the fz-code-reviewer skill file you read in the pre-launch step. This includes all reviewer profiles (DevI and DevC patterns), all 16 review responsibility sections, and the confidence calibration. Do not summarize — include it verbatim.

Tell the agent:
- Review only the changed Go code and its direct impacts
- Apply the Fuzzball-specific review criteria
- Use the fz-code-reviewer confidence calibration (90-100 for proto/lock/logging issues, 80-89 for component/naming/transaction issues, etc.)
- Report findings with confidence >= 50 (the orchestrator handles final filtering)

### Agent 2: Spec Compliance Review

Use `subagent_type: "feature-dev:code-reviewer"`.

Prompt focus: **Spec Compliance** — verify the code changes implement what the specification requires, and don't implement things the spec doesn't call for.

Include in the prompt:
- The spec context gathered in Phase 0 (implementation plan path, design doc path, Jira/Confluence links)
- Instruct the agent to read the implementation plan and/or design document to understand what the spec requires
- If Jira/Confluence links are available, instruct the agent to fetch the current spec from those sources
- The agent should flag: missing spec requirements, implemented behavior that contradicts the spec, scope creep (code that implements things not in the spec), and spec ambiguities that the code resolves in a questionable way

### Agent 3: Dead/Legacy Code Review

Use `subagent_type: "feature-dev:code-reviewer"`.

Prompt focus: **Dead and Legacy Code Detection** — if the change is removing or refactoring something, ensure no dead code is left behind.

Include in the prompt:
- Look for: unused functions, unreferenced variables, orphaned imports, stale comments referencing removed code, unused type definitions, dead branches in conditionals, legacy code paths that are no longer reachable after the change
- Use `grep` and code navigation to verify whether seemingly-dead code is actually unreferenced
- Check if removed/refactored code had callers elsewhere that now reference nothing
- Flag any code that was clearly part of the old implementation but wasn't cleaned up

### Agent 4: Code Simplification Review

Use `subagent_type: "feature-dev:code-reviewer"`.

Prompt focus: **Code Simplification** — within the scope of changed code, look for opportunities to simplify.

Include in the prompt:
- "Simpler" means: solutions that are just as robust and capable but easier to maintain and test
- Look for: over-engineering, unnecessary abstractions, complex control flow that could be flattened, duplicated logic that could be consolidated, verbose patterns where idiomatic alternatives exist, unnecessary intermediate data structures
- Do NOT flag simplifications that would reduce capability or robustness
- Do NOT suggest premature abstractions — three similar lines is better than a premature abstraction

### Agent 5: Security Review

Use `subagent_type: "feature-dev:code-reviewer"`.

Prompt focus: **Security Posture** — look for places where the change weakens security or creates vulnerabilities.

Include in the prompt:
- Look for: weakened authorization checks, removed or bypassed authentication, exposed internal APIs, SQL injection vectors, command injection, path traversal, insecure defaults, secrets in code, overly permissive CORS/RBAC, missing input validation at system boundaries, information leakage in error messages
- Check if the change removes or weakens any existing security controls
- Check if new endpoints or APIs are properly protected
- Flag any `InsecureSkipVerify`, hardcoded credentials, or disabled security features that aren't clearly documented as temporary with a tracking ticket

### Agent 6: Deferred Work Review

Use `subagent_type: "feature-dev:code-reviewer"`.

Prompt focus: **Deferred Work Detection** — work is NEVER to be deferred with silent code comments.

Include in the prompt:
- Search the changed code for: `// TODO`, `// FIXME`, `// HACK`, `// XXX`, `// LATER`, `// TEMPORARY`, `// PLACEHOLDER`, or any similar deferred-work markers (case insensitive)
- For each found marker: the gap in functionality IS the finding. Assess how severe the gap is — is this a missing error handler, an unimplemented feature, a skipped validation?
- Also look for: empty function bodies with just a comment, stub implementations that return nil/zero without doing real work, commented-out code blocks that suggest incomplete migration
- Severity guidance: a TODO on a non-critical path is medium; a TODO on an error handler or security check is critical

### Additional Agents (from user context)

If the user's additional context requests extra focus areas, create one additional Agent per focus area using the same structure. Use `subagent_type: "feature-dev:code-reviewer"` and adapt the code-reviewer methodology to the requested focus.

---

## Phase 2: Consolidate Findings

After ALL agents have completed and returned their reports:

### Step 2.1: Collect All Findings

Parse each agent's report and extract all individual findings into a unified list. Preserve the original confidence scores, severities, and categories.

### Step 2.2: Deduplicate

Identify duplicate or overlapping findings:
- Same file and line number with similar description → keep the one with higher confidence and richer detail
- Same conceptual issue reported by multiple agents at different granularity → merge into one finding, note which reviewers flagged it (this reinforces confidence — if 3 independent reviewers flagged the same thing at 65 each, that's a strong aggregate signal; boost the merged finding's confidence accordingly)
- Near-duplicates where one agent found a symptom and another found the root cause → keep the root cause, incorporate the symptom description

### Step 2.3: Pre-filter

Remove any finding with confidence < 50 before the verification pass. The subagents report at >= 50 threshold; the final >= 80 filter is applied AFTER verification in Phase 3. This preserves aggregate signal from multiple reviewers who independently flagged the same issue at moderate confidence.

---

## Phase 3: Verification Pass

Launch ONE more Agent (using `subagent_type: "feature-dev:code-reviewer"`) to verify the consolidated findings.

The verification agent's prompt must include:
- The full list of deduplicated, pre-filtered findings
- The diff and changed files
- Instructions to: read the actual code at each reported location, determine if the finding is a real issue or a false positive, adjust confidence scores based on verification, and remove any finding that is not actually an issue
- The agent must explain WHY it kept or removed each finding
- The honesty instruction: "If all findings turn out to be false positives, report that. An empty verified list is a valid and valuable outcome."

### Step 3.1: Apply Verification Results

- Remove any finding the verification agent determined is not a real issue
- Update confidence scores based on the verification agent's assessment
- Apply the final confidence filter: drop anything with verified confidence < 80

---

## Phase 4: Write the Review Document

### Step 4.1: Read Existing Index

Read the output directory's `index.md` to understand the existing format and naming conventions.

### Step 4.2: Write the Report

Create the review document at `<output-directory>/meta-review-<YYYY-MM-DD>.md` (use today's date; if a file with that name exists, append a sequence number: `-02`, `-03`, etc.).

Structure:

```markdown
# Meta-Review: [Branch Name]

**Branch:** [current branch]
**Parent Branch:** [parent branch used for diff]
**Date:** [ISO 8601 timestamp with MST offset]
**Changed Files:** [count]
**Reviewers Run:** [list of review agents that were launched]
**Prior Reviews Consulted:** [list or "none"]

---

## Summary

[2-3 sentence executive summary. State clearly whether significant issues were found or not. Do not hedge — be direct.]

---

## Findings

[If no findings survived the pipeline, write:]

> No issues with confidence >= 80% were identified in this review. The changes were examined for spec compliance, dead code, simplification opportunities, security impact, and deferred work. [Add any other focus areas that ran.] This is a clean review.

[If findings exist, group by severity:]

### Critical

[Findings with severity: critical, ordered by confidence descending]

#### [Finding Title]
- **Confidence:** [score]
- **Severity:** Critical
- **File:** [file_path:line_number]
- **Reviewers:** [which review agents flagged this]
- **Description:** [description]
- **Impact:** [why this matters]
- **Recommended Fix:** [concrete suggestion]

### High

[Same structure]

### Medium

[Same structure]

---

## Review Pipeline Summary

| Reviewer | Focus Area | Findings (raw) | Findings (after dedup + verify) |
|----------|-----------|-----------------|-------------------------------|
| fz-code-reviewer | Fuzzball-specific patterns | [n] | [n] |
| Spec Compliance | Specification adherence | [n] | [n] |
| Dead Code | Unused/orphaned code | [n] | [n] |
| Simplification | Complexity reduction | [n] | [n] |
| Security | Security posture | [n] | [n] |
| Deferred Work | TODO/FIXME markers | [n] | [n] |
| [any extras] | [focus] | [n] | [n] |
| **Verification** | **False positive removal** | **[total in]** | **[total out]** |

---

## Files Reviewed

[List all changed files, grouped by directory/package]

---

## Methodology

This review was conducted using the eng-meta-review pipeline:
1. Parallel specialized review agents examined the changes from independent perspectives
2. Findings were consolidated and deduplicated across reviewers
3. A verification agent confirmed each finding against the actual code
4. Findings below 80% confidence were filtered out
```

### Step 4.3: Update the Index

Read and update `<output-directory>/index.md`. Add a row to the documents table:

```markdown
| [`meta-review-<date>.md`](meta-review-<date>.md) | Multi-agent meta-review of [branch name] — [n] findings ([severity breakdown or "clean review"]) | [ISO 8601 timestamp] |
```

Match the existing table format exactly.

---

## Phase 5: Terminal Report

Present a concise summary to the user:

1. **Branch and scope** — what was reviewed, against what parent
2. **Reviewer count** — how many agents ran
3. **Results summary** — total findings by severity, or "clean review"
4. **Top findings** — if any exist, list the top 3 by severity/confidence with file locations
5. **Document location** — path to the full review document

Keep this terminal output short. The full details are in the written document.

---

## Error Handling

### If an Agent Fails or Times Out

- Note which agent failed in the final report
- Continue with results from the agents that succeeded
- Do NOT re-run the failed agent unless the user asks
- Mark the failed focus area as "not reviewed" in the pipeline summary table

### If No Changed Files Are Found

- Inform the user that no changes were detected between the current branch and the parent
- Ask if they want to specify a different comparison range
- Do NOT write an empty review document

### If the Output Directory Doesn't Exist

- Create it, along with an `index.md` following the standard format:
  ```markdown
  # Reviews Index

  **Parent:** [../index.md](../index.md)
  **Last Updated:** [ISO 8601 timestamp with MST offset]

  ---

  | Document | Description | Created |
  |----------|-------------|---------|
  ```
