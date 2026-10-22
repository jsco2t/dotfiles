"""A deterministic sizing of a Jira epic/issue or a GitHub issue, from the toolkits' JSON
output: children and their status, which ones are too thin to research, linked pages, and
references. It gives the manager a basis for proposing a research budget — it decides nothing.
`TP_JIRA` / `TP_GHTK` override the CLI commands (tests use fakes)."""
from __future__ import annotations

import json
import math
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .common import TPError

THIN_CHARS = 300
MAX_DEEP = 40
HOSTS = {"jira": "ciqinc.atlassian.net", "gh": "api.github.com"}


def _run(env: str, default: str, args: List[str], source: str) -> Any:
    cmd = shlex.split(os.environ.get(env, default)) + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise TPError(f"`{' '.join(cmd)}` failed to run: {exc}.")
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
        raise TPError(f"`{' '.join(cmd)}` failed: {' '.join(tail)}",
                      f"Inside the sandbox this call needs network access to {HOSTS[source]}.")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise TPError(f"`{' '.join(cmd)}` did not print JSON.")


def parse(ref: str) -> Tuple[str, str]:
    if ref.startswith("jira:") and re.fullmatch(r"[A-Z][A-Z0-9]+-\d+", ref[5:]):
        return "jira", ref[5:]
    if ref.startswith("gh:") and re.fullmatch(r"[\w.-]+/[\w.-]+#\d+", ref[3:]):
        return "gh", ref[3:]
    raise TPError(f"{ref!r}: use jira:KEY-123 or gh:owner/repo#123.")


def jira(key: str) -> Dict[str, Any]:
    root = _run("TP_JIRA", "jira", ["issue", "get", key, "--json", "--description", "--comments"], "jira")
    children = _run("TP_JIRA", "jira", ["search", f"parent = {key}", "--json", "--limit", "200", "--comments"],
                    "jira").get("issues", [])
    if not children:
        children = _run("TP_JIRA", "jira", ["search", f'"Epic Link" = {key}', "--json", "--limit", "200",
                                            "--comments"], "jira").get("issues", [])
    try:
        links = _run("TP_JIRA", "jira", ["issue", "links", key, "--json"], "jira")
    except TPError:
        links = []
    open_ = [c for c in children if c.get("statusCategory") != "Done"]
    thin, sizes = [], {}
    for c in open_[:MAX_DEEP]:
        desc = _run("TP_JIRA", "jira", ["issue", "get", c["key"], "--json", "--description"], "jira").get("description") or ""
        sizes[c["key"]] = len(desc.strip())
        if len(desc.strip()) < THIN_CHARS and len(c.get("comments") or []) <= 1:
            thin.append(c["key"])
    by_status: Dict[str, int] = {}
    for c in children:
        by_status[c.get("statusCategory", "?")] = by_status.get(c.get("statusCategory", "?"), 0) + 1
    return {
        "source": "jira", "key": key, "type": root.get("type"), "summary": root.get("summary"),
        "status": root.get("status"), "labels": root.get("labels", []),
        "description_chars": len((root.get("description") or "").strip()), "comments": len(root.get("comments") or []),
        "links": links if isinstance(links, list) else [],
        "children": [{"key": c["key"], "type": c.get("type"), "status": c.get("status"),
                      "summary": c.get("summary"), "comments": len(c.get("comments") or []),
                      "description_chars": sizes.get(c["key"])} for c in children],
        "counts": {"children": len(children), "open": len(open_), "by_status": by_status},
        "thin": thin,
    }


def github(ref: str) -> Dict[str, Any]:
    repo, _, num = ref.partition("#")
    data = _run("TP_GHTK", "ghtk", ["issue", "get", num, "--repo", repo, "--json", "--comments"], "gh")
    text = (data.get("body") or "") + "\n" + "\n".join(c.get("body", "") for c in data.get("comments") or [])
    refs = set(re.findall(r"(?<![\w/])#\d+\b", text)) | set(re.findall(r"\b[A-Z][A-Z0-9]+-\d+\b", text)) | \
        set(re.findall(r"https://github\.com/[\w.-]+/[\w.-]+/(?:issues|pull)/\d+", text))
    return {"source": "gh", "ref": ref, "title": data.get("title"), "state": data.get("state"),
            "is_pr": data.get("isPullRequest"), "labels": data.get("labels", []),
            "body_chars": len((data.get("body") or "").strip()), "comments": len(data.get("comments") or []),
            "references": sorted(refs)}


def summary(data: Dict[str, Any], out: Path) -> str:
    if data["source"] == "gh":
        return (f"{data['ref']} ({'PR' if data['is_pr'] else 'issue'}, {data['state']}): {data['title']} — "
                f"{data['body_chars']} chars, {data['comments']} comments; references: "
                f"{', '.join(data['references']) or 'none'}.\nfull: {out}")
    c = data["counts"]
    specified = c["open"] - len(data["thin"])
    items = math.ceil(specified / 3) + math.ceil(len(data["links"]) / 2)
    lines = [f"{data['key']} ({data['type']}, {data['status']}): {data['summary']} — {data['description_chars']} chars, "
             f"{data['comments']} comments.",
             f"children: {c['children']} ({', '.join(f'{v} {k}' for k, v in c['by_status'].items()) or 'none'}); "
             f"linked pages: {len(data['links'])}.",
             f"thin (under {THIN_CHARS} chars, at most one comment): {', '.join(data['thin']) or 'none'} — research "
             "cannot invent their requirements; ask the human about them.",
             f"starting point for a research budget: {specified} specified open children ≈ {math.ceil(specified / 3)} "
             f"requirements items (up to 3 issues each) + {len(data['links'])} pages ≈ {math.ceil(len(data['links']) / 2)} "
             f"items → about {items * 10} agent-min at 10 min each. Your judgment decides; ask the human if unsure.",
             f"full: {out}"]
    return "\n".join(lines)
