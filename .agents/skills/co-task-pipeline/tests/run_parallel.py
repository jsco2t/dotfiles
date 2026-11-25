#!/usr/bin/env python3
"""Run unittest classes in isolated processes, coordinated by a bounded thread pool.

python3 -B run_parallel.py -j 4 [module | module.Class | module.Class.test_method ...]
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed


def test_ids(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from test_ids(item)
        else:
            yield item.id()


def classes(start, selection):
    sys.path.insert(0, str(start))
    loader = unittest.TestLoader()
    suite = loader.discover(str(start), pattern="test_*.py", top_level_dir=str(start))
    if loader.errors:
        raise ValueError("Test discovery failed:\n" + "\n".join(loader.errors))
    ids = list(test_ids(suite))
    matches = lambda tid, name: tid == name or tid.startswith(name + ".")
    unknown = [name for name in selection if not any(matches(tid, name) for tid in ids)]
    if unknown:
        raise ValueError("Unknown test selection: " + ", ".join(unknown))
    found = {}
    for tid in ids:
        if not selection or any(matches(tid, name) for name in selection):
            group = found.setdefault(tid.rsplit(".", 1)[0], [])
            if tid not in group:
                group.append(tid)
    if not found:
        raise ValueError("No tests discovered")
    return found


def worker(receipt, ids):
    sys.path.insert(0, str(Path.cwd()))
    suite = unittest.TestLoader().loadTestsFromNames(ids)
    loaded = suite.countTestCases()
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    # Written only after unittest finishes, including legitimate class/module fixture skips.
    Path(receipt).write_text(json.dumps(dict(loaded=loaded, ran=result.testsRun, success=result.wasSuccessful())))
    return 0 if result.wasSuccessful() else 1


def run_one(start, target, ids):
    began = time.monotonic()
    # Pass exact IDs: a method selection must never expand to its entire class.
    with tempfile.TemporaryDirectory(prefix="co-test-worker-") as directory:
        receipt = Path(directory) / "result.json"
        proc = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--worker", str(receipt), *ids],
                              cwd=str(start), capture_output=True, text=True,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        out = proc.stdout + proc.stderr
        try:
            result = json.loads(receipt.read_text())
        except (OSError, ValueError):
            result = {}
        ran = result.get("ran", 0)
        complete = result.get("loaded") == len(ids) and result.get("success") is True
        code = proc.returncode or (0 if complete else 1)
        if not result or result.get("loaded") != len(ids):
            out += f"\nIncomplete worker: expected {len(ids)} tests and a completion receipt.\n"
    return target, ran, code, time.monotonic() - began, out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("selection", nargs="*", help="modules, classes or exact test IDs")
    parser.add_argument("-j", "--jobs", type=int, default=min(4, os.cpu_count() or 1),
                        help="maximum concurrent class processes (default: up to 4)")
    parser.add_argument("--dir", default=str(Path(__file__).resolve().parent), help="test directory")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    start = Path(args.dir).resolve()
    try:
        todo = classes(start, args.selection)
    except (ImportError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    workers = min(args.jobs, len(todo))
    # Large classes start first without storing timing state in the skill or other workspaces.
    order = sorted(todo, key=lambda target: (-len(todo[target]), target))
    began = time.monotonic()
    ran, failed = 0, []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_one, start, target, todo[target]): target for target in order}
        for future in as_completed(futures):
            target = futures[future]
            try:
                _, count, code, seconds, output = future.result()
            except Exception as exc:
                count, code, seconds, output = 0, 1, 0, f"Worker failed: {exc}"
            ran += count
            print(f"{'FAIL' if code else 'PASS'} {target}: {count} tests ({seconds:.1f}s)", flush=True)
            if code:
                failed.append(target)
                print(output.rstrip(), flush=True)
    print(f"\nRan {ran} tests in {len(todo)} classes, {workers} at a time, "
          f"in {time.monotonic() - began:.1f}s")
    print("FAILED: " + ", ".join(sorted(failed)) if failed else "OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(worker(sys.argv[2], sys.argv[3:]) if sys.argv[1:2] == ["--worker"] else main())
