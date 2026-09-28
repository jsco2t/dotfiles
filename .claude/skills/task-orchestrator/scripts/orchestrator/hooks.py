"""Hook handlers. Every handler is a no-op unless the session is bound to a
workflow, and every handler fails OPEN (allow / no output) on an internal
error — a broken hook must never wedge a Claude Code session. Errors are logged
to $TASK_ORCH_HOME/hook-errors.log.

Verified payload facts (Claude Code 2.1.282):
* `session_id` inside a subagent's PreToolUse/SubagentStop payload is the
  PARENT session's id, so one binding lookup covers the whole team.
* `agent_type` is the bare agent name for ~/.claude/agents definitions and is
  absent in the main session (as is `agent_id`).
* SubagentStop carries `last_assistant_message` and fires again each time a
  resumed (SendMessage) agent finishes. It cannot block.
* (2.1.283) Subagents may deliver their report through the SubagentHandback
  tool and then write a short closing message, so the result block can live only
  in the hand-back call's `input.message` in `agent_transcript_path` (the
  subagent's own transcript).
* (2.1.283, read from the binary) Hooks declared in an agent definition's
  frontmatter are registered under that agent's id, apply only to its own tool
  calls, and are cleared when it ends; matcher "*" matches every tool, MCP tools
  included. Every roster agent registers `hook.py budget` that way, which is how
  the time budget sees Read/Grep/WebFetch calls the global matcher does not.
"""
from __future__ import annotations

import json
import os
import re
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import activity
from .common import (
    ACTIVE_PHASES,
    QUALITY_MANDATE,
    SKILL_DIR,
    STOP_PHASES,
    Workflow,
    find_workflow,
    get_binding,
    orch_home,
    read_json,
    sha256_text,
    utcnow,
    write_json_atomic,
)
from .roster import (
    AUTHORS,
    LIAISONS,
    MAX_PARALLEL_RESEARCH,
    PLANNERS,
    READONLY,
    RECORD_DONT_INVESTIGATE,
    RESEARCHERS,
    ROSTER,
)

FILE_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
AGENT_TOOLS = frozenset({"Agent", "Task"})
REPORT_DIRS = ("runs", "research", "reviews", "loops", "final")
SUBAGENT_ORCH_COMMANDS = frozenset({"status", "evidence", "gate", "snapshot", "ledger", "validate", "plan-hash",
                                    "where", "wait", "agents"})
OUTPUT_STYLE = Path.home() / ".claude" / "output-styles" / "answer-first.md"
SKILL_FILE = SKILL_DIR / "SKILL.md"
HUMAN_SOURCES = (None, "user", "sdk")
SUBAGENT_TASK_COMMANDS = frozenset({"diff", "scan", "status"})
SYNTHETIC_PROMPT_PREFIXES = ("<agent-message", "<task-notification", "<cross-session-message", "[SYSTEM NOTIFICATION")


# ---------------------------------------------------------------- plumbing


def log_error(event: str, exc: BaseException) -> None:
    try:
        path = orch_home() / "hook-errors.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"{utcnow()} {event}: {exc!r}\n{traceback.format_exc()}\n")
    except Exception:
        pass


def heartbeat(event: str) -> None:
    try:
        path = orch_home() / "heartbeat.json"
        data = read_json(path, default={}) or {}
        data[event] = utcnow()
        write_json_atomic(path, data)
    except Exception:
        pass


def bound_workflow(payload: Dict[str, Any]) -> Optional[Tuple[Workflow, Dict[str, Any]]]:
    session = payload.get("session_id")
    binding = get_binding(session)
    if binding is None:
        # Fallback: derive the parent session from a subagent transcript path
        # (.../<session>/subagents/agent-<id>.jsonl).
        for key in ("agent_transcript_path", "transcript_path"):
            path = payload.get(key)
            if isinstance(path, str) and "/subagents/" in path:
                binding = get_binding(Path(path).parent.parent.name)
                if binding:
                    break
    if binding is None:
        return None
    wf = Workflow(Path(binding["workflow_dir"]))
    state = read_json(wf.state_path)
    if not isinstance(state, dict):
        return None
    return wf, state


def deny(reason: str) -> Dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"task-orchestrator: {reason}",
        }
    }


# ---------------------------------------------------------------- PreToolUse


