#!/usr/bin/env python3
"""
Stop hook for the multi-workflow system.

Determines whether the current session is driving a workflow,
and if so, whether to allow stopping or force continuation.

Uses session_id from the Stop hook payload to look up the
session->workflow binding, then checks that workflow's state.

Portable: macOS and Linux. Python 3.9+.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

sys.path.insert(
    0,
    str(Path.home() / ".claude" / "skills" / "feature-workflow" / "scripts"),
)

from workflow_lib import (
    calculate_plan_hash,
    get_repo_root,
    get_session_binding,
    now,
    read_state,
    resolve_state_root,
    write_state,
)

STOP_PHASES = {
    "AWAITING_APPROVAL",
    "DONE",
    "BLOCKED",
    "HALTED",
    "PLAN_CHANGE_REQUIRED",
    "RETRY_BUDGET_EXCEEDED",
}

# Background-agent wait awareness -------------------------------------------
#
# When the main session dispatches async ("background") subagents and then ends
# its turn with nothing to do but wait, this hook must NOT force a continuation.
# A subagent's hand-back re-invokes the session on its own (verified: the
# hand-back arrives as a fresh prompt / new turn, independent of this hook), so
# forcing a continuation only thrashes: continue -> "still waiting" -> stop ->
# block -> continue ... We detect outstanding background agents from the
# transcript. The dispatch side is harness-generated metadata
# (toolUseResult.isAsync) and cannot be faked by the model; the completion side
# is the hand-back message the harness injects when a subagent returns.
#
# Any parse failure yields "nothing pending", so the hook falls back to its
# normal blocking behavior — never a regression, only a needless stall avoided.

# A subagent silent longer than this is treated as dead/abandoned, so the hook
# resumes its normal blocking behavior rather than waiting on it forever.
WAIT_RECENCY_SECONDS = 1800

# Cap on consecutive waits that make no task progress. Prevents the quality
# mandate from being bypassed by keeping one agent perpetually in flight.
DEFAULT_MAX_CONSECUTIVE_WAITS = 20

# Match the full agent id verbatim. The dispatch side records
# toolUseResult.agentId unfiltered, so the completion side must accept the same
# character set — agent ids are not always pure hex (e.g. "reviewer-security").
# The _HANDBACK_MARKER guard already scopes this to genuine hand-back messages.
_HANDBACK_MARKER = "[Subagent hand-back]"
_FROM_RE = re.compile(r'from="([^"]+)"')


def _iter_transcript(path):
    """Yield parsed JSONL records from a transcript, skipping unparseable lines."""
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def _record_content(record):
    """Best-effort text of a transcript record's message content."""
    message = record.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            try:
                return json.dumps(content)
            except Exception:
                return ""
    return ""


def _parse_ts(record):
    """Parse a record's ISO 8601 timestamp, or None."""
    stamp = record.get("timestamp")
    if not isinstance(stamp, str):
        return None
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def pending_background_agents(payload):
    """
    Return the agentIds of async subagents this session dispatched that have not
    yet handed back and were dispatched recently.

    Empty on any failure (missing/unreadable transcript, parse error), which
    lets the caller fall back to normal blocking behavior.
    """
    transcript_path = payload.get("transcript_path")
    if not transcript_path or not Path(transcript_path).exists():
        return []
    try:
        dispatched = {}  # agentId -> dispatch timestamp (or None)
        handed_back = set()
        for record in _iter_transcript(transcript_path):
            result = record.get("toolUseResult")
            if isinstance(result, dict) and result.get("isAsync"):
                agent_id = result.get("agentId")
                if agent_id:
                    dispatched[agent_id] = _parse_ts(record)
                continue
            content = _record_content(record)
            if content and _HANDBACK_MARKER in content:
                handed_back.update(_FROM_RE.findall(content))
        now_dt = datetime.now(timezone.utc)
        pending = []
        for agent_id, stamp in dispatched.items():
            if agent_id in handed_back:
                continue
            if stamp is not None:
                if (now_dt - stamp).total_seconds() > WAIT_RECENCY_SECONDS:
                    continue  # dead/abandoned: stop waiting on it
            pending.append(agent_id)
        return pending
    except Exception:
        return []


