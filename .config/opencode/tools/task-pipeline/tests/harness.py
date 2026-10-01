"""Test harness: real temporary workspaces (a writable KB folder and a read-only git
source repo), a real workflow directory, and the real `tp.py` CLI run as a subprocess.
Agents are simulated by writing the files a real agent would write."""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

SKILL = Path(__file__).resolve().parents[1]
TP = SKILL / "scripts" / "tp.py"
PY = sys.executable
sys.dont_write_bytecode = True


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        cwd=str(cwd), check=True, capture_output=True, text=True,
    ).stdout


CALC_GO = """// Package calc does arithmetic.
package calc

// Add returns the sum of a and b.
func Add(a, b int) int {
\treturn a + b
}
"""


class Result:
    def __init__(self, proc: subprocess.CompletedProcess):
        self.code = proc.returncode
        self.out = proc.stdout
        self.err = proc.stderr
        self.text = proc.stdout + proc.stderr

    def json(self) -> Any:
        return json.loads(self.out)


class Harness:
    """One workflow with a `kb` (write) and `src` (read) workspace."""

    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="tp-test-", dir=os.environ.get("TMPDIR")))
        self.kb = self.root / "kb"
        self.kb.mkdir()
        self.src = self.root / "src"
        (self.src / "calc").mkdir(parents=True)
        (self.src / "calc" / "calc.go").write_text(CALC_GO)
        (self.src / "README.md").write_text("# calc\n\nA tiny calculator.\n")
        git(self.src, "init", "-q", "-b", "main")
        git(self.src, "add", "-A")
        git(self.src, "commit", "-q", "-m", "init")
        self.wf = self.root / "wf"
        self.request = self.root / "request.txt"
        self.request.write_text("Build a KB for the calc repo.\n")

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    # --- CLI -------------------------------------------------------------

    def tp(self, *args: str, expect: Optional[int] = 0, wf: bool = True) -> Result:
        cmd = [PY, str(TP)] + (["-w", str(self.wf)] if wf else []) + list(args)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        res = Result(subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120))
        if expect is not None and res.code != expect:
            raise AssertionError(f"tp {' '.join(args)} exited {res.code}, expected {expect}:\n{res.text}")
        return res

    def next(self) -> Dict[str, Any]:
        return self.tp("next", "--json").json()

    # --- fixtures --------------------------------------------------------

    def scope(self, **over: Any) -> Dict[str, Any]:
        base = {
            "title": "Calc KB",
            "output": "Markdown KB articles under kb/, one folder per area, linked from kb/index.md.",
            "deliverables": [{"id": "D1", "kind": "kb", "what": "A KB covering calc's code and build", "where": "kb"}],
            "terms": [{"term": "KB", "means": "Markdown files in kb/", "not": "the repo's own docs"}],
            "non_goals": ["No changes to the calc repository"],
            "participants": [{"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."}],
            "review": "none",
            "budget_minutes": 180,
            "workspaces": [
                {"name": "kb", "path": str(self.kb), "mode": "write"},
                {"name": "src", "path": str(self.src), "mode": "read"},
            ],
            "answers": [{"q": "What output do you want?", "a": "Markdown KB articles."}],
        }
        base.update(over)
        return base

    def task(self, tid: str, path: str, **over: Any) -> Dict[str, Any]:
        base = {
            "id": tid, "title": f"Article {tid}", "serves": ["D1"], "agent": "kb-author",
            "workspace": "kb", "paths": [path], "sources": ["src:calc/**"],
            "brief": f"Write the article at {path} about the calc package.",
            "acceptance": ["Explains what Add does, citing src path:line."],
            "checks": ["docs"], "estimate_min": 15, "depends_on": [],
        }
        base.update(over)
        return base

    def plan(self, tasks: Optional[List[Dict[str, Any]]] = None, **over: Any) -> Dict[str, Any]:
        if tasks is None:
            tasks = [
                self.task("T01", "architecture/overview.md"),
                self.task("T02", "build/guide.md"),
                self.task("T03", "index.md", depends_on=["T01", "T02"], checks=[],
                          brief="Write kb/index.md linking every article.",
                          acceptance=["Every article is linked from index.md."]),
            ]
        base = {"title": "Calc KB plan", "summary": "Two articles, then the index.",
                "tasks": tasks, "checks": {}, "final_checks": ["docs-all"]}
        base.update(over)
        return base

    def write_json(self, name: str, data: Dict[str, Any]) -> None:
        (self.wf / name).write_text(json.dumps(data, indent=2))

    def read_json(self, name: str) -> Any:
        return json.loads((self.wf / name).read_text())

    def state(self) -> Dict[str, Any]:
        return json.loads((self.wf / ".tp" / "state.json").read_text())

    # --- lifecycle shortcuts ----------------------------------------------

    def init(self, budget: Optional[int] = None) -> None:
        """`tp init <location>` creates the workflow's own folder under the location; adopt it."""
        args = ["init", str(self.root / "plans"), "--title", "Calc KB", "--request-file", str(self.request)]
        if budget is not None:
            args += ["--budget", str(budget)]
        out = self.tp(*args, wf=False).out
        self.wf = Path(out.splitlines()[0].split("workflow: ", 1)[1])

    def confirmed(self, **scope_over: Any) -> None:
        self.init()
        self.write_json("scope.json", self.scope(**scope_over))
        self.tp("scope", "check")
        self.tp("scope", "confirm", "--answer", "yes, that's the scope")

    def approved(self, plan: Optional[Dict[str, Any]] = None, **scope_over: Any) -> None:
        self.confirmed(**scope_over)
        self.write_json("plan.json", plan or self.plan())
        self.tp("plan", "check")
        self.tp("plan", "submit")
        self.tp("approve", "--answer", "approve")

    # --- simulated agents ----------------------------------------------------

    def run_dir(self, tid: str) -> Path:
        return self.wf / "runs" / tid

    def result(self, tid: str, step: str, status: str = "done", summary: str = "Wrote the article.",
               **extra: Any) -> None:
        data = {"task": tid, "step": step, "status": status, "summary": summary,
                "changed": extra.pop("changed", []), "noticed": extra.pop("noticed", []),
                "questions": extra.pop("questions", [])}
        data.update(extra)
        d = self.run_dir(tid)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"result-{step}.json").write_text(json.dumps(data))

    def review(self, tid: str, n: int, verdict: str, findings: Optional[List[Dict[str, Any]]] = None) -> None:
        d = self.run_dir(tid)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"review-{n}.json").write_text(json.dumps(
            {"task": tid, "verdict": verdict, "findings": findings or []}))

    def good_article(self, rel: str, title: str = "Overview") -> None:
        p = self.kb / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# {title}\n\n`Add` returns the sum of two ints (`calc/calc.go:5`).\n")

    def author(self, tid: str, rel: str, step: str = "author", agent_id: str = "agent-1") -> Result:
        """Dispatch, write a good article, hand back, and record."""
        self.tp("dispatch", tid)
        self.good_article(rel)
        self.result(tid, step, changed=[rel])
        return self.tp("record", tid, "--agent-id", agent_id)


def deep(d: Dict[str, Any]) -> Dict[str, Any]:
    return copy.deepcopy(d)
