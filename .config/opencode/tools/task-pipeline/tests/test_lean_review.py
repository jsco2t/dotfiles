"""The end-of-pipeline review applies the reviewomatic lessons: the single-lens code reviewers pack
into one lean session, each reviewer sees only the work of its kind, code review starts as soon as
the code is accepted, the diff and one shared test run are files every reviewer reads instead of
re-running, and reports carry near misses as one line each."""
from __future__ import annotations

import json
import time
import unittest

from scenarios import Mixed

LENSES = "B1/lens-reviewer"


class PackedSessionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.m = m = Mixed()
        m.approve([m.code_task("T01"), m.doc_task("T02", depends_on=["T01"])],
                  m.scope(["code", "docs"], ["tests", "code", "docs", "correctness", "security",
                                             "test-review", "doc-review"]))

    def tearDown(self) -> None:
        self.m.close()

    def test_single_lens_code_reviewers_share_one_session_per_batch(self) -> None:
        # Every reviewer still sees every batch: in a real run, the doc reviewer caught wrong code
        # comments and the code lenses caught false claims in the docs. The default batches split
        # code from documents, so code review can start before the documents are written.
        reviews = self.m.h.state()["reviews"]
        units = [LENSES.split("/")[1], "doc-reviewer", "test-reviewer"]
        self.assertEqual(sorted(reviews), sorted(f"{b}/{u}" for b in ("B1", "B2") for u in units))
        self.assertEqual(reviews[LENSES]["lenses"], ["correctness-reviewer", "security-reviewer"])
        self.assertEqual(reviews[LENSES]["tasks"], ["T01"])
        self.assertEqual(reviews["B1/doc-reviewer"]["tasks"], ["T01"])
        self.assertEqual(reviews["B2/lens-reviewer"]["tasks"], ["T02"])

    def test_the_lens_session_runs_as_one_lean_agent_with_each_lens_in_full(self) -> None:
        m = self.m
        m.code_done("T01")
        out = m.h.tp("dispatch", LENSES).out
        self.assertIn('subagent_type="lens-reviewer"', out)
        brief = (m.h.wf / "runs" / "B1" / "brief-lens-reviewer-1.md").read_text()
        self.assertIn("correctness-reviewer", brief)
        self.assertIn("security-reviewer", brief)
        self.assertIn("own full pass", brief)
        self.assertIn("untrusted input", brief.lower())                  # security's definition, inlined
        self.assertNotIn("docs/calc.md", brief.split("## Hand back")[0])  # the docs task is in batch B2

    def test_code_review_starts_once_the_code_is_accepted(self) -> None:
        m = self.m
        m.code_done("T01")
        acts = m.actions()
        ready = [a["id"] for a in acts if a["action"] == "review"]
        self.assertIn(LENSES, ready)                                       # T02 is not written yet
        self.assertTrue(all(sid.startswith("B1/") for sid in ready))
        self.assertIn("T02", [a.get("id") for a in acts if a["action"] == "dispatch"])  # shares the three slots
        m.h.tp("dispatch", LENSES, "B1/test-reviewer", "B1/doc-reviewer")

    def test_docs_review_waits_for_the_code_reviews_to_finish(self) -> None:
        m = self.m
        m.code_done("T01")
        m.doc_done("T02")
        ready = [a["id"] for a in m.actions() if a["action"] == "review"]
        self.assertFalse([sid for sid in ready if sid.startswith("B2/")])
        for sid in (LENSES, "B1/test-reviewer", "B1/doc-reviewer"):
            m.h.tp("dispatch", sid)
            m.review_file(sid, 1, "pass")
            m.h.tp("record", sid)
        ready = [a["id"] for a in m.actions() if a["action"] == "review"]
        self.assertEqual(sorted(ready), ["B2/doc-reviewer", "B2/lens-reviewer", "B2/test-reviewer"])

    def test_the_diff_and_the_tasks_test_logs_are_files_reviewers_read(self) -> None:
        m = self.m
        m.code_done("T01")
        before = sorted(p.name for p in m.app.iterdir())
        m.h.tp("dispatch", LENSES)
        brief = (m.h.wf / "runs" / "B1" / "brief-lens-reviewer-1.md").read_text()
        diff = m.h.wf / "runs" / "B1" / "lens-reviewer-change.diff"
        self.assertIn(str(diff), brief)
        self.assertIn("def mul", diff.read_text())
        self.assertIn("test_calc.py", diff.read_text())                # untracked files are in it too
        self.assertIn(str(m.h.run_dir("T01") / "tests-impl-0.log"), brief)
        self.assertIn("re-run", brief)
        # Nothing runs in the workspace on the reviewers' behalf: a background suite there would
        # leave build output that the snapshots blame on whichever agent is in flight.
        time.sleep(0.5)
        self.assertEqual(sorted(p.name for p in m.app.iterdir()), before)
        self.assertFalse((m.h.wf / "runs" / "B1" / "baseline.txt").exists())

    def test_near_misses_are_one_line_each_and_never_routed(self) -> None:
        m = self.m
        m.code_done("T01")
        m.h.tp("dispatch", LENSES)
        brief = (m.h.wf / "runs" / "B1" / "brief-lens-reviewer-1.md").read_text()
        self.assertIn("near_misses", brief)
        m.review_file(LENSES, 1, "pass", near_misses=["calc.py:6 · 65 · mul ignores overflow (Python has none)."])
        m.h.tp("record", LENSES)
        self.assertEqual(m.h.state()["reviews"][LENSES]["status"], "done")
        self.assertEqual(m.status("T01"), "accepted")

    def test_findings_from_the_lens_session_route_to_the_owning_task(self) -> None:
        m = self.m
        m.code_done("T01")
        m.h.tp("dispatch", LENSES)
        m.review_file(LENSES, 1, "changes", [m.finding("F1", "calc.py:6", state="unclear")])
        out = m.h.tp("record", LENSES, "--agent-id", "lens-1").out
        self.assertIn("F1 → T01", out)


class OneCodeLensIsNotPackedTest(unittest.TestCase):
    def test_a_single_selected_lens_runs_as_itself(self) -> None:
        m = Mixed()
        try:
            m.approve([m.code_task("T01")], m.scope(["code"], ["tests", "code", "correctness"]))
            self.assertEqual(list(m.h.state()["reviews"]), ["B1/correctness-reviewer"])
        finally:
            m.close()


class WorkingRulesTest(unittest.TestCase):
    def test_every_brief_carries_the_batching_and_no_rerun_rules(self) -> None:
        m = Mixed()
        try:
            m.approve([m.code_task("T01")], m.scope(["code"], ["tests", "code", "correctness"]))
            m.h.tp("dispatch", "T01")
            brief = (m.h.run_dir("T01") / "brief-tests-0.md").read_text()
            self.assertIn("one message", brief)
            self.assertIn("Read each region once", brief)
        finally:
            m.close()


if __name__ == "__main__":
    unittest.main()
