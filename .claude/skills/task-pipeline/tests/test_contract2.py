"""Contract 2 — what new runs do differently, each traced to a measured cost in real runs:

- questions are settled with the human before the plan, and asking never stops the run
  (blocking questions held hand-backs unrecorded for 8 to 42 hours);
- an independent plan review, bound to the exact plan revision, replaces the human's approval;
- a requirements ledger the plan must cover (a run narrowed "per managed node" to one node);
- fused code rounds whose red run the pipeline itself observes (`tp red`);
- routine mechanics the manager settles without the human (test corrections, false gates, widen);
- gates that stop failing on noise (sandbox placeholders, siblings dispatched later, HEAD moves);
- a workflow from before contract 2 keeps its human approval."""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from harness import Harness, git
from scenarios import CALC_MUL_PY, TEST_PY, Mixed


class RequirementsLedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def test_a_new_scope_needs_the_ledger(self) -> None:
        h = self.h
        h.init()
        scope = h.scope()
        del scope["requirements"]
        h.write_json("scope.json", scope)
        self.assertIn("requirements", h.tp("scope", "check", expect=2).text)

    def test_a_paraphrased_source_is_flagged(self) -> None:
        h = self.h
        h.init()
        h.write_json("scope.json", h.scope(requirements=[
            {"id": "R1", "text": "A KB", "source": "a knowledge base for every repo", "deliverables": ["D1"]}]))
        self.assertIn("not found verbatim", h.tp("scope", "check").out)

    def test_every_requirement_needs_a_task_and_plan_md_shows_coverage(self) -> None:
        h = self.h
        h.confirmed(requirements=[
            {"id": "R1", "text": "A KB for the calc repo", "source": "Build a KB for the calc repo",
             "deliverables": ["D1"]},
            {"id": "R2", "text": "An index of every article", "source": "Build a KB", "deliverables": ["D1"]}])
        h.write_json("plan.json", h.plan())
        self.assertIn("R2 (An index of every article) is served by no task", h.tp("plan", "check", expect=2).text)
        plan = h.plan()
        plan["tasks"][2]["requirements"] = ["R1", "R2"]
        h.write_json("plan.json", plan)
        h.tp("plan", "check")
        md = (h.wf / "plan.md").read_text()
        self.assertIn("## Requirement coverage", md)
        self.assertIn("| R2 — An index of every article | T03 |", md)
        self.assertIn("## Deliverable coverage", md)


class QuestionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def test_open_questions_and_plan_questions_block_submit(self) -> None:
        h = self.h
        h.confirmed()
        out = h.tp("ask", "--question", "Should the KB cover the build scripts too?").out
        self.assertIn("Q1", out)
        h.write_json("plan.json", h.plan(questions=["Cover the build scripts?"]))
        h.tp("plan", "check")
        text = h.tp("plan", "submit", expect=2).text
        self.assertIn("Q1 is still open", text)
        self.assertIn("plan.json still lists `questions`", text)
        h.tp("answer", "Q1", "--answer", "Yes, the build scripts too.")
        h.write_json("plan.json", h.plan())
        h.tp("plan", "check")
        self.assertIn("Settled with the human", (h.wf / "plan.md").read_text())
        h.tp("plan", "submit")
        self.assertIn("Yes, the build scripts too.", (h.wf / "clarifications.md").read_text())

    def test_a_mid_run_question_parks_only_its_task_and_is_measured(self) -> None:
        h = self.h
        h.approved()
        h.tp("dispatch", "T01")
        h.result("T01", "author", status="needs_input", questions=["Which build tool is canonical?"])
        h.tp("record", "T01")
        out = h.tp("ask", "--about", "T01", "--question", "Which build tool is canonical, make or mage?").out
        self.assertIn("plain text", out)  # never AskUserQuestion mid-run
        nxt = h.tp("next").out
        self.assertIn("waiting on the human: Q1 (T01)", nxt)
        self.assertIn("dispatch T02", nxt)  # the rest keeps moving
        self.assertNotIn("Needs a decision", nxt)  # the parked item is one short line, not the guide
        h.tp("answer", "Q1", "--answer", "make")
        report = json.loads((h.wf / ".tp" / "state.json").read_text())["questions"]["Q1"]
        self.assertIn("waited_min", report)


class PlanReviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = h = Harness()
        h.confirmed()
        h.tp("ask", "--question", "Should the KB cover the build scripts too?")
        h.tp("answer", "Q1", "--answer", "Yes, the build scripts too.")
        h.write_json("plan.json", h.plan())
        h.tp("plan", "check")
        h.tp("plan", "submit")

    def tearDown(self) -> None:
        self.h.close()

    def finding(self, fid="F1", **over):
        f = {"id": fid, "state": "narrowed", "requirement": "R1",
             "issue": "T01 covers only the overview, not the build the request names.", "fix": "Add the build."}
        f.update(over)
        return f

    def test_the_gate_is_the_review_not_the_human(self) -> None:
        h = self.h
        self.assertEqual(h.next()["actions"][0]["action"], "plan_review")
        self.assertIn("plan review is pending", h.tp("approve", expect=2).text)
        out = h.tp("plan", "review").out
        self.assertIn('Agent(subagent_type="plan-reviewer"', out)
        brief = (h.wf / "runs" / "plan" / "brief-review-1.md").read_text()
        self.assertIn("Build a KB for the calc repo.", brief)              # the request, verbatim
        self.assertIn("source: “Build a KB for the calc repo”", brief)     # the ledger, with its words
        self.assertIn("Yes, the build scripts too.", brief)                # the human's answers
        self.assertIn("Narrowing", brief)
        h.plan_review_pass()
        self.assertEqual(h.next()["actions"][0]["action"], "approve")
        h.tp("approve")
        self.assertEqual(h.state()["phase"], "EXECUTING")
        self.assertIn("independent plan review passed", (h.wf / "decisions.md").read_text())

    def test_malformed_verdicts_go_back_to_the_reviewer(self) -> None:
        h = self.h
        res = h.plan_review_pass(verdict="changes", record=False)
        self.assertIn("nothing to fix", res.text)                        # changes with no finding
        res = h.plan_review_pass(verdict="pass", findings=[self.finding()], record=False)
        self.assertIn("contradictory", res.text)                         # pass with a finding
        res = h.plan_review_pass(verdict="changes", findings=[{"issue": "something is off here"}], record=False)
        self.assertIn("must be unique and look like F1", res.text)       # never a KeyError
        self.assertEqual(h.state()["plan_review"]["status"], "in_flight")

    def test_an_uncovered_requirement_is_a_finding(self) -> None:
        h = self.h
        out = h.plan_review_pass(verdict="changes", findings=[self.finding()],
                                 coverage=[{"requirement": "R1", "covered": False}]).out
        self.assertIn("1 finding", out)
        self.assertEqual(h.state()["plan_review"]["status"], "needs_triage")

    def test_a_dismissal_goes_back_to_the_same_reviewer_never_self_approves(self) -> None:
        h = self.h
        h.plan_review_pass(verdict="changes", findings=[self.finding()])
        h.tp("plan", "triage", "--dismiss", "F1=The build is covered by T02, which the reviewer missed.")
        self.assertEqual(h.state()["plan_review"]["status"], "changes")
        self.assertIn("plan review is changes", h.tp("approve", expect=2).text)
        h.tp("plan", "check")
        h.tp("plan", "submit")
        out = h.tp("plan", "review").out
        self.assertIn('SendMessage(to="plan-rev-1"', out)                # the same reviewer, resumed
        brief = (h.wf / "runs" / "plan" / "brief-review-2.md").read_text()
        self.assertIn("the manager dismissed it: The build is covered by T02", brief)

    def test_rounds_run_out_to_the_human_and_revise_starts_afresh(self) -> None:
        h = self.h
        for _ in range(3):
            h.plan_review_pass(verdict="changes", findings=[self.finding()])
            h.tp("plan", "triage", "--accept-all")
            h.tp("plan", "check")
            h.tp("plan", "submit")
        self.assertEqual(h.next()["actions"][0]["action"], "human")
        self.assertIn("3 independent review rounds", h.tp("plan", "review", expect=2).text)
        h.tp("revise", "--feedback", "Merge the two articles into one.")
        h.tp("plan", "check")
        h.tp("plan", "submit")
        h.plan_review_pass()                                             # round 1 again, not refused
        self.assertEqual(h.state()["plan_review"]["round"], 1)

    def test_a_plan_changed_during_review_is_not_approved(self) -> None:
        h = self.h
        h.tp("plan", "review")
        plan = h.read_json("plan.json")
        plan["summary"] = "Changed while under review."
        h.write_json("plan.json", plan)
        res = h.plan_review_pass(record=False)
        self.assertIn("changed while it was under review", res.text)


