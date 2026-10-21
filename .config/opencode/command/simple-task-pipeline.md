---
description: >-
  Task pipeline — plan, get human approval, then autonomously execute a substantial piece of work
  (code, docs, KB articles, tutorials, research, Jira/GitHub epics) entirely in the main session,
  without subagents. Usage: /simple-task-pipeline <location for planning docs> <request> |
  /simple-task-pipeline resume <workflow dir> | /simple-task-pipeline halt |
  /simple-task-pipeline status <workflow dir>
---

# Simple Task Pipeline (OpenCode)

You perform the entire pipeline in the **main agent's context**: scope with the human, research,
write the plan, implement each task, review the work, fix findings, and report the outcome.
**Never launch or resume subagents, call the `task` tool, or delegate any part of this workflow.**
Work sequentially, including research and review. When using another skill, apply its relevant
instructions and review lenses yourself; disable delegation with `--max-agents=0` where supported.
If a skill requires delegation, perform the equivalent work directly instead.

Use the existing `tp.py` for persistent state, validation, approvals, briefs, checks, and reports:

```bash
python3 ~/.config/opencode/tools/task-pipeline/scripts/tp.py -w <workflow dir> <command>
```

`tp <command>` below means exactly that line; spell it out in every Bash call (zsh does not
word-split a variable). **Run `tp next` after every step** and interpret its actions using the
local execution rules below.

## Script compatibility: every dispatch is local work

The shared tool uses agent terminology and prints instructions intended for `/task-pipeline`.
For this command, apply these translations everywhere, including briefs and error messages:

- **Roster and participants** identify work roles and review lenses that **you** perform.
  Keep catalog-supported names in `scope.json`, task `agent` fields, and research items because
  validation requires them. They do not represent separate agents or sessions. Do not invent a
  `main` agent name; use `tp roster suggest --kinds <kinds>` to select valid role labels.
- **Dispatch** means prepare one local step: run `tp dispatch <id>` for **one id only**, read
  the brief at the printed path, and perform it yourself. Ignore the printed `send: task(...)`
  line, agent/model selection, and requests to send or resume an agent. Do not dispatch another
  id while any step is in flight.
- **Result / hand-back** means write the JSON result yourself at the exact path and with the
  schema in the brief. Then run **`tp record <id>` without `--agent-id`**. The flag is optional;
  never fabricate an agent or session id. Fix malformed or oversized result files yourself
  before recording again. The brief's `RESULT <path>` reply is an internal convention, not a
  reason to end your turn or omit a useful update to the human.
- **Fix / resume / verify** means read the new brief, prior results, findings, and recorded
  decisions and do the next pass yourself. After `tp resolve`, check whether the script has
  already put the step back in flight; if so, continue its existing brief and result path
  without dispatching it again.
- **Wait / in flight** means a local step is unfinished, not that a background agent exists.
  Inspect `tp status --json`, finish or recover that step, record it, and continue. Never end
  your turn to wait for an agent hand-back that cannot arrive.
- **Timing** is reporting metadata. The shared tool can estimate parallel execution; report
  your own sequential estimate at scope and approval. Do not compress or omit work to fit an
  estimate. Keep genuine validation, write fences, approval gates, and retry limits intact.

Briefs may still name `/task-pipeline`, call you an agent, or address a manager. Apply their
task contract, sources, write paths, checks, and result schema in this same context. This
command's prohibition on delegation overrides their execution and messaging instructions.

## Parse the arguments: `$ARGUMENTS`

The first word selects the mode; the rest are positional arguments.

- **`resume`** — the workflow directory ($1). Skip to _Halt, resume, status_.
- **`halt`** (or `hault`) — no arguments. Use the active workflow directory from this session;
  ask if it cannot be determined. Skip to _Halt, resume, status_.
- **`status`** — the workflow directory ($1). Run `tp status`, present it answer-first, and stop:
  for looking at a workflow from outside without driving it (mid-run "status?" is not this mode).
- **Anything else** — a new pipeline: **$1 is the location** for the planning documents (ask if
  missing); **everything after it is the request**, verbatim including quoting (ask if missing).

