"""Is an in-flight dispatch's agent actually alive? opencode records every agent session in
a local SQLite store; read-only, that store says whether a dispatch's task call ever started
a session and when its agent last produced a turn — the two things a pure clock cannot know.
Grounded in the 2026-11-27 KUB-1335 run: two dispatches sat 21 and 29 minutes with no agent
session at all (their task calls were never sent) while tp reported them in flight and the
watchdog kept firing, and the manager lost one as dead when its call had simply never
started; a live session or a running test command, by contrast, is work — never a stall.

Every read is best-effort: any failure (no store, a locked file, a schema change) returns
None, and the caller falls back to the clock alone — the behavior before this module."""
from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional

# A store whose newest row is older than this is not this run's store (a wrong path, a
# stale copy): trusting it could "prove" a running agent unstarted and double-dispatch it.
_TRUST_WINDOW_MS = 6 * 3600 * 1000
# A session starts within seconds of the task call; this grace absorbs a manager that
# assembles its message a moment before sending.
_STARTED_GRACE_MS = 2 * 60 * 1000


def _db_path() -> Path:
    override = os.environ.get("TP_OPENCODE_DB")
    if override:
        return Path(override)
    data = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data) / "opencode" / "opencode.db"


def _connect() -> Optional[sqlite3.Connection]:
    path = _db_path()
    if not path.is_file():
        return None
    try:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
    except sqlite3.Error:
        return None


def session_activity(agent: Optional[str], tid: str, step: str, since_seconds: float) -> Optional[Dict[str, object]]:
    """The dispatch's agent session, as {"state": "unstarted"} when no session ever started
    for it, or {"state": "live", "idle_min": minutes since its last turn}. None when no
    readable session store says anything (then only the clock decides).

    The label the dispatch printed names the session ("T07 fix", "B3/test-reviewer verify");
    the state records the verify round's step as "review", so both labels are tried."""
    if not agent:
        return None
    con = _connect()
    if con is None:
        return None
    try:
        now_ms = int(time.time() * 1000)
        if con.execute("select 1 from session_v2 where time_updated >= ? limit 1",
                       (now_ms - _TRUST_WINDOW_MS,)).fetchone() is None:
            return None  # not this run's store
        since_ms = now_ms - int(since_seconds * 1000) - _STARTED_GRACE_MS
        labels = [f"{tid} {step}"] + ([f"{tid} verify"] if step == "review" else [])
        marks = ",".join("?" * len(labels))
        row = con.execute(f"select max(time_updated) from session_v2 "
                          f"where agent=? and title in ({marks}) and time_updated >= ?",
                          (agent, *labels, since_ms)).fetchone()
        if row is None or row[0] is None:  # no titled session: an unnamed one still counts
            row = con.execute("select max(time_updated) from session_v2 "
                              "where agent=? and time_updated >= ?", (agent, since_ms)).fetchone()
        if row is None or row[0] is None:
            return {"state": "unstarted"}
        return {"state": "live", "idle_min": max(0.0, (now_ms - row[0]) / 60000)}
    except (sqlite3.Error, ValueError):
        return None
    finally:
        con.close()


def _normalize(cmd: str) -> str:
    """One comparable shape: quotes stripped, runs of whitespace collapsed — the process
    table shows `go test -run AdminCancel` where the command says `-run 'AdminCancel'`."""
    return re.sub(r"\s+", " ", cmd.replace("'", "").replace('"', "")).strip()


def cmd_running(ps_text: str, cmd: str) -> bool:
    """Whether the process table's full text carries this command's line. A leading wrapper
    token with a slash in it (`tools/with-toolchain go test ...`) is not itself a process:
    dropped, the wrapped command is matched instead."""
    if not cmd or not ps_text:
        return False
    norm_ps = _normalize(ps_text)
    if _normalize(cmd) in norm_ps:
        return True
    parts = _normalize(cmd).split(" ")
    if len(parts) > 1 and ("/" in parts[0] or parts[0].endswith(".sh")):
        return _normalize(" ".join(parts[1:])) in norm_ps
    return False


def process_running(cmd: str) -> bool:
    """The live process table, for one command."""
    try:
        ps = subprocess.run(["ps", "-eo", "args="], capture_output=True, text=True, timeout=5)
        return cmd_running(ps.stdout, cmd)
    except (OSError, subprocess.SubprocessError):
        return False
