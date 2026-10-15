"""Round 2 — progress signals, not the clock: the budget meters cost while stuckness is
detected from state transitions (empty hand-backs, cycling findings, repeated losses, a
workflow that stops changing), and the manager gets a human-digestable status report."""
from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from harness import Harness  # noqa: E402

CODE = dict(
    deliverables=[{"id": "D1", "kind": "code", "what": "calc gains mul()", "where": "app"}],
    participants=[{"agent": "test-author", "role": "tests", "why": "Writes mul's tests first."},
                  {"agent": "code-author", "role": "author", "why": "Implements mul to pass them."}],
)

TEST_PY = "import unittest\nfrom calc import mul\n\nclass T(unittest.TestCase):\n" \
          "    def test_mul(self):\n        self.assertEqual(mul(2, 3), 6)\n"


class CoreCommandsTest(unittest.TestCase):
    """The round must not retire anything the manager relies on."""

    def test_core_subcommands_survive(self) -> None:
        out = self.h.tp("--help", wf=False).text
        for cmd in ("revise", "halt", "resume", "approve", "amend", "dispatch", "record",
                    "exception", "resolve", "final", "status", "next", "research", "plan",
                    "scope", "note", "noticed", "report", "check-docs", "show", "triage",
                    "closeout"):
            self.assertRegex(out, rf"\b{cmd}\b", cmd)

    def setUp(self) -> None:
        self.h = Harness()


class EmptyHandbackTest(unittest.TestCase):
    """A `done` hand-back that changed nothing in the workspace is a stall or a lie,
    whatever the clock says — unless the work itself changed nothing (a commit-only task:
    git history moved, the tree did not)."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def test_done_with_an_unchanged_workspace_fails_the_task(self) -> None:
        self.h.tp("dispatch", "T01")
        self.h.result("T01", "author", changed=[])          # claims done, wrote nothing
        out = self.h.tp("record", "T01", "--agent-id", "a-1").out
        self.assertIn("wrote nothing", out)
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "needs_fix")

    def test_a_commit_only_task_is_not_flagged(self) -> None:
        # The reported false positive: a task whose job is to commit pre-existing work
        # changes no tree files, but git history moved. Verify the agent's claim against
        # git, like the manager did by hand.
        from harness import git
        git(self.h.kb, "init", "-q", "-b", "main")
        (self.h.kb / "README.md").write_text("# kb\n")
        git(self.h.kb, "add", "-A")
        git(self.h.kb, "commit", "-q", "-m", "base")
        self.h.good_article("architecture/overview.md")     # uncommitted work, in the tree
        self.h.approved()                                   # dispatch snapshot holds the article
        self.h.tp("dispatch", "T01")
        git(self.h.kb, "add", "-A")
        git(self.h.kb, "commit", "-q", "-m", "T01: commit the article")
        self.h.result("T01", "author", changed=[])
        out = self.h.tp("record", "T01", "--agent-id", "a-1").out
        self.assertNotIn("wrote nothing", out)
        self.assertIn("commit", out)
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "needs_check")

    def test_review_steps_may_change_nothing(self) -> None:
        h = self.h
        scope = dict(
            deliverables=[{"id": "D1", "kind": "kb", "what": "articles", "where": "kb"}],
            participants=[{"agent": "kb-author", "role": "author", "why": "Writes every article for D1."},
                          {"agent": "doc-reviewer", "role": "reviewer", "why": "Reviews D1's articles."}],
            review="final",
        )
        plan = h.plan(review_batches=[{"id": "B1", "tasks": ["T01", "T02", "T03"]}])
        h.approved(plan, **scope)
        h.author("T01", "architecture/overview.md", agent_id="a-1")
        h.author("T02", "build/guide.md", agent_id="a-2")
        h.tp("accept", "T01", "--note", "ok")
        h.tp("accept", "T02", "--note", "ok")
        h.tp("dispatch", "T03")
        (h.kb / "index.md").write_text("# KB\n\n- [O](architecture/overview.md)\n- [B](build/guide.md)\n")
        h.result("T03", "author", changed=["index.md"])
        h.tp("record", "T03", "--agent-id", "a-3")
        h.tp("accept", "T03", "--note", "ok")
        h.tp("dispatch", "B1/doc-reviewer")
        (h.wf / "runs" / "B1" / "doc-reviewer-1.json").write_text(json.dumps(
            {"batch": "B1", "verdict": "pass", "findings": []}))
        out = h.tp("record", "B1/doc-reviewer", "--agent-id", "rev-1").out
        self.assertNotIn("wrote nothing", out)


class CyclingTest(unittest.TestCase):
    """The same findings twice in a row means the fix loop is not converging: stop burning
    rounds and put it to the human."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def test_identical_findings_block_as_not_converging(self) -> None:
        h = self.h
        h.tp("dispatch", "T01")
        h.good_article("architecture/overview.md")
        (h.kb / "index.md").write_text("# KB\n")            # belongs to T03: the violation
        h.result("T01", "author", changed=["architecture/overview.md"])
        h.tp("record", "T01", "--agent-id", "a-1")
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_fix")
        for rnd in (1, 2):                                   # the cap is 2: both rounds repeat it
            h.tp("dispatch", "T01")
            p = h.kb / "architecture" / "overview.md"
            p.write_text(p.read_text() + f"\nRound {rnd} detail.\n")   # real work...
            (h.kb / "index.md").write_text(f"# KB v{rnd}\n")           # ...but the same violation again
            h.result("T01", "fix", changed=["architecture/overview.md"])
            out = h.tp("record", "T01", "--agent-id", "a-1").out
        self.assertIn("same findings", out)                  # the cap-block names the non-convergence
        st = h.state()["tasks"]["T01"]
        self.assertEqual(st["status"], "blocked")
        self.assertEqual(st["blocked"]["kind"], "rounds")

    def test_different_findings_still_take_their_rounds(self) -> None:
        h = self.h
        h.tp("dispatch", "T01")
        h.good_article("architecture/overview.md")
        (h.kb / "index.md").write_text("# KB\n")
        h.result("T01", "author", changed=["architecture/overview.md"])
        h.tp("record", "T01", "--agent-id", "a-1")
        h.tp("dispatch", "T01")
        p = h.kb / "architecture" / "overview.md"
        p.write_text(p.read_text() + "\nMore detail, really.\n")
        (h.kb / "other.md").write_text("# other\n")          # a different violation this round
        h.result("T01", "fix", changed=["architecture/overview.md"])
        out = h.tp("record", "T01", "--agent-id", "a-1").out
        self.assertNotIn("same findings", out)
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_fix")


