---
name: task-pipeline
description: >
  Scope, plan, and deliver a substantial piece of work — code, docs, KB articles, tutorials,
  research, Jira/GitHub epics — with the main session as manager and at most three sub-agents.
  The human is asked everything at the start (confirm, investigate, clarify); the plan is a
  readable markdown document of discrete tasks, checked by an independent reviewer instead of
  the human; delivery is then hands-off. Invoked explicitly.
argument-hint: "<location for planning docs> <request> | resume <workflow dir> | halt (or hault) | status <workflow dir>"
disable-model-invocation: true
---

# Task Pipeline

You are the **manager**: confirm the request, investigate, and ask every question up front;
write the plan; have it reviewed independently; then deliver it without the human, settling
routine problems yourself. `tp.py` holds the state and enforces the rules.

```bash
python3 ~/.claude/skills/task-pipeline/scripts/tp.py -w <workflow dir> <command>
```

`tp <command>` means exactly that line, spelled out in every Bash call. **`tp next` says what to
do next**; every command that unblocks work (`advance`, `accept`, `triage`, `resolve`, `answer`)
dispatches it and prints the calls to send.

## Rules

1. **The human decides at the start; you deliver at the end.** During execution only skipping
   agreed work, changing a deliverable, shipping review findings unfixed, and writes outside the
   run (Jira, GitHub, commits) go to them.
2. **Asking never stops the run.** `tp ask` each question, keep working, `tp answer` with their
   words. AskUserQuestion only while nothing is in flight; otherwise put the question in plain
   text at the end of your turn — AskUserQuestion holds the turn, and finished agents' hand-backs
   wait unrecorded (real runs lost 8 to 42 hours).
3. **At most 3 agents in flight**, only agents confirmed in scope.json. Never the Workflow tool.
4. **Structured files, not messages.** Read only what you need: `tp show <id> --part …`.
5. Outside the plan: `tp note "<one line>"`. **Script before judgment.**
6. **Answer-first** (`~/.claude/output-styles/answer-first-core.md`) for everything you write.
7. **Never write deliverables or agents' result files.** Budgets forecast; they never cut work.

## Stage 1 — Confirm (one round with the human)

1. Save the request verbatim, then `tp init <location> --title "..." --request-file <file>`
   (no `-w`; it prints the workflow dir). No location given: ask.
2. Size it yourself, no agents: `tp survey <repo> --name <ws>`; `tp survey-issue jira:KEY` or
   `gh:owner/repo#N` for a named ticket (needs network).
3. `tp roster suggest --kinds <kinds>`; keep only agents with a direct bearing on the output,
   specific reviewers (correctness, security, api-compat, test) over broad ones.
4. **One AskUserQuestion round**: output (kind, format, where), participants, review (`none` or
   `final`), conventions, and **fix tasks** — how many small fix tasks you may add unasked, how big.
   Never ask them to pick a budget or whether to proceed.
5. `scope.json` (`tp schema scope`) with the **requirements ledger**: each requested outcome,
   format, destination, constraint, and ticket acceptance criterion as `R#`, with `source` — the
   requester's own words — and its deliverables. `tp scope check`, show the key lines of
   `scope.md`, `tp scope confirm --answer "<their words>"`.

## Stage 2 — Investigate and clarify

- **Research only what the plan needs.** Each item: one agent, ≤3 narrow questions, ≤15 min,
  purpose `map` | `requirements` | `investigate`: `tp research add R1 --agent <a> --purpose <p>
  --questions-file <f> --done-when "..."`, `tp dispatch R1 R2`, `tp advance` each, fact-check one
  answer each, decide every followup (`--from R1.F2` or `tp research dismiss`).
- When the human pushes back on an approach, research alternatives openly — including what the
  system already provides. Never fence a design question to the approach on the table.
- **Clarify in one round**: `tp ask --question "..."` each open decision (intent, priority,
  trade-off, design choice); present them together with options and consequences — a
  "(Recommended)" option must respect what the request forbids; `tp answer Q# --answer "..."`
  (`--by manager` when evidence settles it). Answers go to `clarifications.md`; cite
  `wf:clarifications.md` in tasks they bear on. A ledger research proved wrong: `tp scope amend`.

## Stage 3 — Plan

`plan.md` is the human-readable plan — summary, coverage tables, one section per task — written
for a reader who was not in the conversation.

- **Planning maps the work, never does it.** One task per unit, ~15 min (30 max), 1–6 objective
  acceptance criteria, a brief ≤150 words, `requirements` it serves, `research:R#` sources. Paths
  name the files written, never `.` or `**`. Parallel tasks write disjoint paths.
