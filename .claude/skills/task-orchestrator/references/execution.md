# Execution reference

Detail for Stage 3 (orchestration loops) and Stage 4 (final review). `orch status` always
names the next unmet item; this document explains the why and the edge cases.

## The task gate checklist

`orch task accept T###` passes only when every item holds for the task's current attempt:

1. readiness verified (task-verifier) — pass
2. PM start check — pass
3. work by each author, in order; between authors a passing PM scope check; for code
   tasks a **checkpoint** before code-author's work: `red` (red-green — every red_green
   command fails) or `baseline` (characterization — every command passes)
4. (integration + `external_writes`) a dry-run, the human's `confirm`, then the executed write
5. green evidence **at the current snapshot** (red-green / characterization / test tasks)
6. standard gate **at the current snapshot** (when the workspace has standard commands)
7. PM scope check **at the current snapshot**
8. completion verification **at the current snapshot**, every acceptance criterion
   assessed and met with evidence
9. every required reviewer passes **at the current snapshot** with zero blocking findings
   (or the human waived those findings at this snapshot)
10. integrity scan **at the current snapshot**
11. PM acceptance **at the current snapshot**, citing the current scan digest

"At the current snapshot" is recomputed from the workspace at accept time, so any change
after an item was satisfied reopens it.

## Author sequences in practice

- **code (red-green):** test-author writes the tests from the task's test plan and runs
  `orch evidence T red` (every command must fail — for the right reason, which the PM and
  verifier judge from the logs) → PM scope check → code-author implements → (verifier runs
  green + gate).
- **code (characterization):** test-author pins current behavior, `orch evidence T baseline`
  (must pass) → PM scope → code-author refactors → green must still pass.
- **code (not-applicable):** code-author only; the plan justified why no test can express
  the change (e.g. a pure build-config change) and the PM audited it.