class LostBreakerTest(unittest.TestCase):
    """Three losses of the same task stop the re-dispatch loop at the workflow level."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved(budget_minutes=300)

    def tearDown(self) -> None:
        self.h.close()

    def lose_once(self, note: str) -> None:
        self.h.tp("dispatch", "T01")
        self.h.tp("lost", "T01", "--summary", note)
        self.h.tp("resolve", "--task", "T01", "--action", "retry", "--answer", "manager: re-run")

    def test_three_losses_block_the_workflow(self) -> None:
        self.lose_once("harness interrupt")
        self.lose_once("session restart")
        self.h.tp("dispatch", "T01")
        out = self.h.tp("lost", "T01", "--summary", "host loss").out
        self.assertIn("3 times", out)
        self.assertEqual(self.h.next()["actions"][0]["action"], "human")
        self.h.tp("resolve", "--task", "T01", "--action", "answer",
                  "--answer", "Stop retrying on this machine; take a different approach.")
        self.assertNotEqual(self.h.next()["actions"][0]["action"], "human")

    def test_two_losses_do_not_trip_the_breaker(self) -> None:
        self.lose_once("harness interrupt")
        self.lose_once("session restart")
        self.assertNotEqual(self.h.next()["actions"][0]["action"], "human")


class NoStateChangeTest(unittest.TestCase):
    """`tp next` flags a workflow whose state has stopped changing — the workflow-level
    analog of the supervisor's tool-call recency."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def test_repeated_next_with_no_events_warns(self) -> None:
        self.h.tp("next")
        time.sleep(1.1)
        warnings = self.h.next()["warnings"]
        self.assertTrue(any("no state change" in w for w in warnings), warnings)

    def test_a_record_clears_the_flag(self) -> None:
        self.h.tp("next")
        self.h.author("T01", "architecture/overview.md", agent_id="a-1")
        self.assertEqual(self.h.next()["warnings"], [])


