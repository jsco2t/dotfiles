#!/usr/bin/env python3
"""Run the test suite one test class per process, several at a time.

    python3 run_parallel.py                 # everything, one worker per CPU
    python3 run_parallel.py -j 4 test_plan  # a module, a class (test_plan.PlanTest), or a test id

Nearly all of the suite's time is spent waiting on `tp` subprocesses, so classes run side by
side scale with the worker count. Each class gets its own interpreter: tests that change
os.environ (a fake session store, a fake tool on PATH) cannot leak into one another. The
slowest classes start first, by the timings of the last run (kept in __pycache__, which git
ignores).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


def _ids(suite: Iterable) -> Iterable[str]:
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _ids(item)
        else:
            yield item.id()


def classes(start: Path, selection: List[str]) -> Dict[str, List[str]]:
    """{module.Class: [test ids]} for every discovered test the selection names (all when empty)."""
    sys.path.insert(0, str(start))
    found: Dict[str, List[str]] = {}
    for tid in _ids(unittest.defaultTestLoader.discover(str(start), pattern="test_*.py", top_level_dir=str(start))):
        if tid.startswith("unittest.loader._FailedTest"):
            found.setdefault(tid, []).append(tid)  # an import error: run it so it reports
            continue
        if selection and not any(tid == s or tid.startswith(s + ".") for s in selection):
            continue
        found.setdefault(tid.rsplit(".", 1)[0], []).append(tid)
    return found


def run_one(start: Path, target: str, ids: List[str]) -> Tuple[str, int, int, float, str]:
    """(target, tests run, return code, seconds, output)."""
    t0 = time.monotonic()
    names = [target] if not target.startswith("unittest.loader") else ids
    proc = subprocess.run([sys.executable, "-m", "unittest", "-q", *names], cwd=str(start),
                          capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    m = re.search(r"^Ran (\d+) tests?", out, re.M)
    return target, int(m.group(1)) if m else 0, proc.returncode, time.monotonic() - t0, out


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("selection", nargs="*", help="modules, classes, or test ids (default: all)")
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 4, help="worker processes")
    ap.add_argument("--dir", default=str(Path(__file__).resolve().parent), help="the test directory")
    args = ap.parse_args()
    start = Path(args.dir).resolve()
    timing_file = start / "__pycache__" / "parallel-timings.json"
    try:
        timings = json.loads(timing_file.read_text())
    except (OSError, ValueError):
        timings = {}
    todo = classes(start, args.selection)
    order = sorted(todo, key=lambda c: (-float(timings.get(c, 0)), -len(todo[c]), c))
    t0 = time.monotonic()
    ran, failed = 0, []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = [pool.submit(run_one, start, c, todo[c]) for c in order]
        for fut in as_completed(futures):
            target, n, code, secs, out = fut.result()
            ran += n
            timings[target] = round(secs, 1)
            if code != 0:
                failed.append(target)
                print(f"\n=== FAILED: {target} ({secs:.0f}s)\n{out.rstrip()}", flush=True)
    try:
        timing_file.parent.mkdir(exist_ok=True)
        timing_file.write_text(json.dumps(timings, indent=1, sort_keys=True))
    except OSError:
        pass
    print(f"\nRan {ran} test{'s' if ran != 1 else ''} in {len(todo)} classes, {args.jobs} at a time, "
          f"in {time.monotonic() - t0:.0f}s")
    if failed:
        print(f"FAILED: {len(failed)} class{'es' if len(failed) != 1 else ''}: {', '.join(sorted(failed))}")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
