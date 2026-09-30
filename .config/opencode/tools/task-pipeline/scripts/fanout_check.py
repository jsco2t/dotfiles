#!/usr/bin/env python3
"""fanout_check — how many sub-agents an OpenCode session started, and whether a budget held.

Sources, mixed freely:
  - a session id (ses_…) or a whole manager session: read from the OpenCode store
    (default ~/.local/share/opencode/opencode.db, override with --db). Use --since to count
    only from a marker, e.g. --since /oc-task-pipeline for the command that started the run.
  - a JSONL export: one OpenCode part object per line
    ({"type":"tool","tool":"task","state":{"input":{...}}}, ...).

  python3 fanout_check.py <ses_id|file>... [--db PATH] [--max N] [--since TEXT]

Per source it reports: the `task` calls (fresh dispatches and resumes of a finished agent's
session), the largest batch sent in one message (the parallel fan-out — the pipeline's cap is on
agents in flight, not calls over a run), the agent types, whether the session text carried the
pipeline's `--max-agents=0` budget line, and the other tools used.

Exit code 1 when --max is given and any source sent a parallel batch larger than N.
"""
from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import sys
from pathlib import Path

# The line /task-pipeline briefs carry to switch an agent's own fan-out off.
BUDGET_MARK = "--max-agents=0"
DEFAULT_DB = Path.home() / ".local/share/opencode/opencode.db"


def db_parts(db: Path, session_id: str):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT data, time_created, message_id FROM part WHERE session_id = ? ORDER BY time_created, id",
            (session_id,)).fetchall()
    finally:
        conn.close()
    for data, ts, message_id in rows:
        try:
            yield json.loads(data), ts, message_id
        except json.JSONDecodeError:
            continue


def jsonl_parts(path: str):
    with open(path, errors="replace") as handle:
        for n, line in enumerate(handle):
            try:
                yield json.loads(line), n, f"line-{n}"
            except json.JSONDecodeError:
                continue


def summarize(source: str, db: Path, since: str | None) -> dict:
    parts = db_parts(db, source) if source.startswith("ses_") else jsonl_parts(source)
    tools: collections.Counter = collections.Counter()
    batches: collections.Counter = collections.Counter()
    types, batches_per_message = [], collections.Counter()
    budget_seen, counting = False, since is None
    marker_ts = None
    for data, ts, message_id in parts:
        text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
        if marker_ts is None and since and since in text:
            marker_ts = ts
        if not counting:
            counting = marker_ts is not None
            if not counting:
                continue
        if BUDGET_MARK in text:
            budget_seen = True
        if not isinstance(data, dict) or data.get("type") != "tool":
            continue
        name, state = data.get("tool", "?"), data.get("state") or {}
        inp = state.get("input") or {}
        tools[name] += 1
        if name == "task":
            batches_per_message[message_id] += 1
            types.append(inp.get("subagent_type") or ("resume " + inp["task_id"] if inp.get("task_id") else "resume"))
    batches = list(batches_per_message.values())
    return {"source": source, "budget_seen": budget_seen, "agents": tools.pop("task", 0),
            "largest_batch": max(batches, default=0), "types": types, "other": dict(tools),
            "found_marker": counting}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("sources", nargs="+", help="a session id (ses_…) or a JSONL export")
    p.add_argument("--db", default=str(DEFAULT_DB), help="the OpenCode session store")
    p.add_argument("--max", type=int, help="the sub-agent budget the run was given")
    p.add_argument("--since", help="count only from the first part containing this text")
    args = p.parse_args(argv)
    failed = False
    for source in args.sources:
        s = summarize(source, Path(args.db), args.since)
        print(f"== {source}")
        if not s["found_marker"]:
            print(f"   marker {args.since!r} not found — nothing counted")
            continue
        print(f"   budget line present: {'yes' if s['budget_seen'] else 'no (no /task-pipeline brief in scope?)'}")
        print(f"   task calls: {s['agents']} · largest parallel batch: {s['largest_batch']}"
              + (f" · types: {', '.join(s['types'])}" if s["types"] else ""))
        print(f"   other tools: {s['other'] or 'none'}")
        if args.max is not None:
            over = s["largest_batch"] > args.max
            failed |= over
            print(f"   {'OVER BUDGET' if over else 'within budget'} (max {args.max} in flight)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
