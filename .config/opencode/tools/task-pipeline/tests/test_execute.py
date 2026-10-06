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
        self.assertIn("`task` tool", brief)           # no sub-agent fan-out
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
        self.assertIn("task(task_id=\"agent-77\"", out)          # the fix goes to the same agent's session
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


class WfRootWorkspaceTest(unittest.TestCase):
    """A task whose write workspace IS the workflow root — e.g. a Jira-filing pipeline
    whose only local deliverables are small record files. The record and review gates
    must blame an agent only for its own stray writes there, never for tp.py's own
    bookkeeping: the briefs, snapshots and mandated result files under runs/, noticed.md
    appends written from the result's own `noticed` list during record, or plan.json,
    plan.approved.json and decisions.md rewritten by the manager's `tp amend` mid-flight.
    (Seen live: every task of a 15-bug Jira filing took a spurious fix round 'reverting'
    files its agent never touched, and all three review sessions blocked on their own
    protocol artifacts.)"""

    def setUp(self) -> None:
        self.h = h = Harness()
        h.init()   # sets h.wf; the workflow root is also the tasks' write workspace below
        self._confirm(review="none", tasks=["T01", "T02"])

    def _confirm(self, review, tasks, batches=None) -> None:
        h = self.h
        participants = [{"agent": "kb-author", "role": "author", "why": "Writes every record for D1."}]
        if review != "none":
            participants.append({"agent": "doc-reviewer", "role": "reviewer",
                                  "why": "Reviews the records."})
        h.write_json("scope.json", h.scope(
            workspaces=[{"name": "flow", "path": str(h.wf), "mode": "write"},
                        {"name": "src", "path": str(h.src), "mode": "read"}],
            review=review, participants=participants))
        h.tp("scope", "check")
        h.tp("scope", "confirm", "--answer", "confirmed")
        plan = h.plan(tasks=[h.task(t, f"out/{t.lower()}.md", workspace="flow", checks=[]) for t in tasks],
                      **({"review_batches": batches} if batches else {}))
        h.write_json("plan.json", plan)
        h.tp("plan", "check")
        h.tp("plan", "submit")
        h.tp("approve", "--answer", "approve")

    def tearDown(self) -> None:
        self.h.close()

    def hand_back(self, tid: str, rel: str, noticed=()):
        h = self.h
        out = h.wf / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f"# {tid}\n\n`Add` returns the sum (`calc/calc.go:5`).\n")
        h.result(tid, "author", changed=[rel], noticed=list(noticed))
        return h.tp("record", tid, "--agent-id", "a1")

    def test_the_agents_own_result_file_and_noticed_list_are_not_blamed(self) -> None:
        # runs/T01/result-author.json is the file the brief mandates; noticed.md is written
        # by `tp record` itself, from this result's `noticed` list, before the gate diff.
        h = self.h
        h.tp("dispatch", "T01")
        out = self.hand_back("T01", "out/t01.md", noticed=["calc has no tests."]).out
        self.assertEqual(statuses(h)["T01"], "needs_check")
        self.assertIn("calc has no tests.", (h.wf / "noticed.md").read_text())

    def test_concurrent_dispatch_artifacts_are_not_blamed(self) -> None:
        # Dispatching T02 while T01 works writes runs/T02/brief-*.md and snap-*.json
        # after T01's baseline snapshot: tp's own artifacts, not T01's agent's edits.
        h = self.h
        h.tp("dispatch", "T01", "T02")
        self.hand_back("T01", "out/t01.md")
        self.assertEqual(statuses(h)["T01"], "needs_check")

    def test_a_manager_amend_mid_flight_is_not_blamed_on_the_agent(self) -> None:
        # `tp amend` rewrites plan.json, plan.approved.json and decisions.md while the
        # task is in flight; the fix brief it spawned told the agent to revert them.
        h = self.h
        h.tp("dispatch", "T01")
        plan = h.read_json("plan.json")
        plan["tasks"][0]["brief"] += " Also note the build command."
        h.write_json("plan.json", plan)
        h.tp("amend", "--reason", "One more line in the brief.")
        self.hand_back("T01", "out/t01.md")
        self.assertEqual(statuses(h)["T01"], "needs_check")

    def test_a_stray_agent_write_in_the_workspace_is_still_flagged(self) -> None:
        # The gate keeps its teeth: an agent write no plan path covers still fails.
        h = self.h
        h.tp("dispatch", "T01")
        (h.wf / "evil.md").write_text("not mine to write\n")
        out = self.hand_back("T01", "out/t01.md").out
        self.assertIn("evil.md", out)
        self.assertEqual(statuses(h)["T01"], "needs_fix")


