"""The improvement round from task-pipeline-improvements.md: widen, budget honesty,
lost agents, safe path expansion, the additive tests gate, final-check cwd, explicit
budgets, and the parked-patch triage hint."""
from __future__ import annotations

import json
import sys
import time
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


def set_state(h: Harness, **fields) -> None:
    p = h.wf / ".tp" / "state.json"
    st = json.loads(p.read_text())
    st.update(fields)
    p.write_text(json.dumps(st, indent=1))


class BudgetReportingTest(unittest.TestCase):
    """Budgets are reporting metadata the manager sizes itself — never a human question,
    never a gate, never a reason to cut work. Time vs estimate feeds stall detection only."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved(budget_minutes=200)

    def tearDown(self) -> None:
        self.h.close()

    def test_next_never_warns_about_the_budget_and_still_reports_the_meter(self) -> None:
        set_state(self.h, agent_minutes=999.0)
        out = self.h.next()
        self.assertEqual([w for w in out["warnings"] if "budget" in w.lower()], [])
        self.assertIn("999", self.h.tp("next").out.splitlines()[0])

    def test_dispatch_does_not_gate_on_the_budget(self) -> None:
        set_state(self.h, agent_minutes=999.0)
        self.h.tp("dispatch", "T01")     # the right solution lands even when the meter is over
        self.assertIn("T01", self.h.state()["in_flight"])

    def test_budget_extend_is_metadata_not_an_approval(self) -> None:
        self.h.tp("budget", "extend", "--minutes", "100", "--note", "manager re-estimate after scoping.")
        self.assertEqual(json.loads((self.h.wf / "scope.json").read_text())["budget_minutes"], 300)
        self.assertIn("manager re-estimate", (self.h.wf / "decisions.md").read_text())
        self.h.tp("budget", "extend", "--minutes", "50", "--answer", "Sure, take more.")  # human may volunteer
        self.assertEqual(json.loads((self.h.wf / "scope.json").read_text())["budget_minutes"], 350)

    def test_headline_shows_net_of_dead_minutes(self) -> None:
        set_state(self.h, agent_minutes=100.0, dead_minutes=40.0)
        self.assertIn("60", self.h.tp("next").out.splitlines()[0])


class LostTest(unittest.TestCase):
    """T5/T3a: a lost dispatch is a first-class path that freezes its dead clock."""

    def setUp(self) -> None:
        self.h = h = Harness()
        h.approved(budget_minutes=300)

    def tearDown(self) -> None:
        self.h.close()

    def test_lost_task_blocks_freezes_clock_and_redispatches(self) -> None:
        self.h.tp("dispatch", "T01")
        out = self.h.tp("lost", "T01", "--summary", "Harness restart killed the session; no result.").out
        self.assertIn("re-dispatch", out)
        st = self.h.state()
        self.assertEqual(st["tasks"]["T01"]["status"], "blocked")
        self.assertEqual(st["tasks"]["T01"]["blocked"]["kind"], "exception")
        self.assertNotIn("T01", st["in_flight"])
        self.assertGreaterEqual(st["dead_minutes"], 0.0)
        # the human's answer re-opens it; a fresh dispatch is possible again
        self.h.tp("resolve", "--task", "T01", "--action", "retry", "--answer", "Re-run it.")
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "needs_fix")
        self.h.tp("dispatch", "T01")

    def test_lost_needs_an_in_flight_task(self) -> None:
        self.h.tp("lost", "T01", "--summary", "nothing in flight", expect=2)

    def test_record_dead_minutes_deducts_stall_clock(self) -> None:
        self.h.tp("dispatch", "T01")
        time.sleep(4)  # real in-flight wall clock, so --dead-minutes has something to freeze
        self.h.good_article("architecture/overview.md")
        self.h.result("T01", "author", changed=["architecture/overview.md"])
        self.h.tp("record", "T01", "--agent-id", "a-1", "--dead-minutes", "10")
        st = self.h.state()
        # frozen, capped at the elapsed clock (the meter keeps 0.1-min granularity)
        self.assertGreaterEqual(st["dead_minutes"], 0.05)
        # the meter never sees the frozen minutes: with the whole hand-back frozen it reads zero
        self.assertEqual(self.h.next()["agent_minutes"], 0.0)


class WidenTest(unittest.TestCase):
    """T1: a mechanical write-set growth, allowed even on accepted tasks."""

    def setUp(self) -> None:
        self.h = h = Harness()
        h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def test_widen_accepted_task_grows_plan_and_snapshot(self) -> None:
        self.h.author("T01", "architecture/overview.md", agent_id="a-1")
        self.h.tp("accept", "T01", "--note", "good")
        out = self.h.tp("widen", "T01", "--path", "architecture/glossary.md",
                        "--reason", "Review finding F1 pins the glossary cross-reference.").out
        self.assertIn("widen", out)
        plan = self.h.read_json("plan.json")
        self.assertIn("architecture/glossary.md", plan["tasks"][0]["paths"])
        snap = json.loads((self.h.wf / "plan.approved.json").read_text())
        self.assertIn("architecture/glossary.md", snap["tasks"][0]["paths"])
        self.assertIn("glossary", (self.h.wf / "decisions.md").read_text())
        # the widened file is now a legal write for a later fix round
        self.h.tp("resolve", "--task", "T01", "--action", "reopen", "--answer", "F1 needs the glossary.")
        self.h.tp("dispatch", "T01")
        self.h.good_article("architecture/glossary.md", title="Glossary")
        self.h.result("T01", "fix", changed=["architecture/glossary.md"])
        self.assertNotIn("outside this task's paths", self.h.tp("record", "T01", "--agent-id", "a-1").out)

    def test_widen_rejects_paths_of_a_live_task(self) -> None:
        self.h.tp("widen", "T01", "--path", "build/guide.md", "--reason", "collides",
                  expect=2)

    def test_widen_requires_executing_and_a_real_task(self) -> None:
        self.h.tp("widen", "T99", "--path", "x.md", "--reason", "no such task", expect=2)
        st = self.h.state()
        st["phase"] = "PLANNING"
        (self.h.wf / ".tp" / "state.json").write_text(json.dumps(st, indent=1))
        self.h.tp("widen", "T01", "--path", "x.md", "--reason", "wrong phase", expect=2)


class ExpandTest(unittest.TestCase):
    """T4: paths name files; bare catch-alls are rejected at plan check and huge
    expansions at dispatch; ignored trees never enter the expansion."""

    def setUp(self) -> None:
        self.h = h = Harness()
        self.h.confirmed()

    def tearDown(self) -> None:
        self.h.close()

    def plan_with(self, paths: list) -> None:
        self.h.write_json("plan.json", self.h.plan([self.h.task("T01", paths[0], paths=paths)]))

    def test_plan_check_rejects_dot_and_bare_globs(self) -> None:
        for bad in (["."], ["**"], ["./"], ["**/*"]):
            with self.subTest(paths=bad):
                self.plan_with(bad)
                self.assertIn("names the whole workspace",
                              self.h.tp("plan", "check", expect=2).text)

    def test_huge_expansion_is_refused_at_dispatch_with_guidance(self) -> None:
        d = self.h.kb / "gen"
        d.mkdir()
        for i in range(210):
            (d / f"f{i:03}.md").write_text("x\n")
        self.plan_with(["gen/**", "architecture/overview.md"])
        self.h.tp("plan", "check")
        self.h.tp("plan", "submit")
        self.h.tp("approve", "--answer", "ok")
        err = self.h.tp("dispatch", "T01", expect=2).text
        self.assertIn("gen", err)
        self.assertIn("file", err)

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
    """T6: the impl gate allows additive test growth and still refuses weakening."""

    def setUp(self) -> None:
        self.h = h = Harness()
        self.app = h.root / "app"
        self.app.mkdir()
        (self.app / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        git(self.app, "init", "-q", "-b", "main")
        git(self.app, "add", "-A")
        git(self.app, "commit", "-q", "-m", "init")
        scope = dict(CODE, workspaces=[{"name": "app", "path": str(self.app), "mode": "write"}])
        task = {"id": "T01", "title": "mul", "serves": ["D1"], "agent": "code-author", "workspace": "app",
                "paths": ["calc.py", "test_calc.py"], "sources": ["app:calc.py"],
                "brief": "Add mul(a, b) beside add.", "acceptance": ["mul(2, 3) == 6"],
                "test_cmd": "python3 -m unittest -q test_calc", "tests_paths": ["test_calc.py"],
                "checks": [], "estimate_min": 10, "depends_on": []}
        self.approve = lambda: h.approved(h.plan([task], final_checks=[]), **scope)

    def tearDown(self) -> None:
        self.h.close()

    def _tests_step(self) -> None:
        self.h.tp("dispatch", "T01")
        (self.app / "test_calc.py").write_text(TEST_PY)
        self.h.result("T01", "tests", changed=["test_calc.py"])
        self.h.tp("record", "T01", "--agent-id", "ta-1")
        self.h.tp("dispatch", "T01")

    def _impl_record(self) -> str:
        (self.app / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n")
        self.h.result("T01", "impl", changed=["calc.py", "test_calc.py"])
        return self.h.tp("record", "T01", "--agent-id", "ca-1").out

    def test_adding_a_test_passes_the_gate(self) -> None:
        self.approve()
        self._tests_step()
        (self.app / "test_calc.py").write_text(TEST_PY +
                                               "\n    def test_mul_commutes(self):\n"
                                               "        self.assertEqual(mul(3, 2), 6)\n")
        out = self._impl_record()
        self.assertIn("green", out)
        self.assertNotIn("tests changed", out)
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "needs_check")

    def test_weakening_a_test_still_fails_the_gate(self) -> None:
        self.approve()
        self._tests_step()
        (self.app / "test_calc.py").write_text(
            "import unittest\nfrom calc import mul\n\nclass T(unittest.TestCase):\n"
            "    def test_mul(self):\n        self.assertTrue(mul(2, 3) is not None)\n")
        out = self._impl_record()
        self.assertIn("tests changed", out)
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "needs_fix")


class FinalCheckTest(unittest.TestCase):
    """T7: a final check may pin an absolute cwd; final_checks are amendable."""

    def setUp(self) -> None:
        self.h = h = Harness()
        self.target = h.root / "elsewhere"
        self.target.mkdir()

    def tearDown(self) -> None:
        self.h.close()

    def plan_with_cwd(self) -> dict:
        return self.h.plan(checks={"elsewhere": {"cmd": "test -f marker.txt", "cwd": str(self.target)}},
                           final_checks=["elsewhere"])

    def test_final_check_accepts_absolute_cwd(self) -> None:
        (self.target / "marker.txt").write_text("x\n")
        self.h.approved(self.plan_with_cwd())
        self.h.author("T01", "architecture/overview.md", agent_id="a-1")
        self.h.author("T02", "build/guide.md", agent_id="a-2")
        self.h.tp("accept", "T01", "--note", "ok")
        self.h.tp("accept", "T02", "--note", "ok")
        self.h.author("T03", "index.md", agent_id="a-3")
        self.h.tp("accept", "T03", "--note", "ok")
        out = self.h.tp("final").out
        self.assertIn("DONE", out)

    def test_final_checks_are_amendable_while_executing(self) -> None:
        (self.target / "marker.txt").write_text("x\n")
        self.h.approved(self.plan_with_cwd())
        self.h.author("T01", "architecture/overview.md", agent_id="a-1")
        self.h.author("T02", "build/guide.md", agent_id="a-2")
        self.h.tp("accept", "T01", "--note", "ok")
        self.h.tp("accept", "T02", "--note", "ok")
        self.h.author("T03", "index.md", agent_id="a-3")
        self.h.tp("accept", "T03", "--note", "ok")
        plan = self.h.read_json("plan.json")
        plan["final_checks"] = []
        self.h.write_json("plan.json", plan)
        self.h.tp("amend", "--reason", "the human approved dropping the check for this run")
        self.h.tp("final")


class ScopeBudgetTest(unittest.TestCase):
    """A null budget is fine: the manager sizes budgets itself, and never asks the human."""

    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def test_null_budget_needs_nothing_from_the_human(self) -> None:
        self.h.init()
        self.h.write_json("scope.json", self.h.scope(budget_minutes=None))
        self.h.tp("scope", "check")     # no budget_declined, no question: budgets are metadata
        self.assertIn("none set", (self.h.wf / "scope.md").read_text())


class TriageHintTest(unittest.TestCase):
    """O1: triage points at a parked impl patch when the blocked task left one behind."""

    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def review_file(self, session: str, n: int, verdict: str, findings: list) -> None:
        batch, reviewer = session.split("/")
        d = self.h.wf / "runs" / batch
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{reviewer}-{n}.json").write_text(json.dumps(
            {"batch": batch, "verdict": verdict, "findings": findings}))

    def test_hint_mentions_the_parked_patch(self) -> None:
        h = self.h
        scope = dict(
            deliverables=[{"id": "D1", "kind": "kb", "what": "articles", "where": "kb"}],
            participants=[{"agent": "kb-author", "role": "author", "why": "Writes every article for D1."},
                          {"agent": "doc-reviewer", "role": "reviewer", "why": "Reviews D1's articles."}],
            review="final",
        )
        plan = h.plan([h.task("T01", "architecture/overview.md")],
                      review_batches=[{"id": "B1", "tasks": ["T01"]}])
        h.approved(plan, **scope)
        h.author("T01", "architecture/overview.md", agent_id="a-1")
        h.tp("accept", "T01", "--note", "ok")
        h.tp("dispatch", "B1/doc-reviewer")
        self.review_file("B1/doc-reviewer", 1, "changes",
                         [{"id": "F1", "state": "wrong", "blocking": True,
                           "where": "architecture/overview.md:3",
                           "issue": "Wrong claim.", "fix": "Fix it."}])
        h.tp("record", "B1/doc-reviewer", "--agent-id", "rev-1")
        parked = h.run_dir("T01") / "impl-1.patch"
        parked.write_text("--- a\n+++ b\n")
        out = h.tp("triage", "B1/doc-reviewer", "--accept-all").out
        self.assertIn("impl-1.patch", out)


if __name__ == "__main__":
    unittest.main()
