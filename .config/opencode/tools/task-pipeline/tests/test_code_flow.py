"""Code tasks are test-forward: tests first and observed failing (red), then the
implementation observed passing (green), without the tests being weakened."""
from __future__ import annotations

import json
import unittest

from harness import Harness, deep, git

CODE = dict(
    deliverables=[{"id": "D1", "kind": "code", "what": "calc gains mul()", "where": "app"}],
    participants=[{"agent": "test-author", "role": "tests", "why": "Writes mul's tests first."},
                  {"agent": "code-author", "role": "author", "why": "Implements mul to pass them."}],
)

TEST_PY = "import unittest\nfrom calc import mul\n\nclass T(unittest.TestCase):\n" \
          "    def test_mul(self):\n        self.assertEqual(mul(2, 3), 6)\n"


class CodeFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = h = Harness()
        self.app = h.root / "app"
        self.app.mkdir()
        (self.app / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        git(self.app, "init", "-q", "-b", "main")
        git(self.app, "add", "-A")
        git(self.app, "commit", "-q", "-m", "init")
        scope = dict(CODE, workspaces=[{"name": "app", "path": str(self.app), "mode": "write"}])
        task = {"id": "T01", "title": "mul", "serves": ["D1"], "agent": "code-author", "workspace": "app",
                "paths": ["calc.py", "test_calc.py"], "sources": ["app:calc.py"],
                "brief": "Add mul(a, b) beside add.", "acceptance": ["mul(2, 3) == 6"],
                "test_cmd": "python3 -m unittest -q test_calc", "tests_paths": ["test_calc.py"],
                "checks": [], "estimate_min": 10, "depends_on": []}
        self.plan = h.plan([task], final_checks=[])
        self.scope = scope

    def tearDown(self) -> None:
        self.h.close()

    def approve(self, plan=None) -> None:
        self.h.approved(plan=plan or self.plan, **self.scope)

    def write_tests(self) -> None:
        self.h.tp("dispatch", "T01")
        (self.app / "test_calc.py").write_text(TEST_PY)
        self.h.result("T01", "tests", changed=["test_calc.py"])

    def test_code_task_without_a_test_command_is_refused(self) -> None:
        plan = deep(self.plan)
        del plan["tasks"][0]["test_cmd"]
        self.h.confirmed(**self.scope)
        self.h.write_json("plan.json", plan)
        self.assertIn("test_cmd", self.h.tp("plan", "check", expect=2).text)

    def test_red_then_green(self) -> None:
        self.approve()
        act = self.h.next()["actions"][0]
        self.assertEqual((act["step"], act["agent"]), ("tests", "test-author"))
        self.write_tests()
        out = self.h.tp("record", "T01", "--agent-id", "ta-1").out
        self.assertIn("red", out)
        act = self.h.next()["actions"][0]
        self.assertEqual((act["step"], act["agent"]), ("impl", "code-author"))
        self.h.tp("dispatch", "T01")
        (self.app / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n")
        self.h.result("T01", "impl", changed=["calc.py"])
        out = self.h.tp("record", "T01", "--agent-id", "ca-1").out
        self.assertIn("green", out)
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "needs_check")

    def test_tests_that_already_pass_are_not_red(self) -> None:
        self.approve()
        self.h.tp("dispatch", "T01")
        (self.app / "test_calc.py").write_text("import unittest\n\nclass T(unittest.TestCase):\n"
                                               "    def test_nothing(self):\n        pass\n")
        self.h.result("T01", "tests", changed=["test_calc.py"])
        self.assertIn("not red", self.h.tp("record", "T01").out)
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "needs_fix")

    def test_weakening_the_tests_during_implementation_is_caught(self) -> None:
        self.approve()
        self.write_tests()
        self.h.tp("record", "T01")
        self.h.tp("dispatch", "T01")
        (self.app / "test_calc.py").write_text("import unittest\n\nclass T(unittest.TestCase):\n"
                                               "    def test_mul(self):\n        pass\n")
        self.h.result("T01", "impl", changed=["test_calc.py"])
        out = self.h.tp("record", "T01").out
        self.assertIn("tests changed", out)
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "needs_fix")

    def test_code_review_gets_the_change_against_the_approval_baseline(self) -> None:
        base = git(self.app, "rev-parse", "HEAD").strip()
        scope = dict(self.scope, review="final", participants=CODE["participants"] + [
            {"agent": "correctness-reviewer", "role": "reviewer", "why": "Checks mul's edge cases."}])
        self.h.approved(plan=self.plan, **scope)
        self.write_tests()
        self.h.tp("record", "T01")
        self.h.tp("dispatch", "T01")
        (self.app / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n")
        self.h.result("T01", "impl", changed=["calc.py"])
        self.h.tp("record", "T01")
        self.h.tp("accept", "T01", "--note", "ok")
        self.h.tp("dispatch", "B1/correctness-reviewer")
        changes = json.loads((self.h.wf / "runs" / "B1" / "changes.json").read_text())
        self.assertEqual(sorted(changes["files"]), ["app:calc.py", "app:test_calc.py"])
        self.assertIn(base, changes["diff"]["app"])
        self.assertIn("test_calc.py", changes["untracked"]["app"])

    def test_failing_implementation_is_not_green(self) -> None:
        self.approve()
        self.write_tests()
        self.h.tp("record", "T01")
        self.h.tp("dispatch", "T01")
        (self.app / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a + b\n")
        self.h.result("T01", "impl", changed=["calc.py"])
        self.assertIn("not green", self.h.tp("record", "T01").out)
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "needs_fix")


class TestsDeliverableFlowTest(unittest.TestCase):
    """A `tests` deliverable is authored in one step by test-author and recorded only when its
    suite passes against current code (pinned green)."""

    def setUp(self) -> None:
        self.h = h = Harness()
        self.app = h.root / "app"
        self.app.mkdir()
        (self.app / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        git(self.app, "init", "-q", "-b", "main")
        git(self.app, "add", "-A")
        git(self.app, "commit", "-q", "-m", "init")
        self.scope = dict(
            deliverables=[{"id": "D1", "kind": "tests", "what": "A regression suite for calc's Add",
                           "where": "app"}],
            participants=[{"agent": "test-author", "role": "author", "why": "Writes the suite for D1."}],
            workspaces=[{"name": "app", "path": str(self.app), "mode": "write"}])
        self.plan = h.plan([{"id": "T01", "title": "Regression suite", "serves": ["D1"],
                             "agent": "test-author", "workspace": "app", "paths": ["test_add.py"],
                             "sources": ["app:calc.py"], "brief": "Write test_add.py covering Add.",
                             "acceptance": ["Covers Add."],
                             "test_cmd": "python3 -m unittest -q test_add",
                             "checks": [], "estimate_min": 10, "depends_on": []}], final_checks=[])

    def tearDown(self) -> None:
        self.h.close()

    def approve(self) -> None:
        self.h.approved(plan=self.plan, **self.scope)

    def write_suite(self, body: str) -> None:
        self.h.tp("dispatch", "T01")
        (self.app / "test_add.py").write_text(body)
        self.h.result("T01", "author", changed=["test_add.py"])

    def test_a_tests_task_runs_one_author_step_and_records_when_green(self) -> None:
        self.approve()
        act = self.h.next()["actions"][0]
        self.assertEqual((act["step"], act["agent"]), ("author", "test-author"))
        self.write_suite("import unittest\nfrom calc import add\n\nclass T(unittest.TestCase):\n"
                         "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n")
        out = self.h.tp("record", "T01", "--agent-id", "ta-1").out
        self.assertIn("pinned", out)
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "needs_check")

    def test_a_failing_suite_is_not_accepted(self) -> None:
        self.approve()
        self.write_suite("import unittest\nfrom calc import add\n\nclass T(unittest.TestCase):\n"
                         "    def test_add(self):\n        self.assertEqual(add(2, 3), 6)\n")
        out = self.h.tp("record", "T01").out
        self.assertIn("must pass against current code", out)
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "needs_fix")


if __name__ == "__main__":
    unittest.main()
