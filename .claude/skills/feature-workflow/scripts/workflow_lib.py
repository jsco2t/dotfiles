#!/usr/bin/env python3
"""
Shared workflow state library.

Used by both workflow_stop.py (the Stop hook) and the skill (via plan_hash
invocation). Single source of truth for state-root resolution, state I/O,
plan hashing, session binding, and workflow listing.

Portable: macOS and Linux. Python 3.9+.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def now() -> str:
    """UTC timestamp, second precision, ISO 8601."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def resolve_state_root(repo_root: Optional[str] = None) -> Path:
    """
    Resolve the workflow state root directory.

    Precedence:
    1. CLAUDE_WORKFLOW_STATE_ROOT environment variable
    2. .claude/workflow.json in the repository root
    3. ~/.claude/workflow-state/ default
    """
    env_root = os.environ.get("CLAUDE_WORKFLOW_STATE_ROOT")
    if env_root:
        return Path(env_root).expanduser()

    if repo_root:
        pointer = Path(repo_root) / ".claude" / "workflow.json"
        if pointer.exists():
            try:
                config = json.loads(pointer.read_text(encoding="utf-8"))
                if "state_root" in config:
                    return Path(config["state_root"]).expanduser()
            except (json.JSONDecodeError, KeyError):
                pass

    return Path.home() / ".claude" / "workflow-state"


def get_repo_root(cwd: str) -> Optional[str]:
    """Get git repo root, or None if not in a git repo."""
    try:
        return subprocess.check_output(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_session_binding(state_root: Path, session_id: str) -> Optional[dict]:
    """Read a session's workflow binding, or None."""
    binding_path = state_root / "sessions" / f"{session_id}.json"
    if not binding_path.exists():
        return None
    try:
        return json.loads(binding_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def bind_session(
    state_root: Path, session_id: str, workflow_id: str, repo_root: str
) -> None:
    """Bind a session to a workflow."""
    sessions_dir = state_root / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    binding = {
        "session_id": session_id,
        "workflow_id": workflow_id,
        "bound_at": now(),
        "repo_root": repo_root,
    }
    binding_path = sessions_dir / f"{session_id}.json"
    write_json(binding_path, binding)


def unbind_session(state_root: Path, session_id: str) -> None:
    """Remove a session binding."""
    binding_path = state_root / "sessions" / f"{session_id}.json"
    if binding_path.exists():
        binding_path.unlink()


def read_state(state_path: Path) -> dict:
    """Read workflow state from disk."""
    return json.loads(state_path.read_text(encoding="utf-8"))


def write_state(state_path: Path, state: dict) -> None:
    """Atomically write workflow state."""
    state["updated_at"] = now()
    write_json(state_path, state)


def write_json(path: Path, data: dict) -> None:
    """Atomically write a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def calculate_plan_hash(workflow_dir: Path) -> str:
    """
    Hash the frozen planning artifacts.

    Covers: request.md, plan.md, gate.json, tasks/*.md.
    Does NOT include: state.json, status.md, evidence/, archive.json.
    """
    tasks_dir = workflow_dir / "tasks"
    files = [
        workflow_dir / "request.md",
        workflow_dir / "plan.md",
        workflow_dir / "gate.json",
    ]
    if tasks_dir.exists():
        files.extend(sorted(tasks_dir.glob("*.md")))

    digest = hashlib.sha256()
    for path in files:
        if not path.exists():
            return ""
        digest.update(path.relative_to(workflow_dir).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def list_active_workflows(state_root: Path) -> list:
    """List all active workflows with summary info."""
    active_dir = state_root / "active"
    if not active_dir.exists():
        return []
    results = []
    for entry in sorted(active_dir.iterdir()):
        state_path = entry / "state.json"
        if entry.is_dir() and state_path.exists():
            try:
                state = read_state(state_path)
                results.append({
                    "workflow_id": state.get("workflow_id", entry.name),
                    "title": state.get("title", "Unknown"),
                    "phase": state.get("phase", "UNKNOWN"),
                    "iteration": state.get("iteration", 1),
                    "current_task": state.get("current_task"),
                    "created_at": state.get("created_at"),
                    "repo_root": state.get("repo_root", "Unknown"),
                })
            except (json.JSONDecodeError, OSError):
                results.append({
                    "workflow_id": entry.name,
                    "title": "UNREADABLE",
                    "phase": "ERROR",
                })
    return results


def list_archived_workflows(state_root: Path) -> list:
    """List all archived workflows from the index."""
    index_path = state_root / "archive" / "index.md"
    if not index_path.exists():
        return []
    results = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("- "):
            results.append({"entry": line[2:]})
    return results


def _cwd_stamp_key(cwd: str) -> str:
    """Derive a short key from the working directory for stamp file naming."""
    return hashlib.sha256(cwd.encode()).hexdigest()[:16]


def get_current_session_id(
    cwd: Optional[str] = None,
    state_root: Optional[Path] = None,
) -> Optional[str]:
    """
    Read the current session's ID from the stamp file written by the
    SessionStart hook. The stamp is keyed by working directory to support
    multiple independent sessions in different repositories.

    Returns None if no stamp exists.
    """
    if state_root is None:
        repo_root = get_repo_root(cwd or os.getcwd())
        state_root = resolve_state_root(repo_root)

    if cwd is None:
        cwd = os.getcwd()

    key = _cwd_stamp_key(cwd)
    stamp_path = state_root / f".session-{key}"
    if stamp_path.exists():
        try:
            return stamp_path.read_text(encoding="utf-8").strip() or None
        except OSError:
            return None
    return None


def stamp_session_id(
    session_id: str,
    cwd: str,
    state_root: Optional[Path] = None,
) -> None:
    """
    Write the current session_id to a known location so the skill can read it.
    Called by the SessionStart hook. Keyed by cwd to avoid collisions between
    sessions in different repositories.
    """
    if state_root is None:
        repo_root = get_repo_root(cwd)
        state_root = resolve_state_root(repo_root)

    state_root.mkdir(parents=True, exist_ok=True)
    key = _cwd_stamp_key(cwd)
    stamp_path = state_root / f".session-{key}"
    stamp_path.write_text(session_id + "\n", encoding="utf-8")


def unique_workflow_id(base_id: str, parent_dir: Path) -> str:
    """
    Return a unique workflow ID under parent_dir.

    If <base_id> doesn't exist, return it.
    Otherwise append -02, -03, etc.
    """
    if not (parent_dir / base_id).exists():
        return base_id
    n = 2
    while (parent_dir / f"{base_id}-{n:02d}").exists():
        n += 1
    return f"{base_id}-{n:02d}"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: workflow_lib.py <workflow-dir>", file=sys.stderr)
        raise SystemExit(1)
    workflow_dir = Path(sys.argv[1])
    h = calculate_plan_hash(workflow_dir)
    if not h:
        print("ERROR: missing planning artifact", file=sys.stderr)
        raise SystemExit(1)
    print(h)
