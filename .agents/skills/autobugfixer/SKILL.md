---
name: autobugfixer
description: Orchestration skill that runs an autonomous bug-fix loop — bug-hunter finds genuine bugs where change concentrated, the counselor selects at most 3 parallel-safe bugs with confidence >= 80 and independently verifies each one, a work branch is created, and task-pipeline plans and fixes the confirmed bugs while opening one Jira issue per bug. The only human involvement is a counselor escalation; work lands on a local branch and is never pushed. Use when the user invokes /autobugfixer or asks to automatically hunt, verify, and fix bugs end-to-end.
---

# Auto Bug Fixer

You are the orchestrator of an autonomous bug-fix run. You do not hunt, verify,
plan, or fix anything yourself — you chain three skills and hold the state of the
run between their hand-offs:

1. [bug-hunter](~/.agents/skills/bug-hunter/SKILL.md) — finds genuine,
   high-confidence bugs where change has concentrated.
2. [counselor](~/.agents/skills/counselor/SKILL.md) — selects what is worth
   fixing, independently verifies it, and is the sole escalation path to a human.
3. [task-pipeline](~/.claude/skills/task-pipeline/SKILL.md) — plans and executes
   the fixes and opens the Jira issues.

Run each skill through the Skill tool when available; otherwise read and follow
its `SKILL.md` at the path above with the resolved inputs. Their own boundaries
govern their work; yours is the hand-offs, the delegated gates, and the honesty
of the final report.

Two rules define the run:

- **Autonomy with one escape hatch.** The user started this run, so you answer
  task-pipeline's routine gates yourself and the counselor decides plan approval.
  A human is involved only when the counselor escalates — that is the single
  human-involvement path of the entire run.
- **Local only.** All work lands on a new local branch. Never push, never open a
  pull request.

## Inputs

- **Pipeline documents location** — the one required parameter: where
  task-pipeline creates its planning documents (its first argument). Missing?
  Ask for it before starting; that is the invocation, not a human gate.
- Optional, forwarded to bug-hunter: analysis window (`--since`, default
  `6 months ago`) and area budget (`--areas`, default 3).
- In delegated or chained use, accept these as resolved; do not re-ask.

## Requirements and Skill Boundaries

- Orchestrate only. Downstream skills own the analysis, verification, planning,
  and fixes; never do their work in this thread.
- Selection floor: a bug is workable only at confidence >= 80 **per the
  counselor's independent verification** — never on bug-hunter's score alone.
- At most 3 bugs, and they must be parallel-safe: fixes touch disjoint files and
  no shared contract (shared helper, schema, or configuration disqualifies
  pairing). Candidates that conflict are dropped, not queued.
- Do not create the branch or start task-pipeline unless at least one bug is
  confirmed by the counselor.
- Jira issues are created only through task-pipeline's own draft-and-publish
  path. Never hand-key issues with the Atlassian CLI from this skill.
- Commit locally on the work branch; never push, never open a PR.
- Every termination path — clean hunt, nothing verified, fixes landed, partial
  failure, escalation — ends in a report to the human. Silence is not an outcome.

## Core Skill Process

### 1. Verify the ground

- Confirm the working directory is a git repository
  (`git rev-parse --is-inside-work-tree`). Not a repo → stop and say so.
- Record the baseline: current branch, default branch, and
  `git status --porcelain`. Pre-existing uncommitted changes belong to the user —
  list them in the final report and never commit, stash, or discard them. If a
  confirmed bug's fix would need to touch a file with pre-existing modifications,
  that is a conflict → counselor (and, if it escalates, the human).
- Keep the pipeline-documents location for step 5; create nothing there yourself —
  task-pipeline owns that tree.

### 2. Hunt — run bug-hunter

Run [bug-hunter](~/.agents/skills/bug-hunter/SKILL.md) against this repository in
delegated mode: no interactive confirmations, default window and area budget
unless the inputs say otherwise. Forward the repo path, window, area budget, and
the note that this is a delegated, non-interactive run.

- **Findings returned** → hand the complete report — every finding with its
  confidence, evidence chain, and fix scope — to the counselor in step 3.
- **"No genuine issues found above the confidence threshold"** → a valid,
  valuable result. Skip to step 6 and report it plainly: which areas were hunted,
  over what window, and that nothing survived. No branch, no pipeline, no Jira
  issues, no apology.

### 3. Counsel — select and independently verify

Give [counselor](~/.agents/skills/counselor/SKILL.md) the full bug-hunter report
and exactly two requests:

**Request 1 — selection.** From the findings, identify **at most 3** bugs that:
(a) carry a confidence score **>= 80**; and (b) can be worked in parallel without
conflicting — disjoint fix files, no shared contract. Prefer the strongest
evidence and highest confidence; when two candidates share a file or a contract,
keep the stronger and drop the pairing. Fewer than three is a fine answer, and
"none qualify" is too.

