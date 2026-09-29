#!/usr/bin/env python3
"""fanout_check — how many sub-agents a Claude Code transcript started, and whether a budget held.

Reads JSONL transcripts and reports, per file: the skills loaded (with their args), whether the
loaded skill text carried the `--max-agents` budget paragraph, the Agent calls made, the largest
batch sent in one message (the parallel fan-out), and the other tools used.

Where transcripts are:
  - a sub-agent: the `output_file` the Agent tool printed when it launched (…/tasks/<agentId>.output)
  - a whole session: ~/.claude/projects/<project>/<session-id>.jsonl — use --since to count only
    from a marker, e.g. --since /reviewomatic for a skill you ran yourself

  python3 fanout_check.py <transcript>... [--max N] [--since TEXT]

Exit code 1 when --max is given and any transcript made more Agent calls, or sent a larger
parallel batch, than N.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys

BUDGET_MARK = "Sub-agent budget (`--max-agents=N`"


def summarize(path: str, since: str | None) -> dict:
    tools: collections.Counter = collections.Counter()
    skills, batches, types = [], [], []
    budget_seen, counting = False, since is None
    with open(path, errors="replace") as handle:
        for line in handle:
            if not counting:
                counting = since is not None and since in line
                if not counting:
                    continue
            if BUDGET_MARK in line:
                budget_seen = True
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = record.get("message") if isinstance(record, dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, list):
                continue
            agents_here = 0
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name, inp = block.get("name", "?"), block.get("input") or {}
                tools[name] += 1
                if name == "Skill":
                    skills.append(f"{inp.get('skill')} (args: {str(inp.get('args', ''))[:60]!r})")
                elif name == "Agent":
                    agents_here += 1
                    types.append(inp.get("subagent_type") or "general-purpose")
            if agents_here:
                batches.append(agents_here)
    return {"path": path, "skills": skills, "budget_seen": budget_seen, "agents": tools.pop("Agent", 0),
            "largest_batch": max(batches, default=0), "types": types, "other": dict(tools),
            "found_marker": counting}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("transcripts", nargs="+")
    p.add_argument("--max", type=int, help="the sub-agent budget the run was given")
    p.add_argument("--since", help="count only from the first line containing this text")
    args = p.parse_args(argv)
    failed = False
    for path in args.transcripts:
        s = summarize(path, args.since)
        print(f"== {path}")
        if not s["found_marker"]:
            print(f"   marker {args.since!r} not found — nothing counted")
            continue
        print(f"   skills loaded: {', '.join(s['skills']) or 'none'}")
        print(f"   budget paragraph loaded: {'yes' if s['budget_seen'] else 'no (an older copy of the skill?)'}")
        print(f"   Agent calls: {s['agents']} · largest parallel batch: {s['largest_batch']}"
              + (f" · types: {', '.join(s['types'])}" if s["types"] else ""))
        print(f"   other tools: {s['other'] or 'none'}")
        if args.max is not None:
            over = s["agents"] > args.max or s["largest_batch"] > args.max
            failed |= over
            print(f"   {'OVER BUDGET' if over else 'within budget'} (max {args.max})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
