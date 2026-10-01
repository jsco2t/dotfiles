"""Execution: the script decides what runs next, agents hand back through files, and
anything off the plan is caught mechanically."""
from __future__ import annotations

import json
import re
import unittest
from datetime import datetime, timedelta

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


class ConventionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = h = Harness()
        h.confirmed(**FINAL_REVIEW)
        (h.wf / "conventions.md").write_text("# Conventions\n\nOne note per root cause.\n")
        h.write_json("plan.json", h.plan(conventions=["wf:conventions.md"]))
        h.tp("plan", "check")
        h.tp("plan", "submit")
        h.tp("approve", "--answer", "approve")

    def tearDown(self) -> None:
        self.h.close()

    def test_conventions_reach_every_brief(self) -> None:
        h = self.h
        h.tp("dispatch", "T01")
        conventions = str(h.wf / "conventions.md")
        brief = (h.run_dir("T01") / "brief-author-0.md").read_text()
        self.assertIn(conventions, brief.split("## Start from")[1].split("## Done when")[0])
        h.author("T02", "build/guide.md")
        h.good_article("architecture/overview.md")
        h.result("T01", "author", changed=["architecture/overview.md"])
        h.tp("record", "T01")
        for tid in ("T01", "T02"):
            h.tp("accept", tid, "--note", "ok")
        h.tp("dispatch", "T03")
        (h.kb / "index.md").write_text("# KB\n\n- [O](architecture/overview.md)\n- [B](build/guide.md)\n")
        h.result("T03", "author", changed=["index.md"])
        h.tp("record", "T03")
        h.tp("accept", "T03", "--note", "ok")
        h.tp("dispatch", "B1/doc-reviewer")
        self.assertIn(conventions, (h.wf / "runs" / "B1" / "brief-doc-reviewer-1.md").read_text())

    def test_conventions_freeze_with_the_plan(self) -> None:
        (self.h.wf / "conventions.md").write_text("# Conventions\n\nAnything goes.\n")
        self.assertIn("conventions.md changed", self.h.tp("next", expect=2).text)

    def test_conventions_change_through_an_amendment_without_stopping_the_run(self) -> None:
        # New conventions go in a new file the draft points at: the frozen one stays as it is, so
        # agents in flight keep recording while the human considers the amendment.
        h = self.h
        h.tp("dispatch", "T01")
        out = h.tp("plan", "amend").out
        self.assertIn("new file", out)
        (h.wf / "conventions-2.md").write_text("# Conventions\n\nOne note per finding.\n")
        draft = json.loads((h.wf / "plan-amend.json").read_text())
        draft["conventions"] = ["wf:conventions-2.md"]
        (h.wf / "plan-amend.json").write_text(json.dumps(draft))
        self.assertIn("conventions changed", h.tp("plan", "amend").out)
        h.tp("next")
        h.good_article("architecture/overview.md")
        h.result("T01", "author", changed=["architecture/overview.md"])
        h.tp("record", "T01")                                        # the run carries on meanwhile
        h.tp("plan", "amend", "--answer", "Yes, one note per finding.")
        h.tp("dispatch", "T02")
        brief = (h.run_dir("T02") / "brief-author-0.md").read_text()
        self.assertIn(str(h.wf / "conventions-2.md"), brief)
        self.assertNotIn(str(h.wf / "conventions.md"), brief)


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

    def test_answers_reach_every_later_brief_for_their_task(self) -> None:
        # Seen live: "One note per root cause" went to decisions.md only; the task's brief never
        # carried it, so it reached the agent only through a hand-edited conventions file.
        h = self.h
        h.tp("exception", "--task", "T01", "--summary", "One note per finding, or per root cause?")
        h.tp("resolve", "--task", "T01", "--action", "answer", "--by", "human", "--answer", "One note per root cause.")
        h.tp("exception", "--summary", "Cite the pinned commit or main?")
        h.tp("resolve", "--action", "answer", "--answer", "Cite the pinned commit.")
        h.tp("dispatch", "T01", "T02")
        t01 = (h.run_dir("T01") / "brief-author-0.md").read_text()
        self.assertIn("One note per finding, or per root cause?", t01)
        self.assertIn("One note per root cause.", t01)
        self.assertIn("Cite the pinned commit.", t01)
        t02 = (h.run_dir("T02") / "brief-author-0.md").read_text()
        self.assertNotIn("One note per root cause.", t02)   # T01's own decision stays with T01
        self.assertIn("Cite the pinned commit.", t02)
        p = h.kb / "architecture" / "overview.md"
        p.parent.mkdir(parents=True)
        p.write_text("# Overview\n\nSee [missing](nope.md).\n")
        h.result("T01", "author", changed=["architecture/overview.md"])
        h.tp("record", "T01", "--agent-id", "a1")
        h.tp("dispatch", "T01")                                 # a fix round to the same agent
        self.assertIn("One note per root cause.", (h.run_dir("T01") / "brief-fix-1.md").read_text())

    def test_an_answer_to_a_question_is_kept_for_later_briefs(self) -> None:
        h = self.h
        h.tp("dispatch", "T01")
        h.result("T01", "author", status="needs_input", questions=["Is kb/ markdown only?"])
        h.tp("record", "T01", "--agent-id", "a1")
        h.tp("resolve", "--task", "T01", "--action", "answer", "--answer", "Yes, markdown only.")
        p = h.kb / "architecture" / "overview.md"
        p.parent.mkdir(parents=True)
        p.write_text("# Overview\n\nSee [missing](nope.md).\n")
        h.result("T01", "author", changed=["architecture/overview.md"])
        h.tp("record", "T01")
        h.tp("dispatch", "T01")
        self.assertIn("Yes, markdown only.", (h.run_dir("T01") / "brief-fix-1.md").read_text())


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
        self.h.tp("exception", "--summary", "Merge notes that share a root cause?")
        self.h.tp("resolve", "--action", "answer", "--answer", "Yes, one note per root cause.")
        self.h.tp("dispatch", S1)
        brief = (self.h.wf / "runs" / "B1" / "brief-doc-reviewer-1.md").read_text()
        for needle in ("architecture/overview.md", "build/guide.md", "T01", "T02", "Do not edit",
                       "changes.json", "doc-reviewer-1.json", "Agent tool", "one note per root cause"):
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

    def fix_and_accept(self, tid: str, rel: str) -> None:
        h = self.h
        h.tp("dispatch", tid)
        h.good_article(rel)
        h.result(tid, "fix", changed=[rel])
        h.tp("record", tid)
        h.tp("accept", tid, "--note", "fixed")

    def test_a_fix_round_running_beside_a_review_is_not_a_reviewer_edit(self) -> None:
        # Seen live: B1's fix round wrote build/guide.md while B2's reviewer worked; recording B2
        # blamed the reviewer for it. The task-side gates already allow concurrent tasks' paths.
        h = self.h
        self.accept_all()
        h.tp("dispatch", S1, "B2/doc-reviewer")
        self.review(S1, 1, "changes", [self.finding("F1", "build/guide.md:3")])
        h.tp("record", S1)
        h.tp("triage", S1, "--accept-all")
        h.tp("dispatch", "T02")
        (h.kb / "build" / "guide.md").write_text("# Build\n\nFixed by T02's fix round.\n")
        self.review("B2/doc-reviewer", 1, "pass")
        out = h.tp("record", "B2/doc-reviewer").out
        self.assertNotIn("BLOCKED", out)
        self.assertEqual(h.state()["reviews"]["B2/doc-reviewer"]["status"], "done")

    def test_an_edit_no_concurrent_task_owns_still_blocks(self) -> None:
        h = self.h
        self.accept_all()
        h.tp("dispatch", S1)
        (h.kb / "stray.md").write_text("# Written during the review\n")
        self.review(S1, 1, "pass")
        self.assertIn("BLOCKED", h.tp("record", S1).out)
        self.assertEqual(h.state()["reviews"][S1]["status"], "blocked")

    def test_an_edit_block_holds_the_findings_until_cleared(self) -> None:
        # Seen live: accepting a false edit block marked the session done and silently dropped its
        # two valid blocking findings.
        h = self.h
        self.accept_all()
        h.tp("dispatch", S1)
        (h.kb / "stray.md").write_text("# Not the reviewer's\n")
        self.review(S1, 1, "changes", [self.finding("F1", "build/guide.md:3")])
        out = h.tp("record", S1).out
        self.assertIn("1 blocking", out)
        self.assertIn("--action clear", out)
        res = h.tp("resolve", "--review", S1, "--action", "accept", "--answer", "Not the reviewer.", expect=2)
        self.assertIn("F1", res.text)
        self.assertEqual(h.state()["reviews"][S1]["status"], "blocked")
        h.tp("resolve", "--review", S1, "--action", "clear", "--by", "manager",
             "--answer", "stray.md was written by the human, not the reviewer.")
        self.assertEqual(h.state()["reviews"][S1]["status"], "needs_triage")
        h.tp("triage", S1, "--accept-all")
        self.assertEqual(statuses(h)["T02"], "needs_fix")
        self.assertIn("· manager: stray.md", (h.wf / "decisions.md").read_text())

    def test_accept_with_force_ships_an_edit_block_without_its_findings(self) -> None:
        h = self.h
        self.accept_all()
        h.tp("dispatch", S1)
        (h.kb / "stray.md").write_text("# Stray\n")
        self.review(S1, 1, "changes", [self.finding("F1", "build/guide.md:3")])
        h.tp("record", S1)
        h.tp("resolve", "--review", S1, "--action", "accept", "--force", "--by", "human",
             "--answer", "Ship it.")
        self.assertEqual(h.state()["reviews"][S1]["status"], "done")

    def test_a_done_session_reopens_its_findings_and_verifies_them(self) -> None:
        # Seen live: findings recovered with a task-side reopen never reached the session's counts
        # or its verification round.
        h = self.h
        self.accept_all()
        h.tp("dispatch", S1)
        self.review(S1, 1, "changes", [self.finding("F1", "build/guide.md:3"),
                                       self.finding("F2", "architecture/overview.md:1", blocking=False)])
        h.tp("record", S1, "--agent-id", "rev-1")
        h.tp("triage", S1, "--dismiss", "F1", "--reason", "Looked fine at first.")
        self.assertEqual(h.state()["reviews"][S1]["status"], "done")
        out = h.tp("resolve", "--review", S1, "--action", "reopen", "--findings", "F1,F2", "--by", "manager",
                   "--answer", "F1 was dismissed by mistake; F2 matters too.").out
        self.assertIn("T02", out)
        self.assertEqual(statuses(h)["T02"], "needs_fix")
        self.assertEqual(statuses(h)["T01"], "needs_fix")
        s = h.state()["reviews"][S1]
        self.assertEqual((s["status"], s["accepted"], s["dismissed"]), ("waiting_fixes", ["F1", "F2"], {}))
        self.fix_and_accept("T01", "architecture/overview.md")
        self.fix_and_accept("T02", "build/guide.md")
        self.assertEqual(h.state()["tasks"]["T02"]["round"], 1)
        act = [a for a in h.next()["actions"] if a.get("id") == S1][0]
        self.assertEqual((act["action"], act["step"]), ("review", "verify"))
        h.tp("dispatch", S1)
        verify = (h.wf / "runs" / "B1" / "brief-doc-reviewer-2.md").read_text()
        self.assertIn("F1", verify)
        self.assertIn("F2", verify)

    def test_reopen_applies_only_to_done_sessions(self) -> None:
        h = self.h
        self.accept_all()
        h.tp("dispatch", S1)
        self.review(S1, 1, "changes", [self.finding("F1", "build/guide.md:3")])
        h.tp("record", S1)
        res = h.tp("resolve", "--review", S1, "--action", "reopen", "--findings", "F1", "--answer", "x", expect=2)
        self.assertIn("needs_triage", res.text)

    def test_more_findings_for_a_task_join_its_waiting_fix_round(self) -> None:
        # A second routing to a task whose fix round has not been dispatched must not replace the
        # first one's findings; one routed while its fix round runs is refused until it hands back.
        h = self.h
        self.accept_all()
        h.tp("dispatch", S1)
        self.review(S1, 1, "changes", [self.finding("F1", "build/guide.md:3")])
        h.tp("record", S1)
        h.tp("triage", S1, "--accept-all")
        h.tp("resolve", "--task", "T02", "--action", "reopen", "--answer", "Also link the overview.")
        ts = h.state()["tasks"]["T02"]
        self.assertEqual((ts["status"], ts["round"]), ("needs_fix", 1))
        h.tp("dispatch", "T02")
        brief = (h.run_dir("T02") / "brief-fix-1.md").read_text()
        self.assertIn("F1", brief)
        self.assertIn("Also link the overview.", brief)
        res = h.tp("resolve", "--task", "T02", "--action", "reopen", "--answer", "And more.", expect=2)
        self.assertIn("in flight", res.text)

    def test_report_attributes_rulings_only_as_recorded(self) -> None:
        h = self.h
        self.accept_all()
        h.tp("dispatch", S1)
        (h.kb / "stray.md").write_text("# Stray\n")
        self.review(S1, 1, "pass")
        h.tp("record", S1)
        h.tp("resolve", "--review", S1, "--action", "accept", "--by", "manager", "--answer", "Stray is mine.")
        (h.kb / "stray.md").unlink()
        h.tp("dispatch", "B2/doc-reviewer")
        self.review("B2/doc-reviewer", 1, "pass")
        h.tp("record", "B2/doc-reviewer")
        h.tp("final")
        report = (h.wf / "report.md").read_text()
        self.assertIn("accepted as is by the manager: Stray is mine.", report)
        self.assertNotIn("by the human", report)

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


