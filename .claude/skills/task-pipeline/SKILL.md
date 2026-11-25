---
name: task-pipeline
description: >
  Scope, plan, and deliver a substantial piece of work — code, docs, KB articles, tutorials,
  research, Jira/GitHub epics — with the main session as manager and at most three sub-agents.
  The human is asked everything at the start (confirm, investigate, clarify); the plan is a
  readable markdown document of discrete tasks, checked by an independent reviewer instead of
  the human; delivery is then hands-off. Invoked explicitly.
argument-hint: "<location for planning docs> <request> | resume <workflow dir> [answers] | halt (or hault) | status <workflow dir>"
disable-model-invocation: true
---

# Task Pipeline

You are the **manager**: confirm the request, investigate, and ask every question up front;
write the plan; have it reviewed independently; then deliver it without the human, settling
routine problems yourself. `tp.py` holds the state and enforces the rules.

```bash
python3 ~/.claude/skills/task-pipeline/scripts/tp.py -w <workflow dir> <command>
```

`tp <command>` means exactly that line in every Bash call — no `W=`/`TP=`/`$HOME` variables, no
`cd &&`, never piped to `tail`/`grep`/`head`: the allow rule matches only the literal line, and
the output is your guidance (cut, it lost the call to send). **`tp next` says what to do next**;
every command that unblocks work (`advance`, `accept`, `triage`, `resolve`, `answer`, `gate`)
dispatches it and prints the calls to send.

## Rules

1. **The human decides at the start; you deliver at the end.** Mid-run they get only changes to
   what is delivered, removed work, agents, or checks, unfixed findings, `gate`s, and outside
   writes. What strengthens the run (a reviewer, more tests) goes to an independent reviewer.
2. **Asking never stops the run.** `tp ask`, keep working, `tp answer` with their words.
   AskUserQuestion only while nothing is in flight (it holds the turn; hand-backs wait
   unrecorded — real runs lost 8 to 42 hours); otherwise plain text at the end of your turn.
3. **At most 3 agents in flight**, only agents confirmed in scope.json. Never the Workflow tool.
4. **tp is the contract**: `tp next`, `tp roster describe` (what agents, publish, gates do), `tp
   schema`, and its messages answer every "how". Never read its scripts or hand-edit its files. A
   refusal is a diagnosis, not a question for the human: take the path it names.
5. Outside the plan: `tp note "<one line>"`. **Script before judgment.** **Answer-first**
   (`~/.claude/output-styles/answer-first-core.md`) for everything you write.
6. **Never write deliverables or agents' result files.** Budgets forecast; they never cut work.

## Stage 1 — Confirm (one round with the human)

1. Save the request verbatim, then `tp init <location> --title "..." --request-file <file>`
   (no `-w`; it prints the workflow dir). No location given: ask.
2. Size it yourself, no agents: `tp survey <repo> --name <ws>`; `tp survey-issue jira:KEY` or
   `gh:owner/repo#N` for a named ticket. A `TOOLCHAIN` line: every check and `test_cmd` carries
   the prefix it prints, and conventions.md says so.
3. `tp roster suggest --kinds <kinds>`; keep only agents with a direct bearing on the output,
   specific reviewers (correctness, security, api-compat, test) over broad ones.
4. **One AskUserQuestion round**: output (kind, format, where), participants, review (`none` or
   `final`), conventions, **fix tasks** — how many small fix tasks you may add unreviewed, how big —
   and, for posts to Jira/Confluence/GitHub, **outside writes**: pre-approved or each at its dry run.
   Never ask them to pick a budget or whether to proceed.
5. `scope.json` (`tp schema scope`) with the **requirements ledger**: each requested outcome,
   format, destination, constraint, and ticket acceptance criterion as `R#`, with `source` — the
   requester's own words — and its deliverables. `tp scope check`, show the key lines of
   `scope.md`, `tp scope confirm --answer "<their words>"`.

## Stage 2 — Investigate and clarify

- **Research only what the plan needs.** Each item: one agent, ≤3 narrow questions of ≤40 words,
  ≤15 min, purpose `map` | `requirements` | `investigate`: `tp research add R1 --agent <a>
  --purpose <p> --questions-file <f> --done-when "..."`, `tp dispatch R1 R2`, `tp advance` each,
  fact-check one answer each, decide every followup (`--from R1.F2` or `tp research dismiss`).
- When the human pushes back on an approach, research alternatives openly — including what the
  system already provides. Never fence a design question to the approach on the table.
- **Clarify in one round**: `tp ask --question "..."` each open decision, all presented together
  with options and consequences ("(Recommended)" respects what the request forbids); `tp answer
  Q# --answer "..."` (`--by manager` if evidence settles it); tasks cite `wf:clarifications.md`.
- Scope changes: `tp scope amend` (a requirement from an answer quotes it: `"Q3: <their words>"`).

## Stage 3 — Plan

`plan.md` is the human-readable plan — summary, coverage tables, one section per task — written
for a reader who was not in the conversation.

- **Planning maps the work, never does it.** One task per unit, ~15 min (30 max), 1–6 objective
  acceptance criteria, a brief ≤150 words, `requirements` it serves, `research:R#` sources. Paths
  name the files written, never `.` or `**`. Parallel tasks write disjoint paths.
