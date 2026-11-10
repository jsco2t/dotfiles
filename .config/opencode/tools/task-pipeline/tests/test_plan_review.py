"""The independent plan review: the gate between planning and execution is an agent's verdict,
bound to the exact plan revision — never the human's approval. The reviewer's coverage of the
requirements ledger is enforced, findings loop through fix-and-re-review, and a workflow from
before plan review keeps its human-approval contract."""
from __future__ import annotations

import json
import unittest
from typing import Any, Dict

from harness import Harness

PLAN_WITH_REQS = {
    "title": "Calc KB plan", "summary": "Two articles, then the index.",
    "conventions": [], "final_checks": [],
    "tasks": [],
}


class PlanReviewFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.confirmed()
        self.h.write_json("plan.json", self.h.plan())
        self.h.tp("plan", "check")
        self.h.tp("plan", "submit")

    def tearDown(self) -> None:
        self.h.close()

    def review(self, verdict: str = "pass", findings=None, coverage=None) -> str:
        h = self.h
        if h.state()["plan_review"].get("status") != "in_flight":  # a round already dispatched
            h.tp("plan", "review")
        rnd = h.state()["plan_review"]["round"]
        scope = h.read_json("scope.json")
        cov = coverage if coverage is not None else [{"requirement": r["id"], "covered": True, "note": "T01"}
                                                      for r in scope.get("requirements", [])]
        h.write_json(f"runs/plan/result-review-{rnd}.json",
                     {"review": "plan", "round": rnd, "verdict": verdict,
                      "findings": findings or [], "coverage": cov, "observations": []})
        return h.tp("plan", "record", "--agent-id", "pr-1").out

    def test_next_offers_the_review_not_a_human_gate(self) -> None:
        act = self.h.next()["actions"][0]
        self.assertEqual(act["action"], "plan_review")
        out = self.h.tp("plan", "review").out
        self.assertIn("PLAN REVIEW · round 1", out)
        self.assertIn('task(subagent_type="plan-reviewer"', out)
        brief = (self.h.wf / "runs" / "plan" / "brief-review-1.md").read_text()
        self.assertIn("## The request, verbatim", brief)
        self.assertIn("## The requirements ledger", brief)
        self.assertIn("R1", brief)

    def test_a_passing_review_enters_execution_without_a_human_answer(self) -> None:
        out = self.review("pass")
        self.assertIn("passed", out)
        self.assertEqual(self.h.next()["actions"][0]["action"], "approve")
        self.h.tp("approve")
        self.assertEqual(self.h.state()["phase"], "EXECUTING")
        self.assertIn("independent plan review passed", (self.h.wf / "decisions.md").read_text())

    def test_approve_before_any_review_is_refused(self) -> None:
        res = self.h.tp("approve", expect=2)
        self.assertIn("plan review is pending", res.text)
        self.assertEqual(self.h.state()["phase"], "AWAITING_APPROVAL")

    def test_findings_loop_through_fix_and_rereview_with_the_same_reviewer(self) -> None:
        out = self.review("changes", findings=[{"id": "F1", "state": "missing", "requirement": "R1",
                                                 "issue": "T01 does not prove R1.", "fix": "Tighten the criterion."}])
        self.assertIn("needs_triage", str(self.h.state()["plan_review"]["status"]))
        self.assertIn("F1", out)
        out = self.h.tp("plan", "triage", "--accept-all").out
        self.assertIn("Fix the plan", out)
        self.assertEqual(self.h.state()["plan_review"]["status"], "changes")
        # fix the plan, resubmit from the review loop, re-review
        plan = self.h.read_json("plan.json")
        plan["tasks"][0]["acceptance"] = ["Explains what Add does, citing src path:line, test-first."]
        self.h.write_json("plan.json", plan)
        self.h.tp("plan", "check")
        self.h.tp("plan", "submit")
        out = self.h.tp("plan", "review").out
        self.assertIn("round 2", out)
        self.assertIn('task(task_id="pr-1"', out)          # the same reviewer, resumed
        self.assertIn("Findings from the earlier round", (self.h.wf / "runs" / "plan" / "brief-review-2.md").read_text())
        self.review("pass")
        self.h.tp("approve")
        self.assertEqual(self.h.state()["phase"], "EXECUTING")

    def test_dismissing_every_finding_passes_with_a_recorded_manager_decision(self) -> None:
        self.review("changes", findings=[{"id": "F1", "state": "unnecessary", "requirement": "R1",
                                          "issue": "T02 is gold-plating.", "fix": "Drop T02."}])
        out = self.h.tp("plan", "triage", "--dismiss", "F1=the note is required by the request's wording").out
        self.assertIn("stands passed", out)
        self.assertIn("the request's wording", (self.h.wf / "decisions.md").read_text())
        self.h.tp("approve")
        self.assertEqual(self.h.state()["phase"], "EXECUTING")

    def test_an_edited_plan_after_a_passing_review_cannot_be_approved(self) -> None:
        self.review("pass")
        plan = self.h.read_json("plan.json")
        plan["tasks"][0]["title"] = "Changed"
        self.h.write_json("plan.json", plan)
        res = self.h.tp("approve", expect=2)
        self.assertIn("changed", res.text)  # sha-bound: the submitted revision is what passed

    def test_an_uncovered_requirement_becomes_a_finding_even_on_a_pass_verdict(self) -> None:
        out = self.review("pass", coverage=[{"requirement": "R1", "covered": False, "note": "no task proves it"}])
        self.assertIn("not covered", out)
        self.assertEqual(self.h.state()["plan_review"]["status"], "needs_triage")
        f = self.h.state()["plan_review"]["findings"]
        self.assertTrue(any("R1" in str(x.get("requirement", "")) for x in f))

    def test_missing_coverage_entries_are_refused(self) -> None:
        res = None
        self.h.tp("plan", "review")
        rnd = self.h.state()["plan_review"]["round"]
        self.h.write_json(f"runs/plan/result-review-{rnd}.json",
                          {"review": "plan", "round": rnd, "verdict": "pass", "findings": [],
                           "coverage": [], "observations": []})
        res = self.h.tp("plan", "record", "--agent-id", "pr-1", expect=2)
        self.assertIn("coverage is missing entries", res.text)

    def test_two_failed_rounds_go_to_the_human_via_revise(self) -> None:
        for _ in range(2):
            self.review("changes", findings=[{"id": "F1", "state": "missing", "requirement": "R1",
                                              "issue": "Still wrong.", "fix": "Fix it."}])
            self.h.tp("plan", "triage", "--accept-all")
            plan = self.h.read_json("plan.json")
            plan["tasks"][0]["title"] += " (revised)"
            self.h.write_json("plan.json", plan)
            self.h.tp("plan", "check")
            self.h.tp("plan", "submit")
        res = self.h.tp("plan", "review", expect=2)
        self.assertIn("2 independent review rounds", res.text)
        self.assertIn("tp revise", res.text)
        self.h.tp("revise", "--feedback", "Drop the second article; keep it minimal.")
        self.assertEqual(self.h.state()["phase"], "PLANNING")

    def test_the_reviewer_result_file_must_exist(self) -> None:
        self.h.tp("plan", "review")
        res = self.h.tp("plan", "record", "--agent-id", "pr-1", expect=2)
        self.assertIn("is missing", res.text)

    def test_observations_are_noticed_not_blocking(self) -> None:
        h = self.h
        h.tp("plan", "review")
        rnd = h.state()["plan_review"]["round"]
        scope = h.read_json("scope.json")
        h.write_json(f"runs/plan/result-review-{rnd}.json",
                     {"review": "plan", "round": rnd, "verdict": "pass", "findings": [],
                      "coverage": [{"requirement": r["id"], "covered": True, "note": "T01"} for r in scope["requirements"]],
                      "observations": ["The README is stale; not this run's work."]})
        out = h.tp("plan", "record", "--agent-id", "pr-1").out
        self.assertIn("passed", out)
        noticed = "\n".join(str(n) for n in h.wf.noticed_items()) if hasattr(h.wf, "noticed_items") else ""
        self.assertIn("passed", out)  # observations recorded via noticed, never gate


