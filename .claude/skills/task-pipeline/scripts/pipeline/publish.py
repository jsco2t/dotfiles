"""Publishing: the manager posts a reviewed `wf:` draft to Jira after the human's OK. A script
step, not an agent's: in real runs a liaison agent drafted the text itself, re-ran builds and tests
to check it, and hand-built the ADF payload in throwaway scripts three times.

`tp publish T##` is the dry run: it renders the draft, records its hash, the workspace HEAD, and
the target's current state, and writes nothing anywhere else. `tp publish T## --answer "..."`
posts exactly that payload once, only if none of those moved, then reads it back."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from . import adf, run
from . import plan as planmod
from .common import TPError, Workflow, now_iso

TIMEOUT = 120


def _jira() -> str:
    return os.environ.get("TP_JIRA_BIN") or "jira"


def _call(args: List[str], stdin: Optional[str] = None) -> str:
    try:
        proc = subprocess.run([_jira(), *args], input=stdin, capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TPError(f"`jira {' '.join(args[:3])}` could not run: {exc}. `atlassian doctor` diagnoses auth and "
                      "connectivity.")
    if proc.returncode != 0:
        raise TPError(f"`jira {' '.join(args[:3])}` failed (exit {proc.returncode}): "
                      f"{(proc.stderr or proc.stdout).strip()[:400]}")
    return proc.stdout


def _comments(key: str) -> List[Dict[str, Any]]:
    data = json.loads(_call(["issue", "comments", key, "--json", "--limit", "100"]) or "[]")
    return data if isinstance(data, list) else []


def _description(key: str) -> Any:
    data = json.loads(_call(["issue", "get", key, "--raw", "--fields", "description"]) or "{}")
    return (data.get("fields") or {}).get("description")


def _target_state(pub: Dict[str, Any]) -> Dict[str, Any]:
    """What the dry run saw at the target; the post goes ahead only if it is unchanged."""
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
    if pub["to"] == "jira-comment":
        return (f"edit comment {pub['comment_id']} on {pub['target']}" if pub.get("comment_id")
                else f"add one comment to {pub['target']}")
    return f"replace the description of {pub['target']}"


def _post(pub: Dict[str, Any], payload: str) -> str:
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


def _read_back(pub: Dict[str, Any], posted: str, doc: Dict[str, Any]) -> Tuple[bool, str]:
    if pub["to"] == "jira-comment":
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
        pub = task["publish"]
        body = wf.root / planmod.wf_rel(pub["body"])
        if not body.is_file():
            raise TPError(f"{body} does not exist; the task that writes it must be accepted first.")
        doc = adf.to_adf(body.read_text())
        payload = json.dumps(doc, separators=(",", ":"), sort_keys=True)
        sha = hashlib.sha256(payload.encode()).hexdigest()
        head = run._git_head(run._ws(scope, task["workspace"]))
        out_file = wf.run_dir(tid) / "payload.json"

        if answer is None:
            seen = _target_state(pub)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(json.dumps(doc, indent=1) + "\n")
            ts["publish"] = {"sha": sha, "head": head, "seen": seen, "ts": now_iso()}
            ts["started"] = ts.get("started") or now_iso()
            wf.save(state)
            wf.event("publish_dry_run", id=tid, sha=sha[:12])
            markup = adf.literal_markup(doc)
            preview = [ln for ln in body.read_text().splitlines() if ln.strip()][:30]
            return "\n".join(
                [f"DRY RUN {tid}: {_what(pub)} — nothing was written.",
                 f"payload: {out_file} (ADF rendered from {body.name}), sha256 {sha[:16]}",
                 f"pre-flight: HEAD {(head or 'n/a')[:12]}; " + ", ".join(f"{k} {v if k != 'text' else '(recorded)'}"
                                                                     for k, v in seen.items()),
                 *([f"WARN: Markdown the renderer left as text: {markup[0][:80]!r}"] if markup else []),
                 "draft (what the human approves):"] + [f"  {ln}" for ln in preview]
                + (["  …"] if len(preview) == 30 else [])
                + ["Show the human the draft path and what it says, ask once (AskUserQuestion), then "
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
        posted = _post(pub, payload)
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
        return f"published {tid}: {_what(pub)}; read back: {detail}. `tp next`."
