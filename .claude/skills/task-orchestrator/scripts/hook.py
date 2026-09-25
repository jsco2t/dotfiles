#!/usr/bin/env python3
"""task-orchestrator hook entry point for SessionStart, UserPromptSubmit,
PreToolUse, SubagentStart, SubagentStop, and Stop. Register it in
~/.claude/settings.json (see the skill's references/installation.md)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    try:
        from orchestrator.hooks import dispatch
    except Exception:
        return 0
    text, code = dispatch(payload)
    if text:
        print(text)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
