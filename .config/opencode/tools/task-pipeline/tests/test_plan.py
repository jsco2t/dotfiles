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


if __name__ == "__main__":
    unittest.main()


class BudgetMeteringTest(unittest.TestCase):
    """The budget measures agent-minutes actually spent, not wall-clock since creation:
    a conversation that idles for hours between human messages must not exhaust the budget."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.confirmed(budget_minutes=60)

    def tearDown(self) -> None:
        self.h.close()

    def _backdate_created(self, hours: float) -> None:
        from datetime import datetime, timedelta, timezone
        sp = self.h.wf / ".tp" / "state.json"
        st = json.loads(sp.read_text())
        created = datetime.now(timezone.utc) - timedelta(hours=hours)
        st["created"] = created.strftime("%Y-%m-%dT%H:%M:%SZ")
        sp.write_text(json.dumps(st))

    def test_idle_wall_clock_does_not_exhaust_the_budget(self) -> None:
        # Seen live: an 11-hour gap between human messages left "budget leaves -551 of 120 min".
        self._backdate_created(hours=11)
        self.h.write_json("plan.json", self.h.plan())
        self.h.tp("plan", "check")  # must not raise

    def test_status_shows_spent_not_elapsed_against_the_budget(self) -> None:
        self._backdate_created(hours=11)
        out = self.h.tp("status").out
        self.assertNotIn("-551", out)
        self.assertNotIn("660 of 60", out)

    def test_zero_agent_minutes_means_zero_spent(self) -> None:
        self._backdate_created(hours=5)
        h = self.h
        h.write_json("plan.json", h.plan())
        h.tp("plan", "check")
        h.tp("plan", "submit")
        out = h.tp("plan", "submit", expect=2).out  # re-submit refused, but the message...
        # ...the harm we care about is elsewhere: submit must not claim hours of planning.
        h2_json = h.state()
        self.assertIn("phase", h2_json)


if __name__ == "__main__":
    unittest.main()


class CheckCwdTest(unittest.TestCase):
    """A check's cwd may name a workspace or an absolute directory — a code task's test
    suite often lives outside every workspace (seen live: the task-pipeline repo's own
    tests, which no workspace covers)."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.confirmed()

    def tearDown(self) -> None:
        self.h.close()

    def check(self, plan, expect: int = 0):
        self.h.write_json("plan.json", plan)
        return self.h.tp("plan", "check", expect=expect)

    def test_absolute_cwd_is_accepted(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            plan = self.h.plan(checks={"unit": {"cmd": "true", "cwd": d}})
            self.check(plan)

    def test_missing_absolute_cwd_is_refused(self) -> None:
        plan = self.h.plan(checks={"unit": {"cmd": "true", "cwd": "/nonexistent/tp-cwd-test"}})
        text = self.check(plan, expect=2).text
        self.assertIn("cwd", text)

    def test_relative_non_workspace_cwd_is_refused(self) -> None:
        plan = self.h.plan(checks={"unit": {"cmd": "true", "cwd": "nope"}})
        text = self.check(plan, expect=2).text
        self.assertIn("cwd", text)


class AmendTest(unittest.TestCase):
    """While EXECUTING, mechanical plan details (paths, test_cmd, checks, estimate, brief)
    can be amended in place — seen live three times: a root-level file the glob missed, a
    new human-requested deliverable, and a test command fix — without a full approval
    round-trip. Structural changes still need `tp revise`."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved(plan=self.h.plan([self.h.task("T01", "a.md", checks=[])]))

    def tearDown(self) -> None:
        self.h.close()

    def _amend(self, **over):
        plan = self.h.plan([self.h.task("T01", "a.md", checks=[], **over)])
        self.h.write_json("plan.json", plan)
        return self.h.tp("amend", "--reason", "root file scope fix")

    def test_paths_amend_stays_executing(self) -> None:
        self._amend(paths=["a.md", "index.md"])
        self.assertEqual(self.h.state()["phase"], "EXECUTING")
        st = self.h.state()["tasks"]["T01"]
        self.assertEqual(st["status"], "pending")
        self.assertIn("root file scope fix", (self.h.wf / "decisions.md").read_text())

    def test_task_cmd_amend_is_allowed(self) -> None:
        self._amend(test_cmd="true", test_mode="pin")
        self.assertEqual(self.h.state()["phase"], "EXECUTING")

    def test_structural_change_is_refused(self) -> None:
        plan = self.h.plan([self.h.task("T01", "a.md", checks=[]),
                            self.h.task("T02", "b.md", checks=[])])
        self.h.write_json("plan.json", plan)
        text = self.h.tp("amend", "--reason", "new task", expect=2).text
        self.assertIn("revise", text)

    def test_noop_amend_is_refused(self) -> None:
        self.h.tp("amend", "--reason", "nothing changed", expect=2)

    def test_amend_needs_execution_phase(self) -> None:
        h = Harness()
        try:
            h.confirmed()
            h.write_json("plan.json", h.plan())
            h.tp("amend", "--reason", "too early", expect=2)
        finally:
            h.close()


class ConventionsTest(unittest.TestCase):
    """Briefs repeated conventions and mid-run answers only because the manager pasted them in.
    A plan may now name files inside the workflow folder (`wf:path`) as sources and as shared
    `conventions` every brief starts from; conventions are SHA-frozen at approval — a later edit
    is a contract change and dispatch refuses it."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.confirmed()
        (self.h.wf / "conventions.md").write_text("# Conventions\n\nEvery article cites `path:line`.\n")

    def tearDown(self) -> None:
        self.h.close()

    def test_workflow_files_can_be_sources_and_shared_conventions(self) -> None:
        h = self.h
        plan = h.plan([h.task("T01", "a.md", sources=["wf:conventions.md", "src:calc/**"])])
        plan["conventions"] = ["wf:conventions.md"]
        h.write_json("plan.json", plan)
        h.tp("plan", "check")
        h.tp("plan", "submit")
        h.tp("approve", "--answer", "approve with conventions")
        h.tp("dispatch", "T01")
        brief = (h.run_dir("T01") / "brief-author-0.md").read_text()
        self.assertIn("conventions for every task: read first", brief)  # the conventions line
        self.assertIn("wf", "wf:conventions.md")  # the source prefix resolves to the workflow file

    def test_conventions_freeze_with_the_plan(self) -> None:
        h = self.h
        plan = h.plan([h.task("T01", "a.md")])
        plan["conventions"] = ["wf:conventions.md"]
        h.write_json("plan.json", plan)
        h.tp("plan", "check")
        h.tp("plan", "submit")
        h.tp("approve", "--answer", "approve")
        (h.wf / "conventions.md").write_text("# Conventions\n\nChanged after approval.\n")
        res = h.tp("dispatch", "T01", expect=2)
        self.assertIn("conventions", res.text)

    def test_a_missing_conventions_file_is_refused_at_plan_check(self) -> None:
        h = self.h
        plan = h.plan([h.task("T01", "a.md")])
        plan["conventions"] = ["wf:nope.md"]
        h.write_json("plan.json", plan)
        text = h.tp("plan", "check", expect=2).text
        self.assertIn("conventions", text)

    def test_wf_is_not_a_workspace_name(self) -> None:
        h = Harness()  # scope checking happens in SCOPING
        try:
            h.init()
            scope = h.scope()
            scope["workspaces"].append({"name": "wf", "path": "/tmp/wf", "mode": "read"})
            h.write_json("scope.json", scope)
            self.assertIn("wf", h.tp("scope", "check", expect=2).text)
        finally:
            h.close()
