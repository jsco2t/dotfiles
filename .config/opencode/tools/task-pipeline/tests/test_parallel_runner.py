"""The suite runs one test class per process, several at a time (`python3 run_parallel.py`):
serially it takes about eight minutes, nearly all of it spent waiting on `tp` subprocesses."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RUNNER = Path(__file__).resolve().parent / "run_parallel.py"

OK = ("import unittest\n\n\nclass A(unittest.TestCase):\n    def test_one(self):\n        pass\n\n"
      "    def test_two(self):\n        pass\n\n\nclass B(unittest.TestCase):\n    def test_three(self):\n"
      "        pass\n")
BAD = ("import unittest\n\n\nclass C(unittest.TestCase):\n    def test_broken(self):\n"
       "        self.assertEqual(1, 2, 'the broken one')\n")


class ParallelRunnerTest(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "test_ok.py").write_text(OK)
        (self.dir / "test_bad.py").write_text(BAD)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_it(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(RUNNER), "--dir", str(self.dir), "-j", "2", *args],
                               capture_output=True, text=True, timeout=120)

    def test_every_class_runs_and_a_failure_is_shown_and_fails_the_run(self) -> None:
        res = self.run_it()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("Ran 4 tests", res.stdout)
        self.assertIn("test_bad.C", res.stdout)
        self.assertIn("the broken one", res.stdout)

    def test_a_selection_runs_only_what_it_names(self) -> None:
        res = self.run_it("test_ok")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("Ran 3 tests", res.stdout)
        self.assertIn("OK", res.stdout)
        res = self.run_it("test_ok.B")
        self.assertIn("Ran 1 test", res.stdout)


if __name__ == "__main__":
    unittest.main()