def _resolve(path_text: str, cwd: Optional[str]) -> Path:
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = Path(cwd or os.getcwd()) / path
    return Path(os.path.realpath(path))


def _workspaces(wf: Workflow) -> Dict[str, Path]:
    gate = read_json(wf.gate, default={}) or {}
    out = {}
    for name, entry in (gate.get("workspaces") or {}).items():
        if isinstance(entry, dict) and isinstance(entry.get("path"), str):
            out[name] = Path(os.path.realpath(Path(entry["path"]).expanduser()))
    return out


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _workflow_write(wf: Workflow, state: Dict[str, Any], path: Path, caller: str, is_main: bool) -> Optional[str]:
    rel = path.relative_to(wf.root)
    parts = rel.parts
    phase = state.get("phase")
    if not parts:
        return "the workflow directory itself cannot be written"
    if parts[0] == ".orch":
        return "`.orch/` is owned by the orch CLI and hooks; use `orch` commands to change state"
    if wf.is_generated_path(path):
        return f"`{rel}` is generated by `orch render`; it is rewritten from state automatically"
    if path == wf.decisions:
        return "decisions.md is append-only; add clarifications with `orch note --file <path>`"
    if path == wf.halt_path:
        return None
    if wf.is_frozen_path(path):
        if phase != "PLANNING":
            return (f"`{rel}` is part of the approved plan and is frozen. If the plan cannot be followed, "
                    "record it with `orch deviation --summary ...` and stop for the human")
        if path == wf.request:
            return None if is_main else "only the orchestrator records request.md"
        if path == wf.scope:
            return None if is_main else "only the orchestrator drafts scope.md; the human confirms it"
        if caller in PLANNERS:
            return None
        return (f"plan documents are written by planning-author (and test-planner for the test plan); "
                f"`{caller}` may not write `{rel}`")
    if parts[0] in REPORT_DIRS:
        suffix = f".{caller}.md"
        if path.name.endswith(suffix):
            return None
        return (f"report files are named `<nn>-<stage>.<agent>.md` and each agent writes only its own; "
                f"`{caller}` may write only files ending in `{suffix}` (use the report path from your brief)")
    return f"`{rel}` is not a plan document or an agent report; nothing else belongs in the workflow directory"


ORCH_CALL_RE = re.compile(
    r"(?:orch\.py[\"']*|\$\{?ORCH\}?)[ \t]+(?:--wf[ \t]+\S+[ \t]+)?([a-z][a-z-]*)(?:[ \t]+([a-z][a-z-]*))?"
)
ORCH_MENTION_RE = re.compile(r"orch\.py|\$\{?ORCH\b")
CONTROL_MENTION_RE = re.compile(r"(?:^|[\s'\"=/:(])\.orch(?:/|\b)")


def _orch_invocations(command: str) -> List[Tuple[str, str]]:
    """Every `orch.py <sub> [<sub2>]` / `$ORCH <sub> [<sub2>]` call in a command."""
    return [(m.group(1), m.group(2) or "") for m in ORCH_CALL_RE.finditer(command)]