class LegacyContractTest(unittest.TestCase):
    def test_a_workflow_from_before_contract_2_keeps_its_human_approval(self) -> None:
        h = Harness(legacy=True)
        try:
            h.confirmed()                                                # no ledger needed
            h.write_json("plan.json", h.plan())
            h.tp("plan", "check")
            h.tp("plan", "submit")
            self.assertEqual(h.next()["actions"][0]["action"], "human")
            self.assertIn("predates", h.tp("plan", "review", expect=2).text)
            self.assertIn("--answer", h.tp("approve", expect=2).text)
            h.tp("approve", "--answer", "approve")
            h.author("T01", "architecture/overview.md")
            self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_check")
        finally:
            h.close()


class FusedBuildTest(unittest.TestCase):
    def setUp(self) -> None:
        self.m = m = Mixed()
        self.h = m.h
        scope = m.scope(["code"], ["code", "correctness"])
        scope["split_tests"] = False
        m.approve([m.code_task()], scope)

    def tearDown(self) -> None:
        self.m.close()

    def red_cmd(self):
        return ["red", "T01"]

    def test_one_agent_tests_first_then_code_with_the_red_run_observed(self) -> None:
        h, m = self.h, self.m
        act = h.next()["actions"][0]
        self.assertEqual((act["step"], act["agent"]), ("build", "code-author"))
        h.tp("dispatch", "T01")
        brief = (h.run_dir("T01") / "brief-build-0.md").read_text()
        self.assertIn(" red T01", brief)
        self.assertIn("no test file has changed", h.tp(*self.red_cmd(), expect=2).text)
        (m.app / "test_calc.py").write_text(TEST_PY)
        (m.app / "calc.py").write_text(CALC_MUL_PY)
        self.assertIn("production files differ", h.tp(*self.red_cmd(), expect=2).text)
        git(m.app, "checkout", "calc.py")
        self.assertIn("red recorded", h.tp(*self.red_cmd()).out)
        (m.app / "calc.py").write_text(CALC_MUL_PY)
        h.result("T01", "build", changed=["calc.py", "test_calc.py"])
        out = h.tp("record", "T01", "--agent-id", "ca-1").out
        self.assertIn("green", out)
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_check")

    def test_the_printed_red_command_runs_as_written(self) -> None:
        # The code author copies the command from its brief: it must run as printed (and, when the
        # skill is installed, match the documented allow rule `python3 ~/.claude/skills/...`).
        import re
        import subprocess
        h, m = self.h, self.m
        h.tp("dispatch", "T01")
        brief = (h.run_dir("T01") / "brief-build-0.md").read_text()
        cmd = re.search(r"Run `([^`]+ red T01)`", brief).group(1)
        self.assertTrue(cmd.startswith("python3 "))
        (m.app / "test_calc.py").write_text(TEST_PY)
        proc = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("red recorded", proc.stdout)

    def test_the_red_command_uses_the_allow_rule_form_when_installed(self) -> None:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from pipeline import run
        from pipeline.common import Workflow
        installed = Path("~/.claude/skills/task-pipeline/scripts/tp.py").expanduser()
        saved = run.TP_SCRIPT
        try:
            run.TP_SCRIPT = installed
            cmd = run.tp_command(Workflow(self.h.wf), "red", "T01")
        finally:
            run.TP_SCRIPT = saved
        self.assertTrue(cmd.startswith("python3 ~/.claude/skills/task-pipeline/scripts/tp.py -w "), cmd)

    def test_a_build_without_the_red_run_is_sent_back(self) -> None:
        h, m = self.h, self.m
        h.tp("dispatch", "T01")
        (m.app / "test_calc.py").write_text(TEST_PY)
        (m.app / "calc.py").write_text(CALC_MUL_PY)
        h.result("T01", "build", changed=["calc.py", "test_calc.py"])
        self.assertIn("red run was never recorded", h.tp("record", "T01", "--agent-id", "ca-1").out)
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_fix")

    def test_a_failed_build_is_fixed_without_a_second_red_run(self) -> None:
        # The OpenCode variant demands a fresh red log in every fix round of a fused build, so a
        # correct fix still fails until the task blocks; red is observed once, at the start.
        h, m = self.h, self.m
        h.tp("dispatch", "T01")
        (m.app / "test_calc.py").write_text(TEST_PY)
        h.tp(*self.red_cmd())
        (m.app / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a + b\n")
        h.result("T01", "build", changed=["calc.py", "test_calc.py"])
        self.assertIn("not green", h.tp("record", "T01", "--agent-id", "ca-1").out)
        out = h.tp("dispatch", "T01").out
        self.assertIn('SendMessage(to="ca-1"', out)                       # the same author, resumed
        (m.app / "calc.py").write_text(CALC_MUL_PY)
        h.result("T01", "fix", changed=["calc.py"])
        out = h.tp("record", "T01").out
        self.assertIn("green", out)
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_check")

    def test_tests_that_pass_before_the_code_are_not_red(self) -> None:
        h, m = self.h, self.m
        h.tp("dispatch", "T01")
        (m.app / "test_calc.py").write_text("import unittest\n\nclass T(unittest.TestCase):\n"
                                            "    def test_nothing(self):\n        pass\n")
        self.assertIn("not red", h.tp(*self.red_cmd(), expect=2).text)


class ExistingTestsTest(unittest.TestCase):
    def test_a_removal_proves_itself_with_the_existing_tests(self) -> None:
        # A real run's removal task fought the red gate: tests restored to HEAD pass, by design.
        m = Mixed()
        try:
            (m.app / "test_calc.py").write_text("import unittest\nfrom calc import add\n\n\nclass T(unittest.TestCase):\n"
                                                "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n")
            git(m.app, "add", "-A")
            git(m.app, "commit", "-q", "-m", "tests")
            h = m.h
            m.approve([m.code_task(test_mode="existing", brief="Tidy add's body.")],
                      m.scope(["code"], ["code", "correctness"]))
            self.assertEqual(h.next()["actions"][0]["step"], "build")
            h.tp("dispatch", "T01")
            self.assertIn("existing tests", (h.run_dir("T01") / "brief-build-0.md").read_text())
            (m.app / "calc.py").write_text("def add(a, b):\n    total = a + b\n    return total\n")
            h.result("T01", "build", changed=["calc.py"])
            out = h.tp("record", "T01", "--agent-id", "ca-1").out
            self.assertIn("green", out)
            self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_check")
        finally:
            m.close()


class RoutineAutonomyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def test_accept_takes_a_wave_and_dispatches_what_it_unblocks(self) -> None:
        h = self.h
        h.approved()
        h.follow_on = True
        h.author("T01", "architecture/overview.md")
        h.author("T02", "build/guide.md")
        out = h.tp("accept", "T01", "T02", "--note", "Both cite calc.go:5 correctly.").out
        self.assertIn("accepted T01", out)
        self.assertIn("DISPATCH T03", out)                               # no `tp next` + `tp dispatch`
        self.assertEqual(h.state()["tasks"]["T03"]["status"], "in_flight")

    def test_a_gate_shown_false_is_overridden_with_evidence(self) -> None:
        h = self.h
        h.approved()
        h.tp("dispatch", "T01")
        h.result("T01", "author", changed=[])
        h.tp("record", "T01")                                            # wrote nothing → needs_fix
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_fix")
        self.assertIn("evidence", h.tp("accept", "T01", "--override", "--note", "fine", expect=2).text)
        h.tp("accept", "T01", "--override", "--note", "The article already existed at HEAD and is correct as is.")
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "accepted")
        self.assertEqual(h.state()["overrides"][0]["task"], "T01")
        self.assertIn("over its gate findings", (h.wf / "decisions.md").read_text())

    def test_a_review_finding_is_never_overridden(self) -> None:
        h = self.h
        h.approved()
        h.author("T01", "architecture/overview.md")
        h.tp("accept", "T01", "--note", "Cites calc.go:5 correctly.")
        h.tp("resolve", "--task", "T01", "--action", "reopen", "--answer", "Also cover Sub.", "--by", "manager")
        self.assertIn("not failing a gate", h.tp("accept", "T01", "--override", "--note",
                                                 "The reviewer asked for a section the article already has today.", expect=2).text)


class GateNoiseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def test_sandbox_placeholders_are_not_edits(self) -> None:
        h = self.h
        h.tp("dispatch", "T01")
        h.good_article("architecture/overview.md")
        (h.kb / ".bashrc").write_text("")                                # a deny mount left behind
        (h.kb / ".claude").mkdir()
        (h.kb / ".claude" / "agents").write_text("")
        h.result("T01", "author", changed=["architecture/overview.md"])
        out = h.tp("record", "T01", "--agent-id", "a-1").out
        self.assertNotIn("outside this task's paths", out)
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_check")

    def test_a_non_empty_dotfile_is_still_an_edit(self) -> None:
        h = self.h
        h.tp("dispatch", "T01")
        h.good_article("architecture/overview.md")
        (h.kb / ".env").write_text("TOKEN=x\n")
        h.result("T01", "author", changed=["architecture/overview.md"])
        self.assertIn("outside this task's paths", h.tp("record", "T01").out)

    def test_a_sibling_dispatched_later_is_not_charged_to_this_task(self) -> None:
        h = self.h
        h.tp("dispatch", "T01")
        h.tp("dispatch", "T02")                                          # dispatched after T01
        h.good_article("build/guide.md")                                  # T02's work lands first
        h.good_article("architecture/overview.md")
        h.result("T01", "author", changed=["architecture/overview.md"])
        out = h.tp("record", "T01", "--agent-id", "a-1").out
        self.assertNotIn("outside this task's paths", out)

    def test_a_widened_test_file_joins_the_tests(self) -> None:
        m = Mixed()
        try:
            m.approve([m.code_task()], m.scope(["code"], ["tests", "code", "correctness"]))
            m.h.tp("widen", "T01", "--path", "helpers_test.py", "--reason", "the fixture the finding needs")
            task = m.h.read_json("plan.json")["tasks"][0]
            self.assertIn("helpers_test.py", task["tests_paths"])
        finally:
            m.close()