class WfRootReviewTest(unittest.TestCase):
    """Review gates where the task workspace is the workflow root: the session's own
    protocol artifacts (its mandated result file under runs/, the dispatch's
    changes.json, noticed.md written from the review's own `noticed` list) must not
    read as the reviewer editing the deliverables. (Seen live: three review sessions
    blocked with 'files changed while the reviewer worked' — every flagged file
    tp's own.)"""

    def _workflow(self, review: str, batches=None) -> Harness:
        h = Harness()
        h.init()
        participants = [
            {"agent": "kb-author", "role": "author", "why": "Writes every record for D1."},
            {"agent": "doc-reviewer", "role": "reviewer", "why": "Reviews the records."}]
        h.write_json("scope.json", h.scope(
            review=review, participants=participants,
            workspaces=[{"name": "flow", "path": str(h.wf), "mode": "write"},
                        {"name": "src", "path": str(h.src), "mode": "read"}]))
        h.tp("scope", "check")
        h.tp("scope", "confirm", "--answer", "confirmed")
        plan = h.plan(tasks=[h.task("T01", "out/t01.md", workspace="flow", checks=[])],
                      **({"review_batches": batches} if batches else {}))
        h.write_json("plan.json", plan)
        h.tp("plan", "check")
        h.tp("plan", "submit")
        h.tp("approve", "--answer", "approve")
        return h

    def test_a_batch_session_records_clean_despite_its_own_protocol_files(self) -> None:
        h = self._workflow("final", batches=[{"id": "B1", "tasks": ["T01"]}])
        try:
            h.tp("dispatch", "T01")
            out = h.wf / "out" / "t01.md"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("# T01\n\n`Add` returns the sum (`calc/calc.go:5`).\n")
            h.result("T01", "author", changed=["out/t01.md"])
            h.tp("record", "T01", "--agent-id", "a1")
            h.tp("accept", "T01", "--note", "ok")
            h.tp("dispatch", "B1/doc-reviewer")
            d = h.wf / "runs" / "B1"
            d.mkdir(parents=True, exist_ok=True)
            (d / "doc-reviewer-1.json").write_text(json.dumps(
                {"batch": "B1", "verdict": "pass", "findings": [],
                 "noticed": ["The out/ records lack an index."]}))
            res = h.tp("record", "B1/doc-reviewer", "--agent-id", "rev-1").out
            self.assertNotIn("files changed while the reviewer worked", res)
            self.assertEqual(h.state()["reviews"]["B1/doc-reviewer"]["status"], "done")
            self.assertIn("The out/ records lack an index.", (h.wf / "noticed.md").read_text())
        finally:
            h.close()

    def test_a_per_task_review_step_records_clean(self) -> None:
        h = self._workflow("per-task")
        try:
            h.tp("dispatch", "T01")
            out = h.wf / "out" / "t01.md"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("# T01\n\n`Add` returns the sum (`calc/calc.go:5`).\n")
            h.result("T01", "author", changed=["out/t01.md"])
            h.tp("record", "T01", "--agent-id", "a1")
            self.assertEqual(statuses(h)["T01"], "needs_review")
            h.tp("dispatch", "T01")
            d = h.run_dir("T01")
            d.mkdir(parents=True, exist_ok=True)
            (d / "review-1.json").write_text(json.dumps(
                {"task": "T01", "verdict": "pass", "findings": [],
                 "noticed": ["The out/ records lack an index."]}))
            res = h.tp("record", "T01", "--agent-id", "rev-1").out
            self.assertNotIn("The reviewer changed", res)
            self.assertEqual(statuses(h)["T01"], "needs_check")
        finally:
            h.close()


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
                       "changes.json", "doc-reviewer-1.json", "`task` tool"):
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
        self.assertIn("task(task_id=\"rev-1\"", out)              # verification: the same reviewer's session
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

    def test_final_does_not_block_on_a_readme_rooted_workspace_with_orphans(self) -> None:
        # A code repo's README is an entry page, not a nav index: it legitimately links to
        # none of the internal notes, ADRs, or sub-READMEs the tree carries. An orphan next
        # to a README warns; only a deliberate index.md makes reachability blocking.
        h = self.h
        try:
            h.approved(plan=h.plan([h.task("T01", "notes/design.md", checks=[])],
                                   final_checks=["docs-all"]))
            (h.kb / "README.md").write_text("# kb\n\nEntry page only, no nav.\n")
            h.author("T01", "notes/design.md")
            h.tp("accept", "T01", "--note", "ok")
            h.tp("final")
            log = (h.wf / ".tp" / "final-docs-all.log").read_text()
            self.assertIn("WARN", log)
            self.assertIn("notes/design.md", log)
            self.assertIn("not reachable", log)
        finally:
            h.close()

    def test_final_still_blocks_on_a_readme_rooted_workspace_with_a_broken_link(self) -> None:
        h = self.h
        try:
            h.approved(plan=h.plan([h.task("T01", "notes/design.md", checks=[])],
                                   final_checks=["docs-all"]))
            (h.kb / "README.md").write_text("# kb\n\n- [gone](missing.md)\n")
            h.author("T01", "notes/design.md")
            h.tp("accept", "T01", "--note", "ok")
            res = h.tp("final", expect=2)
            self.assertIn("broken link", res.text)
        finally:
            h.close()

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

    def test_star_star_glob_covers_root_level_files(self) -> None:
        # Seen live, twice: a task declaring paths ["**/*.md"] that edits the root index.md was
        # FAILed as "changed files outside this task's paths" — pathlib's ** does not match
        # files at the root, so the record gate rejected exactly the files the brief asked for.
        h = Harness()
        try:
            h.approved(plan=h.plan([h.task("T01", "**/*.md", checks=[],
                                           brief="Write every article including the root index.")]))
            h.tp("dispatch", "T01")
            sub = h.kb / "sub"
            sub.mkdir()
            (sub / "a.md").write_text("A\n")
            (h.kb / "index.md").write_text("# index\n")
            h.result("T01", "author", changed=["sub/a.md", "index.md"])
            out = h.tp("record", "T01", "--agent-id", "a1").out
            self.assertNotIn("outside this task's paths", out)
            self.assertIn("passed its checks", out)
        finally:
            h.close()

    def test_star_star_glob_does_not_widen_to_other_files(self) -> None:
        # The de-noising must not hide genuine scope violations: a root file NOT covered by the
        # pattern's extension is still outside the task's paths.
        h = Harness()
        try:
            h.approved(plan=h.plan([h.task("T01", "**/*.md", checks=[])]))
            h.tp("dispatch", "T01")
            (h.kb / "a.md").write_text("A\n")
            (h.kb / "stray.txt").write_text("not markdown\n")
            h.result("T01", "author", changed=["a.md", "stray.txt"])
            out = h.tp("record", "T01", "--agent-id", "a1", expect=0).out
            self.assertIn("outside this task's paths", out)
            self.assertIn("stray.txt", out)
        finally:
            h.close()


