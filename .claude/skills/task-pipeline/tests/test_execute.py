"""Execution: the script decides what runs next, agents hand back through files, and
anything off the plan is caught mechanically."""
from __future__ import annotations

import json
import unittest

from harness import Harness

REVIEWED = dict(review="per-task", participants=[
    {"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."},
    {"agent": "doc-reviewer", "role": "reviewer", "why": "Checks every article's accuracy."}])


def statuses(h: Harness):
    return {tid: t["status"] for tid, t in h.state()["tasks"].items()}


class DispatchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def test_next_respects_dependencies(self) -> None:
        ids = [a["id"] for a in self.h.next()["actions"] if a["action"] == "dispatch"]
        self.assertEqual(ids, ["T01", "T02"])

    def test_at_most_three_in_flight(self) -> None:
        h = Harness()
        try:
            h.approved(plan=h.plan([h.task(f"T0{i}", f"a{i}.md") for i in range(1, 5)]))
            h.tp("dispatch", "T01", "T02", "T03")
            self.assertEqual([a for a in h.next()["actions"] if a["action"] == "dispatch"], [])
            self.assertIn("3 agents", h.tp("dispatch", "T04", expect=2).text)
        finally:
            h.close()

    def test_two_dispatches_in_one_call(self) -> None:
        # Seen live: the manager chained two dispatches with `echo =====`, which zsh treats as a
        # command lookup and aborts. One call that takes both ids leaves nothing to chain.
        nxt = self.h.tp("next").out
        self.assertIn("tp dispatch T01 T02", nxt)
        out = self.h.tp("dispatch", "T01", "T02").out
        self.assertIn("DISPATCH T01", out)
        self.assertIn("DISPATCH T02", out)
        self.assertEqual(set(self.h.state()["in_flight"]), {"T01", "T02"})

    def test_a_refused_id_does_not_hide_the_dispatches_that_succeeded(self) -> None:
        h = Harness()
        try:
            h.approved(plan=h.plan([h.task(f"T0{i}", f"a{i}.md") for i in range(1, 5)]))
            res = h.tp("dispatch", "T01", "T02", "T03", "T04", expect=2)
            self.assertTrue(res.out.startswith("DISPATCH T01"))   # printed as dispatched, not as an error
            self.assertIn("\nDISPATCH T03", res.out)
            self.assertIn("ERROR: T04: 3 agents", res.out)
            self.assertEqual(set(h.state()["in_flight"]), {"T01", "T02", "T03"})
        finally:
            h.close()

    def test_dispatch_refuses_a_task_whose_dependencies_are_open(self) -> None:
        self.assertIn("T01", self.h.tp("dispatch", "T03", expect=2).text)

    def test_brief_is_small_self_contained_and_file_based(self) -> None:
        out = self.h.tp("dispatch", "T01").out
        self.assertIn("kb-author", out)
        brief_path = self.h.run_dir("T01") / "brief-author-0.md"
        self.assertIn(str(brief_path), out)
        brief = brief_path.read_text()
        self.assertLess(len(brief.encode()), 4000)
        self.assertIn("/task-pipeline", brief)
        self.assertIn("complete contract", brief)    # the brief, not the agent definition, rules
        self.assertNotIn("orchestrator", brief)
        self.assertIn("Point first", brief)           # answer-first core, inlined
        self.assertIn("Agent tool", brief)            # no sub-agent fan-out
        self.assertIn("--max-agents=0", brief)        # ...including inside the skills it loads
        self.assertIn(str(self.h.kb / "architecture/overview.md"), brief)
        self.assertIn("result-author.json", brief)
        self.assertIn("one line", brief)
        # Seen live: a "Read" list was taken as a fence, and the article skipped its callers.
        self.assertIn("## Start from", brief)
        self.assertIn("anything in the read-only workspaces", brief)


class RecordTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def test_missing_or_malformed_result_is_refused_with_a_hint(self) -> None:
        self.h.tp("dispatch", "T01")
        self.assertIn("result-author.json", self.h.tp("record", "T01", expect=2).text)
        self.h.result("T01", "author", summary="word " * 120)
        self.assertIn("summary", self.h.tp("record", "T01", expect=2).text)

    def test_clean_author_pass_goes_to_the_manager_fact_check(self) -> None:
        out = self.h.author("T01", "architecture/overview.md").out
        self.assertEqual(statuses(self.h)["T01"], "needs_check")
        self.assertIn("calc/calc.go:5", out)          # the sampled citation
        self.assertIn("return a + b", out)             # ...and the source lines it cites
        self.h.tp("accept", "T01", "--note", "Citation matches Add.")
        self.assertEqual(statuses(self.h)["T01"], "accepted")

    def test_doubtful_citations_go_to_the_front_of_the_fact_check_not_to_a_fix_round(self) -> None:
        self.h.tp("dispatch", "T01")
        p = self.h.kb / "architecture" / "overview.md"
        p.parent.mkdir(parents=True)
        p.write_text("# Overview\n\n`Add` sums (`calc/calc.go:5`). `Divide` divides (`calc/calc.go:2`).\n")
        self.h.result("T01", "author", changed=["architecture/overview.md"])
        out = self.h.tp("record", "T01").out
        self.assertEqual(statuses(self.h)["T01"], "needs_check")
        flagged = out.index("Divide")
        self.assertLess(flagged, out.index("`Add` sums"))
        self.assertIn("may not support", out)

    def test_files_outside_the_task_paths_fail_the_task(self) -> None:
        self.h.tp("dispatch", "T01")
        self.h.good_article("architecture/overview.md")
        (self.h.kb / "index.md").write_text("# KB\n")      # belongs to T03
        self.h.result("T01", "author", changed=["architecture/overview.md"])
        out = self.h.tp("record", "T01", "--agent-id", "a1").out
        self.assertIn("index.md", out)
        self.assertEqual(statuses(self.h)["T01"], "needs_fix")

    def test_a_modified_read_only_workspace_fails_the_task(self) -> None:
        self.h.tp("dispatch", "T01")
        self.h.good_article("architecture/overview.md")
        (self.h.src / "calc" / "calc.go").write_text("package calc\n")
        self.h.result("T01", "author", changed=["architecture/overview.md"])
        out = self.h.tp("record", "T01").out
        self.assertIn("read-only", out)
        self.assertEqual(statuses(self.h)["T01"], "needs_fix")

    def test_broken_check_starts_a_fix_round_with_the_same_agent(self) -> None:
        self.h.tp("dispatch", "T01")
        p = self.h.kb / "architecture" / "overview.md"
        p.parent.mkdir(parents=True)
        p.write_text("# Overview\n\nSee [missing](nope.md).\n")
        self.h.result("T01", "author", changed=["architecture/overview.md"])
        self.h.tp("record", "T01", "--agent-id", "agent-77")
        self.assertEqual(statuses(self.h)["T01"], "needs_fix")
        fix = [a for a in self.h.next()["actions"] if a["id"] == "T01"][0]
        self.assertEqual(fix["action"], "fix")
        self.assertEqual(fix["agent_id"], "agent-77")
        out = self.h.tp("dispatch", "T01").out
        self.assertIn("SendMessage", out)
        self.assertIn("agent-77", out)
        brief = (self.h.run_dir("T01") / "brief-fix-1.md").read_text()
        self.assertIn("nope.md", brief)
        self.h.good_article("architecture/overview.md")
        self.h.result("T01", "fix", changed=["architecture/overview.md"])
        self.h.tp("record", "T01")
        self.assertEqual(statuses(self.h)["T01"], "needs_check")

    def test_fix_rounds_are_capped_then_the_human_decides(self) -> None:
        self.h.tp("dispatch", "T01")
        p = self.h.kb / "architecture" / "overview.md"
        p.parent.mkdir(parents=True)
        for step in ("author", "fix", "fix"):
            if step == "fix":
                self.h.tp("dispatch", "T01")
            p.write_text("# Overview\n\nSee [missing](nope.md).\n")
            self.h.result("T01", step, changed=["architecture/overview.md"])
            self.h.tp("record", "T01")
        self.assertEqual(statuses(self.h)["T01"], "blocked")
        acts = self.h.next()["actions"]
        self.assertEqual(acts[0]["action"], "human")
        self.h.tp("resolve", "--task", "T01", "--action", "retry", "--answer", "One more try.")
        self.assertEqual(statuses(self.h)["T01"], "needs_fix")

    def test_needs_input_blocks_until_answered(self) -> None:
        self.h.tp("dispatch", "T01")
        self.h.result("T01", "author", status="needs_input", questions=["Is kb/ markdown only?"])
        out = self.h.tp("record", "T01").out
        self.assertIn("Is kb/ markdown only?", out)
        self.assertEqual(statuses(self.h)["T01"], "blocked")
        self.h.tp("resolve", "--task", "T01", "--action", "answer", "--answer", "Yes, markdown only.")
        self.assertEqual(statuses(self.h)["T01"], "in_flight")
        self.assertIn("Yes, markdown only.", (self.h.wf / "decisions.md").read_text())

    def test_noticed_items_are_logged_not_actioned(self) -> None:
        self.h.tp("dispatch", "T01")
        self.h.good_article("architecture/overview.md")
        self.h.result("T01", "author", changed=["architecture/overview.md"],
                      noticed=["calc has no tests."])
        self.h.tp("record", "T01")
        self.assertIn("calc has no tests.", (self.h.wf / "noticed.md").read_text())

    def test_concurrent_tasks_do_not_flag_each_other(self) -> None:
        self.h.tp("dispatch", "T01")
        self.h.tp("dispatch", "T02")
        self.h.good_article("architecture/overview.md")
        self.h.good_article("build/guide.md", "Build")
        self.h.result("T01", "author", changed=["architecture/overview.md"])
        self.h.tp("record", "T01")
        self.assertEqual(statuses(self.h)["T01"], "needs_check")

    def test_manager_rejection_is_a_fix_round(self) -> None:
        self.h.author("T01", "architecture/overview.md", agent_id="a9")
        self.h.tp("reject", "T01", "--reason", "The overview never mentions mul.")
        self.assertEqual(statuses(self.h)["T01"], "needs_fix")
        self.h.tp("dispatch", "T01")
        self.assertIn("never mentions mul", (self.h.run_dir("T01") / "brief-fix-1.md").read_text())


class ReviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved(**REVIEWED)

    def tearDown(self) -> None:
        self.h.close()

    def test_review_loop(self) -> None:
        h = self.h
        h.author("T01", "architecture/overview.md", agent_id="author-1")
        self.assertEqual(statuses(h)["T01"], "needs_review")
        act = [a for a in h.next()["actions"] if a["id"] == "T01"][0]
        self.assertEqual((act["action"], act["agent"]), ("review", "doc-reviewer"))
        h.tp("dispatch", "T01")
        brief = (h.run_dir("T01") / "brief-review-1.md").read_text()
        self.assertIn("Do not edit", brief)
        self.assertIn("review-1.json", brief)
        h.review("T01", 1, "changes", [{"id": "F1", "state": "wrong", "blocking": True,
                                        "where": "architecture/overview.md:3",
                                        "issue": "Add returns an int, not a float.", "fix": "Say int."}])
        h.tp("record", "T01", "--agent-id", "rev-1")
        self.assertEqual(statuses(h)["T01"], "needs_fix")
        out = h.tp("dispatch", "T01").out
        self.assertIn("author-1", out)
        self.assertIn("review-1.json", (h.run_dir("T01") / "brief-fix-1.md").read_text())
        h.result("T01", "fix", changed=["architecture/overview.md"])
        h.tp("record", "T01")
        self.assertEqual(statuses(h)["T01"], "needs_review")
        h.tp("dispatch", "T01")
        h.review("T01", 2, "pass")
        h.tp("record", "T01")
        self.assertEqual(statuses(h)["T01"], "needs_check")

    def test_verdict_must_match_blocking_findings(self) -> None:
        h = self.h
        h.author("T01", "architecture/overview.md")
        h.tp("dispatch", "T01")
        h.review("T01", 1, "pass", [{"id": "F1", "state": "wrong", "blocking": True,
                                     "where": "x:1", "issue": "Wrong.", "fix": "Fix."}])
        self.assertIn("verdict", h.tp("record", "T01", expect=2).text)

    def test_reviewer_edits_are_refused(self) -> None:
        h = self.h
        h.author("T01", "architecture/overview.md")
        h.tp("dispatch", "T01")
        (h.kb / "architecture" / "overview.md").write_text("# Rewritten by the reviewer\n")
        h.review("T01", 1, "pass")
        self.assertIn("reviewer changed", h.tp("record", "T01").out)
        self.assertEqual(statuses(h)["T01"], "needs_fix")


class ExceptionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def test_a_stopped_agent_frees_its_slot_and_the_task_can_be_redispatched(self) -> None:
        self.h.tp("dispatch", "T01")
        self.h.tp("exception", "--task", "T01", "--summary", "Agent ran 40 min past its box; stopped it.")
        self.assertEqual(statuses(self.h)["T01"], "blocked")
        self.assertEqual(self.h.state()["in_flight"], {})
        self.assertEqual(self.h.next()["actions"][0]["action"], "human")
        self.h.tp("resolve", "--task", "T01", "--action", "answer", "--answer", "Re-run it with the same brief.")
        self.assertEqual(statuses(self.h)["T01"], "pending")
        self.h.tp("dispatch", "T01")

    def test_workflow_level_exception_blocks_until_resolved(self) -> None:
        self.h.tp("exception", "--summary", "The source repo moved to a new commit mid-run.")
        self.assertEqual(self.h.next()["actions"][0]["action"], "human")
        self.h.tp("resolve", "--action", "answer", "--answer", "Keep the original pin.")
        self.assertNotEqual(self.h.next()["actions"][0]["action"], "human")


FINAL_REVIEW = dict(review="final", participants=[
    {"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."},
    {"agent": "doc-reviewer", "role": "reviewer", "why": "Reviews the finished KB for accuracy."}])
S1 = "B1/doc-reviewer"


