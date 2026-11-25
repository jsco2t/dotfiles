"""`/reviewomatic` over the whole change, once, after every code change (KUB-1332).

The batch reviews passed; a /reviewomatic pass the human ran afterwards found about eight real
defects. The pipeline now runs it itself, with fresh eyes (told nothing of the plan), after the
batch reviews and the closeout, and fixes every finding at 80% confidence or more. Its fixes get
one verification scoped to its findings, never a second whole review."""
from __future__ import annotations

import unittest

from scenarios import Mixed

WHOLE = "W/code-reviewer"
SUB_TEST = ("import unittest\nfrom sub import sub\n\n\nclass S(unittest.TestCase):\n"
            "    def test_sub(self):\n        self.assertEqual(sub(5, 3), 2)\n")


class WholeChangeReviewTest(unittest.TestCase):

    def setUp(self) -> None:
        self.m = m = Mixed()
        sub = m.code_task("T02", title="sub", paths=["sub.py", "test_sub.py"], brief="Add sub(a, b).",
                          acceptance=["sub(5, 3) == 2"], test_cmd="python3 -m unittest -q test_sub",
                          tests_paths=["test_sub.py"])
        m.approve([m.code_task("T01"), sub],
                  m.scope(["code"], ["tests", "code", "correctness", "security", "test-review"]),
                  review_batches=[{"id": "B1", "tasks": ["T01"]}, {"id": "B2", "tasks": ["T02"]}])

    def tearDown(self) -> None:
        self.m.close()

    def sub_done(self) -> None:
        h = self.m.h
        h.tp("dispatch", "T02")
        (self.m.app / "test_sub.py").write_text(SUB_TEST)
        h.result("T02", "tests", changed=["test_sub.py"], noticed=["calc.py has no module docstring."])
        h.tp("record", "T02", "--agent-id", "ta-2")
        h.tp("dispatch", "T02")
        (self.m.app / "sub.py").write_text("def sub(a, b):\n    return a - b\n")
        h.result("T02", "impl", changed=["sub.py"])
        h.tp("record", "T02", "--agent-id", "ca-2")
        h.tp("accept", "T02", "--note", "red then green")

    def batches_pass(self, tasks: bool = True) -> None:
        m = self.m
        if tasks:
            m.code_done("T01")
            self.sub_done()
        for sid in [s for s in m.h.state()["reviews"] if not s.startswith("W/")]:
            m.h.tp("dispatch", sid)
            m.review_file(sid, 1, "pass")
            m.h.tp("record", sid)

    def kinds(self):
        return [(a["action"], a.get("id")) for a in self.m.actions()]

    def classify(self) -> None:
        self.m.h.tp("closeout", "--items", "1", "--class", "observation", "--note", "cosmetic")

    def test_one_reviewomatic_session_covers_the_whole_change(self) -> None:
        reviews = self.m.h.state()["reviews"]
        self.assertEqual(reviews[WHOLE]["tasks"], ["T01", "T02"])
        self.assertEqual([s for s in reviews if s.startswith("W/")], [WHOLE])  # once: whole reviews are expensive

    def test_it_waits_for_the_batch_reviews_and_the_closeout(self) -> None:
        m = self.m
        m.code_done("T01")
        self.sub_done()
        self.assertNotIn(("review", WHOLE), self.kinds())
        self.batches_pass(tasks=False)
        self.assertIn(("closeout", None), self.kinds())
        self.assertNotIn(("review", WHOLE), self.kinds())
        self.assertIn("closeout", m.h.tp("dispatch", WHOLE, expect=2).text)
        self.classify()
        self.assertEqual([k for k in self.kinds() if k[0] != "wait"], [("review", WHOLE)])

    def test_it_runs_once_and_then_the_run_finishes(self) -> None:
        m = self.m
        self.batches_pass()
        self.classify()
        m.h.tp("dispatch", WHOLE)
        out = m.h.tp("next").out
        brief = (m.h.wf / "runs" / "W" / "brief-code-reviewer-1.md").read_text()
        self.assertIn("Skill: reviewomatic", brief)
        self.assertIn("local --confidence=80", brief)
        self.assertIn("fresh eyes", brief)
        self.assertNotIn("--max-agents=0", brief)      # it batches across its own sub-agents
        self.assertIn("calc.py", brief)
        self.assertIn("sub.py", brief)
        self.assertNotIn("Add sub(a, b)", brief)       # fresh eyes: nothing of the plan or the tasks
        self.assertNotIn("sub(5, 3) == 2", brief)
        self.assertNotIn("red then green", brief)
        self.assertTrue(out)
        m.review_file(WHOLE, 1, "pass")
        m.h.tp("record", WHOLE)
        self.assertEqual([k[0] for k in self.kinds()], ["final"])

    def test_its_fixes_get_one_scoped_verification_never_a_second_whole_review(self) -> None:
        m = self.m
        self.batches_pass()
        self.classify()
        m.h.tp("dispatch", WHOLE)
        m.review_file(WHOLE, 1, "changes", [m.finding("F1", "sub.py:2", state="unclear")])
        m.h.tp("record", WHOLE)
        m.h.tp("triage", WHOLE, "--accept-all")
        m.h.tp("dispatch", "T02")
        (m.app / "sub.py").write_text("def sub(a, b):\n    \"\"\"a minus b.\"\"\"\n    return a - b\n")
        m.h.result("T02", "fix", changed=["sub.py"])
        m.h.tp("record", "T02", "--agent-id", "ca-2")
        m.h.tp("accept", "T02", "--note", "docstring added")
        self.assertIn(("review", WHOLE), self.kinds())
        m.h.tp("dispatch", WHOLE)
        self.assertIn("Verify the fixes", (m.h.wf / "runs" / "W" / "brief-code-reviewer-2.md").read_text())
        m.review_file(WHOLE, 2, "changes", [m.finding("F1", "sub.py:2", state="unclear")])
        out = m.h.tp("record", WHOLE).out
        self.assertIn("BLOCKED", out)  # the human decides; no third round of the whole review
        self.assertEqual(m.h.state()["reviews"][WHOLE]["status"], "blocked")