if __name__ == "__main__":
    unittest.main()


class TrimSummaryTest(unittest.TestCase):
    """A mechanical result rejection (over-long summary) costs an agent round-trip; the
    manager may instead trim it on record — nothing else in the result may change."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved(plan=self.h.plan([self.h.task("T01", "a.md", checks=[])]))

    def tearDown(self) -> None:
        self.h.close()

    def test_trim_summary_records_instead_of_failing(self) -> None:
        self.h.tp("dispatch", "T01")
        (self.h.kb / "a.md").write_text("x\n")
        long_summary = " ".join(f"word{i}" for i in range(120))
        self.h.result("T01", "author", summary=long_summary, changed=["a.md"])
        out = self.h.tp("record", "T01", "--agent-id", "a1", "--trim-summary").out
        self.assertIn("passed its checks", out)
        data = json.loads((self.h.run_dir("T01") / "result-author.json").read_text())
        self.assertLessEqual(len(data["summary"].split()), 80)
        self.assertEqual(data["changed"], ["a.md"])
        self.assertEqual(data["status"], "done")

    def test_without_trim_the_rejection_stands(self) -> None:
        self.h.tp("dispatch", "T01")
        (self.h.kb / "a.md").write_text("x\n")
        self.h.result("T01", "author", summary="word " * 82, changed=["a.md"])
        res = self.h.tp("record", "T01", "--agent-id", "a1", expect=2)
        self.assertIn("summary is 82 words", res.text)
        data = json.loads((self.h.run_dir("T01") / "result-author.json").read_text())
        self.assertEqual(data["summary"], "word " * 82)


class NoticedResolveTest(unittest.TestCase):
    """Noticed items stay open until the human settles them; `tp resolve --noticed N`
    records the decision and the item stops appearing in submit output and reports."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.confirmed()

    def tearDown(self) -> None:
        self.h.close()

    def test_resolved_item_leaves_the_open_list(self) -> None:
        self.h.tp("note", "The README's build section is stale.")
        self.h.tp("note", "An id may need reassignment on import.")
        listed = self.h.tp("noticed").out
        self.assertIn("README's build section", listed)
        self.h.tp("resolve", "--noticed", "1", "--action", "answer",
                  "--answer", "Checked against the code; it is correct.")
        open_items = self.h.tp("noticed").out
        self.assertNotIn("README's build section", open_items)
        self.assertIn("id may need reassignment", open_items)
        text = (self.h.wf / "noticed.md").read_text()
        self.assertIn("RESOLVED: Checked against the code", text)

    def test_resolved_item_does_not_block_submit_output(self) -> None:
        self.h.tp("note", "A stale observation.")
        self.h.tp("resolve", "--noticed", "1", "--action", "answer", "--answer", "settled")
        self.h.write_json("plan.json", self.h.plan())
        out = self.h.tp("plan", "submit").out
        self.assertNotIn("A stale observation", out)

    def test_bad_index_is_refused(self) -> None:
        self.h.tp("resolve", "--noticed", "4", "--action", "answer", "--answer", "x", expect=2)


