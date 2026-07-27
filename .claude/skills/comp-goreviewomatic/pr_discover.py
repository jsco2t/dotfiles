#!/usr/bin/env python3
"""Discover a PR from a URL, number, or the current branch.

Usage:
    pr_discover.py                          # discover from current branch
    pr_discover.py 123                      # by number
    pr_discover.py '#123'                   # by number (with hash)
    pr_discover.py https://github.com/org/repo/pull/123  # by URL

Outputs JSON:
    {"number": 123, "url": "...", "title": "...", "branch": "...",
     "owner": "...", "repo": "...", "state": "OPEN"}
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gh import gh, repo_info, error, output


def from_url(url):
    """Extract owner, repo, PR number from a GitHub PR URL."""
    m = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", url)
    if not m:
        return None
    return m.group(1), m.group(2), int(m.group(3))


def discover():
    arg = sys.argv[1].strip().lstrip("#") if len(sys.argv) > 1 else None

    # Case 1: URL
    if arg and "github.com" in arg:
        parsed = from_url(arg)
        if not parsed:
            error(f"Could not parse PR URL: {arg}")
        owner, repo, number = parsed
        pr = gh("pr", "view", str(number),
                "--repo", f"{owner}/{repo}",
                "--json", "number,url,headRefName,title,state")
        pr["owner"] = owner
        pr["repo"] = repo
        pr["branch"] = pr.pop("headRefName", "")
        return pr

    # Case 2: Number
    if arg and arg.isdigit():
        number = int(arg)
        owner, repo = repo_info()
        pr = gh("pr", "view", str(number),
                "--json", "number,url,headRefName,title,state")
        pr["owner"] = owner
        pr["repo"] = repo
        pr["branch"] = pr.pop("headRefName", "")
        return pr

    # Case 3: Discover from current branch
    owner, repo = repo_info()

    try:
        pr = gh("pr", "view", "--json", "number,url,headRefName,title,state")
        pr["owner"] = owner
        pr["repo"] = repo
        pr["branch"] = pr.pop("headRefName", "")
        return pr
    except RuntimeError:
        pass

    from subprocess import run as _run
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                  capture_output=True, text=True).stdout.strip()
    prs = gh("pr", "list", "--head", branch,
             "--json", "number,url,headRefName,title,state")
    if prs:
        pr = prs[0]
        pr["owner"] = owner
        pr["repo"] = repo
        pr["branch"] = pr.pop("headRefName", "")
        return pr

    error(f"No PR found for branch '{branch}'. Provide a PR URL or number.")


if __name__ == "__main__":
    try:
        result = discover()
        output(result)
    except RuntimeError as e:
        error(str(e))
