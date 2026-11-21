"""Ordinary delivery and recovery, using disposable workspaces and scripted review records."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

import test_autonomous as autonomous


class DeliveryTest(unittest.TestCase):
    setUp = autonomous.AutonomousTest.setUp
    tearDown = autonomous.AutonomousTest.tearDown
    cli = autonomous.AutonomousTest.cli
    put = autonomous.AutonomousTest.put
    state = autonomous.AutonomousTest.state
    scope = autonomous.AutonomousTest.scope
    task = autonomous.AutonomousTest.task
    plan = autonomous.AutonomousTest.plan
    result = autonomous.AutonomousTest.result
    automated = autonomous.AutonomousTest.automated
    settle = autonomous.AutonomousTest.settle
    reviewer = autonomous.AutonomousTest.reviewer
    finish_reviewer = autonomous.AutonomousTest.finish_reviewer
    accept = autonomous.AutonomousTest.accept

    def multiplication(self, second=False):
        (self.app / "calc.py").write_text("def mul(a,b): return a+b\n")
        plan = self.automated("red-green", [sys.executable, "-B", "-m", "unittest", "test_calc"])
        plan["tasks"][0]["kind"] = "code"
        if second:
            task = copy.deepcopy(plan["tasks"][0])
            task.update(id="T02", title="Cover zero", depends_on=["T01"],
                        verification=dict(mode="existing", check="unit", reason="Extend existing regression suite."))
            plan["tasks"].append(task)
        self.accept(plan)
        self.cli("start", "T01")
        (self.app / "test_calc.py").write_text(
            "import unittest\nfrom calc import mul\nclass Test(unittest.TestCase):\n"
            " def test_mul(self): self.assertEqual(mul(2,3),6)\n")
        self.cli("test", "T01", "--stage", "red", "--note", "Behavioral failure: 5 != 6.")
        (self.app / "calc.py").write_text("def mul(a,b): return a*b\n")
        self.cli("check", "unit")

    def correction(self, aid="A2"):
        return dict(kind="correction", reason="Preserve original regression while extending the shared suite.",
                    evidence="Original multiplication assertion retained; all tests run and pass.", agent=aid,
                    regression=dict(basis="retained", assertions_unchanged=True, original_checkpoint_valid=True,
                                    evidence="Original red 5 != 6 and original assertion remain valid."))

    def test_ordinary_task_can_correct_pinned_tests_with_review_and_retained_proof(self):
        self.multiplication()
        original = self.state()["tasks"]["T01"]["test_checkpoint"]
        test = self.app / "test_calc.py"
        test.write_text(test.read_text() + "# Explain the unchanged assertion.\n")
        self.cli("check", "unit")
        correction = self.correction()
        self.cli("test-update", "T01", "--file", "-", payload=correction, expect=2)
        self.reviewer(purpose="test-correction", aid="A2", task="T01")
        self.cli("test-update", "T01", "--file", "-", payload=correction)
        self.cli("done", "T01", "--result-file", self.result())
        self.assertEqual(self.state()["tasks"]["T01"]["test_updates"][0]["previous"], original)
        self.assertTrue((self.wf / original["files"]["app:test_calc.py"]).exists())

    def test_later_task_can_review_shared_test_evolution_without_reopening_owner(self):
        self.multiplication(second=True)
        self.cli("done", "T01", "--result-file", self.result())
        original = self.state()["tasks"]["T01"]["test_checkpoint"]
        self.cli("start", "T02")
        test = self.app / "test_calc.py"
        test.write_text(test.read_text() + " def test_zero(self): self.assertEqual(mul(0,3),0)\n")
        self.cli("check", "unit")
        # Green alone cannot approve changed regression coverage.
        self.cli("done", "T02", "--result-file", self.result("T02"), expect=2)
        self.reviewer(purpose="test-correction", aid="A2", task="T01")
        self.cli("test-update", "T01", "--file", "-", payload=self.correction())
        self.assertEqual(self.state()["tasks"]["T01"]["status"], "done")
        self.assertEqual(self.state()["tasks"]["T01"]["test_updates"][0]["previous"], original)
        self.cli("done", "T02", "--result-file", self.result("T02"))
        self.cli("next")
        self.cli("review", "--file", "-", payload=dict(method="self", verdict="pass", summary="Both cases verified.",
                 findings=[], requirements=[dict(id="R1", evidence="Original request and both tasks checked.")]))
        self.cli("final")
        self.assertEqual(self.state()["phase"], "COMPLETE")
        self.assertFalse(any(e["action"] in ("question", "amend", "reopen") for e in self.state()["history"]))

    def test_ordinary_task_can_add_checks_and_paths_without_expanding_outcomes(self):
        self.accept()
        self.cli("start", "T01")
        self.cli("refine", "T01", "--reason", "Verify required companion article.", "--file", "-",
                 payload=dict(paths=["details.md"], checks=dict(article=dict(
                     argv=[sys.executable, "-B", "-c", "from pathlib import Path; assert Path('details.md').read_text()"],
                     workspace="app"))))
        (self.app / "details.md").write_text("Required details.\n")
        self.cli("check", "article")
        self.cli("done", "T01", "--result-file", self.result())
        self.assertEqual(self.state()["tasks"]["T01"]["status"], "done")

    def test_done_verify_runs_only_missing_checks_and_returns_next_action(self):
        marker = self.base / "count"
        plan = self.automated(argv=[sys.executable, "-B", "-c",
            "from pathlib import Path; p=Path(" + repr(str(marker)) + "); p.write_text(p.read_text()+'x' if p.exists() else 'x')"])
        plan["tasks"].append(self.task("T02", "b.md", ["T01"]))
        self.accept(plan)
        self.cli("start", "T01")
        (self.app / "a.md").write_text("Overview.\n")
        output = self.cli("done", "T01", "--verify", "--result-file", self.result())
        self.assertIn("start: T02", output)
        self.assertEqual(marker.read_text(), "x")
        self.cli("start", "T02")
        self.cli("done", "T02", "--verify", "--result-file", self.result("T02"))
        self.assertEqual(marker.read_text(), "x")

    def test_done_verify_failure_keeps_task_running_and_real_log(self):
        self.accept(self.automated(argv=[sys.executable, "-B", "-c", "raise SystemExit(1)"]))
        self.cli("start", "T01")
        self.cli("done", "T01", "--verify", "--result-file", self.result(), expect=2)
        state = self.state()
        self.assertEqual(state["tasks"]["T01"]["status"], "running")
        self.assertIn("unit", state["checks"], "The verification command must actually execute.")
        self.assertEqual(state["checks"]["unit"]["exit_code"], 1)
        self.assertTrue((self.wf / state["checks"]["unit"]["log"]).exists())

    def test_bounded_glob_inputs_do_not_adopt_unrelated_siblings(self):
        for mode in ("walk", "git"):
            with self.subTest(snapshot=mode):
                if mode == "git":
                    subprocess.run(["git", "init", "-q", str(self.app)], check=True)
                (self.app / "src").mkdir(exist_ok=True)
                (self.app / "src/source.py").write_text("one")
                (self.app / "src/archived-log.json").write_text("old")
                scope = self.scope()
                scope["workspaces"][0].update(snapshot=mode, monitor=["a.md"])
                plan = self.automated()
                plan["checks"]["unit"].update(reuse=True, inputs={"app": ["src/**/*.py"]})
                # Each subcase gets a separate pipeline; only disposable fixture roots are reused.
                if mode == "git":
                    self.wf = None
                    output = self.cli("init", str(self.base / "planning"), "--title", "Git boundary",
                                      "--request-file", str(self.request))
                    self.wf = Path(output.splitlines()[0].removeprefix("workflow: "))
                self.accept(plan, scope)
                self.cli("start", "T01")
                self.cli("check", "unit")
                (self.app / "src/archived-log.json").write_text("changed unrelated history")
                self.cli("done", "T01", "--verify", "--result-file", self.result())
                self.assertNotIn("app:src/archived-log.json", self.state()["tasks"]["T01"]["changes"])

    def test_shared_test_growth_covers_multiple_retained_pins_in_one_review(self):
        self.multiplication(second=True)
        self.cli("done", "T01", "--result-file", self.result())
        self.cli("start", "T02")
        # Establish a second genuine characterization pin on the shared file.
        spec = dict(id="F1", reason="Characterize positive multiplication before extending coverage.", criteria=[1],
                    paths=["calc.py", "test_calc.py"], checks=dict(unit=json.loads((self.wf / "plan.json").read_text())["checks"]["unit"]),
                    verification=dict(mode="characterization", check="unit", test_paths=["test_calc.py"], reason="Preserve behavior."))
        # Repair steps must be available for ordinary autonomous tasks too.
        self.cli("repair", "start", "T02", "--file", "-", payload=spec)
        self.cli("repair", "test", "T02", "--id", "F1", "--stage", "pin", "--note", "Original multiplication passes.")
        self.cli("repair", "done", "T02", "--id", "F1", "--file", "-", payload=dict(summary="Characterized.", evidence="Actual green log."))
        test = self.app / "test_calc.py"
        test.write_text(test.read_text() + " def test_zero(self): self.assertEqual(mul(0,3),0)\n")
        self.cli("check", "unit")
        self.reviewer(purpose="test-correction", aid="A2", task="T01")
        self.cli("test-update", "T01", "--file", "-", payload=self.correction())
        self.cli("done", "T02", "--result-file", self.result("T02"))
        state = self.state()
        self.assertEqual(len(state["tasks"]["T01"]["test_updates"]), 1)
        self.assertEqual(len(state["tasks"]["T02"]["repairs"][0]["test_updates"]), 1)

    def test_second_repair_records_red_before_reviewing_shared_suite_evolution(self):
        (self.app / "calc.py").write_text("def mul(a,b): return a+b\ndef sub(a,b): return a+b\n")
        plan = self.plan()
        plan["tasks"][0].update(adaptive=True, paths=["calc.py", "test_calc.py"])
        self.accept(plan)
        self.cli("start", "T01")
        check = dict(argv=[sys.executable, "-B", "-m", "unittest", "test_calc"], workspace="app")
        spec = dict(id="F1", reason="Required arithmetic behavior is incorrect.", criteria=[1],
                    paths=["calc.py", "test_calc.py"], checks=dict(unit=check),
                    verification=dict(mode="red-green", check="unit", test_paths=["test_calc.py"], reason="Reproduce arithmetic defect."))
        self.cli("repair", "start", "T01", "--file", "-", payload=spec)
        test = self.app / "test_calc.py"
        test.write_text("import unittest\nfrom calc import mul, sub\nclass Test(unittest.TestCase):\n"
                        " def test_mul(self): self.assertEqual(mul(2,3),6)\n")
        self.cli("repair", "test", "T01", "--id", "F1", "--stage", "red", "--note", "5 != 6")
        (self.app / "calc.py").write_text("def mul(a,b): return a*b\ndef sub(a,b): return a+b\n")
        self.cli("check", "unit")
        self.cli("repair", "done", "T01", "--id", "F1", "--file", "-", payload=dict(summary="Multiplication fixed.", evidence="Red/green logs."))
        self.cli("repair", "start", "T01", "--file", "-", payload=dict(spec, id="F2"))
        test.write_text(test.read_text() + " def test_sub(self): self.assertEqual(sub(3,2),1)\n")
        self.cli("repair", "test", "T01", "--id", "F2", "--stage", "red", "--note", "5 != 1; multiplication still passes.")
        (self.app / "calc.py").write_text("def mul(a,b): return a*b\ndef sub(a,b): return a-b\n")
        self.cli("check", "unit")
        self.cli("repair", "done", "T01", "--id", "F2", "--file", "-", payload=dict(summary="Subtraction fixed.", evidence="Red/green logs."), expect=2)
        self.reviewer(purpose="test-correction", aid="A2", task="T01", repair="F1")
        self.cli("test-update", "T01", "--repair", "F1", "--file", "-", payload=self.correction())
        self.cli("repair", "done", "T01", "--id", "F2", "--file", "-", payload=dict(summary="Subtraction fixed.", evidence="Red/green logs."))
        self.cli("done", "T01", "--result-file", self.result())
        self.assertEqual([r["status"] for r in self.state()["tasks"]["T01"]["repairs"]], ["done", "done"])

    def test_widen_captures_newly_monitored_originals_without_human_adoption(self):
        (self.app / "existing.md").write_text("Original content, outside the initial monitor.\n")
        scope = self.scope()
        scope["workspaces"][0]["monitor"] = ["a.md"]
        self.accept(scope=scope)
        self.cli("start", "T01")
        (self.app / "a.md").write_text("Partial requested work.\n")
        self.cli("widen", "T01", "--path", "existing.md", "--deliverable", "D1",
                 "--reason", "Inspected existing article; required companion to the requested overview.")
        original = self.state()["baseline_files"]["app:existing.md"]
        self.assertEqual((self.wf / original).read_text(), "Original content, outside the initial monitor.\n")
        (self.app / "existing.md").write_text("Updated required article.\n")
        self.cli("done", "T01", "--result-file", self.result())
        self.assertEqual(self.state()["tasks"]["T01"]["status"], "done")
        self.assertFalse(any(e["action"] == "question" for e in self.state()["history"]))

    def test_refine_captures_new_check_inputs_but_never_adopts_monitored_external_edits(self):
        (self.app / "runner.py").write_text("print('real runner')\n")
        (self.app / "reference.md").write_text("Operator reference.\n")
        scope = self.scope()
        scope["workspaces"][0]["monitor"] = ["reference.md"]
        self.accept(scope=scope)
        self.cli("start", "T01")
        spec = dict(checks=dict(unit=dict(argv=[sys.executable, "-B", "runner.py"], workspace="app",
                                         inputs={"app": ["runner.py"]})))
        self.cli("refine", "T01", "--reason", "Inspected runner for required verification.", "--file", "-", payload=spec)
        (self.app / "reference.md").write_text("Concurrent operator edit.\n")
        self.cli("refine", "T01", "--reason", "Attempt unrelated adoption.", "--file", "-",
                 payload=dict(paths=["extra.md"]), expect=2)
        self.assertEqual((self.app / "reference.md").read_text(), "Concurrent operator edit.\n")

    def test_agent_can_finish_with_actual_identity_in_one_return_record(self):
        self.settle()
        brief = dict(role="review", purpose="plan", requirements=["R1"], question="Review original request and plan.",
                     paths=[str(self.app)], done_when="Return verified coverage and defects.",
                     model="inherit", reasoning="inherit")
        self.cli("agent", "reserve", "--id", "A1", "--capacity", "1", "--file", "-", payload=brief)
        result = dict(accepted=True, summary="Fixture-reviewed exact plan.", evidence=["request.md and plan.md"],
                      validation="Scripted record for CLI validation only.", unresolved=[])
        self.cli("agent", "finish", "--id", "A1", "--agent-id", "main", "--file", "-", payload=result, expect=2)
        self.cli("agent", "finish", "--id", "A1", "--agent-id", "scripted-review-host", "--file", "-", payload=result)
        self.cli("plan", "accept", "--agent", "A1")
        self.assertEqual(self.state()["agents"]["A1"]["agent_id"], "scripted-review-host")
        self.assertIsNone(self.state()["agents"]["A1"]["actual_model"])

    def test_semantic_correction_of_shared_pins_reproduces_each_original_obligation(self):
        # A mistaken expectation and matching bad implementation escape early checks.
        self.multiplication(second=True)
        test = self.app / "test_calc.py"
        test.write_text(test.read_text().replace(",6)", ",7)"))
        (self.app / "calc.py").write_text("def mul(a,b): return a*b+1\n")
        self.cli("check", "unit")
        self.reviewer(purpose="test-correction", aid="A2", task="T01")
        # This is a temporary fixture of an earlier bad review, not accepted user behavior.
        self.cli("test-update", "T01", "--file", "-", payload=self.correction())
        self.cli("done", "T01", "--result-file", self.result())
        self.cli("start", "T02")
        spec = dict(id="F1", reason="Characterize multiplication.", criteria=[1], paths=["calc.py", "test_calc.py"],
                    checks=dict(unit=json.loads((self.wf / "plan.json").read_text())["checks"]["unit"]),
                    verification=dict(mode="characterization", check="unit", test_paths=["test_calc.py"], reason="Preserve expected behavior."))
        self.cli("repair", "start", "T02", "--file", "-", payload=spec)
        self.cli("repair", "test", "T02", "--id", "F1", "--stage", "pin", "--note", "Observed 7, later found incorrect.")
        # Source review now finds the mistaken expectation; retaining it would be dishonest.
        test.write_text(test.read_text().replace(",7)", ",6)"))
        proofs = []
        for tid, repair, production in [("T01", None, "def mul(a,b): return a+b\n"),
                                        ("T02", "F1", "def mul(a,b): return a*b+1\n")]:
            baseline = self.base / ("baseline-" + tid)
            baseline.mkdir()
            (baseline / "calc.py").write_text(production)
            (baseline / "test_calc.py").write_text(test.read_text())
            args = ["correction-proof", tid, "--baseline", str(baseline), "--identity", "Actual pre-fix source for " + tid]
            if repair:
                args += ["--repair", repair, "--stage", "red"]
            else:
                self.cli(*args, "--stage", "pin", expect=2)
            output = self.cli(*args)
            operation = output.split("Baseline proof recorded: ")[1].split(";")[0]
            proofs.append(operation)
        (self.app / "calc.py").write_text("def mul(a,b): return a*b\n")
        self.cli("check", "unit")
        self.reviewer(purpose="test-correction", aid="A3", task="T01", proof=proofs[0], proofs=proofs[1:])
        correction = self.correction("A3")
        correction["regression"] = dict(basis="reproduced", operation=proofs[0], evidence="Corrected test fails 5 != 6.",
            related=[dict(task="T02", repair="F1", basis="reproduced", operation=proofs[1], evidence="Corrected test fails 7 != 6.")])
        missing = copy.deepcopy(correction)
        missing["regression"].pop("related")
        self.cli("test-update", "T01", "--file", "-", payload=missing, expect=2)
        fake = copy.deepcopy(correction)
        fake["regression"]["related"][0]["operation"] = "invented-proof"
        self.cli("test-update", "T01", "--file", "-", payload=fake, expect=2)
        self.assertEqual(self.state()["tasks"]["T02"]["repairs"][0]["test_checkpoint"]["stage"], "pin")
        self.cli("test-update", "T01", "--file", "-", payload=correction)
        repaired = self.state()["tasks"]["T02"]["repairs"][0]
        self.assertEqual(repaired["test_checkpoint"]["stage"], "red")
        self.assertEqual(repaired["verification"]["mode"], "red-green")
        self.assertEqual(repaired["test_checkpoint"]["proof"], proofs[1])
        self.cli("repair", "done", "T02", "--id", "F1", "--file", "-", payload=dict(summary="Correct multiplication.", evidence="Two real baselines and current green."))
        self.cli("done", "T02", "--result-file", self.result("T02"))

    def test_reopening_final_review_owner_does_not_leave_permanent_dirty_gate(self):
        self.accept()
        self.cli("start", "T01")
        self.cli("done", "T01", "--result-file", self.result())
        self.cli("reopen", "T01", "--reason", "Fix inaccurate source citation.")
        self.cli("start", "T01")
        (self.app / "a.md").write_text("Correct citation.\n")
        self.cli("done", "T01", "--result-file", self.result())
        self.assertNotIn("T01", self.state().get("verification_dirty", {}))


if __name__ == "__main__":
    unittest.main()