class HeadMoveTest(unittest.TestCase):
    """A rebase onto upstream during a dispatch is history, not the agent's edit; a local commit is."""

    def setUp(self) -> None:
        self.m = m = Mixed()
        self.up = m.h.root / "upstream.git"
        git(m.h.root, "clone", "-q", "--bare", str(m.app), str(self.up))
        git(m.app, "remote", "add", "origin", str(self.up))
        git(m.app, "fetch", "-q", "origin")
        m.approve([m.doc_task("T01", path="docs/calc.md")], m.scope(["docs"], ["docs", "doc-review"]))
        m.h.tp("dispatch", "T01")

    def tearDown(self) -> None:
        self.m.close()

    def finish(self) -> str:
        m = self.m
        (m.app / "docs").mkdir(exist_ok=True)
        (m.app / "docs" / "calc.md").write_text("# calc\n\n`add` returns a sum (`calc.py:2`).\n")
        m.h.result("T01", "author", changed=["docs/calc.md"])
        return m.h.tp("record", "T01", "--agent-id", "da-1").out

    def rebase_onto_upstream(self) -> None:
        m = self.m
        other = m.h.root / "other"
        git(m.h.root, "clone", "-q", str(self.up), str(other))
        (other / "NEWS.md").write_text("# News\n")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", "upstream work")
        git(other, "push", "-q", "origin", "HEAD:main")
        git(m.app, "pull", "-q", "--rebase", "origin", "main")

    def test_a_declared_rebase_is_excused(self) -> None:
        self.rebase_onto_upstream()
        out = self.m.h.tp("head-moved", "app", "--reason", "the human rebased onto main",
                          "--answer", "I rebased app onto main").out
        self.assertIn("1 commit(s)", out)
        self.assertNotIn("outside this task's paths", self.finish())
        self.assertIn("head moved in app", (self.m.h.wf / "decisions.md").read_text())
        self.assertEqual(len(self.m.h.state()["head_moves"]), 1)

    def test_an_undeclared_move_is_still_flagged(self) -> None:
        # Nothing in the workspace can vouch for a commit (an agent can forge dates and refs).
        self.rebase_onto_upstream()
        self.assertIn("NEWS.md", self.finish())

    def test_a_local_commit_of_another_file_is_still_flagged(self) -> None:
        m = self.m
        (m.app / "NEWS.md").write_text("# News\n")
        git(m.app, "add", "-A")
        git(m.app, "commit", "-q", "-m", "slipped in")
        self.assertIn("NEWS.md", self.finish())


class TriageRouteTest(unittest.TestCase):
    def test_a_comment_finding_never_forces_a_red_test(self) -> None:
        from importlib import import_module
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        run = import_module("pipeline.run")
        task = {"workspace": "app", "serves": ["D1"], "tests_paths": ["test_calc.py"], "paths": ["calc.py"]}
        scope = {"deliverables": [{"id": "D1", "kind": "code"}],
                 "workspaces": [{"name": "app", "path": "/x", "mode": "write"}]}
        f = {"state": "missing", "where": "calc.py:3", "issue": "The doc comment on mul is missing."}
        self.assertEqual(run.fix_route(task, scope, f), "impl")
        f = {"state": "missing", "where": "calc.py:3", "issue": "mul(0, x) returns x, not 0."}
        self.assertEqual(run.fix_route(task, scope, f), "tests-red")
        f["route"] = "impl"
        self.assertEqual(run.fix_route(task, scope, f), "impl")


if __name__ == "__main__":
    unittest.main()