def task_progress_signature(state):
    """
    Stable fingerprint of task-level progress. It changes when any task's status
    or evidence changes, or when phase/current_task/iteration advance, so that
    genuine forward progress resets the consecutive-wait counter while parking
    on background agents without progress does not.
    """
    snapshot = {
        "phase": state.get("phase"),
        "current_task": state.get("current_task"),
        "iteration": state.get("iteration"),
        "tasks": [
            {
                "id": task.get("id"),
                "status": task.get("status"),
                "evidence": bool(task.get("evidence")),
            }
            for task in state.get("tasks", [])
        ],
    }
    blob = json.dumps(snapshot, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def allow_stop() -> NoReturn:
    raise SystemExit(0)


def block(reason) -> NoReturn:
    print(json.dumps({"decision": "block", "reason": reason}))
    raise SystemExit(0)


def hard_stop(message) -> NoReturn:
    print(json.dumps({"continue": False, "stopReason": message}))
    raise SystemExit(0)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow_stop()

    if payload.get("hook_event_name") != "Stop":
        allow_stop()

    if payload.get("agent_id"):
        allow_stop()

    session_id = payload.get("session_id")
    if not session_id:
        allow_stop()

    cwd = payload.get("cwd") or "."
    repo_root = get_repo_root(cwd)

    state_root = resolve_state_root(repo_root)

    binding = get_session_binding(state_root, session_id)
    if not binding:
        allow_stop()

    workflow_id = binding.get("workflow_id")
    if not workflow_id:
        allow_stop()

    workflow_dir = state_root / "active" / workflow_id
    state_path = workflow_dir / "state.json"

    if not state_path.exists():
        allow_stop()

    try:
        state = read_state(state_path)
    except Exception as exc:
        hard_stop(f"Workflow state is unreadable: {exc}")

    phase = state.get("phase")

    halt_file = workflow_dir / "HALT"
    if state.get("halt_requested") or halt_file.exists():
        state["phase"] = "HALTED"
        state["block_reason"] = "Halt requested by user."
        if halt_file.exists():
            halt_file.unlink()
        write_state(state_path, state)
        allow_stop()

    if phase in STOP_PHASES:
        allow_stop()

    # Only drive autonomous continuation after approval.
    # Before approval (PLANNING, etc.), the model should stop normally.
    if not state.get("approved_at"):
        allow_stop()

    expected_hash = state.get("approved_plan_sha256")
    if expected_hash:
        actual_hash = calculate_plan_hash(workflow_dir)
        if actual_hash and actual_hash != expected_hash:
            state["phase"] = "PLAN_CHANGE_REQUIRED"
            state["block_reason"] = (
                "Approved request, plan, quality gate, or task documents "
                "changed after approval."
            )
            write_state(state_path, state)
            block(
                "Approved plan changed after approval. Set phase "
                "PLAN_CHANGE_REQUIRED, record the reason, update status, and "
                "stop. Human re-approval is required."
            )

    # Safeguard: task-set integrity check.
    # Compare task IDs in state against actual tasks/*.md files on disk.
    tasks_dir = workflow_dir / "tasks"
    if tasks_dir.exists() and state.get("tasks"):
        disk_ids = set()
        for f in sorted(tasks_dir.glob("*.md")):
            stem = f.stem
            if stem and stem[:3].isdigit():
                disk_ids.add(stem[:3])
        state_ids = {t.get("id") for t in state["tasks"] if t.get("id")}
        if disk_ids != state_ids:
            missing_from_state = disk_ids - state_ids
            missing_from_disk = state_ids - disk_ids
            msg_parts = []
            if missing_from_state:
                msg_parts.append(
                    f"Task files on disk not in state: {sorted(missing_from_state)}"
                )
            if missing_from_disk:
                msg_parts.append(
                    f"State entries with no task file: {sorted(missing_from_disk)}"
                )
            state["phase"] = "PLAN_CHANGE_REQUIRED"
            state["block_reason"] = (
                "Task-set integrity violation: " + "; ".join(msg_parts)
            )
            write_state(state_path, state)
            block(
                state["block_reason"]
                + " Human re-approval is required."
            )

    # Safeguard: per-criterion completion verification.
    # If a task claims COMPLETE but has unmet criteria or missing evidence,
    # block and name the specific gap.
    for task in state.get("tasks", []):
        if task.get("status") != "COMPLETE":
            continue
        criteria = task.get("acceptance_criteria", [])
        unmet = [c for c in criteria if not c.get("met")]
        if unmet:
            unmet_texts = [c.get("text", "unknown") for c in unmet[:3]]
            state["phase"] = "BLOCKED"
            state["block_reason"] = (
                f"Task {task.get('id')} claims COMPLETE but has unmet "
                f"acceptance criteria: {unmet_texts}"
            )
            write_state(state_path, state)
            block(state["block_reason"])
        if not task.get("evidence"):
            state["phase"] = "BLOCKED"
            state["block_reason"] = (
                f"Task {task.get('id')} claims COMPLETE but has no "
                "evidence file."
            )
            write_state(state_path, state)
            block(state["block_reason"])

    # Safeguard: deviation detection.
    # If the model wrote a pending_deviation, force PLAN_CHANGE_REQUIRED.
    if state.get("pending_deviation"):
        state["phase"] = "PLAN_CHANGE_REQUIRED"
        state["block_reason"] = (
            "Pending deviation detected: "
            + str(state["pending_deviation"])
        )
        write_state(state_path, state)
        block(
            state["block_reason"]
            + " Human approval is required before proceeding."
        )

    # Safeguard: background-agent wait awareness.
    # If this session is legitimately blocked waiting on background subagents it
    # dispatched, let the turn end — the hand-back re-invokes us, so forcing a
    # continuation here only thrashes. Do NOT spend the continuation budget on a
    # wait. But cap consecutive waits that make no task progress, so the quality
    # mandate cannot be silently bypassed by parking on background agents.
    pending = pending_background_agents(payload)
    if pending:
        progress_sig = task_progress_signature(state)
        previous = state.get("last_wait") or {}
        if previous.get("progress_sig") == progress_sig:
            waits = int(previous.get("consecutive_waits", 0)) + 1
        else:
            waits = 1
        max_waits = int(
            state.get("max_consecutive_waits", DEFAULT_MAX_CONSECUTIVE_WAITS)
        )
        state["last_wait"] = {
            "at": now(),
            "pending": pending,
            "consecutive_waits": waits,
            "progress_sig": progress_sig,
        }
        if waits <= max_waits:
            # Legitimate wait: let the turn end. The subagent hand-back will
            # re-invoke this session. Breadcrumb written; budget untouched.
            write_state(state_path, state)
            allow_stop()
        # Too many consecutive waits with no task progress: refuse to keep
        # parking on background agents in place of real progress.
        state["last_wait"]["bypass_guard_tripped"] = True
        write_state(state_path, state)
        block(
            f"{len(pending)} background agent(s) still outstanding, but this "
            f"workflow has waited {waits} consecutive turns with no task "
            "progress. Do not keep agents in flight to defer completion. "
            "Consolidate the results that have returned, make concrete "
            "progress on the current task now, and if you are genuinely "
            "blocked, set an appropriate stop phase and ask a human."
        )

    # No background agents outstanding: normal continuation logic applies and
    # the quality mandate governs. Clear the wait breadcrumb.
    if state.get("last_wait"):
        state["last_wait"] = None

    platform_continuation = bool(payload.get("stop_hook_active"))

    continuations = int(state.get("stop_continuations", 0)) + 1
    limit = int(state.get("max_stop_continuations", 60))
    state["stop_continuations"] = continuations

    if continuations > limit:
        state["phase"] = "BLOCKED"
        state["block_reason"] = (
            f"Autonomous continuation budget exceeded ({limit}). "
            "Human review is required."
        )
        write_state(state_path, state)
        block(
            state["block_reason"]
            + " Update status.md and stop for human review."
        )

    write_state(state_path, state)

    reason = (
        "/feature-workflow resume\n\n"
        f"The approved workflow '{workflow_id}' is still active. "
        "Read the workflow state.json and continue from the recorded phase. "
        "Do not repeat completed tasks. Do not ask for permission between "
        "tasks. Stop only at AWAITING_APPROVAL, DONE, BLOCKED, HALTED, "
        "PLAN_CHANGE_REQUIRED, or RETRY_BUDGET_EXCEEDED.\n\n"
        "QUALITY MANDATE: The goal here is to not find ways to make this "
        "process more efficient or to cut corners. The goal IS to produce "
        "the highest quality feature possible. DO NOT SKIP STEPS. DO NOT "
        "DEFER WORK. If you are not sure how to proceed — ask a human."
    )
    if platform_continuation:
        reason += (
            "\n\n(This turn is already a hook-driven continuation; make "
            "concrete progress on the current phase before ending the turn.)"
        )
    block(reason)


if __name__ == "__main__":
    main()