def pretool_policy(payload: Dict[str, Any], wf: Workflow, state: Dict[str, Any]) -> Optional[str]:
    """Reason to deny this tool call, or None to allow it."""
    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    agent = payload.get("agent_type")
    is_main = not payload.get("agent_id")
    caller = "orchestrator" if is_main else (agent or "unknown-agent")
    phase = state.get("phase")

    if tool == "Workflow":
        return "this process never uses the Workflow tool; orchestrate with roster subagents (Agent tool)"

    if tool in AGENT_TOOLS:
        if is_main and activity.pause_requested(wf, state):
            return ("the human paused this workflow: dispatch nothing new. Agents already running finish or "
                    "write interim reports; end your turn (it becomes HALTED) and wait for "
                    "`/task-orchestrator resume`")
        if is_main and phase in (ACTIVE_PHASES | {"PLANNING"}):
            wanted = tool_input.get("subagent_type")
            if wanted not in ROSTER:
                return (f"this process uses pre-defined roster agents only; `{wanted}` is not one "
                        f"(roster: {', '.join(sorted(ROSTER))})")
            if phase == "PLANNING" and wanted in (RESEARCHERS | LIAISONS):
                from . import ledger

                running = [r for r in activity.summaries(wf, state, ledger.read(wf))
                           if r["status"] == "running" and r["agent_type"] in (RESEARCHERS | LIAISONS)]
                if len(running) >= MAX_PARALLEL_RESEARCH:
                    return (f"{len(running)} research agents are already running (the limit is "
                            f"{MAX_PARALLEL_RESEARCH}); end your turn and dispatch this one when one hands back")
            return _brief_problem(wf, str(wanted), str(tool_input.get("prompt") or ""))
        return None

    if tool in FILE_TOOLS:
        raw = tool_input.get("file_path") or tool_input.get("notebook_path")
        if not isinstance(raw, str) or not raw:
            return None
        path = _resolve(raw, payload.get("cwd"))
        if _within(path, wf.root):
            return _workflow_write(wf, state, path, caller, is_main)
        if agent in READONLY:
            return f"`{agent}` is a read-only role; it may write only its own report inside the workflow directory"
        if is_main and phase in (ACTIVE_PHASES | {"PLANNING"}):
            return ("the orchestrator delegates all deliverable work to roster author agents; it does not "
                    "edit workspace files itself")
        if agent in (AUTHORS | PLANNERS):
            spaces = _workspaces(wf)
            if not any(_within(path, root) for root in spaces.values()):
                return f"`{agent}` may write only inside the declared workspaces ({', '.join(str(p) for p in spaces.values())})"
        return None

    if tool == "Bash":
        command = str(tool_input.get("command") or "")
        if str(wf.control) in command or CONTROL_MENTION_RE.search(command):
            return ("`.orch/` is owned by the orch CLI and hooks — no command may reference it; "
                    "read state with `orch status` / `orch ledger`")
        if not is_main and ORCH_MENTION_RE.search(command):
            calls = _orch_invocations(command)
            if not calls:
                return ("could not identify the orch subcommand; call it plainly as "
                        "`python3 \"$HOME/.claude/skills/task-orchestrator/scripts/orch.py\" <subcommand> ...`")
            for sub, sub2 in calls:
                if sub == "task":
                    if sub2 not in SUBAGENT_TASK_COMMANDS:
                        return f"only the orchestrator runs `orch task {sub2}`"
                elif sub not in SUBAGENT_ORCH_COMMANDS:
                    return f"only the orchestrator runs `orch {sub}`"
        return None
    return None


BRIEF_REPORT_RE = re.compile(r"Write your full report to `([^`]+)`")


def _brief_problem(wf: Workflow, agent: str, prompt: str) -> Optional[str]:
    """Roster dispatches must carry a saved `orch brief` verbatim (auditable by the PM)."""
    match = BRIEF_REPORT_RE.search(prompt)
    if not match:
        return "dispatch roster agents with the exact output of `orch brief ... --agent <agent>` as the prompt"
    report = Path(os.path.realpath(match.group(1)))
    if not _within(report, wf.root):
        return "the brief's report path is not inside this workflow directory"
    if not report.name.endswith(f".{agent}.md"):
        return f"that brief was generated for a different agent than `{agent}`"
    brief = report.parent / "briefs" / report.name
    try:
        text = brief.read_text(encoding="utf-8").strip()
    except OSError:
        return "no saved brief matches this prompt; generate it with `orch brief`"
    if text not in prompt:
        return ("the prompt must contain the generated brief verbatim; put extra context in "
                "`orch brief ... --note-file <path>` instead of editing it")
    return None


# ---------------------------------------------------------------- handlers