- **test:** test-author only; green at the end.
- **research:** the researcher's work report is the findings; doc-author then writes the
  deliverable from it (`orch brief T work --agent doc-author` refuses until the
  researcher's report exists). The researcher has a time budget; an interim report blocks
  the work step until it is acted on (see [Interim reports](#interim-reports-time-budgets)).
- **integration with external_writes:** liaison dry-run (`external_action: dry-run`) →
  `orch needs-human --kind external_write --task T --summary "<what will be written where>"`
  → the human types `/task-orchestrator resolve confirm T <notes>` → `orch resolve --action confirm`
  → resume the **same** liaison to execute (`external_action: executed`).
- **parallel_safe document tasks:** `orch task start` allows several at once in the same
  loop when their `expected_paths` are disjoint; each task's snapshot covers only its own
  paths. Dispatch their authors concurrently, but run reviewers within the concurrency
  budget below. The loop-exit PM check attributes every changed file to a task.

## Fix rounds (the review loop)

A failing verdict at the current snapshot — verification, any reviewer, green evidence, the
standard gate, or a PM scope check — starts a fix round:

1. `orch task round T###` (refuses when nothing is failing; escalates when the budget is used)
2. For each author whose area has findings: SendMessage the **same** agent the output of
   `orch brief T### fix --agent <author>`. Findings about tests go to test-author;
   production findings to code-author; run them in sequence, each followed by a PM scope check.
3. Re-run verification, then **every** required reviewer (the snapshot changed).

Budget: 3 verification/review passes per attempt (rounds 0, 1, 2). A failure at the last
pass stops at NEEDS_HUMAN (`review_budget`). Present: the remaining findings, the
disputes, your recommendation. The human chooses:

- `/task-orchestrator resolve continue T### [n] <notes>` — n more passes (default 3)
- `/task-orchestrator resolve waive T### <notes>` — accept the remaining findings as known
  issues (recorded; the PM stamp and final report must list them)
- `/task-orchestrator resolve retry T### <notes>` — abandon this attempt, start a new one

## Attempts and resolution guidance

A PM rejection (pm-accept fail) ends the attempt: `orch task fail T### --reason "<findings>"`,
then `orch task start T###`. The next attempt starts again at readiness; its briefs carry
the previous attempt's PM reports. Resume the same author unless the PM concluded the
approach itself was wrong.

After 3 failed attempts the task is BLOCKED. Write
`runs/T###/resolution.orchestrator.md`:

```markdown
# T### — resolution guidance

## What was attempted
One paragraph per attempt: approach, where it failed, the deciding evidence (report paths).

## Root cause
Why the attempts failed — the real cause, not the last symptom. Evidence.

## Options
For each: what changes, what it costs, what risk it carries, whether it needs a plan
revision. At least one option must meet the task as written; never propose lowering the bar
as the only way forward.

## Recommendation
The option you recommend and why.

## What the human must decide
The exact decision and the command for each choice.
```

Then `orch brief T### pm-resolution --agent project-manager`; revise until it passes;
`orch needs-human --kind task_budget --task T### --summary "<one line>"`; present the
guidance and stop. The human answers `/task-orchestrator resolve retry T### [n] <guidance
approved / adjusted>` (n more attempts, default 1) or `/task-orchestrator revise <plan change>`.

## Readiness failures

- **plan-defect** (criteria not objective, scope contradicts the plan, missing test plan):
  `orch deviation --summary "..."` → the human revises the plan.
- **environment** (tool missing, baseline gate failing, service unavailable):
  `orch needs-human --kind environment --summary "..."`.
- **dependency** (a dependency's output is missing): this is an ordering or acceptance
  defect — investigate the accepted dependency; if its acceptance was wrong, raise it with
  the human (`--kind readiness`).
- **missing-input**: answer from plan/research/decisions (`orch note`) and resume the
  verifier, or `orch needs-human --kind question`.

## Concurrency budget

`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` (10 in this setup) counts every running subagent,
including the sub-agents skills fan out to. Reviewer skills fan out 3–6 sub-agents each, so:

- run **reviewers sequentially** (one reviewer agent at a time);
- run at most **3 research agents** at once in planning;
- run at most **one author per workspace** (except parallel_safe document tasks);
- never run a verifier while an author is writing in the same workspace.

## Interim reports (time budgets)

The budget hook (every roster agent's frontmatter) records each agent's tool calls in
`.orch/agents/` and stops an agent at its first tool call past its budget —
`budgets.agent_minutes` in state: 30 active minutes for researchers and liaisons, no limit
for other roles. The stopped agent writes an interim report into the `interim/` folder
beside its report and finishes with status `interim`. An interim result never satisfies a
gate: the stage it belongs to stays unmet, and `orch status` shows `INTERIM — …` before
anything else.

1. `orch brief pm-interim --of <agent_id> --agent project-manager` → dispatch the PM. Its
   brief carries the agent's own brief (its scope), the interim report, and the command for
   the agent's tool-call log. It decides `continue` / `redirect` / `split` and
   `grant_minutes`.
2. `orch agent continue <agent_id>` refuses until that review exists, then records the grant
   and prints the message to SendMessage to the **same** agent.
3. For `split`, register the PM's remaining questions as new research items — they need
   the PM's research-plan approval like any other. `split` is for planning research only:
   in a task stage the PM's brief offers `continue` or `redirect`, `orch agent continue`
   refuses a split, and a task too big as planned becomes `orch deviation`.
4. Two extensions per agent (`budgets.time_grants`). The third attempt refuses: raise
   `orch needs-human --kind time_budget --agent <id> --summary "..."` and stop. The human's
   `resolve continue [minutes]` allows one more extension (their minutes when given, else
   the PM's); a reply (`resolve --action answer`) leaves the decision to their words.

## Pause and resume

- `orch halt` (the human's `/task-orchestrator halt`, or `touch <workflow>/HALT`) sets a
  pause: new dispatches are refused at once, running read-only agents are stopped at their
  next tool call (interim reports, reason `pause`), authors and planners finish their pass,
  and the Stop hook moves the workflow to HALTED at the end of the orchestrator's turn.
  `orch status` reports `safe to exit` once no agent is running.
- `orch resume` needs the human's typed `/task-orchestrator resume` after the halt. Paused
  agents resume with `orch agent continue <id>` — no PM review.
- A new session: `orch list` catalogs every workflow (`$TASK_ORCH_HOME/workflows/`), with its
  phase, last activity, driving session, agents that need attention, and next action.
  `orch bind <dir | workflow-id>` takes it over; it refuses when another session drove the
  workflow in the last 15 minutes unless `--take-over`. A `/task-orchestrator resume <dir |
  workflow-id>` typed in the unbound session is recorded in that workflow's ledger, so it
  counts for `orch resume` after the bind.
- Agents running when a session died show as `INTERRUPTED`: after `orch bind` from a new
  session their activity is from the old one, and after `claude -r` (same session id) the
  SessionStart hook (`source` resume/startup) closes their open segments and marks them.
  `orch agent continue <id>` acknowledges one and prints a resume message; SendMessage it to
  that agent id, or dispatch a fresh agent for the stage if that fails. The downtime never
  counts toward the agent's budget.
- A workflow created before workflow kinds and research items, still in PLANNING, is
  blocked (`UPGRADE NEEDED`; planning briefs refused) until the human types
  `/task-orchestrator upgrade <kind>` and the orchestrator runs `orch upgrade --kind <kind>`.
  The upgrade sets the kind, research items, and budgets; research gathered before it
  carries over; only a PM research check made after it counts; decisions.md records it.

## Final review

`orch final start` writes `final/changes-<workspace>.patch` (baseline → now). Required final
reviewers: code-reviewer, architecture-reviewer, test-reviewer when any code/test task
exists; doc-reviewer when any document-type task exists or documentation changed. Then
`orch gate run final --final`, final-verification (every FAC with evidence), pm-final,
`orch final accept`. Fix rounds: `orch final round` → resume the author of the affected
area (`orch brief --final final-fix --agent <author>`) → re-run what the snapshot staled.
Three passes, then NEEDS_HUMAN (`final_review_budget`: continue or waive).

## Human boundaries

| Phase / kind | Present | The human answers with |
| --- | --- | --- |
| AWAITING_APPROVAL | plan summary, index.md path, open questions | `approve` · `revise <feedback / answers>` |
| NEEDS_HUMAN `question` | the question, context, options | any reply (`orch resolve --action answer`) |
| NEEDS_HUMAN `readiness` / `environment` | the blocker and what would fix it | a reply (`answer`) · `resolve retry` |
| NEEDS_HUMAN `review_budget` | remaining findings + disputes, recommendation | `resolve continue|waive|retry T### ...` |
| NEEDS_HUMAN `task_budget` | the reviewed resolution guidance | `resolve retry T### [n] ...` · `revise ...` |
| NEEDS_HUMAN `external_write` | the exact dry-run request | `resolve confirm T### ...` |
| NEEDS_HUMAN `final_review_budget` | remaining final findings | `resolve continue|waive ...` |
| NEEDS_HUMAN `continuation_budget` | progress summary | `resolve continue ...` |
| NEEDS_HUMAN `integrity` | the integrity violation | a reply (`answer`) after they inspect |
| NEEDS_HUMAN `time_budget` | the agent's interim report and the PM's review | `resolve continue [minutes] ...` · a reply (`answer`) |
| PLAN_CHANGE_REQUIRED | the deviation and why | `revise <feedback>` |
| HALTED | where things stand | `resume` |
| DONE | the final report | `close` · `revise <feedback>` |

After `orch resolve`, the human's own words are appended to `decisions.md`; every later
brief carries them.

## Command reference

| Command | Who | What |
| --- | --- | --- |
| `orch init <location> --title T --kind K --workspace n=path --request-file F` | orchestrator | create, catalog, bind |
| `orch bind <dir \| workflow-id> [--take-over]` / `orch unbind` / `orch where` | orchestrator | session binding |
| `orch list [--all] [--json]` | orchestrator | catalogued workflows, most recent first (to pick one to resume) |
| `orch status [--task T] [--fast] [--json]` | anyone | next action / checklist (+ agents needing attention) |
| `orch validate [--for-approval]` / `orch plan-hash` / `orch render` | anyone / orchestrator | plan package |
| `orch research add --agent A --title T --questions-file F --done-when D [--context-file F] [--mode map\|investigate]` | orchestrator | register a focused research item (PROPOSED) |
| `orch research list [-v]` / `orch research drop R## --reason R` | orchestrator | research items |
| `orch brief [T] <stage> --agent A [--loop N\|--final] [--item R##] [--of AGENT_ID] [--mode] [--note \| --note-file]` | orchestrator | dispatch brief (`--item` for research, `--of` for pm-interim) |
| `orch agents [AGENT_ID] [--calls] [--all] [--json]` | anyone | agents: status, active minutes vs budget, tool calls |
| `orch agent continue AGENT_ID` | orchestrator | after an interim report (PM-reviewed for time stops) or an interruption |
| `orch submit` / `orch approve` / `orch revise` | orchestrator | planning → approval → execution |
| `orch loop open N` / `orch loop close N` | orchestrator | loop gates |
| `orch task start\|round\|accept\|fail T` | orchestrator | task transitions |
| `orch task diff\|scan\|status T` | anyone | task views |
| `orch evidence T red\|baseline\|green [--detach]` | test-author, task-verifier | CLI-run test evidence |
| `orch gate run standard\|final --task T\|--loop N\|--final [--workspace W] [--label L] [--detach]` | task-verifier, orchestrator | CLI-run gates |
| `orch wait <job> [--timeout S]` | anyone | collect a `--detach` run (default 540 s per wait) |
| `orch snapshot --task T\|--workspace W` | anyone | record a snapshot |
| `orch final start\|round\|accept` | orchestrator | final review |
| `orch needs-human --kind K --summary S [--task T] [--agent ID] [--report P]` | orchestrator | stop for the human |
| `orch resolve --action answer\|continue\|waive\|retry\|confirm [--grant N]` | orchestrator | apply the human's decision |
| `orch deviation --summary S [--task T]` | orchestrator | plan cannot be followed |
| `orch note "text" \| --file <path> [--title]` | orchestrator | append a clarification to decisions.md (`--file` for text with backticks or `$`) |
| `orch halt` / `orch resume` / `orch close` | orchestrator | human-driven lifecycle |
| `orch upgrade --kind K` | orchestrator | a workflow from before kinds/research items (needs the human's `/task-orchestrator upgrade K`) |
| `orch ledger [--task T] [--kind K] [--tail N] [--json]` | anyone | inspect evidence |
| `orch doctor` / `orch selftest [--check]` | orchestrator | installation checks |
