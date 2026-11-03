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


if __name__ == "__main__":
    unittest.main()
