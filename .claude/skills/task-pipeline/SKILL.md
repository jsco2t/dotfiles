---
name: task-pipeline
description: >
  Plan, human-approve, and autonomously execute a substantial piece of work — code, docs,
  knowledge-base articles, tutorials, research — with the main session as manager, at most
  two sub-agents at a time, scripted gates, and file-based hand-offs. Planning is fast
  (target under 45 minutes): scope confirmed with the human first, a deterministic repo
  survey instead of research agents, one plan.json the manager writes. Invoked explicitly.
argument-hint: "<workflow dir> <request> | resume <workflow dir> | status <workflow dir>"
disable-model-invocation: true
---

# Task Pipeline

You are the **manager**. You scope with the human, write the plan, dispatch at most two agents
at a time, fact-check every hand-back, and stop only where the human must decide. `tp.py` holds
the state, enforces the rules, and says what is next.

```bash
python3 ~/.claude/skills/task-pipeline/scripts/tp.py -w <workflow dir> <command>
```

Below, `tp <command>` is shorthand for exactly that line. Spell it out in every Bash call:
shell state does not persist, and zsh does not word-split a variable holding a command.
**`tp next` always says what to do next** — run it after every step and follow it.

## Rules

1. **Only the human decides** scope, plan approval, and anything off the plan. Ask with
   AskUserQuestion; record their words verbatim (`--answer` / `--feedback`).
2. **At most 2 agents in flight**, only agents confirmed in scope.json. The script refuses a
   third agent or an unconfirmed one. Never the Workflow tool, never ad-hoc agents.
3. **Files, not messages.** An agent reads a brief file, writes its deliverable and a result
   file, and replies with one line. Never paste file contents into a prompt; read only what
   the step needs (`tp` output, result summaries, the fact-check sample).
4. **The approved plan is the contract.** No new tasks, no reinterpretation, no deferral.
   Something outside the plan is `tp note "<one line>"` (the human sees it at approval and in
   the report); something that blocks is `tp exception --summary "..."` and a question.
5. **Script before judgment.** What a command can check is a plan check, not a review.
6. **Answer-first** (`~/.claude/output-styles/answer-first-core.md`) for everything you
   write: point first, complete sentences, no private shorthand, findings lead with their state.
7. **Never write deliverables or agents' result files.** You fact-check and route.

## Stage 1 — Scope (one round with the human)

1. The first argument is the workflow directory; if it is missing, ask. Save the request
   verbatim to a scratch file, then `tp init --title "<title>" --request-file <file>
   [--budget <minutes for the whole job>]`.
2. Orient in five minutes or less: `tp survey <repo> --name <ws>` for each source repository,
   plus the README. The survey is the structure map; do not dispatch agents for it.
3. **Choose participants critically.** `tp roster suggest --kinds <kinds>` prints the minimal
   set. Keep an agent only when it has a direct bearing on the requested output; when unsure,
   ask. A reviewer's lens must fit the deliverable: documents get `doc-reviewer`, never an
   architecture review.
4. **One AskUserQuestion call**, at most 4 questions, always covering:
   - **Output:** what kind, what format, where (for example, KB articles under `kb/`).
   - **Participants:** the suggested author, plus each optional reviewer (multiSelect).
   - **Review depth:** `none` (scripted checks plus your fact-check), `per-task`, `final`, or
     `both`.
   - **Budget** if the request did not give one, and only the term questions whose answer
     changes the work (which comparison set, which version).
5. Write `scope.json` (schema below), then `tp scope check`. Show the human the key lines of
   `scope.md` and ask them to confirm (AskUserQuestion: Confirm / Change). Then
   `tp scope confirm --answer "<their words>"`. The scope is now frozen.

## Stage 2 — Plan (you write it)

- **Planning maps the work; it never does the work.** Split along the survey: one task per
  area, article, or unit, about 15 minutes each (30 at most). Each task gets 1–6 objective
  acceptance criteria and a brief of 150 words or less that names what to read.
- **Recon, rarely.** Only when the survey and your own reading cannot settle how to split the
  work: `tp recon add R1 --agent <confirmed recon agent> --questions-file <f> --done-when
  "..."`. That allows at most 3 questions, a map rather than content, and a 15-minute box.
  Then `tp dispatch R1`, send the printed call, and `tp record R1`. Fact-check one answer.
- **Parallel tasks write disjoint paths.** Shared files (`index.md`, READMEs) belong to one
  integration task that depends on the others.
- **Code is test-forward.** Every code task has `test_cmd` and `tests_paths`: tests first,
  observed red, then implementation observed green, with the tests unchanged. Use
  `test_mode: "pin"` for refactors. Point `test_cmd` at the task's package, not the whole suite.
- **Checks.** `docs` is built in: links, `path:line` citations exist, and each citation's
  sentence names something near the cited line. Define repository commands under `checks`.
  The final check `docs-all` adds reachability from `index.md`.
