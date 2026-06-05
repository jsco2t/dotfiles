"""Shared helper for calling the gh CLI. Stdlib only — no external deps."""

import json
import subprocess
import sys
import re


def _run(args, *, check=True, capture=True):
    """Run a subprocess, return CompletedProcess."""
    result = subprocess.run(
        args,
        capture_output=capture,
        text=True,
    )
    if check and result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args)}\n{stderr}")
    return result


def gh(*args, json_output=True, check=True):
    """Run a gh CLI command. Returns parsed JSON if json_output=True, else raw stdout.

    Set check=False for commands that exit non-zero on valid data
    (e.g., 'gh pr checks' exits 1 on failures, 8 on pending).
    """
    result = _run(["gh", *args], check=check)
    stdout = result.stdout or ""
    if json_output and stdout.strip():
        return json.loads(stdout)
    if json_output:
        return [] if not stdout.strip() else stdout.strip()
    return stdout.strip()


def graphql(query, **variables):
    """Run a GraphQL query via gh api graphql. Returns the 'data' dict."""
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, val in variables.items():
        flag = "-F" if isinstance(val, int) else "-f"
        cmd.extend([flag, f"{key}={val}"])
    result = _run(cmd)
    parsed = json.loads(result.stdout)
    if "errors" in parsed:
        msgs = "; ".join(e.get("message", str(e)) for e in parsed["errors"])
        raise RuntimeError(f"GraphQL error: {msgs}")
    return parsed.get("data", parsed)


def repo_info():
    """Get owner and repo name from the current git remote."""
    result = _run(["gh", "repo", "view", "--json", "owner,name"], check=False)
    if result.returncode == 0 and result.stdout.strip():
        info = json.loads(result.stdout)
        return info["owner"]["login"], info["name"]
    result = _run(["git", "remote", "get-url", "origin"], check=False)
    if result.returncode == 0:
        url = result.stdout.strip()
        m = re.search(r"[:/]([^/]+)/([^/.]+?)(?:\.git)?$", url)
        if m:
            return m.group(1), m.group(2)
    raise RuntimeError("Cannot determine owner/repo from git remote")


def error(msg):
    """Print error to stderr and exit."""
    print(json.dumps({"error": msg}), file=sys.stderr)
    sys.exit(1)


def output(data):
    """Print JSON to stdout."""
    print(json.dumps(data, indent=2))
