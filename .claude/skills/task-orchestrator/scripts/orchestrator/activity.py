"""Per-agent activity records and the time budget.

Every roster agent's frontmatter registers the budget hook (`hook.py budget`,
PreToolUse, matcher "*"), so every tool call a roster agent makes — Read, Grep,
WebFetch, MCP calls included — passes through `on_tool`. Together with
SubagentStart (`start`) and SubagentStop (`stop`) that keeps one record per
agent in <workflow>/.orch/agents/<agent_id>.json, plus a one-line-per-call log
in <agent_id>.calls.jsonl. Only the hooks and `orch agent continue` write them.

Active time is the sum of the agent's segments. A segment opens at SubagentStart
or at the first tool call after a stop, and closes at SubagentStop, so the clock
pauses between a hand-back and the next SendMessage resume.

The budget hook stops an agent — refuses every tool call except writing its
interim report and handing back — when:

* time: its active minutes reach its type's budget plus any granted extensions
  (checked at each tool call, so an agent may run past the budget until its
  next call); or
* pause: the human paused the workflow and the agent is a read-only role
  (authors and planners finish their current pass).

The agent then writes an interim report (common.interim_path) and finishes with
status `interim`. The PM reviews time stops (stage pm-interim) before
`orch agent continue` grants more time.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from .common import (
    INTERIM_DIR,
    Workflow,
    file_lock,
    parse_ts,
    read_json,
    utcnow,
    write_json_atomic,
)
from .roster import DEFAULT_AGENT_MINUTES, READONLY

HANDBACK_TOOL = "SubagentHandback"
FILE_TOOLS = ("Write", "Edit", "MultiEdit")
RECENT_CALLS = 12
BRIEF_REPORT_RE = re.compile(r"Write your full report to `([^`]+)`")
BRIEF_HEAD_RE = re.compile(r"# Dispatch brief — `([a-z-]+)` · `([a-z-]+)`")
BRIEF_SUBJECT_RE = re.compile(r"^- (?:Research item|Task): (.+)$", re.M)


# ---------------------------------------------------------------- storage


def _safe(agent_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(agent_id))


def _path(wf: Workflow, agent_id: str) -> Path:
    return wf.agents_dir / f"{_safe(agent_id)}.json"


def calls_path(wf: Workflow, agent_id: str) -> Path:
    return wf.agents_dir / f"{_safe(agent_id)}.calls.jsonl"


@contextlib.contextmanager
def _locked(wf: Workflow, agent_id: str) -> Generator[None, None, None]:
    with file_lock(wf.agents_dir / f"{_safe(agent_id)}.lock"):
        yield


def load(wf: Workflow, agent_id: str) -> Optional[Dict[str, Any]]:
    data = read_json(_path(wf, agent_id))
    return data if isinstance(data, dict) else None


def all_agents(wf: Workflow) -> List[Dict[str, Any]]:
    if not wf.agents_dir.is_dir():
        return []
    out = []
    for path in wf.agents_dir.glob("*.json"):
        data = read_json(path)
        if isinstance(data, dict) and data.get("agent_id"):
            out.append(data)
    return sorted(out, key=lambda i: i.get("started_at") or "")


def _new(agent_id: str, agent_type: str, session_id: Optional[str], stamp: str) -> Dict[str, Any]:
    return {
        "agent_id": agent_id,
        "agent_type": agent_type,
        "session_id": session_id,
        "started_at": stamp,
        "segments": [],
        "calls": 0,
        "denied": 0,
        "granted_minutes": 0,
        "last_call_at": None,
        "last_tool": None,
        "recent": [],
        "stop_reason": None,
        "report": None,
        "stage": None,
        "subject": None,
        "brief_lookups": 0,
    }


def grant(wf: Workflow, agent_id: str, minutes: int) -> Dict[str, Any]:
    """Add PM/human-approved minutes to an agent's budget (`orch agent continue`)."""
    with _locked(wf, agent_id):
        info = load(wf, agent_id) or _new(agent_id, "unknown", None, utcnow())
        info["granted_minutes"] = int(info.get("granted_minutes") or 0) + int(minutes)
        write_json_atomic(_path(wf, agent_id), info)
        return info


# ---------------------------------------------------------------- time


def _open(info: Dict[str, Any]) -> bool:
    segments = info.get("segments") or []
    return bool(segments) and segments[-1].get("end") is None


def _open_segment(info: Dict[str, Any], stamp: str) -> bool:
    if _open(info):
        return False
    info.setdefault("segments", []).append({"start": stamp, "end": None})
    return True


