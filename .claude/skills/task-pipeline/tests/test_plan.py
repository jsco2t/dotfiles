"""Plan validation: only approved agents, small tasks, a plan that fits the time budget,
and a plan that freezes once the human approves it."""
from __future__ import annotations

import json
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
        # 30 tasks x 20 min over 3 lanes = 200 min > the 180-min budget.
        tasks = [self.h.task(f"T{i:02d}", f"a{i}.md", estimate_min=20) for i in range(1, 31)]
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

    def test_unknown_research_source_is_refused(self) -> None:
        plan = self.h.plan([self.h.task("T01", "a.md", sources=["research:R9"])])
        self.assertIn("R9", self.check(plan, expect=2).text)

    def test_workflow_files_can_be_sources_and_shared_conventions(self) -> None:
        # Seen live: conventions.md could only be named by absolute path inside each 150-word brief.
        (self.h.wf / "conventions.md").write_text("# Conventions\n")
        plan = self.h.plan([self.h.task("T01", "a.md", sources=["src:calc/**", "wf:conventions.md"])],
                           conventions=["wf:conventions.md"], final_checks=[])
        self.check(plan)
        self.assertIn("conventions.md", (self.h.wf / "plan.md").read_text())
        bad = self.h.plan([self.h.task("T01", "a.md", sources=["wf:nope.md"])], conventions=["wf:../x.md", "x.md"])
        res = self.check(bad, expect=2)
        for needle in ("wf:nope.md", "wf:../x.md", "'x.md'"):
            self.assertIn(needle, res.text)

    def test_a_report_like_deliverable_name_is_warned_about_not_refused(self) -> None:
        # Seen live: Claude Code refused a sub-agent's Write of a new report.md ("Subagents should
        # return findings as text, not write report files"); the run waited three hours on it.
        out = self.check(self.h.plan([self.h.task("T01", "review/report.md")], final_checks=[])).out
        self.assertIn("WARN: T01 writes report.md", out)
        self.assertIn("plan ok", out)
        self.assertNotIn("WARN", self.check(self.h.plan()).out)

    def test_wf_is_not_a_workspace_name(self) -> None:
        h = Harness()
        try:
            h.init()
            h.write_json("scope.json", h.scope(workspaces=[{"name": "wf", "path": str(h.kb), "mode": "write"}]))
            self.assertIn("'wf'", h.tp("scope", "check", expect=2).text)
        finally:
            h.close()

    def test_unknown_check_name_is_refused(self) -> None:
        plan = self.h.plan([self.h.task("T01", "a.md", checks=["lint"])])
        self.assertIn("lint", self.check(plan, expect=2).text)


FINAL_REVIEW = dict(review="final", participants=[
    {"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."},
    {"agent": "doc-reviewer", "role": "reviewer", "why": "Reviews the finished KB for accuracy."}])


class ReviewPlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def check(self, plan, expect: int = 0, **scope):
        self.h.confirmed(**scope)
        self.h.write_json("plan.json", plan)
        return self.h.tp("plan", "check", expect=expect)

    def test_the_review_tail_counts_against_the_budget(self) -> None:
        tasks = [self.h.task(f"T0{i}", f"a{i}.md") for i in range(1, 4)]
        self.check(self.h.plan(tasks), budget_minutes=30)                      # 15 min of work: fits
        h2 = Harness()
        try:
            h2.confirmed(budget_minutes=30, **FINAL_REVIEW)
            h2.write_json("plan.json", h2.plan([h2.task(f"T0{i}", f"a{i}.md") for i in range(1, 4)]))
            text = h2.tp("plan", "check", expect=2).text                      # + 28 min review tail: over
            self.assertIn("review", text)
            self.assertIn("budget", text)
        finally:
            h2.close()

    def test_large_packages_are_split_into_review_batches(self) -> None:
        tasks = [self.h.task(f"T{i:02d}", f"a{i}.md", estimate_min=5) for i in range(1, 13)]
        self.assertIn("review_batches", self.check(self.h.plan(tasks), expect=2, **FINAL_REVIEW).text)

    def test_a_review_session_is_sized_by_what_it_reviews(self) -> None:
        # Measured live: one ~75-line document took a doc reviewer about 10 minutes, so four
        # articles in one session exceed the 30-minute cap.
        tasks = [self.h.task(f"T0{i}", f"a{i}.md", estimate_min=5) for i in range(1, 5)]
        text = self.check(self.h.plan(tasks), expect=2, **FINAL_REVIEW).text
        self.assertIn("40 min of review", text)
        self.assertIn("review_batches", text)

    def test_a_small_code_batch_fits_one_session(self) -> None:
        h = Harness()
        try:
            app = h.root / "app"
            app.mkdir()
            h.confirmed(review="final", deliverables=[{"id": "D1", "kind": "code", "what": "four small fixes"}],
                        workspaces=[{"name": "app", "path": str(app), "mode": "write"}],
                        participants=[{"agent": "code-author", "role": "author", "why": "Implements the D1 fixes."},
                                      {"agent": "correctness-reviewer", "role": "reviewer", "why": "Checks D1 edge cases."}])
            tasks = [h.task(f"T0{i}", f"f{i}.py", agent="code-author", workspace="app", checks=[], sources=["app:."],
                            test_cmd="true", tests_paths=[f"f{i}.py"], estimate_min=5) for i in range(1, 5)]
            h.write_json("plan.json", h.plan(tasks, final_checks=[]))
            h.tp("plan", "check")
        finally:
            h.close()

    def test_every_task_is_in_exactly_one_batch(self) -> None:
        tasks = [self.h.task(f"T0{i}", f"a{i}.md") for i in range(1, 4)]
        bad = self.h.plan(tasks, review_batches=[{"id": "B1", "tasks": ["T01", "T02"]},
                                                 {"id": "B2", "tasks": ["T02"]}])
        text = self.check(bad, expect=2, **FINAL_REVIEW).text
        self.assertIn("T02", text)
        self.assertIn("T03", text)

    def test_plan_md_shows_the_review_sessions_approval_covers(self) -> None:
        tasks = [self.h.task(f"T0{i}", f"a{i}.md") for i in range(1, 5)]
        plan = self.h.plan(tasks, review_batches=[{"id": "B1", "tasks": ["T01", "T02"]},
                                                  {"id": "B2", "tasks": ["T03", "T04"]}])
        self.check(plan, **FINAL_REVIEW)
        md = (self.h.wf / "plan.md").read_text()
        self.assertIn("2 batches × 1 reviewer = 2 review sessions", md)
        self.assertIn("after every task is accepted", md)


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


