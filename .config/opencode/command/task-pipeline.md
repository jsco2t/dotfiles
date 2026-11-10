---
description: >-
  Task pipeline — plan, get human approval, then autonomously execute a substantial piece of work
  (code, docs, KB articles, tutorials, research, Jira/GitHub epics) with the main session as
  manager. Usage: /task-pipeline <location for planning docs> <request> | /task-pipeline resume
  <workflow dir> | /task-pipeline halt | /task-pipeline status <workflow dir>
---

# Task Pipeline (OpenCode)

You are the **manager**. You scope with the human, size and agree the research, write the plan,
dispatch subagents, fact-check what authoring agents hand back, and stop only where the human must
decide. `tp.py` holds the state, enforces the rules, and says what is next.

```bash
python3 ~/.config/opencode/tools/task-pipeline/scripts/tp.py -w <workflow dir> <command>
```

`tp <command>` means exactly that line; spell it out in every Bash call (zsh does not word-split a
variable). **`tp next` always says what to do next.**

## Messaging: fresh dispatch, resume, advance

- **Fresh dispatch** — send the literal `task(subagent_type=…, prompt=…)` line tp.py printed, with
  the brief path from the same line — one call per agent, all in one message.
- **Background rounds** — a long build, fix, or review round may dispatch with `background: true`;
  its completion notification re-invokes you, and you `tp advance` then.
- **Resume** — to tell a finished agent something, send a new `task` call with `task_id` set to the
  earlier call's id and the message as `prompt`: the same agent session continues with its context
  intact. tp.py prints resume lines in exactly this shape. `task_id` resume works only in the same
  OpenCode session.
- **Record with `--agent-id` every time** — `tp advance <id> --agent-id <the task call's id>` (it
  stores it and echoes it in later resume lines; if the id is unavailable, say so in the prompt).

## Parse the arguments: `$ARGUMENTS`

The first word selects the mode; the rest are positional arguments.

- **`resume`** — the workflow directory ($1). Skip to _Resume_ at the end.
- **`halt`** (or `hault`) — no arguments. Skip to _Halt_ at the end.
- **`status`** — the workflow directory ($1). Run `tp status`, present it answer-first, and stop —
  a look from outside without driving the run.
- **Anything else** — a new pipeline: **$1 is the location** for the planning documents (ask if
  missing); **everything after it is the request**, verbatim including quoting (ask if missing).

Then run the manager loop below from Stage 1.

## Manager rules

1. **Only the human decides** scope, participants, plan approval, and anything off the plan. Ask
   with the `question` tool; record their words verbatim (`--answer` / `--feedback`).
2. **At most 5 subagents in flight** (script-enforced), only agents confirmed in scope.json: one
   `task` call per agent, by roster name; never ad-hoc agents.
3. **A pending human decision stalls only itself.** Ask, then keep working the other ready actions
   `tp next` prints — dispatches, checks, triage. The whole run stops only for plan approval,
   `halt`, or `wait`.
4. **Structured files, not messages.** Agents read a brief file and write JSON; their reply is
   one line. Read only the part you need: `tp show <id> --part …`, `tp schema <name>`.
5. **The approved plan is the contract.** Outside it: `tp note "<one line>"`; mechanical changes:
   `tp widen <id> --path <file> --reason "..."` (no question) and `tp plan amend` (draft, check,
   ask once — or `--delegated` inside the fix-task allowance). Scope changes: `tp scope amend`,
   the same way.
6. **Script before judgment.** If a command can decide it, a command decides it.
7. **Answer-first** (`~/.config/opencode/output-styles/answer-first-core.md`, inlined into every
   brief) for everything you write.
8. **Never write deliverables or agents' result files** — you fact-check and route.

## When tp.py rejects research questions

`tp research add` enforces: at most **3 questions per item**, each **under 40 words**
(whitespace-split — every absolute path eats the count); `map`/`requirements` questions may not
ask for content (`all/every`, `exhaustive`, `end-to-end`). It fails with all problems at once.
When they will not fit:

- **Split into more items, never into compound questions** — more `R<n>` items, each with its own
  agent and time box.
- **Move detail into a referenced file** — stay under 40 words by pointing at a workflow-dir
  file you wrote, e.g. `Group the notes per <wf>/research/R1-q1.md; output each batch's name
  and dominant repo paths.` The agent reads files its questions reference.
- **Cut words honestly.** Drop articles and hedging, prefer repo-relative paths, and split
  two-clause questions in two.

## Stage 1 — Scope (one round with the human)

1. Save the request verbatim to a file, then run `tp init <location> --title "<title>"
   --request-file <file> [--budget <minutes>]`. It creates `<location>/<date>-<slug>/` and prints
   it: that is `-w` from then on.
