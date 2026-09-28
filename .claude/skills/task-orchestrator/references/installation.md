# Installation, verification, and maintenance

## Components

| Piece | Location |
| --- | --- |
| Skill (the orchestrator's procedure) | `~/.claude/skills/task-orchestrator/SKILL.md` + `references/` |
| State CLI | `~/.claude/skills/task-orchestrator/scripts/orch.py` (+ `scripts/orchestrator/`) |
| Hooks (one entry point) | `~/.claude/skills/task-orchestrator/scripts/hook.py` (`hook.py budget` for the per-agent budget hook) |
| Roster agents (19) | `~/.claude/agents/<name>.md` — names, models, and efforts in `scripts/orchestrator/roster.py`; each registers the budget hook in its frontmatter |
| Output style agents follow | `~/.claude/output-styles/answer-first.md` |
| Registry | `$TASK_ORCH_HOME` (default `~/.cache/task-orchestrator/`: `sessions/` bindings, `workflows/` catalog, `heartbeat.json`, `hook-errors.log`) |
| Tests | `~/.claude/skills/task-orchestrator/tests/` |

Stdlib-only Python, 3.9+ (the stock `/usr/bin/python3` on macOS, Rocky 9, Debian 11 is
3.9 — run the tests on it too). `git` is required (snapshots).

## Hook registration (`~/.claude/settings.json`)

One command handles every event; it is a no-op for sessions not bound to a workflow and
fails open on internal errors (logged to `hook-errors.log`).

```json
{
  "hooks": {
    "SessionStart": [{"matcher": "*", "hooks": [
      {"type": "command", "command": "python3 \"$HOME/.claude/skills/task-orchestrator/scripts/hook.py\"", "timeout": 10}]}],
    "UserPromptSubmit": [{"hooks": [
      {"type": "command", "command": "python3 \"$HOME/.claude/skills/task-orchestrator/scripts/hook.py\"", "timeout": 10}]}],
    "UserPromptExpansion": [{"hooks": [
      {"type": "command", "command": "python3 \"$HOME/.claude/skills/task-orchestrator/scripts/hook.py\"", "timeout": 10}]}],
    "PreToolUse": [{"matcher": "Edit|Write|MultiEdit|NotebookEdit|Bash|Agent|Task|Workflow", "hooks": [
      {"type": "command", "command": "python3 \"$HOME/.claude/skills/task-orchestrator/scripts/hook.py\"", "timeout": 10}]}],
    "SubagentStart": [{"hooks": [
      {"type": "command", "command": "python3 \"$HOME/.claude/skills/task-orchestrator/scripts/hook.py\"", "timeout": 10}]}],
    "SubagentStop": [{"hooks": [
      {"type": "command", "command": "python3 \"$HOME/.claude/skills/task-orchestrator/scripts/hook.py\"", "timeout": 20}]}],
    "Stop": [{"hooks": [
      {"type": "command", "command": "python3 \"$HOME/.claude/skills/task-orchestrator/scripts/hook.py\"", "timeout": 30,
       "statusMessage": "Checking task-orchestrator state"}]}]
  }
}
```

## The budget hook (agent frontmatter — no settings.json change)

The global PreToolUse matcher above never sees Read, Grep, Glob, WebSearch, WebFetch, or MCP
calls — most of what a researcher does. So every roster agent registers a second hook in
its own frontmatter, which applies to that agent's tool calls only:

```yaml
hooks:
  PreToolUse:
    - matcher: "*"
      hooks:
        - type: command
          command: python3 "$HOME/.claude/skills/task-orchestrator/scripts/hook.py" budget
          timeout: 10
```

It records each call in `<workflow>/.orch/agents/` (active time, the call log `orch agents
<id> --calls` shows) and stops the agent at its time budget or when the human pauses (see
[execution.md](execution.md#interim-reports-time-budgets)). It costs one short Python run
per tool call of a roster agent, and nothing anywhere else. `orch doctor` checks that every
agent file pins the roster's model and effort and registers this hook.

What each does:

| Event | Behavior (bound sessions only) |
| --- | --- |
| SessionStart | Injects the workflow, phase, and next action; after compaction also re-injects the core rules. On `resume`/`startup` (a new process — e.g. `claude -r` after a reboot, which keeps the session id) it marks agents still recorded as running INTERRUPTED and closes their clocks at their last tool call. |
| UserPromptSubmit | Records what the human actually typed in the ledger — the only source of approvals and decisions. Counts only `source` `user`/`sdk` (or absent); `system` (peer messages, task notifications, auto-continuations) and wakeups are never human. Parses both the raw `/task-orchestrator …` form and the `<command-name>` form. In an **unbound** session it records one thing: `/task-orchestrator resume <dir \| workflow-id>`, into the named workflow's ledger, so un-halting after a restart needs the command only once. |
| UserPromptExpansion | Records user-typed `/task-orchestrator` slash commands from `command_name` + `command_args` (deduplicated against UserPromptSubmit); the same unbound `resume` rule. |
| PreToolUse | Refuses: any reference to `.orch/`; edits to generated files, `decisions.md`, frozen plan documents after approval, other agents' reports; workspace edits by the orchestrator or read-only roles; author edits outside declared workspaces; non-roster agents, hand-written (non-`orch brief`) dispatch prompts, the Workflow tool, any dispatch while the human's pause is pending or in force, and an 8th planning research agent while 7 run; `scope.md` edits by anyone but the orchestrator (and by anyone after approval); orchestrator-only `orch` commands from subagents (in either the `orch.py …` or the `$ORCH …` form). |
| SubagentStart | Injects the roster contract (the two-sided mandate, the confirmed scope and non-goals, scope proposals, the budget rules, the answer-first output style) into roster agents; opens the agent's activity record and logs a `dispatch` entry. Into any **other** sub-agent while a workflow is bound — a skill's fan-out helper — it injects a short scope line ("answer only the question your parent gave you; record, don't investigate"). Unverified live: whether it fires for agents that sub-agents start; `orch doctor` shows `last SubagentStart-helper` once it has. |
| SubagentStop | Parses the roster agent's `orch-result` block from `last_assistant_message`, or — when that has none — from the agent's latest SubagentHandback `input.message` since its previous stop (read from `agent_transcript_path`; `result_source` in the ledger says which). Validates it and appends it to the ledger with the harness-supplied agent type (writes the report from that message if the agent forgot to). Closes the agent's activity segment (the clock pauses) and, for an `interim` result, records why it stopped (`time`, `pause`, or `self`). |
| Budget (`hook.py budget`, agent frontmatter) | Every tool call of a roster agent: logs it, and past the agent's time budget — or while the human's pause applies to a read-only role — refuses every call except writing its interim report and SubagentHandback. |
| Stop | Main session only. Plan-hash, task-set, and acceptance integrity checks; wait-aware continuation while background agents run (capped when nothing progresses); a continuation budget; forces the loop to keep working until a human boundary, quoting the next action and the quality mandate. |

Verified payload facts behind these (Claude Code 2.1.282 — observed live, or read from the
binary's hook input schemas): subagent PreToolUse/SubagentStop payloads carry the **parent**
session's `session_id` plus `agent_id`/`agent_type`; SubagentStop carries
`last_assistant_message` and fires again after every SendMessage resume, and cannot block;
UserPromptSubmit carries `prompt` and `source`; UserPromptExpansion carries
`expansion_type`, `command_name`, `command_args`; Stop carries `background_tasks`
("in-flight background work … empty array when nothing is in flight"). The Stop hook keeps
the first 25 real payload shapes in `$TASK_ORCH_HOME/stop-payload-samples.jsonl`. In the
transcript, a hand-back is a `queue-operation` / `queued_command` record and a SendMessage
resume is a `toolUseResult` with `resumedAgentId`. In a subagent's own transcript
(`agent_transcript_path`, observed on 2.1.283), a SubagentHandback call is an `assistant`
record with a `tool_use` block named `SubagentHandback` whose `input.message` is the
delivered report; agents often follow it with a short closing text that lacks the result
block, so `last_assistant_message` alone is not enough.

Read from the 2.1.283 binary (not yet observed live — the selftest's budget step checks the
first two):

- Hooks in an agent definition's frontmatter are registered under that agent's id, apply
  only to its own tool calls, and are cleared when it ends. Matcher `"*"` (or empty) matches
  every tool, MCP tools included.
- PreToolUse hook output accepts `permissionDecision` (`allow`/`deny`/`ask`/`defer`),
  `permissionDecisionReason`, `updatedInput`, and `additionalContext`.
- Agent frontmatter keys include `model`, `effort`, `hooks`, and `maxTurns` (a turn cap that
  ends the agent with a partial result — not used here); there is no time-limit key.
  Model aliases: `fable` → claude-fable-5-1, `opus` → claude-opus-5-5, `sonnet` →
  claude-sonnet-5, `haiku` → claude-haiku-4-5.
- `claude --resume` keeps the original session id unless `--fork-session` is given, so a
  resumed session keeps its binding. SendMessage to an agent id reloads it from
  `<session>/subagents/agent-<id>.jsonl`.
- Sub-agents that a roster agent's skill starts do not inherit its frontmatter hooks, so
  the budget sees the parent's next tool call after they return, not their own calls.

## Verify

```bash
python3 ~/.claude/skills/task-orchestrator/scripts/orch.py doctor
```

checks the roster files (each one's model, effort, and budget hook), the output style
file, hook registration, recent hook activity (including the budget hook), git, and the
registry.

End-to-end (in a fresh, unbound session, after a restart so new agents and hooks load):

1. `/task-orchestrator selftest` → the orchestrator runs `orch selftest`, which creates a
   scratch workflow with a 0-minute budget for project-manager, binds the session, and
   prints a brief.
2. The orchestrator dispatches `project-manager` with that brief. Its one Read call is
   refused by the budget hook, and it hands back an interim report.
3. The human types `/task-orchestrator status`.
4. `orch selftest --check` confirms: SubagentStop recorded the result, the agent type came
   from the harness, the block validated, SubagentStart injected the contract, PreToolUse
   is live, the agent's frontmatter budget hook saw its calls and stopped it, the interim
   report was accepted, and the human's typed command was captured as a command (it prints
   the raw captured prompt, which hook saw it, and its `source`). It unbinds and cleans up
   on success.

Unit tests:

```bash
cd ~/.claude/skills/task-orchestrator/tests
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s . -t .
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest discover -s . -t .
```

## Permissions for unattended runs

Roster agents run in the background. **Any permission prompt stalls the pipeline** until
someone answers it (a live selftest spent 9½ minutes waiting on two Read prompts for files
outside the project directory). Before a real run, make sure these need no prompt:

- **Read** and **Edit/Write** for the workflow location and every workspace: keep them inside
  the project directory, or add rules such as `Read(~/path/to/plans/**)` and
  `Edit(~/path/to/plans/**)` (the notebook `projects/substrate` and `projects/fuzzball` paths
  already have them).
- **Read** for `~/.cache/task-orchestrator/**` if you run the selftest (its scratch workflow
  lives there).
- **Bash** for `python3 ".../task-orchestrator/scripts/orch.py" ...`: sandboxed Bash is
  auto-approved in this setup; if yours prompts, allow
  `Bash(python3 */task-orchestrator/scripts/orch.py *)`, plus the workspaces' gate commands
  (note `Bash(python *)` does not cover `python3`).

The CLI and hooks never need extra permissions. Hooks run outside the sandbox, and the CLI
writes only the workflow directory, the workspaces' git object stores (snapshots), and
`$TASK_ORCH_HOME`.

## Sandbox notes

- The CLI runs under the Bash sandbox: the workflow directory and every workspace must be
  writable from it (the project directory, or paths in `sandbox.filesystem.allowWrite`).
  `orch init` reports a clear error otherwise.
- The registry defaults to `~/.cache/task-orchestrator` because `~/.claude` is not
  writable from sandboxed Bash. Losing it only loses session bindings and the workflow
  catalog; `orch bind <dir>` restores both for that workflow.
- Hooks run outside the sandbox.

## Tuning

State fields (change them only through a plan revision conversation with the human):
`budgets.task_attempts` (3), `budgets.review_passes` (3), `budgets.final_review_passes` (3),
`budgets.time_grants` (2 PM-approved extensions per agent), `budgets.agent_minutes`
(active minutes per dispatch by agent type — 30 for the researchers and liaisons; a type not
listed is logged, not limited), `max_stop_continuations` (150), `max_consecutive_waits` (40).
The defaults live in `scripts/orchestrator/roster.py`, as do each agent's model and effort.

## Uninstall

Remove the seven hook entries from `~/.claude/settings.json`, then delete
`~/.claude/skills/task-orchestrator/`, the roster agent files (their frontmatter budget hook
goes with them), and `~/.cache/task-orchestrator/`. Workflow directories are ordinary
folders and remain as records.
