"""Plan validation: only approved agents, small tasks, a plan that fits the time budget,
and a plan that freezes once the human approves it."""
from __future__ import annotations

import unittest

from harness import Harness


class PlanCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.confirmed()

    def tearDown(self) -> None:
        self.h.close()

    def check(self, plan, expect: int = 0):
        self.h.write_json("plan.json", plan)
        return self.h.tp("plan", "check", expect=expect)

    def test_valid_plan_renders_plan_md(self) -> None:
        self.check(self.h.plan())
        md = (self.h.wf / "plan.md").read_text()
        for tid in ("T01", "T02", "T03"):
            self.assertIn(tid, md)
        self.assertIn("kb-author", md)

    def test_agent_not_confirmed_in_scope_is_refused(self) -> None:
        plan = self.h.plan([self.h.task("T01", "a.md", agent="doc-author")])
        self.assertIn("doc-author", self.check(plan, expect=2).text)

    def test_dependency_cycle_is_refused(self) -> None:
        plan = self.h.plan([self.h.task("T01", "a.md", depends_on=["T02"]),
                            self.h.task("T02", "b.md", depends_on=["T01"])])
        self.assertIn("cycle", self.check(plan, expect=2).text)

    def test_unknown_dependency_and_deliverable_are_refused(self) -> None:
        plan = self.h.plan([self.h.task("T01", "a.md", depends_on=["T09"], serves=["D7"])])
        text = self.check(plan, expect=2).text
        self.assertIn("T09", text)
        self.assertIn("D7", text)

    def test_oversized_task_is_refused(self) -> None:
        plan = self.h.plan([self.h.task("T01", "a.md", estimate_min=45)])
        self.assertIn("estimate_min", self.check(plan, expect=2).text)

    def test_long_brief_and_many_criteria_are_refused(self) -> None:
        plan = self.h.plan([self.h.task("T01", "a.md", brief="word " * 200,
                                        acceptance=[f"criterion {i}" for i in range(9)])])
        text = self.check(plan, expect=2).text
        self.assertIn("brief", text)
        self.assertIn("acceptance", text)

    def test_the_43_task_stratum_plan_is_refused(self) -> None:
        # Regression: a 43-task plan for a KB the user expected in about 3 hours.
        tasks = [self.h.task(f"T{i:02d}", f"area{i}/article.md") for i in range(1, 44)]
        text = self.check(self.h.plan(tasks), expect=2).text
        self.assertIn("tasks", text)
        self.assertIn("budget", text)

    def test_plan_that_cannot_finish_in_the_budget_is_refused(self) -> None:
        # 20 tasks x 20 min over 2 lanes = 200 min > the 180-min budget.
        tasks = [self.h.task(f"T{i:02d}", f"a{i}.md", estimate_min=20) for i in range(1, 21)]
        text = self.check(self.h.plan(tasks), expect=2).text
        self.assertIn("budget", text)
        self.assertIn("200", text)

    def test_a_long_dependency_chain_counts_against_the_budget(self) -> None:
        tasks = [self.h.task(f"T{i:02d}", f"a{i}.md", estimate_min=25,
                             depends_on=[f"T{i - 1:02d}"] if i > 1 else []) for i in range(1, 9)]
        self.assertIn("critical path", self.check(self.h.plan(tasks), expect=2).text)

    def test_overlapping_paths_need_an_ordering(self) -> None:
        plan = self.h.plan([self.h.task("T01", "arch/**"), self.h.task("T02", "arch/overview.md")])
        self.assertIn("overlap", self.check(plan, expect=2).text)
        plan = self.h.plan([self.h.task("T01", "arch/**"),
                            self.h.task("T02", "arch/overview.md", depends_on=["T01"])])
        self.check(plan)

    def test_paths_must_stay_inside_a_write_workspace(self) -> None:
        text = self.check(self.h.plan([self.h.task("T01", "../escape.md")]), expect=2).text
        self.assertIn("../escape.md", text)
        text = self.check(self.h.plan([self.h.task("T01", "calc/new.go", workspace="src")]), expect=2).text
        self.assertIn("read", text)

    def test_every_deliverable_is_served(self) -> None:
        h = Harness()
        try:
            h.confirmed(deliverables=[{"id": "D1", "kind": "kb", "what": "KB", "where": "kb"},
                                      {"id": "D2", "kind": "kb", "what": "Glossary", "where": "kb"}])
            h.write_json("plan.json", h.plan([h.task("T01", "a.md")]))
            self.assertIn("D2", h.tp("plan", "check", expect=2).text)
        finally:
            h.close()

    def test_unknown_check_name_is_refused(self) -> None:
        plan = self.h.plan([self.h.task("T01", "a.md", checks=["lint"])])
        self.assertIn("lint", self.check(plan, expect=2).text)


class ApprovalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.confirmed()
        self.h.write_json("plan.json", self.h.plan())

    def tearDown(self) -> None:
        self.h.close()

    def test_approve_needs_a_submitted_plan(self) -> None:
        self.h.tp("approve", "--answer", "approve", expect=2)

    def test_plan_edited_after_submit_cannot_be_approved(self) -> None:
        self.h.tp("plan", "submit")
        self.h.write_json("plan.json", self.h.plan([self.h.task("T01", "a.md")]))
        self.assertIn("changed", self.h.tp("approve", "--answer", "approve", expect=2).text)

    def test_approve_starts_execution_and_freezes_the_plan(self) -> None:
        self.h.tp("plan", "submit")
        self.assertEqual(self.h.state()["phase"], "AWAITING_APPROVAL")
        self.h.tp("approve", "--answer", "approve")
        self.assertEqual(self.h.state()["phase"], "EXECUTING")
        self.assertIn("approve", (self.h.wf / "decisions.md").read_text())
        self.h.write_json("plan.json", self.h.plan([self.h.task("T01", "a.md")]))
        self.assertIn("changed after approval", self.h.tp("next", expect=2).text)

    def test_revise_returns_to_planning(self) -> None:
        self.h.tp("plan", "submit")
        self.h.tp("revise", "--feedback", "Split T01 in two.")
        self.assertEqual(self.h.state()["phase"], "PLANNING")
        self.assertIn("Split T01 in two.", (self.h.wf / "decisions.md").read_text())

    def test_submit_lists_noticed_items_for_the_human(self) -> None:
        self.h.tp("note", "The README's build section is stale.")
        out = self.h.tp("plan", "submit").out
        self.assertIn("README's build section is stale", out)


if __name__ == "__main__":
    unittest.main()
