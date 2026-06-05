#!/usr/bin/env python3
"""Fetch review threads from a GitHub PR, with optional Copilot/unresolved filtering.

Usage:
    pr_threads.py PR_NUMBER
    pr_threads.py PR_NUMBER --copilot-only
    pr_threads.py PR_NUMBER --unresolved-only
    pr_threads.py PR_NUMBER --copilot-only --unresolved-only

Outputs JSON array of thread objects:
    [{"id": "...", "path": "file.go", "line": 42, "isResolved": false,
      "isOutdated": false, "isCopilot": true,
      "comments": [{"id": "...", "body": "...", "author": "...",
                     "isBot": true, "createdAt": "..."}]}]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gh import graphql, repo_info, error, output

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


def is_copilot_thread(thread):
    """A thread is Copilot-authored if its first comment's author login contains 'copilot'.

    We match on login substring rather than requiring __typename == 'Bot' because
    GitHub bot account types are inconsistent (may show as Bot, App, or User).
    The login name is the reliable signal.
    """
    comments = thread.get("comments", {}).get("nodes", [])
    if not comments:
        return False
    author = comments[0].get("author") or {}
    login = (author.get("login") or "").lower()
    return "copilot" in login


def fetch_threads(pr_number, copilot_only=False, unresolved_only=False):
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
        if unresolved_only and t.get("isOutdated"):
            continue

        is_copilot = is_copilot_thread(t)
        if copilot_only and not is_copilot:
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
            "isCopilot": is_copilot,
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
    copilot = "--copilot-only" in flags
    unresolved = "--unresolved-only" in flags

    try:
        threads = fetch_threads(pr_num, copilot_only=copilot, unresolved_only=unresolved)
        output(threads)
    except RuntimeError as e:
        error(str(e))