def _close_segment(info: Dict[str, Any], stamp: str) -> None:
    if _open(info):
        info["segments"][-1]["end"] = stamp


def _adopt_session(info: Dict[str, Any], session_id: Optional[str]) -> None:
    """An agent reached from a new session (resumed after a restart): its old segment ended
    at its last sign of life, so the downtime never counts as active time."""
    if not session_id or not info.get("session_id") or session_id == info["session_id"]:
        return
    if _open(info):
        segment = info["segments"][-1]
        segment["end"] = info.get("last_call_at") or segment["start"]
    info["session_id"] = session_id


def active_seconds(info: Dict[str, Any], now: Optional[datetime] = None) -> float:
    now = now or datetime.now(timezone.utc)
    total = 0.0
    for seg in info.get("segments") or []:
        start = parse_ts(seg.get("start"))
        end = parse_ts(seg.get("end")) if seg.get("end") else now
        if start and end and end > start:
            total += (end - start).total_seconds()
    return total


def active_minutes(info: Dict[str, Any], now: Optional[datetime] = None) -> int:
    return int(active_seconds(info, now) // 60)


def budget_minutes(state: Dict[str, Any], agent_type: Optional[str]) -> Optional[int]:
    """The agent type's per-dispatch budget, or None when it is logged but not limited."""
    table = (state.get("budgets") or {}).get("agent_minutes")
    if not isinstance(table, dict):
        table = DEFAULT_AGENT_MINUTES
    value = table.get(agent_type or "")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return int(value)


def pause_requested(wf: Workflow, state: Dict[str, Any]) -> bool:
    return bool(state.get("halt_requested")) or wf.halt_path.exists() or state.get("phase") == "HALTED"


# ---------------------------------------------------------------- brief lookup


def _transcript_candidates(payload: Dict[str, Any]) -> List[Path]:
    agent_id = str(payload.get("agent_id") or "")
    out: List[Path] = []
    for key in ("agent_transcript_path", "transcript_path"):
        raw = payload.get(key)
        if not isinstance(raw, str) or not raw:
            continue
        path = Path(raw)
        if "/subagents/" in raw:
            out.append(path)
        elif agent_id:
            out.append(path.with_suffix("") / "subagents" / f"agent-{agent_id}.jsonl")
    return out


def _first_prompt(path: Path, max_lines: int = 40) -> Optional[str]:
    try:
        with open(path, encoding="utf-8") as handle:
            for n, line in enumerate(handle):
                if n >= max_lines:
                    break
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict) or record.get("type") != "user":
                    continue
                content = (record.get("message") or {}).get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    texts = [str(b["text"]) for b in content if isinstance(b, dict) and isinstance(b.get("text"), str)]
                    if texts:
                        return "\n".join(texts)
    except OSError:
        return None
    return None


def _learn_brief(info: Dict[str, Any], payload: Dict[str, Any]) -> None:
    """Best effort: read the agent's own dispatch prompt (its brief) for the stage and report path."""
    if info.get("report") or int(info.get("brief_lookups") or 0) >= 5:
        return
    info["brief_lookups"] = int(info.get("brief_lookups") or 0) + 1
    for path in _transcript_candidates(payload):
        prompt = _first_prompt(path)
        if not prompt:
            continue
        report = BRIEF_REPORT_RE.search(prompt)
        if not report:
            continue
        info["report"] = report.group(1)
        head = BRIEF_HEAD_RE.search(prompt)
        if head:
            info["stage"] = head.group(1)
        subject = BRIEF_SUBJECT_RE.search(prompt)
        if subject:
            info["subject"] = subject.group(1).strip()[:160]
        return


# ---------------------------------------------------------------- tool calls


