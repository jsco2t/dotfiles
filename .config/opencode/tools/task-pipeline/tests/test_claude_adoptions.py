"""Agent-agnostic improvements adopted from the Claude task-pipeline tree: noticed items
merge across moved line numbers, research leaves workspaces exactly as it found them, a
research estimate that swallows the budget warns instead of refusing, a re-approval keeps
the review baselines of the first approval, closeout classifies in bulk and auto-classifies
agent chatter, and a review brief hands the reviewer one diff file plus the pipeline's own
logs instead of each reviewer re-deriving them."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from harness import Harness, git  # noqa: E402

CODE = dict(
    deliverables=[{"id": "D1", "kind": "code", "what": "calc gains mul()", "where": "app"}],
    participants=[{"agent": "test-author", "role": "tests", "why": "Writes mul's tests first."},
                  {"agent": "code-author", "role": "author", "why": "Implements mul to pass them."}],
)

TEST_PY = "import unittest\nfrom calc import mul\n\nclass T(unittest.TestCase):\n" \
          "    def test_mul(self):\n        self.assertEqual(mul(2, 3), 6)\n"

RESEARCH_PARTS = [
    {"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."},
    {"agent": "codebase-researcher", "role": "research", "why": "Maps dash/, which the survey cannot see."},
]
ANSWER = {"answers": [{"q": "Which areas?", "a": "Three: api, ui, store.", "evidence": ["dash/api/"]}],
          "followups": [], "unknowns": []}


class NoticedMergeTest(unittest.TestCase):
    """Later fix rounds re-notice the same gap after its lines moved; the pile of duplicates
    buried the decisions the closeout must put to the human."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.confirmed()

    def tearDown(self) -> None:
        self.h.close()

    def test_a_re_noticed_gap_with_moved_lines_merges(self) -> None:
        self.h.noticed("T01 review", "LICENSING.md:329 cites a paragraph the file no longer has.")
        self.h.noticed("T01 fix", "LICENSING.md:340 cites a paragraph the file no longer has.")
        text = (self.h.wf / "noticed.md").read_text()
        self.assertIn("×2", text)                                   # one merged line, counted
        self.assertEqual(len([ln for ln in text.splitlines() if ln.startswith("- ")
                              and "LICENSING.md" in ln]), 1)
        self.assertEqual(len(self.h.tp("noticed").out.splitlines()), 1)   # one open item

    def test_different_gaps_stay_separate(self) -> None:
        self.h.noticed("T01 review", "LICENSING.md:329 cites a paragraph the file no longer has.")
        self.h.noticed("T01 review", "LICENSING.md:330 cites a different, still-present paragraph.")
        self.assertEqual(len(self.h.tp("noticed").out.splitlines()), 2)


