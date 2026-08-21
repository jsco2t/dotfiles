#!/usr/bin/env python3
"""Get CI check status for a GitHub PR, with optional failure log retrieval.

Usage:
    pr_checks.py PR_NUMBER
    pr_checks.py PR_NUMBER --failing-only
    pr_checks.py PR_NUMBER --failing-only --logs

Outputs JSON:
    {"checks": [...], "summary": {"total": N, "pass": N, "fail": N, "pending": N}}

With --logs, failing checks include a "log" field with truncated failure output.
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gh import gh, error, output


def get_checks(pr_number, failing_only=False, with_logs=False):
    # gh pr checks exits non-zero when checks fail (1) or are pending (8),
    # but still prints valid JSON — must use check=False
    checks_raw = gh("pr", "checks", str(pr_number),
                     "--json", "name,state,bucket,link,completedAt,workflow",
                     check=False)

    summary = {"total": 0, "pass": 0, "fail": 0, "pending": 0, "skipping": 0}
    checks = []

    for c in checks_raw:
        bucket = c.get("bucket", "")
        summary["total"] += 1
        if bucket in summary:
            summary[bucket] += 1

        if failing_only and bucket != "fail":
            continue

        entry = {
            "name": c.get("name", ""),
            "state": c.get("state", ""),
            "bucket": bucket,
            "link": c.get("link", ""),
            "workflow": c.get("workflow", ""),
            "completedAt": c.get("completedAt", ""),
        }

        if with_logs and bucket == "fail":
            entry["log"] = get_failure_log(c.get("link", ""))

        checks.append(entry)

    return {"checks": checks, "summary": summary}


def get_failure_log(link):
    """Extract run ID from link and fetch failure logs."""
    if not link:
        return "(no link available)"
    m = re.search(r"/actions/runs/(\d+)", link)
    if not m:
        return f"(could not extract run ID from: {link})"
    run_id = m.group(1)
    try:
        result = subprocess.run(
            ["gh", "run", "view", run_id, "--log-failed"],
            capture_output=True, text=True, timeout=30,
        )
        log = result.stdout or result.stderr or "(empty log)"
        max_chars = 5000
        if len(log) > max_chars:
            log = f"...(truncated, showing last {max_chars} chars)...\n" + log[-max_chars:]
        return log
    except subprocess.TimeoutExpired:
        return "(log retrieval timed out)"
    except Exception as e:
        return f"(error fetching log: {e})"


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        sys.exit(0)

    try:
        pr_num = int(sys.argv[1])
    except ValueError:
        error(f"PR number must be an integer, got: {sys.argv[1]}")

    flags = set(sys.argv[2:])
    failing = "--failing-only" in flags
    logs = "--logs" in flags

    try:
        result = get_checks(pr_num, failing_only=failing, with_logs=logs)
        output(result)
    except RuntimeError as e:
        error(str(e))
