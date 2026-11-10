"""Behavioral tests use only temporary workflows, workspaces, and local commands."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "tp.py"


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex-pipeline-test-")
        self.base = Path(self.temp.name).resolve()
        self.app = self.base / "app"
        self.app.mkdir()
        self.request = self.base / "request.txt"
        self.request.write_text('Write an overview.\nKeep `literal` and "quotes".\n')
        self.wf = None
        output = self.cli("init", str(self.base / "planning"), "--legacy-approvals", "--title", "Overview", "--request-file", str(self.request))
        self.wf = Path(output.splitlines()[0].removeprefix("workflow: "))

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args, expect=0):
        command = [sys.executable, "-B", str(SCRIPT)]
        if self.wf is not None:
            command += ["-w", str(self.wf)]
        result = subprocess.run(command + list(args), capture_output=True, text=True, timeout=15,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def put(self, name, value):
        path = self.wf / name
        path.write_text(json.dumps(value))
        return str(path)

    def state(self):
        return json.loads((self.wf / ".tp" / "state.json").read_text())

    def scope(self):
        return dict(title="Overview", deliverables=[dict(id="D1", kind="docs", what="Overview", where="app/a.md")],
                    workspaces=[dict(name="app", path=str(self.app), mode="write")], constraints=[], non_goals=[],
                    review="self", max_agents=0)

    def task(self, tid="T01", path="a.md", dependencies=None):
        return dict(id=tid, title="Overview", kind="docs", serves=["D1"], workspace="app", paths=[path],
                    depends_on=dependencies or [], acceptance=["Explain the application."], checks=[],
                    verification=dict(mode="manual", reason="Compare prose against the source."))

    def plan(self, tasks=None):
        return dict(summary="Write the requested overview.", tasks=tasks or [self.task()], checks={}, final_checks=[])

    def confirm(self, scope=None):
        self.put("scope.json", scope or self.scope())
        self.cli("scope", "check")
        self.cli("scope", "confirm", "--answer", "Yes, this exact scope.")

    def approve(self, plan=None, scope=None):
        self.confirm(scope)
        self.put("plan.json", plan or self.plan())
        self.cli("plan", "check")
        self.cli("approve", "--answer", "Approve this plan.")

    def result(self, tid="T01"):
        return self.put(tid + "-result.json", dict(task=tid, summary="The overview describes the application.",
                        acceptance=[dict(criterion=1, evidence="a.md:1 matches source documentation.")]))

    def finish_task(self, tid="T01", path="a.md"):
        self.cli("start", tid)
        (self.app / path).write_text("# Application\nThe application does the requested thing.\n")
        self.cli("done", tid, "--result-file", self.result(tid))

    def review(self, **changes):
        result = dict(method="self", verdict="pass", summary="Verified criteria and source accuracy.", findings=[])
        result.update(changes)
        return self.cli("review", "--file", self.put("review.json", result))

    def test_init_preserves_request_and_does_not_overwrite_collisions(self):
        self.assertEqual((self.wf / "request.md").read_bytes(), self.request.read_bytes())
        old = self.wf
        self.wf = None
        result = self.cli("init", str(self.base / "planning"), "--legacy-approvals", "--title", "Overview", "--request-file", str(self.request))
        self.assertIn(str(old) + "-2", result)
        self.assertTrue(old.is_dir())

    def test_status_is_read_only(self):
        before = {str(p): p.stat().st_mtime_ns for p in self.wf.rglob("*")}
        self.assertIn("SCOPING", self.cli("status"))
        after = {str(p): p.stat().st_mtime_ns for p in self.wf.rglob("*")}
        self.assertEqual(before, after)

    def test_old_client_state_is_rejected_unchanged(self):
        path = self.wf / ".tp" / "state.json"
        path.write_text('{"version": 1, "phase": "EXECUTING"}')
        before = path.read_bytes()
        self.assertIn("Incompatible", self.cli("status", expect=2))
        self.assertEqual(path.read_bytes(), before)

    def test_scope_and_plan_need_separate_real_answers(self):
        self.assertIn("confirm scope", self.cli("approve", "--answer", "yes", expect=2))
        self.put("scope.json", self.scope())
        self.assertIn("--answer", self.cli("scope", "confirm", expect=2))
        self.assertEqual(self.state()["phase"], "SCOPING")
        self.confirm()
        self.put("plan.json", self.plan())
        self.assertIn("not be blank", self.cli("approve", "--answer", " ", expect=2))

    def test_uncovered_deliverable_cannot_be_approved(self):
        scope = self.scope()
        scope["deliverables"].append(dict(id="D2", kind="docs", what="Glossary", where="app/b.md"))
        self.confirm(scope)
        self.put("plan.json", self.plan())
        self.assertIn("uncovered", self.cli("approve", "--answer", "yes", expect=2))

    def test_cycle_cannot_be_approved(self):
        self.confirm()
        self.put("plan.json", self.plan([self.task("T01", dependencies=["T02"]), self.task("T02", "b.md", ["T01"])]))
        self.assertIn("cycle", self.cli("plan", "check", expect=2))

    def test_paths_reject_traversal_globs_directories_and_symlinks(self):
        self.confirm()
        (self.app / "directory").mkdir()
        (self.app / "link").symlink_to(self.base, target_is_directory=True)
        for path in ("../escape", "*.md", ".", "directory", "link/outside.md", ".git/config"):
            with self.subTest(path=path):
                self.put("plan.json", self.plan([self.task(path=path)]))
                self.cli("plan", "check", expect=2)

    def test_code_requires_review_and_independence_requires_allowance(self):
        scope = self.scope()
        scope["deliverables"][0]["kind"] = "code"
        scope["review"] = "none"
        self.put("scope.json", scope)
        self.assertIn("require final review", self.cli("scope", "check", expect=2))
        scope["review"] = "independent"
        self.put("scope.json", scope)
        self.assertIn("allowance", self.cli("scope", "check", expect=2))

    def test_read_workspace_cannot_receive_task_edits(self):
        scope = self.scope()
        scope["workspaces"][0]["mode"] = "read"
        self.confirm(scope)
        self.put("plan.json", self.plan())
        self.assertIn("writable", self.cli("plan", "check", expect=2))

    def test_approved_plan_and_scope_cannot_be_edited_directly(self):
        self.approve()
        for name in ("scope", "plan"):
            path = self.wf / (name + ".json")
            original = path.read_text()
            value = json.loads(original)
            value["unapproved"] = "extra work"
            path.write_text(json.dumps(value))
            self.assertIn("differs", self.cli("next", expect=2))
            self.assertIn(name, self.cli("status"))
            path.write_text(original)

    def test_dependencies_and_single_writer(self):
        self.approve(self.plan([self.task(), self.task("T02", "b.md", ["T01"])]))
        self.assertIn("dependencies", self.cli("start", "T02", expect=2))
        self.cli("start", "T01")
        self.assertIn("one main-session", self.cli("start", "T02", expect=2))

    def test_all_acceptance_evidence_is_required_without_duplicates(self):
        plan = self.plan()
        plan["tasks"][0]["acceptance"].append("Cite the main entry point.")
        self.approve(plan)
        self.cli("start", "T01")
        self.assertIn("every criterion", self.cli("done", "T01", "--result-file", self.result(), expect=2))
        result = dict(task="T01", summary="done", acceptance=[dict(criterion=1, evidence="proof")] * 2)
        self.assertIn("every criterion", self.cli("done", "T01", "--result-file", self.put("bad.json", result), expect=2))

    def test_unplanned_edits_are_rejected_and_preserved(self):
        self.approve()
        self.cli("start", "T01")
        outside = self.app / "unplanned.txt"
        outside.write_text("operator edit")
        self.assertIn("outside", self.cli("done", "T01", "--result-file", self.result(), expect=2))
        self.assertEqual(outside.read_text(), "operator edit")
        self.assertEqual(self.state()["tasks"]["T01"]["status"], "running")

    def test_changes_between_tasks_cannot_be_silently_adopted(self):
        self.approve(self.plan([self.task(), self.task("T02", "b.md")]))
        self.finish_task()
        (self.app / "unplanned.md").write_text("stray edit")
        self.assertIn("between tasks", self.cli("start", "T02", expect=2))
        self.assertIn("between tasks", self.cli("next", expect=2))

    def test_baseline_preserves_preexisting_edits_and_absent_file_state(self):
        (self.app / "a.md").write_text("preexisting user edit")
        self.approve(self.plan([self.task(), self.task("T02", "b.md")]))
        files = self.state()["baseline_files"]
        self.assertEqual((self.wf / files["app:a.md"]).read_text(), "preexisting user edit")
        self.assertIsNone(files["app:b.md"])
        self.finish_task()
        self.assertEqual((self.wf / files["app:a.md"]).read_text(), "preexisting user edit")

    def test_approved_adoption_reopens_completed_owning_task(self):
        self.approve()
        self.finish_task()
        (self.app / "a.md").write_text("concurrent edit to the accepted deliverable")
        self.cli("amend", "--answer", "Adopt the reviewed concurrent edit and verify it.")
        self.assertEqual(self.state()["tasks"]["T01"]["status"], "pending")
        self.assertIn("app:a.md", " ".join(self.state()["history"][-1]["changes"]))

    def test_halt_and_resume_preserve_partial_edits_and_approval(self):
        self.approve()
        self.cli("start", "T01")
        (self.app / "a.md").write_text("partial")
        self.cli("hault", "--reason", "Operator says stop.")
        self.assertIn("halted", self.cli("next").lower())
        self.cli("done", "T01", "--result-file", self.result(), expect=2)
        self.cli("resume", "--answer", "Resume this run.")
        self.assertIn("continue: T01", self.cli("next"))
        self.assertEqual((self.app / "a.md").read_text(), "partial")
        self.cli("done", "T01", "--result-file", self.result())

    def test_pending_question_blocks_execution_until_actual_answer(self):
        self.approve()
        self.cli("block", "--question", "Which application version?")
        self.assertIn("human", self.cli("next"))
        self.assertIn("pending", self.cli("start", "T01", expect=2))
        self.cli("resolve", "--answer", "Document the checked-out version.")
        self.cli("start", "T01")
        answer = next(event for event in reversed(self.state()["history"]) if event["action"] == "answer")
        self.assertEqual(answer["answer"], "Document the checked-out version.")

    def test_amendment_records_scope_changes_and_reopens_affected_work(self):
        self.approve()
        self.finish_task()
        scope = self.scope()
        scope["constraints"] = ["Include the application version."]
        self.cli("amend", "--scope-file", self.put("scope-amend.json", scope), "--answer", "Yes, include the version.")
        state = self.state()
        self.assertEqual(state["tasks"]["T01"]["status"], "pending")
        self.assertEqual(state["history"][-1]["action"], "amend")
        self.assertTrue(state["history"][-1]["changes"])
        self.assertTrue((self.wf / "request.md").is_file())

    def test_amendment_reopens_unchanged_dependents(self):
        plan = self.plan([self.task(), self.task("T02", "b.md", ["T01"])])
        self.approve(plan)
        self.finish_task()
        self.finish_task("T02", "b.md")
        plan["tasks"][0]["acceptance"].append("Include a source reference.")
        self.cli("amend", "--plan-file", self.put("plan-amend.json", plan), "--answer", "Approve the additional criterion.")
        self.assertEqual([t["status"] for t in self.state()["tasks"].values()], ["pending", "pending"])

    def test_repointed_workspace_needs_a_new_name_for_baseline_provenance(self):
        self.approve()
        other = self.base / "other"
        other.mkdir()
        scope = self.scope()
        scope["workspaces"][0]["path"] = str(other)
        self.assertIn("new workspace name", self.cli("amend", "--scope-file", self.put("repoint.json", scope),
                      "--answer", "Use the other checkout.", expect=2))

    def test_final_refuses_missing_review_or_unfinished_tasks(self):
        self.approve()
        self.assertIn("completion gate", self.cli("final", expect=2))
        self.finish_task()
        self.assertIn("review", self.cli("final", expect=2))
        self.review()
        self.cli("final")
        self.assertEqual(self.state()["phase"], "COMPLETE")
        self.assertIn("Criterion 1:", (self.wf / "report.md").read_text())

    def test_independent_review_cannot_silently_become_self_review(self):
        scope = self.scope()
        scope.update(review="independent", max_agents=1)
        self.approve(scope=scope)
        self.finish_task()
        result = dict(method="self", verdict="pass", summary="Reviewed.", findings=[])
        self.assertIn("differs", self.cli("review", "--file", self.put("review.json", result), expect=2))
        result["method"] = "independent"
        self.assertIn("actual independent", self.cli("review", "--file", self.put("review.json", result), expect=2))
        result["agent_id"] = "synthetic-reviewer-fixture"
        self.cli("review", "--file", self.put("review.json", result))
        self.cli("final")

    def test_reopen_preserves_contract_and_original_baseline(self):
        (self.app / "a.md").write_text("original user content")
        self.approve()
        self.finish_task()
        self.review()
        scope, plan = self.state()["scope"], self.state()["plan"]
        original = self.wf / self.state()["baseline_files"]["app:a.md"]
        self.cli("reopen", "T01", "--reason", "Correct a source reference within criterion 1.")
        self.assertEqual(self.state()["scope"], scope)
        self.assertEqual(self.state()["plan"], plan)
        self.assertIsNone(self.state()["review"])
        self.finish_task()
        self.review()
        self.cli("final")
        self.assertEqual(original.read_text(), "original user content")

    def test_estimate_is_reporting_metadata_and_never_cuts_tasks(self):
        scope = self.scope()
        scope["estimate_minutes"] = 1
        self.approve(self.plan([self.task(), self.task("T02", "b.md", ["T01"])]), scope)
        self.finish_task()
        self.assertIn("start: T02", self.cli("next"))
        self.cli("final", expect=2)
        self.finish_task("T02", "b.md")
        self.review()
        self.cli("final")
        self.assertIn("Estimate: 1 minutes", (self.wf / "report.md").read_text())

    def test_closeout_cannot_defer_without_answer(self):
        self.approve()
        self.finish_task()
        self.review()
        self.cli("note", "An unrelated CLI has no help text; users cannot discover flags.")
        decisions = [dict(id=1, classification="followup", reason="Improve CLI discovery in separate work.")]
        path = self.put("closeout.json", decisions)
        self.assertIn("operator", self.cli("closeout", "--file", path, expect=2))
        self.cli("final", expect=2)
        self.cli("closeout", "--file", path, "--answer", "Keep that as a follow-up; do not file a ticket.")
        self.cli("final")
        self.assertIn("followup", (self.wf / "report.md").read_text())

    def test_confirmed_review_findings_reopen_owner_and_dependents(self):
        self.approve(self.plan([self.task(), self.task("T02", "b.md", ["T01"])]))
        self.finish_task()
        self.finish_task("T02", "b.md")
        self.review(verdict="changes", findings=[dict(task="T01", issue="The entry point is wrong.", evidence="app.py:1")])
        self.assertTrue(all(t["status"] == "pending" for t in self.state()["tasks"].values()))
        self.cli("final", expect=2)

    def automated(self, mode="existing", argv=None):
        plan = self.plan()
        plan["checks"] = dict(unit=dict(argv=argv or [sys.executable, "-B", "-c", "print('verified')"], workspace="app"))
        plan["final_checks"] = ["unit"]
        plan["tasks"][0]["checks"] = ["unit"]
        plan["tasks"][0]["verification"] = dict(mode=mode, check="unit", reason="Verify requested behavior.")
        if mode in ("red-green", "characterization"):
            plan["tasks"][0]["paths"] = ["calc.py", "test_calc.py"]
            plan["tasks"][0]["verification"]["test_paths"] = ["test_calc.py"]
        return plan

    def test_checks_are_required_and_content_changes_invalidate_them(self):
        self.approve(self.automated())
        self.cli("start", "T01")
        self.cli("done", "T01", "--result-file", self.result(), expect=2)
        self.cli("check", "unit")
        (self.app / "a.md").write_text("source changed after check")
        self.assertIn("stale", self.cli("done", "T01", "--result-file", self.result(), expect=2))
        self.cli("check", "unit")
        self.cli("done", "T01", "--result-file", self.result())

    def test_failed_and_missing_commands_are_persisted_and_never_pass(self):
        for argv in ([sys.executable, "-B", "-c", "raise SystemExit(1)"], ["/nonexistent-program-for-pipeline-test"]):
            with self.subTest(argv=argv):
                if self.state()["phase"] == "SCOPING":
                    self.approve(self.automated(argv=argv))
                    self.cli("start", "T01")
                else:
                    self.cli("amend", "--plan-file", self.put("amend.json", self.automated(argv=argv)), "--answer", "Use this check.")
                    self.cli("start", "T01")
                self.cli("check", "unit", expect=2)
                result = self.state()["checks"]["unit"]
                self.assertNotEqual(result["exit_code"], 0)
                self.assertTrue((self.wf / result["log"]).is_file())
                self.cli("done", "T01", "--result-file", self.result(), expect=2)

    def test_source_mutating_check_is_not_a_pass(self):
        argv = [sys.executable, "-B", "-c", "from pathlib import Path; Path('a.md').write_text('changed')"]
        self.approve(self.automated(argv=argv))
        self.cli("start", "T01")
        self.assertIn("changed source", self.cli("check", "unit", expect=2))
        self.assertFalse(self.state()["checks"]["unit"]["stable"])

    def test_timeout_is_persisted_as_failure(self):
        plan = self.automated(argv=[sys.executable, "-B", "-c", "import time; time.sleep(5)"])
        plan["checks"]["unit"]["timeout_seconds"] = 1
        self.approve(plan)
        self.cli("check", "unit", expect=2)
        self.assertEqual(self.state()["checks"]["unit"]["exit_code"], 124)

    def test_final_only_check_is_required_before_review(self):
        plan = self.automated()
        plan["checks"]["package"] = dict(argv=[sys.executable, "-B", "-c", "print('package verified')"], workspace="app")
        plan["final_checks"] = ["package"]
        self.approve(plan)
        self.cli("start", "T01")
        self.cli("check", "unit")
        self.cli("done", "T01", "--result-file", self.result())
        self.assertIn("check: package", self.cli("next"))
        self.cli("check", "package")
        self.review()
        self.cli("final")

    def test_literal_check_arguments_do_not_expand_shell_expressions(self):
        marker = self.app / "executed"
        literal = f"$(touch {marker})"
        self.approve(self.automated(argv=[sys.executable, "-B", "-c", "import sys; print(sys.argv[1])", literal]))
        self.cli("check", "unit")
        self.assertFalse(marker.exists())
        log = self.wf / self.state()["checks"]["unit"]["log"]
        self.assertEqual(log.read_text().strip(), literal)

    def test_red_then_green_preserves_tests(self):
        (self.app / "calc.py").write_text("def add(a, b): return a + b\n")
        plan = self.automated("red-green", [sys.executable, "-B", "-m", "unittest", "test_calc"])
        self.approve(plan)
        self.cli("start", "T01")
        tests = "import unittest\nfrom calc import mul\nclass Test(unittest.TestCase):\n def test_mul(self): self.assertEqual(mul(2, 3), 6)\n"
        (self.app / "test_calc.py").write_text(tests)
        self.cli("test", "T01", "--stage", "red", "--note", "Import of the requested missing mul fails.")
        (self.app / "calc.py").write_text("def mul(a, b): return a * b\n")
        self.cli("check", "unit")
        self.cli("done", "T01", "--result-file", self.result())
        self.assertEqual((self.app / "test_calc.py").read_text(), tests)
        self.review()
        self.cli("final")

    def test_test_first_rejects_early_production_changes(self):
        self.approve(self.automated("red-green", [sys.executable, "-B", "-c", "raise SystemExit(1)"]))
        self.cli("start", "T01")
        (self.app / "test_calc.py").write_text("test")
        (self.app / "calc.py").write_text("production implementation")
        self.assertIn("production", self.cli("test", "T01", "--stage", "red", "--note", "red", expect=2))

    def test_green_cannot_replace_observed_red(self):
        self.approve(self.automated("red-green"))
        self.cli("start", "T01")
        (self.app / "test_calc.py").write_text("test")
        self.cli("check", "unit")
        self.assertIn("checkpoint", self.cli("done", "T01", "--result-file", self.result(), expect=2))
        self.assertIn("expected", self.cli("test", "T01", "--stage", "red", "--note", "test", expect=2))

    def test_pinned_test_edits_block_completion(self):
        self.approve(self.automated("characterization"))
        self.cli("start", "T01")
        (self.app / "test_calc.py").write_text("original assertions")
        self.cli("test", "T01", "--stage", "pin", "--note", "Current behavior pinned.")
        (self.app / "test_calc.py").write_text("weaker assertions")
        self.assertIn("already pinned", self.cli("test", "T01", "--stage", "pin", "--note", "repin", expect=2))
        self.cli("check", "unit")
        self.assertIn("pinned tests changed", self.cli("done", "T01", "--result-file", self.result(), expect=2))

    def test_requirements_cannot_point_at_missing_deliverables_or_leave_them_unmapped(self):
        scope = self.scope()
        scope["requirements"] = [dict(id="R1", text="Write the overview.", deliverables=["D2"])]
        self.put("scope.json", scope)
        self.assertIn("existing deliverables", self.cli("scope", "check", expect=2))
        scope["requirements"][0]["deliverables"] = ["D1"]
        scope["deliverables"].append(dict(id="D2", kind="docs", what="Glossary", where="app/b.md"))
        self.put("scope.json", scope)
        self.assertIn("trace", self.cli("scope", "check", expect=2))

    def test_review_requires_evidence_for_each_original_requirement_and_report_keeps_it(self):
        scope = self.scope()
        scope["requirements"] = [dict(id="R1", text="Write the application overview.", deliverables=["D1"])]
        plan = self.plan()
        plan["tasks"][0]["requirements"] = ["R1"]
        self.approve(plan, scope)
        self.finish_task()
        review = dict(method="self", verdict="pass", summary="Checked the full original request.", findings=[])
        self.assertIn("requirement coverage", self.cli("review", "--file", self.put("review.json", review), expect=2))
        evidence = dict(id="R1", evidence="request.md and a.md:1: application overview delivered.")
        for coverage in ([], [dict(evidence, id="R2")], [evidence, evidence]):
            review["requirements"] = coverage
            self.assertIn("exactly once", self.cli("review", "--file", self.put("review.json", review), expect=2))
        review["requirements"] = [evidence]
        self.cli("review", "--file", self.put("review.json", review))
        self.cli("final")
        report = (self.wf / "report.md").read_text()
        self.assertIn("Write the application overview.", report)
        self.assertIn(evidence["evidence"], report)

    def test_plan_cannot_lose_a_requirement_even_when_its_deliverable_has_a_task(self):
        scope = self.scope()
        scope["requirements"] = [dict(id="R1", text="Write the application overview.", deliverables=["D1"]),
                                 dict(id="R2", text="Include runnable examples.", deliverables=["D1"])]
        self.confirm(scope)
        plan = self.plan()
        plan["tasks"][0]["requirements"] = ["R1"]
        self.put("plan.json", plan)
        self.assertIn("uncovered request requirements: ['R2']", self.cli("plan", "check", expect=2))
        plan["tasks"][0]["requirements"].append("R2")
        self.put("plan.json", plan)
        self.cli("plan", "check")

    def test_widen_preserves_scope_partial_work_and_baselines_without_operator_answer(self):
        (self.app / "source.md").write_text("existing user source")
        self.approve()
        original_scope = self.state()["scope"]
        original_task = self.state()["plan"]["tasks"][0]
        self.cli("start", "T01")
        (self.app / "a.md").write_text("partial overview")
        self.cli("widen", "T01", "--path", "source.md", "--path", "b.md", "--deliverable", "D1",
                 "--reason", "Correct the source reference and add the companion section required by D1.")
        state = self.state()
        self.assertEqual(state["scope"], original_scope)
        task = state["plan"]["tasks"][0]
        self.assertEqual({k: v for k, v in task.items() if k != "paths"},
                         {k: v for k, v in original_task.items() if k != "paths"})
        self.assertEqual((self.wf / state["baseline_files"]["app:source.md"]).read_text(), "existing user source")
        self.assertIsNone(state["baseline_files"]["app:b.md"])
        self.assertEqual(state["history"][-1]["by"], "manager")
        (self.app / "source.md").write_text("correct source")
        (self.app / "b.md").write_text("companion section")
        self.cli("done", "T01", "--result-file", self.result())
        self.review()
        self.cli("final")
        self.assertIn("widen (manager)", (self.wf / "report.md").read_text())

    def test_widen_refuses_unknown_deliverables_escaping_paths_and_prior_unplanned_edits(self):
        self.approve()
        before = self.state()
        for path, delivery in (("b.md", "D2"), ("../escape", "D1"), ("*.md", "D1")):
            self.cli("widen", "T01", "--path", path, "--deliverable", delivery, "--reason", "Needed for overview.", expect=2)
            self.assertEqual(self.state(), before)
        self.cli("start", "T01")
        (self.app / "b.md").write_text("unplanned concurrent edit")
        self.assertIn("outside", self.cli("widen", "T01", "--path", "b.md", "--deliverable", "D1",
                      "--reason", "Needed for overview.", expect=2))
        self.assertEqual((self.app / "b.md").read_text(), "unplanned concurrent edit")
        self.assertEqual(self.state()["plan"], before["plan"])

    def test_widen_does_not_silently_adopt_existing_ignored_contents(self):
        (self.app / "dist").mkdir()
        (self.app / "dist" / "overview.md").write_text("contents absent from original checkpoint")
        self.approve()
        self.assertIn("previously untracked", self.cli("widen", "T01", "--path", "dist/overview.md",
                      "--deliverable", "D1", "--reason", "Needed for overview.", expect=2))

    def test_widen_keeps_pinned_tests_and_current_check_results(self):
        self.approve(self.automated("characterization"))
        self.cli("start", "T01")
        (self.app / "test_calc.py").write_text("pinned behavior")
        self.cli("test", "T01", "--stage", "pin", "--note", "Behavior confirmed.")
        checkpoint = self.state()["tasks"]["T01"]["test_checkpoint"]
        self.cli("widen", "T01", "--path", "helper.py", "--deliverable", "D1", "--reason", "Implementation dependency.")
        self.assertEqual(self.state()["tasks"]["T01"]["test_checkpoint"], checkpoint)
        self.assertEqual(self.state()["checks"]["unit"]["log"], checkpoint["log"])
        (self.app / "test_calc.py").write_text("weaker assertions")
        self.cli("check", "unit")
        self.assertIn("pinned tests changed", self.cli("done", "T01", "--result-file", self.result(), expect=2))

    def test_saved_decision_can_resolve_question_as_manager_with_honest_provenance(self):
        self.approve()
        self.cli("block", "--question", "Should this be an overview?")
        self.assertIn("--evidence", self.cli("resolve", "--by", "manager", "--answer", "Yes.", expect=2))
        self.assertIsNotNone(self.state()["question"])
        self.cli("resolve", "--by", "manager", "--answer", "Yes, D1 already requests the overview.",
                 "--evidence", "scope.json deliverables D1; history scope-confirm.")
        event = self.state()["history"][-1]
        self.assertEqual(event["by"], "manager")
        self.assertIn("scope-confirm", event["evidence"])
        self.cli("start", "T01")

    def test_opted_in_check_reuse_avoids_execution_but_force_and_changed_contents_rerun(self):
        counter = self.base / "check-count.txt"
        script = "from pathlib import Path; p=Path(" + repr(str(counter)) + "); p.write_text(p.read_text()+'x' if p.exists() else 'x')"
        plan = self.automated(argv=[sys.executable, "-B", "-c", script])
        plan["checks"]["unit"]["reuse"] = True
        self.approve(plan)
        self.cli("start", "T01")
        self.cli("check", "unit")
        self.assertIn("reused", self.cli("check", "unit"))
        self.assertEqual(counter.read_text(), "x")
        self.cli("check", "unit", "--force")
        self.assertEqual(counter.read_text(), "xx")
        (self.app / "a.md").write_text("new contents")
        self.cli("check", "unit")
        self.assertEqual(counter.read_text(), "xxx")

    def test_check_reuse_is_opt_in_and_failures_are_never_reused(self):
        counter = self.base / "check-count.txt"
        script = "from pathlib import Path; p=Path(" + repr(str(counter)) + "); p.write_text(p.read_text()+'x' if p.exists() else 'x')"
        self.approve(self.automated(argv=[sys.executable, "-B", "-c", script]))
        self.cli("check", "unit")
        self.cli("check", "unit")
        self.assertEqual(counter.read_text(), "xx")
        plan = self.state()["plan"]
        plan["checks"]["unit"].update(reuse=True, argv=[sys.executable, "-B", "-c", script + "; raise SystemExit(1)"])
        self.cli("amend", "--plan-file", self.put("amend.json", plan), "--answer", "Use the changed check.")
        self.cli("check", "unit", expect=2)
        self.cli("check", "unit", expect=2)
        self.assertEqual(counter.read_text(), "xxxx")

    def test_nested_write_workspace_is_excluded_from_read_parent(self):
        docs = self.app / "docs"
        docs.mkdir()
        scope = self.scope()
        scope["workspaces"][0]["mode"] = "read"
        scope["workspaces"].append(dict(name="docs", path=str(docs), mode="write"))
        plan = self.plan()
        plan["tasks"][0]["workspace"] = "docs"
        self.approve(plan, scope)
        self.cli("start", "T01")
        (docs / "a.md").write_text("overview")
        self.cli("done", "T01", "--result-file", self.result())

    def git_workspace(self):
        subprocess.run(["git", "init", "-q", str(self.app)], check=True)
        (self.app / ".gitignore").write_text("sdk/\nbuild/\n")
        (self.app / "build").mkdir()
        (self.app / "build/tracked.txt").write_text("tracked generated source")
        subprocess.run(["git", "-C", str(self.app), "add", ".gitignore"], check=True)
        subprocess.run(["git", "-C", str(self.app), "add", "-f", "build/tracked.txt"], check=True)
        scope = self.scope()
        scope["workspaces"][0]["snapshot"] = "git"
        return scope

    def test_git_snapshot_ignores_cache_churn_but_keeps_tracked_ignored_files(self):
        self.approve(scope=self.git_workspace())
        self.cli("start", "T01")
        (self.app / "sdk").mkdir()
        os.mkfifo(self.app / "sdk/socket")
        (self.app / "build/cache.txt").write_text("mutable output")
        self.cli("done", "T01", "--result-file", self.result())
        self.assertIn("app:build/tracked.txt", self.state()["checkpoint"])
        self.assertNotIn("app:build/cache.txt", self.state()["checkpoint"])
        (self.app / "build/tracked.txt").write_text("unexpected tracked change")
        self.assertIn("between tasks", self.cli("next", expect=2))

    def test_git_snapshot_catches_untracked_source_and_explicit_ignored_test(self):
        scope = self.git_workspace()
        self.approve(self.plan([self.task(path="build/explicit.txt")]), scope)
        self.cli("start", "T01")
        (self.app / "build/explicit.txt").write_text("explicit artifact")
        (self.app / "stray.py").write_text("unplanned source")
        self.assertIn("stray.py", self.cli("done", "T01", "--result-file", self.result(), expect=2))
        (self.app / "stray.py").unlink()
        self.cli("done", "T01", "--result-file", self.result())
        self.assertIn("app:build/explicit.txt", self.state()["checkpoint"])

    def test_git_snapshot_requires_git_and_walk_remains_legacy_default(self):
        scope = self.scope()
        scope["workspaces"][0]["snapshot"] = "git"
        self.confirm(scope)
        self.put("plan.json", self.plan())
        self.assertIn("Git snapshot", self.cli("approve", "--answer", "Approve.", expect=2))

    def test_git_snapshot_keeps_directory_symlinks_and_detects_tracked_deletion(self):
        scope = self.git_workspace()
        (self.app / "link").symlink_to(self.base, target_is_directory=True)
        self.approve(scope=scope)
        self.assertIn("app:link", self.state()["checkpoint"])
        (self.app / "build/tracked.txt").unlink()
        self.assertIn("build/tracked.txt", self.cli("next", expect=2))

    def test_git_snapshot_scopes_nested_workspaces_without_duplicate_paths(self):
        scope = self.git_workspace()
        docs = self.app / "docs"
        docs.mkdir()
        (docs / "source.md").write_text("source")
        scope["workspaces"].append(dict(name="docs", path=str(docs), mode="write", snapshot="git"))
        plan = self.plan()
        plan["tasks"][0]["workspace"] = "docs"
        self.approve(plan, scope)
        snapshot = self.state()["checkpoint"]
        self.assertIn("docs:source.md", snapshot)
        self.assertNotIn("app:docs/source.md", snapshot)
        self.cli("start", "T01")
        (docs / "a.md").write_text("overview")
        self.cli("done", "T01", "--result-file", self.result())

    def adaptive_plan(self):
        plan = self.plan()
        plan["tasks"][0].update(adaptive=True)
        return plan

    def refinement(self):
        return dict(paths=["calc.py", "test_calc.py"], checks=dict(unit=dict(
            argv=[sys.executable, "-B", "-m", "unittest", "test_calc"], workspace="app")),
            verification=dict(mode="red-green", check="unit", test_paths=["test_calc.py"],
                              reason="Reproduce the validated missing multiplication behavior."))

    def test_refine_keeps_outcomes_and_partial_work_without_approval_or_new_tasks(self):
        (self.app / "calc.py").write_text("def add(a, b): return a + b\n")
        self.approve(self.adaptive_plan())
        self.cli("start", "T01")
        (self.wf / "review-notes.md").write_text("Finding F1: multiplication is missing.")
        original = self.state()
        self.cli("refine", "T01", "--file", self.put("refine.json", self.refinement()),
                 "--reason", "Finding F1 needs a regression and implementation in the approved unit.")
        state = self.state()
        self.assertEqual(state["scope"], original["scope"])
        self.assertEqual(state["tasks"]["T01"]["before"], original["tasks"]["T01"]["before"])
        self.assertEqual(state["plan"]["tasks"][0]["acceptance"], original["plan"]["tasks"][0]["acceptance"])
        self.assertEqual(len(state["tasks"]), 1)
        self.assertEqual(state["history"][-1]["by"], "manager")
        (self.app / "test_calc.py").write_text("import unittest\nfrom calc import mul\nclass Test(unittest.TestCase):\n def test_mul(self): self.assertEqual(mul(2, 3), 6)\n")
        self.cli("test", "T01", "--stage", "red", "--note", "The requested mul is missing from the existing module.")
        (self.app / "calc.py").write_text("def mul(a, b): return a * b\n")
        self.cli("check", "unit")
        self.cli("done", "T01", "--result-file", self.result())
        self.review()
        self.cli("final")

    def test_refine_refuses_missing_allowance_drift_and_changed_outcomes(self):
        self.approve()
        args = ("refine", "T01", "--file", self.put("refine.json", self.refinement()), "--reason", "Needed.")
        self.assertIn("adaptive", self.cli(*args, expect=2))
        plan = self.state()["plan"]
        plan["tasks"][0]["adaptive"] = True
        self.cli("amend", "--plan-file", self.put("adaptive.json", plan), "--answer", "Permit refinement.")
        spec = self.refinement()
        spec["acceptance"] = ["Weaker outcome"]
        self.assertIn("fields", self.cli("refine", "T01", "--file", self.put("bad-refine.json", spec),
                                          "--reason", "Needed.", expect=2))
        (self.app / "calc.py").write_text("unplanned edit")
        self.assertIn("between tasks", self.cli(*args, expect=2))

    def test_refine_cannot_replace_checks_or_weaken_verification(self):
        plan = self.automated("characterization")
        plan["tasks"][0]["adaptive"] = True
        self.approve(plan)
        spec = dict(checks=dict(unit=dict(argv=["true"], workspace="app")))
        self.assertIn("replace", self.cli("refine", "T01", "--file", self.put("replace.json", spec),
                                           "--reason", "Needed.", expect=2))
        spec = dict(verification=dict(mode="manual", reason="Skip test-first"))
        self.assertIn("test-first", self.cli("refine", "T01", "--file", self.put("weaken.json", spec),
                                              "--reason", "Needed.", expect=2))

    def test_refine_preserves_pins_and_rejects_newly_exposed_ignored_contents(self):
        plan = self.automated("characterization")
        plan["tasks"][0]["adaptive"] = True
        (self.app / "dist").mkdir()
        (self.app / "dist/hidden.py").write_text("preexisting ignored work")
        self.approve(plan)
        self.cli("start", "T01")
        (self.app / "test_calc.py").write_text("pinned assertions")
        self.cli("test", "T01", "--stage", "pin", "--note", "Current behavior.")
        pin = self.state()["tasks"]["T01"]["test_checkpoint"]
        self.assertIn("previously untracked", self.cli("refine", "T01", "--file", self.put(
            "hidden.json", dict(paths=["dist/hidden.py"])), "--reason", "Needed.", expect=2))
        spec = dict(verification=self.refinement()["verification"])
        self.assertIn("already pinned", self.cli("refine", "T01", "--file", self.put("strategy.json", spec),
                                                 "--reason", "Needed.", expect=2))
        self.cli("refine", "T01", "--file", self.put("extra-path.json", dict(paths=["helper.py"])),
                 "--reason", "The existing behavior needs a helper.")
        self.assertEqual(self.state()["tasks"]["T01"]["test_checkpoint"], pin)
        self.assertEqual(self.state()["checks"]["unit"]["log"], pin["log"])

    def test_mechanical_test_update_preserves_original_pin_and_requires_current_green(self):
        plan = self.automated("characterization")
        plan["tasks"][0]["adaptive"] = True
        self.approve(plan)
        self.cli("start", "T01")
        (self.app / "test_calc.py").write_text("mode = 0\n")
        self.cli("test", "T01", "--stage", "pin", "--note", "Current behavior pinned.")
        original = self.state()["tasks"]["T01"]["test_checkpoint"]
        (self.app / "test_calc.py").write_text("mode = 0o0\n")
        evidence = self.put("correction.json", dict(kind="mechanical", reason="Correct the octal lint.",
                            evidence="Only the spelling of the zero literal changed; value, cases and assertions are identical."))
        args = ("test-update", "T01", "--file", evidence)
        self.assertIn("current", self.cli(*args, expect=2))
        self.cli("check", "unit")
        self.cli(*args)
        entry = self.state()["tasks"]["T01"]
        self.assertEqual(entry["test_updates"][0]["previous"], original)
        self.assertEqual((self.wf / original["files"]["app:test_calc.py"]).read_text(), "mode = 0\n")
        self.cli("done", "T01", "--result-file", self.result())
        self.review()
        self.cli("final")
        self.assertIn("test-update (manager)", (self.wf / "report.md").read_text())

    def test_test_update_rejects_strategy_change_and_needs_explicit_allowance(self):
        self.approve(self.automated("characterization"))
        self.cli("start", "T01")
        (self.app / "test_calc.py").write_text("assertions")
        self.cli("test", "T01", "--stage", "pin", "--note", "Pinned.")
        args = ("test-update", "T01", "--file", self.put("correction.json", dict(
            kind="mechanical", reason="Lint.", evidence="Equivalent literal.")))
        self.assertIn("adaptive", self.cli(*args, expect=2))

    def test_test_update_refuses_nonmechanical_changes_and_missing_original_copies(self):
        plan = self.automated("characterization")
        plan["tasks"][0]["adaptive"] = True
        self.approve(plan)
        self.cli("start", "T01")
        (self.app / "test_calc.py").write_text("original assertions")
        self.cli("test", "T01", "--stage", "pin", "--note", "Pinned.")
        spec = dict(kind="strategy", reason="Weaker expectation.", evidence="Changed assertion.")
        self.assertIn("mechanical", self.cli("test-update", "T01", "--file", self.put("semantic.json", spec), expect=2))
        bad = dict(spec, kind="mechanical", previous="Cannot inject checkpoint history")
        self.assertIn("mechanical", self.cli("test-update", "T01", "--file", self.put("extra-key.json", bad), expect=2))
        # Simulate a legacy pin written before original copies were retained.
        state = self.state()
        del state["tasks"]["T01"]["test_checkpoint"]["files"]
        (self.wf / ".tp/state.json").write_text(json.dumps(state))
        spec["kind"] = "mechanical"
        self.assertIn("copies unavailable", self.cli("test-update", "T01", "--file", self.put("legacy.json", spec), expect=2))

    def test_show_returns_one_task_without_workspace_fingerprints(self):
        self.approve()
        self.cli("start", "T01")
        before = {str(p): p.stat().st_mtime_ns for p in self.wf.rglob("*")}
        output = json.loads(self.cli("show", "T01"))
        self.assertEqual(output["task"]["id"], "T01")
        self.assertEqual(output["status"], "running")
        self.assertNotIn("before", output)
        self.assertEqual(before, {str(p): p.stat().st_mtime_ns for p in self.wf.rglob("*")})


if __name__ == "__main__":
    unittest.main()
