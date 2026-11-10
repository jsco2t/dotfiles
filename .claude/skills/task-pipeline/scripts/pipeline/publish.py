"""Publishing: the manager posts a reviewed `wf:` draft to Jira or Confluence after the human's OK.
A script step in the main session, not an agent's: in real runs a liaison agent drafted the text
itself, re-ran builds and tests to check it, and hand-built the ADF payload three times; and a
Confluence comment the human had approved was refused by the permission check because a sub-agent
made the write (the run never finished). A page edit goes in as storage XHTML with the version it
was based on, so tables and macros survive and a concurrent edit is never overwritten.

`tp publish T##` is the dry run: it renders the draft, records its hash, the workspace HEAD, and
the target's current state, and writes nothing anywhere else. `tp publish T## --answer "..."`
posts exactly that payload once, only if none of those moved, then reads it back."""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from . import adf, run
from . import plan as planmod
from .common import TPError, Workflow, now_iso

TIMEOUT = 120


def _jira() -> str:
    return os.environ.get("TP_JIRA_BIN") or "jira"


def _confluence() -> str:
    return os.environ.get("TP_CONFLUENCE_BIN") or "confluence"


def _call(args: List[str], stdin: Optional[str] = None, tool: str = "jira") -> str:
    binary = _confluence() if tool == "confluence" else _jira()
    try:
        proc = subprocess.run([binary, *args], input=stdin, capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TPError(f"`{tool} {' '.join(args[:3])}` could not run: {exc}. `atlassian doctor` diagnoses auth and "
                      "connectivity (inside the sandbox, allow ciqinc.atlassian.net).")
    if proc.returncode != 0:
        raise TPError(f"`{tool} {' '.join(args[:3])}` failed (exit {proc.returncode}): "
                      f"{(proc.stderr or proc.stdout).strip()[:400]}")
    return proc.stdout


CONFLUENCE = ("confluence-comment", "confluence-page")


def _page(pid: str) -> Dict[str, Any]:
    """A Confluence page as the API stores it: title, version, and storage XHTML body."""
    data = json.loads(_call(["page", str(pid), "--raw", "--body-format", "storage"], tool="confluence") or "{}")
    version = (data.get("version") or {}).get("number")
    if not isinstance(version, int):
        raise TPError(f"Confluence page {pid} came back without a version: cannot edit it safely.")
    return {"title": data.get("title", ""), "version": version,
            "storage": ((data.get("body") or {}).get("storage") or {}).get("value") or ""}


def storage_text(xhtml: str) -> str:
    """A storage body's words, for the read-back and the dry run's comparison."""
    text = re.sub(r"<[^>]+>", " ", re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", xhtml, flags=re.S))
    return " ".join(html.unescape(text).split())


def structure(xhtml: str) -> Dict[str, int]:
    """What a flat-text edit destroys: in a real run an agent could only read a page as flat text and
    could not apply the edits without losing its tables and code block."""
    return {"tables": len(re.findall(r"<table\b", xhtml)),
            "macros": len(re.findall(r"<ac:structured-macro\b", xhtml)),
            "headings": len(re.findall(r"<h[1-6]\b", xhtml)),
            "links": len(re.findall(r"<a\b|<ac:link\b", xhtml))}


def _comments(key: str) -> List[Dict[str, Any]]:
    data = json.loads(_call(["issue", "comments", key, "--json", "--limit", "100"]) or "[]")
    return data if isinstance(data, list) else []


def _description(key: str) -> Any:
    data = json.loads(_call(["issue", "get", key, "--raw", "--fields", "description"]) or "{}")
    return (data.get("fields") or {}).get("description")


def _issue_fields(key: str) -> Dict[str, Any]:
    data = json.loads(_call(["issue", "get", key, "--raw", "--fields", "summary,description"]) or "{}")
    return data.get("fields") or {}


def _split_issue(text: str) -> Tuple[str, str]:
    """A jira-issue draft: its first non-blank line is the summary, the rest the description."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip():
            return ln.strip().lstrip("#").strip(), "\n".join(lines[i + 1:]).strip() + "\n"
    return "", ""


def _target_state(pub: Dict[str, Any]) -> Dict[str, Any]:
    """What the dry run saw at the target; the post goes ahead only if it is unchanged."""
    if pub["to"] == "confluence-page":
        page = _page(pub["target"])
        return {"version": page["version"], "title": page["title"]}
    if pub["to"] == "confluence-comment":
        return {"title": _page(pub["target"])["title"]}  # the page exists; comments do not collide
    if pub["to"] == "jira-issue":
        _issue_fields(pub["target"])  # the parent must exist (an unknown key fails the call)
        return {"parent": pub["target"]}
    if pub["to"] == "jira-comment":
        comments = _comments(pub["target"])
        state: Dict[str, Any] = {"comments": len(comments)}
        if pub.get("comment_id"):
            mine = [c for c in comments if str(c.get("id")) == str(pub["comment_id"])]
            if not mine:
                raise TPError(f"{pub['target']} has no comment {pub['comment_id']} to edit.")
            state["text"] = adf.text_of(mine[0].get("body"))
        return state
    return {"text": adf.text_of(_description(pub["target"]))}


def _what(pub: Dict[str, Any]) -> str:
    if pub["to"] == "confluence-page":
        return f"replace the body of Confluence page {pub['target']}"
    if pub["to"] == "confluence-comment":
        return f"add one footer comment to Confluence page {pub['target']}"
    if pub["to"] == "jira-issue":
        return (f"create a {pub.get('type', 'Task')} in {pub.get('project')} under {pub['target']}: "
                f"{pub.get('_summary', '')!r}")
    if pub["to"] == "jira-comment":
        return (f"edit comment {pub['comment_id']} on {pub['target']}" if pub.get("comment_id")
                else f"add one comment to {pub['target']}")
    return f"replace the description of {pub['target']}"


def _post(pub: Dict[str, Any], payload: str, body_file: Optional[str] = None,
          version: Optional[int] = None) -> str:
    if pub["to"] == "confluence-page":
        # --version: the CLI refuses if anyone edited the page since the dry run read it.
        _call(["update", str(pub["target"]), "--body-file", str(body_file), "--storage", "--version",
               str(version), "--json"], tool="confluence")
        return str(pub["target"])
    if pub["to"] == "confluence-comment":
        out = _call(["comment", str(pub["target"]), "-", "--adf", "--json"], stdin=payload, tool="confluence")
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            return ""
        pub["_response"] = data
        return str(data.get("id") or "")
    if pub["to"] == "jira-issue":
        args = ["issue", "create", "--project", str(pub["project"]), "--type", str(pub["type"]),
                "--parent", pub["target"], "--summary", pub["_summary"]]
        for label in pub.get("labels") or []:
            args += ["--label", str(label)]
        out = _call(args + ["--field", f"description={payload}", "--json"])
        try:
            return str(json.loads(out).get("key") or "")
        except (json.JSONDecodeError, AttributeError):
            return out.strip().split()[0] if out.strip() else ""
    if pub["to"] == "jira-comment":
        args = ["issue", "comment", pub["target"], "-", "--adf", "--json"]
        if pub.get("comment_id"):
            args += ["--id", str(pub["comment_id"])]
        out = _call(args, stdin=payload)
        try:
            return str(json.loads(out).get("id") or pub.get("comment_id") or "")
        except json.JSONDecodeError:
            return str(pub.get("comment_id") or "")
    _call(["issue", "edit", pub["target"], "--field", f"description={payload}"])
    return pub["target"]


def _read_back(pub: Dict[str, Any], posted: str, doc: Any) -> Tuple[bool, str]:
    if pub["to"] == "confluence-page":
        stored = _page(pub["target"])["storage"]
        if storage_text(stored) != storage_text(doc):
            return False, "the page's text differs from what was sent"
        if structure(stored) != structure(doc):
            return False, f"the page's structure differs from what was sent ({structure(stored)} vs {structure(doc)})"
        return True, f"matches what was sent ({len(storage_text(doc).split())} words, {structure(doc)})"
    if pub["to"] == "confluence-comment":
        if not posted:
            return False, "the comment call returned no comment id"
        body = ((pub.get("_response") or {}).get("body") or {}).get("atlas_doc_format") or {}
        value = body.get("value") if isinstance(body, dict) else None
        if not value:
            return True, (f"comment {posted} created (the Confluence CLI cannot list comments, so its text was not "
                          "read back)")
        try:
            stored = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return True, f"comment {posted} created (its stored body could not be parsed for a read-back)"
        if adf.text_of(stored) != adf.text_of(doc):
            return False, "the stored comment differs from what was sent"
        return True, f"comment {posted} matches what was sent ({len(adf.text_of(doc).split())} words)"
    if pub["to"] == "jira-issue":
        if not posted:
            return False, "the create call returned no issue key"
        fields = _issue_fields(posted)
        if fields.get("summary") != pub["_summary"]:
            return False, f"{posted}'s summary differs from what was sent"
        stored = fields.get("description")
    elif pub["to"] == "jira-comment":
        stored = next((c.get("body") for c in _comments(pub["target"]) if str(c.get("id")) == posted), None)
    else:
        stored = _description(pub["target"])
    if stored is None:
        return False, "the posted text is not there"
    if adf.text_of(stored) != adf.text_of(doc):
        return False, "the stored text differs from what was sent"
    markup = adf.literal_markup(stored)
    if markup:
        return False, f"Markdown survived as literal text ({markup[0][:60]!r})"
    return True, f"matches what was sent ({len(adf.text_of(doc).split())} words, rich text)"


def cmd_publish(wf: Workflow, tid: str, answer: Optional[str]) -> str:
    with wf.locked():
        state = wf.load()
        if state["phase"] != "EXECUTING":
            raise TPError(f"publish runs while EXECUTING; the workflow is {state['phase']}.")
        plan, scope, tasks = run._loaded(wf, state)
        task = tasks.get(tid)
        if task is None or not planmod.is_publish(task):
            raise TPError(f"{tid} is not a publish task in the approved plan.")
        ts = state["tasks"][tid]
        if ts["status"] in run.DONE_STATES:
            raise TPError(f"{tid} is already {ts['status']}: it posts once ({ts.get('note') or ''}).")
        act = run._action_for(tid, ts, task, scope, state)
        if not act or act.get("action") != "publish":
            raise TPError(f"{tid} is not ready to publish: it waits on its dependencies, and on every other task and "
                          "the final review — the external system is written once, with reviewed content.")
        pub = dict(task["publish"])
        body = wf.root / planmod.wf_rel(pub["body"])
        if not body.is_file():
            raise TPError(f"{body} does not exist; the task that writes it must be accepted first.")
        text = body.read_text()
        if pub["to"] == "jira-issue":
            pub["_summary"], text = _split_issue(text)
            if not pub["_summary"]:
                raise TPError(f"{body} is empty: a jira-issue draft's first line is the issue summary.")
        page_edit = pub["to"] == "confluence-page"
        base_version = None
        if page_edit:
            if not text.strip():
                raise TPError(f"{body} is empty: a confluence-page draft is the page's whole new storage body.")
            doc, payload = text, text  # storage XHTML, sent as written
            if pub.get("base"):
                base_path = wf.root / planmod.wf_rel(pub["base"])
                try:
                    base_version = (json.loads(base_path.read_text()).get("version") or {}).get("number")
                except (OSError, ValueError, AttributeError):
                    raise TPError(f"{base_path} is not the page as read when the draft started (`confluence page "
                                  f"{pub['target']} --raw --body-format storage > {base_path}`).")
        else:
            doc = adf.to_adf(text)
            payload = json.dumps(doc, separators=(",", ":"), sort_keys=True)
        # The summary is part of what the human approves, so a changed summary needs a new dry run.
        sha = hashlib.sha256(((pub["_summary"] + "\n") if "_summary" in pub else "").encode()
                             + payload.encode()).hexdigest()
        head = run._git_head(run._ws(scope, task["workspace"]))
        out_file = wf.run_dir(tid) / ("payload.xml" if pub["to"] == "confluence-page" else "payload.json")

        if answer is None:
            seen = _target_state(pub)
            page_lines: List[str] = []
            if page_edit:
                if base_version is not None and seen["version"] != base_version:
                    raise TPError(f"Confluence page {pub['target']} is at version {seen['version']}, but the draft was "
                                  f"written from version {base_version}: someone edited it since. Re-read it into "
                                  f"`{pub['base']}`, rework the draft on top of their edit (a fix round), and dry-run "
                                  "again — never overwrite their change.")
                current = _page(pub["target"])["storage"]
                before, after = structure(current), structure(doc)
                page_lines = [f"page structure (now → after): " + ", ".join(
                    f"{k} {before[k]} → {after[k]}" for k in before),
                    f"page words: {len(storage_text(current).split())} → {len(storage_text(doc).split())}"]
                page_lines += [f"WARN: the new body has fewer {k} ({before[k]} → {after[k]}) — a replacement keeps "
                               "everything it does not mean to change; show the human this line."
                               for k in before if after[k] < before[k]]
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(doc if page_edit else json.dumps(doc, indent=1) + "\n")
            ts["publish"] = {"sha": sha, "head": head, "seen": seen, "ts": now_iso()}
            ts["started"] = ts.get("started") or now_iso()
            wf.save(state)
            wf.event("publish_dry_run", id=tid, sha=sha[:12])
            markup = [] if page_edit else adf.literal_markup(doc)
            preview = [ln for ln in body.read_text().splitlines() if ln.strip()][:30]
            return "\n".join(
                [f"DRY RUN {tid}: {_what(pub)} — nothing was written.",
                 f"payload: {out_file} ({'storage XHTML' if page_edit else 'ADF rendered'} from {body.name}), "
                 f"sha256 {sha[:16]}", *page_lines,
                 f"pre-flight: HEAD {(head or 'n/a')[:12]}; " + ", ".join(f"{k} {v if k != 'text' else '(recorded)'}"
                                                                     for k, v in seen.items()),
                 *([f"WARN: Markdown the renderer left as text: {markup[0][:80]!r}"] if markup else []),
                 "draft (what the human approves):"] + [f"  {ln}" for ln in preview]
                + (["  …"] if len(preview) == 30 else [])
                + ["Show the human the draft path and what it says, and ask once — every publish that is ready in "
                   "the same question, in plain text if agents are in flight — then "
                   f"`tp publish {tid} --answer \"<their words>\"`. A change to the draft, HEAD, or {pub['target']} "
                   "before then means a new dry run and a new ask."])

        dry = ts.get("publish")
        if not dry:
            raise TPError(f"run the dry run first (`tp publish {tid}`) and show the human what it prints.")
        if dry.get("posted"):
            raise TPError(f"{tid} was already posted ({dry['posted']}); its read-back needs the human's decision.")
        if sha != dry["sha"]:
            raise TPError(f"{body.name} changed since the dry run the human approved: run `tp publish {tid}` again and "
                          "ask again.")
        if head != dry["head"]:
            raise TPError(f"the workspace HEAD moved since the dry run ({(dry['head'] or 'n/a')[:12]} → "
                          f"{(head or 'n/a')[:12]}): the draft may describe an older state. Re-check it, run the dry "
                          "run again, and ask again.")
        now = _target_state(pub)
        if now != dry["seen"]:
            moved = "; ".join(f"{k}: {dry['seen'].get(k) if k != 'text' else 'as recorded'} → "
                              f"{v if k != 'text' else 'changed'}" for k, v in now.items() if dry["seen"].get(k) != v)
            raise TPError(f"{pub['target']} changed since the dry run ({moved}) — someone else wrote there (new "
                          f"comments or edits). Read it, run `tp publish {tid}` again, and ask the human again.")
        if page_edit:
            out_file.write_text(payload)  # exactly the approved bytes (the sha above proved them unchanged)
        posted = _post(pub, payload, body_file=str(out_file), version=now.get("version"))
        ok, detail = _read_back(pub, posted, doc)
        dry["posted"] = posted or pub["target"]
        wf.decision(f"publish {tid}", answer, who="human")
        if not ok:
            ts["status"] = "blocked"
            ts["blocked"] = {"kind": "exception", "prior": "pending", "since": now_iso(),
                             "summary": f"{tid} posted ({_what(pub)}), but the read-back failed: {detail}"}
            wf.save(state)
            wf.event("publish", id=tid, ok=False)
            return (f"POSTED {tid} ({_what(pub)}), but the read-back failed: {detail}. Do not post again: show the "
                    "human, and resolve with their decision (`tp resolve --task ... --by human`).")
        ts.update(status="accepted", accepted=now_iso(),
                  note=f"published: {_what(pub)}" + (f" (id {posted})" if posted else "") + f"; read back: {detail}")
        wf.save(state)
        wf.event("publish", id=tid, ok=True)
        wf.event("accept", id=tid, minutes=round(run.task_minutes(state, ts), 1))
        return (f"published {tid}: {_what(pub)}" + (f" → {posted}" if pub["to"] == "jira-issue" and posted else "")
                + f"; read back: {detail}. `tp next`.")
