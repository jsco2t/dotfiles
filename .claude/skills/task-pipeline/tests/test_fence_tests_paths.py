"""The write fence counts a task's `tests_paths` as files it writes.

A real run (KUB-1339) listed each code task's test files only in `tests_paths`, never in
`paths` — the plan schema does not ask for both, and `tp plan check` accepted it. The fence
then charged 8 of 8 code tasks with their own test files and with the test files of the
siblings running beside them, and every fix round it opened told the agent to revert them:
another task's work. Only a file no in-window task may write is still outside the fence."""
from __future__ import annotations

import unittest

from scenarios import CALC_MUL_PY, TEST_PY, Mixed

OTHER_TEST_PY = ("import unittest\nfrom other import sub\n\n\nclass T(unittest.TestCase):\n"
                 "    def test_sub(self):\n        self.assertEqual(sub(3, 2), 1)\n")


class TestsPathsFenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.m = m = Mixed()
        self.h = m.h
        scope = m.scope(["code"], ["code", "correctness"])
        scope["split_tests"] = False
        # The KUB-1339 shape: production files in `paths`, test files only in `tests_paths`.
        m.approve([m.code_task("T01", paths=["calc.py"], tests_paths=["test_calc.py"]),
                   m.code_task("T02", title="sub", paths=["other.py"], tests_paths=["test_other.py"],
                               brief="Add sub(a, b) in other.py.", acceptance=["sub(3, 2) == 1"],
                               test_cmd="python3 -m unittest -q test_other")], scope)

    def tearDown(self) -> None:
        self.m.close()

    def build_t01(self) -> None:
        """T01's fused round: its tests, the observed red run, then the code."""
        m, h = self.m, self.h
        (m.app / "test_calc.py").write_text(TEST_PY)
        h.tp("red", "T01")
        (m.app / "calc.py").write_text(CALC_MUL_PY)
        h.result("T01", "build", changed=["calc.py", "test_calc.py"])

    def test_a_task_writing_its_own_tests_paths_is_inside_the_fence(self) -> None:
        h = self.h
        h.tp("dispatch", "T01")
        self.build_t01()
        out = h.tp("record", "T01", "--agent-id", "ca-1").out
        self.assertNotIn("outside this task's paths", out)
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_check")

    def test_a_sibling_writing_its_tests_paths_is_not_charged_to_this_task(self) -> None:
        m, h = self.m, self.h
        h.tp("dispatch", "T01", "T02")
        (m.app / "test_other.py").write_text(OTHER_TEST_PY)           # T02's tests land mid-round
        self.build_t01()
        out = h.tp("record", "T01", "--agent-id", "ca-1").out
        self.assertNotIn("outside this task's paths", out)
        self.assertNotIn("revert", out)
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_check")

    def test_a_file_no_task_writes_is_still_outside_the_fence(self) -> None:
        m, h = self.m, self.h
        h.tp("dispatch", "T01", "T02")
        (m.app / "stray.py").write_text("x = 1\n")
        self.build_t01()
        out = h.tp("record", "T01", "--agent-id", "ca-1").out
        self.assertIn("outside this task's paths: stray.py", out)
        self.assertNotIn("test_calc.py", out.split("outside this task's paths")[1].split("\n")[0])

    def test_an_idle_siblings_tests_paths_stay_guarded(self) -> None:
        # T02 never ran in T01's window, so nothing excuses a change to its files.
        m, h = self.m, self.h
        h.tp("dispatch", "T01")
        (m.app / "test_other.py").write_text(OTHER_TEST_PY)
        self.build_t01()
        self.assertIn("outside this task's paths: test_other.py", h.tp("record", "T01", "--agent-id", "ca-1").out)


class TestsPathsCheckFilesTest(unittest.TestCase):
    """`{files}` in a per-task check covers the task's tests too. KUB-1339's T01 ran
    `gofmt -l {files}` on its production files only: its three test files, listed only in
    `tests_paths`, were never checked."""

    def setUp(self) -> None:
        import sys
        from pathlib import Path
        from harness import Harness
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from pipeline import run
        self.run = run
        self.h = Harness()
        for rel in ("internal/hub/hub.go", "internal/hub/hub_test.go"):
            (self.h.kb / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.h.kb / rel).write_text("package hub\n")
        self.task = {"id": "T01", "workspace": "kb", "paths": ["internal/hub/hub.go"],
                     "tests_paths": ["internal/hub/hub_test.go"]}

    def tearDown(self) -> None:
        self.h.close()

    def test_a_go_tool_gets_the_tasks_test_files_too(self) -> None:
        kb = self.h.kb
        self.assertEqual(self.run._expand_cmd("gofmt -l {files}", self.task, self.h.scope()),
                         f"gofmt -l {kb / 'internal/hub/hub.go'} {kb / 'internal/hub/hub_test.go'}")


if __name__ == "__main__":
    unittest.main()
