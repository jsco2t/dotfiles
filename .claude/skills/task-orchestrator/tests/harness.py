"""Test harness: a real temporary git workspace, a real workflow directory, the
real CLI (as a subprocess), and the real hook handlers (in-process), with
synthetic agent hand-offs and human prompts."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ORCH = SCRIPTS / "orch.py"
sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True

from orchestrator import hooks  # noqa: E402
from orchestrator.common import utcnow  # noqa: E402

TEMPLATE_RE = re.compile(r"```orch-result\n(.*?)\n```", re.S)
PY = sys.executable


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        cwd=str(cwd), check=True, capture_output=True, text=True,
    ).stdout


PLAN_MD = """# Plan — add multiplication

## Objective
Give calc a multiplication function.

## Requirements
- R1: calc provides mul(a, b) returning the product.

## Current state
`calc.py:1` defines only `add`.

## Approach
Add `mul` beside `add`, test-forward.

## Architectural decisions
Keep calc a flat module.

## Architectural review
Skipped — one function in one existing module.

## Loop plan
Loop 1: T001.

## Quality gate
`python -m unittest discover -q` — the repository's only test runner.

## Test strategy
Unit tests. Test gap assessment: nothing tests multiplication today.

## Test plan
- `test_mul.TestMul.test_product`: mul(2, 3) == 6.

## Risks
None material.

## Out of scope
Division.

## Final acceptance criteria
- [ ] FAC1: mul(a, b) returns a*b — Verified by: unittest discover

## Open questions
- [x] Q1: Integers only? — Resolution: any numbers.
"""


def task_md(red_cmd: str, task_cmd: str, **meta_overrides: Any) -> str:
    meta = {
        "id": "T001",
        "title": "Add mul",
        "type": "code",
        "loop": 1,
        "depends_on": [],
        "requirements": ["R1"],
        "workspace": "code",
        "authors": ["test-author", "code-author"],
        "reviewers": ["code-reviewer", "test-reviewer"],
        "test_forward": "red-green",
        "estimated_days": 0.5,
        "expected_paths": ["calc.py", "test_mul.py"],
        "validation": {"red_green": [red_cmd], "task": [task_cmd]},
    }
    meta.update(meta_overrides)
    return f"""# T001 — Add mul

```json task
{json.dumps(meta, indent=2)}
```

## Goal
calc.mul exists.

## Context
Requested multiplication.

## Scope
### In scope
mul in calc.py.
### Out of scope
Division.

## Acceptance criteria
- [ ] AC1: mul(2, 3) returns 6 — Verified by: test `test_mul.TestMul.test_product`

## Test plan
- test_product: mul(2, 3) == 6.

## Validation
{red_cmd}

## Dependencies
None.