class BatchReviewTest(unittest.TestCase):
    """Review runs once, at the end, over completed work in bulk: one session per batch and
    reviewer, a manager triage of what it found, fixes by the owning authors, and one
    verification session scoped to those findings."""

    def setUp(self) -> None:
        self.h = h = Harness()
        plan = h.plan(review_batches=[{"id": "B1", "tasks": ["T01", "T02"]}, {"id": "B2", "tasks": ["T03"]}])
        h.approved(plan=plan, **FINAL_REVIEW)

    def tearDown(self) -> None:
        self.h.close()

    def accept_all(self) -> None:
        h = self.h
        for tid, rel in (("T01", "architecture/overview.md"), ("T02", "build/guide.md")):
            h.author(tid, rel, agent_id=f"author-{tid}")
            h.tp("accept", tid, "--note", "ok")
        h.tp("dispatch", "T03")
        (h.kb / "index.md").write_text("# KB\n\n- [O](architecture/overview.md)\n- [B](build/guide.md)\n")
        h.result("T03", "author", changed=["index.md"])
        h.tp("record", "T03", "--agent-id", "author-T03")
        h.tp("accept", "T03", "--note", "ok")

    def review(self, session: str, n: int, verdict: str, findings=()) -> None:
        batch, reviewer = session.split("/")
        d = self.h.wf / "runs" / batch
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{reviewer}-{n}.json").write_text(json.dumps({"batch": batch, "verdict": verdict,
                                                           "findings": list(findings)}))

    def finding(self, fid: str, where: str, blocking: bool = True) -> dict:
        return {"id": fid, "state": "wrong" if blocking else "cosmetic", "blocking": blocking, "where": where,
                "issue": f"{fid} is wrong at {where}.", "fix": "Correct it."}

    def test_review_waits_until_every_task_is_accepted(self) -> None:
        h = self.h
        for tid, rel in (("T01", "architecture/overview.md"), ("T02", "build/guide.md")):
            h.author(tid, rel)
            h.tp("accept", tid, "--note", "ok")
        self.assertNotIn("review", [a["action"] for a in h.next()["actions"]])   # B1 done, but T03 is not
        h.tp("dispatch", S1, expect=2)
        self.assertEqual(statuses(h)["T01"], "accepted")   # per-task review is off: straight to fact check

    def test_every_session_starts_together_once_all_work_is_accepted(self) -> None:
        self.accept_all()
        reviews = [a["id"] for a in self.h.next()["actions"] if a["action"] == "review"]
        self.assertEqual(reviews, ["B1/doc-reviewer", "B2/doc-reviewer"])
        self.h.tp("final", expect=2)

    def test_the_brief_covers_the_whole_batch_and_the_change_as_a_file(self) -> None:
        self.accept_all()
        self.h.tp("dispatch", S1)
        brief = (self.h.wf / "runs" / "B1" / "brief-doc-reviewer-1.md").read_text()
        for needle in ("architecture/overview.md", "build/guide.md", "T01", "T02", "Do not edit",
                       "changes.json", "doc-reviewer-1.json", "Agent tool"):
            self.assertIn(needle, brief)
        self.assertNotIn("index.md", brief.split("## Hand back")[0].split("Deliverables")[1])   # B2's file
        changes = json.loads((self.h.wf / "runs" / "B1" / "changes.json").read_text())
        self.assertEqual(sorted(changes["files"]), ["kb:architecture/overview.md", "kb:build/guide.md"])

    def test_findings_route_by_path_to_the_owning_task_after_triage(self) -> None:
        h = self.h
        self.accept_all()
        h.tp("dispatch", S1)
        self.review(S1, 1, "changes", [self.finding("F1", "build/guide.md:3"),
                                       self.finding("F2", "architecture/overview.md:1", blocking=False)])
        out = h.tp("record", S1, "--agent-id", "rev-1").out
        self.assertIn("F1 → T02", out)
        self.assertEqual(h.next()["actions"][0]["action"], "triage")
        h.tp("triage", S1, "--accept-all")
        self.assertEqual(statuses(h)["T02"], "needs_fix")
        self.assertEqual(statuses(h)["T01"], "accepted")
        out = h.tp("dispatch", "T02").out
        self.assertIn("author-T02", out)                                  # the same author fixes it
        self.assertIn("doc-reviewer-1.json", (h.run_dir("T02") / "brief-fix-1.md").read_text())
        h.result("T02", "fix", changed=["build/guide.md"])
        h.tp("record", "T02")
        h.tp("accept", "T02", "--note", "fixed")
        act = [a for a in h.next()["actions"] if a.get("id") == S1][0]
        self.assertEqual((act["action"], act["agent_id"]), ("review", "rev-1"))  # verification: same reviewer
        out = h.tp("dispatch", S1).out
        self.assertIn("SendMessage", out)
        verify = (h.wf / "runs" / "B1" / "brief-doc-reviewer-2.md").read_text()
        self.assertIn("F1", verify)
        self.assertIn("do not start a new review", verify)
        self.review(S1, 2, "pass")
        h.tp("record", S1)
        self.assertEqual(h.state()["reviews"][S1]["status"], "done")

    def test_the_manager_dismisses_a_false_positive_with_a_reason(self) -> None:
        h = self.h
        self.accept_all()
        h.tp("dispatch", S1)
        self.review(S1, 1, "changes", [self.finding("F1", "build/guide.md:3")])
        h.tp("record", S1)
        h.tp("triage", S1, "--dismiss", "F1", "--reason", "The guide already says int on line 3.")
        self.assertEqual(statuses(h)["T02"], "accepted")
        self.assertEqual(h.state()["reviews"][S1]["status"], "done")
        self.assertIn("already says int", (h.wf / "decisions.md").read_text())

    def test_a_finding_no_task_owns_must_be_assigned_or_dismissed(self) -> None:
        h = self.h
        self.accept_all()
        h.tp("dispatch", S1)
        self.review(S1, 1, "changes", [self.finding("F1", "glossary.md:1")])
        h.tp("record", S1)
        self.assertIn("F1", h.tp("triage", S1, "--accept-all", expect=2).text)
        h.tp("triage", S1, "--assign", "F1=T02")
        self.assertEqual(statuses(h)["T02"], "needs_fix")

    def test_verification_is_the_last_round_then_the_human_decides(self) -> None:
        h = self.h
        self.accept_all()
        h.tp("dispatch", S1)
        self.review(S1, 1, "changes", [self.finding("F1", "build/guide.md:3")])
        h.tp("record", S1, "--agent-id", "rev-1")
        h.tp("triage", S1, "--accept-all")
        h.tp("dispatch", "T02")
        h.result("T02", "fix", changed=["build/guide.md"])
        h.tp("record", "T02")
        h.tp("accept", "T02", "--note", "fixed")
        h.tp("dispatch", S1)
        self.review(S1, 2, "changes", [self.finding("F1", "build/guide.md:3")])
        h.tp("record", S1)
        self.assertEqual(h.state()["reviews"][S1]["status"], "blocked")
        self.assertEqual(h.next()["actions"][0]["action"], "human")
        h.tp("resolve", "--review", S1, "--action", "accept", "--answer", "Ship it; I'll fix F1 by hand.")
        self.assertEqual(h.state()["reviews"][S1]["status"], "done")

    def test_final_runs_after_every_session_is_done_and_reports_them(self) -> None:
        h = self.h
        self.accept_all()
        h.tp("dispatch", S1, "B2/doc-reviewer")
        self.review(S1, 1, "pass")
        self.review("B2/doc-reviewer", 1, "pass")
        h.tp("record", S1)
        h.tp("record", "B2/doc-reviewer")
        self.assertEqual(h.next()["actions"][0]["action"], "final")
        h.tp("final")
        report = (h.wf / "report.md").read_text()
        self.assertIn("B1/doc-reviewer", report)
        self.assertIn("2 review sessions", report)