2. **Size it yourself first**, ten minutes or less, no agents: `tp survey <repo> --name <ws>` per
   repository; `tp survey-issue jira:KEY` or `gh:owner/repo#N` for a named issue or epic —
   children, thin issues, links, and a research estimate.
3. **Judge the research.** A clear, bounded ask needs none — plan directly. Research earns its
   cost when details are missing or the work is large (an epic's children, unfamiliar code);
   if unsure how much, ask.
4. **Choose participants critically.** `tp roster suggest --kinds <kinds>`. Keep an agent only
   when it has a direct bearing on the output; prefer specific reviewers (correctness, security,
   api-compat, test) over broad ones; if unsure, ask.
5. **One `question` call** (at most 4 questions) covering the output (kind, format, where),
   participants (multiple choice, several allowed), review (`none` or `final`), conventions
   (a workflow-dir file listed in `conventions`), **fix tasks** (may you add small fix tasks
   without asking — how many, how big? their words), and **shipping** (commit after the report?
   also push and open a PR? → the `ship` scope field). **Never ask the human to approve or pick a
   time budget** — size budgets yourself as reporting metadata; never cut work to fit one.
6. Write `scope.json` (`tp schema scope`), `tp scope check`, then **present the key lines of
   `scope.md` in the same turn** and record their scoping answers as the confirmation:
   `tp scope confirm --answer "<their words from the question>"`. Ask a second time only if they
   asked for a change — one round, one gate, not two.

## Stage 2 — Research (only inside the agreed budget)

- Each item is one agent, at most 3 narrow questions, a ≤15-min box, and a purpose: `map`,
  `requirements`, or `investigate` — many small items beat one big one:
  `tp research add R1 --agent <a> --purpose <p> --questions-file <f> --done-when "..." [--minutes N]`
  (rejected questions: see _When tp.py rejects research questions_).
- `tp dispatch R1 R2 R3`, then one `task` call per id with the brief file it printed. As each
  returns: `tp advance <id> --agent-id <its id>` — it records, dispatches what that unblocked,
  and prints the next calls. Fact-check one answer per item.
- **Followups** come back in the result; decide each: `tp research add … --from R1.F2`, or
  `tp research dismiss R1.F2 --reason "..."`. Submit refuses while any is undecided.
- Out of budget is not a stop: add items freely; each keeps its ≤15-min box
  (`tp research extend --minutes N --note "..."` grows the reporting budget).

## Stage 3 — Plan (you write it)

- **Planning maps the work; it never does the work.** One task per area, article, or unit, about
  15 minutes (30 at most), 1–6 objective acceptance criteria, a brief of 150 words or less. Tasks
  cite findings as sources: `research:R3`. Every deliverable must be served by a task (plan check
  refuses an unserved one; plan.md carries a coverage matrix the human reads at approval).
- **Route each kind of work to the agent built for it** (`tp plan check` enforces it): code,
  comments included, is a code task; a document author never owns source files; a liaison only
  transports — what it posts comes verbatim from a reviewed draft (`wf:drafts/<name>.md`) a
  doc-author task wrote; a `publish` task posts that draft to Jira (`tp schema plan`).
- **Code tasks are fused by default**: one code-author round writes the tests, observes them red
  (saving the failing run to the log the brief names), implements to green, and hands back once —
  the pipeline checks the red log, re-runs the tests, and the review still reads the change.
  `split_tests: true` in scope restores the separate test-author step when the human wants
  independent red-test authorship.
- **Paths name the repo files the task writes.** Never `.` or a bare `**` — plan check refuses
  catch-alls and >200-file expansions (real runs blew up git argvs on `.git` and `node_modules`).
  Name each file, optional ones too; a directory path only when its files exist at plan time.
- Parallel tasks write disjoint paths; shared files (`index.md`) go to one integration task.
- `test_cmd` (the task's package, not the whole suite), `tests_paths`, and `test_mode`.
- `docs` is a built-in task check, `docs-all` a final one. Repo commands go in `checks`, scoped
  per task with `{dirs}` (`go vet {dirs}`). With `review: final`, split packages over 10 tasks
  into `review_batches`.
- `tp plan check` until clean, then `tp plan submit`. `tp next` warns once planning passes 45 min.

## Stage 4 — Approval

Give the human ten lines or fewer: tasks, time against the budget, review sessions, questions,
and noticed items, with `plan.md`'s path (its coverage matrix shows the request→task fit). 
`question`: Approve / Revise. Then `tp approve --answer "..."` or `tp revise --feedback "..."`
— never approve without their answer.

## Stage 5 — Execute (autonomous)

If this machine or repo has known breakage the plan did not cause, run `tp baseline` once right
after approval: `tp final` reports those failures as pre-existing instead of blocking on them.

Loop on `tp next`:

- **dispatch / fix / review** → `tp dispatch <id> [<id> …]` (every ready id in one call), then
  one `task` call per printed brief, all in one message.
- **An agent replies** → `tp advance <id> --agent-id <its id>`: it records, dispatches what that
  unblocked, and prints what to send next.
- **Time reports, never gates.** The meter (net of dead clock) shows in `tp next`, `tp digest`,
  and the report; nothing is refused for being over budget and no work is compressed to fit one.
- **Digest sparingly** — `tp next` carries the status line; a full `tp digest` on a status
  question, on halt/resume, at closeout, or when several hours pass. Do not digest every wave.
- **check** → only authoring hand-backs (author, impl, build) reach you: fact-check the printed
  sample (does each cited line say what the sentence claims? for code, read the diff), then
  `tp accept <id> --note "..."` or `tp reject <id> --reason "..."`. Green **fix** rounds
  auto-accept — the end-of-run review still reads them, and
  `tp resolve --task <id> --action reopen` reopens one you disagree with.
- **triage** → `tp show <id> --part blocking`, verify each against the source, then
  `tp triage <id> --accept-all`, or `--dismiss F# --reason "..."` (a pair each) and
  `--assign F#=T##`. `tp` routes findings to their author: test files to the test author (in a
  split-tests run); a behaviour bug's fix round starts with a failing test. Dropped or wrongly
  dismissed findings on a done session: `tp resolve --review <id> --action reopen --findings F1,F2`.
  A parked patch (`runs/<id>/*.patch`): have the fix round verify and adopt it.
- **publish** → `tp publish <id>` (dry run), show the human, ask once, `--answer "..."`.
- **human** → ask with `question`, record with
  `tp resolve [--task <id> | --review <id>] --action … --answer "..." --by human` — and keep
  working the other ready actions while you wait. A needs_input question that scope, plan, or
  decisions already settle, answer yourself (`--by manager`). A test gate that is the test's
  fault: `tp resolve --task <id> --action tests`; an approved test change:
  `tp rebaseline-tests <id>`.
- **wait** → end your turn only when `tp next` says to wait for in-flight agents and nothing
  else is actionable; their hand-backs arrive here and re-invoke you.
- **A status question mid-run** → `tp digest`, present it answer-first, then `tp next` and
  **keep working in the same turn**.
- **A dispatch dies** (harness interrupt, restart, host loss; resume returns "Task cancelled") →
  check the workspace for stranded edits, then `tp lost <id> --summary "..."`, resolve, and
  dispatch fresh.
- **An agent far past its estimate** → a running `task` call cannot be stopped: note it, raise
  `tp exception --task <id> --summary "..."` when needed, and keep agent commands
  short-returning (the supervisor kills ~35 min of silence).

## Stage 6 — Closeout, then final, then ship

When `tp next` says **closeout** (all tasks and reviews done): `tp closeout` lists the noticed
items — plain notes about an agent's own work are classified for you; classify the rest several
at a time: `tp closeout --items 1,3-5 --class deferred|followup|observation --note "..."` (the
note, required for deferred/follow-up, names the issue and its consequence in plain words —
never a bare file path). With nothing deferred or a follow-up, **no question is asked** — go
straight to final. With a deferral, `tp closeout --ask` renders the decision brief; one
`question` (fix now / file tickets / accept as recorded), then
`tp closeout --decide --answer "<their words>"`. `tp final` runs the checks (baseline failures
report as pre-existing), writes `report.md`; present it answer-first.

With `ship` in scope: `tp ship` (a dry run), ask once, `tp ship --answer "<their words>"` —
it commits (and with `ship.pr`, pushes and opens the PR); it never rebases. Without `ship`,
committing stays the human's call.

## Halt, resume, status

- **Halt mode** (`/task-pipeline halt`, or `hault`) → `tp halt --reason "<their words>"`. Nothing
  new starts; in-flight agents finish and are recorded; `halt.json` then records where work
  stopped. Tell the human, stop.
- **Resume mode** (`/task-pipeline resume <dir>`) → `tp status`; if halted,
  `tp resume --answer "<their words>"`; then `tp next`. An agent lost mid-run: check the workspace
  for stranded edits, then `tp lost <id> --summary "..."`, resolve, re-dispatch fresh.
- **Unattended runs** need no permission prompts: sandbox-writable workflow and write workspaces,
  and `Bash(python3 ~/.config/opencode/tools/task-pipeline/scripts/tp.py:*)` allowed in
  `permission`.

## Special Instructions

### Coding Related Tasks

- **Always** be test forward with code changes — tests observed red first, then green, in the
  same round by default.
- **Always** review code before considering a unit of work as done — even if smaller reviews
  happened during the coding tasks. Unsure which reviewer: use the skill `reviewomatic`.