**Request 2 — independent verification.** For each selected bug, verify from
scratch that it is an actual issue that needs fixing: re-read the cited code at
its current state, re-trace the failure path, hunt counter-evidence (guards
elsewhere, constraining callers, tests that already cover the case), and confirm
the fix scope is real and disjoint from the other selected bugs. Verdict per bug:
**confirmed** (the counselor still grades it >= 80), **downgraded** (now < 80 —
drop it), or **refuted** (not an issue — drop it, with the reason). The
counselor's verdict replaces bug-hunter's score for the rest of the run.

- **At least one confirmed** → continue.
- **Zero confirmed** → skip to step 6 and report honestly: what was hunted, what
  was selected, and why each candidate fell (downgraded versus refuted). Do not
  soften it — a refuted candidate is the process working, not a failure.

### 4. Create the work branch

Only now, with confirmed bugs in hand, branch from the default branch:

```bash
git switch <default-branch>   # only if not already on it
git switch -c autobugfixer/<YYYY-MM-DD>-<short-slug>
```

Derive the slug from the bugs' areas or the dominant file. Record the branch
name for the report.

### 5. Pipeline — run task-pipeline

Invoke [task-pipeline](~/.claude/skills/task-pipeline/SKILL.md) with its two
arguments: the pipeline-documents location from the inputs, and a request that
names each confirmed bug — file:line, evidence chain, counselor verdict and
confidence, fix scope, introducing commit when known — and instructs it to:

- plan and fix **all confirmed bugs**, test-forward, with parallel tasks writing
  disjoint paths;
- create **one Jira issue per bug** through its own draft-and-publish path —
  title, evidence, fix description, introducing commit — and record the returned
  issue keys;
- run its code review before any code task closes (its own standing rule).

**Answer the pipeline's human gates yourself, under the delegation:**

- **Scope confirmation** → confirm, recording that the run was user-initiated via
  `/autobugfixer` — the delegation is the authorization.
- **Plan approval** → give the plan to the counselor for review. Approved →
  record its answer verbatim and proceed. Rejected or needing refinement → feed
  its feedback back through the pipeline's revise path and re-present the revised
  plan to the counselor. Only the counselor's verdict moves the plan forward;
  never rubber-stamp it yourself.
- **Jira publish prompts** → authorize: issue creation for the confirmed bugs was
  pre-authorized by the user in this skill's contract.
- **Questions the approved plan already settles** → answer as manager, per
  task-pipeline's own rule, recording the answer and its basis in the plan.
- **Anything genuinely new, risky, or outside the plan** → take it to the
  counselor. If the counselor escalates → halt the pipeline cleanly, make no
  further changes, and go to step 6 carrying the escalation verbatim. This is
  the run's only path to a human.

Work then completes autonomously through closeout. **Never push.** Land local
commits on the work branch with messages matching repository conventions
(task-pipeline treats committing and pushing as the human's; this delegation
covers the commit, never the push). On partial completion — a fix that fails
review or testing — keep the successful fixes, leave the failed task's work
uncommitted or reverted per repo safety, and say exactly that in the report.

### 6. Report to the human

Whatever the outcome, report answer-first per the Output Formatting below:
bottom line, what was fixed and how it was verified, the Jira issue keys mapped
to each bug, the branch, and pre-existing changes left untouched. On partial
completion, say which fixes landed, which did not, and what remains open, with
the Jira issues that exist either way. If the run ended before the pipeline
started, report the hunt result and the counselor's verdicts — no noise about
work that never began. If the counselor escalated, present its escalation and
options verbatim; the next move is the human's.

## Output Formatting

```markdown
# Auto Bug Fixer — Run Report

**Branch:** <name> · **Pipeline docs:** <location>

## Bottom Line

[N bugs verified and fixed / nothing worth fixing / escalated — 2–4 sentences.]

## Fixed

### <bug headline — what was broken>
- **Jira:** <KEY>
- **Verified:** counselor confidence <N> — <one-line independent-verification note>
- **Files:** path:line[, ...]
- **Tests:** [test-forward coverage added]

## Not Worked

[Downgraded or refuted candidates with one-line reasons; or the hunt-empty note;
or "None".]

## Jira

| Bug | Issue | Status |
|-----|-------|--------|
| <headline> | <KEY> | fixed / open / partial |

## Escalation

[The counselor's escalation verbatim, its options, and the decision the human
must make — or "None".]

## Notes

[Pre-existing changes untouched; baseline test state; anything partial.]
```

Omit an empty section only with a stated reason ("Not Worked: none — all
confirmed bugs fixed"). A run that finds nothing, verifies nothing, and says so
cleanly is a successful run of this skill; a run that invents work to fill the
report is its failure.
