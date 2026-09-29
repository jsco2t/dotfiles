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

    def test_at_most_two_in_flight(self) -> None:
        h = Harness()
        try:
            h.approved(plan=h.plan([h.task(f"T0{i}", f"a{i}.md") for i in range(1, 4)]))
            h.tp("dispatch", "T01")
            h.tp("dispatch", "T02")
            self.assertEqual([a for a in h.next()["actions"] if a["action"] == "dispatch"], [])
            self.assertIn("2 agents", h.tp("dispatch", "T03", expect=2).text)
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
        self.assertIn("orch-result", brief)          # names what it replaces
        self.assertIn("Point first", brief)           # answer-first core, inlined
        self.assertIn("Agent tool", brief)            # no sub-agent fan-out
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


class FinalReviewTest(unittest.TestCase):
    def test_whole_package_review_runs_before_final(self) -> None:
        h = Harness()
        try:
            h.approved(plan=h.plan([h.task("T01", "index.md", checks=[])]), review="final", participants=[
                {"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."},
                {"agent": "doc-reviewer", "role": "reviewer", "why": "Reviews the finished KB as a whole."}])
            h.tp("dispatch", "T01")
            (h.kb / "index.md").write_text("# KB\n")
            h.result("T01", "author", changed=["index.md"])
            h.tp("record", "T01")
            self.assertEqual(statuses(h)["T01"], "needs_check")   # final-only review: no per-task review
            h.tp("accept", "T01", "--note", "ok")
            act = h.next()["actions"][0]
            self.assertEqual((act["action"], act["id"]), ("review", "FINAL"))
            h.tp("final", expect=2)
            h.tp("dispatch", "FINAL")
            (h.wf / "runs" / "FINAL" / "review-1.json").write_text(json.dumps({"task": "FINAL", "verdict": "changes", "findings": [
                {"id": "F1", "state": "missing", "blocking": True, "where": "index.md:1", "issue": "No articles.", "fix": "Add."}]}))
            h.tp("record", "FINAL")
            self.assertEqual(h.next()["actions"][0]["action"], "human")
            h.tp("resolve", "--action", "accept", "--answer", "Ship it as is.")
            self.assertEqual(h.next()["actions"][0]["action"], "final")
            h.tp("final")
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