ISO = re.compile(r'"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)"')


def elapse(h: Harness, minutes: int) -> None:
    """Pretend `minutes` pass: every timestamp the state holds moves that far into the past."""
    path = h.wf / ".tp" / "state.json"

    def back(m: "re.Match[str]") -> str:
        ts = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%SZ") - timedelta(minutes=minutes)
        return '"' + ts.strftime("%Y-%m-%dT%H:%M:%SZ") + '"'

    path.write_text(ISO.sub(back, path.read_text()))


class ClockTest(unittest.TestCase):
    """Seen live: 995 min of "execution" against a 240-min budget, for about 145 min of work — the
    clocks counted halts and hours spent waiting on the human as work."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def row(self, report: str, tid: str) -> list:
        return [c.strip() for c in next(ln for ln in report.splitlines() if ln.startswith(f"| {tid} ")).split("|")]

    def finish_others(self) -> None:
        h = self.h
        h.author("T02", "build/guide.md")
        h.tp("accept", "T02", "--note", "ok")
        h.tp("dispatch", "T03")
        (h.kb / "index.md").write_text("# KB\n\n- [O](architecture/overview.md)\n- [B](build/guide.md)\n")
        h.result("T03", "author", changed=["index.md"])
        h.tp("record", "T03")
        h.tp("accept", "T03", "--note", "ok")

    def test_waiting_on_the_human_is_not_counted_as_work(self) -> None:
        h = self.h
        h.tp("dispatch", "T01")
        elapse(h, 10)
        h.result("T01", "author", status="needs_input", questions=["Which style?"])
        h.tp("record", "T01", "--agent-id", "a1")
        elapse(h, 120)                                   # two hours until the human answers
        h.tp("resolve", "--task", "T01", "--action", "answer", "--answer", "House style.")
        elapse(h, 5)
        h.good_article("architecture/overview.md")
        h.result("T01", "author", changed=["architecture/overview.md"])
        h.tp("record", "T01")
        self.assertIn("(15 min", h.tp("accept", "T01", "--note", "ok").out)
        self.finish_others()
        h.tp("final")
        report = (h.wf / "report.md").read_text()
        cols = self.row(report, "T01")
        self.assertEqual((cols[4], cols[5]), ("15", "15"))  # active, agent
        self.assertIn("execution took 135 min wall-clock: 15 min of work and 120 min halted or waiting "
                      "on the human", report)
        self.assertIn("Agents worked 15 min", report)

    def test_a_halt_is_not_counted_as_work(self) -> None:
        h = self.h
        h.tp("halt", "--reason", "Overnight.")
        elapse(h, 600)
        h.tp("resume", "--answer", "Morning.")
        self.assertIn("600 min halted or waiting", h.tp("report").out)

    def test_an_accepted_task_waiting_for_review_findings_is_not_working(self) -> None:
        h = Harness()
        try:
            h.approved(plan=h.plan([h.task("T01", "a.md")], final_checks=[]), **FINAL_REVIEW)
            h.author("T01", "a.md")
            h.tp("accept", "T01", "--note", "ok")
            h.tp("dispatch", "B1/doc-reviewer")
            elapse(h, 30)                                # the review runs; T01 is done meanwhile
            (h.wf / "runs" / "B1").mkdir(parents=True, exist_ok=True)
            (h.wf / "runs" / "B1" / "doc-reviewer-1.json").write_text(json.dumps({"batch": "B1", "verdict": "changes",
                "findings": [{"id": "F1", "state": "wrong", "blocking": True, "where": "a.md:3", "issue": "Wrong."}]}))
            h.tp("record", "B1/doc-reviewer")
            h.tp("triage", "B1/doc-reviewer", "--accept-all")
            h.tp("dispatch", "T01")
            elapse(h, 4)
            h.good_article("a.md")
            h.result("T01", "fix", changed=["a.md"])
            h.tp("record", "T01")
            self.assertIn("(4 min", h.tp("accept", "T01", "--note", "ok").out)
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

    def test_a_session_blocked_by_the_previous_version_resolves_as_before(self) -> None:
        # Its block has no kind: it reads as blocked after verification, so accept ships it as is.
        h = Harness()
        try:
            h.approved(plan=h.plan([h.task("T01", "a.md")], final_checks=[]), **FINAL_REVIEW)
            path = h.wf / ".tp" / "state.json"
            state = json.loads(path.read_text())
            state["reviews"]["B1/doc-reviewer"].update(status="blocked", summary="the reviewer edited a.md", findings=[
                {"id": "F1", "state": "wrong", "blocking": True, "where": "a.md:1", "issue": "x", "task": "T01"}])
            path.write_text(json.dumps(state))
            h.tp("resolve", "--review", "B1/doc-reviewer", "--action", "clear", "--answer", "x", expect=2)
            h.tp("resolve", "--review", "B1/doc-reviewer", "--action", "accept", "--answer", "Ship it.")
            self.assertEqual(h.state()["reviews"]["B1/doc-reviewer"]["status"], "done")
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
