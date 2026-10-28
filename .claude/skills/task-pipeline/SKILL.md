---
name: task-pipeline
description: >
  Plan, human-approve, and autonomously execute a substantial piece of work — code, docs,
  knowledge-base articles, tutorials, research, Jira/GitHub epics — with the main session as
  manager, at most three sub-agents at a time, scripted gates, and structured-file hand-offs.
  Scope is agreed with the human first; research runs in small, strictly scoped items; review
  runs once, in bulk, at the end; stalls are judged by progress, not the clock. Invoked explicitly.
argument-hint: "<location for planning docs> <request> | resume <workflow dir> | halt (or hault) | status <workflow dir>"
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
word-split a variable). **`tp next` always says what to do next.**

## Rules

1. **Only the human decides** scope, participants, plan approval, and anything off the plan.
   Ask with AskUserQuestion; record their words verbatim (`--answer` / `--feedback`).
2. **At most 3 agents in flight**, only agents confirmed in scope.json (both script-enforced).
   Never the Workflow tool or ad-hoc agents.
3. **Structured files, not messages.** Agents read a brief file and write JSON; their reply is
   one line. Read only what you need: `tp show <id> --part …`, `tp schema <name>`.
4. **The approved plan is the contract.** Outside it: `tp note "<one line>"`; blocking:
   `tp exception --summary "..."` and a question.
5. **Script before judgment.** If a command can decide it, a command decides it.
6. **Answer-first** (`~/.claude/output-styles/answer-first-core.md`) for everything you write.
7. **Never write deliverables or agents' result files.** You fact-check and route.
8. **Budgets and estimates forecast; they never cut or squeeze work, or stop an agent.** `tp`
   flags stalls. Re-estimate with `tp budget extend` / `tp research extend` and `--note`.

## Stage 1 — Scope (one round with the human)

1. The first argument is the **location** for planning documents; if missing, ask. Save the
   request verbatim to a file, then `tp init <location> --title "<title>" --request-file <file>
   [--budget <minutes>]` (no `-w`): it creates `<location>/<date>-<slug>/`, the `-w` from then on.
2. **Size it yourself first**, in ten minutes or less and with no agents: `tp survey <repo> --name
   <ws>` per repository, and `tp survey-issue jira:KEY` or `gh:owner/repo#N` for a named issue or
   epic: children, thin issues, links, and a research estimate.
3. **Judge the research.** A clear, bounded ask needs none — plan directly. Research earns its
   cost when details are missing or the work is large (an epic's children, linked designs,
   unfamiliar code). **If you are unsure how much research to do, ask.**
4. **Choose participants critically.** `tp roster suggest --kinds <kinds>`. Keep an agent only
   with a direct bearing on the output; prefer specific lenses (correctness, security,
   api-compat, test) over broad ones; unsure about one? Ask.
5. **AskUserQuestion** (two calls if needed) covering the output
   (kind, format, where), participants (multiSelect), review (`none` or `final`), conventions, and
   **fix tasks**: may you add small fix tasks without asking — how many, how big? (`fix_tasks`,
   their words). **Never ask them to pick a time budget**: you size it. Ambiguous? Ask again.
6. Write `scope.json` (`tp schema scope`; sandbox mount points go in `ignore`, a limit the work
   outgrows in `limits`), `tp scope check`, show the human the key lines of
   `scope.md`, and confirm (AskUserQuestion: Confirm / Change): `tp scope confirm --answer "..."`.

## Stage 2 — Research (your call)

- Each item is one agent, at most 3 narrow questions, a box of 15 minutes or less, and a purpose:
  `map` (how to split the work), `requirements` (what named issues require), or `investigate`
  (how one named thing works). Many small items beat one big one.
  `tp research add R1 --agent <a> --purpose <p> --questions-file <f> --done-when "..."` (`--model
  sonnet` suits pattern work). `tp dispatch R1 R2 R3`, send the calls, `tp advance` each, and
  fact-check one answer per item.
- **Followups** come back in the result; decide each: `tp research add … --from R1.F2`, or
  `tp research dismiss R1.F2 --reason "..."`. Submit refuses while any is undecided.

## Stage 3 — Plan (you write it)

- **Planning maps the work; it never does the work.** One task per area, article, or unit, about
  15 minutes (30 at most), 1–6 objective acceptance criteria, a brief of 150 words or less.
  Tasks cite findings as sources: `research:R3`. Paths name the files a task writes, never `.` or `**`.
- **Route each kind of work to the agent built for it** (`tp plan check` enforces it):
  code, comments included, is a code task; a document author never owns source files; a liaison
  only transports (`wf:` paths only, never drafting). Text for Jira is a doc-author task writing
  `wf:drafts/<name>.md`; a `publish` task posts it as a comment, description, or child issue
  (`tp schema plan`). Integration runs after review.
