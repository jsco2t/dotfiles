"""Shared fixtures for workflows that mix code, documents, and integration work in one git
workspace: the shape of a real ticket run (tests first, then code, then docs about the code,
then a post to Jira)."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Dict, List, Optional

from harness import Harness, git

CALC_PY = "def add(a, b):\n    return a + b\n"
CALC_MUL_PY = "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"
TEST_PY = ("import unittest\nfrom calc import mul\n\n\nclass T(unittest.TestCase):\n"
           "    def test_mul(self):\n        self.assertEqual(mul(2, 3), 6)\n")

PARTICIPANTS = {
    "tests": {"agent": "test-author", "role": "tests", "why": "Writes mul's tests first, red."},
    "code": {"agent": "code-author", "role": "author", "why": "Implements mul to pass the tests."},
    "docs": {"agent": "doc-author", "role": "author", "why": "Writes the note and the comment text."},
    "liaison": {"agent": "atlassian-liaison", "role": "author", "why": "Performs approved Jira writes."},
    "correctness": {"agent": "correctness-reviewer", "role": "reviewer", "why": "Checks mul's edge cases."},
    "security": {"agent": "security-reviewer", "role": "reviewer", "why": "Checks mul's input handling."},
    "test-review": {"agent": "test-reviewer", "role": "reviewer", "why": "Checks the mul tests prove it."},
    "doc-review": {"agent": "doc-reviewer", "role": "reviewer", "why": "Checks the note against the code."},
}

DELIVERABLES = {
    "code": {"id": "D1", "kind": "code", "what": "calc gains mul()", "where": "app"},
    "docs": {"id": "D2", "kind": "docs", "what": "A note on mul and the KUB-1 comment text", "where": "app"},
    "integration": {"id": "D3", "kind": "integration", "what": "One comment on KUB-1", "where": "jira:KUB-1"},
}


class Mixed:
    """A Harness plus an `app` git repository (the write workspace) holding calc.py."""

    def __init__(self) -> None:
        self.h = h = Harness()
        self.app = h.root / "app"
        self.app.mkdir()
        (self.app / "calc.py").write_text(CALC_PY)
        git(self.app, "init", "-q", "-b", "main")
        git(self.app, "add", "-A")
        git(self.app, "commit", "-q", "-m", "init")

    def close(self) -> None:
        self.h.close()

    # --- scope and plan -------------------------------------------------------------------

    def scope(self, deliverables: List[str], participants: List[str], review: str = "final",
              extra_workspaces: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        return dict(deliverables=[DELIVERABLES[d] for d in deliverables],
                    participants=[PARTICIPANTS[p] for p in participants], review=review,
                    workspaces=[{"name": "app", "path": str(self.app), "mode": "write"}] + (extra_workspaces or []))

    def code_task(self, tid: str = "T01", **over: Any) -> Dict[str, Any]:
        t = {"id": tid, "title": "mul", "serves": ["D1"], "agent": "code-author", "workspace": "app",
             "paths": ["calc.py", "test_calc.py"], "sources": ["app:calc.py"],
             "brief": "Add mul(a, b) beside add.", "acceptance": ["mul(2, 3) == 6"],
             "test_cmd": "python3 -m unittest -q test_calc", "tests_paths": ["test_calc.py"],
             "checks": [], "estimate_min": 10, "depends_on": []}
        t.update(over)
        return t

    def doc_task(self, tid: str = "T02", path: str = "docs/calc.md", **over: Any) -> Dict[str, Any]:
        t = {"id": tid, "title": "Note on mul", "serves": ["D2"], "agent": "doc-author", "workspace": "app",
             "paths": [path], "sources": ["app:calc.py"], "brief": "Explain mul, citing calc.py.",
             "acceptance": ["Explains mul, citing calc.py path:line."], "checks": ["docs"], "estimate_min": 10,
             "depends_on": []}
        t.update(over)
        return t

    def plan(self, tasks: List[Dict[str, Any]], **over: Any) -> Dict[str, Any]:
        return self.h.plan(tasks, final_checks=[], **over)

    def approve(self, tasks: List[Dict[str, Any]], scope: Dict[str, Any], **plan_over: Any) -> None:
        self.h.approved(plan=self.plan(tasks, **plan_over), **scope)

    # --- simulated agents -----------------------------------------------------------------

    def red(self, tid: str = "T01", agent_id: str = "ta-1") -> str:
        h = self.h
        h.tp("dispatch", tid)
        (self.app / "test_calc.py").write_text(TEST_PY)
        h.result(tid, "tests", changed=["test_calc.py"])
        return h.tp("record", tid, "--agent-id", agent_id).out

    def green(self, tid: str = "T01", agent_id: str = "ca-1") -> str:
        h = self.h
        h.tp("dispatch", tid)
        (self.app / "calc.py").write_text(CALC_MUL_PY)
        h.result(tid, "impl", changed=["calc.py"])
        return h.tp("record", tid, "--agent-id", agent_id).out

    def code_done(self, tid: str = "T01") -> None:
        self.red(tid)
        self.green(tid)
        self.h.tp("accept", tid, "--note", "red then green; read the diff")

    def note(self, rel: str = "docs/calc.md", cite: str = "calc.py:5-6") -> None:
        p = self.app / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# mul\n\n`mul` returns the product of two numbers (`{cite}`).\n")

    def doc_done(self, tid: str = "T02", rel: str = "docs/calc.md", cite: str = "calc.py:5-6",
                 agent_id: str = "da-1") -> None:
        h = self.h
        h.tp("dispatch", tid)
        self.note(rel, cite)
        h.result(tid, "author", changed=[rel])
        h.tp("record", tid, "--agent-id", agent_id)
        h.tp("accept", tid, "--note", "citation holds")

    def review_file(self, sid: str, n: int, verdict: str, findings=(), **extra: Any) -> None:
        batch, reviewer = sid.split("/")
        d = self.h.wf / "runs" / batch
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{reviewer}-{n}.json").write_text(json.dumps(
            dict({"batch": batch, "verdict": verdict, "findings": list(findings)}, **extra)))

    @staticmethod
    def finding(fid: str, where: str, state: str = "wrong", blocking: bool = True) -> Dict[str, Any]:
        return {"id": fid, "state": state, "blocking": blocking, "where": where,
                "issue": f"{fid} is {state} at {where}.", "fix": "Correct it."}

    def actions(self) -> List[Dict[str, Any]]:
        return self.h.next()["actions"]

    def status(self, tid: str) -> str:
        return self.h.state()["tasks"][tid]["status"]


class FakeCli:
    """A stand-in for the `jira` (and `ghtk`) CLI: a script that logs every call and keeps
    Jira-like comment state in a JSON file. tp finds it through TP_JIRA_BIN / TP_GHTK_BIN."""

    SCRIPT = r'''#!/usr/bin/env python3
import json, sys
from pathlib import Path
state_path = Path(__file__).with_suffix(".state.json")
log_path = Path(__file__).with_suffix(".log")
state = json.loads(state_path.read_text()) if state_path.exists() else {"comments": [], "next": 100}
args = sys.argv[1:]
body = sys.stdin.read() if "-" in args else None
with open(log_path, "a") as fh:
    fh.write(json.dumps({"args": args, "stdin": body}) + "\n")
def save():
    state_path.write_text(json.dumps(state))
if args[:2] == ["issue", "comments"]:
    print(json.dumps(state["comments"]))
elif args[:2] == ["issue", "create"]:
    def opt(flag):
        return args[args.index(flag) + 1] if flag in args else None
    field = opt("--field") or "description=null"
    key = "KUB-" + str(state.get("next_issue", 900))
    state["next_issue"] = state.get("next_issue", 900) + 1
    state.setdefault("issues", {})[key] = {"summary": opt("--summary"), "parent": opt("--parent"),
                                           "description": json.loads(field.partition("=")[2])}
    save()
    print(json.dumps({"key": key}))
elif args[:2] == ["issue", "get"] and args[2] in state.get("issues", {}):
    print(json.dumps({"key": args[2], "fields": state["issues"][args[2]]}))
elif args[:2] == ["issue", "get"] and "--raw" in args:
    print(json.dumps({"key": args[2], "fields": {"description": state.get("description")}}))
elif args[:2] == ["issue", "edit"]:
    field = args[args.index("--field") + 1]
    name, _, value = field.partition("=")
    state[name] = json.loads(value)
    save()
    print(args[2] + " updated")
elif args[:2] == ["issue", "comment"]:
    doc = json.loads(body)
    if "--id" in args:
        cid = args[args.index("--id") + 1]
        for c in state["comments"]:
            if c["id"] == cid:
                c["body"] = doc
    else:
        cid = str(state["next"]); state["next"] += 1
        state["comments"].append({"id": cid, "body": doc})
    save()
    print(json.dumps({"id": cid, "body": doc}))
else:
    print("unsupported", args, file=sys.stderr)
    sys.exit(3)
'''

    def __init__(self, root: Path, name: str = "jira", env: str = "TP_JIRA_BIN") -> None:
        self.path = root / "bin" / name
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(self.SCRIPT)
        self.path.chmod(self.path.stat().st_mode | stat.S_IEXEC)
        self.env = env
        self.saved = os.environ.get(env)
        os.environ[env] = str(self.path)

    def restore(self) -> None:
        if self.saved is None:
            os.environ.pop(self.env, None)
        else:
            os.environ[self.env] = self.saved

    def calls(self) -> List[Dict[str, Any]]:
        log = self.path.with_suffix(".log")
        return [json.loads(ln) for ln in log.read_text().splitlines()] if log.exists() else []

    def writes(self) -> List[Dict[str, Any]]:
        return [c for c in self.calls() if c["args"][:2] in (["issue", "comment"], ["issue", "edit"],
                                                              ["issue", "create"])]

    def description(self) -> Any:
        state = self.path.with_suffix(".state.json")
        return json.loads(state.read_text()).get("description") if state.exists() else None

    def comments(self) -> List[Dict[str, Any]]:
        state = self.path.with_suffix(".state.json")
        return json.loads(state.read_text())["comments"] if state.exists() else []

    def seed(self, comments: List[Dict[str, Any]]) -> None:
        self.path.with_suffix(".state.json").write_text(json.dumps({"comments": comments, "next": 100}))
