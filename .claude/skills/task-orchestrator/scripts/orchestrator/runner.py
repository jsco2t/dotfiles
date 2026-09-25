"""Run validation / gate commands and capture objective results.

Commands come from the frozen plan (task `validation` blocks, gate.json), never
from the caller, so an agent cannot record evidence for a weaker command. Each
command runs under bash with `pipefail` so a pipe cannot hide a failure.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence

from .common import utcnow

DEFAULT_TIMEOUT = 3600


def run_commands(
    commands: Sequence[str],
    cwd: Path,
    log_dir: Path,
    label: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> List[Dict[str, Any]]:
    log_dir.mkdir(parents=True, exist_ok=True)
    results: List[Dict[str, Any]] = []
    for index, command in enumerate(commands, start=1):
        log = log_dir / f"{label}-{index}.log"
        started = time.time()
        timed_out = False
        with open(log, "w", encoding="utf-8") as handle:
            handle.write(f"$ {command}\n# cwd: {cwd}\n# started: {utcnow()}\n\n")
            handle.flush()
            try:
                proc = subprocess.run(
                    ["/bin/bash", "-c", f"set -o pipefail; {command}"],
                    cwd=str(cwd),
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                )
                code = proc.returncode
            except subprocess.TimeoutExpired:
                code = 124
                timed_out = True
                handle.write(f"\n# TIMED OUT after {timeout}s\n")
            handle.write(f"\n# exit: {code}\n")
        results.append(
            {
                "command": command,
                "exit": code,
                "log": str(log),
                "seconds": round(time.time() - started, 1),
                "timed_out": timed_out,
            }
        )
    return results


def tail(path: str, lines: int = 25) -> str:
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return ""
    return "\n".join(content[-lines:])