## Risks / notes
None.
"""


class Harness:
    def __init__(self, git_workspace: bool = True):
        self._tmp = tempfile.TemporaryDirectory(prefix="orch-test-")
        self.tmp = Path(self._tmp.name).resolve()
        self.home = self.tmp / "home"
        self.session = f"test-session-{time.time_ns()}"
        os.environ["TASK_ORCH_HOME"] = str(self.home)
        self.env = dict(os.environ, CLAUDE_CODE_SESSION_ID=self.session, PYTHONDONTWRITEBYTECODE="1")
        self.ws = self.tmp / "ws"
        self.ws.mkdir()
        (self.ws / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        (self.ws / "test_calc.py").write_text(
            "import unittest\nimport calc\n\n\nclass TestAdd(unittest.TestCase):\n"
            "    def test_add(self):\n        self.assertEqual(calc.add(1, 2), 3)\n"
        )
        if git_workspace:
            git(self.ws, "init", "-q")
            git(self.ws, "add", "-A")
            git(self.ws, "commit", "-qm", "init")
        self.wf: Optional[Path] = None
        self.agent_counter = 0

    def close(self) -> None:
        self._tmp.cleanup()

    # -------------------------------------------------------- CLI + hooks
    def orch(self, *args: str, expect: Optional[int] = 0) -> str:
        proc = subprocess.run([PY, str(ORCH), *args], env=self.env, capture_output=True, text=True)
        text = proc.stdout + proc.stderr
        if expect is not None and proc.returncode != expect:
            raise AssertionError(f"orch {' '.join(args)} exited {proc.returncode}, expected {expect}:\n{text}")
        return text

    def hook(self, payload: Dict[str, Any]) -> Tuple[Optional[str], int]:
        full = {"session_id": self.session, "cwd": str(self.tmp)}
        full.update(payload)
        return hooks.dispatch(full)

    def human(self, prompt: str) -> None:
        time.sleep(0.01)
        self.hook({"hook_event_name": "UserPromptSubmit", "prompt": prompt})
        time.sleep(0.01)

    def pretool(self, tool: str, tool_input: Dict[str, Any], agent: Optional[str] = None) -> Optional[str]:
        payload: Dict[str, Any] = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}
        if agent:
            payload.update(agent_type=agent, agent_id=f"agent-{agent}")
        text, _ = self.hook(payload)
        if not text:
            return None
        return json.loads(text)["hookSpecificOutput"]["permissionDecisionReason"]

    def state(self) -> Dict[str, Any]:
        return json.loads((self.wf / ".orch" / "state.json").read_text())

    def ledger(self) -> List[Dict[str, Any]]:
        path = self.wf / ".orch" / "ledger.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    # -------------------------------------------------------- agents
    def agent(
        self,
        brief_args: List[str],
        agent: str,
        verdict: str = "pass",
        status: str = "complete",
        mutate: Optional[Callable[[Dict[str, Any]], None]] = None,
        write_report: bool = True,
        work: Optional[Callable[[], None]] = None,
        raw_message: Optional[str] = None,
        handback: Optional[str] = None,
        handback_error: bool = False,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate the brief, do the 'work', fill the template, hand back via SubagentStop."""
        text = self.orch("brief", *brief_args, "--agent", agent)
        fields = json.loads(TEMPLATE_RE.findall(text)[-1])
        if work:
            work()
        fields["status"] = status
        if fields.get("verdict") == "pass | fail":
            fields["verdict"] = verdict
        if isinstance(fields.get("findings"), dict):
            fields["findings"] = {"blocking": 0, "recorded": 0, "disputes_ruled": 0}
        if isinstance(fields.get("criteria"), list):
            fields["criteria"] = [dict(c, met=True, evidence="asserted by test") for c in fields["criteria"]]
        if "changed_files" in fields:
            fields["changed_files"] = []
        if "external_action" in fields:
            fields["external_action"] = "none"
        if "blockers" in fields:
            fields["blockers"] = []
        if "contract_seen" in fields:
            fields["contract_seen"] = True
        if mutate:
            mutate(fields)
        report = Path(fields["report"])
        if write_report:
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(f"# {agent} report\n\nverdict {fields.get('verdict')}\n")
        block = "```orch-result\n" + json.dumps(fields, indent=2) + "\n```"
        message = raw_message if raw_message is not None else "Done.\n\n" + block
        if agent_id is None:
            self.agent_counter += 1
            agent_id = f"a{self.agent_counter:04d}"
        payload = {
            "hook_event_name": "SubagentStop",
            "agent_type": agent,
            "agent_id": agent_id,
            "last_assistant_message": message,
        }
        if handback is not None:
            self.transcript(agent_id, handback.replace("{block}", block), error=handback_error)
            payload["agent_transcript_path"] = str(self.transcript_path(agent_id))
        self.hook(payload)
        return self.ledger()[-1]

    def transcript_path(self, agent_id: str) -> Path:
        return self.tmp / "transcripts" / self.session / "subagents" / f"agent-{agent_id}.jsonl"

    def transcript(self, agent_id: str, handback: Optional[str], error: bool = False) -> None:
        """Append one turn to the agent's transcript in Claude Code's record shape:
        an optional SubagentHandback call and its tool_result, then a closing text."""
        path = self.transcript_path(agent_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        time.sleep(0.01)
        stamp = utcnow()
        records: List[Dict[str, Any]] = []
        if handback is not None:
            use_id = f"toolu_{time.time_ns()}"
            records.append({"type": "assistant", "timestamp": stamp, "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": use_id, "name": "SubagentHandback", "input": {"message": handback}}]}})
            result = {"type": "tool_result", "tool_use_id": use_id,
                      "content": [{"type": "text", "text": '{"success":true}'}]}
            if error:
                result["is_error"] = True
            records.append({"type": "user", "timestamp": stamp, "message": {"role": "user", "content": [result]}})
        records.append({"type": "assistant", "timestamp": stamp, "message": {"role": "assistant", "content": [
            {"type": "text", "text": "I've sent my report to the orchestrator."}]}})
        with open(path, "a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record) + "\n")
        time.sleep(0.01)

    # -------------------------------------------------------- scenario steps
    def init(self) -> None:
        req = self.tmp / "request.txt"
        req.write_text("Please add multiplication to calc.\n")
        out = self.orch("init", str(self.tmp / "plans"), "--title", "Add mul", "--workspace", f"code={self.ws}",
                        "--request-file", str(req))
        self.wf = Path(out.splitlines()[0])

    def write_plan(self, **task_overrides: Any) -> None:
        assert self.wf is not None
        (self.wf / "plan.md").write_text(PLAN_MD)
        gate = json.loads((self.wf / "gate.json").read_text())
        gate["workspaces"]["code"].update(standard=[f"{PY} -m unittest discover -q"],
                                          final=[f"{PY} -m unittest discover -q"])
        (self.wf / "gate.json").write_text(json.dumps(gate, indent=2))
        (self.wf / "tasks" / "T001-add-mul.md").write_text(
            task_md(f"{PY} -m unittest -q test_mul", f"{PY} -m unittest discover -q", **task_overrides))

    def plan_to_approval(self) -> None:
        self.init()
        self.agent(["research", "--topic", "calc module"], "codebase-researcher")
        self.agent(["pm-research"], "project-manager")
        self.agent(["plan"], "planning-author", work=self.write_plan)
        self.agent(["test-plan"], "test-planner")
        self.agent(["plan-review"], "doc-reviewer")
        self.orch("validate")
        self.agent(["pm-plan"], "project-manager")
        self.orch("submit")
        self.human("/task-orchestrator approve")
        self.orch("approve")

    def write_test(self) -> None:
        (self.ws / "test_mul.py").write_text(
            "import unittest\nimport calc\n\n\nclass TestMul(unittest.TestCase):\n"
            "    def test_product(self):\n        self.assertEqual(calc.mul(2, 3), 6)\n"
        )

    def implement(self) -> None:
        (self.ws / "calc.py").write_text(
            "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n")

    def task_to_ready_for_accept(self) -> None:
        self.agent(["--loop", "1", "pm-loop-entry"], "project-manager")
        self.orch("loop", "open", "1")
        self.orch("task", "start", "T001")
        self.agent(["T001", "readiness"], "task-verifier")
        self.agent(["T001", "pm-start"], "project-manager")

        def tests_then_red() -> None:
            self.write_test()
            self.orch("evidence", "T001", "red")
        self.agent(["T001", "work"], "test-author", work=tests_then_red)
        self.agent(["T001", "pm-scope"], "project-manager")
        self.agent(["T001", "work"], "code-author", work=self.implement)
        self.orch("evidence", "T001", "green")
        self.orch("gate", "run", "standard", "--task", "T001")
        self.agent(["T001", "pm-scope"], "project-manager")
        self.agent(["T001", "verification"], "task-verifier")
        self.agent(["T001", "review"], "code-reviewer")
        self.agent(["T001", "review"], "test-reviewer")
        self.agent(["T001", "pm-accept"], "project-manager")