Ask for a missing workflow directory in resume or status mode. For a new pipeline, start at Stage 1.

## Execution rules

1. **Only the human decides** scope, work roles/review lenses, plan approval, and anything off
   the plan. Ask with the `question` tool; record their words verbatim (`--answer` / `--feedback`).
2. **One local step at a time.** You perform all research, tests, implementation, reviews,
   fixes, and verification. No background workers or separate agent contexts.
3. **Structured files preserve progress.** Read briefs and write their result JSON yourself.
   Read only the part you need: `tp show <id> --part …`, `tp schema <name>`.
4. **The approved plan is the contract.** Outside it: `tp note "<one line>"`; blocking:
   `tp exception --summary "..."` and a question. Honor write paths and read-only workspaces.
5. **Script before judgment.** If a command can decide it, a command decides it.
6. **Answer-first** (`~/.config/opencode/output-styles/answer-first-core.md`, inlined into every
   brief) for everything you write.
7. **Separate doing from checking.** After writing a result, inspect the actual source, diff,
   and check output before accepting it. During a review step, do not edit deliverables; write
   findings and route fixes through the pipeline. Describe reviews honestly as self-review.

## When tp.py rejects research questions

`tp research add` enforces hard caps: at most **3 questions per item**, each **under 40 words**
(whitespace-split — every absolute path eats the count), and `map`/`requirements` questions may not
ask for content (`all/every files|lines|…`, `exhaustive`, `end-to-end`). It fails with all problems
at once, so fix every question before re-running. When the questions will not fit:

- **Split into more items, never into compound questions** — more `R<n>` items, each with its
  own purpose and time box, performed sequentially by you.
- **Move detail into a referenced file.** Stay under 40 words by pointing at a file you wrote in
  the workflow dir, e.g. `Group the notes per the rules in <wf>/research/R1-q1.md; output each
  batch's name and dominant repo paths.` Read those referenced files when executing the item.
- **Cut words honestly.** Drop articles and hedging, prefer repo-relative paths, and split
  two-clause questions in two.

## Stage 1 — Scope and budget metadata (one round with the human)

1. Save the request verbatim to a file, then run `tp init <location> --title "<title>"
   --request-file <file> [--budget <minutes>]`. It creates the workflow's own
   `<location>/<date>-<slug>/` folder and prints it: that is `-w` from then on.
2. **Size it yourself first**, in ten minutes or less: `tp survey <repo> --name <ws>` per
   repository; `tp survey-issue jira:KEY` or `gh:owner/repo#N` for a named issue. It prints
   children, thin issues, links, and a starting-point research estimate.
3. **Judge the research.** A clear, bounded ask needs none — plan directly. Research earns its
   cost when details are missing or the work is large; if unsure how much, ask.
4. **Choose work roles and review lenses critically.** `tp roster suggest --kinds <kinds>`.
   Keep only roles with a direct bearing on the output; prefer specific review lenses
   (correctness, security, api-compat, test) over broad ones. Explain that all are performed by
   the main agent. Retain required author, tests, and research roles for schema validation.
5. **One `question` call** (at most 4 questions) covering the output (kind, format, where),
   work roles/review lenses (multiple choice, several allowed), review (`none` or `final`), and
   any conventions/policies the work must honor (a workflow-dir file listed in `conventions`:
   they freeze with the plan and reach every brief). **Never ask the human to approve or pick
   a time budget** — size sequential budgets yourself as reporting metadata; never cut work
   to fit one.
6. Write `scope.json` (`tp schema scope`), `tp scope check`, show the human the key lines of
   `scope.md`, and confirm (`question`: Confirm / Change): `tp scope confirm --answer "..."`.

## Stage 2 — Research (sequential, within the agreed scope)

- Each item is one local research step, at most 3 narrow questions, a box of 15 minutes or
  less, and a purpose: `map`, `requirements`, or `investigate`:
  `tp research add R1 --agent <approved role label> --purpose <p> --questions-file <f>
  --done-when "..." [--minutes N]` (rejected questions: see above).