def summarize(tool: str, tool_input: Dict[str, Any]) -> str:
    """One short line describing a tool call, for the activity log the PM reads."""
    for key in ("file_path", "notebook_path", "url", "pattern", "query", "command", "description", "skill",
                "subagent_type", "libraryName", "libraryId"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            text = " ".join(value.split())
            return f"{tool} {key}={text[:160]}"
    return tool


def _allowed_while_stopped(wf: Workflow, agent_type: str, tool: str, tool_input: Dict[str, Any],
                           cwd: Optional[str]) -> bool:
    if tool == HANDBACK_TOOL:
        return True
    if tool not in FILE_TOOLS:
        return False
    raw = tool_input.get("file_path")
    if not isinstance(raw, str) or not raw:
        return False
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path(cwd or os.getcwd()) / path
    path = Path(os.path.realpath(path))
    try:
        path.relative_to(wf.root)
    except ValueError:
        return False
    return path.parent.name == INTERIM_DIR and path.name.endswith(f".{agent_type}.md")


def stop_message(reason: str, info: Dict[str, Any], total: Optional[int]) -> str:
    where = ("Write your interim report to the `interim/` folder beside your report, with the same file name "
             "(your brief's \"If you are stopped\" section gives the exact path)")
    if info.get("report"):
        from .common import interim_path
        where = f"Write your interim report to `{interim_path(Path(info['report']))}`"
    finish = ("Then finish with your brief's result block, with \"status\": \"interim\" and \"report\" set to the "
              "interim report's path.")
    if reason == "pause":
        return ("THE HUMAN PAUSED THE WORKFLOW — stop now and report. Every tool call except writing your interim "
                f"report is refused. {where}: what you finished, what remains, and exactly where to pick up. "
                f"{finish} You will be resumed, with your context intact, when the human resumes the workflow.")
    used = active_minutes(info)
    return ("TIME BUDGET REACHED — stop and report. You have used "
            f"{used} of your {total if total is not None else '?'} active minutes. Every tool call except writing "
            f"your interim report is now refused; do not start anything new. {where}. Cover: (1) each question "
            "or deliverable in your brief — done (with the evidence) or not yet; (2) what remains, and why it is "
            "taking longer than planned; (3) whether your scope grew, and what led you there; (4) what you would "
            f"do with more time, and how many minutes it needs. {finish} The project-manager reviews it, and you "
            "will be resumed with its decision.")


def on_tool(wf: Workflow, state: Dict[str, Any], payload: Dict[str, Any]) -> Optional[str]:
    """Record one tool call; return the reason to refuse it, or None to allow it."""
    agent_id = str(payload.get("agent_id") or "")
    agent_type = str(payload.get("agent_type") or "")
    if not agent_id:
        return None
    tool = str(payload.get("tool_name") or "")
    raw_input = payload.get("tool_input")
    tool_input: Dict[str, Any] = raw_input if isinstance(raw_input, dict) else {}
    stamp = utcnow()
    wf.agents_dir.mkdir(parents=True, exist_ok=True)
    with _locked(wf, agent_id):
        info = load(wf, agent_id) or _new(agent_id, agent_type, payload.get("session_id"), stamp)
        _adopt_session(info, payload.get("session_id"))
        if _open_segment(info, stamp):
            info["stop_reason"] = None  # a resumed agent is judged afresh
            info["interrupted_at"] = None
        info["calls"] = int(info.get("calls") or 0) + 1
        info["last_call_at"] = stamp
        info["last_tool"] = tool
        line = summarize(tool, tool_input)
        info["recent"] = (list(info.get("recent") or []) + [{"at": stamp, "call": line}])[-RECENT_CALLS:]
        _learn_brief(info, payload)
        base = budget_minutes(state, agent_type)
        total = None if base is None else base + int(info.get("granted_minutes") or 0)
        reason = info.get("stop_reason")
        if reason is None:
            if agent_type in READONLY and pause_requested(wf, state):
                reason = "pause"
            elif total is not None and active_seconds(info) >= total * 60:
                reason = "time"
            if reason:
                info["stop_reason"] = reason
                info["stopped_at_minutes"] = active_minutes(info)
        allowed = reason is None or _allowed_while_stopped(wf, agent_type, tool, tool_input, payload.get("cwd"))
        if not allowed:
            info["denied"] = int(info.get("denied") or 0) + 1
        write_json_atomic(_path(wf, agent_id), info)
    with open(calls_path(wf, agent_id), "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": stamp, "call": line, "refused": not allowed,
                                 "minutes": active_minutes(info)}) + "\n")
    return None if allowed else stop_message(str(reason), info, total)


def start(wf: Workflow, payload: Dict[str, Any]) -> Dict[str, Any]:
    """SubagentStart: open (or reopen) the agent's record."""
    agent_id = str(payload.get("agent_id") or "")
    stamp = utcnow()
    wf.agents_dir.mkdir(parents=True, exist_ok=True)
    with _locked(wf, agent_id):
        existing = load(wf, agent_id)
        info = existing or _new(agent_id, str(payload.get("agent_type") or ""), payload.get("session_id"), stamp)
        _adopt_session(info, payload.get("session_id"))
        if _open_segment(info, stamp):
            info["stop_reason"] = None
        info["resumed"] = existing is not None
        info["interrupted_at"] = None
        write_json_atomic(_path(wf, agent_id), info)
        return info


