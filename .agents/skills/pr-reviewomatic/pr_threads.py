#!/usr/bin/env python3
"""Fetch review threads from a GitHub PR, with optional filtering.

Usage:
    pr_threads.py PR_NUMBER
    pr_threads.py PR_NUMBER --unresolved-only
    pr_threads.py PR_NUMBER --mine-only
    pr_threads.py PR_NUMBER --unresolved-only --mine-only
    pr_threads.py PR_NUMBER --unresolved-only --mine-only --include-outdated

The --mine-only flag filters to threads whose first comment contains
the hidden marker '<!-- pr-reviewomatic -->', which identifies comments
posted by this skill (as opposed to other comments from the same user).

The --include-outdated flag keeps threads on lines that have since changed.
By default, --unresolved-only skips outdated threads. Use --include-outdated
in resolve mode — an outdated thread often means the code was updated to
address the feedback.

Outputs JSON array of thread objects:
    [{"id": "...", "path": "file.go", "line": 42, "isResolved": false,
      "isOutdated": false, "isMine": true,
      "comments": [{"id": "...", "body": "...", "author": "...",
                     "isBot": true, "createdAt": "..."}]}]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gh import graphql, repo_info, error, output

MARKER = "<!-- pr-reviewomatic -->"

THREADS_QUERY = """
query($owner: String!, $repo: String!, $pr: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          startLine
          diffSide
          comments(first: 20) {
            nodes {
              id
              body
              createdAt
              author {
                login
                ... on Bot { __typename }
              }
            }
          }
        }
      }
    }
  }
}
"""


def is_mine(thread):
    """A thread belongs to this skill if any comment contains the marker."""
    for c in thread.get("comments", {}).get("nodes", []):
        if MARKER in (c.get("body") or ""):
            return True
    return False


def fetch_threads(pr_number, unresolved_only=False, mine_only=False, include_outdated=False):
    owner, repo = repo_info()
    data = graphql(THREADS_QUERY, owner=owner, repo=repo, pr=pr_number)

    raw_threads = (data.get("repository", {})
                       .get("pullRequest", {})
                       .get("reviewThreads", {})
                       .get("nodes", []))

    results = []
    for t in raw_threads:
        if unresolved_only and t.get("isResolved"):
            continue
        if unresolved_only and t.get("isOutdated") and not include_outdated:
            continue

        thread_is_mine = is_mine(t)
        if mine_only and not thread_is_mine:
            continue

        comments = []
        for c in t.get("comments", {}).get("nodes", []):
            author_info = c.get("author") or {}
            comments.append({
                "id": c["id"],
                "body": c.get("body", ""),
                "author": author_info.get("login", "unknown"),
                "isBot": "__typename" in author_info and author_info["__typename"] == "Bot",
                "createdAt": c.get("createdAt", ""),
            })

        results.append({
            "id": t["id"],
            "path": t.get("path", ""),
            "line": t.get("line"),
            "startLine": t.get("startLine"),
            "isResolved": t.get("isResolved", False),
            "isOutdated": t.get("isOutdated", False),
            "isMine": thread_is_mine,
            "comments": comments,
        })

    return results


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        sys.exit(0)

    try:
        pr_num = int(sys.argv[1])
    except ValueError:
        error(f"PR number must be an integer, got: {sys.argv[1]}")

    flags = set(sys.argv[2:])
    unresolved = "--unresolved-only" in flags
    mine = "--mine-only" in flags
    outdated = "--include-outdated" in flags

    try:
        threads = fetch_threads(pr_num, unresolved_only=unresolved, mine_only=mine, include_outdated=outdated)
        output(threads)
    except RuntimeError as e:
        error(str(e))
