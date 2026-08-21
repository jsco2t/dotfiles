#!/usr/bin/env python3
"""Resolve a GitHub PR review thread.

Usage:
    pr_resolve.py THREAD_ID

Outputs JSON:
    {"success": true, "isResolved": true}

If resolution fails (e.g., insufficient permissions), outputs:
    {"success": false, "error": "..."}
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gh import graphql, error, output

RESOLVE_MUTATION = """
mutation($threadId: ID!) {
  resolveReviewThread(input: {threadId: $threadId}) {
    thread {
      isResolved
    }
  }
}
"""


def resolve(thread_id):
    try:
        data = graphql(RESOLVE_MUTATION, threadId=thread_id)
        resolved = (data.get("resolveReviewThread", {})
                        .get("thread", {})
                        .get("isResolved", False))
        return {"success": True, "isResolved": resolved}
    except RuntimeError as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        sys.exit(0)

    thread_id = sys.argv[1]
    result = resolve(thread_id)
    output(result)
    if not result["success"]:
        sys.exit(1)
