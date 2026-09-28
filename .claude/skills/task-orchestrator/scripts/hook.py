#!/usr/bin/env python3
"""task-orchestrator hook entry point.

`hook.py` handles SessionStart, UserPromptSubmit, UserPromptExpansion,
PreToolUse, SubagentStart, SubagentStop, and Stop — register it in
~/.claude/settings.json (see the skill's references/installation.md).

`hook.py budget` is the per-agent budget hook: every roster agent definition
registers it in its frontmatter (PreToolUse, matcher "*"), so it sees each of
that agent's tool calls and nothing else.
"""
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
        from orchestrator.hooks import dispatch, dispatch_budget
    except Exception:
        return 0
    budget = len(sys.argv) > 1 and sys.argv[1] == "budget"
    text, code = dispatch_budget(payload) if budget else dispatch(payload)
    if text:
        print(text)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