class HaltTest(unittest.TestCase):
    """`halt` (or `hault`): nothing new starts, agents already working finish their current
    step, and once the last is recorded the stop point is written to halt.json."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def test_in_flight_work_finishes_then_the_stop_point_is_recorded(self) -> None:
        h = self.h
        h.tp("dispatch", "T01", "T02")
        out = h.tp("halt", "--reason", "Stopping for the day.").out
        self.assertIn("T01", out)
        self.assertIn("T02", out)
        self.assertEqual([a["action"] for a in h.next()["actions"]], ["halting"])
        self.assertIn("halt", h.tp("dispatch", "T03", expect=2).text)
        h.good_article("architecture/overview.md")
        h.result("T01", "author", changed=["architecture/overview.md"])
        self.assertIn("still waiting for T02", h.tp("record", "T01").out)
        self.assertFalse((h.wf / "halt.json").exists())
        h.good_article("build/guide.md", "Build")
        h.result("T02", "author", changed=["build/guide.md"])
        self.assertIn("HALTED", h.tp("record", "T02").out)
        record = json.loads((h.wf / "halt.json").read_text())
        self.assertEqual(record["reason"], "Stopping for the day.")
        self.assertEqual(sorted(record["tasks"]["needs_check"]), ["T01", "T02"])
        self.assertIn({"action": "check", "id": "T01"}, record["next_on_resume"])
        self.assertEqual(h.next()["actions"], [{"action": "halted"}])
        self.assertIn("HALT complete", h.tp("status").out)

    def test_hault_is_accepted_and_stops_at_once_when_nothing_is_running(self) -> None:
        out = self.h.tp("hault").out
        self.assertIn("HALTED", out)
        self.assertTrue((self.h.wf / "halt.json").exists())

    def test_resume_continues_from_where_it_stopped(self) -> None:
        h = self.h
        h.tp("halt", "--reason", "Lunch.")
        h.tp("resume", "--answer", "Back — carry on.")
        self.assertEqual([a["id"] for a in h.next()["actions"] if a["action"] == "dispatch"], ["T01", "T02"])
        decisions = (h.wf / "decisions.md").read_text()
        self.assertIn("Lunch.", decisions)
        self.assertIn("carry on", decisions)
        h.tp("dispatch", "T01")

    def test_a_halt_holds_research_during_planning(self) -> None:
        h = Harness()
        try:
            h.confirmed(participants=[
                {"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."},
                {"agent": "codebase-researcher", "role": "research", "why": "Maps dash/ for D1."}],
                research={"budget_minutes": 30, "why": "dash/ is opaque to the survey."})
            qf = h.root / "q"
            qf.write_text("Which areas does dash/ split into?")
            h.tp("research", "add", "R1", "--agent", "codebase-researcher", "--purpose", "map",
                 "--questions-file", str(qf), "--done-when", "I can split it.")
            h.tp("halt", "--reason", "Pause planning.")
            self.assertEqual(h.next()["actions"], [{"action": "halted"}])
            self.assertIn("halt", h.tp("dispatch", "R1", expect=2).text)
        finally:
            h.close()


class CompatTest(unittest.TestCase):
    def test_state_written_by_the_previous_version_still_runs(self) -> None:
        # A workflow approved before research budgets and review batches existed must keep
        # executing after the new version is installed mid-run.
        h = Harness()
        try:
            h.approved()
            path = h.wf / ".tp" / "state.json"
            state = json.loads(path.read_text())
            for key in ("reviews", "research_extra", "write_baseline"):
                state.pop(key, None)
            path.write_text(json.dumps(state))
            h.tp("status")
            h.tp("report")
            h.author("T01", "architecture/overview.md")
            h.tp("accept", "T01", "--note", "ok")
            self.assertEqual(statuses(h)["T01"], "accepted")
        finally:
            h.close()


class FinalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def finish(self, link_everything: bool = True) -> None:
        h = self.h
        for tid, rel in (("T01", "architecture/overview.md"), ("T02", "build/guide.md")):
            h.author(tid, rel)
            h.tp("accept", tid, "--note", "Sampled citation is correct.")
        h.tp("dispatch", "T03")
        links = "- [Overview](architecture/overview.md)\n"
        if link_everything:
            links += "- [Build](build/guide.md)\n"
        (h.kb / "index.md").write_text("# Calc KB\n\n" + links)
        h.result("T03", "author", changed=["index.md"])
        h.tp("record", "T03")
        h.tp("accept", "T03", "--note", "Index links checked.")

    def test_final_runs_package_checks_and_writes_the_report(self) -> None:
        self.finish()
        self.assertEqual(self.h.next()["actions"][0]["action"], "final")
        self.h.tp("final")
        self.assertEqual(self.h.state()["phase"], "DONE")
        report = (self.h.wf / "report.md").read_text()
        for tid in ("T01", "T02", "T03"):
            self.assertIn(tid, report)
        self.assertIn("min", report)

    def test_final_catches_an_article_no_index_reaches(self) -> None:
        self.finish(link_everything=False)
        res = self.h.tp("final", expect=2)
        self.assertIn("build/guide.md", res.text)
        self.assertNotEqual(self.h.state()["phase"], "DONE")

    def test_final_refuses_while_tasks_are_open(self) -> None:
        self.h.tp("final", expect=2)

    def test_report_shows_timings(self) -> None:
        self.h.author("T01", "architecture/overview.md")
        out = self.h.tp("report").out
        self.assertIn("planning", out)
        self.assertIn("T01", out)


class StatusTest(unittest.TestCase):
    def test_status_is_compact(self) -> None:
        h = Harness()
        try:
            h.approved()
            h.tp("dispatch", "T01")
            out = h.tp("status").out
            self.assertIn("EXECUTING", out)
            self.assertIn("T01", out)
            self.assertLess(len(out.splitlines()), 25)
            data = json.loads(h.tp("status", "--json").out)
            self.assertEqual(data["phase"], "EXECUTING")
        finally:
            h.close()


if __name__ == "__main__":
    unittest.main()