def handle_pretool(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    bound = bound_workflow(payload)
    if bound is None:
        return None
    wf, state = bound
    heartbeat("PreToolUse")
    reason = pretool_policy(payload, wf, state)
    return deny(reason) if reason else None


def _record_human(wf: Workflow, parsed: Optional[Tuple[str, List[str]]], raw: str, via: str,
                  source: Optional[str]) -> None:
    """Append a human entry, skipping the duplicate when both prompt hooks see one command."""
    from . import ledger
    from .common import parse_ts

    verb = parsed[0] if parsed else None
    args = (parsed[1] if parsed else [])[:60]
    if verb is not None:
        # One typed command reaches both prompt hooks; the same hook twice is the human typing it twice.
        hook = via.split(" (")[0]
        recent = [e for e in ledger.read(wf)[-5:] if e.get("kind") == "human"]
        now = parse_ts(utcnow())
        for entry in recent:
            stamp = parse_ts(entry.get("ts"))
            if (entry.get("verb") == verb and entry.get("args") == args and stamp and now
                    and str(entry.get("via") or "").split(" (")[0] != hook
                    and (now - stamp).total_seconds() < 15):
                return
    ledger.append(wf, {"kind": "human", "verb": verb, "args": args, "raw": raw[:4000],
                       "prompt_sha": sha256_text(raw)[:16], "via": via, "source": source})


def _resume_target(parsed: Optional[Tuple[str, List[str]]]) -> Optional[Workflow]:
    """The workflow a `/task-orchestrator resume <dir | workflow-id>` names, for an unbound session.

    A fresh session is not bound yet, so without this the human's resume would reach
    no ledger and un-halting would need the command typed twice. The capture is still
    the hook recording what the human typed; only the target comes from the argument.
    """
    if not parsed or parsed[0] != "resume" or not parsed[1]:
        return None
    root = find_workflow(parsed[1][0])
    return Workflow(root) if root else None


def handle_user_prompt(payload: Dict[str, Any]) -> None:
    prompt = payload.get("prompt")
    if not isinstance(prompt, str):
        return
    # Only a human at the composer (or the SDK entrypoint) counts. `system` covers
    # peer messages, task notifications, and auto-continuations; wakeups are not humans.
    source = payload.get("source")
    if source not in HUMAN_SOURCES:
        return
    stripped = prompt.lstrip()
    if stripped.startswith(SYNTHETIC_PROMPT_PREFIXES) or "[Subagent hand-back]" in prompt[:400]:
        return
    from . import ledger

    parsed = ledger.parse_human_command(prompt)
    bound = bound_workflow(payload)
    via = "UserPromptSubmit"
    if bound is None:
        target = _resume_target(parsed)
        if target is None:
            return
        wf, via = target, "UserPromptSubmit (unbound session)"
    else:
        wf = bound[0]
    _record_human(wf, parsed, prompt, via, source)
    heartbeat("UserPromptSubmit")


def handle_user_prompt_expansion(payload: Dict[str, Any]) -> None:
    """User-typed slash commands, before expansion (command_name + command_args)."""
    if payload.get("expansion_type") not in (None, "slash_command"):
        return
    from . import ledger

    parsed = ledger.parse_command_parts(payload.get("command_name"), payload.get("command_args"))
    if parsed is None:
        return
    bound = bound_workflow(payload)
    via = "UserPromptExpansion"
    if bound is None:
        target = _resume_target(parsed)
        if target is None:
            return
        wf, via = target, "UserPromptExpansion (unbound session)"
    else:
        wf = bound[0]
    raw = f"/{str(payload.get('command_name')).lstrip('/')} {payload.get('command_args') or ''}".strip()
    _record_human(wf, parsed, raw, via, "user")
    heartbeat("UserPromptExpansion")


CONTRACT = """TASK-ORCHESTRATOR CONTRACT (injected by the SubagentStart hook)
Workflow `{workflow_id}` — directory {root}
- You are a pre-defined roster agent. Your dispatch brief defines your stage, the identity values to echo, the files to read in full, and your report path.
- Read {decisions} first: it holds clarifications and human decisions that bind every agent.
- You cannot ask the user anything (AskUserQuestion is unavailable to subagents). If you need input, finish with status "needs_input" and list your questions; the orchestrator resumes you with answers. Never guess to fill a gap.
- Write only your own report file (its name ends in `.{agent}.md`). Never edit `.orch/`, plan documents after approval, generated index files, or another agent's report — hooks will refuse.
- Judge the snapshot you were given. If the workspace changes under you, say so in your report.
- Finish with the ```orch-result block from your brief, every placeholder replaced. If you hand back with SubagentHandback, end that message with the block; either way, also end your final text message with it. Without a valid block your work is not recorded.
- Scope: {non_goals} {record}{scope_line}
- Exactly what was asked — not less, and not more. If you believe the plan missed something the human needs, never do it: raise it in `scope_proposals` (your brief says how). If you hit something the plan does not cover, stop (`blocked`) and say so answer-first: what you hit, what needs deciding, the options.
- The budget hook may stop you — when your time budget is reached, the planning research window closes, or the human pauses the workflow. Every tool call except writing your interim report is then refused: follow its message and your brief's "If you are stopped" section.
- Output style: write your report and your final message answer-first, as {style} defines it — read it before you write. The point first, then only the explanation the reader needs; every finding leads with its state; complete sentences; tables only for short, uniform values. Reviewers always give each finding's confidence score.
- {mandate}"""

HELPER_CONTRACT = """TASK-ORCHESTRATOR SCOPE (injected by the SubagentStart hook)
You are a helper started by an agent of task-orchestrator workflow `{workflow_id}`. Answer only the question your parent gave you, as far as it needs and no further. {record} Change no files unless your parent's instructions explicitly require it. Report answer-first: the answer, then its evidence."""


def handle_subagent_start(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    agent = payload.get("agent_type")
    if agent not in ROSTER:
        return _helper_start(payload)
    bound = bound_workflow(payload)
    if bound is None:
        return None
    wf, state = bound
    heartbeat("SubagentStart")
    from . import ledger
    from .roster import LEGACY_KIND, NON_GOALS

    try:
        info = activity.start(wf, payload)
        ledger.append(wf, {"kind": "dispatch", "agent_type": agent, "agent_id": payload.get("agent_id"),
                           "resumed": bool(info.get("resumed"))})
    except Exception as exc:  # the contract still goes out
        log_error("SubagentStart activity", exc)
    kind = state.get("kind") or LEGACY_KIND
    scope_line = (f" Read {wf.scope}: the scope the human confirmed — work only in its deliverables and significant "
                  "terms." if wf.scope.is_file() else "")
    text = CONTRACT.format(
        workflow_id=state.get("workflow_id"), root=wf.root, decisions=wf.decisions, agent=agent,
        mandate=QUALITY_MANDATE, non_goals=NON_GOALS.get(kind, NON_GOALS[LEGACY_KIND]),
        record=RECORD_DONT_INVESTIGATE, style=OUTPUT_STYLE, scope_line=scope_line,
    )
    return {"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": text}}


def _helper_start(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """A non-roster sub-agent (a skill's fan-out) while a workflow is bound: give it the scope line.

    Unverified live: whether SubagentStart fires for agents started by sub-agents.
    `heartbeat("SubagentStart-helper")` records it when it does (`orch doctor` shows it).
    """
    bound = bound_workflow(payload)
    if bound is None:
        return None
    _, state = bound
    heartbeat("SubagentStart-helper")
    text = HELPER_CONTRACT.format(workflow_id=state.get("workflow_id"), record=RECORD_DONT_INVESTIGATE)
    return {"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": text}}


def handle_budget(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The budget hook: every tool call of a roster agent (frontmatter PreToolUse, matcher "*")."""
    if payload.get("hook_event_name") not in (None, "PreToolUse") or not payload.get("agent_id"):
        return None
    if payload.get("agent_type") not in ROSTER:
        return None
    bound = bound_workflow(payload)
    if bound is None:
        return None
    wf, state = bound
    heartbeat("Budget")
    reason = activity.on_tool(wf, state, payload)
    return deny(reason) if reason else None


HANDBACK_TOOL = "SubagentHandback"


def _handback_messages(path: Path, since: Optional[str]) -> List[Tuple[str, str]]:
    """(tool_use id, message) of each delivered SubagentHandback call after `since`, oldest first.

    A call whose tool_result is an error never reached the orchestrator and is skipped.
    """
    from .common import parse_ts

    floor = parse_ts(since) if since else None
    calls: List[Tuple[str, str]] = []
    failed = set()
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            content = (record.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_result" and block.get("is_error"):
                    failed.add(block.get("tool_use_id"))
                if (record.get("type") != "assistant" or block.get("type") != "tool_use"
                        or block.get("name") != HANDBACK_TOOL):
                    continue
                stamp = parse_ts(record.get("timestamp"))
                if floor is not None and (stamp is None or stamp <= floor):
                    continue
                text = (block.get("input") or {}).get("message")
                if isinstance(text, str):
                    calls.append((str(block.get("id")), text))
    return [call for call in calls if call[0] not in failed]


def _handback_result(wf: Workflow, payload: Dict[str, Any]) -> Optional[Tuple[str, str, Dict[str, Any]]]:
    """The result block from this turn's latest SubagentHandback call, as (tool_use id, message, result).

    Only hand-backs made since this agent's previous stop count, so a resumed turn
    can never be credited with an earlier turn's result. Fails closed (None).
    """
    from . import ledger

    try:
        path = payload.get("agent_transcript_path")
        if not isinstance(path, str) or not path:
            return None
        agent_id = payload.get("agent_id")
        previous = [e for e in ledger.read(wf)
                    if e.get("kind") == "agent_result" and agent_id and e.get("agent_id") == agent_id]
        since = ledger.latest(previous).get("ts") if previous else None
        for tool_use_id, text in reversed(_handback_messages(Path(path), since)):
            result, error = ledger.parse_result_block(text)
            if result is not None and not error:
                return tool_use_id, text, result
    except Exception as exc:
        log_error("SubagentStop hand-back fallback", exc)
    return None


def handle_subagent_stop(payload: Dict[str, Any]) -> None:
    agent = payload.get("agent_type")
    if agent not in ROSTER:
        return
    bound = bound_workflow(payload)
    if bound is None:
        return
    wf, state = bound
    from . import ledger

    message = payload.get("last_assistant_message") or ""
    result, error = ledger.parse_result_block(message)
    source = "final_message"
    handback_id = None
    if error:
        found = _handback_result(wf, payload)
        if found is not None:
            handback_id, message, result = found
            source, error = "handback", None
        elif error == ledger.MISSING_BLOCK:
            error = ledger.NO_BLOCK_ERROR
    errors = [error] if error else ledger.validate_result(result or {}, agent, wf, state)
    entry: Dict[str, Any] = {
        "kind": "agent_result",
        "agent_type": agent,
        "agent_id": payload.get("agent_id"),
        "valid": not errors,
        "errors": errors,
        "result": result or {},
        "result_source": source,
        "message_chars": len(message),
        "agent_transcript": payload.get("agent_transcript_path"),
    }
    if handback_id:
        entry["handback_tool_use_id"] = handback_id
    try:
        info = activity.stop(wf, payload)
    except Exception as exc:
        log_error("SubagentStop activity", exc)
        info = None
    if info is not None:
        entry["active_minutes"] = activity.active_minutes(info)
        if (result or {}).get("status") == "interim":
            # Why it stopped: the budget hook's reason, or `self` if it stopped on its own.
            entry["interim_reason"] = info.get("stop_reason") or "self"
    if result:
        report = ledger.report_path(result, wf)
        if report is not None and not report.exists() and report.name.endswith(f".{agent}.md"):
            try:
                if report.resolve().relative_to(wf.root):
                    report.parent.mkdir(parents=True, exist_ok=True)
                    report.write_text(message + "\n", encoding="utf-8")
                    entry["report_written_by_hook"] = True
            except (ValueError, OSError):
                pass
    ledger.append(wf, entry)
    heartbeat("SubagentStop")


def handle_session_start(payload: Dict[str, Any]) -> Optional[str]:
    bound = bound_workflow(payload)
    if bound is None:
        return None
    wf, state = bound
    heartbeat("SessionStart")
    swept: List[str] = []
    if payload.get("source") in ("resume", "startup"):
        # A new process: no background agent from before it survived. (`clear` and
        # `compact` happen inside a live process whose agents may still be running.)
        try:
            swept = activity.sweep_interrupted(wf)
        except Exception as exc:
            log_error("SessionStart sweep", exc)
    try:
        from .gates import Context, next_action

        nxt = next_action(Context(wf, fast=True))
    except Exception:
        nxt = "run `orch status`"
    lines = [
        f"task-orchestrator: this session drives workflow `{state.get('workflow_id')}` ({wf.root}), "
        f"phase {state.get('phase')}.",
        f"NEXT: {nxt}",
        f"State lives on disk. Re-read {SKILL_FILE} (the orchestrator procedure) and run "
        f"`python3 \"{SKILL_DIR / 'scripts' / 'orch.py'}\" status` rather than relying on memory; "
        "continue with `/task-orchestrator resume`.",
    ]
    if swept:
        lines.append(f"Agents that were running when the previous process ended are INTERRUPTED: "
                     f"{', '.join(swept)} (`orch agents`).")
    if payload.get("source") == "compact":
        lines += [
            QUALITY_MANDATE,
            "Rules that survive compaction: use only roster agents; dispatch every agent with `orch brief`; "
            "never edit .orch/ or frozen plan documents; approval and every human decision come only from "
            "the human's own /task-orchestrator command; every verdict must be at the current snapshot.",
        ]
    return "\n".join(lines)


def _sample_stop_payload(payload: Dict[str, Any], limit: int = 25) -> None:
    """Keep the first few real Stop payload shapes (keys + background_tasks) for diagnosis."""
    try:
        path = orch_home() / "stop-payload-samples.jsonl"
        if path.exists():
            with open(path, encoding="utf-8") as handle:
                if sum(1 for _ in handle) >= limit:
                    return
        path.parent.mkdir(parents=True, exist_ok=True)
        sample = {"at": utcnow(), "keys": sorted(payload.keys()),
                  "background_tasks": payload.get("background_tasks"),
                  "stop_hook_active": payload.get("stop_hook_active")}
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(sample) + "\n")
    except Exception:
        pass


def _progress_signature(wf: Workflow, state: Dict[str, Any]) -> str:
    from . import ledger

    snapshot = {
        "phase": state.get("phase"),
        "tasks": {k: [v.get("status"), v.get("attempt"), v.get("round")] for k, v in (state.get("tasks") or {}).items()},
        "loops": {k: v.get("status") for k, v in (state.get("loops") or {}).items()},
        "final": (state.get("final") or {}).get("status"),
        "ledger": ledger.count(wf),
    }
    return sha256_text(json.dumps(snapshot, sort_keys=True))


def handle_stop(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if payload.get("agent_id"):
        return None
    bound = bound_workflow(payload)
    if bound is None:
        return None
    wf, state = bound
    heartbeat("Stop")
    _sample_stop_payload(payload)
    from . import plan as planmod
    from .common import file_lock
    from .waits import pending

    def save(mutate) -> Dict[str, Any]:
        with file_lock(wf.control / "state.lock"):
            fresh = read_json(wf.state_path) or state
            mutate(fresh)
            fresh["updated_at"] = utcnow()
            write_json_atomic(wf.state_path, fresh)
            return fresh

    def to_phase(phase: str, reason: str, kind: Optional[str] = None):
        def mutate(s: Dict[str, Any]) -> None:
            if phase == "HALTED":
                # A halt can land in any phase, including stop phases and
                # NEEDS_HUMAN / PLAN_CHANGE_REQUIRED, whose own resume_phase must
                # survive it. Record the exact place to return to separately.
                if s.get("phase") != "HALTED":
                    s["halted_from"] = {"phase": s.get("phase"), "block_reason": s.get("block_reason")}
            elif s.get("phase") not in STOP_PHASES:
                s["resume_phase"] = s.get("phase")
            s["phase"] = phase
            s["block_reason"] = reason
            s["phase_since"] = utcnow()
            if phase == "HALTED":
                s["halted_at"] = utcnow()
                s["halt_requested"] = False
            if kind:
                s["needs_human"] = {"kind": kind, "summary": reason, "raised_at": utcnow()}
        return save(mutate)

    if state.get("halt_requested") or wf.halt_path.exists():
        if wf.halt_path.exists():
            wf.halt_path.unlink()
        to_phase("HALTED", "Halt requested by the human.")
        return None
    phase = state.get("phase")
    if phase in STOP_PHASES or not state.get("approved_at"):
        return None

    # Integrity safeguards (separate process; the model cannot bypass them).
    expected = state.get("approved_plan_sha256")
    if expected and planmod.plan_hash(wf) != expected:
        reason = "The approved plan (request, plan, architecture, gate, or task documents) changed after approval."
        to_phase("PLAN_CHANGE_REQUIRED", reason)
        return {"decision": "block", "reason": reason + " Human re-approval is required: explain the change to the human and stop."}
    disk_ids = {p.name.split("-", 1)[0] for p in wf.task_files()}
    state_ids = set((state.get("tasks") or {}).keys())
    if disk_ids != state_ids:
        reason = (f"Task-set integrity violation: on disk not in state {sorted(disk_ids - state_ids)}; "
                  f"in state not on disk {sorted(state_ids - disk_ids)}.")
        to_phase("PLAN_CHANGE_REQUIRED", reason)
        return {"decision": "block", "reason": reason + " Human re-approval is required; stop."}
    from . import ledger

    entries = ledger.read(wf)
    accepted = {(e.get("task"), e.get("attempt")) for e in entries if e.get("kind") == "accept"}
    for tid, info in (state.get("tasks") or {}).items():
        if info.get("status") == "ACCEPTED" and (tid, info.get("attempt")) not in accepted:
            reason = f"{tid} is ACCEPTED in state but the ledger has no acceptance for attempt {info.get('attempt')}."
            to_phase("NEEDS_HUMAN", reason, kind="integrity")
            return {"decision": "block", "reason": reason + " State was changed outside the CLI; stop for the human."}

    # Legitimate wait on background subagents: let the turn end (hand-backs
    # re-invoke the session). Never spend the continuation budget on a wait,
    # but cap consecutive waits that make no progress.
    waiting = pending(payload)
    if waiting:
        signature = _progress_signature(wf, state)
        previous = state.get("last_wait") or {}
        waits = int(previous.get("consecutive_waits", 0)) + 1 if previous.get("signature") == signature else 1
        limit = int(state.get("max_consecutive_waits", 40))

        def mark(s: Dict[str, Any]) -> None:
            s["last_wait"] = {"at": utcnow(), "pending": waiting, "consecutive_waits": waits, "signature": signature}
        save(mark)
        if waits <= limit:
            return None
        return {"decision": "block", "reason": (
            f"{len(waiting)} background agent(s) are still outstanding, but this workflow has waited {waits} "
            "consecutive turns with no recorded progress. Do not keep agents in flight to defer the work: "
            "consolidate what has returned and make concrete progress now; if you are genuinely blocked, "
            "raise it with `orch needs-human`.")}

    limit = int(state.get("max_stop_continuations", 150))
    count = int(state.get("stop_continuations", 0)) + 1

    def bump(s: Dict[str, Any]) -> None:
        s["last_wait"] = None
        s["stop_continuations"] = count
    save(bump)
    if count > limit:
        reason = f"Autonomous continuation budget ({limit}) exhausted."
        to_phase("NEEDS_HUMAN", reason, kind="continuation_budget")
        return {"decision": "block", "reason": reason + " Summarize progress for the human and stop."}
    try:
        from .gates import Context, next_action

        nxt = next_action(Context(wf, fast=True))
    except Exception:
        nxt = "run `orch status` to find the next required action"
    reason = (
        "/task-orchestrator resume\n\n"
        f"The approved workflow `{state.get('workflow_id')}` is still active (phase {phase}). Continue from "
        "the recorded state; do not repeat accepted work; do not ask for permission between steps. Stop only "
        "at a human boundary (AWAITING_APPROVAL, NEEDS_HUMAN, PLAN_CHANGE_REQUIRED, HALTED, DONE). "
        f"The procedure is in {SKILL_FILE}.\n\n"
        f"NEXT: {nxt}\n\n{QUALITY_MANDATE}"
    )
    if payload.get("stop_hook_active"):
        reason += "\n\n(This turn is already a hook-driven continuation; make concrete progress before ending it.)"
    return {"decision": "block", "reason": reason}


HANDLERS = {
    "PreToolUse": handle_pretool,
    "UserPromptSubmit": handle_user_prompt,
    "UserPromptExpansion": handle_user_prompt_expansion,
    "SubagentStart": handle_subagent_start,
    "SubagentStop": handle_subagent_stop,
    "SessionStart": handle_session_start,
    "Stop": handle_stop,
}


def _run(name: str, handler, payload: Dict[str, Any]) -> Tuple[Optional[str], int]:
    try:
        result = handler(payload)
    except Exception as exc:  # fail open
        log_error(name, exc)
        return None, 0
    if result is None:
        return None, 0
    if isinstance(result, str):
        return result, 0
    return json.dumps(result), 0


def dispatch(payload: Dict[str, Any]) -> Tuple[Optional[str], int]:
    """Run the handler for this payload; return (stdout text, exit code)."""
    event = payload.get("hook_event_name")
    handler = HANDLERS.get(str(event))
    if handler is None:
        return None, 0
    return _run(str(event), handler, payload)


def dispatch_budget(payload: Dict[str, Any]) -> Tuple[Optional[str], int]:
    """Entry for `hook.py budget` — the frontmatter PreToolUse hook of every roster agent."""
    return _run("Budget", handle_budget, payload)
