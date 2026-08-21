#!/usr/bin/env python3
"""Post inline review comments on a GitHub PR as a single review.

Creates a pending review, adds all comments to it, then submits it.
This produces one review with multiple inline comments rather than
N independent comments — cleaner for the PR author.

Every comment body is prefixed with a hidden HTML marker so the skill
can later identify its own comments for resolution.

Usage:
    pr_comment.py PR_NUMBER --comments-file /path/to/comments.json

The comments file must contain a JSON array of objects:
    [
      {
        "path": "pkg/foo/bar.go",
        "line": 42,
        "body": "Consider handling the error case here..."
      },
      ...
    ]

Optional fields per comment:
    "side": "RIGHT" (default) or "LEFT" — which diff side the line refers to
    "start_line": int — for multi-line comments, the first line of the range

Outputs JSON:
    {"success": true, "review_id": "...", "comments_posted": 3}
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gh import gh, repo_info, error, output

MARKER = "<!-- doc-reviewomatic -->"


def get_head_sha(pr_number, owner, repo):
    """Get the HEAD commit SHA for the PR."""
    pr = gh("pr", "view", str(pr_number),
            "--repo", f"{owner}/{repo}",
            "--json", "headRefOid")
    return pr["headRefOid"]


def post_review(pr_number, comments):
    """Post a review with inline comments, writing the payload to a temp file."""
    import tempfile

    owner, repo = repo_info()
    head_sha = get_head_sha(pr_number, owner, repo)

    review_comments = []
    for c in comments:
        marked_body = f"{MARKER}\n\n{c['body']}"
        comment = {
            "path": c["path"],
            "line": c["line"],
            "side": c.get("side", "RIGHT"),
            "body": marked_body,
        }
        if "start_line" in c:
            comment["start_line"] = c["start_line"]
            comment["start_side"] = c.get("side", "RIGHT")
        review_comments.append(comment)

    review_body = {
        "commit_id": head_sha,
        "event": "COMMENT",
        "comments": review_comments,
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(review_body, f)
        tmppath = f.name

    try:
        import subprocess
        result = subprocess.run(
            ["gh", "api",
             f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
             "--method", "POST",
             "--input", tmppath],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            if "must be part of the diff" in stderr and len(review_comments) > 1:
                os.unlink(tmppath)
                return _retry_without_invalid(pr_number, owner, repo, head_sha, review_comments)
            raise RuntimeError(f"Failed to create review: {stderr}")
        parsed = json.loads(result.stdout) if result.stdout.strip() else {}
        return {
            "success": True,
            "review_id": parsed.get("id", ""),
            "comments_posted": len(review_comments),
            "comments_dropped": 0,
        }
    finally:
        if os.path.exists(tmppath):
            os.unlink(tmppath)


def _retry_without_invalid(pr_number, owner, repo, head_sha, review_comments):
    """Fall back to posting comments individually, dropping any that fail.

    The batch API rejects the entire review if any comment targets a line
    outside the diff. This retries each comment separately so valid ones
    still land.
    """
    import subprocess
    import tempfile

    posted = 0
    dropped = 0
    dropped_paths = []

    for rc in review_comments:
        single_review = {
            "commit_id": head_sha,
            "event": "COMMENT",
            "comments": [rc],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(single_review, f)
            tmppath = f.name
        try:
            result = subprocess.run(
                ["gh", "api",
                 f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
                 "--method", "POST",
                 "--input", tmppath],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                posted += 1
            else:
                dropped += 1
                dropped_paths.append(f"{rc['path']}:{rc['line']}")
        finally:
            os.unlink(tmppath)

    return {
        "success": posted > 0,
        "review_id": "",
        "comments_posted": posted,
        "comments_dropped": dropped,
        "dropped_locations": dropped_paths,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        sys.exit(0)

    try:
        pr_num = int(sys.argv[1])
    except ValueError:
        error(f"PR number must be an integer, got: {sys.argv[1]}")

    if "--comments-file" not in sys.argv:
        error("--comments-file is required")

    try:
        idx = sys.argv.index("--comments-file")
        comments_path = sys.argv[idx + 1]
    except (IndexError, ValueError):
        error("--comments-file requires a file path argument")

    try:
        with open(comments_path) as f:
            comments = json.load(f)
    except FileNotFoundError:
        error(f"Comments file not found: {comments_path}")
    except json.JSONDecodeError as e:
        error(f"Invalid JSON in comments file: {e}")

    if not isinstance(comments, list) or not comments:
        error("Comments file must contain a non-empty JSON array")

    for i, c in enumerate(comments):
        if "path" not in c or "line" not in c or "body" not in c:
            error(f"Comment {i} missing required fields (path, line, body)")

    try:
        result = post_review(pr_num, comments)
        output(result)
    except RuntimeError as e:
        error(str(e))