class ResearchLeavesWorkspacesTest(unittest.TestCase):
    """Planning research reads workspaces; it never writes one. A researcher that edits a
    tracked file must be refused at record until the workspace is restored."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.confirmed(participants=RESEARCH_PARTS, research={"budget_minutes": 45, "why": "The epic is thin."})
        qf = self.h.root / "R1.q"
        qf.write_text("Which top-level areas does dash/ split into?")
        self.h.tp("research", "add", "R1", "--agent", "codebase-researcher", "--purpose", "map",
                  "--questions-file", str(qf), "--done-when", "I can split the work into tasks.")
        self.h.tp("dispatch", "R1")

    def tearDown(self) -> None:
        self.h.close()

    def record(self, expect: int = 0):
        (self.h.wf / "recon" / "R1.json").write_text(json.dumps(ANSWER))
        return self.h.tp("record", "R1", expect=expect)

    def test_a_workspace_edit_between_dispatch_and_record_is_refused(self) -> None:
        calc = self.h.src / "calc" / "calc.go"
        was = calc.read_text()
        calc.write_text(was + "// touched by the researcher\n")
        res = self.record(expect=2)
        self.assertIn("workspace files changed", res.text)
        self.assertIn("calc.go", res.text)
        self.assertEqual(self.h.state()["recon"]["R1"]["status"], "in_flight")  # not recorded
        calc.write_text(was)                                   # restored: the gate opens again
        self.assertIn("done", self.record().out)

    def test_an_untouched_workspace_records_normally(self) -> None:
        self.assertIn("done", self.record().out)


class ScopeBudgetWarnsTest(unittest.TestCase):
    """A research estimate that takes the whole budget is information for the human, not a
    refusal: budgets forecast, they never gate (never shrink the research to fit one)."""

    def test_the_check_warns_and_confirms_instead_of_refusing(self) -> None:
        h = Harness()
        try:
            h.init()
            h.write_json("scope.json", h.scope(
                budget_minutes=20,                                   # 60 agent-min on 3 lanes ≈ 20 min
                participants=RESEARCH_PARTS,
                research={"budget_minutes": 60, "why": "The epic is thin and the survey sizes nothing."}))
            res = h.tp("scope", "check")                             # expect 0: a warning, not an error
            self.assertIn("WARN", res.out)
            self.assertIn("never shrink the research to fit", res.out)
            h.tp("scope", "confirm", "--answer", "yes — honest forecast")
            self.assertEqual(h.state()["phase"], "PLANNING")
        finally:
            h.close()


class ReapprovalKeepsBaselinesTest(unittest.TestCase):
    """After `tp revise` and a second approval, the review must still diff against the state
    the run started from — not a HEAD that already holds the run's own committed work."""

    def setUp(self) -> None:
        self.h = h = Harness()
        self.app = h.root / "app"
        self.app.mkdir()
        (self.app / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        git(self.app, "init", "-q", "-b", "main")
        git(self.app, "add", "-A")
        git(self.app, "commit", "-q", "-m", "init")
        scope = dict(CODE, review="none",
                     workspaces=[{"name": "app", "path": str(self.app), "mode": "write"}])
        task = {"id": "T01", "title": "mul", "serves": ["D1"], "agent": "code-author", "workspace": "app",
                "paths": ["calc.py", "test_calc.py"], "sources": ["app:calc.py"],
                "brief": "Add mul(a, b) beside add.", "acceptance": ["mul(2, 3) == 6"],
                "test_cmd": "python3 -m unittest -q test_calc", "tests_paths": ["test_calc.py"],
                "checks": [], "estimate_min": 10, "depends_on": []}
        h.approved(plan=h.plan([task], final_checks=[]), **scope)
        h.tp("dispatch", "T01")                                     # tests step, red
        (self.app / "test_calc.py").write_text(TEST_PY)
        h.result("T01", "tests", changed=["test_calc.py"])
        h.tp("record", "T01")
        h.tp("dispatch", "T01")                                     # impl step, green
        (self.app / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n")
        h.result("T01", "impl", changed=["calc.py"])
        h.tp("record", "T01")
        h.tp("accept", "T01", "--note", "ok")
        git(self.app, "add", "-A")                                  # the accepted work, committed
        git(self.app, "commit", "-q", "-m", "mul")

    def tearDown(self) -> None:
        self.h.close()

    def test_the_second_approval_diffs_against_the_first_baseline(self) -> None:
        first = self.h.state()["write_baseline"]["app"]
        self.h.tp("revise", "--feedback", "one more acceptance criterion")   # back to PLANNING
        self.h.tp("plan", "check")
        self.h.tp("plan", "submit")
        self.h.tp("approve", "--answer", "approve again")
        self.assertEqual(self.h.state()["write_baseline"]["app"], first)


class CloseoutBulkAndChatterTest(unittest.TestCase):
    """Classifying noticed items one `--item` call at a time buried the human decision under
    manager bookkeeping; and agents' notes about their own work never needed the human at
    all — the script classifies that chatter as observations itself."""

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

    def test_items_classifies_a_range_in_one_call(self) -> None:
        self.run_to_closeout(["webhookauth.go still writes admission-webhook.yaml non-atomically.",
                              "docs still say the kubelet dir is kept when it is not.",
                              "the runbook never mentions the CRD.",
                              "old flag --verbose is undocumented."])
        out = self.h.tp("closeout", "--items", "2,3-4", "--class", "observation").out
        self.assertIn("items #2, #3, #4", out)
        self.assertIn("observation", out)
        listing = self.h.tp("closeout").out
        self.assertIn("4 noticed item(s), 3 classified", listing)  # one call classified three
        self.assertIn("1. [UNCLASSIFIED] (T01) webhookauth.go", listing)  # item 1 still open
        self.assertIn("no noticed item", self.h.tp("closeout", "--items", "9", "--class", "observation",
                                                   expect=2).text)

    def test_chatter_about_an_agents_own_work_is_classified_for_the_manager(self) -> None:
        self.run_to_closeout(["webhookauth.go still writes admission-webhook.yaml non-atomically.",
                              "Implementation note: renamed the helper for clarity.",
                              "FYI the sibling task's file was left untouched."])
        out = self.h.tp("closeout").out
        self.assertIn("2 automatically as observations", out)     # the script classified the chatter
        self.assertNotIn("renamed the helper", out)                # classified chatter is not listed
        self.assertNotIn("left untouched", out)                     # the FYI note likewise
        self.assertIn("1. [UNCLASSIFIED] (T01) webhookauth.go", out)  # the real gap still is
        self.h.tp("closeout", "--item", "1", "--class", "observation")
        self.assertEqual(self.h.next()["actions"][0]["action"], "final")  # chatter no longer blocks the gate

    def test_the_ask_options_offer_fixing_now(self) -> None:
        self.run_to_closeout(["webhookauth.go still writes admission-webhook.yaml non-atomically."])
        self.h.tp("closeout", "--item", "1", "--class", "deferred",
                  "--note", "a crash mid-write can tear the admission config the apiserver reads.")
        out = self.h.tp("closeout", "--ask").out
        self.assertIn("fix them now", out)                         # reopen beats "extend the run"
        self.assertIn("accept the deferral", out)


class ReviewSharedFilesTest(unittest.TestCase):
    """A reviewer's time goes into the code, not into re-deriving the change: the dispatch
    hands it one plain diff (tracked changes, then new files in full) and the logs the
    pipeline itself produced when it ran the task's tests and checks."""

    def setUp(self) -> None:
        self.h = h = Harness()
        self.app = h.root / "app"
        self.app.mkdir()
        (self.app / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        git(self.app, "init", "-q", "-b", "main")
        git(self.app, "add", "-A")
        git(self.app, "commit", "-q", "-m", "init")
        scope = dict(CODE, review="final",
                     participants=CODE["participants"] + [{"agent": "test-reviewer", "role": "reviewer",
                                                           "why": "Reviews the finished tests."}],
                     workspaces=[{"name": "app", "path": str(self.app), "mode": "write"}])
        task = {"id": "T01", "title": "mul", "serves": ["D1"], "agent": "code-author", "workspace": "app",
                "paths": ["calc.py", "test_calc.py"], "sources": ["app:calc.py"],
                "brief": "Add mul(a, b) beside add.", "acceptance": ["mul(2, 3) == 6"],
                "test_cmd": "python3 -m unittest -q test_calc", "tests_paths": ["test_calc.py"],
                "checks": [], "estimate_min": 10, "depends_on": []}
        h.approved(plan=h.plan([task], final_checks=[]), **scope)
        h.tp("dispatch", "T01")
        (self.app / "test_calc.py").write_text(TEST_PY)
        h.result("T01", "tests", changed=["test_calc.py"])
        h.tp("record", "T01")
        h.tp("dispatch", "T01")
        (self.app / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n")
        h.result("T01", "impl", changed=["calc.py"])
        h.tp("record", "T01")
        h.tp("accept", "T01", "--note", "ok")
        h.tp("dispatch", "B1/test-reviewer")

    def tearDown(self) -> None:
        self.h.close()

    def test_the_brief_names_one_diff_file_and_the_pipelines_logs(self) -> None:
        brief = (self.h.wf / "runs" / "B1" / "brief-test-reviewer-1.md").read_text()
        self.assertIn("change.diff", brief)
        self.assertIn("instead of running git yourself", brief)
        self.assertIn("tests-", brief)                              # the log of the red/green run
        self.assertIn("re-running the suite", brief)
        diff = (self.h.wf / "runs" / "B1" / "change.diff").read_text()
        self.assertIn("def mul", diff)                              # the tracked change, already rendered
        self.assertIn("test_calc.py", diff)                         # the new file, in full

    def test_the_working_rules_travel_in_every_brief(self) -> None:
        brief = (self.h.wf / "runs" / "B1" / "brief-test-reviewer-1.md").read_text()
        self.assertIn("Batch independent reads", brief)
        self.assertIn("Read each region once", brief)


class ReposTest(unittest.TestCase):
    """Citations resolve in every workspace: documents describe the code the run is
    changing, which lives in a write workspace."""

    def test_write_workspaces_resolve_too(self) -> None:
        from pipeline import run
        repos = run._repos({"workspaces": [{"name": "app", "path": "/x", "mode": "write"},
                                           {"name": "src", "path": "/y", "mode": "read"}]})
        self.assertEqual(set(repos), {"app", "src"})


if __name__ == "__main__":
    unittest.main()
