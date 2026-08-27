#!/usr/bin/env python3
"""
SessionStart hook for the multi-workflow system.

Stamps the current session_id to a known file so the skill can read it.
Also emits a reminder if an active workflow binding exists for this session.

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
    get_repo_root,
    get_session_binding,
    resolve_state_root,
    stamp_session_id,
)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    session_id = payload.get("session_id")
    if not session_id:
        return

    cwd = payload.get("cwd") or "."
    repo_root = get_repo_root(cwd)
    state_root = resolve_state_root(repo_root)

    stamp_session_id(session_id, cwd, state_root)

    binding = get_session_binding(state_root, session_id)
    if binding:
        workflow_id = binding.get("workflow_id", "unknown")
        print(
            f"An active feature-workflow '{workflow_id}' is bound to this "
            "session. Run /feature-workflow resume to continue, or "
            "/feature-workflow status to check state."
        )


if __name__ == "__main__":
    main()
