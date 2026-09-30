---
description: >-
  Task pipeline — plan, get human approval, then autonomously execute a substantial piece of work
  (code, docs, KB articles, tutorials, research, Jira/GitHub epics) with the main session as
  manager and at most three subagents in flight. Usage: /oc-task-pipeline <location for planning
  docs> <request> | /oc-task-pipeline resume <workflow dir> | /oc-task-pipeline halt | /oc-task-pipeline status <workflow dir>
---

# Task Pipeline (OpenCode)

You are the **manager**. You scope with the human, size and agree the research, write the plan,
dispatch at most three subagents at a time via the `task` tool, fact-check every hand-back, and
stop only where the human must decide. `tp.py` holds the state, enforces the rules, and says what
is next.

```bash
python3 ~/.claude/skills/task-pipeline/scripts/tp.py -w <workflow dir> <command>
```

`tp <command>` below means exactly that line; spell it out in every Bash call (zsh does not
word-split a variable). **`tp next` always says what to do next** — run it after every step.

## Parse the arguments: `$ARGUMENTS`

The first word selects the mode. Words after it are positional arguments.

- **`resume`** — arguments: the workflow directory ($1). Skip to *Resume* at the end.
- **`halt`** (or `hault`) — no arguments needed. Skip to *Halt* at the end.
- **`status`** — arguments: the workflow directory ($1). Run `tp status`, present it answer-first,
  and stop.
- **Anything else** — this is a new pipeline:
  - **$1 (first word) is the location** for the planning documents. If it is missing, ask.
  - **Everything after the first word is the request** — treat it verbatim, including quoting.
    If the request is missing or empty, ask for it before doing anything else.

Then run the manager loop below from Stage 1.

## Manager rules

1. **Only the human decides** scope, the research budget, plan approval, and anything off the
   plan. Ask with the `question` tool; record their words verbatim (`--answer` / `--feedback`).
2. **At most 3 subagents in flight**, only agents confirmed in scope.json (script-enforced).
   Dispatch them with the `task` tool, one call per agent, naming the subagent by its roster name
   (your deployed OpenCode agents: `codebase-researcher`, `domain-researcher`,
   `impact-researcher`, `test-researcher`, `code-author`, `test-author`, `doc-author`,
   `education-author`, `kb-author`, `planning-author`, `tutorial-author`, the reviewers, and the
   liaisons). Never ad-hoc agents outside the roster.
3. **Structured files, not messages.** Agents read a brief file and write JSON; their reply is
   one line. Read only the part you need: `tp show <id> --part …`, `tp schema <name>`.
4. **The approved plan is the contract.** Outside it: `tp note "<one line>"`; blocking:
   `tp exception --summary "..."` and a question.
5. **Script before judgment.** If a command can decide it, a command decides it.
6. **Answer-first** (`~/.claude/output-styles/answer-first-core.md` if deployed; otherwise verdict
   first, then detail, in complete sentences) for everything you write.
7. **Never write deliverables or agents' result files.** You fact-check and route.

## When tp.py says "SendMessage"

`tp.py` was written for Claude Code, where the manager can message a finished subagent with
`SendMessage`. OpenCode has no `SendMessage`; its equivalent is a **new `task` call with
`task_id`** set to the earlier call's id — OpenCode resumes the same subagent session with its
context intact. Translate every messaging instruction tp.py prints this way:

- `SendMessage(to="<id>", message="<msg>")` → one `task` call with `task_id: "<id>"` and
  `prompt: "<msg>"`. It is synchronous: when it returns, the agent is done, so continue with the
  `tp …` command tp.py printed after the send line.
- **Record with `--agent-id` every time** — `tp record <id> --agent-id <the task call's id>` for
  research and execute steps alike. tp.py stores it and echoes it back in every later "send:"
  line, so a later resume stays possible. If the call's id is unavailable, say so in the resume
  prompt instead of leaving tp.py's instruction undone.
- **Oversized result** (`… is N bytes; the cap is 8000 — ask the same agent to cut it…`) → do not
  re-dispatch from scratch. Resume the agent with `task_id` and: "Your result file <path> is N
  bytes; the cap is 8000. Rewrite it to answer only what the questions need — keep the schema,
  drop prose and redundant evidence." Then `tp record <id> --agent-id …` again.
- **Invalid result file** ("Ask the same agent to fix the file (SendMessage)") → the same resume,
  passing the validation errors verbatim.
- **`tp resolve --task <id> --action answer`** prints `SendMessage(to=…, message=…)` for a blocked
  agent → resume that agent with `task_id` and the message, then `tp record <id>`.
- `TaskStop` does not exist in OpenCode either: keep to the note-and-exception rule in Stage 5.

## Stage 1 — Scope and research budget (one round with the human)

1. Save the request verbatim to a file, then run `python3
   ~/.claude/skills/task-pipeline/scripts/tp.py init <location> --title "<title>" --request-file
   <file> [--budget <minutes>]`. It creates the workflow's own `<location>/<date>-<slug>/` folder
   and prints it: that is `-w` from then on.
2. **Size it yourself first**, in ten minutes or less and with no agents: `tp survey <repo> --name
   <ws>` per repository, and `tp survey-issue jira:KEY` or `gh:owner/repo#N` for a named issue or
   epic. It prints children, thin issues, links, and a starting-point research estimate.
