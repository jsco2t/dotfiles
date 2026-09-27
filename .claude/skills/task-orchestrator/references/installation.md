# Installation, verification, and maintenance

## Components

| Piece | Location |
| --- | --- |
| Skill (the orchestrator's procedure) | `~/.claude/skills/task-orchestrator/SKILL.md` + `references/` |
| State CLI | `~/.claude/skills/task-orchestrator/scripts/orch.py` (+ `scripts/orchestrator/`) |
| Hooks (one entry point) | `~/.claude/skills/task-orchestrator/scripts/hook.py` |
| Roster agents (19) | `~/.claude/agents/<name>.md` — names in `scripts/orchestrator/roster.py` |
| Session registry | `$TASK_ORCH_HOME` (default `~/.cache/task-orchestrator/`: `sessions/`, `heartbeat.json`, `hook-errors.log`) |
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

What each does:

| Event | Behavior (bound sessions only) |
| --- | --- |
| SessionStart | Injects the workflow, phase, and next action; after compaction also re-injects the core rules. |
| UserPromptSubmit | Records what the human actually typed in the ledger — the only source of approvals and decisions. Counts only `source` `user`/`sdk` (or absent); `system` (peer messages, task notifications, auto-continuations) and wakeups are never human. Parses both the raw `/task-orchestrator …` form and the `<command-name>` form. |
| UserPromptExpansion | Records user-typed `/task-orchestrator` slash commands from `command_name` + `command_args` (deduplicated against UserPromptSubmit). |
| PreToolUse | Refuses: any reference to `.orch/`; edits to generated files, `decisions.md`, frozen plan documents after approval, other agents' reports; workspace edits by the orchestrator or read-only roles; author edits outside declared workspaces; non-roster agents, hand-written (non-`orch brief`) dispatch prompts, and the Workflow tool from the orchestrator; orchestrator-only `orch` commands from subagents (in either the `orch.py …` or the `$ORCH …` form). |
| SubagentStart | Injects the roster contract into roster agents. |
| SubagentStop | Parses the roster agent's `orch-result` block from `last_assistant_message`, or — when that has none — from the agent's latest SubagentHandback `input.message` since its previous stop (read from `agent_transcript_path`; `result_source` in the ledger says which). Validates it and appends it to the ledger with the harness-supplied agent type (writes the report from that message if the agent forgot to). |
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

## Verify

```bash
python3 ~/.claude/skills/task-orchestrator/scripts/orch.py doctor
```

checks the roster files, hook registration, recent hook activity, git, and the registry.

End-to-end (in a fresh, unbound session, after a restart so new agents and hooks load):

1. `/task-orchestrator selftest` → the orchestrator runs `orch selftest`, which creates a
   scratch workflow, binds the session, and prints a brief.
2. The orchestrator dispatches `project-manager` with that brief.
3. The human types `/task-orchestrator status`.
4. `orch selftest --check` confirms: SubagentStop recorded the result, the agent type came
   from the harness, the block validated, SubagentStart injected the contract, PreToolUse
   is live, and the human's typed command was captured as a command (it prints the raw
   captured prompt, which hook saw it, and its `source`). It unbinds and cleans up on success.

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
  writable from sandboxed Bash. Losing it only loses session bindings; `orch bind <dir>`
  restores one.
- Hooks run outside the sandbox.

## Tuning

State fields (change them only through a plan revision conversation with the human):
`budgets.task_attempts` (3), `budgets.review_passes` (3), `budgets.final_review_passes` (3),
`max_stop_continuations` (150), `max_consecutive_waits` (40).

## Uninstall

Remove the seven hook entries from `~/.claude/settings.json`, then delete
`~/.claude/skills/task-orchestrator/`, the roster agent files, and `~/.cache/task-orchestrator/`.
Workflow directories are ordinary folders and remain as records.