class CodeReviewerRunsOnceTest(unittest.TestCase):
    """A scope that lists code-reviewer (a live run's scoper added it as "the closeout /reviewomatic
    pass") gets it once, over the whole change, not once per batch as well: four batch sessions of
    the same /reviewomatic cost that run 29 minutes before the whole-change pass ran it again."""

    def test_code_reviewer_reviews_the_whole_change_only(self) -> None:
        m = Mixed()
        try:
            scope = m.scope(["code"], ["tests", "code", "correctness", "security"])
            scope["participants"].append({"agent": "code-reviewer", "role": "reviewer",
                                          "why": "Closeout /reviewomatic pass over the whole change."})
            sub = m.code_task("T02", title="sub", paths=["sub.py", "test_sub.py"], tests_paths=["test_sub.py"],
                              test_cmd="python3 -m unittest -q test_sub")
            m.approve([m.code_task("T01"), sub], scope,
                      review_batches=[{"id": "B1", "tasks": ["T01"]}, {"id": "B2", "tasks": ["T02"]}])
            reviews = m.h.state()["reviews"]
            self.assertEqual(sorted(reviews), ["B1/lens-reviewer", "B2/lens-reviewer", WHOLE])
            self.assertIn("W/code-reviewer", (m.h.wf / "plan.md").read_text())
        finally:
            m.close()


class OnlyCodeReviewerTest(unittest.TestCase):
    """code-reviewer as the only reviewer: no batch sessions, and the whole-change pass still runs."""

    def test_the_whole_change_pass_runs_with_no_batch_sessions(self) -> None:
        m = Mixed()
        try:
            scope = m.scope(["code"], ["tests", "code"])
            scope["participants"].append({"agent": "code-reviewer", "role": "reviewer",
                                          "why": "Closeout /reviewomatic pass over the whole change."})
            m.approve([m.code_task("T01")], scope)
            self.assertEqual(list(m.h.state()["reviews"]), [WHOLE])
            m.code_done("T01")
            kinds = [(a["action"], a.get("id")) for a in m.actions()]
            if ("closeout", None) in kinds:
                m.h.tp("closeout", "--items", "1", "--class", "observation", "--note", "cosmetic")
                kinds = [(a["action"], a.get("id")) for a in m.actions()]
            self.assertIn(("review", WHOLE), kinds)
            m.h.tp("dispatch", WHOLE)
            m.review_file(WHOLE, 1, "pass")
            m.h.tp("record", WHOLE)
            self.assertEqual([a["action"] for a in m.actions()], ["final"])
        finally:
            m.close()


class NoWholeReviewTest(unittest.TestCase):

    def test_a_run_the_human_chose_no_review_for_gets_none(self) -> None:
        m = Mixed()
        try:
            m.approve([m.doc_task("T01")], m.scope(["docs"], ["docs"], review="none"))
            self.assertFalse([s for s in m.h.state().get("reviews", {}) if s.startswith("W/")])
        finally:
            m.close()


if __name__ == "__main__":
    unittest.main()