- `tp dispatch R1`, read the brief, investigate its questions yourself, write its research
  result JSON, fact-check one answer against its evidence, then `tp record R1`. Complete this
  item before dispatching another. Research does not write the final deliverables.
- **Followups** go in the result; decide each: `tp research add … --from R1.F2`, or
  `tp research dismiss R1.F2 --reason "..."`. Submit refuses while any is undecided.
- Out of budget is not a stop: add items freely within scope; each keeps its ≤15-min box.
  `tp research extend --minutes N --note "..."` grows the reporting budget.

## Stage 3 — Plan (you write it)

- **Planning maps the work; it never does the work.** One task per area, article, or unit, about
  15 minutes (30 at most), 1–6 objective acceptance criteria, a brief of 150 words or less.
  Tasks cite findings as sources: `research:R3`. Use approved catalog role labels for `agent`.
- **Paths name the repo files the task writes.** Never `.` or a bare `**` — plan check refuses
  catch-alls and >200-file expansions. Name each file, optional ones too; a directory path only
  when its files exist at plan time.
- All tasks run sequentially. Use `depends_on` for actual dependencies; shared files such as
  `index.md` can belong to one integration task. Keep paths precise even without parallel work.
- Code is test-forward: `test_cmd` (the task's package, not the whole suite) and `tests_paths`.
  Preserve the separate tests and implementation steps enforced by the script.
- `docs` is a built-in task check; `docs-all` a built-in final check. Define repo commands in `checks`.
- With `review: final`, split packages over 10 tasks into `review_batches`; perform all batches
  and lenses yourself in sequence.
- `tp plan check` until clean, then `tp plan submit`. `tp next` warns once planning passes 45 min.

## Stage 4 — Approval

Give the human ten lines or fewer: tasks, sequential time against the budget, self-review
passes, questions, and noticed items, with the path to `plan.md`. `question`: Approve / Revise.
Then `tp approve --answer "..."` or `tp revise --feedback "..."` — never approve without their answer.

## Stage 5 — Execute (autonomous, in the main context)

If this machine or repo has known breakage the plan did not cause, run `tp baseline` once right
after approval: `tp final` reports those failures as pre-existing instead of blocking on them.

Loop on `tp next`, finishing any in-flight local step before starting another:

- **dispatch / fix / review** → choose one ready id, `tp dispatch <id>`, read its brief, and do
  the work yourself. For code: tests-only first (observe the expected red or pinned green),
  record that step, then implement in the separate implementation step without editing tests.
- **Local step finished** → write the result JSON at the brief's exact path, inspect what you
  wrote, then `tp record <id>` with no agent id. For backend stalls, add `--dead-minutes N`
  (`tp clock <id> --dead-minutes N --note "..."` corrects one already recorded).
- **Time reports, never gates.** The meter (net of dead clock) shows in `tp next`, `tp digest`,
  and the report; nothing is refused for being over budget and no work is compressed to fit one.
- **Present a digest at a reasonable interval** — after a completed task or review pass:
  `tp digest`, shown answer-first. Narrate decisions and results; let the digest carry status.
- **Mechanical corrections batch.** Widen a write set (`tp widen <id> --path <file> --reason
  "..."` — allowed even after acceptance; refuses paths a live task owns) and fix checks
  (`tp amend --reason "..."`) in one call per round; ask the human **once per round** if at all.
- **check** → fact-check the printed sample (does each cited line say what the sentence claims?
  for code, read the diff and review it), then `tp accept <id> --note "..."` or
  `tp reject <id> --reason "..."`. A rejected task is a local fix round: dispatch it, read the
  fix brief, make the corrections yourself, write its new result, and record again.
- **A noticed item the task's own acceptance depends on routes, it does not rest** — at the
  next `tp next`, widen the task, amend the plan, or record a follow-up. Do not leave acceptance
  gaps as noticed lines while claiming the task is complete.
- **triage** (after end-of-pipeline self-review) → `tp show <id> --part blocking`, verify each
  against the source, then `tp triage <id> --accept-all`, or `--dismiss F# --reason "..."` and
  `--assign F#=T##`. When triage points at a parked patch (`runs/<id>/*.patch`), verify and adopt
  it in the owning task's fix round. Verify fixes yourself in the later verification step.
- **human** → stop, ask with `question`, then
  `tp resolve [--task <id> | --review <id>] --action … --answer "..."`. A needs_input question
  that scope, plan, or decisions already settle, answer yourself. Apply any printed continuation
  locally; do not send its agent message.
- **wait** → inspect the unfinished local step and complete or recover it using the rules
  below. There is no background worker to wait for.
- **A status question mid-run** ("status?", "how's it going?") → `tp digest`, present it
  answer-first, then `tp next` and **keep working in the same turn**. Work stops for a human
  decision, an explicit halt, or completion.
- **An interruption or restart** → read the saved scope, plan, decisions, current brief and
  results, and inspect workspace edits before continuing. Do not repeat a dispatch for a step
  already in flight. Finish its existing contract and record it. If a task step cannot safely
  continue, `tp lost <task id> --summary "..."`, resolve, and dispatch it locally again; honor
  retry limits. `tp lost` handles task ids, not research ids or batch review ids. For interrupted
  research or review, continue the existing brief and result file; if genuinely blocked, report
  the problem to the human instead of altering internal state or pretending it succeeded.
- **A step far past its estimate** → inspect progress, keep commands short-returning (the
  supervisor kills ~35 min of silence), and raise `tp exception --task <id> --summary "..."`
  for a blocking task issue. Use the task's package tests, not the whole suite.

## Stage 6 — Closeout, then final

When `tp next` says **closeout** (all tasks and reviews done): `tp closeout` lists every noticed
item; classify each — `tp closeout --item N --class deferred|followup|observation --note "..."`.
A deferred or follow-up note is required and is what the human reads: plain language naming the
issue and its consequence ("admission-webhook.yaml keeps a non-atomic write path; a crash mid-write
tears the file the apiserver reads") — never a bare file path. Then `tp closeout --ask` renders the
decision brief; put it in one `question` (accept the deferral / file follow-up tasks / extend the
run) and `tp closeout --decide --answer "<their words>"`. `tp final` then runs the checks (baseline
failures report as pre-existing) and writes `report.md` with honest Deferred / Follow-ups /
Observations lists; present it answer-first and identify reviews as self-review. If `tp next`
goes directly to **final**, run `tp final`. Committing and pushing are the human's call.

## Halt, resume, status

- **Halt mode** (`/simple-task-pipeline halt`, or `hault`) → `tp halt --reason "<their words>"`.
  Nothing new starts. If a local step is in flight, save its progress and record it at a safe
  boundary before stopping. For a task that is unfinished, use its brief's `blocked` result
  with an honest summary rather than claiming `done`; for research/review, finish the bounded
  current pass and record its actual findings. If that cannot be done safely, stop immediately
  and report that halt is pending with the saved brief/result paths. Do not start another step
  to finish halting. Once no step is in flight, the tool writes `halt.json` recording where work
  stopped and what runs next. Tell the human, stop.
- **Resume mode** (`/simple-task-pipeline resume <dir>`) → `tp status`; if halted or halting,
  `tp resume --answer "<their words>"`; then read saved scope, plan, decisions, and active
  brief/results, inspect workspace edits, and run `tp next`. Recover unfinished local work as
  described in Stage 5. Continue every remaining step yourself, regardless of role labels or
  old agent ids printed by the tool. Never resume a separate agent session.
- **Status mode** (`/simple-task-pipeline status <dir>`) → report `tp status` answer-first and
  stop without advancing the workflow.
- **Unattended runs** need sandbox-writable workflow and write workspaces, and
  `Bash(python3 ~/.config/opencode/tools/task-pipeline/scripts/tp.py:*)` allowed in `permission`.
  Human scope, plan, exception, and closeout decisions still apply.

## Special Instructions

### Coding Related Tasks

- **Always** be test forward with code changes.
- **Always** review code before considering a unit of work done, even if smaller reviews
  happened during coding. Apply relevant review lenses yourself in this main context; do not
  invoke a review workflow that launches subagents. A final review, when agreed, checks the
  combined change after all tasks are accepted.
