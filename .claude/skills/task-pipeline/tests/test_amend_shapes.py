"""Adding work mid-run takes one draft of just that work.

In a real run (KUB-1407) the manager needed four tries and four hand-written JSON edits to add two
fix tasks: it edited plan.json (refused), then wrote only the new tasks to plan-amend.json (read as a
whole plan that dropped every approved task), then hit an overlap with a task already accepted, and
only then passed by ordering the new task after it by hand.
"""
from __future__ import annotations

import json
import unittest

from harness import Harness
from test_approvals import YES_TWO
from test_progress import FINAL_REVIEW


class AmendShapesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = h = Harness()
        h.approved(plan=h.plan([h.task("T01", "a.md"), h.task("T02", "b.md")], final_checks=[]),
                   fix_tasks=YES_TWO, **FINAL_REVIEW)
        for tid, rel in (("T01", "a.md"), ("T02", "b.md")):
            h.author(tid, rel)
            h.tp("accept", tid, "--note", "ok")
        h.tp("dispatch", "B1/doc-reviewer")  # B1's review has started: it keeps exactly its tasks

    def tearDown(self) -> None:
        self.h.close()

    def fix(self) -> dict:
        # Writes T01's file, as KUB-1407's T04 wrote T01's: T01 is accepted, so they never run together.
        return self.h.task("T03", "a.md", brief="Correct the default shown in a.md.", estimate_min=10)

    def plan(self) -> dict:
        return json.loads((self.h.wf / "plan.json").read_text())

    def test_a_draft_of_only_the_new_task_is_enough(self) -> None:
        h = self.h
        (h.wf / "plan-amend.json").write_text(json.dumps({"tasks": [self.fix()]}))
        out = h.tp("plan", "amend").out
        self.assertIn("merged 1 task(s) into the approved plan", out)
        self.assertIn("T03 writes files of T01 (finished): ordered after them", out)
        self.assertIn("new review batch B2: T03", out)
        self.assertIn("amendment ok — added T03", out)
        h.tp("plan", "amend", "--delegated", "--note", "a.md shows the wrong default for the flag.")
        plan = self.plan()
        self.assertEqual([t["id"] for t in plan["tasks"]], ["T01", "T02", "T03"])
        self.assertEqual(plan["tasks"][2]["depends_on"], ["T01"])
        self.assertTrue(plan["title"])
        self.assertEqual(h.state()["tasks"]["T03"]["status"], "pending")
        self.assertEqual(h.state()["reviews"]["B1/doc-reviewer"]["status"], "in_flight")
        self.assertEqual(h.state()["reviews"]["B2/doc-reviewer"]["status"], "pending")

    def test_an_edit_to_plan_json_becomes_the_draft(self) -> None:
        h = self.h
        approved = (h.wf / "plan.json").read_bytes()
        edited = self.plan()
        edited["tasks"].append(self.fix())
        (h.wf / "plan.json").write_text(json.dumps(edited, indent=2))
        self.assertIn("`tp plan amend` makes your edit the draft", h.tp("next", expect=2).text)
        out = h.tp("plan", "amend").out
        self.assertIn("your edit of plan.json is now the draft plan-amend.json", out)
        self.assertIn("amendment ok — added T03", out)
        self.assertEqual((h.wf / "plan.json").read_bytes(), approved)
        h.tp("next")  # every other command works again

    def test_without_a_kept_copy_an_edited_plan_is_still_refused(self) -> None:
        # A run approved before tp kept the approved plan: nothing to restore from.
        h = self.h
        (h.wf / ".tp" / "plan-approved.json").unlink()
        edited = self.plan()
        edited["tasks"].append(self.fix())
        (h.wf / "plan.json").write_text(json.dumps(edited, indent=2))
        self.assertIn("restore it", h.tp("plan", "amend", expect=2).text)

    def test_a_refused_merge_still_says_what_it_merged(self) -> None:
        h = self.h
        bad = self.fix()
        bad["requirements"] = ["R99"]
        (h.wf / "plan-amend.json").write_text(json.dumps({"tasks": [bad]}))
        err = h.tp("plan", "amend", expect=2).text
        self.assertIn("merged 1 task(s)", err)
        self.assertIn("R99", err)
        self.assertNotIn("served by no task", err)  # the approved tasks still serve every requirement


if __name__ == "__main__":
    unittest.main()
