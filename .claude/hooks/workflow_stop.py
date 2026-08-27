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

import json
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path.home() / ".claude" / "skills" / "feature-workflow" / "scripts"),
)

from workflow_lib import (
    calculate_plan_hash,
    get_repo_root,
    get_session_binding,
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


def allow_stop():
    raise SystemExit(0)


def block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))
    raise SystemExit(0)


def hard_stop(message):
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