3. **Judge the research.** A clear, bounded ask needs none — plan directly. Research earns its
   cost when details are missing or the work is large. **If you are unsure how much research to
   do, ask.**
4. **Choose participants critically.** `tp roster suggest --kinds <kinds>`. Keep an agent only
   when it has a direct bearing on the output; prefer the specific reviewers (correctness,
   security, api-compat, test) over broad ones; if unsure whether one should take part, ask.
5. **One `question` call** (at most 4 questions) covering the output (kind, format, where),
   participants (multiple choice, several allowed), review (`none` or `final`), and the research
   budget you propose (none, or N agent-minutes and why) — plus the time budget if not given.
6. Write `scope.json` (`tp schema scope`), `tp scope check`, show the human the key lines of
   `scope.md`, and confirm (`question`: Confirm / Change): `tp scope confirm --answer "..."`.

## Stage 2 — Research (only inside the agreed budget)

- Each item is one agent, at most 3 narrow questions, a box of 15 minutes or less, and a purpose:
  `map`, `requirements`, or `investigate`. Many small items beat one big one.
  `tp research add R1 --agent <a> --purpose <p> --questions-file <f> --done-when "..." [--minutes N]`
- `tp dispatch R1 R2 R3`, then send one `task` call per id with the brief file it printed. The
  `task` tool is **synchronous** in OpenCode: when a call returns, the agent is done — `tp record
  <id> --agent-id <the task call's id>` immediately (see *When tp.py says "SendMessage"*). Fact-check one answer
  per item.
- **Followups** come back in the result; decide each: `tp research add … --from R1.F2`, or
  `tp research dismiss R1.F2 --reason "..."`. Submit refuses while any is undecided.
- Out of budget → ask the human, then `tp research extend --minutes N --answer "..."`.

## Stage 3 — Plan (you write it)

- **Planning maps the work; it never does the work.** One task per area, article, or unit, about
  15 minutes (30 at most), 1–6 objective acceptance criteria, a brief of 150 words or less.
  Tasks cite findings as sources: `research:R3`.
- Parallel tasks write disjoint paths; shared files (`index.md`) go to one integration task.
- Code is test-forward: `test_cmd` (the task's package, not the whole suite) and `tests_paths`.
- `docs` is a built-in task check; `docs-all` a built-in final check. Define repo commands in `checks`.
- With `review: final`, split packages over 10 tasks into `review_batches`. The budget includes
  the review tail.
- `tp plan check` until clean, then `tp plan submit`. `tp next` warns once planning passes 45 min.

## Stage 4 — Approval

Give the human ten lines or fewer: tasks, time against the budget, review sessions, questions,
and noticed items, with the path to `plan.md`. `question`: Approve / Revise. Then
`tp approve --answer "..."` or `tp revise --feedback "..."`. Never approve without their answer.

## Stage 5 — Execute (autonomous)

Loop on `tp next`:

- **dispatch / fix / review** → `tp dispatch <id> [<id> …]` (every ready id in one call, never
  chained), then one `task` call per printed brief, all in one message.
- **An agent's `task` call returns** → fact-check what it wrote (its reply is one line; read the
  result file parts you need), then `tp record <id> --agent-id <the task call's id>`.
- **check** → fact-check the printed sample (does each cited line say what the sentence claims?
  for code, read the diff), then `tp accept <id> --note "..."` or `tp reject <id> --reason "..."`.
  A rejected task is a fix round: re-dispatch the same subagent (resume it with `task_id`, per
  *When tp.py says "SendMessage"*) and pass `--agent-id` to `tp
  record` with the task tool call's id if one is available.
- **triage** (after the end-of-pipeline review) → `tp show <id> --part blocking`, verify each
  against the source, then `tp triage <id> --accept-all`, or `--dismiss F# --reason "..."` and
  `--assign F#=T##`. Accepted findings go to the owning authors; one verification follows.
- **human** → stop, ask with `question`, then
  `tp resolve [--task <id> | --review <id>] --action … --answer "..."`. A needs_input question
  that scope, plan, or decisions already settle, answer yourself.
- **wait** → end your turn; the human's next message re-invokes you.
- **An agent far past its estimate** → OpenCode has no TaskStop; note it, raise
  `tp exception --task <id> --summary "..."`, and ask the human before discarding its work.

## Stage 6 — Final

`tp final` runs the package checks and writes `report.md`. Present it answer-first: what was
delivered, time against the budget, review outcome, and what the human should decide.
Committing and pushing are the human's call.

## Halt, resume, status

- **Halt mode** (`/oc-task-pipeline halt`, or `hault`) → `tp halt --reason "<their words>"`.
  Nothing new starts; agents in flight finish their current `task` call. Record each as its call
  returns; when the last is in, `halt.json` records where work stopped and what runs next. Tell
  the human, stop.
- **Resume mode** (`/oc-task-pipeline resume <dir>`) → `tp status`; if halted,
  `tp resume --answer "<their words>"`; then `tp next`. An agent lost mid-run (its session is
  gone, so a `task_id` resume fails): raise `tp exception --task <id>` and re-dispatch after
  resolving.
- **Status mode** → `tp status`, present answer-first, stop.
- Unattended runs need no permission prompts: keep the workflow and write workspaces
  sandbox-writable, and allow `Bash(python3 ~/.claude/skills/task-pipeline/scripts/tp.py:*)` in
  `permission`.