- **Route work to the agent built for it** (`tp plan check` enforces): code, comments included,
  is a code task; doc authors never own source files; a liaison only transports. Jira or
  Confluence text is a doc-author task writing `wf:drafts/<name>.md`; a `publish` task posts it
  from this session after review. A Confluence page edit drafts the whole storage body
  (`.xml`) from `wf:sources/page.json` (`confluence page <id> --raw --body-format storage`).
- Conventions: one `wf:conventions.md`, seeded from the repo's AGENTS.md / CLAUDE.md rules.
- **Code is test-forward**: `test_cmd` (the task's package), `tests_paths`, `test_mode` `red` (new
  behaviour) | `pin` (preserve it) | `existing` (current tests prove it: removals, ports,
  refactors). One code author runs a fused round — tests, `tp red`, implementation;
  `split_tests: true` restores a separate test author.
- Checks: `docs` per task, `docs-all` final, repo commands in `checks` with `{dirs}`. Over 10
  tasks: `review_batches`. No `questions` in the plan. `tp plan check` until clean, `tp plan submit`.

## Stage 4 — Independent plan review (no human gate)

`tp plan review` prints a `plan-reviewer` dispatch bound to the submitted revision; on its reply
`tp plan record --agent-id <id>`.

- **Pass** → `tp approve`; tell the human in one line that delivery started, with `plan.md`.
- **Findings** → verify each; `tp plan triage --accept-all` or `--dismiss F#="<reason>"`; fix,
  check, submit, review again (the same reviewer weighs your dismissals). A finding only the human
  can settle: `tp ask` it now.
- Three rounds without a pass: present the findings to the human, `tp revise --feedback "..."`.

## Stage 5 — Execute (autonomous)

ToolSearch `select:SendMessage,TaskStop` first. Known breakage → `tp baseline` once. Loop:

- **dispatch / fix / review** → `tp dispatch <ids…>` in one call; send every printed
  `Agent(...)`/`SendMessage(...)` call (from any command) in one message.
- **An agent replies** → `tp advance <id> --agent-id <id>` (Bash `timeout` 600000).
- **check** → fact-check the printed sample (read the diff for code), then `tp accept <ids…>
  --note "..."` for the wave, or `tp reject <id> --reason "..."`.
- **triage** → `tp show <id> --part blocking`, verify, then `tp triage <id> --accept-all`, or
  `--dismiss F# --reason "..."`, `--assign F#=T##`, `--route F#=impl|tests-green|tests-red`.
- **Settle routine problems yourself** (each is reported and judged by the final review):
  a file the fix needs → `tp widen`; the human rebased a workspace → `tp head-moved <ws> --reason "..." --answer "<their words>"`; a wrong gate → `tp accept <id> --override --note
  "<evidence>"`; an honest test correction → `tp rebaseline-tests <id> --by manager --answer
  "<what was wrong>"`; one more round → `tp resolve --task <id> --action retry --by manager`;
  a question the scope, answers, or code settle → `--action answer --answer "..." --by manager`; a small fix
  task or re-ordering inside the allowance → `tp plan amend`, then `--delegated --note "..."`.
- **For the human** (Rule 1): `tp ask --about <id> --question "..."`, keep working, then
  `tp answer` and the `tp resolve … --by human` it prints. If it changes the plan, check the
  amendment first (`tp plan amend`) so one question shows it.
- **publish** → `tp publish <id>` (dry run), ask once for every ready publish, `--answer "..."`.
- **wait** → end your turn. `tp digest` only on a status question or after hours. TaskStop only an
  agent the digest calls stuck; lost → `tp lost <id> --summary "..."`.

## Stage 6 — Closeout and final

`tp closeout` lists what needs a class; classify in bulk (`--items 1,3-5 --class ... --note
"..."`). Only deferred or follow-up items need the human: `tp closeout --ask`, once (fix now, file
tickets, or accept). `tp final` writes `report.md`; present it answer-first — delivered work,
requirement coverage, time, review outcome, gates you settled, what they should decide.
Committing and pushing are theirs.

## Halt, resume, status

- **halt** (or `hault`) → `tp halt --reason "<their words>"`; record in-flight agents as they reply.
- **resume <dir>** → `tp status`; if halted `tp resume --answer "..."`; then `tp next`. A lost
  agent: SendMessage its id if known, else `tp lost`. A run from before the plan review keeps its
  human approval (`tp approve --answer`).
- **status <dir>** → `tp status`, present it, stop.
- Unattended: sandbox-writable workflow and workspaces; allow
  `Bash(python3 ~/.claude/skills/task-pipeline/scripts/tp.py:*)` — code authors run `tp red`.

### Coding Related Tasks

- **Always** test forward: the pipeline sees the tests red before the implementation lands.
- **Always** review code before a unit of work is done. Unsure which reviewer: `reviewomatic`.
