#!/usr/bin/env python3
"""Scan open PRs in the current repo and identify candidates for code review.

Usage:
    pr_scan.py

Uses the current repo (determined from git remote). Scans all open PRs and
identifies those that meet ALL of the following criteria:
    1. NOT in draft state
    2. No human reviews (bot reviews like Copilot are ignored)
    3. CI/CD pipeline has no failed stages

Outputs JSON array of candidate PRs:
    [{"number": 123, "url": "...", "title": "...", "author": "...",
      "file_count": 5, "draft": false, "human_reviewed": false,
      "ci_status": "pass", "ci_details": [...]}]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gh import gh, graphql, repo_info, error, output


def has_human_review(owner, repo, number):
    """Check if a PR has been reviewed by a human (not a bot).

    Uses GraphQL to get the __typename of review authors. Bot accounts
    (like copilot-pull-request-reviewer) have __typename "Bot".
    Only __typename "User" counts as a human review.
    """
    data = graphql(
        """
        query($owner: String!, $repo: String!, $number: Int!) {
          repository(owner: $owner, name: $repo) {
            pullRequest(number: $number) {
              reviews(first: 100) {
                nodes {
                  author { __typename login }
                  state
                }
              }
            }
          }
        }
        """,
        owner=owner,
        repo=repo,
        number=number,
    )
    reviews = (
        data.get("repository", {})
        .get("pullRequest", {})
        .get("reviews", {})
        .get("nodes", [])
    )
    return any(
        r.get("author", {}).get("__typename") == "User"
        for r in reviews
        if r.get("author")
    )


def ci_status(number):
    """Get CI status for a PR. Returns (status_string, details_list).

    status_string is one of: "pass", "fail", "pending", "none".
    details_list contains per-check info.

    gh pr checks exits 1 on failures and 8 on pending, so we use check=False.
    """
    checks = gh("pr", "checks", str(number),
                "--json", "name,state,bucket",
                check=False)
    if not checks or not isinstance(checks, list):
        return "none", []

    details = [{"name": c["name"], "state": c["state"], "bucket": c["bucket"]}
               for c in checks]

    if any(c["bucket"] == "fail" for c in checks):
        return "fail", details
    if any(c["bucket"] == "pending" for c in checks):
        return "pending", details
    return "pass", details


def scan(owner, repo):
    """List open PRs that are candidates for code review."""
    prs = gh("pr", "list",
             "--repo", f"{owner}/{repo}",
             "--state", "open",
             "--json", "number,url,title,author,isDraft",
             "--limit", "100")

    candidates = []
    for pr in prs:
        number = pr["number"]

        # Filter 1: not draft (cheapest check)
        if pr.get("isDraft", False):
            continue

        # Filter 3: CI not failing (cheaper than GraphQL review check)
        ci, ci_details = ci_status(number)
        if ci == "fail":
            continue

        # Filter 2: no human review (GraphQL call)
        if has_human_review(owner, repo, number):
            continue

        # Get file count
        files_data = gh("pr", "view", str(number),
                        "--repo", f"{owner}/{repo}",
                        "--json", "files")
        file_count = len(files_data.get("files") or [])

        author = pr.get("author", {})
        author_login = (author.get("login", "unknown")
                        if isinstance(author, dict) else str(author))

        candidates.append({
            "number": number,
            "url": pr["url"],
            "title": pr["title"],
            "author": author_login,
            "file_count": file_count,
            "draft": False,
            "human_reviewed": False,
            "ci_status": ci,
            "ci_details": ci_details,
        })

    return candidates


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        sys.exit(0)

    try:
        owner, repo = repo_info()
        results = scan(owner, repo)
        output(results)
    except RuntimeError as e:
        error(str(e))