class ExceptionResolveTest(unittest.TestCase):
    """A workflow-level exception resolves with --exception instead of --task, so one
    human decision does not need two command shapes."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved(plan=self.h.plan([self.h.task("T01", "a.md", checks=[])]))

    def tearDown(self) -> None:
        self.h.close()

    def test_workflow_exception_resolves_with_the_exception_flag(self) -> None:
        self.h.tp("exception", "--summary", "the final check count is stale")
        self.assertIn("BLOCKED", self.h.tp("status").out)
        self.h.tp("resolve", "--exception", "--action", "answer", "--answer", "31 is correct; update the check")
        out = self.h.tp("status").out
        self.assertNotIn("BLOCKED", out)
        self.assertNotIn("HALT", out)

    def test_exception_flag_without_a_block_is_refused(self) -> None:
        self.h.tp("resolve", "--exception", "--action", "answer", "--answer", "x", expect=2)


class ExceptionRetryTest(unittest.TestCase):
    """A task-level exception block accepts retry: the human's answer goes in the decision
    log and the task returns to a fix round without a second resolve call."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved(plan=self.h.plan([self.h.task("T01", "a.md", checks=[])]))

    def tearDown(self) -> None:
        self.h.close()

    def _raise_task_exception(self) -> None:
        self.h.tp("dispatch", "T01")
        (self.h.kb / "a.md").write_text("x\n")
        self.h.result("T01", "author", changed=["a.md"])
        self.h.tp("record", "T01", "--agent-id", "a1")
        self.h.tp("exception", "--summary", "final check count is stale", "--task", "T01")

    def test_retry_returns_the_task_to_a_fix_round(self) -> None:
        self._raise_task_exception()
        self.h.tp("resolve", "--task", "T01", "--action", "retry", "--answer", "31 is correct")
        st = self.h.state()["tasks"]["T01"]
        self.assertEqual(st["status"], "needs_fix")
        self.assertIsNone(st["blocked"])

    def test_answer_still_works_for_an_exception_block(self) -> None:
        self._raise_task_exception()
        self.h.tp("resolve", "--task", "T01", "--action", "answer", "--answer", "no change needed")
        self.assertIn(self.h.state()["tasks"]["T01"]["status"], ("needs_check", "accepted"))


