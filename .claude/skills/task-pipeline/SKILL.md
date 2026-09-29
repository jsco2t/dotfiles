---
name: task-pipeline
description: >
  Plan, human-approve, and autonomously execute a substantial piece of work — code, docs,
  knowledge-base articles, tutorials, research, Jira/GitHub epics — with the main session as
  manager, at most three sub-agents at a time, scripted gates, and structured-file hand-offs.
  Scope and a research budget are agreed with the human first; research runs in small, strictly
  scoped items; review runs once, in bulk, at the end. Invoked explicitly.
argument-hint: "<workflow dir> <request> | resume <workflow dir> | halt (or hault) | status <workflow dir>"
disable-model-invocation: true
---

# Task Pipeline

You are the **manager**. You scope with the human, size and agree the research, write the plan,
dispatch at most three agents at a time, fact-check every hand-back, and stop only where the human
must decide. `tp.py` holds the state, enforces the rules, and says what is next.

```bash
python3 ~/.claude/skills/task-pipeline/scripts/tp.py -w <workflow dir> <command>
```

`tp <command>` below means exactly that line; spell it out in every Bash call (zsh does not
word-split a variable). **`tp next` always says what to do next** — run it after every step.

## Rules

1. **Only the human decides** scope, the research budget, plan approval, and anything off the
   plan. Ask with AskUserQuestion; record their words verbatim (`--answer` / `--feedback`).
2. **At most 3 agents in flight**, only agents confirmed in scope.json (both script-enforced).
   Never the Workflow tool or ad-hoc agents.
3. **Structured files, not messages.** Agents read a brief file and write JSON; their reply is
   one line. Read only the part you need: `tp show <id> --part …`, `tp schema <name>`.
4. **The approved plan is the contract.** Outside it: `tp note "<one line>"`; blocking:
   `tp exception --summary "..."` and a question.
5. **Script before judgment.** If a command can decide it, a command decides it.
6. **Answer-first** (`~/.claude/output-styles/answer-first-core.md`) for everything you write.
7. **Never write deliverables or agents' result files.** You fact-check and route.

## Stage 1 — Scope and research budget (one round with the human)

1. The first argument is the workflow directory; if missing, ask. Save the request verbatim to a
   file, then `tp init --title "<title>" --request-file <file> [--budget <minutes>]`.
2. **Size it yourself first**, in ten minutes or less and with no agents: `tp survey <repo> --name
   <ws>` per repository, and `tp survey-issue jira:KEY` or `gh:owner/repo#N` for a named issue or
   epic (it needs network access to that host). It prints children, thin issues, links, and a
   starting-point research estimate.
3. **Judge the research.** A clear, bounded ask needs none — plan directly. Research earns its
   cost when details are missing or the work is large: an epic's children, linked designs,
   unfamiliar code a change must fit. **If you are unsure how much research to do, ask.**
4. **Choose participants critically.** `tp roster suggest --kinds <kinds>`. Keep an agent only
   when it has a direct bearing on the output; prefer the specific lenses (correctness,
   security, api-compat, test) over broad ones; if unsure whether one should take part, ask.
5. **One AskUserQuestion call** (at most 4 questions) covering the output (kind, format, where),
   participants (multiSelect), review (`none` or `final`), and the research budget you propose
   (none, or N agent-minutes and why) — plus the time budget if not given.
6. Write `scope.json` (`tp schema scope`), `tp scope check`, show the human the key lines of
   `scope.md`, and confirm (AskUserQuestion: Confirm / Change): `tp scope confirm --answer "..."`.

## Stage 2 — Research (only inside the agreed budget)

- Each item is one agent, at most 3 narrow questions, a box of 15 minutes or less, and a purpose:
  `map` (how to split the work), `requirements` (what named issues or pages require), or
  `investigate` (how one named thing works). Many small items beat one big one.
  `tp research add R1 --agent <a> --purpose <p> --questions-file <f> --done-when "..." [--minutes N]`
- `tp dispatch R1 R2 R3`, send the calls, `tp record` each. Fact-check one answer per item.
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
and noticed items, with the path to `plan.md`. AskUserQuestion: Approve / Revise. Then
`tp approve --answer "..."` or `tp revise --feedback "..."`. Never approve without their answer.

## Stage 5 — Execute (autonomous)

Load the deferred tools first: ToolSearch `select:SendMessage,TaskStop`. Then loop on `tp next`:

- **dispatch / fix / review** → `tp dispatch <id> [<id> …]` (every ready id in one call, never
  chained), then send each printed `Agent(...)`/`SendMessage(...)` call, all in one message.
- **An agent replies** → `tp record <id> --agent-id <its id>` with Bash `timeout` 600000.
- **check** → fact-check the printed sample (does each cited line say what the sentence claims?
  for code, read the diff), then `tp accept <id> --note "..."` or `tp reject <id> --reason "..."`.
- **triage** (after the end-of-pipeline review) → `tp show <id> --part blocking`, verify each
  against the source, then `tp triage <id> --accept-all`, or `--dismiss F# --reason "..."` and
  `--assign F#=T##`. Accepted findings go to the owning authors; one verification follows.
- **human** → stop, ask, then `tp resolve [--task <id> | --review <id>] --action … --answer "..."`.
  A needs_input question that scope, plan, or decisions already settle, answer yourself.
- **wait** → end your turn; each hand-back re-invokes you.
- **An agent far past its estimate** → TaskStop it, then `tp exception --task <id> --summary "..."`.

## Stage 6 — Final

`tp final` runs the package checks and writes `report.md`. Present it answer-first: what was
delivered, time against the budget, review outcome, and what the human should decide.
Committing and pushing are the human's call.

## Halt, resume, status

- **`/task-pipeline halt`** (or `hault`) → `tp halt --reason "<their words>"`. Nothing new
  starts; agents in flight finish their current step. Keep recording them as they reply; when
  the last is in, `halt.json` records where work stopped and what runs next. Tell the human, stop.
- **`/task-pipeline resume <dir>`** → `tp status`; if halted, `tp resume --answer "<their words>"`;
  then `tp next`. An agent lost with a dead session: SendMessage its id if known, otherwise
  `tp exception --task <id>` and re-dispatch after resolving.
- Unattended runs need no permission prompts: keep the workflow and write workspaces
  sandbox-writable, and allow `Bash(python3 ~/.claude/skills/task-pipeline/scripts/tp.py:*)`.
