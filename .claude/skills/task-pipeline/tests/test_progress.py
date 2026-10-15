"""Progress signals, not the clock. Time is reported (plan, digest, report) and never gates
or compresses work; stuckness is detected from what the work does — an authoring hand-back
that changed nothing, fix rounds that repeat the same findings, a dispatch lost again and
again, a workflow whose state stops changing, an agent whose writes stop moving — and the
report waits on a closeout of everything noticed along the way."""
from __future__ import annotations

import json
import re
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Tuple

from harness import Harness, git

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

CODE = dict(
    deliverables=[{"id": "D1", "kind": "code", "what": "calc gains mul()", "where": "app"}],
    participants=[{"agent": "test-author", "role": "tests", "why": "Writes mul's tests first."},
                  {"agent": "code-author", "role": "author", "why": "Implements mul to pass them."},
                  {"agent": "correctness-reviewer", "role": "reviewer", "why": "Reviews the D1 change."}],
    review="final",
)
TEST_PY = "import unittest\nfrom calc import mul\n\nclass T(unittest.TestCase):\n" \
          "    def test_mul(self):\n        self.assertEqual(mul(2, 3), 6)\n"
MUL_PY = "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"
FINAL_REVIEW = dict(review="final", participants=[
    {"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."},
    {"agent": "doc-reviewer", "role": "reviewer", "why": "Reviews the finished KB for accuracy."}])
INDEX = "# KB\n\n- [O](architecture/overview.md)\n- [B](build/guide.md)\n"
ISO = re.compile(r'"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)"')


def elapse(h: Harness, minutes: int) -> None:
    """Pretend `minutes` pass: every timestamp the state holds moves that far into the past."""
    path = h.wf / ".tp" / "state.json"

    def back(m: "re.Match[str]") -> str:
        ts = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%SZ") - timedelta(minutes=minutes)
        return '"' + ts.strftime("%Y-%m-%dT%H:%M:%SZ") + '"'

    path.write_text(ISO.sub(back, path.read_text()))