class AmendTest(unittest.TestCase):
    """`tp plan amend`: mid-run plan changes the human approves, limited to work not yet started."""

    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def draft(self):
        self.h.tp("plan", "amend")                        # starts the draft as a copy of the approved plan
        return json.loads((self.h.wf / "plan-amend.json").read_text())

    def test_amend_adds_tasks_and_changes_unstarted_ones_mid_run(self) -> None:
        # Seen live: a task sized for 12 notes met 39 findings, and nothing could add or split a
        # task once execution started.
        h = self.h
        h.approved()
        h.author("T01", "architecture/overview.md")          # T01 has started: frozen
        draft = self.draft()
        draft["tasks"].insert(2, h.task("T04", "faq.md", brief="Write the FAQ."))
        draft["tasks"][3]["brief"] = "Write kb/index.md linking every article, the FAQ included."
        draft["tasks"][3]["depends_on"] = ["T01", "T02", "T04"]
        (h.wf / "plan-amend.json").write_text(json.dumps(draft))
        out = h.tp("plan", "amend").out
        for needle in ("added T04", "changed T03", "--answer", "remaining work"):
            self.assertIn(needle, out)
        self.assertNotIn("T04", (h.wf / "plan.json").read_text())   # nothing applies without the human
        h.tp("next")                                                # ...and the run carries on meanwhile
        h.tp("plan", "amend", "--answer", "Yes, add the FAQ.")
        self.assertEqual(h.state()["tasks"]["T04"]["status"], "pending")
        self.assertIn("T04", (h.wf / "plan.md").read_text())
        self.assertFalse((h.wf / "plan-amend.json").exists())
        self.assertIn("Yes, add the FAQ.", (h.wf / "decisions.md").read_text())
        ready = [a["id"] for a in json.loads(h.tp("next", "--json").out)["actions"] if a["action"] == "dispatch"]
        self.assertEqual(ready, ["T02", "T04"])

    def test_amend_never_changes_a_task_that_has_started(self) -> None:
        h = self.h
        h.approved()
        h.tp("dispatch", "T01")
        draft = self.draft()
        draft["tasks"][0]["brief"] = "Something else."
        del draft["tasks"][1]                                       # T02 has not started: may go
        draft["tasks"][1]["depends_on"] = ["T01"]
        (h.wf / "plan-amend.json").write_text(json.dumps(draft))
        res = h.tp("plan", "amend", "--answer", "ok", expect=2)
        self.assertIn("T01 has started", res.text)
        self.assertNotIn("T02", res.text)

    def test_amend_warns_when_the_remaining_work_overruns_the_budget(self) -> None:
        h = self.h
        h.approved()
        draft = self.draft()
        draft["tasks"] += [h.task(f"T{i}", f"x{i}.md", estimate_min=30) for i in range(10, 30)]
        (h.wf / "plan-amend.json").write_text(json.dumps(draft))
        self.assertIn("WARN: the remaining work runs past the budget", h.tp("plan", "amend").out)

    def test_amend_puts_new_work_in_a_review_batch_that_has_not_started(self) -> None:
        h = self.h
        h.approved(plan=h.plan([h.task("T01", "a.md"), h.task("T02", "b.md")], final_checks=[]), **FINAL_REVIEW)
        for tid, rel in (("T01", "a.md"), ("T02", "b.md")):
            h.author(tid, rel)
            h.tp("accept", tid, "--note", "ok")
        h.tp("dispatch", "B1/doc-reviewer")
        draft = self.draft()
        draft["tasks"].append(h.task("T03", "c.md"))
        (h.wf / "plan-amend.json").write_text(json.dumps(draft))
        self.assertIn("B1", h.tp("plan", "amend", expect=2).text)
        draft["review_batches"] = [{"id": "B1", "tasks": ["T01", "T02"]}, {"id": "B2", "tasks": ["T03"]}]
        (h.wf / "plan-amend.json").write_text(json.dumps(draft))
        h.tp("plan", "amend", "--answer", "Add T03 with its own review.")
        self.assertEqual(h.state()["reviews"]["B2/doc-reviewer"]["status"], "pending")
        self.assertEqual(h.state()["reviews"]["B1/doc-reviewer"]["status"], "in_flight")



if __name__ == "__main__":
    unittest.main()