- Parallel tasks write disjoint paths; shared files (`index.md`) go to one task.
- Rules every task follows: one file in plan `conventions` (`wf:conventions.md`); it freezes with the plan.
- Code is test-forward: `test_cmd` (the task's package, not the whole suite) and `tests_paths`.
- `docs` is a built-in task check, `docs-all` a final one; repo commands go in `checks`, scoped
  per task with `{dirs}` (`go vet {dirs}`). Over 10
  tasks: `review_batches`. `tp plan check` until clean, then `tp plan submit`.

## Stage 4 — Approval

Give the human ten lines or fewer: tasks, time against the budget, review sessions, questions,
and noticed items, with the path to `plan.md`. AskUserQuestion: Approve / Revise. Then
`tp approve --answer "..."` or `tp revise --feedback "..."`. Never approve without their answer.

## Stage 5 — Execute (autonomous)

Load the deferred tools first: ToolSearch `select:SendMessage,TaskStop`. Pre-existing breakage →
`tp baseline` once now. Then loop on `tp next`:

- **dispatch / fix / review** → `tp dispatch <id> [<id> …]` (every ready id in one call), then
  send exactly the printed `Agent(...)`/`SendMessage(...)` calls, all in one message. Never
  reuse an earlier task's agent.
- **An agent replies** → `tp advance <id> --agent-id <its id>` (Bash `timeout` 600000): it records,
  dispatches what that unblocks, and prints what to send next.
- **Digest** (`tp digest`) after a wave settles or on "status?" — then keep working.
- **check** → fact-check the printed sample (do the quoted lines say what is claimed? for code,
  read the diff), then `tp accept <id> --note "..."` or `tp reject <id> --reason "..."`.
- **triage** → `tp show <id> --part blocking`, verify each against the source, then
  `tp triage <id> --accept-all`, or `--dismiss F# --reason "..."` (a pair each) and
  `--assign F#=T##`. `tp` routes each to its author: test files to the test author; behaviour
  bugs get a failing test first.
  Reopen a done session's findings: `tp resolve --review <id> --action reopen --findings F1,F2`.
- **publish** → `tp publish <id>` (dry run), show the human, ask once, `--answer "..."`.
- **human** → stop, ask, then `tp resolve [--task <id> | --review <id>] --action … --answer "..." --by human`.
  A needs_input question that scope, plan, or decisions already settle, answer yourself (`--by manager`).
  A test must change: `--action tests`; already changed with their OK: `tp rebaseline-tests <id>`.
- **Something falls outside the plan** → a file a task's fix needs: reopen it, or `tp widen <id>
  --path <file> --reason "..."`, no question.
  Else draft first (`tp plan amend` starts `plan-amend.json`); `tp plan amend` checks it and prints
  the one question: ask once, then `--answer "..."` — or, inside the human's fix-task allowance,
  `--delegated --note "..."`. Scope changes: `tp scope amend`, the same way.
- **wait** → end your turn; each hand-back re-invokes you.
- **Past its estimate** is a cue to look (`tp digest`), never a verdict. TaskStop only an agent
  the digest calls possibly stuck, or on the human's say-so. Lost → `tp lost <id> --summary "..."`.

## Stage 6 — Closeout and final

**closeout** → `tp closeout` lists what still needs a class (chatter is classified for you);
classify in bulk (`--items 1,3-5 --class ... --note "<issue and consequence>"`) and ask the
human once (`tp closeout --ask`): fix now, file tickets (`jira-issue` publishes), or accept —
never a local file.
`tp final` writes `report.md`. Present it answer-first: what was delivered, time against the
budget, review outcome, and what the human should decide. Committing and pushing are theirs.

## Halt, resume, status

- **`/task-pipeline halt`** (or `hault`) → `tp halt --reason "<their words>"`. Nothing new
  starts; record agents in flight as they reply.
- **`/task-pipeline resume <dir>`** → `tp status`; if halted, `tp resume --answer "<their words>"`;
  then `tp next`. An agent lost with its session: SendMessage its id if known, else `tp lost <id>`.
- **`/task-pipeline status <dir>`** → `tp status`, present it, stop (from outside a run only).
- Unattended runs: sandbox-writable workflow and workspaces; allow `Bash(python3 ~/.claude/skills/task-pipeline/scripts/tp.py:*)`.

### Coding Related Tasks

- **Always** be test forward with code changes.
- **Always** review code before a unit of work is done, even after smaller reviews. Unsure which
  reviewer to use: the skill `reviewomatic`.