def code_harness() -> Tuple[Harness, Path, Callable[[], None]]:
    """A one-task code plan in its own git workspace: tests first (red), then impl (green)."""
    h = Harness()
    app = h.root / "app"
    app.mkdir()
    (app / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    git(app, "init", "-q", "-b", "main")
    git(app, "add", "-A")
    git(app, "commit", "-q", "-m", "init")
    scope = dict(CODE, workspaces=[{"name": "app", "path": str(app), "mode": "write"}])
    task = {"id": "T01", "title": "mul", "serves": ["D1"], "agent": "code-author", "workspace": "app",
            "paths": ["calc.py", "test_calc.py"], "sources": ["app:calc.py"],
            "brief": "Add mul(a, b) beside add.", "acceptance": ["mul(2, 3) == 6"],
            "test_cmd": "python3 -m unittest -q test_calc", "tests_paths": ["test_calc.py"],
            "checks": [], "estimate_min": 10, "depends_on": []}
    return h, app, lambda: h.approved(h.plan([task], final_checks=[]), **scope)


def finish_index(h: Harness, noticed=()) -> None:
    h.tp("dispatch", "T03")
    (h.kb / "index.md").write_text(INDEX)
    h.result("T03", "author", changed=["index.md"], noticed=list(noticed))
    h.tp("record", "T03", "--agent-id", "a-3")
    h.tp("accept", "T03", "--note", "ok")


class TimeNeverGatesTest(unittest.TestCase):
    """Budgets are reporting metadata the manager sizes itself: never a human approval, never a
    refusal, never a reason to cut or merge work."""

    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def test_next_never_warns_about_the_budget_and_dispatch_never_gates_on_it(self) -> None:
        h = self.h
        h.approved()                                        # a 180-min budget
        elapse(h, 900)                                      # far past it
        self.assertEqual([w for w in h.next()["warnings"] if "budget" in w.lower()], [])
        self.assertIn("of 180", h.tp("next").out.splitlines()[0])   # still reported
        h.tp("dispatch", "T01")                             # the right solution still lands
        self.assertIn("T01", h.state()["in_flight"])

    def test_budget_extend_is_manager_bookkeeping_and_keeps_scope_consistent(self) -> None:
        h = self.h
        h.confirmed()
        out = h.tp("budget", "extend", "--minutes", "60", "--note", "manager re-estimate after the survey.").out
        self.assertIn("240", out)
        self.assertEqual(h.read_json("scope.json")["budget_minutes"], 240)
        self.assertIn("240 min", (h.wf / "scope.md").read_text())
        decisions = (h.wf / "decisions.md").read_text()
        self.assertRegex(decisions, r"budget extend \+60 min · manager: .*manager re-estimate")
        h.write_json("plan.json", h.plan())
        h.tp("plan", "check")                               # the frozen scope still matches its sha
        h.tp("budget", "extend", "--minutes", "30", "--answer", "Sure, take more.")
        self.assertIn("· human: ", (h.wf / "decisions.md").read_text())
        h.tp("budget", "extend", "--minutes", "0", "--note", "x", expect=2)

    def test_budget_extend_needs_a_reason(self) -> None:
        self.h.confirmed()
        self.assertIn("--note", self.h.tp("budget", "extend", "--minutes", "30", expect=2).text)


class EmptyHandbackTest(unittest.TestCase):
    """A `done` authoring hand-back that changed nothing is a stall or a lie, whatever the clock
    says — unless git history moved (a commit-only task). Reviews and fix rounds are exempt."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def test_done_with_an_unchanged_workspace_fails_the_task(self) -> None:
        self.h.tp("dispatch", "T01")
        self.h.result("T01", "author", changed=[])
        out = self.h.tp("record", "T01", "--agent-id", "a-1").out
        self.assertIn("wrote nothing", out)
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "needs_fix")

    def test_a_commit_only_task_is_not_flagged(self) -> None:
        h = self.h
        git(h.kb, "init", "-q", "-b", "main")
        (h.kb / "README.md").write_text("# kb\n")
        git(h.kb, "add", "-A")
        git(h.kb, "commit", "-q", "-m", "base")
        h.good_article("architecture/overview.md")         # uncommitted work already in the tree
        h.approved()                                        # dispatch snapshot holds the article
        h.tp("dispatch", "T01")
        git(h.kb, "add", "-A")
        git(h.kb, "commit", "-q", "-m", "T01: commit the article")
        h.result("T01", "author", changed=[])
        out = h.tp("record", "T01", "--agent-id", "a-1").out
        self.assertNotIn("wrote nothing", out)
        self.assertIn("commit", out)
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_check")

    def test_a_fix_round_may_change_nothing(self) -> None:
        h = self.h
        h.author("T01", "architecture/overview.md")
        h.tp("reject", "T01", "--reason", "Check the claim again.")
        h.tp("dispatch", "T01")
        h.result("T01", "fix", changed=[], summary="The claim holds; disputed with evidence.")
        self.assertNotIn("wrote nothing", h.tp("record", "T01", "--agent-id", "a-1").out)

    def test_an_integration_task_may_change_nothing_locally(self) -> None:
        # A liaison's work lands in Jira or GitHub; its workspace legitimately stays untouched.
        h = self.h
        scope = dict(deliverables=[{"id": "D1", "kind": "integration", "what": "The calc epic updated in Jira",
                                    "where": "jira"}],
                     participants=[{"agent": "atlassian-liaison", "role": "author",
                                    "why": "Makes the approved Jira updates for D1."}])
        task = h.task("T01", "notes/jira.md", agent="atlassian-liaison", checks=[],
                      brief="Post the approved status comment on the calc epic.",
                      acceptance=["The comment is on the epic, read back."])
        h.approved(h.plan([task], final_checks=[]), **scope)
        h.tp("dispatch", "T01")
        h.result("T01", "author", changed=[], summary="Posted the comment; read it back.")
        out = h.tp("record", "T01", "--agent-id", "liaison-1").out
        self.assertNotIn("wrote nothing", out)
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_check")

    def test_a_final_review_may_change_nothing(self) -> None:
        h = self.h
        h.approved(h.plan(review_batches=[{"id": "B1", "tasks": ["T01", "T02", "T03"]}]), **FINAL_REVIEW)
        for tid, rel in (("T01", "architecture/overview.md"), ("T02", "build/guide.md")):
            h.author(tid, rel, agent_id=f"a-{tid}")
            h.tp("accept", tid, "--note", "ok")
        finish_index(h)
        h.tp("dispatch", "B1/doc-reviewer")
        (h.wf / "runs" / "B1" / "doc-reviewer-1.json").write_text(json.dumps(
            {"batch": "B1", "verdict": "pass", "findings": []}))
        self.assertNotIn("wrote nothing", h.tp("record", "B1/doc-reviewer", "--agent-id", "rev-1").out)


class CyclingTest(unittest.TestCase):
    """The same findings twice in a row means the fix loop is not converging: the block at the
    cap says so instead of a bare round count."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def first_round_with_a_stray(self) -> None:
        h = self.h
        h.tp("dispatch", "T01")
        h.good_article("architecture/overview.md")
        (h.kb / "index.md").write_text("# KB\n")           # T03's file: the violation
        h.result("T01", "author", changed=["architecture/overview.md"])
        h.tp("record", "T01", "--agent-id", "a-1")

    def test_identical_findings_block_as_not_converging(self) -> None:
        h = self.h
        self.first_round_with_a_stray()
        for rnd in (1, 2):
            h.tp("dispatch", "T01")
            p = h.kb / "architecture" / "overview.md"
            p.write_text(p.read_text() + f"\nRound {rnd} detail.\n")
            (h.kb / "index.md").write_text(f"# KB v{rnd}\n")   # the same violation again
            h.result("T01", "fix", changed=["architecture/overview.md"])
            out = h.tp("record", "T01", "--agent-id", "a-1").out
        self.assertIn("same findings", out)
        st = h.state()["tasks"]["T01"]
        self.assertEqual((st["status"], st["blocked"]["kind"]), ("blocked", "rounds"))
        self.assertIn("not converging", st["blocked"]["summary"])
        self.assertIn("since", st["blocked"])                # the waiting clock still starts

    def test_different_findings_still_take_their_rounds(self) -> None:
        h = self.h
        self.first_round_with_a_stray()
        h.tp("dispatch", "T01")
        p = h.kb / "architecture" / "overview.md"
        p.write_text(p.read_text() + "\nMore detail.\n")
        (h.kb / "other.md").write_text("# other\n")         # a different violation
        h.result("T01", "fix", changed=["architecture/overview.md"])
        out = h.tp("record", "T01", "--agent-id", "a-1").out
        self.assertNotIn("same findings", out)
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_fix")


class LostTest(unittest.TestCase):
    """A dispatch that dies (session restart, crash, a TaskStop on a stuck agent) is a first-class
    path: the slot frees, the dead span stays out of the task's minutes, the re-dispatch is fresh,
    and a task lost again and again goes to the human instead of looping."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def lose_once(self, note: str, by: str = "manager") -> None:
        self.h.tp("dispatch", "T01")
        self.h.tp("lost", "T01", "--summary", note)
        self.h.tp("resolve", "--task", "T01", "--action", "retry", "--answer", "re-run it", "--by", by)

    def test_lost_frees_the_slot_blocks_and_redispatches_fresh(self) -> None:
        h = self.h
        h.author("T01", "architecture/overview.md", agent_id="a-1")
        h.tp("reject", "T01", "--reason", "Cite the line.")
        h.tp("dispatch", "T01")                              # a fix round: resumes agent a-1
        elapse(h, 30)
        out = h.tp("lost", "T01", "--summary", "Session restarted; no hand-back.").out
        self.assertIn("re-dispatch", out)
        st = h.state()
        self.assertNotIn("T01", st["in_flight"])
        self.assertEqual((st["tasks"]["T01"]["status"], st["tasks"]["T01"]["blocked"]["kind"]),
                         ("blocked", "exception"))
        self.assertNotIn("author", st["tasks"]["T01"]["agents"])   # the dead session is never resumed
        act = h.next()["actions"][0]
        self.assertEqual((act["action"], act["id"]), ("rerun", "T01"))   # the manager's call, not the human's
        self.assertIn("--by manager", h.tp("next").out)
        h.tp("resolve", "--task", "T01", "--action", "retry", "--answer", "re-run it", "--by", "manager")
        out = h.tp("dispatch", "T01").out
        self.assertIn("Agent(", out)
        self.assertNotIn("SendMessage", out)
        h.good_article("architecture/overview.md")
        h.result("T01", "fix", changed=["architecture/overview.md"])
        h.tp("record", "T01", "--agent-id", "a-2")
        mins = float(re.search(r"\((\d+) min", h.tp("accept", "T01", "--note", "ok").out).group(1))
        self.assertLess(mins, 25)                            # the 30 lost minutes are not work

    def test_lost_needs_an_in_flight_task(self) -> None:
        self.assertIn("not in flight", self.h.tp("lost", "T01", "--summary", "nothing", expect=2).text)
        self.assertIn("tp record", self.h.tp("lost", "R1", "--summary", "a researcher died", expect=2).text)

    def test_two_losses_leave_the_rerun_to_the_manager(self) -> None:
        self.lose_once("harness interrupt")
        self.h.tp("dispatch", "T01")
        self.h.tp("lost", "T01", "--summary", "session restart")
        self.assertEqual(self.h.next()["actions"][0]["action"], "rerun")

    def test_the_third_loss_in_a_row_needs_the_human(self) -> None:
        h = self.h
        self.lose_once("harness interrupt")
        self.lose_once("session restart")
        h.tp("dispatch", "T01")
        out = h.tp("lost", "T01", "--summary", "crashed again").out
        self.assertIn("3 times", out)
        self.assertEqual(h.next()["actions"][0]["action"], "human")
        refused = h.tp("resolve", "--task", "T01", "--action", "retry", "--answer", "again", "--by", "manager",
                       expect=2).text
        self.assertIn("human", refused)
        h.tp("resolve", "--task", "T01", "--action", "retry", "--answer", "Try a smaller first step.",
             "--by", "human")
        self.assertEqual(h.next()["actions"][0]["action"], "dispatch")

    def test_a_real_handback_resets_the_streak(self) -> None:
        h = self.h
        self.lose_once("harness interrupt")
        self.lose_once("session restart")
        h.tp("dispatch", "T01")
        h.good_article("architecture/overview.md")
        h.result("T01", "author", changed=["architecture/overview.md"])
        h.tp("record", "T01", "--agent-id", "a-1")
        h.tp("reject", "T01", "--reason", "Cite the line.")
        h.tp("dispatch", "T01")
        self.assertNotIn("3 times", h.tp("lost", "T01", "--summary", "one more").out)
        h.tp("resolve", "--task", "T01", "--action", "retry", "--answer", "re-run", "--by", "manager")


class LivenessTest(unittest.TestCase):
    """`tp next` flags a workflow whose state has stopped changing between two looks; `tp status`
    only looks and never counts as one."""

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
        self.assertFalse(any("no state change" in w for w in self.h.next()["warnings"]))

    def test_status_is_look_and_stop(self) -> None:
        self.h.tp("status")
        self.h.tp("status")
        self.assertFalse(any("no state change" in w for w in self.h.next()["warnings"]))


class DigestTest(unittest.TestCase):
    """`tp digest`: the human-digestable status the manager presents at intervals — progress by
    group, time by group, and each in-flight agent's evidence of progress."""

    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def test_executing_digest_shows_progress_time_and_agents(self) -> None:
        h = self.h
        h.approved()
        h.author("T01", "architecture/overview.md", agent_id="a-1")
        h.tp("accept", "T01", "--note", "ok")
        h.tp("dispatch", "T02")
        out = h.tp("digest").out
        self.assertIn("EXECUTING", out)
        self.assertIn("1/3 tasks accepted", out)
        self.assertIn("of 180 min", out)
        self.assertIn("writing 1/3", out)
        self.assertIn("writing", out.split("Agent time:")[1])
        self.assertIn("T02", out.split("In flight:")[1])

    def t01(self) -> str:
        return next(ln for ln in self.h.tp("digest").out.splitlines() if ln.startswith("  T01 "))

    def test_an_agents_writes_are_its_progress_signal(self) -> None:
        h = self.h
        h.approved()
        h.tp("dispatch", "T01")
        self.assertIn("no writes in its paths yet; first look", self.t01())
        h.good_article("architecture/overview.md")
        moved = self.t01()
        self.assertIn("1 file in its paths changed since dispatch", moved)
        self.assertIn("moved since your last look", moved)
        h.tp("dispatch", "T02")                             # other work moves on
        self.assertIn("no change across 1 look while other work moved", self.t01())
        h.good_article("build/guide.md")
        h.result("T02", "author", changed=["build/guide.md"])
        h.tp("record", "T02", "--agent-id", "a-2")
        self.assertIn("no change across 2 looks while other work moved — possibly stuck", self.t01())

    def test_looking_twice_in_a_row_is_no_evidence(self) -> None:
        # Two digests seconds apart say nothing about a thinking agent; only looks separated by
        # other work moving count, so a lone agent can never be declared stuck by the clock.
        h = self.h
        h.approved()
        h.tp("dispatch", "T01")
        h.tp("digest")
        for _ in range(3):
            line = self.t01()
            self.assertIn("too soon to tell", line)
            self.assertNotIn("no change across", line)

    def test_writes_outside_the_task_are_not_its_progress(self) -> None:
        h = self.h
        h.approved()
        h.tp("dispatch", "T01")
        h.tp("digest")
        (h.kb / "unrelated.md").write_text("# someone else\n")
        self.assertIn("no writes in its paths yet", h.tp("digest").out.split("In flight:")[1])

    def test_planning_digest_reports_research(self) -> None:
        h = self.h
        h.confirmed(participants=[{"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."},
                                  {"agent": "codebase-researcher", "role": "research",
                                   "why": "Maps calc's areas for D1."}])
        qf = h.root / "q"
        qf.write_text("Which areas does calc split into?")
        h.tp("research", "add", "R1", "--agent", "codebase-researcher", "--purpose", "map",
             "--questions-file", str(qf), "--done-when", "I can split it.")
        h.tp("dispatch", "R1")
        out = h.tp("digest").out
        self.assertIn("PLANNING", out)
        self.assertIn("research 0/1", out)
        self.assertIn("result file", out.split("In flight:")[1])   # researchers write at the end

    def test_done_digest_points_at_the_report(self) -> None:
        h = self.h
        h.approved()
        for tid, rel in (("T01", "architecture/overview.md"), ("T02", "build/guide.md")):
            h.author(tid, rel, agent_id=f"a-{tid}")
            h.tp("accept", tid, "--note", "ok")
        finish_index(h)
        h.tp("final")
        out = h.tp("digest").out
        self.assertIn("DONE", out)
        self.assertIn("report.md", out)

    def test_code_and_writing_groups_are_separate(self) -> None:
        h, app, approve = code_harness()
        try:
            approve()
            h.tp("dispatch", "T01")
            (app / "test_calc.py").write_text(TEST_PY)
            h.result("T01", "tests", changed=["test_calc.py"])
            h.tp("record", "T01", "--agent-id", "ta-1")
            out = h.tp("digest").out
            self.assertIn("coding 0/1", out)
            self.assertNotIn("writing", out.split("Agent time:")[0])
        finally:
            h.close()


class CloseoutTest(unittest.TestCase):
    """Work noticed mid-run is a decision, never a silent deferral: nothing reaches DONE while
    noticed items are unclassified, and deferred or follow-up work needs the human's answer."""

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
        finish_index(h, noticed=noticed[1:])

    def test_final_refuses_until_items_are_classified(self) -> None:
        self.run_to_closeout(["webhookauth.go still writes admission-webhook.yaml non-atomically.",
                              "docs still say the kubelet dir is kept when it is not."])
        self.assertEqual(self.h.next()["actions"][0]["action"], "closeout")
        self.assertIn("closeout", self.h.tp("final", expect=2).text)
        self.assertNotEqual(self.h.state()["phase"], "DONE")

    def test_classify_then_decide_releases_the_report(self) -> None:
        h = self.h
        self.run_to_closeout(["webhookauth.go still writes admission-webhook.yaml non-atomically.",
                              "vet needs the dash SPA built; environmental, pre-existing."])
        h.tp("closeout", "--item", "1", "--class", "deferred",
             "--note", "a crash mid-write can tear the admission config; needs its own task")
        h.tp("closeout", "--item", "2", "--class", "observation")
        self.assertEqual(h.next()["actions"][0]["action"], "closeout")   # the deferral is undecided
        h.tp("closeout", "--decide", "--answer", "Accept the deferral; file KUB-600 for webhookauth.")
        self.assertEqual(h.next()["actions"][0]["action"], "final")
        h.tp("final")
        report = (h.wf / "report.md").read_text()
        self.assertIn("Deferred with the human's OK", report)
        self.assertIn("webhookauth.go", report)
        self.assertIn("Observations", report)
        self.assertRegex((h.wf / "decisions.md").read_text(), r"closeout.* · human: .*KUB-600")

    def test_observations_alone_need_no_human_decision(self) -> None:
        h = self.h
        self.run_to_closeout(["vet needs the dash SPA built; environmental, pre-existing."])
        h.tp("closeout", "--item", "1", "--class", "observation")
        self.assertEqual(h.next()["actions"][0]["action"], "final")
        h.tp("final")
        self.assertEqual(h.state()["phase"], "DONE")

    def test_nothing_noticed_goes_straight_to_final(self) -> None:
        self.run_to_closeout([])
        self.assertEqual(self.h.next()["actions"][0]["action"], "final")

    def test_deferrals_need_a_plain_language_note(self) -> None:
        h = self.h
        self.run_to_closeout(["webhookauth.go still writes admission-webhook.yaml non-atomically."])
        res = h.tp("closeout", "--item", "1", "--class", "deferred", expect=2)
        self.assertIn("--note", res.text)
        self.assertIn("consequence", res.text)
        h.tp("closeout", "--item", "1", "--class", "followup", "--note", "admission-webhook.yaml", expect=2)
        h.tp("closeout", "--item", "1", "--class", "deferred",
             "--note", "a crash mid-write can tear the admission config the apiserver reads.")

    def test_ask_renders_an_answer_first_decision_brief(self) -> None:
        h = self.h
        self.run_to_closeout(["webhookauth.go still writes admission-webhook.yaml non-atomically.",
                              "vet needs the dash SPA built; environmental, pre-existing."])
        h.tp("closeout", "--item", "1", "--class", "deferred",
             "--note", "a crash mid-write can tear the admission config the apiserver reads.")
        h.tp("closeout", "--item", "2", "--class", "observation")
        out = h.tp("closeout", "--ask").out
        self.assertIn("How should they be handled", out.splitlines()[0])
        self.assertIn("webhookauth.go still writes", out)
        self.assertIn("Why it matters: a crash mid-write", out)
        self.assertIn("AskUserQuestion", out)
        self.assertNotIn("environmental, pre-existing", out)

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
        h.tp("resolve", "--task", "T02", "--action", "reopen", "--answer", "the late gap touches this task",
             "--by", "manager")
        h.tp("dispatch", "T02")
        h.good_article("build/guide.md")
        h.result("T02", "fix", changed=["build/guide.md"], noticed=["a late gap worth its own task."])
        h.tp("record", "T02", "--agent-id", "a-late")
        h.tp("accept", "T02", "--note", "ok")
        self.assertEqual(h.next()["actions"][0]["action"], "closeout")
        self.assertIn("closeout", h.tp("final", expect=2).text)


class NoticedDedupeTest(unittest.TestCase):
    """Repeated notices merge, so a pile of duplicates cannot bury the real decisions."""

    def test_repeats_merge_with_a_count(self) -> None:
        from pipeline.common import Workflow
        with tempfile.TemporaryDirectory() as tmp:
            wf = Workflow(Path(tmp))
            wf.noticed("T05", "webhookauth.go still writes the pair non-atomically.")
            wf.noticed("T05 review", "webhookauth.go  still writes the pair\nnon-atomically.")
            wf.noticed("T03", "a different gap entirely.")
            wf.noticed("T07", "webhookauth.go still writes the pair non-atomically.")
            text = (wf.root / "noticed.md").read_text()
            self.assertEqual(text.count("webhookauth.go still writes the pair non-atomically."), 1)
            self.assertIn("- (T05, ×3) webhookauth.go", text)
            self.assertEqual(len(wf.noticed_items()), 2)


class StaleFixBriefTest(unittest.TestCase):
    """A fix brief names the files outside the task that changed since its round failed — usually
    accepted concurrent work — so the fix agent never reverts them off a stale finding, while the
    stray file the finding is about is not presented as someone else's work."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def test_fix_brief_names_concurrent_work_only(self) -> None:
        h = self.h
        h.tp("dispatch", "T01")
        h.good_article("architecture/overview.md")
        (h.kb / "stray.md").write_text("# stray\n")         # off-path: the round fails on it
        h.result("T01", "author", changed=["architecture/overview.md"])
        h.tp("record", "T01", "--agent-id", "a-1")
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_fix")
        h.good_article("build/guide.md")                    # concurrent work lands after the failure
        h.tp("dispatch", "T01")
        brief = (h.run_dir("T01") / "brief-fix-1.md").read_text()
        guard = next(ln for ln in brief.splitlines() if "never revert" in ln)
        self.assertIn("build/guide.md", guard)
        self.assertNotIn("stray.md", guard)

    def test_no_guard_when_nothing_else_changed(self) -> None:
        h = self.h
        h.author("T01", "architecture/overview.md")
        h.tp("reject", "T01", "--reason", "Cite the line.")
        h.tp("dispatch", "T01")
        self.assertNotIn("never revert", (h.run_dir("T01") / "brief-fix-1.md").read_text())


class TestsStepBriefTest(unittest.TestCase):
    def test_the_tests_step_forbids_any_production_edit(self) -> None:
        h, app, approve = code_harness()
        try:
            approve()
            h.tp("dispatch", "T01")
            brief = (h.run_dir("T01") / "brief-tests-0.md").read_text()
            self.assertIn("Touch no file outside the test paths", brief)
            self.assertIn("no stubs", brief)
        finally:
            h.close()


class WidenTest(unittest.TestCase):
    """A mechanical write-set growth the manager may make while EXECUTING — even on an accepted
    task — so a fix that needs one more file does not loop on 'outside this task's paths'."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def test_widen_an_accepted_task_and_fix_inside_the_new_path(self) -> None:
        h = self.h
        h.author("T01", "architecture/overview.md", agent_id="a-1")
        h.tp("accept", "T01", "--note", "ok")
        out = h.tp("widen", "T01", "--path", "architecture/glossary.md",
                   "--reason", "Review finding F1 needs the glossary cross-reference.").out
        self.assertIn("architecture/glossary.md", out)
        self.assertIn("architecture/glossary.md", h.read_json("plan.json")["tasks"][0]["paths"])
        self.assertIn("glossary", (h.wf / "plan.md").read_text())
        self.assertRegex((h.wf / "decisions.md").read_text(), r"widen T01 paths · manager: .*glossary")
        h.tp("next")                                        # the approved plan still loads
        h.tp("resolve", "--task", "T01", "--action", "reopen", "--answer", "F1 needs the glossary.", "--by", "manager")
        h.tp("dispatch", "T01")
        h.good_article("architecture/glossary.md", title="Glossary")
        h.result("T01", "fix", changed=["architecture/glossary.md"])
        self.assertNotIn("outside this task's paths", h.tp("record", "T01", "--agent-id", "a-1").out)

    def test_widen_refuses_an_unordered_overlap_even_with_finished_work(self) -> None:
        # Overlapping an accepted sibling would make every later plan check refuse the plan; a
        # finding about another task's file belongs to that task.
        h = self.h
        for tid, rel in (("T01", "architecture/overview.md"), ("T02", "build/guide.md")):
            h.author(tid, rel, agent_id=f"a-{tid}")
            h.tp("accept", tid, "--note", "ok")
        self.assertIn("T02", h.tp("widen", "T01", "--path", "build/guide.md", "--reason", "x", expect=2).text)
        h.tp("widen", "T03", "--path", "architecture/overview.md", "--reason", "T03 depends on T01: ordered")
        h.tp("plan", "amend")                                # starts a draft
        h.tp("plan", "amend")                                # the widened plan still validates

    def test_widen_refuses_a_path_a_live_task_owns(self) -> None:
        self.assertIn("T02", self.h.tp("widen", "T01", "--path", "build/guide.md", "--reason", "collides",
                                       expect=2).text)

    def test_widen_refuses_catch_alls_unknown_tasks_and_other_phases(self) -> None:
        h = self.h
        self.assertIn("whole workspace", h.tp("widen", "T01", "--path", ".", "--reason", "everything", expect=2).text)
        self.assertIn("not a task", h.tp("widen", "T99", "--path", "x.md", "--reason", "no such task", expect=2).text)
        h2 = Harness()
        try:
            h2.confirmed()
            self.assertIn("EXECUTING", h2.tp("widen", "T01", "--path", "x.md", "--reason", "wrong phase",
                                             expect=2).text)
        finally:
            h2.close()


class ExpandTest(unittest.TestCase):
    """Paths name files: bare catch-alls are refused at plan check, a runaway expansion at
    dispatch, and ignored trees never enter an expansion."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.confirmed()

    def tearDown(self) -> None:
        self.h.close()

    def plan_with(self, paths: list) -> None:
        self.h.write_json("plan.json", self.h.plan([self.h.task("T01", paths[0], paths=paths)]))

    def test_plan_check_rejects_dot_and_bare_globs(self) -> None:
        for bad in (["."], ["**"], ["./"], ["**/*"]):
            with self.subTest(paths=bad):
                self.plan_with(bad)
                self.assertIn("names the whole workspace", self.h.tp("plan", "check", expect=2).text)

    def test_a_runaway_expansion_is_refused_at_dispatch(self) -> None:
        d = self.h.kb / "gen"
        d.mkdir()
        for i in range(210):
            (d / f"f{i:03}.md").write_text("x\n")
        self.plan_with(["gen/**", "architecture/overview.md"])
        self.h.tp("plan", "check")
        self.h.tp("plan", "submit")
        self.h.tp("approve", "--answer", "ok")
        err = self.h.tp("dispatch", "T01", expect=2).text
        self.assertIn("210 files", err)
        self.assertEqual(self.h.state()["in_flight"], {})

    def test_ignored_trees_do_not_expand(self) -> None:
        from pipeline import run as runmod
        (self.h.kb / "node_modules" / ".pnpm").mkdir(parents=True)
        (self.h.kb / "node_modules" / ".pnpm" / "x.js").write_text("junk\n")
        (self.h.kb / "architecture").mkdir()
        (self.h.kb / "architecture" / "overview.md").write_text("# a\n")
        files = runmod._expand(self.h.kb, ["architecture/**", "node_modules/**"])
        rels = {str(p.relative_to(self.h.kb)) for p in files}
        self.assertIn("architecture/overview.md", rels)
        self.assertNotIn("node_modules/.pnpm/x.js", rels)


class TestsGateTest(unittest.TestCase):
    """The implementation may add tests (a review often asks for one) but never weaken them."""

    def setUp(self) -> None:
        self.h, self.app, approve = code_harness()
        approve()
        self.h.tp("dispatch", "T01")
        (self.app / "test_calc.py").write_text(TEST_PY)
        self.h.result("T01", "tests", changed=["test_calc.py"])
        self.h.tp("record", "T01", "--agent-id", "ta-1")
        self.h.tp("dispatch", "T01")

    def tearDown(self) -> None:
        self.h.close()

    def impl_record(self) -> str:
        (self.app / "calc.py").write_text(MUL_PY)
        self.h.result("T01", "impl", changed=["calc.py", "test_calc.py"])
        return self.h.tp("record", "T01", "--agent-id", "ca-1").out

    def test_adding_a_test_passes_the_gate(self) -> None:
        (self.app / "test_calc.py").write_text(TEST_PY + "\n    def test_mul_commutes(self):\n"
                                                         "        self.assertEqual(mul(3, 2), 6)\n")
        out = self.impl_record()
        self.assertIn("green", out)
        self.assertIn("tests grew", out)
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "needs_check")

    def test_weakening_a_test_still_fails_the_gate(self) -> None:
        (self.app / "test_calc.py").write_text(
            "import unittest\nfrom calc import mul\n\nclass T(unittest.TestCase):\n"
            "    def test_mul(self):\n        self.assertTrue(mul(2, 3) is not None)\n")
        out = self.impl_record()
        self.assertIn("weakened", out)
        self.assertIn("assertEqual(mul(2, 3), 6)", out)
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "needs_fix")


class BaselineTest(unittest.TestCase):
    """Final checks that already failed before the run are reported as pre-existing, not as
    breakage the run caused — the run still stops for the human either way."""

    def setUp(self) -> None:
        self.h = Harness()
        self.flag = self.h.root / "broken"

    def tearDown(self) -> None:
        self.h.close()

    def finish(self) -> None:
        h = self.h
        for tid, rel in (("T01", "architecture/overview.md"), ("T02", "build/guide.md")):
            h.author(tid, rel, agent_id=f"a-{tid}")
            h.tp("accept", tid, "--note", "ok")
        finish_index(h)

    def approve(self) -> None:
        self.h.approved(self.h.plan(checks={"lint": {"cmd": f"test ! -e {self.flag}"}},
                                    final_checks=["docs-all", "lint"]))

    def test_a_failure_present_at_baseline_is_labelled_pre_existing(self) -> None:
        self.flag.write_text("x")
        self.approve()
        self.assertIn("1 final-check failure", self.h.tp("baseline").out)
        self.finish()
        err = self.h.tp("final", expect=2).text
        self.assertIn("pre-existing", err)

    def test_a_new_failure_is_not_masked(self) -> None:
        self.approve()
        self.assertIn("every final check passes", self.h.tp("baseline").out)
        self.flag.write_text("x")
        self.finish()
        err = self.h.tp("final", expect=2).text
        self.assertIn("final check lint failed", err)
        self.assertNotIn("pre-existing", err)

    def test_baseline_refuses_while_agents_are_in_flight(self) -> None:
        self.approve()
        self.h.tp("dispatch", "T01")
        self.assertIn("in flight", self.h.tp("baseline", expect=2).text)


class TriageHintTest(unittest.TestCase):
    """Triage points at work a blocked hand-back parked as a patch, so its fix round can adopt it."""

    def test_triage_mentions_a_parked_patch(self) -> None:
        h = Harness()
        try:
            h.approved(h.plan([h.task("T01", "architecture/overview.md")], final_checks=[],
                              review_batches=[{"id": "B1", "tasks": ["T01"]}]), **FINAL_REVIEW)
            h.author("T01", "architecture/overview.md", agent_id="a-1")
            h.tp("accept", "T01", "--note", "ok")
            h.tp("dispatch", "B1/doc-reviewer")
            (h.wf / "runs" / "B1" / "doc-reviewer-1.json").write_text(json.dumps(
                {"batch": "B1", "verdict": "changes", "findings": [
                    {"id": "F1", "state": "wrong", "blocking": True, "where": "architecture/overview.md:3",
                     "issue": "Wrong claim.", "fix": "Fix it."}]}))
            h.tp("record", "B1/doc-reviewer", "--agent-id", "rev-1")
            (h.run_dir("T01") / "author-1.patch").write_text("--- a\n+++ b\n")
            self.assertIn("author-1.patch", h.tp("triage", "B1/doc-reviewer", "--accept-all").out)
        finally:
            h.close()


if __name__ == "__main__":
    unittest.main()
