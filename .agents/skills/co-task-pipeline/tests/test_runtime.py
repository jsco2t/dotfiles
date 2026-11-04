"""Integration regressions for measured, recoverable incremental execution."""
import json
import os
import subprocess
import sys
import time
import unittest

import test_tp as fixtures


class RuntimeTest(unittest.TestCase):
    setUp = fixtures.PipelineTest.setUp
    tearDown = fixtures.PipelineTest.tearDown
    cli = fixtures.PipelineTest.cli
    put = fixtures.PipelineTest.put
    state = fixtures.PipelineTest.state
    scope = fixtures.PipelineTest.scope
    task = fixtures.PipelineTest.task
    plan = fixtures.PipelineTest.plan
    confirm = fixtures.PipelineTest.confirm
    approve = fixtures.PipelineTest.approve
    result = fixtures.PipelineTest.result
    review = fixtures.PipelineTest.review
    automated = fixtures.PipelineTest.automated

    def wait_for(self, predicate, seconds=6):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.025)
        self.fail("timed out waiting for the launched local fixture")

    def helper_process(self, *args):
        return subprocess.Popen([sys.executable, "-B", str(fixtures.SCRIPT), "-w", str(self.wf), *args],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def measured_check(self, script, inputs=None):
        plan = self.automated(argv=[sys.executable, "-B", "-c", script])
        plan["checks"]["unit"]["reuse"] = True
        if inputs is not None:
            plan["checks"]["unit"]["inputs"] = inputs
        return plan

    def test_scoped_check_reuses_after_docs_change_and_reruns_for_new_missing_input(self):
        counter = self.base / "count"
        script = "from pathlib import Path; p=Path(" + repr(str(counter)) + "); p.write_text(p.read_text()+'x' if p.exists() else 'x')"
        self.approve(self.measured_check(script, {"app": ["calc.py", "test_*.py", "config.toml"]}))
        self.cli("start", "T01")
        self.cli("check", "unit")
        (self.app / "a.md").write_text("unrelated docs")
        self.assertIn("reused", self.cli("check", "unit"))
        (self.app / "config.toml").write_text("newly created declared input")
        self.cli("check", "unit")
        self.assertEqual(counter.read_text(), "xx")

    def test_scoped_check_includes_shared_workspace_and_environment(self):
        shared = self.base / "shared"
        shared.mkdir()
        (shared / "lock").write_text("v1")
        scope = self.scope()
        scope["workspaces"].append(dict(name="shared", path=str(shared), mode="read"))
        plan = self.measured_check("print('ok')", {"app": ["src/**/*.py"], "shared": ["lock"]})
        plan["checks"]["unit"]["environment"] = ["PIPELINE_FIXTURE_FLAG"]
        self.approve(plan, scope)
        self.cli("start", "T01")
        self.cli("check", "unit")
        original = self.state()["checks"]["unit"]["fingerprint"]
        (shared / "lock").write_text("v2")
        self.cli("check", "unit")
        self.assertNotEqual(original, self.state()["checks"]["unit"]["fingerprint"])
        before = self.state()["checks"]["unit"]["fingerprint"]
        old = os.environ.get("PIPELINE_FIXTURE_FLAG")
        try:
            os.environ["PIPELINE_FIXTURE_FLAG"] = "changed"
            self.cli("check", "unit")
        finally:
            if old is None:
                os.environ.pop("PIPELINE_FIXTURE_FLAG", None)
            else:
                os.environ["PIPELINE_FIXTURE_FLAG"] = old
        self.assertNotEqual(before, self.state()["checks"]["unit"]["fingerprint"])

    def test_literal_ignored_input_is_checkpointed_and_cannot_hide_a_change(self):
        (self.app / "target").mkdir()
        (self.app / "target/contract.json").write_text("v1")
        self.approve(self.measured_check("print('ok')", {"app": ["target/contract.json"]}))
        self.cli("start", "T01")
        self.cli("check", "unit")
        first = self.state()["checks"]["unit"]["fingerprint"]
        (self.app / "target/contract.json").write_text("v2")
        self.cli("check", "unit")
        self.assertNotEqual(first, self.state()["checks"]["unit"]["fingerprint"])
        self.assertIn("outside", self.cli("done", "T01", "--result-file", self.result(), expect=2))

    def test_recovery_does_not_relabel_old_check_with_new_environment(self):
        marker = self.base / "started"
        script = "from pathlib import Path; import time; Path(" + repr(str(marker)) + ").touch(); time.sleep(0.6)"
        plan = self.measured_check(script)
        plan["checks"]["unit"]["environment"] = ["PIPELINE_RECOVERY_ENV"]
        self.approve(plan)
        process = self.helper_process("check", "unit")
        self.wait_for(marker.exists)
        original = next(iter(self.state()["operations"].values()))["input_fingerprint"]
        process.kill()
        process.communicate(timeout=3)
        op = next(iter(self.state()["operations"].values()))
        self.wait_for((self.wf / op["receipt"]).exists)
        old = os.environ.get("PIPELINE_RECOVERY_ENV")
        try:
            os.environ["PIPELINE_RECOVERY_ENV"] = "new invocation environment"
            self.cli("recover")
            self.assertEqual(self.state()["checks"]["unit"]["fingerprint"], original)
            self.assertNotIn("reused", self.cli("check", "unit"))
        finally:
            if old is None:
                os.environ.pop("PIPELINE_RECOVERY_ENV", None)
            else:
                os.environ["PIPELINE_RECOVERY_ENV"] = old

    def repair_spec(self, rid, test_path):
        return dict(id=rid, reason="Demonstrated arithmetic defect required by criterion 1.", criteria=[1],
                    paths=["app.py", test_path], checks=dict(unit=dict(
                        argv=[sys.executable, "-B", "-m", "unittest", "discover", "-p", "test_*.py"],
                        workspace="app", inputs={"app": ["app.py", "test_*.py"]}, reuse=True)),
                    verification=dict(mode="red-green", check="unit", test_paths=[test_path], reason="Reproduce before repair."))

    def begin_adaptive(self):
        (self.app / "app.py").write_text("def inc(x): return x\ndef double(x): return x\n")
        plan = self.plan()
        plan["tasks"][0].update(adaptive=True, paths=[])
        self.approve(plan)
        self.cli("start", "T01")

    def finish_repair(self, rid):
        self.cli("check", "unit")
        self.cli("repair", "done", "T01", "--id", rid, "--file", self.put(rid + "-done.json", dict(
            summary="Arithmetic repaired.", evidence="Original regression failed before fix and now passes with prior regressions.")))

    def test_two_incremental_repairs_keep_separate_red_green_and_original_task(self):
        self.begin_adaptive()
        self.cli("repair", "start", "T01", "--file", self.put("r1.json", self.repair_spec("F1", "test_inc.py")))
        (self.app / "test_inc.py").write_text("import unittest\nfrom app import inc\nclass Test(unittest.TestCase):\n def test_inc(self): self.assertEqual(inc(3),4)\n")
        self.cli("repair", "test", "T01", "--id", "F1", "--stage", "red", "--note", "inc(3) returned 3.")
        (self.app / "app.py").write_text("def inc(x): return x+1\ndef double(x): return x\n")
        self.finish_repair("F1")
        first = self.state()["tasks"]["T01"]["repairs"][0]["test_checkpoint"]
        self.cli("repair", "start", "T01", "--file", self.put("r2.json", self.repair_spec("F2", "test_double.py")))
        (self.app / "test_double.py").write_text("import unittest\nfrom app import double\nclass Test(unittest.TestCase):\n def test_double(self): self.assertEqual(double(3),6)\n")
        self.cli("repair", "test", "T01", "--id", "F2", "--stage", "red", "--note", "double(3) returned 3; inc stays green.")
        (self.app / "app.py").write_text("def inc(x): return x+1\ndef double(x): return x*2\n")
        self.finish_repair("F2")
        self.cli("done", "T01", "--result-file", self.result())
        self.review()
        self.cli("final")
        state = self.state()
        self.assertEqual(len(state["tasks"]), 1)
        self.assertEqual([r["status"] for r in state["tasks"]["T01"]["repairs"]], ["done", "done"])
        self.assertEqual(state["tasks"]["T01"]["repairs"][0]["test_checkpoint"], first)
        self.assertEqual(sum(e["action"] == "repair-test" for e in state["history"]), 2)
        metrics = json.loads(self.cli("metrics"))
        for category in ("research", "implementation", "verification", "bookkeeping", "waiting"):
            self.assertGreater(metrics["activities"][category], 0)
        self.assertLessEqual(metrics["covered_phase_seconds"], metrics["wall_seconds"] + 0.05)
        self.assertEqual(metrics["unclassified_wall_seconds"], max(0, metrics["wall_seconds"] - metrics["covered_phase_seconds"]))

    def test_repair_rejects_unapproved_outcome_early_production_and_unfinished_completion(self):
        self.begin_adaptive()
        spec = self.repair_spec("F1", "test_inc.py")
        spec["criteria"] = [99]
        self.cli("repair", "start", "T01", "--file", self.put("bad.json", spec), expect=2)
        spec["criteria"] = [1]
        self.cli("repair", "start", "T01", "--file", self.put("r1.json", spec))
        (self.app / "test_inc.py").write_text("fixture")
        (self.app / "app.py").write_text("def inc(x): return x+1\n")
        self.assertIn("production", self.cli("repair", "test", "T01", "--id", "F1", "--stage", "red", "--note", "Early fix.", expect=2))
        self.cli("done", "T01", "--result-file", self.result(), expect=2)

    def test_halt_cancels_long_check_promptly_and_preserves_task(self):
        marker = self.base / "started"
        script = "from pathlib import Path; import time; Path(" + repr(str(marker)) + ").touch(); time.sleep(20)"
        self.approve(self.measured_check(script))
        self.cli("start", "T01")
        process = self.helper_process("check", "unit")
        try:
            self.wait_for(marker.exists)
            began = time.monotonic()
            self.cli("halt", "--reason", "Stop the active check now.")
            self.assertLess(time.monotonic() - began, 2)
            process.communicate(timeout=5)
            self.assertEqual(process.returncode, 2)
            state = self.state()
            self.assertEqual(state["phase"], "HALTED")
            self.assertEqual(state["checks"]["unit"]["exit_code"], 130)
            self.assertEqual(state["tasks"]["T01"]["status"], "running")
        finally:
            if process.poll() is None:
                self.cli("halt", "--reason", "Fixture cleanup.")
                process.communicate(timeout=5)

    def test_detached_receipt_recovers_after_parent_loss_without_reexecution(self):
        marker = self.base / "started"
        script = "from pathlib import Path; import time; p=Path(" + repr(str(marker)) + "); p.write_text(p.read_text()+'x' if p.exists() else 'x'); time.sleep(0.8)"
        self.approve(self.measured_check(script))
        process = self.helper_process("check", "unit")
        self.wait_for(marker.exists)
        process.kill()
        process.communicate(timeout=3)
        op = next(iter(self.state()["operations"].values()))
        self.wait_for((self.wf / op["receipt"]).exists)
        self.cli("recover")
        self.assertEqual(self.state()["checks"]["unit"]["exit_code"], 0)
        self.cli("recover")
        self.assertIn("reused", self.cli("check", "unit"))
        self.assertEqual(marker.read_text(), "x")
        self.assertEqual(sum(e["action"] == "check" for e in self.state()["history"]), 1)

    def test_manual_effect_unknown_outcome_requires_evidence_before_resume(self):
        self.approve()
        self.cli("start", "T01")
        self.cli("operation", "begin", "--id", "C1", "--kind", "commit", "--task", "T01",
                 "--intent", "Record the approved cycle commit.", "--authority", "Operator approved local cycle commits.")
        self.cli("halt", "--reason", "Interrupted handoff.")
        self.assertEqual(self.state()["operations"]["C1"]["status"], "unknown")
        self.cli("operation", "finish", "--id", "C1", "--file", self.put("receipt.json", dict(
            status="completed", evidence="Fixture read-back establishes the commit ID; no command was replayed.")))
        self.cli("resume", "--answer", "Resume the interrupted fixture.")
        self.cli("done", "T01", "--result-file", self.result())

    def test_recover_is_safe_before_plan_exists(self):
        self.cli("halt", "--reason", "Pause during scope.")
        self.assertEqual(json.loads(self.cli("recover"))["recovered"], [])
        self.cli("resume", "--answer", "Continue scoping.")
        self.assertEqual(self.state()["phase"], "SCOPING")

    def test_unknown_dead_check_can_be_reconciled_but_never_prose_passed(self):
        self.approve()
        state = self.state()
        state["operations"] = dict(C1=dict(id="C1", kind="check", status="unknown", receipt=".tp/operations/C1/receipt.json"))
        (self.wf / ".tp/state.json").write_text(json.dumps(state))
        self.assertIn("only from worker", self.cli("operation", "finish", "--id", "C1", "--file", self.put("claim.json", dict(
            status="completed", evidence="A made-up pass cannot replace missing worker evidence.")), expect=2))
        self.cli("operation", "finish", "--id", "C1", "--file", self.put("reconciled.json", dict(
            status="cancelled", evidence="Inspected launch receipt and local process list; no command was launched or left running.")))
        self.assertEqual(self.state()["operations"]["C1"]["status"], "cancelled")

    def agent_scope(self):
        scope = self.scope()
        scope["max_agents"] = 3
        scope["requirements"] = [dict(id="R1", text="Explain the application.", deliverables=["D1"])]
        return scope

    def brief(self, model="TERRA"):
        return dict(role="research", requirements=["R1"], question="Locate the documented entry point.",
                    paths=[str(self.app)], done_when="Return the source path and symbol with evidence.",
                    model=model, reasoning="medium" if model == "TERRA" else "high",
                    model_reason="Bounded extraction is suitable for TERRA." if model == "TERRA" else "Conflicting behaviors need SOL reasoning.")

    def test_three_agent_limit_parent_model_choice_and_actual_identity(self):
        self.confirm(self.agent_scope())
        for index, model in enumerate(("TERRA", "SOL", "TERRA")):
            self.cli("agent", "reserve", "--id", "A"+str(index), "--capacity", "3", "--file", self.put("brief.json", self.brief(model)))
        self.assertIn("capacity", self.cli("agent", "reserve", "--id", "A3", "--capacity", "3",
                                           "--file", self.put("brief.json", self.brief()), expect=2))
        self.cli("agent", "attach", "--id", "A0", "--agent-id", "fixture-runtime-id")
        self.cli("agent", "finish", "--id", "A0", "--file", self.put("agent-result.json", dict(
            accepted=True, summary="Entry point found.", evidence=["source.md:1"], validation="Parent read and verified the referenced source.")))
        self.assertIsNone(self.state()["agents"]["A0"]["actual_model"])
        self.assertEqual(self.state()["agents"]["A1"]["requested_model"], "gpt-6.1-sol")

    def test_agent_runtime_capacity_and_source_drift_are_not_silently_ignored(self):
        self.confirm(self.agent_scope())
        self.cli("agent", "reserve", "--id", "A0", "--capacity", "1", "--file", self.put("brief.json", self.brief()))
        self.cli("agent", "reserve", "--id", "A1", "--capacity", "1", "--file", self.put("brief.json", self.brief()), expect=2)
        self.cli("agent", "attach", "--id", "A0", "--agent-id", "fixture-id")
        (self.app / "new-source.md").write_text("changed while reader ran")
        self.assertIn("source changed", self.cli("agent", "finish", "--id", "A0", "--file", self.put("result.json", dict(
            accepted=True, summary="Found.", evidence=["source"], validation="Claimed inspection.")), expect=2))

    def test_metrics_and_packet_are_read_only_and_usage_import_is_idempotent(self):
        scope = self.agent_scope()
        plan = self.plan()
        plan["tasks"][0]["requirements"] = ["R1"]
        self.approve(plan, scope)
        self.cli("activity", "begin", "research", "--label", "Map application entry point.")
        self.cli("activity", "end", "--evidence", "Evidence saved once in research.md.")
        usage = self.put("usage.json", dict(id="main-session", source="measured host session final counters", measurements=dict(
            input_tokens=100, cached_input_tokens=60, output_tokens=20, tool_calls=7)))
        self.cli("usage", "--file", usage)
        self.cli("usage", "--file", usage)
        before = {str(p): p.stat().st_mtime_ns for p in self.wf.rglob("*")}
        packet = json.loads(self.cli("packet", "T01"))
        self.assertEqual(packet["requirements"][0]["id"], "R1")
        metrics = json.loads(self.cli("metrics"))
        self.assertEqual(metrics["usage"]["input_tokens"], 100)
        self.assertGreater(metrics["helper_calls"]["count"], 0)
        self.assertGreater(metrics["activities"]["research"], 0)
        self.assertEqual(before, {str(p): p.stat().st_mtime_ns for p in self.wf.rglob("*")})
        self.assertIn("essential packet", self.cli("packet", "T01", "--max-bytes", "10", expect=2))

    def test_amendment_and_reopen_preserve_repairs_and_enforce_prior_pins(self):
        self.begin_adaptive()
        self.cli("repair", "start", "T01", "--file", self.put("r1.json", self.repair_spec("F1", "test_inc.py")))
        (self.app / "test_inc.py").write_text("import unittest\nfrom app import inc\nclass Test(unittest.TestCase):\n def test_inc(self): self.assertEqual(inc(3),4)\n")
        self.cli("repair", "test", "T01", "--id", "F1", "--stage", "red", "--note", "inc(3) returned 3.")
        (self.app / "app.py").write_text("def inc(x): return x+1\ndef double(x): return x\n")
        self.finish_repair("F1")
        original = self.state()["tasks"]["T01"]["repairs"][0]
        scope = self.state()["scope"]
        scope["constraints"].append("Preserve the confirmed arithmetic behavior.")
        self.cli("amend", "--scope-file", self.put("changed-scope.json", scope), "--answer", "Approve this additional constraint.")
        self.assertEqual(self.state()["tasks"]["T01"]["repairs"][0], original)
        self.cli("start", "T01")
        self.cli("check", "unit")
        self.cli("done", "T01", "--result-file", self.result())
        self.cli("reopen", "T01", "--reason", "Inspect an in-scope follow-through.")
        self.assertEqual(self.state()["tasks"]["T01"]["repairs"][0], original)
        self.assertTrue(self.state()["evidence_history"])
        self.cli("start", "T01")
        (self.app / "test_inc.py").write_text("import unittest\nclass Test(unittest.TestCase):\n def test_weakened(self): self.assertTrue(True)\n")
        self.cli("check", "unit")
        self.assertIn("pinned tests changed", self.cli("done", "T01", "--result-file", self.result(), expect=2))

    def test_running_pinned_repair_continues_after_unrelated_adoption(self):
        self.begin_adaptive()
        self.cli("repair", "start", "T01", "--file", self.put("r1.json", self.repair_spec("F1", "test_inc.py")))
        (self.app / "test_inc.py").write_text("import unittest\nfrom app import inc\nclass Test(unittest.TestCase):\n def test_inc(self): self.assertEqual(inc(3),4)\n")
        self.cli("repair", "test", "T01", "--id", "F1", "--stage", "red", "--note", "inc(3) returned 3.")
        pin = self.state()["tasks"]["T01"]["repairs"][0]["test_checkpoint"]
        (self.app / "app.py").write_text("def inc(x): return x+1\ndef double(x): return x\n")
        (self.app / "operator.md").write_text("Unrelated operator edit.")
        self.cli("amend", "--answer", "Adopt my operator.md edit; preserve the running repair.")
        self.cli("start", "T01")
        self.assertEqual(self.state()["tasks"]["T01"]["repairs"][0]["test_checkpoint"], pin)
        self.finish_repair("F1")
        self.cli("done", "T01", "--result-file", self.result())

    def test_amendment_cannot_implicitly_replace_pins_and_explicit_supersession_archives_them(self):
        plan = self.automated("characterization")
        self.approve(plan)
        self.cli("start", "T01")
        (self.app / "test_calc.py").write_text("original assertions")
        self.cli("test", "T01", "--stage", "pin", "--note", "Original behavior.")
        original = self.state()["tasks"]["T01"]["test_checkpoint"]
        (self.app / "test_calc.py").write_text("corrected strategy needs explicit approval")
        self.assertIn("pinned tests changed", self.cli("amend", "--answer", "Approve unrelated documentation.", expect=2))
        self.cli("amend", "--supersede-tests", "T01", "--answer", "Approve this exact corrected test strategy and its replacement checkpoint.")
        history = self.state()["evidence_history"]
        self.assertEqual(history[0]["entry"]["test_checkpoint"], original)
        self.assertTrue((self.wf / original["log"]).is_file())
        self.cli("start", "T01")
        self.cli("done", "T01", "--result-file", self.result(), expect=2)
        self.cli("test", "T01", "--stage", "pin", "--note", "Approved corrected strategy.")
        self.cli("done", "T01", "--result-file", self.result())

    def test_superseded_repair_requires_a_tested_replacement_before_delivery(self):
        self.begin_adaptive()
        spec = self.repair_spec("F1", "test_inc.py")
        self.cli("repair", "start", "T01", "--file", self.put("original.json", spec))
        (self.app / "test_inc.py").write_text("import unittest\nfrom app import inc\nclass Test(unittest.TestCase):\n def test_inc(self): self.assertEqual(inc(3),4)\n")
        self.cli("repair", "test", "T01", "--id", "F1", "--stage", "red", "--note", "Original case fails.")
        self.cli("amend", "--supersede-tests", "T01:F1", "--answer", "Approve replacing F1 with the explicit negative-input regression, retaining its criterion.")
        self.cli("start", "T01")
        (self.app / "app.py").write_text("def inc(x): return x+1\ndef double(x): return x\n")
        self.cli("check", "unit")
        self.assertIn("replacement", self.cli("done", "T01", "--result-file", self.result(), expect=2))
        # Restore the unfixed source so the approved replacement gets a genuine red.
        (self.app / "app.py").write_text("def inc(x): return x\ndef double(x): return x\n")
        spec.update(id="F2", replaces=["F1"], paths=["app.py", "test_negative.py"])
        spec["verification"]["test_paths"] = ["test_negative.py"]
        self.cli("repair", "start", "T01", "--file", self.put("replacement.json", spec))
        (self.app / "test_negative.py").write_text("import unittest\nfrom app import inc\nclass Test(unittest.TestCase):\n def test_inc(self): self.assertEqual(inc(-3),-2)\n")
        self.cli("repair", "test", "T01", "--id", "F2", "--stage", "red", "--note", "Negative input reproduces the defect.")
        (self.app / "app.py").write_text("def inc(x): return x+1\ndef double(x): return x\n")
        self.finish_repair("F2")
        self.cli("done", "T01", "--result-file", self.result())
        self.review()
        self.cli("final")
        self.assertIn("explicitly superseded", (self.wf / "report.md").read_text())

    def test_changed_verification_cannot_relabel_an_existing_characterization_as_red(self):
        plan = self.automated("characterization")
        self.approve(plan)
        self.cli("start", "T01")
        (self.app / "test_calc.py").write_text("original characterization")
        self.cli("test", "T01", "--stage", "pin", "--note", "Original passing characterization.")
        original = self.state()["tasks"]["T01"]["test_checkpoint"]
        plan["tasks"][0]["verification"]["mode"] = "red-green"
        self.assertIn("supersede-tests", self.cli("amend", "--plan-file", self.put("red-plan.json", plan),
                      "--answer", "Approve the red-green replacement strategy.", expect=2))
        self.assertEqual(self.state()["tasks"]["T01"]["test_checkpoint"], original)

    def test_later_task_cannot_weaken_a_completed_tasks_regression(self):
        plan = self.automated("characterization")
        plan["tasks"].append(self.task("T02", "test_calc.py", ["T01"]))
        self.approve(plan)
        self.cli("start", "T01")
        (self.app / "test_calc.py").write_text("original regression cases")
        self.cli("test", "T01", "--stage", "pin", "--note", "Original behavior characterized.")
        self.cli("done", "T01", "--result-file", self.result())
        self.cli("start", "T02")
        (self.app / "test_calc.py").write_text("accidentally removed earlier cases")
        self.assertIn("pinned tests changed in T01", self.cli("done", "T02", "--result-file", self.result("T02"), expect=2))

    def test_scoped_review_accepts_unrelated_edits_but_catches_dependencies_and_new_files(self):
        self.confirm(self.agent_scope())
        for name in ("source.py", "dependency.lock"):
            (self.app / name).write_text("original")
        brief = self.brief()
        brief.update(role="review", inputs={"app": ["source.py", "dependency.lock", "new_*.py"]})
        result = self.put("agent-result.json", dict(accepted=True, summary="Reviewed.", evidence=["source.py:1"],
                                                  validation="Inspected the declared source and dependency inputs."))
        for index, changed_path in enumerate(("operator.md", "dependency.lock", "new_source.py", "source.py")):
            aid = "A" + str(index)
            self.cli("agent", "reserve", "--id", aid, "--capacity", "1", "--file", self.put("brief.json", brief))
            self.cli("agent", "attach", "--id", aid, "--agent-id", "runtime-" + aid)
            (self.app / changed_path).write_text("changed " + aid)
            if index == 0:
                self.cli("agent", "finish", "--id", aid, "--file", result)
            else:
                self.assertIn("source changed", self.cli("agent", "finish", "--id", aid, "--file", result, expect=2))
                self.cli("agent", "cancel", "--id", aid, "--evidence", "Review is stale; source changed.")
        brief["inputs"] = {"app": ["../escape"]}
        self.cli("agent", "reserve", "--id", "bad", "--capacity", "1", "--file", self.put("bad-brief.json", brief), expect=2)

    def test_scoped_review_fingerprints_literal_ignored_dependencies(self):
        (self.app / "target").mkdir()
        dependency = self.app / "target/dependency.lock"
        dependency.write_text("v1")
        self.confirm(self.agent_scope())
        brief = dict(self.brief(), inputs={"app": ["target/dependency.lock"]})
        self.cli("agent", "reserve", "--id", "A1", "--capacity", "1", "--file", self.put("brief.json", brief))
        self.cli("agent", "attach", "--id", "A1", "--agent-id", "fixture-review")
        dependency.write_text("v2")
        result = self.put("review-result.json", dict(accepted=True, summary="Claimed clean.", evidence=["dependency.lock:1"],
                                                   validation="This stale evidence must not pass."))
        self.assertIn("source changed", self.cli("agent", "finish", "--id", "A1", "--file", result, expect=2))

    def test_fresh_unscoped_checks_survive_refinement_and_unchanged_amendment(self):
        plan = self.measured_check("print('ok')")
        plan["tasks"][0]["adaptive"] = True
        self.approve(plan)
        self.cli("start", "T01")
        self.cli("check", "unit")
        self.cli("refine", "T01", "--file", self.put("extra.json", dict(paths=["helper.py"])), "--reason", "Needed for the existing criterion.")
        self.assertIn("reused", self.cli("check", "unit"))
        self.cli("amend", "--answer", "Confirm the same contract and current work.")
        self.assertIn("reused", self.cli("check", "unit"))
        changed = self.state()["plan"]
        changed["checks"]["unit"]["argv"][-1] = "print('different check')"
        self.cli("amend", "--plan-file", self.put("changed-check.json", changed), "--answer", "Approve the changed check command.")
        self.assertNotIn("reused", self.cli("check", "unit"))

    def test_plan_warns_about_unscoped_reuse_without_changing_legacy_contract(self):
        self.confirm()
        plan = self.measured_check("print('ok')")
        self.put("plan.json", plan)
        self.assertIn("unit: reusable check has no scoped inputs", self.cli("plan", "check"))
        self.assertEqual(json.loads((self.wf / "plan.json").read_text()), plan)

    def test_explicit_reviewer_lifecycle_prevents_cross_component_context_reuse(self):
        self.confirm(self.agent_scope())
        first = dict(self.brief(), unit="storage", context="fresh")
        self.cli("agent", "reserve", "--id", "A1", "--capacity", "1", "--file", self.put("brief1.json", first))
        self.cli("agent", "attach", "--id", "A1", "--agent-id", "runtime-storage")
        self.cli("agent", "finish", "--id", "A1", "--file", self.put("a1.json", dict(
            accepted=True, summary="Storage inspected.", evidence=["storage.py:1"], validation="Parent verified source.")))
        continued = dict(first, context="continue", continues="A1")
        self.cli("agent", "reserve", "--id", "A2", "--capacity", "1", "--file", self.put("brief2.json", continued))
        self.cli("agent", "attach", "--id", "A2", "--agent-id", "runtime-storage")
        self.cli("agent", "cancel", "--id", "A2", "--evidence", "Finished bounded follow-through.")
        other = dict(continued, unit="generation")
        self.assertIn("same unit", self.cli("agent", "reserve", "--id", "A3", "--capacity", "1",
                                           "--file", self.put("brief3.json", other), expect=2))
        fresh = dict(first, unit="generation")
        self.cli("agent", "reserve", "--id", "A4", "--capacity", "1", "--file", self.put("brief4.json", fresh))
        self.assertIn("fresh context", self.cli("agent", "attach", "--id", "A4", "--agent-id", "runtime-storage", expect=2))
        self.cli("agent", "attach", "--id", "A4", "--agent-id", "runtime-generation")

    def test_cancel_single_check_preserves_task_and_allows_retry(self):
        marker = self.base / "started"
        script = "from pathlib import Path; import time; p=Path(" + repr(str(marker)) + "); existed=p.exists(); p.touch(); time.sleep(20 if not existed else 0)"
        self.approve(self.measured_check(script))
        self.cli("start", "T01")
        process = self.helper_process("check", "unit")
        try:
            self.wait_for(marker.exists)
            operation = next(iter(self.state()["operations"]))
            self.cli("cancel-check", "--id", operation, "--reason", "Owned fixture is hung; repair and retry.")
            process.communicate(timeout=5)
            self.cli("recover")
            self.assertEqual(process.returncode, 2)
            self.assertEqual(self.state()["phase"], "EXECUTING")
            self.assertEqual(self.state()["tasks"]["T01"]["status"], "running")
            self.assertEqual(self.state()["checks"]["unit"]["exit_code"], 130)
            self.cli("check", "unit")
            self.cli("cancel-check", "--id", operation, "--reason", "Idempotent retry after receipt.")
            self.cli("cancel-check", "--id", "unknown", "--reason", "Must not target an unknown process.", expect=2)
        finally:
            if process.poll() is None:
                self.cli("halt", "--reason", "Fixture cleanup.")
                process.communicate(timeout=5)

    def test_cancellation_race_recovers_real_pass_and_cannot_cancel_external_effect(self):
        marker = self.base / "ran"
        script = "from pathlib import Path; import time; Path(" + repr(str(marker)) + ").touch(); time.sleep(0.5)"
        self.approve(self.measured_check(script))
        self.cli("start", "T01")
        process = self.helper_process("check", "unit")
        try:
            self.wait_for(marker.exists)
            process.kill()
            process.communicate(timeout=3)
            operation = next(iter(self.state()["operations"].values()))
            self.wait_for((self.wf / operation["receipt"]).exists)
            self.assertIn("already settled", self.cli("cancel-check", "--id", operation["id"], "--reason", "Late cancellation raced with completion."))
            self.assertEqual(self.state()["checks"]["unit"]["exit_code"], 0)
            self.assertIn("reused", self.cli("check", "unit"))
            self.cli("operation", "begin", "--id", "C1", "--kind", "commit", "--task", "T01",
                     "--intent", "Fixture receipt only; no actual commit.", "--authority", "Fixture authorization.")
            self.assertIn("known check", self.cli("cancel-check", "--id", "C1", "--reason", "Must not cancel an external effect.", expect=2))
            self.assertEqual(self.state()["operations"]["C1"]["status"], "running")
        finally:
            if process.poll() is None:
                self.cli("halt", "--reason", "Fixture cleanup.")
                process.communicate(timeout=5)

    def test_growing_packet_keeps_authority_and_pages_every_check_without_writes(self):
        plan = self.plan()
        plan["checks"] = {"check" + str(i): dict(argv=[sys.executable, "-B", "-c", "#" * 1500], workspace="app") for i in range(24)}
        plan["tasks"][0]["checks"] = list(plan["checks"])
        scope = self.scope()
        scope["constraints"] = ["Keep this complete essential constraint " + "!" * 3000]
        self.approve(plan, scope)
        before = {str(p): p.stat().st_mtime_ns for p in self.wf.rglob("*")}
        packet = json.loads(self.cli("packet", "T01"))
        self.assertEqual(packet["constraints"], scope["constraints"])
        self.assertEqual(packet["task"], plan["tasks"][0])
        self.assertEqual(packet["details"]["checks"]["total"], 24)
        offset, found = 0, []
        while offset is not None:
            output = self.cli("packet", "T01", "--section", "checks", "--offset", str(offset), "--max-bytes", "4000")
            self.assertLessEqual(len(output.strip().encode()), 4000)
            page = json.loads(output)
            found += [item["name"] for item in page["items"]]
            offset = page["next_offset"]
        self.assertEqual(found, list(plan["checks"]))
        self.assertEqual(before, {str(p): p.stat().st_mtime_ns for p in self.wf.rglob("*")})


if __name__ == "__main__":
    unittest.main()
