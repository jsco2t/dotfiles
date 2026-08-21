#!/usr/bin/env python3
"""Scan open PRs in the current repo and identify those that contain only documentation changes.

Usage:
    pr_scan.py

Uses the current repo (determined from git remote). Scans all open PRs and
identifies those where every changed file has a documentation extension
(.md, .mdx, .rst, .adoc, .asciidoc).

Outputs JSON array of doc-only PRs:
    [{"number": 123, "url": "...", "title": "...", "author": "...",
      "files": ["docs/foo.md", "docs/bar.md"], "file_count": 2}]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gh import gh, repo_info, error, output

DOC_EXTENSIONS = {".md", ".mdx", ".rst", ".adoc", ".asciidoc"}


def is_doc_file(path):
    """Return True if the file has a documentation extension."""
    _, ext = os.path.splitext(path)
    return ext.lower() in DOC_EXTENSIONS


def scan(owner, repo):
    """List open PRs that only touch documentation files."""
    prs = gh("pr", "list",
             "--repo", f"{owner}/{repo}",
             "--state", "open",
             "--json", "number,url,title,author",
             "--limit", "100")

    doc_prs = []
    for pr in prs:
        number = pr["number"]
        files_data = gh("pr", "view", str(number),
                        "--repo", f"{owner}/{repo}",
                        "--json", "files")
        files = [f["path"] for f in (files_data.get("files") or [])]

        if not files:
            continue

        if all(is_doc_file(f) for f in files):
            author = pr.get("author", {})
            author_login = author.get("login", "unknown") if isinstance(author, dict) else str(author)
            doc_prs.append({
                "number": number,
                "url": pr["url"],
                "title": pr["title"],
                "author": author_login,
                "files": files,
                "file_count": len(files),
            })

    return doc_prs


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
