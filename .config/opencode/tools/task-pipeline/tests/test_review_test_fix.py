"""A reviewer-accepted finding may point at the tests themselves — e.g. a route-table
guard whose registration assertion cannot fire. The fix round that triage opens must be
allowed to change the test files the finding names: that is sanctioned strengthening, not
the "tests weakened" regression the impl gate exists to catch. Correctness stays gated by
test_cmd and the same reviewer's verification session.

Relatedly, the agent harness's own runtime state (.opencode/) is written inside the
workspace during every task run (long-task audit logs), so the changed-files gate must
never read it as task output."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pipeline import snapshot

from harness import Harness, git

CODE = dict(
    deliverables=[{"id": "D1", "kind": "code", "what": "calc gains mul()", "where": "app"}],
    participants=[{"agent": "test-author", "role": "tests", "why": "Writes mul's tests first."},
                  {"agent": "code-author", "role": "author", "why": "Implements mul to pass them."},
                  {"agent": "test-reviewer", "role": "reviewer", "why": "Reviews the finished tests."}],
)

TEST_PY = "import unittest\nfrom calc import mul\n\nclass T(unittest.TestCase):\n" \
          "    def test_mul(self):\n        self.assertEqual(mul(2, 3), 6)\n"

STRONGER_TEST_PY = "import unittest\nfrom calc import mul\n\nclass T(unittest.TestCase):\n" \
                   "    def test_mul(self):\n        self.assertEqual(mul(2, 3), 6)\n" \
                   "    def test_mul_zero(self):\n        self.assertEqual(mul(0, 3), 0)\n"

S1 = "B1/test-reviewer"


class HarnessReviewMixin:
    def review(self, session: str, n: int, verdict: str, findings=()) -> None:
        batch, reviewer = session.split("/")
        d = self.h.wf / "runs" / batch
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{reviewer}-{n}.json").write_text(json.dumps({"batch": batch, "verdict": verdict,
                                                           "findings": list(findings)}))


class ReviewMayStrengthenTestsTest(unittest.TestCase, HarnessReviewMixin):
    """The red/green flow completes; the final review finds a real defect in a test file;
    triage routes it to the task; the fix round edits that test file and must record green."""

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
        # tests step: red
        h.tp("dispatch", "T01")
        (self.app / "test_calc.py").write_text(TEST_PY)
        h.result("T01", "tests", changed=["test_calc.py"])
        h.tp("record", "T01")
        # impl step: green
        h.tp("dispatch", "T01")
        (self.app / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n")
        h.result("T01", "impl", changed=["calc.py"])
        h.tp("record", "T01")   # T01 is needs_check; each test decides accept vs reject

    def tearDown(self) -> None:
        self.h.close()

    def finding(self, fid: str, where: str) -> dict:
        return {"id": fid, "state": "wrong", "blocking": True, "where": where,
                "issue": f"{fid}: the guard at {where} can never fire.",
                "fix": "Detect the handler's own miss instead."}

    def test_a_review_fix_may_strengthen_the_tests(self) -> None:
        h = self.h
        h.tp("accept", "T01", "--note", "ok")
        h.tp("dispatch", S1)
        self.review(S1, 1, "changes", [self.finding("F1", "test_calc.py:1")])
        h.tp("record", S1, "--agent-id", "rev-1")
        h.tp("triage", S1, "--accept-all")
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_fix")
        # The fix round edits the test file the finding names — sanctioned.
        h.tp("dispatch", "T01")
        (self.app / "test_calc.py").write_text(STRONGER_TEST_PY)
        h.result("T01", "fix", changed=["test_calc.py"])
        out = h.tp("record", "T01", "--agent-id", "ca-1").out
        self.assertNotIn("tests changed", out)
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_check")
        h.tp("accept", "T01", "--note", "guard strengthened")
        # The same reviewer verifies the fix, and the suite still passes.
        act = [a for a in h.next()["actions"] if a.get("id") == S1][0]
        self.assertEqual(act["action"], "review")
        h.tp("dispatch", S1)
        self.review(S1, 2, "pass")
        h.tp("record", S1)
        self.assertEqual(h.state()["reviews"][S1]["status"], "done")

    def test_an_impl_step_test_edit_without_a_review_finding_is_still_caught(self) -> None:
        h = self.h
        # A plain manager-rejected fix round carries no review sanction: the frozen
        # tests hash must still hold, so a test edit here stays "tests changed".
        h.tp("reject", "T01", "--reason", "manager fact check: the impl summary is wrong")
        h.tp("dispatch", "T01")
        (self.app / "test_calc.py").write_text(STRONGER_TEST_PY)
        h.result("T01", "fix", changed=["test_calc.py"])
        out = h.tp("record", "T01").out
        self.assertIn("tests changed", out)
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_fix")


class HarnessRuntimeStateTest(unittest.TestCase):
    """The changed-files gate measures what the agent wrote; the agent runtime's own
    state directories (.opencode/) change on their own during every task run."""

    def test_snapshot_ignores_opencode_but_still_sees_real_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n")
            (root / ".opencode" / "ciq-loop").mkdir(parents=True)
            (root / ".opencode" / "ciq-loop" / "audit.log").write_text("{}\n")
            before = snapshot.take(root)
            # The harness logs a long-task event mid-task; the agent writes real code.
            (root / ".opencode" / "ciq-loop" / "audit.log").write_text('{"event":"long-task"}\n')
            (root / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n")
            changed = snapshot.diff(before, snapshot.take(root))
            self.assertEqual(changed, ["src/calc.py"])


if __name__ == "__main__":
    unittest.main()
