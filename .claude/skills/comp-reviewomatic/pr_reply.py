#!/usr/bin/env python3
"""Reply to a GitHub PR review thread.

Usage:
    pr_reply.py THREAD_ID "Reply body text"
    pr_reply.py THREAD_ID --body-file /path/to/reply.txt

Outputs JSON:
    {"success": true, "commentId": "..."}
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gh import graphql, error, output

REPLY_MUTATION = """
mutation($threadId: ID!, $body: String!) {
  addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $threadId, body: $body}) {
    comment {
      id
      url
    }
  }
}
"""


def reply(thread_id, body):
    data = graphql(REPLY_MUTATION, threadId=thread_id, body=body)
    comment = data.get("addPullRequestReviewThreadReply", {}).get("comment", {})
    return {
        "success": True,
        "commentId": comment.get("id", ""),
        "url": comment.get("url", ""),
    }


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        sys.exit(0)

    thread_id = sys.argv[1]

    if sys.argv[2] == "--body-file":
        if len(sys.argv) < 4:
            error("--body-file requires a file path")
        try:
            with open(sys.argv[3]) as f:
                body = f.read()
        except FileNotFoundError:
            error(f"File not found: {sys.argv[3]}")
    else:
        body = sys.argv[2]

    try:
        result = reply(thread_id, body)
        output(result)
    except RuntimeError as e:
        error(str(e))