class DigestTest(unittest.TestCase):
    """`tp digest`: the human-digestable status report the manager presents on interval."""

    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def test_executing_digest_shows_agents_groups_and_time(self) -> None:
        h = self.h
        h.approved(budget_minutes=180)
        h.author("T01", "architecture/overview.md", agent_id="a-1")
        h.tp("accept", "T01", "--note", "ok")
        h.tp("dispatch", "T02")
        out = h.tp("digest").out
        self.assertIn("EXECUTING", out)
        self.assertIn("T02", out)                              # agents in flight
        self.assertIn("writing 1/3", out)                      # kb tasks: 1 accepted of 3
        self.assertIn("of 180 agent-min", out)                 # budget
        self.assertIn("writing", out.split("Time:")[1])        # time by group

    def test_planning_digest_reports_research(self) -> None:
        h = self.h
        h.confirmed(budget_minutes=240)
        out = h.tp("digest").out
        self.assertIn("PLANNING", out)
        self.assertIn("research", out)
        self.assertIn("240", out)

    def test_done_digest_points_at_the_report(self) -> None:
        h = self.h
        h.approved()
        for tid, rel in (("T01", "architecture/overview.md"), ("T02", "build/guide.md")):
            h.author(tid, rel, agent_id=f"a-{tid}")
            h.tp("accept", tid, "--note", "ok")
        h.tp("dispatch", "T03")
        (h.kb / "index.md").write_text("# KB\n\n- [O](architecture/overview.md)\n- [B](build/guide.md)\n")
        h.result("T03", "author", changed=["index.md"])
        h.tp("record", "T03", "--agent-id", "a-T03")
        h.tp("accept", "T03", "--note", "ok")
        h.tp("final")
        out = h.tp("digest").out
        self.assertIn("DONE", out)
        self.assertIn("report", out)

    def test_code_and_writing_groups_are_separate(self) -> None:
        h = self.h
        app = h.root / "app"
        app.mkdir()
        (app / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        from harness import git
        git(app, "init", "-q", "-b", "main")
        git(app, "add", "-A")
        git(app, "commit", "-q", "-m", "init")
        scope = dict(
            deliverables=[{"id": "D1", "kind": "code", "what": "calc gains mul()", "where": "app"},
                          {"id": "D2", "kind": "kb", "what": "A usage article", "where": "kb"}],
            participants=[{"agent": "test-author", "role": "tests", "why": "Writes mul's tests first."},
                          {"agent": "code-author", "role": "author", "why": "Implements mul for D1."},
                          {"agent": "kb-author", "role": "author", "why": "Writes the D2 article."}],
            workspaces=[{"name": "app", "path": str(app), "mode": "write"},
                        {"name": "kb", "path": str(h.kb), "mode": "write"},
                        {"name": "src", "path": str(h.src), "mode": "read"}],
        )
        tasks = [
            {"id": "T01", "title": "mul", "serves": ["D1"], "agent": "code-author", "workspace": "app",
             "paths": ["calc.py", "test_calc.py"], "sources": ["app:calc.py"], "brief": "Add mul.",
             "acceptance": ["mul(2, 3) == 6"], "test_cmd": "python3 -m unittest -q test_calc",
             "tests_paths": ["test_calc.py"], "checks": [], "estimate_min": 10, "depends_on": []},
            h.task("T02", "usage.md", serves=["D2"]),
            h.task("T03", "faq.md", serves=["D2"]),
        ]
        h.approved(h.plan(tasks, final_checks=[]), **scope)
        h.tp("dispatch", "T01")                       # code task: tests step first, red
        (app / "test_calc.py").write_text(TEST_PY)
        h.result("T01", "tests", changed=["test_calc.py"])
        h.tp("record", "T01", "--agent-id", "ta-1")
        h.tp("dispatch", "T01")                       # then impl, green
        (app / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n")
        h.result("T01", "impl", changed=["calc.py"])
        h.tp("record", "T01", "--agent-id", "ca-1")
        h.tp("accept", "T01", "--note", "ok")
        out = h.tp("digest").out
        self.assertIn("coding 1/1", out)
        self.assertIn("writing 0/2", out)


class CloseoutTest(unittest.TestCase):
    """The closeout gate: ticket-scope work found mid-run is a human decision, never a
    silent deferral. `tp final` refuses while noticed items are unclassified or a deferral
    lacks the human's recorded answer."""

    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def run_to_closeout(self, noticed: list) -> None:
        h = self.h
        h.approved()
        h.tp("dispatch", "T01")
        h.good_article("architecture/overview.md")
        h.result("T01", "author", changed=["architecture/overview.md"], noticed=noticed[:1])
        h.tp("record", "T01", "--agent-id", "a-1")
        h.tp("accept", "T01", "--note", "ok")
        h.author("T02", "build/guide.md", agent_id="a-2")
        h.tp("accept", "T02", "--note", "ok")
        h.tp("dispatch", "T03")
        (h.kb / "index.md").write_text("# KB\n\n- [O](architecture/overview.md)\n- [B](build/guide.md)\n")
        h.result("T03", "author", changed=["index.md"], noticed=noticed[1:])
        h.tp("record", "T03", "--agent-id", "a-3")
        h.tp("accept", "T03", "--note", "ok")

    def test_final_refuses_until_items_are_classified(self) -> None:
        self.run_to_closeout(["webhookauth.go still writes admission-webhook.yaml non-atomically.",
                              "docs still say the kubelet dir is kept when it is not."])
        self.assertEqual(self.h.next()["actions"][0]["action"], "closeout")
        res = self.h.tp("final", expect=2)
        self.assertIn("closeout", res.text)
        self.assertNotEqual(self.h.state()["phase"], "DONE")

    def test_classify_then_decide_releases_the_report(self) -> None:
        h = self.h
        self.run_to_closeout(["webhookauth.go still writes admission-webhook.yaml non-atomically.",
                              "vet needs the dash SPA built; environmental, pre-existing."])
        h.tp("closeout", "--item", "1", "--class", "deferred",
             "--note", "same hazard class as KUB-522; needs its own task")
        h.tp("closeout", "--item", "2", "--class", "observation")
        self.assertEqual(h.next()["actions"][0]["action"], "closeout")   # deferral undecided
        h.tp("closeout", "--decide", "--answer", "Accept the deferral; file KUB-600 for webhookauth.")
        self.assertEqual(h.next()["actions"][0]["action"], "final")
        h.tp("final")
        report = (h.wf / "report.md").read_text()
        self.assertIn("Deferred with the human's OK", report)
        self.assertIn("webhookauth.go", report)
        self.assertIn("KUB-600", (h.wf / "decisions.md").read_text())
        self.assertIn("Observations", report)

    def test_observations_alone_need_no_human_decision(self) -> None:
        h = self.h
        self.run_to_closeout(["vet needs the dash SPA built; environmental, pre-existing."])
        h.tp("closeout", "--item", "1", "--class", "observation")
        self.assertEqual(h.next()["actions"][0]["action"], "final")
        h.tp("final")
        self.assertEqual(h.state()["phase"], "DONE")

    def test_deferrals_need_a_plain_language_note(self) -> None:
        # The decision brief is what the human actions: a deferred item whose note is a bare
        # file path is not a decision, it is a riddle (the kub-522 complaint).
        h = self.h
        self.run_to_closeout(["webhookauth.go still writes admission-webhook.yaml non-atomically.",
                              "vet needs the dash SPA built; environmental, pre-existing."])
        res = h.tp("closeout", "--item", "1", "--class", "deferred", expect=2)
        self.assertIn("--note", res.text)
        self.assertIn("consequence", res.text)
        h.tp("closeout", "--item", "1", "--class", "deferred",
             "--note", "a crash mid-write can tear the admission config the apiserver reads; "
                       "the same hazard KUB-522 removes elsewhere.")
        h.tp("closeout", "--item", "2", "--class", "observation")   # observations need no note

    def test_ask_renders_an_answer_first_decision_brief(self) -> None:
        h = self.h
        self.run_to_closeout(["webhookauth.go still writes admission-webhook.yaml non-atomically.",
                              "vet needs the dash SPA built; environmental, pre-existing."])
        h.tp("closeout", "--item", "1", "--class", "deferred",
             "--note", "a crash mid-write can tear the admission config the apiserver reads.")
        h.tp("closeout", "--item", "2", "--class", "observation")
        out = h.tp("closeout", "--ask").out
        self.assertIn("How should they be handled", out.splitlines()[0])   # the decision leads
        self.assertIn("webhookauth.go still writes", out)                  # the issue, verbatim
        self.assertIn("Why it matters: a crash mid-write", out)            # the consequence
        self.assertIn("accept the deferral", out)                          # the options
        self.assertNotIn("environmental, pre-existing", out)               # observations stay out

    def test_ask_refuses_unclassified_or_already_decided(self) -> None:
        h = self.h
        self.run_to_closeout(["first gap.", "second gap."])
        h.tp("closeout", "--item", "1", "--class", "observation")
        self.assertIn("unclassified", h.tp("closeout", "--ask", expect=2).text)
        h.tp("closeout", "--item", "2", "--class", "observation")
        self.assertIn("no human decision", h.tp("closeout", "--ask", expect=2).text)
        h.tp("closeout", "--item", "2", "--class", "deferred", "--note", "work for a later task.")
        h.tp("closeout", "--decide", "--answer", "accepted; filed a follow-up.")
        self.assertIn("already", h.tp("closeout", "--ask", expect=2).text)

    def test_items_noticed_after_the_decision_reopen_the_gate(self) -> None:
        h = self.h
        self.run_to_closeout(["first gap."])
        h.tp("closeout", "--item", "1", "--class", "observation")
        h.tp("resolve", "--task", "T02", "--action", "reopen", "--answer", "the late gap touches this task")
        h.tp("dispatch", "T02")
        h.good_article("build/guide.md")
        h.result("T02", "fix", changed=["build/guide.md"], noticed=["a late gap worth its own task."])
        h.tp("record", "T02", "--agent-id", "a-late")
        h.tp("accept", "T02", "--note", "ok")
        self.assertEqual(h.next()["actions"][0]["action"], "closeout")
        self.assertIn("closeout", h.tp("final", expect=2).text)

    def test_dedupe_merges_repeated_notices(self) -> None:
        import tempfile
        from pipeline.common import Workflow
        with tempfile.TemporaryDirectory() as tmp:
            wf = Workflow(Path(tmp))
            wf.noticed("T05", "webhookauth.go still writes the pair non-atomically.")
            wf.noticed("T05 review", "webhookauth.go  still writes the pair\nnon-atomically.")
            wf.noticed("T03", "a different gap entirely.")
            text = (wf.root / "noticed.md").read_text()
            self.assertEqual(text.count("webhookauth.go still writes the pair non-atomically."), 1)
            self.assertIn("×2", text)
            self.assertEqual(len(wf.noticed_items()), 2)
            self.assertIsNotNone(wf.noticed_resolve(1, "settled"))


class StaleFixBriefTest(unittest.TestCase):
    """A fix-round brief carries a staleness guard: files that changed since the failing
    round — usually accepted concurrent work — are named, so the fix agent never reverts
    them on the strength of a stale finding (the T05 incident in the kub-522 run)."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def test_fix_brief_names_concurrent_work(self) -> None:
        h = self.h
        h.tp("dispatch", "T01")
        h.good_article("architecture/overview.md")
        (h.kb / "stray.md").write_text("# stray\n")            # foreign file: the round fails
        h.result("T01", "author", changed=["architecture/overview.md"])
        h.tp("record", "T01", "--agent-id", "a-1")
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_fix")
        (h.kb / "build").mkdir()
        (h.kb / "build" / "guide.md").write_text("# guide\n")  # concurrent accepted work lands
        h.tp("dispatch", "T01")
        brief = (h.run_dir("T01") / "brief-fix-1.md").read_text()
        self.assertIn("never revert", brief)
        self.assertIn("build/guide.md", brief)


if __name__ == "__main__":
    unittest.main()