def stop(wf: Workflow, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """SubagentStop: close the open segment; returns the record (with its stop_reason)."""
    agent_id = str(payload.get("agent_id") or "")
    if not agent_id:
        return None
    stamp = utcnow()
    wf.agents_dir.mkdir(parents=True, exist_ok=True)
    with _locked(wf, agent_id):
        info = load(wf, agent_id)
        if info is None:
            return None
        _close_segment(info, stamp)
        info["stopped_at"] = stamp
        write_json_atomic(_path(wf, agent_id), info)
        return info


def sweep_interrupted(wf: Workflow) -> List[str]:
    """SessionStart after a restart (`resume`/`startup`): no agent from before survived the
    process, so close every open segment at its last sign of life and mark it interrupted.
    Needed because `claude -r` keeps the session id, so `_adopt_session` never fires."""
    stamp = utcnow()
    swept = []
    for info in all_agents(wf):
        if not _open(info):
            continue
        aid = str(info["agent_id"])
        with _locked(wf, aid):
            fresh = load(wf, aid)
            if not fresh or not _open(fresh):
                continue
            segment = fresh["segments"][-1]
            segment["end"] = fresh.get("last_call_at") or segment["start"]
            fresh["interrupted_at"] = stamp
            write_json_atomic(_path(wf, aid), fresh)
            swept.append(aid)
    return swept


def read_calls(wf: Workflow, agent_id: str, tail: int = 200) -> List[Dict[str, Any]]:
    path = calls_path(wf, agent_id)
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-tail:]


# ---------------------------------------------------------------- views


def summaries(wf: Workflow, state: Dict[str, Any], entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every recorded agent with its current status, for `orch agents`, status, and list.

    status: running | interrupted (its segment is open but the workflow is now driven by
    another session — e.g. after a restart) | interim | needs_input | blocked | invalid |
    done | stopped (handed back without a recorded result).
    """
    latest: Dict[str, Dict[str, Any]] = {}
    continued: Dict[str, int] = {}
    acknowledged: Dict[str, str] = {}  # agent id -> latest "interrupted" acknowledgment time
    for entry in entries:
        aid = entry.get("agent_id")
        if not aid:
            continue
        if entry.get("kind") == "agent_result":
            latest[aid] = entry
        elif entry.get("kind") == "agent_continue":
            continued[aid] = max(continued.get(aid, 0), int(entry.get("seq") or 0))
            if entry.get("reason") == "interrupted":
                acknowledged[aid] = str(entry.get("ts") or "")
    now = datetime.now(timezone.utc)
    rows = []
    for info in all_agents(wf):
        aid = info["agent_id"]
        result = latest.get(aid)
        res = (result or {}).get("result") or {}
        swept = info.get("interrupted_at")  # set by the SessionStart sweep after a restart
        if _open(info) or swept:
            driver = state.get("session_id")
            cut_off = bool(swept) or bool(info.get("session_id") and driver and info["session_id"] != driver)
            # `orch agent continue` acknowledged it (resumed by SendMessage or re-dispatched).
            done = aid in acknowledged and (not swept or acknowledged[aid] >= str(swept))
            status = ("resumed" if done else "interrupted") if cut_off else "running"
        elif result is None:
            status = "stopped"
        elif not result.get("valid"):
            status = "invalid"
        elif res.get("status") == "interim":
            status = "resumed" if continued.get(aid, 0) > int(result.get("seq") or 0) else "interim"
        elif res.get("status") in ("needs_input", "blocked"):
            status = res["status"]
        else:
            status = "done"
        base = budget_minutes(state, info.get("agent_type"))
        last = parse_ts(info.get("last_call_at"))
        rows.append({
            "agent_id": aid,
            "agent_type": info.get("agent_type"),
            "stage": res.get("stage") or info.get("stage"),
            "subject": info.get("subject") or res.get("task") or res.get("item"),
            "report": res.get("report") or info.get("report"),
            "status": status,
            "stop_reason": (result or {}).get("interim_reason") or info.get("stop_reason"),
            "active_minutes": active_minutes(info, now),
            "budget_minutes": None if base is None else base + int(info.get("granted_minutes") or 0),
            "calls": int(info.get("calls") or 0),
            "refused": int(info.get("denied") or 0),
            "last_tool": info.get("last_tool"),
            "last_call_age_s": int((now - last).total_seconds()) if last else None,
            "recent": info.get("recent") or [],
            "session_id": info.get("session_id"),
            "result_seq": (result or {}).get("seq"),
        })
    return rows


ACTIVE_STATUSES = ("running", "interrupted", "interim", "needs_input", "blocked", "invalid", "stopped")