class HumanWaitCreditTest(unittest.TestCase):
    """An agent blocked on a permission prompt or a human question does not do work while
    it waits: the human's delay must not bill against the task's budget. The manager sees
    the delay and credits it at record time — the meter is never responsible for the
    human's response time. (40-min task, prompt at 20, human answers in 20: 20 min left.)"""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved(plan=self.h.plan([self.h.task("T01", "a.md", checks=[])]))

    def tearDown(self) -> None:
        self.h.close()

    def _dispatch_and_backdate(self, minutes: float) -> None:
        import json as _json
        from datetime import datetime, timedelta, timezone
        self.h.tp("dispatch", "T01")
        sp = self.h.wf / ".tp" / "state.json"
        st = _json.loads(sp.read_text())
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        st["in_flight"]["T01"]["since"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        sp.write_text(_json.dumps(st))
        (self.h.kb / "a.md").write_text("x\n")
        self.h.result("T01", "author", changed=["a.md"])

    def test_credit_deducts_the_human_wait(self) -> None:
        # Simulate: dispatched 20 min ago, but the agent only worked ~0 min of that
        # because a permission prompt sat waiting for the human.
        self._dispatch_and_backdate(minutes=20)
        out = self.h.tp("record", "T01", "--agent-id", "a1", "--credit", "20").out
        self.assertIn("human-wait", out)
        self.assertLessEqual(self.h.state()["agent_minutes"], 1.0)

    def test_partial_credit_leaves_the_worked_minutes(self) -> None:
        # 40-min window, 20 min waiting on the human: 20 billed, 20 left.
        self._dispatch_and_backdate(minutes=40)
        self.h.tp("record", "T01", "--agent-id", "a1", "--credit", "20")
        spent = self.h.state()["agent_minutes"]
        self.assertGreaterEqual(spent, 18.0)
        self.assertLessEqual(spent, 22.0)

    def test_without_credit_the_full_window_bills(self) -> None:
        self._dispatch_and_backdate(minutes=20)
        self.h.tp("record", "T01", "--agent-id", "a1")
        self.assertGreaterEqual(self.h.state()["agent_minutes"], 19.0)

    def test_credit_floors_at_zero_and_is_audited(self) -> None:
        self._dispatch_and_backdate(minutes=20)
        self.h.tp("record", "T01", "--agent-id", "a1", "--credit", "999")
        self.assertEqual(self.h.state()["agent_minutes"], 0.0)
        events = [json.loads(ln) for ln in (self.h.wf / ".tp" / "events.jsonl").read_text().splitlines()]
        credits = [e for e in events if e["kind"] == "credit"]
        self.assertEqual(len(credits), 1)
        self.assertLessEqual(credits[0]["minutes"], 20.0)

    def test_credit_needs_no_flag_and_defaults_to_zero(self) -> None:
        self._dispatch_and_backdate(minutes=5)
        self.h.tp("record", "T01", "--agent-id", "a1")
        self.assertGreaterEqual(self.h.state()["agent_minutes"], 4.0)


class DecisionsTravelTest(unittest.TestCase):
    """Seen live twice: an answer given mid-run (the README must not be pinned; the final
    check's count must change) reached later fix rounds only because the manager restated it
    in resume prompts by hand. Decisions made during the run must travel: every later brief
    for the work they settle quotes them, and they win over the brief where they differ."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved(plan=self.h.plan([
            self.h.task("T01", "a.md", checks=[], reviewer="doc-reviewer",
                        brief="Write the article at a.md. Pin its front matter like the index."),
            self.h.task("T02", "b.md", depends_on=["T01"]),
        ]), review="per-task",
           participants=[{"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."},
                         {"agent": "doc-reviewer", "role": "reviewer", "why": "Reviews D1's KB articles."}])

    def tearDown(self) -> None:
        self.h.close()

    def test_task_answer_reaches_the_fix_round_brief(self) -> None:
        # A rejected review opens a fix round; the answer given while blocked (needs_input)
        # must appear in that fix brief and settle its question.
        h = self.h
        h.tp("dispatch", "T01")
        h.result("T01", "author", status="blocked", summary="Stuck on the pin question",
                 questions=["Should a.md carry a pin?"])
        h.tp("record", "T01", "--agent-id", "a1")
        h.tp("resolve", "--task", "T01", "--action", "answer", "--answer", "No pin: it is meta-documentation.")
        # resolve --action answer resumes the author in flight: finish the author round
        h.good_article("a.md")
        h.result("T01", "author", changed=["a.md"])
        h.tp("record", "T01", "--agent-id", "a1")
        # task review with a blocking finding opens the fix round
        h.tp("dispatch", "T01")
        (h.run_dir("T01") / "review-1.json").write_text(json.dumps({"task": "T01", "verdict": "changes",
            "findings": [{"id": "F1", "blocking": True, "where": "a.md:1", "state": "wrong",
                          "issue": "the pin paragraph is wrong", "task": "T01"}]}))
        h.tp("record", "T01", "--agent-id", "rev-1")
        h.tp("dispatch", "T01")  # the fix round's brief is written at dispatch
        brief = (h.run_dir("T01") / "brief-fix-1.md").read_text()
        self.assertIn("No pin: it is meta-documentation", brief)
        self.assertIn("Should a.md carry a pin?", brief)

    def test_workflow_answer_reaches_every_brief(self) -> None:
        h = self.h
        h.tp("exception", "--summary", "the est column means estimate")
        h.tp("resolve", "--exception", "--action", "answer", "--answer", "31 is correct; update the check.")
        h.tp("dispatch", "T01")
        brief = (h.run_dir("T01") / "brief-author-0.md").read_text()
        self.assertIn("31 is correct", brief)

    def test_decisions_win_over_the_brief(self) -> None:
        h = self.h
        h.tp("exception", "--summary", "brief says pin; human says unpinned")
        h.tp("resolve", "--exception", "--action", "answer", "--answer", "a.md stays unpinned.")
        h.tp("dispatch", "T01")
        brief = (h.run_dir("T01") / "brief-author-0.md").read_text()
        pin_pos, dec_pos = brief.find("Pin its front matter"), brief.find("a.md stays unpinned")
        self.assertLess(pin_pos, dec_pos)  # the decision appears after, with precedence stated

    def test_reviewer_brief_carries_the_decisions_too(self) -> None:
        h = self.h
        h.tp("dispatch", "T01")
        h.good_article("a.md")
        h.result("T01", "author", changed=["a.md"])
        h.tp("record", "T01", "--agent-id", "a1")
        h.tp("exception", "--summary", "flag style")
        h.tp("resolve", "--exception", "--action", "answer", "--answer", "Tables beat prose for enums.")
        h.tp("dispatch", "T01")  # the task review brief
        brief = (h.run_dir("T01") / "brief-review-1.md").read_text()
        self.assertIn("Tables beat prose for enums", brief)

    def test_decisions_do_not_leak_between_tasks(self) -> None:
        # A task-level decision stays on its task; the workflow-level context carries only
        # workflow decisions. T02's brief must not quote T01's decision.
        h = self.h
        h.tp("dispatch", "T01")
        h.result("T01", "author", status="blocked", summary="Stuck", questions=["T01-only question?"])
        h.tp("record", "T01", "--agent-id", "a1")
        h.tp("resolve", "--task", "T01", "--action", "answer", "--answer", "Only for T01.")
        # The block resolves by resuming the author in flight; complete the round
        h.good_article("a.md")
        h.result("T01", "author", changed=["a.md"])
        h.tp("record", "T01", "--agent-id", "a1")
        # task review (per-task reviewer) with a blocking finding → T01 into a fix round
        h.tp("dispatch", "T01")
        (h.run_dir("T01") / "review-1.json").write_text(json.dumps({"task": "T01", "verdict": "changes",
            "findings": [{"id": "F1", "blocking": True, "where": "a.md:1", "state": "wrong",
                          "issue": "the pin paragraph contradicts the decision", "task": "T01"}]}))
        h.tp("record", "T01", "--agent-id", "rev-1")
        h.tp("dispatch", "T01")  # the fix brief
        self.assertIn("Only for T01", (h.run_dir("T01") / "brief-fix-1.md").read_text())
        # T02 (different task, no decisions of its own) must not see T01's decision
        h.good_article("a.md")
        h.result("T01", "fix", changed=["a.md"])
        h.tp("record", "T01", "--agent-id", "a1")
        h.tp("dispatch", "T01")  # review round 2 (verify the fix)
        (h.run_dir("T01") / "review-2.json").write_text(json.dumps({"task": "T01", "verdict": "pass",
                                                                    "findings": []}))
        h.tp("record", "T01", "--agent-id", "rev-1")
        h.tp("accept", "T01", "--note", "ok")
        h.tp("dispatch", "T02")
        self.assertNotIn("Only for T01", (h.run_dir("T02") / "brief-author-0.md").read_text())


class ReviewEditsHeldTest(unittest.TestCase):
    """Seen live: a reviewer session that blocked on unexpected file edits discarded its
    blocking findings — the manager had to choose between losing them and hand-copying.
    An edit block now holds the findings: clear (not the reviewer's) or accept --force (ship
    without them) decide them; accept without --force refuses while findings are held."""

    def setUp(self) -> None:
        self.h = h = Harness()
        plan = h.plan(review_batches=[{"id": "B1", "tasks": ["T01", "T02"]}])
        plan["tasks"] = [t for t in plan["tasks"] if t["id"] != "T03"]  # the default plan's T03 leaves the batch
        h.approved(plan=plan, **FINAL_REVIEW)
        # finish every task so the batch review can dispatch
        for tid, rel in (("T01", "architecture/overview.md"), ("T02", "build/guide.md")):
            h.author(tid, rel)
            h.tp("accept", tid, "--note", "ok")

    def tearDown(self) -> None:
        self.h.close()

    def _review_with_edits(self) -> None:
        h = self.h
        h.tp("dispatch", S1)
        d = h.wf / "runs" / "B1"
        (d / "doc-reviewer-1.json").write_text(json.dumps(
            {"batch": "B1", "verdict": "changes",
             "findings": [{"id": "F1", "blocking": True, "task": "T01", "state": "wrong",
                           "where": "kb/architecture/overview.md:1", "issue": "the intro overstates the pin"}]}))
        # a file nobody's task owns appears while the reviewer runs
        (h.kb / "stray.md").write_text("stray\n")
        h.tp("record", S1, "--agent-id", "rev-1")

    def test_edit_block_holds_the_findings(self) -> None:
        self._review_with_edits()
        st = self.h.state()["reviews"]["B1/doc-reviewer"]
        self.assertEqual(st["status"], "blocked")
        self.assertEqual(st["block"], "edits")
        self.assertEqual([f["id"] for f in st["findings"] if f["blocking"]], ["F1"])

    def test_clear_resumes_the_findings(self) -> None:
        self._review_with_edits()
        out = self.h.tp("resolve", "--review", "B1/doc-reviewer", "--action", "clear",
                        "--answer", "the stray file was the manager's check scratch").out
        st = self.h.state()["reviews"]["B1/doc-reviewer"]
        self.assertEqual(st["status"], "needs_triage")
        self.assertIn("F1", out)

    def test_accept_without_force_refuses_while_findings_are_held(self) -> None:
        self._review_with_edits()
        res = self.h.tp("resolve", "--review", "B1/doc-reviewer", "--action", "accept",
                        "--answer", "ship it", expect=2)
        self.assertIn("--force", res.text)

    def test_accept_with_force_ships_and_records_the_decision(self) -> None:
        self._review_with_edits()
        self.h.tp("resolve", "--review", "B1/doc-reviewer", "--action", "accept", "--force",
                  "--answer", "ship without F1 — the stray file is unrelated")
        st = self.h.state()["reviews"]["B1/doc-reviewer"]
        self.assertEqual(st["status"], "done")
        self.assertIn("ship without F1", (self.h.wf / "decisions.md").read_text())


class ByAttributionTest(unittest.TestCase):
    """decisions.md records every resolve identically, so the live log could not tell a ruling
    the human made from one the manager made interpreting them. `--by human|manager` attributes
    it — and where it is left out, the record attributes nobody."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved(plan=self.h.plan([self.h.task("T01", "a.md", checks=[])]))

    def tearDown(self) -> None:
        self.h.close()

    def test_by_human_records_the_attribution(self) -> None:
        self.h.tp("exception", "--summary", "the count is stale")
        self.h.tp("resolve", "--exception", "--action", "answer", "--by", "human",
                  "--answer", "31 is correct.")
        text = (self.h.wf / "decisions.md").read_text()
        self.assertIn("human: 31 is correct", text)

    def test_by_manager_records_the_attribution(self) -> None:
        self.h.tp("exception", "--summary", "the count is stale")
        self.h.tp("resolve", "--exception", "--action", "answer", "--by", "manager",
                  "--answer", "same count per the brief.")
        self.assertIn("manager: same count", (self.h.wf / "decisions.md").read_text())

    def test_without_by_nobody_is_attributed(self) -> None:
        self.h.tp("exception", "--summary", "the count is stale")
        self.h.tp("resolve", "--exception", "--action", "answer", "--answer", "fine as is.")
        line = next(ln for ln in (self.h.wf / "decisions.md").read_text().splitlines() if "fine as is" in ln)
        self.assertNotIn("human:", line)
        self.assertNotIn("manager:", line)


class ReviewReopenTest(unittest.TestCase):
    """A done review session's dismissed or non-blocking findings are unreachable when the human
    re-judges one later: reopen sends named findings back to their owning authors and puts the
    session back into waiting_fixes for a verification round."""

    def setUp(self) -> None:
        self.h = h = Harness()
        plan = h.plan(review_batches=[{"id": "B1", "tasks": ["T01", "T02"]}])
        plan["tasks"] = [t for t in plan["tasks"] if t["id"] != "T03"]
        h.approved(plan=plan, **FINAL_REVIEW)
        for tid, rel in (("T01", "architecture/overview.md"), ("T02", "build/guide.md")):
            h.author(tid, rel)
            h.tp("accept", tid, "--note", "ok")

    def tearDown(self) -> None:
        self.h.close()

    def _done_session_with_a_dismissed_finding(self) -> None:
        h = self.h
        h.tp("dispatch", S1)
        d = h.wf / "runs" / "B1"
        (d / "doc-reviewer-1.json").write_text(json.dumps(
            {"batch": "B1", "verdict": "changes",
             "findings": [{"id": "F1", "blocking": True, "task": "T01", "state": "wrong",
                           "where": "kb/architecture/overview.md:2", "issue": "the wording is loose"}]}))
        h.tp("record", S1, "--agent-id", "rev-1")
        h.tp("triage", S1, "--dismiss", "F1", "--reason", "cosmetic; the wording is fine")  # session done

    def test_reopen_sends_findings_back_to_their_owners(self) -> None:
        h = self.h
        self._done_session_with_a_dismissed_finding()
        if h.state()["reviews"][S1]["status"] != "done":
            h.tp("triage", S1, "--accept-all")  # or dismiss all: settle to done
            # --accept-all with no blocking findings: nothing accepted; session done
        st = h.state()["reviews"][S1]
        self.assertEqual(st["status"], "done")
        h.tp("resolve", "--review", S1, "--action", "reopen", "--findings", "F1",
             "--answer", "on reflection the wording matters — fix it")
        st = h.state()["reviews"][S1]
        self.assertEqual(st["status"], "waiting_fixes")
        self.assertIn("T01", st["fix_tasks"])
        ts = h.state()["tasks"]["T01"]
        self.assertEqual(ts["status"], "needs_fix")

    def test_reopen_needs_findings_and_a_done_session(self) -> None:
        h = self.h
        self._done_session_with_a_dismissed_finding()
        h.tp("resolve", "--review", S1, "--action", "reopen", "--answer", "x", expect=2)