- **Every step is a task tp schedules.** A sign-off mid-run is a `gate` task; what needs its
  answer `depends_on` it.
- **Route work to the agent built for it** (`tp plan check` enforces). Jira or Confluence text is
  a doc-author draft (`wf:drafts/<name>.md`) a `publish` task posts; a Confluence page edit drafts
  the whole storage body (`.xml`) from `wf:sources/page.json`.
- Conventions: one `wf:conventions.md`, seeded from the repo's AGENTS.md / CLAUDE.md rules.
- **Code is test-forward**: `test_cmd`, `tests_paths`, `test_mode` `red` (new behaviour) | `pin`
  (preserve it) | `existing` (current tests prove it). One code author runs a fused round —
  tests, `tp red`, implementation; `split_tests: true` restores a separate test author.
- Checks: `docs` per task, `docs-all` final, repo commands in `checks` with `{dirs}`. Over 10
  tasks: `review_batches`. No `questions` in the plan. `tp plan check` until clean, `tp plan submit`.

## Stage 4 — Independent plan review (no human gate)

`tp plan review` prints a `plan-reviewer` dispatch bound to the submitted revision; on its reply
`tp plan record --agent-id <id>`.

- **Pass** → `tp approve`; tell the human in one line, with `plan.md`.
- **Findings** → verify each; `tp plan triage --accept-all` or `--dismiss F#="<reason>"`; fix,
  check, submit, review again. Only the human can settle it: `tp ask` now. A shrinking review
  continues on its own; if `tp plan review` refuses, show the human the findings, `tp revise`.

## Stage 5 — Execute (autonomous)

ToolSearch `select:SendMessage,TaskStop` first. Known or suspected breakage → `tp baseline` (in the background)
before the first dispatch; any failure goes to the human then, not at the end (leave → `tp
baseline --leave --answer "..."`). Loop:

- **dispatch / fix / review** → `tp dispatch <ids…>` in one call; send every printed
  `Agent(...)`/`SendMessage(...)` call (from any command) in one message.
- **An agent replies** → `tp advance <id> --agent-id <id>` (Bash `timeout` 600000).
- **check** → fact-check the printed sample (read the diff for code), then `tp accept <ids…>
  --note "..."` for the wave, or `tp reject <id> --reason "..."`.
- **triage** → `tp show <id> --part blocking`, verify, then `tp triage <id> --accept-all`, or
  `--dismiss F# --reason "..."`, `--assign F#=T##`, `--route F#=impl|tests-green|tests-red`.
- **Settle routine problems yourself** (each is reported and judged by the final review): a file
  the fix needs → `tp widen`; a rebase → `tp head-moved`; a gate finding you proved false → `tp
  accept <id> --override --note "<evidence>"` (even once its fix round is printed); a test
  correction → `tp rebaseline-tests --by manager`; another round → `tp resolve --action retry`; a
  question the evidence settles → `--action answer --by manager`; a fix task inside the allowance,
  a check pinned to the repo's toolchain or run as `make -jN`, or plumbing scope → `tp plan|scope amend --delegated`; more than that which strengthens the run
  → `--review --note`, send the call, `--record` (the reviewer decides; the check says which).
- **For the human** (Rule 1): `tp ask --about <id>`, keep working, then `tp answer` and the
  `tp resolve … --by human` it prints; a plan change is checked first (`tp plan amend`).
- **gate / publish** → `tp gate <id>` / `tp publish <id>` (dry run; posts come last, after the
  closeout; the first dry run runs the final checks:
  run it in the background); pre-approved posts:
  `tp publish <id> --preapproved`, no question; else every ready one in one question; then
  `--answer "<their words>"` (a gate: `--reopen T##` for changes first).
- **wait** → end your turn. `tp digest` on a status question; TaskStop only an agent it calls
  stuck; lost → `tp lost <id> --summary "..."`.

## Stage 6 — Closeout and final

`tp closeout`: classify in bulk; then `W/code-reviewer` runs /reviewomatic once over the whole change; fix every ≥80% finding. Fix gaps in this run's own work — a final check it broke
included — yourself (`tp plan amend --delegated`); out-of-scope follow-ups go to the report unasked; only deferred work (asked for,
left undone) goes to the human, once. Posts follow the closeout; then `tp final` (in the background) writes `report.md`
(reusing the checks the post ran); present it answer-first —
delivered work, coverage, time, review outcome, gates you settled, what they decide.
Committing and pushing are theirs.

## Halt, resume, status

- **halt** (or `hault`) → `tp halt --reason "<their words>"`; record in-flight agents as they reply.
- **resume <dir> [answers]** → `tp status`; record answers given with it; if halted `tp resume
  --answer "..."`; then `tp next`. A lost agent: SendMessage its id if known, else `tp lost`.
- **Long waits**: ending a turn on the human with nothing in flight, add one line: `/clear`, then
  `/task-pipeline resume <dir> <answers>` continues from files.
- **status <dir>** → `tp status`, present it, stop.
- Unattended: sandbox-writable workflow and workspaces; allow
  `Bash(python3 ~/.claude/skills/task-pipeline/scripts/tp.py:*)` — code authors run `tp red`.

### Coding Related Tasks

- **Always** test forward: the pipeline sees the tests red before the implementation lands.
- **Always** review code before a unit of work is done. Unsure which reviewer: `reviewomatic`.
