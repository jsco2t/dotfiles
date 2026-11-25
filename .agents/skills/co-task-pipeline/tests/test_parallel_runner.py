"""Exercise the parallel runner using real, isolated unittest subprocesses."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


RUNNER = Path(__file__).with_name("run_parallel.py")
PASSING = """import unittest
class A(unittest.TestCase):
    def test_one(self): pass
    def test_two(self): pass
class B(unittest.TestCase):
    def test_three(self): pass
"""


class ParallelRunnerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="co-parallel-")
        self.root = Path(self.temp.name)
        (self.root / "test_ok.py").write_text(PASSING)

    def tearDown(self):
        self.temp.cleanup()

    def run_it(self, *args):
        return subprocess.run([sys.executable, "-B", str(RUNNER), "--dir", str(self.root),
                               "-j", "2", *args], capture_output=True, text=True, timeout=20)

    def test_discovery_runs_every_case_and_reports_actual_count(self):
        result = self.run_it()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Ran 3 tests", result.stdout)

    def test_selection_runs_exact_methods_and_deduplicates_overlaps(self):
        # An unselected sibling fails, so running its class is observably wrong.
        (self.root / "test_ok.py").write_text(PASSING.replace(
            "def test_two(self): pass", "def test_two(self): self.fail('unselected sibling')"))
        result = self.run_it("test_ok.A.test_one", "test_ok.B", "test_ok.B.test_three")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Ran 2 tests", result.stdout)

    def test_unknown_or_partly_unknown_selection_fails(self):
        for names in (("test_missing",), ("test_ok", "test_ok.A.typo")):
            with self.subTest(names=names):
                result = self.run_it(*names)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(names[-1], result.stdout + result.stderr)

    def test_empty_discovery_cannot_pass(self):
        (self.root / "test_ok.py").unlink()
        result = self.run_it()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_failure_and_import_error_preserve_diagnostics(self):
        (self.root / "test_bad.py").write_text(
            "import unittest\nclass Bad(unittest.TestCase):\n"
            " def test_bad(self): self.fail('regression detail')\n")
        result = self.run_it()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("regression detail", result.stdout + result.stderr)
        (self.root / "test_bad.py").write_text("raise RuntimeError('broken fixture import')\n")
        result = self.run_it()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("broken fixture import", result.stdout + result.stderr)

    def test_classes_overlap_with_two_workers(self):
        # Both processes must reach the barrier before either can finish. No speed threshold.
        (self.root / "test_ok.py").write_text("""import time
import unittest
from pathlib import Path
def barrier(mine, other):
    Path(mine).touch()
    deadline = time.monotonic() + 5
    while not Path(other).exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert Path(other).exists(), 'classes did not overlap'
class A(unittest.TestCase):
    def test_a(self): barrier('a.started', 'b.started')
class B(unittest.TestCase):
    def test_b(self): barrier('b.started', 'a.started')
""")
        result = self.run_it()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Ran 2 tests", result.stdout)

    def test_classes_get_fresh_processes_even_with_one_worker(self):
        (self.root / "test_ok.py").write_text("""import os
import unittest
from pathlib import Path
def record(name):
    assert 'CO_RUNNER_FIXTURE' not in os.environ, 'environment leaked'
    os.environ['CO_RUNNER_FIXTURE'] = name
    Path(name + '.pid').write_text(str(os.getpid()))
class A(unittest.TestCase):
    def test_a(self): record('a')
class B(unittest.TestCase):
    def test_b(self): record('b')
""")
        result = self.run_it("-j", "1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotEqual((self.root / "a.pid").read_text(), (self.root / "b.pid").read_text())

    def test_premature_successful_worker_exit_cannot_pass(self):
        (self.root / "test_ok.py").write_text(
            "import os, unittest\nclass A(unittest.TestCase):\n"
            " def test_exit(self): os._exit(0)\n")
        result = self.run_it()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_class_and_module_fixture_skips_are_successful_completed_workers(self):
        for fixture in (
                "def setUpModule(): raise unittest.SkipTest('module unavailable')\n",
                ""):
            with self.subTest(module_fixture=bool(fixture)):
                setup = "" if fixture else (
                    " @classmethod\n def setUpClass(cls): raise unittest.SkipTest('class unavailable')\n")
                (self.root / "test_ok.py").write_text(
                    "import unittest\n" + fixture + "class A(unittest.TestCase):\n" + setup +
                    " def test_one(self): self.fail('fixture should skip this')\n"
                    " def test_two(self): self.fail('fixture should skip this too')\n")
                result = self.run_it()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Ran 0 tests", result.stdout)

    def test_nonpositive_worker_count_is_rejected(self):
        for count in ("0", "-1"):
            with self.subTest(count=count):
                result = self.run_it("-j", count)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