- **Questions.** One that blocks the plan: `tp exception` and ask now. Non-blocking ones go
  in the plan's `questions`, shown at approval.
- `tp plan check`, then fix every error (they are the rules: budget, task size, overlaps,
  confirmed agents), then `tp plan submit`. `tp next` warns once planning passes 45 minutes.

## Stage 3 — Approval

Give the human ten lines or fewer: task count, estimated time against the budget, questions,
and noticed items, with the path to `plan.md`. Ask with AskUserQuestion: Approve / Revise.
Then `tp approve --answer "..."`, or `tp revise --feedback "..."`, re-plan, and re-submit.
Never run `tp approve` without the human's answer in hand. After approval, start at once and do
not ask permission between steps.

## Stage 4 — Execute (autonomous)

First load the deferred tools the loop uses: ToolSearch `select:SendMessage,TaskStop`. Then loop
on `tp next`:

- **dispatch / fix / review** → `tp dispatch <id>`, then send exactly the `Agent(...)` or
  `SendMessage(...)` call it prints. When two actions are listed, send both calls in one message.
- **An agent replies** → `tp record <id> --agent-id <its agent id>`, with the Bash `timeout` set to
  600000 (as for `tp final`), because it runs the task's tests and checks. It validates the
  result, fails files outside the task's paths or a touched read-only workspace, runs checks and
  red/green, and routes: a fix round by the same agent, the reviewer, or your fact-check.
- **check** → fact-check the printed sample: does each cited source line say what the sentence
  claims? For code, read the diff. Then `tp accept <id> --note "<what you verified>"` or
  `tp reject <id> --reason "<what is wrong, concretely>"`. This is where you course-correct.
- **human** → stop, ask with AskUserQuestion, then `tp resolve [--task <id>] --action
  answer|retry|skip|reopen|accept --answer "<their words>"`. A needs_input question you can
  answer from `scope.md`, `plan.json`, or `decisions.md` is answered without the human.
- **wait** → end your turn; each hand-back re-invokes you.
- **An agent far past its estimate** (`tp status` shows minutes): TaskStop it, then
  `tp exception --task <id> --summary "..."`; once resolved it can be dispatched again.

Fix rounds are capped at 2 per task, and then the human decides.

## Stage 5 — Final

`tp final` runs the package checks and writes `report.md`. Present it answer-first: what was
delivered and where, time against the budget, anything the human should decide (the noticed
list). Committing and pushing are the human's call.

## Resume, status, unattended runs

`/task-pipeline resume <dir>`: `tp status`, then `tp next`. If an agent was in flight when the
session ended, SendMessage its id if the transcript has it; otherwise raise
`tp exception --task <id>` and re-dispatch after resolving. `tp report` prints timings.
Permission prompts stall autonomous runs: keep the workflow directory and write workspaces
sandbox-writable, and allow `Bash(python3 ~/.claude/skills/task-pipeline/scripts/tp.py:*)`.

## Schemas

`scope.json`:

```json
{"title": "Stratum KB", "output": "Markdown KB under kb/, one folder per area, linked from kb/index.md",
 "deliverables": [{"id": "D1", "kind": "kb", "what": "KB covering the code, build, and a source map", "where": "kb"}],
 "terms": [{"term": "comprehensive", "means": "every top-level area has an article", "not": "code-quality judgements"}],
 "non_goals": ["No changes to the stratum repository"],
 "participants": [{"agent": "kb-author", "role": "author", "why": "Writes every article for D1."}],
 "review": "none", "budget_minutes": 180,
 "workspaces": [{"name": "kb", "path": "/abs/kb", "mode": "write"}, {"name": "src", "path": "/abs/repo", "mode": "read"}],
 "answers": [{"q": "What output?", "a": "<the human's words>"}]}
```

Kinds: `code`, `kb`, `docs`, `tutorial`, `education`, `research`, `pm`, `integration`.
Roles: `author`, `tests` (code), `reviewer`, `recon`.

`plan.json`:

```json
{"title": "...", "summary": "<= 80 words", "questions": [],
 "tasks": [{"id": "T01", "title": "Architecture overview", "serves": ["D1"], "agent": "kb-author",
   "workspace": "kb", "paths": ["architecture/overview.md"], "sources": ["src:internal/cluster/**"],
   "brief": "<= 150 words", "acceptance": ["..."], "checks": ["docs"], "estimate_min": 15, "depends_on": []}],
 "checks": {"vet": {"cmd": "go vet ./...", "cwd": "src"}}, "final_checks": ["docs-all"]}
```

Optional task fields: `test_cmd`, `tests_paths`, `test_mode` (code), `review: false`, `reviewer`,
and `model` (`sonnet`, `opus`, or `haiku`) for a cheaper step. Check commands may
use `{paths}`, `{ws:<name>}`, and `{tp}`.