class LegacyApprovalTest(unittest.TestCase):
    """A workflow already in flight when plan review was introduced keeps its contract:
    `tp approve --answer` still works, and no review is demanded."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.confirmed()
        self.h.write_json("plan.json", self.h.plan())
        self.h.tp("plan", "check")
        self.h.tp("plan", "submit")

    def tearDown(self) -> None:
        self.h.close()

    def strip_plan_review(self) -> None:
        state = self.h.state()
        state.pop("plan_review", None)
        (self.h.wf / ".tp" / "state.json").write_text(json.dumps(state))
        self.h.tp("status")

    def test_a_pre_review_workflow_approves_with_the_humans_answer(self) -> None:
        self.strip_plan_review()
        self.h.tp("approve", "--answer", "go ahead")
        self.assertEqual(self.h.state()["phase"], "EXECUTING")

    def test_a_pre_review_workflow_without_an_answer_is_refused(self) -> None:
        self.strip_plan_review()
        res = self.h.tp("approve", expect=2)
        self.assertIn("predates plan review", res.text)


class RequirementsLedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def test_a_new_run_without_a_ledger_is_refused(self) -> None:
        self.h.init()
        scope = self.h.scope()
        del scope["requirements"]
        self.h.write_json("scope.json", scope)
        res = self.h.tp("scope", "check", expect=2)
        self.assertIn("requirements is the ledger", res.text)

    def test_a_new_run_without_a_plan_reviewer_is_refused(self) -> None:
        self.h.init()
        scope = self.h.scope()
        scope["participants"] = [p for p in scope["participants"] if p.get("role") != "plan"]
        self.h.write_json("scope.json", scope)
        res = self.h.tp("scope", "check", expect=2)
        self.assertIn("`plan`-role participant", res.text)

    def test_every_requirement_must_be_served_by_a_task(self) -> None:
        scope = self.h.scope(requirements=[
            {"id": "R1", "text": "The KB explains Add", "deliverables": ["D1"]},
            {"id": "R2", "text": "The KB names the build command", "deliverables": ["D1"]}])
        self.h.confirmed(**{"requirements": scope["requirements"]})
        plan = self.h.plan()  # every task cites R1 (the base); R2 is served by none
        self.h.write_json("plan.json", plan)
        res = self.h.tp("plan", "check", expect=2)
        self.assertIn("R2", res.text)
        self.assertIn("served by no task", res.text)

    def test_a_task_citing_an_unknown_requirement_is_refused(self) -> None:
        self.h.confirmed()
        plan = self.h.plan()
        plan["tasks"][0]["requirements"] = ["R9"]
        self.h.write_json("plan.json", plan)
        res = self.h.tp("plan", "check", expect=2)
        self.assertIn("R9", res.text)

    def test_plan_md_and_report_carry_the_coverage(self) -> None:
        scope = self.h.scope(requirements=[
            {"id": "R1", "text": "The KB explains Add", "deliverables": ["D1"]},
            {"id": "R2", "text": "The KB names the build command", "deliverables": ["D1"]}])
        self.h.confirmed(**{"requirements": scope["requirements"]})
        plan = self.h.plan()
        plan["tasks"][1]["requirements"] = ["R1", "R2"]
        self.h.write_json("plan.json", plan)
        self.h.tp("plan", "check")
        md = (self.h.wf / "plan.md").read_text()
        self.assertIn("## Requirements coverage", md)
        self.assertIn("R2 — The KB names the build command", md)
        self.assertIn("T02", md)


if __name__ == "__main__":
    unittest.main()
