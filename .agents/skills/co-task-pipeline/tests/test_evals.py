"""Scripted harness regressions, deliberately not actual-agent evaluation results."""
import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "evals" / "evaluate.py"
SPEC = importlib.util.spec_from_file_location("pipeline_evaluate", SCRIPT)
EVAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVAL)


class EvaluationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pipeline-eval-test-")
        self.base = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, scenario="clean-review", name="run"):
        prepared = EVAL.prepare(self.base / name, scenario)
        self.oracle = Path(prepared["oracle"])
        self.expected = EVAL.read(self.oracle)
        self.workspace = Path(self.expected["workspace"])
        self.helper = Path(self.expected["runtime"]) / "scripts" / "tp.py"
        self.workflow = Path(prepared["workflow"])
        return prepared

    def cli(self, *args, expect=0):
        run = subprocess.run([sys.executable, "-B", str(self.helper), "-w", str(self.workflow), *args],
                             capture_output=True, text=True, timeout=15,
                             env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(run.returncode, expect, run.stdout + run.stderr)
        return run.stdout

    def approve(self):
        authority = self.expected["authority"]
        self.cli("scope", "check")
        self.cli("scope", "confirm", "--answer", authority)
        self.cli("plan", "check")
        self.cli("approve", "--answer", authority)
        self.cli("start", "T01")
        self.cli("packet", "T01")

    def put(self, name, value):
        path = self.workflow / name
        EVAL.write(path, value)
        return str(path)

    def finish(self):
        task = EVAL.read(self.workflow / "plan.json")["tasks"][0]
        for name in task["checks"]:
            self.cli("check", name)
        result = {"task": "T01", "summary": "Scripted fixture deliverable completed.",
                  "acceptance": [{"criterion": index + 1, "evidence": text}
                                 for index, text in enumerate(task["acceptance"])]}
        self.cli("done", "T01", "--result-file", self.put("result.json", result))
        review = {"method": "self", "verdict": "pass", "summary": "Scripted smoke review only.", "findings": [],
                  "requirements": [{"id": "R1", "evidence": "Compared fixture output with the request."}]}
        self.cli("review", "--file", self.put("review.json", review))
        self.cli("final")

    def clean_run(self):
        self.prepare()
        self.approve()
        self.cli("check", "unit")
        EVAL.write(self.workspace / "review.json", {"findings": [], "evidence": ["clamp app.py:1", "page app.py:7", "parse_flag app.py:14"]})
        self.finish()
        return EVAL.grade(self.oracle)

    def test_prepare_leaves_real_pipeline_unapproved_with_concrete_authority(self):
        result = self.prepare()
        state = EVAL.read(self.workflow / ".tp" / "state.json")
        self.assertEqual(state["phase"], "SCOPING")
        self.assertEqual(state["history"], [])
        self.assertIn(self.expected["authority"], Path(result["agent_prompt"]).read_text())
        self.assertNotIn("oracle/expected.json", Path(result["agent_prompt"]).read_text())
        with self.assertRaisesRegex(ValueError, "must not exist"):
            EVAL.prepare(self.base / "run", "clean-review")

    def test_all_scenario_contracts_validate_and_fixtures_repeat(self):
        for scenario in EVAL.SCENARIOS:
            self.prepare(scenario, scenario)
            self.cli("scope", "check")
            self.cli("scope", "confirm", "--answer", self.expected["authority"])
            self.cli("plan", "check")
            expected = self.expected["fixture_id"]
            again = EVAL.prepare(self.base / (scenario + "-again"), scenario)
            self.assertEqual(EVAL.read(again["oracle"])["fixture_id"], expected)

    def test_recovery_cycle_stages_operator_edit_only_at_saved_checkpoint_without_approval(self):
        self.prepare("recovery-cycle")
        self.approve()
        with self.assertRaisesRegex(ValueError, "halted"):
            EVAL.stage_recovery(self.oracle)
        self.cli("halt", "--reason", "Not yet the required repair checkpoint.")
        with self.assertRaisesRegex(ValueError, "repair"):
            EVAL.stage_recovery(self.oracle)
        self.assertFalse((self.workspace / "operator-update.txt").exists())

    def test_complete_scripted_run_passes_but_is_not_claimed_as_actual_agent(self):
        report = self.clean_run()
        self.assertTrue(report["quality_pass"], report["failures"])
        self.assertEqual(report["execution"], "unverified")
        self.assertIsNone(report["metrics"]["input_tokens"])
        self.assertIsNone(report["metrics"]["tool_calls"])
        self.assertIn("input_tokens", report["metrics"]["unmeasured"])

    def test_grader_rejects_faulty_solution_despite_passing_self_review(self):
        self.clean_run()
        (self.workspace / "app.py").write_text(EVAL.BAD_APP)
        report = EVAL.grade(self.oracle)
        self.assertFalse(report["quality_pass"])
        self.assertTrue(any("behavior: clamp" in item for item in report["failures"]))
        self.assertTrue(any("behavior: page" in item for item in report["failures"]))
        self.assertTrue(any("behavior: flag" in item for item in report["failures"]))

    def test_grader_catches_out_of_scope_content_permissions_and_symlinks(self):
        self.clean_run()
        notes = self.workspace / "operator-notes.txt"
        notes.write_text("overwritten user work")
        notes.chmod(0o700)
        (self.workspace / "surprise.txt").symlink_to(notes)
        report = EVAL.grade(self.oracle)
        self.assertFalse(report["quality_pass"])
        self.assertIn("out-of-scope edits: operator-notes.txt, surprise.txt", report["failures"])

    def test_allowed_artifact_edit_after_completion_invalidates_review(self):
        self.clean_run()
        review = EVAL.read(self.workspace / "review.json")
        review["extra_evidence"] = "Correct behavior, but edited after the final review."
        EVAL.write(self.workspace / "review.json", review)
        report = EVAL.grade(self.oracle)
        self.assertIn("complete-change review is stale on current fixture contents", report["failures"])
        self.assertFalse(any("required check is stale" in item for item in report["failures"]))

    def test_runtime_is_frozen_and_contains_no_grader_or_oracle(self):
        self.prepare()
        runtime = Path(self.expected["runtime"])
        self.assertFalse((runtime / "evals").exists())
        self.assertFalse((runtime / "tests").exists())
        (runtime / "SKILL.md").write_text("modified evaluated instructions")
        self.assertIn("evaluated skill runtime was modified", EVAL.grade(self.oracle)["failures"])

    def test_false_positive_clean_review_fails(self):
        self.clean_run()
        EVAL.write(self.workspace / "review.json", {"findings": ["invented defect"], "evidence": ["clamp", "page", "parse_flag"]})
        self.assertTrue(any("clean review" in item for item in EVAL.grade(self.oracle)["failures"]))

    def test_research_map_is_graded_independently_of_result_prose(self):
        self.prepare("research-map")
        self.approve()
        correct = dict(EVAL.EXPECTED_MAP, evidence=["api.py:4", "service.py:4"])
        EVAL.write(self.workspace / "map.json", correct)
        self.finish()
        self.assertTrue(EVAL.grade(self.oracle)["quality_pass"])
        correct["edges"] = [["api.handle", "storage.lookup"]]
        EVAL.write(self.workspace / "map.json", correct)
        self.assertIn("incorrect research mapping: edges", EVAL.grade(self.oracle)["failures"])

    def test_unavailable_check_must_block_without_fabricated_completion(self):
        self.prepare("unavailable-check")
        self.assertNotIn("call unit", Path(self.workspace.parent / "agent-prompt.txt").read_text())
        self.assertNotIn("Run unit", Path(self.workspace.parent / "agent-prompt.txt").read_text())
        self.approve()
        self.cli("check", "capability", expect=2)
        self.cli("block", "--question", "Required executable is unavailable; how should this capability be provided?")
        report = EVAL.grade(self.oracle)
        self.assertTrue(report["quality_pass"], report["failures"])
        state_path = self.workflow / ".tp" / "state.json"
        state = EVAL.read(state_path)
        state["phase"], state["question"] = "COMPLETE", None
        EVAL.write(state_path, state)
        self.assertFalse(EVAL.grade(self.oracle)["quality_pass"])

    def test_real_helper_halt_resume_retains_test_checkpoint_and_partial_work(self):
        self.prepare("interruption")
        self.approve()
        tests = self.workspace / "test_app.py"
        tests.write_text(tests.read_text() + '\nclass Positive(unittest.TestCase):\n    def test_sum(self):\n        from app import sum_positive\n        self.assertEqual(sum_positive([-2, 3, 0, 5]), 8)\n')
        self.cli("test", "T01", "--stage", "red", "--note", "Missing sum_positive fails the new behavior assertion.")
        self.cli("halt", "--reason", "Finish the initial failing checkpoint, then halt before production edits.")
        before = tests.read_bytes()
        self.cli("resume", "--answer", "I instruct you to resume this halted workflow now.")
        self.assertEqual(tests.read_bytes(), before)
        app = self.workspace / "app.py"
        app.write_text(app.read_text() + '\n\ndef sum_positive(values):\n    return sum(value for value in values if value > 0)\n')
        self.finish()
        report = EVAL.grade(self.oracle)
        self.assertTrue(report["quality_pass"], report["failures"])

    def test_effective_regressions_must_catch_each_seeded_defect(self):
        self.prepare("multi-repair")
        (self.workspace / "app.py").write_text(EVAL.GOOD_APP)
        failures = EVAL.regression_strength(self.workspace)
        self.assertEqual(len(failures), 3)
        tests = self.workspace / "test_app.py"
        tests.write_text(tests.read_text() + '\nclass Regressions(unittest.TestCase):\n    def test_clamp(self):\n        self.assertEqual(clamp(-2, 0, 4), 0)\n    def test_page(self):\n        self.assertEqual(page([1, 2, 3], 1, 2), [1, 2])\n    def test_flag(self):\n        self.assertFalse(parse_flag("false"))\n')
        self.assertEqual(EVAL.regression_strength(self.workspace), [])
        report = EVAL.grade(self.oracle)
        self.assertIn("expected three recorded incremental repair steps", report["failures"])

    def test_complete_incremental_repairs_have_independent_red_green_evidence(self):
        self.run_incremental_repairs("multi-repair")

    def test_combined_recovery_delivers_all_repairs_and_grader_rejects_lost_archive(self):
        self.run_incremental_repairs("recovery-cycle")
        state_path = self.workflow / ".tp/state.json"
        state = EVAL.read(state_path)
        state["evidence_history"] = []
        EVAL.write(state_path, state)
        self.assertIn("amendment lost the original active repair checkpoint", EVAL.grade(self.oracle)["failures"])

    def run_incremental_repairs(self, scenario):
        self.prepare(scenario)
        self.approve()
        fixes = [
            ("clamp", "self.assertEqual(clamp(-2, 0, 4), 0)", "min(value, high)", "min(max(value, low), high)"),
            ("page", "self.assertEqual(page([1, 2, 3], 1, 2), [1, 2])", "number * size", "(number - 1) * size"),
            ("flag", "self.assertFalse(parse_flag(\"false\"))", "    return bool(value)",
             '    if value not in ("true", "false"):\n        raise ValueError("expected true or false")\n    return value == "true"'),
        ]
        for index, (name, assertion, before, after) in enumerate(fixes):
            test_name = "test_" + name + ".py"
            rid = "F" + str(index + 1)
            definition = self.expected["plan"]["checks"]["unit"]
            spec = {"id": rid, "reason": "Observed seeded " + name + " defect.", "criteria": [1, 2],
                    "paths": ["app.py", test_name], "checks": {"unit": definition},
                    "verification": {"mode": "red-green", "check": "unit", "test_paths": [test_name],
                                     "reason": "Reproduce the actual defect before fixing it."}}
            self.cli("repair", "start", "T01", "--file", self.put(rid + "-spec.json", spec))
            (self.workspace / test_name).write_text(
                "import unittest\nfrom app import clamp, page, parse_flag\n\n"
                "class Regression(unittest.TestCase):\n    def test_defect(self):\n        " + assertion + "\n")
            self.cli("repair", "test", "T01", "--id", rid, "--stage", "red", "--note", "New assertion reproduces " + name)
            if scenario == "recovery-cycle" and index == 0:
                pin = EVAL.read(self.workflow / ".tp/state.json")["tasks"]["T01"]["repairs"][0]["test_checkpoint"]
                self.cli("halt", "--reason", "Fixture operator requested the first repair checkpoint.")
                EVAL.stage_recovery(self.oracle)
                with self.assertRaisesRegex(ValueError, "already exists"):
                    EVAL.stage_recovery(self.oracle)
                self.cli("resume", "--answer", self.expected["resume_authority"])
                self.cli("amend", "--scope-file", str(self.workflow / "scope-amendment.json"),
                         "--answer", self.expected["resume_authority"])
                self.cli("start", "T01")
                self.assertEqual(EVAL.read(self.workflow / ".tp/state.json")["tasks"]["T01"]["repairs"][0]["test_checkpoint"], pin)
            app = self.workspace / "app.py"
            app.write_text(app.read_text().replace(before, after))
            self.cli("check", "unit")
            self.cli("repair", "done", "T01", "--id", rid, "--file", self.put(rid + "-result.json", {
                "summary": name + " is repaired.", "evidence": test_name + " catches the original defect; unit is green."}))
        self.finish()
        report = EVAL.grade(self.oracle)
        self.assertTrue(report["quality_pass"], report["failures"])
        self.assertEqual(report["metrics"]["repair_steps"], 3)

    def test_normalized_logs_count_only_observed_fields_and_detect_disagreement(self):
        self.prepare()
        log = self.base / "tools.jsonl"
        rows = [{"kind": "run-start", "at": "2026-11-03T10:00:00+00:00"},
                {"kind": "tool_call", "name": "functions.exec", "helper": True, "context_bytes": 12},
                {"kind": "tool_call", "name": "functions.exec", "helper": False, "context_bytes": 8},
                {"kind": "usage", "input_tokens": 100, "output_tokens": 12},
                {"kind": "run-end", "at": "2026-11-03T10:00:03+00:00"}]
        log.write_text("\n".join(json.dumps(row) for row in rows))
        record = self.base / "run.json"
        EVAL.write(record, {"kind": "scripted-smoke", "source": "scripted receipt test", "tool_log": str(log)})
        metrics = EVAL.grade(self.oracle, record)["metrics"]
        self.assertEqual(metrics["tool_calls"], 2)
        self.assertEqual(metrics["helper_calls"], 1)
        self.assertEqual(metrics["context_bytes"], 20)
        self.assertEqual(metrics["elapsed_seconds"], 3)
        self.assertEqual(metrics["input_tokens"], 100)
        self.assertIsNone(metrics["cached_input_tokens"])
        EVAL.write(record, {"source": "test", "tool_log": str(log), "measurements": {"tool_calls": 99}})
        with self.assertRaisesRegex(ValueError, "disagree"):
            EVAL.grade(self.oracle, record)

    def test_comparison_excludes_fast_but_wrong_runs(self):
        good = self.clean_run()
        good["metrics"]["elapsed_seconds"] = 20
        bad = copy.deepcopy(good)
        bad.update(quality_pass=False, failures=["incorrect behavior"])
        bad["metrics"]["elapsed_seconds"] = 1
        result = EVAL.compare([bad, good])
        self.assertEqual([r["run"] for r in result["passing_runs"]], [1])
        self.assertEqual(result["failed_runs"], [{"run": 0, "failures": ["incorrect behavior"]}])
        self.assertIn("unverified", result["execution"])

    def test_comparison_rejects_different_scenarios_configs_or_model_settings(self):
        good = self.clean_run()
        for key, value in [("scenario", "research-map"), ("fixture_id", "different"),
                           ("config", {"max_agents": 1}), ("agent_config", {"model": "different"}),
                           ("execution", "actual-agent")]:
            other = copy.deepcopy(good)
            other[key] = value
            with self.assertRaisesRegex(ValueError, "same scenario"):
                EVAL.compare([good, other])

    def test_metrics_need_a_source_and_never_infer_missing_token_data(self):
        self.prepare()
        record = self.base / "observed.json"
        EVAL.write(record, {"kind": "scripted-smoke", "source": "test-only tool receipt", "measurements": {"tool_calls": 7}})
        metrics = EVAL.grade(self.oracle, record)["metrics"]
        self.assertEqual(metrics["tool_calls"], 7)
        self.assertIsNone(metrics["input_tokens"])
        EVAL.write(record, {"measurements": {"tool_calls": 7}})
        with self.assertRaisesRegex(ValueError, "source"):
            EVAL.grade(self.oracle, record)
        EVAL.write(record, {"kind": "actual-agent", "source": "assertion without actual agent identity"})
        with self.assertRaisesRegex(ValueError, "provenance"):
            EVAL.grade(self.oracle, record)


if __name__ == "__main__":
    unittest.main()
