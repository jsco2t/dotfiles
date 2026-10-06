"""A task can block at impl because the seeded test files cannot compile (seen live on
KUB-443: contract.Identity carries a slice, so the seeded == comparisons never built).
The manager's resolve answer may authorize editing those test files — they are the task's
own tests_paths deliverable. But the impl gate compares the test files against the hash
frozen at the red tests step, so the sanctioned edits were flagged "tests changed" and
burned fix rounds; the manager had to patch .tp/state.json by hand.

`tp resolve --task T --action answer|retry --rebaseline-tests` is the sanctioned path:
the human decision is recorded verbatim, the frozen tests hash is released, and the
sanctioned edits are not read as weakening. Correctness stays gated by test_cmd; a
resolve WITHOUT the flag keeps the frozen hash and still catches a plain test edit.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from harness import Harness, git

CODE = dict(
    deliverables=[{"id": "D1", "kind": "code", "what": "calc gains mul()", "where": "app"}],
    participants=[{"agent": "test-author", "role": "tests", "why": "Writes mul's tests first."},
                  {"agent": "code-author", "role": "author", "why": "Implements mul to pass them."},
                  {"agent": "test-reviewer", "role": "reviewer", "why": "Reviews the finished tests."}],
)

# What a test author seeds before the production code exists: broken on purpose for the
# red gate, but here broken in a way no implementation can fix — the comparisons cannot
# compile. The impl fence cannot repair the file; the manager's resolve must.
SEEDED_TEST_PY = "import unittest\nfrom calc import mul\n\nclass T(unittest.TestCase):\n" \
                 "    def test_mul(self):\n        self.assertEqual(mul(2, 3) 6)\n"

FIXED_TEST_PY = "import unittest\nfrom calc import mul\n\nclass T(unittest.TestCase):\n" \
                "    def test_mul(self):\n        self.assertEqual(mul(2, 3), 6)\n"

MUL_GO = "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"


class ResolveRebaselineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = h = Harness()
        self.app = h.root / "app"
        self.app.mkdir()
        (self.app / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        git(self.app, "init", "-q", "-b", "main")
        git(self.app, "add", "-A")
        git(self.app, "commit", "-q", "-m", "init")
        scope = dict(CODE, review="final", workspaces=[{"name": "app", "path": str(self.app), "mode": "write"}])
        task = {"id": "T01", "title": "mul", "serves": ["D1"], "agent": "code-author", "workspace": "app",
                "paths": ["calc.py", "test_calc.py"], "sources": ["app:calc.py"],
                "brief": "Add mul(a, b) beside add.", "acceptance": ["mul(2, 3) == 6"],
                "test_cmd": "python3 -m unittest -q test_calc", "tests_paths": ["test_calc.py"],
                "checks": [], "estimate_min": 10, "depends_on": []}
        plan = h.plan([task], final_checks=[])
        h.approved(plan=plan, **scope)
        # tests step: the seeded tests are red (they do not even compile).
        h.tp("dispatch", "T01")
        (self.app / "test_calc.py").write_text(SEEDED_TEST_PY)
        h.result("T01", "tests", changed=["test_calc.py"])
        h.tp("record", "T01")
        self.assertIsNotNone(h.state()["tasks"]["T01"]["tests_hash"])

    def tearDown(self) -> None:
        self.h.close()

    def block_impl_on_uncompilable_tests(self) -> None:
        """The impl agent hits the broken seeded tests, cannot edit them, and blocks."""
        h = self.h
        h.tp("dispatch", "T01")
        h.result("T01", "impl", status="blocked",
                 summary="The seeded test file does not compile; the fix is outside my write fence.",
                 questions=["test_calc.py:1 has a syntax error; may the impl step repair it?"])
        h.tp("record", "T01")
        st = h.state()["tasks"]["T01"]
        self.assertEqual(st["status"], "blocked")
        self.assertEqual(st["blocked"]["kind"], "input")
        self.assertIsNotNone(st["tests_hash"])

    def finish_impl_editing_the_tests(self, step: str = "impl") -> str:
        """The impl agent repairs the seeded test and delivers the feature."""
        h = self.h
        (self.app / "test_calc.py").write_text(FIXED_TEST_PY)
        (self.app / "calc.py").write_text(MUL_GO)
        h.result("T01", step, changed=["calc.py", "test_calc.py"])
        return h.tp("record", "T01").out

    def test_a_resolve_answer_that_sanctions_test_edits_rebaselines_the_hash(self) -> None:
        h = self.h
        self.block_impl_on_uncompilable_tests()
        out = h.tp("resolve", "--task", "T01", "--action", "answer", "--rebaseline-tests",
                   "--answer", "The seeded tests are T01's own deliverable; repair the compile error.").out
        self.assertIn("baseline", out)
        self.assertIsNone(h.state()["tasks"]["T01"].get("tests_hash"))
        out = self.finish_impl_editing_the_tests()
        self.assertNotIn("tests changed", out)
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_check")

    def test_resolve_without_the_flag_still_catches_the_test_edit(self) -> None:
        h = self.h
        self.block_impl_on_uncompilable_tests()
        h.tp("resolve", "--task", "T01", "--action", "answer",
             "--answer", "The seeded tests are T01's own deliverable; repair the compile error.")
        self.assertIsNotNone(h.state()["tasks"]["T01"]["tests_hash"])
        out = self.finish_impl_editing_the_tests()
        self.assertIn("tests changed", out)
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_fix")

    def test_the_flag_is_refused_where_no_authorization_is_meaningful(self) -> None:
        h = self.h
        self.block_impl_on_uncompilable_tests()
        h.tp("resolve", "--task", "T01", "--action", "skip", "--rebaseline-tests",
             "--answer", "skip it", expect=2)
        # And at workflow level there is no task to re-baseline.
        h.tp("resolve", "--exception", "--action", "answer", "--rebaseline-tests",
             "--answer", "x", expect=2)

    def test_a_rounds_retry_can_release_the_baseline_for_recovery(self) -> None:
        """Recovery path for a run already stuck in needs_fix: burn the fix rounds on the
        frozen baseline, then retry with the flag."""
        h = self.h
        self.block_impl_on_uncompilable_tests()
        h.tp("resolve", "--task", "T01", "--action", "answer",
             "--answer", "repair the seeded tests")
        self.assertIn("tests changed", self.finish_impl_editing_the_tests())
        # Rounds exhausted -> blocked on rounds; the retry carries the sanction.
        for rnd in (1, 2):
            h.tp("dispatch", "T01")
            self.assertIn("tests changed", self.finish_impl_editing_the_tests(step="fix"))
        st = h.state()["tasks"]["T01"]
        self.assertEqual(st["status"], "blocked")
        self.assertEqual(st["blocked"]["kind"], "rounds")
        h.tp("resolve", "--task", "T01", "--action", "retry", "--rebaseline-tests",
             "--answer", "The edits were sanctioned all along.")
        self.assertIsNone(h.state()["tasks"]["T01"].get("tests_hash"))
        h.tp("dispatch", "T01")
        (self.app / "calc.py").write_text(MUL_GO)
        h.result("T01", "fix", changed=["calc.py"])
        out = h.tp("record", "T01").out
        self.assertNotIn("tests changed", out)
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_check")


if __name__ == "__main__":
    unittest.main()
