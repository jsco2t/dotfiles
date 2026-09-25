"""Detect whether the main session is legitimately waiting on background work.

When the orchestrator dispatches background subagents and has nothing to do
but wait, the Stop hook must let the turn end: each hand-back re-invokes the
session on its own, so forcing a continuation only thrashes.

Two sources, in order of authority:

1. `background_tasks` in the hook payload (harness-generated list of the
   session's running background tasks), when present.
2. The session transcript. Verified on Claude Code 2.1.282:
   * dispatch — a record whose `toolUseResult` has `isAsync: true` + `agentId`
   * resume   — a record whose `toolUseResult` has `resumedAgentId`
                (SendMessage to a completed agent restarts it)
   * complete — a `queue-operation` record (top-level `content`) or a
                `queued_command` attachment (`attachment.prompt`) carrying
                `<agent-message from="ID">\n[Subagent hand-back]` or a
                `<task-notification>` for task-id ID with a terminal status.
                Older builds put the same text in `message.content`.
   An agent is pending when its latest dispatch/resume is newer than its
   latest completion. Parse failures mean "nothing pending", which falls back
   to normal blocking — never a silent bypass.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .common import parse_ts

WAIT_RECENCY_SECONDS = 1800
HANDBACK_MARKER = "[Subagent hand-back]"
FROM_RE = re.compile(r'<agent-message from="([^"]+)">\s*\n?\s*\[Subagent hand-back\]')
TASK_NOTE_RE = re.compile(
    r"<task-notification>.*?<task-id>([^<]+)</task-id>.*?<status>([^<]+)</status>", re.S
)
TERMINAL_STATUSES = {"completed", "failed", "killed", "error", "cancelled", "stopped"}


def pending_from_payload(payload: Dict[str, Any]) -> Optional[List[str]]:
    """In-flight work the harness lists (Stop schema: "running/pending + backgrounded";
    "empty array when nothing is in flight"). None when the field is absent."""
    tasks = payload.get("background_tasks")
    if not isinstance(tasks, list):
        return None
    return [
        str(t.get("id"))
        for t in tasks
        if isinstance(t, dict) and str(t.get("status", "running")).lower() not in TERMINAL_STATUSES
    ]


def _texts(record: Dict[str, Any]) -> Iterable[str]:
    content = record.get("content")
    if isinstance(content, str):
        yield content
    attachment = record.get("attachment")
    if isinstance(attachment, dict) and isinstance(attachment.get("prompt"), str):
        yield attachment["prompt"]
    message = record.get("message")
    if isinstance(message, dict):
        body = message.get("content")
        if isinstance(body, str):
            yield body
        elif isinstance(body, list):
            for part in body:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    yield part["text"]


def transcript_events(path: Optional[str]) -> Optional[Dict[str, Dict[str, datetime]]]:
    """{'dispatched': {id: ts}, 'completed': {id: ts}} from a transcript, or None."""
    if not path or not Path(path).is_file():
        return None
    try:
        dispatched: Dict[str, datetime] = {}
        completed: Dict[str, datetime] = {}
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                stamp = parse_ts(record.get("timestamp"))
                if stamp is None:
                    continue
                result = record.get("toolUseResult")
                if isinstance(result, dict):
                    agent = None
                    if result.get("isAsync") and result.get("agentId"):
                        agent = str(result["agentId"])
                    elif result.get("resumedAgentId"):
                        agent = str(result["resumedAgentId"])
                    if agent and stamp > dispatched.get(agent, stamp.replace(year=1970)):
                        dispatched[agent] = stamp
                    continue
                if record.get("type") == "queue-operation" and record.get("operation") not in (None, "enqueue"):
                    continue
                for text in _texts(record):
                    if HANDBACK_MARKER in text:
                        for agent in FROM_RE.findall(text):
                            if stamp > completed.get(agent, stamp.replace(year=1970)):
                                completed[agent] = stamp
                    if "<task-notification>" in text:
                        for agent, status in TASK_NOTE_RE.findall(text):
                            if status.strip().lower() in TERMINAL_STATUSES:
                                agent = agent.strip()
                                if stamp > completed.get(agent, stamp.replace(year=1970)):
                                    completed[agent] = stamp
        return {"dispatched": dispatched, "completed": completed}
    except Exception:
        return None


def _finished(agent: str, events: Dict[str, Dict[str, datetime]]) -> bool:
    done = events["completed"].get(agent)
    if done is None:
        return False
    sent = events["dispatched"].get(agent)
    return sent is None or done >= sent


def pending_from_transcript(path: Optional[str], now: Optional[datetime] = None) -> List[str]:
    events = transcript_events(path)
    if events is None:
        return []
    now = now or datetime.now(timezone.utc)
    pending_ids = []
    for agent, sent in events["dispatched"].items():
        if _finished(agent, events):
            continue
        if (now - sent).total_seconds() > WAIT_RECENCY_SECONDS:
            continue
        pending_ids.append(agent)
    return sorted(pending_ids)


def pending(payload: Dict[str, Any]) -> List[str]:
    """Background work this session is legitimately waiting on.

    The harness list is authoritative for what is in flight; an entry is dropped
    only when the transcript proves it already handed back after its latest
    dispatch/resume (guards against a finished agent lingering in the list).
    """
    from_payload = pending_from_payload(payload)
    if from_payload is None:
        return pending_from_transcript(payload.get("transcript_path"))
    events = transcript_events(payload.get("transcript_path"))
    if events is None:
        return from_payload
    return [agent for agent in from_payload if not _finished(agent, events)]
