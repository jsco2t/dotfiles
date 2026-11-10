"""Code tasks are test-forward: tests first and observed failing (red), then the
implementation observed passing (green), without the tests being weakened."""
from __future__ import annotations

import json
import unittest

from harness import Harness, deep, git

CODE = dict(
    deliverables=[{"id": "D1", "kind": "code", "what": "calc gains mul()", "where": "app"}],
    requirements=[{"id": "R1", "text": "mul(2, 3) returns 6, test-first", "deliverables": ["D1"]}],
    participants=[{"agent": "plan-reviewer", "role": "plan", "why": "Independently reviews the plan against the request."},
                  {"agent": "test-author", "role": "tests", "why": "Writes mul's tests first."},
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
        scope = dict(CODE, workspaces=[{"name": "app", "path": str(self.app), "mode": "write"}], review="final",
                     split_tests=True,  # this class covers the split gates; FusedBuildTest covers the default
                     participants=CODE["participants"] + [  # code is always reviewed
                         {"agent": "correctness-reviewer", "role": "reviewer", "why": "Checks mul's edge cases."}])
        task = {"id": "T01", "title": "mul", "serves": ["D1"], "agent": "code-author", "workspace": "app",
                "paths": ["calc.py", "test_calc.py"], "sources": ["app:calc.py"],
                "brief": "Add mul(a, b) beside add.", "acceptance": ["mul(2, 3) == 6"], "requirements": ["R1"],
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
        self.h.approved(plan=self.plan, **self.scope)
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


class FusedBuildTest(unittest.TestCase):
    """The default code flow: one code-author round writes the tests (observed red, saved to a
    log the pipeline checks), implements to green, and hands back once."""

    def setUp(self) -> None:
        self.h = h = Harness()
        self.app = h.root / "app"
        self.app.mkdir()
        (self.app / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        git(self.app, "init", "-q", "-b", "main")
        git(self.app, "add", "-A")
        git(self.app, "commit", "-q", "-m", "init")
        self.scope = dict(CODE, workspaces=[{"name": "app", "path": str(self.app), "mode": "write"}],
                          review="final",
                          participants=CODE["participants"] + [
                              {"agent": "correctness-reviewer", "role": "reviewer", "why": "Checks mul's edge cases."}])
        self.task = {"id": "T01", "title": "mul", "serves": ["D1"], "agent": "code-author", "workspace": "app",
                     "paths": ["calc.py", "test_calc.py"], "sources": ["app:calc.py"],
                     "brief": "Add mul(a, b) beside add.", "acceptance": ["mul(2, 3) == 6"], "requirements": ["R1"],
                     "test_cmd": "python3 -m unittest -q test_calc", "tests_paths": ["test_calc.py"],
                     "checks": [], "estimate_min": 10, "depends_on": []}

    def tearDown(self) -> None:
        self.h.close()

    def approve(self) -> None:
        self.h.approved(plan=self.h.plan([self.task], final_checks=[]), **self.scope)

    def build(self, red_log: bool = True, implement: bool = True, dispatched: bool = False) -> str:
        import subprocess
        if not dispatched:
            self.h.tp("dispatch", "T01")
        (self.app / "test_calc.py").write_text(TEST_PY)
        if red_log:
            proc = subprocess.run(["python3", "-m", "unittest", "-q", "test_calc"], cwd=str(self.app),
                                  capture_output=True, text=True)
            (self.h.run_dir("T01") / "red-build-0.log").write_text(proc.stdout + proc.stderr)
        if implement:
            (self.app / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n")
        self.h.result("T01", "build", changed=["test_calc.py", "calc.py"])
        return self.h.tp("record", "T01", "--agent-id", "ca-1").out

    def test_one_dispatch_is_the_build_step_to_the_code_author(self) -> None:
        self.approve()
        act = self.h.next()["actions"][0]
        self.assertEqual((act["step"], act["agent"]), ("build", "code-author"))
        self.h.tp("dispatch", "T01")
        brief = (self.h.run_dir("T01") / "brief-build-0.md").read_text()
        self.assertIn("tests first, then the implementation", brief)
        self.assertIn("red-build-0.log", brief)
        out = self.build(dispatched=True)
        self.assertIn("red observed", out)
        self.assertIn("green", out)
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "needs_check")  # review:final reviews in bulk at the end
        self.assertEqual(self.h.state()["tasks"]["T01"]["agents"].get("build"), "ca-1")

    def test_a_missing_red_log_fails_the_round(self) -> None:
        self.approve()
        out = self.build(red_log=False)
        self.assertIn("red run's output is missing", out)
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "needs_fix")

    def test_a_red_log_without_a_failure_is_not_red(self) -> None:
        self.approve()
        self.h.tp("dispatch", "T01")
        (self.app / "test_calc.py").write_text("import unittest\n\nclass T(unittest.TestCase):\n"
                                               "    def test_nothing(self):\n        pass\n")
        (self.app / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n")
        (self.h.run_dir("T01") / "red-build-0.log").write_text("OK\neverything passed\n")
        self.h.result("T01", "build", changed=["test_calc.py", "calc.py"])
        out = self.h.tp("record", "T01").out
        self.assertIn("never observed red", out)
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "needs_fix")

    def test_an_implementation_that_stays_red_is_not_green(self) -> None:
        self.approve()
        out = self.build(implement=False)
        self.assertIn("not green", out)
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "needs_fix")

    def test_a_correct_fix_after_a_failed_build_is_recorded(self) -> None:
        """A fix round has no red moment of its own — its goal is green — so the red evidence
        stays the build round's log; a correct fix must record, not be refused over a
        red-fix-1.log no brief ever asked for."""
        import subprocess
        self.approve()
        self.h.tp("dispatch", "T01")
        (self.app / "test_calc.py").write_text(TEST_PY)
        proc = subprocess.run(["python3", "-m", "unittest", "-q", "test_calc"], cwd=str(self.app),
                              capture_output=True, text=True)
        (self.h.run_dir("T01") / "red-build-0.log").write_text(proc.stdout + proc.stderr)
        (self.app / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a + b\n")
        self.h.result("T01", "build", changed=["test_calc.py", "calc.py"])
        self.h.tp("record", "T01", "--agent-id", "ca-1")
        self.assertEqual(self.h.state()["tasks"]["T01"]["fixing"], "build")
        self.h.tp("dispatch", "T01")
        brief = (self.h.run_dir("T01") / "brief-fix-1.md").read_text()
        self.assertIn("red-build-0.log", brief)      # the round-0 evidence, named
        self.assertNotIn("red-fix", brief)           # no fresh red demanded
        (self.app / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n")
        self.h.result("T01", "fix", changed=["calc.py"])
        out = self.h.tp("record", "T01", "--agent-id", "ca-1").out
        self.assertIn("red observed: red-build-0.log", out)
        self.assertIn("green", out)
        self.assertNotEqual(self.h.state()["tasks"]["T01"]["status"], "needs_fix")

    def test_a_fix_round_after_a_missing_red_log_still_demands_the_build_rounds_log(self) -> None:
        """When the build round failed partly because its red log was never saved, the fix
        round's refusal names that same file — the honest path, consistent with the brief."""
        self.approve()
        out = self.build(implement=False, red_log=False)  # red never logged, tests still red
        self.assertIn("missing", out)
        self.h.tp("dispatch", "T01")
        (self.app / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n")
        self.h.result("T01", "fix", changed=["calc.py"])
        out = self.h.tp("record", "T01", "--agent-id", "ca-1").out
        self.assertIn("FAIL", out)
        self.assertIn("red-build-0.log", out)
        self.assertNotIn("red-fix", out)

    def test_split_tests_restores_the_two_agent_flow(self) -> None:
        scope = dict(self.scope, split_tests=True)
        self.h.approved(plan=self.h.plan([self.task], final_checks=[]), **scope)
        act = self.h.next()["actions"][0]
        self.assertEqual((act["step"], act["agent"]), ("tests", "test-author"))


if __name__ == "__main__":
    unittest.main()
