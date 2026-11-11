"""Autonomous scoping, honest recovery, and bounded bookkeeping regressions.

Reviewer identities here are explicit scripted fixtures, not real agent evaluations.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import test_tp as fixtures


class AutonomousTest(unittest.TestCase):
    tearDown = fixtures.PipelineTest.tearDown
    put = fixtures.PipelineTest.put
    task = fixtures.PipelineTest.task
    plan = fixtures.PipelineTest.plan
    result = fixtures.PipelineTest.result
    automated = fixtures.PipelineTest.automated

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="co-autonomous-")
        self.base = Path(self.temp.name).resolve()
        self.app = self.base / "app"
        self.app.mkdir()
        self.request = self.base / "request.txt"
        self.request.write_text("Write an accurate overview; preserve existing work.\n")
        self.wf = None
        output = self.cli("init", str(self.base / "planning"), "--title", "Overview", "--request-file", str(self.request))
        self.wf = Path(output.splitlines()[0].removeprefix("workflow: "))

    def cli(self, *args, expect=0, payload=None):
        cmd = [sys.executable, "-B", str(fixtures.SCRIPT)]
        if self.wf:
            cmd += ["-w", str(self.wf)]
        run = subprocess.run(cmd + list(args), input=json.dumps(payload) if payload is not None else None,
                             capture_output=True, text=True, timeout=20,
                             env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(run.returncode, expect, run.stdout + run.stderr)
        return run.stdout + run.stderr

    def state(self):
        # Tests inspect the public JSON state, whose large checkpoints are references.
        return json.loads((self.wf / ".tp/state.json").read_text())

    def scope(self):
        value = fixtures.PipelineTest.scope(self)
        value.update(max_agents=2, requirements=[dict(id="R1", text="Accurate overview", deliverables=["D1"])])
        return value

    def settle(self, plan=None, scope=None):
        self.put("scope.json", scope or self.scope())
        self.cli("scope", "settle")
        plan = copy.deepcopy(plan or self.plan())
        for task in plan["tasks"]:
            task["requirements"] = ["R1"]
        self.put("plan.json", plan)
        self.cli("plan", "check")

    def reviewer(self, purpose="plan", aid="A1", finish=True, **extra):
        brief = dict(role="review", purpose=purpose, requirements=["R1"], question="Verify request, plan and evidence.",
                     paths=[str(self.app)], done_when="Return confirmed defects and requirement coverage.",
                     model="TERRA", reasoning="high", model_reason="Bounded independent correctness review.")
        brief.update(extra)
        self.cli("agent", "reserve", "--id", aid, "--capacity", "2", "--file", "-", payload=brief)
        self.cli("agent", "attach", "--id", aid, "--agent-id", "scripted-independent-" + aid)
        if finish:
            self.finish_reviewer(aid)
        return aid

    def finish_reviewer(self, aid="A1", **extra):
        result = dict(accepted=True, summary="Reviewed requirements, exact plan and evidence.",
                      evidence=["request.md; plan.md; current tests and saved baseline"],
                      validation="Scripted fixture review record only, not an actual agent execution.", unresolved=[])
        result.update(extra)
        self.cli("agent", "finish", "--id", aid, "--file", "-", payload=result)

    def accept(self, plan=None, scope=None):
        self.settle(plan, scope)
        self.reviewer()
        self.cli("plan", "accept", "--agent", "A1")

    def finish_task(self, tid="T01", path="a.md"):
        self.cli("start", tid)
        (self.app / path).write_text("# Application\nAccurate overview.\n")
        self.cli("done", tid, "--result-file", "-", payload=dict(task=tid, summary="Overview delivered.",
                 acceptance=[dict(criterion=1, evidence=path + ":1 matches source.")]))

    def test_default_plan_requires_completed_independent_review_and_no_open_question(self):
        self.settle()
        self.assertIn("independent", self.cli("approve", "--answer", "yes", expect=2))
        self.assertIn("completed", self.cli("plan", "accept", "--agent", "missing", expect=2))
        self.reviewer(finish=False)
        self.cli("plan", "accept", "--agent", "A1", expect=2)
        self.finish_reviewer()
        self.cli("block", "--question", "Which audience should the overview address?")
        self.assertIn("questions", self.cli("plan", "accept", "--agent", "A1", expect=2))
        self.cli("resolve", "--answer", "Project developers.")
        self.assertIn("stale",self.cli("plan", "accept", "--agent", "A1",expect=2))
        self.reviewer(aid="A2")
        self.cli("plan", "accept", "--agent", "A2")
        state = self.state()
        self.assertEqual(state["phase"], "EXECUTING")
        self.assertNotIn("approve", [e["action"] for e in state["history"]])
        self.assertEqual(set(state["baseline"]), {"$snapshot"})

    def test_plan_review_rejects_stale_request_plan_source_unresolved_and_author(self):
        self.settle()
        self.reviewer()
        original = self.request.read_text()
        (self.wf / "request.md").write_text(original + "Extra requested detail.")
        self.assertIn("stale", self.cli("plan", "accept", "--agent", "A1", expect=2))
        (self.wf / "request.md").write_text(original)
        plan = json.loads((self.wf / "plan.json").read_text())
        plan["summary"] += " Revised order."
        self.put("plan.json", plan)
        self.assertIn("stale", self.cli("plan", "accept", "--agent", "A1", expect=2))
        self.reviewer(aid="A2", finish=False)
        self.finish_reviewer("A2", unresolved=["Missing scope decision"])
        self.assertIn("completed", self.cli("plan", "accept", "--agent", "A2", expect=2))
        self.reviewer(aid="A3", finish=False)
        # No completed reviewer can be attached to the main author identity.
        brief = dict(role="review", purpose="plan", requirements=["R1"], question="Review", paths=[str(self.app)],
                     done_when="Done", model="TERRA", reasoning="high", model_reason="Independent review")
        self.cli("agent", "reserve", "--id", "A4", "--capacity", "2", "--file", "-", payload=brief)
        self.assertIn("author", self.cli("agent", "attach", "--id", "A4", "--agent-id", "main", expect=2))

    def test_plan_review_requires_explicit_typed_unresolved_list(self):
        self.settle()
        self.reviewer(finish=False)
        result = dict(accepted=True, summary="Reviewed the plan.", evidence=["plan.md"],
                      validation="Scripted schema validation fixture.")
        malformed = [result] + [dict(result, unresolved=value) for value in
                               (None, False, {}, "", "Missing requirement", [None], [""], [{"issue": "Missing requirement"}])]
        for payload in malformed:
            with self.subTest(payload=payload):
                self.assertIn("unresolved", self.cli("agent", "finish", "--id", "A1", "--file", "-",
                                                    payload=payload, expect=2))
                self.assertEqual(self.state()["agents"]["A1"]["status"], "running")
                self.cli("plan", "accept", "--agent", "A1", expect=2)
        self.finish_reviewer()
        self.cli("plan", "accept", "--agent", "A1")

    def test_plan_accept_rejects_malformed_previously_saved_unresolved_list(self):
        self.settle()
        self.reviewer()
        state = self.state()
        path = self.wf / ".tp/state.json"
        for value in (None, False, {}, ""):
            with self.subTest(value=value):
                state["agents"]["A1"]["unresolved"] = value
                path.write_text(json.dumps(state))
                self.assertIn("unresolved", self.cli("plan", "accept", "--agent", "A1", expect=2))
                self.assertEqual(self.state()["phase"], "PLANNING")
        state["agents"]["A1"].pop("unresolved")
        path.write_text(json.dumps(state))
        self.cli("plan", "accept", "--agent", "A1", expect=2)

    def test_plan_review_can_continue_after_multiple_rejected_revisions(self):
        self.settle()
        for number in range(3):
            aid = "A" + str(number + 1)
            self.reviewer(aid=aid, finish=False)
            self.finish_reviewer(aid, accepted=False, unresolved=["Clarify delivery sequence."])
            self.cli("plan", "accept", "--agent", aid, expect=2)
            plan = json.loads((self.wf / "plan.json").read_text())
            plan["summary"] += " Revised delivery sequence."
            self.put("plan.json", plan)
            self.cli("plan", "check")
        self.reviewer(aid="A4")
        self.cli("plan", "accept", "--agent", "A4")
        self.assertEqual(self.state()["phase"], "EXECUTING")

    def test_final_review_rejects_empty_changes_and_malformed_findings(self):
        self.accept()
        self.finish_task()
        review = dict(method="self", verdict="changes", summary="Scripted invalid review fixture.", findings=[],
                      requirements=[dict(id="R1", evidence="a.md matches request.")])
        payloads = [review,
                    dict(review, findings=[dict(issue="Incorrect overview", evidence="a.md:1")]),
                    dict(review, verdict="pass", findings=[dict(task="T01", issue="Incorrect overview", evidence="a.md:1")]),
                    dict(review, verdict="pass", requirements=[dict(evidence="Missing requirement id.")])]
        for payload in payloads:
            with self.subTest(payload=payload):
                output = self.cli("review", "--file", "-", payload=payload, expect=2)
                self.assertNotIn("Traceback", output)
                self.assertIsNone(self.state()["review"])
                self.cli("final", expect=2)

    def test_success_output_with_error_words_cannot_be_red_evidence(self):
        self.accept(self.automated("red-green", [sys.executable, "-B", "-c", "print('0 errors; no failures')"]))
        self.cli("start", "T01")
        (self.app / "test_calc.py").write_text("Scripted fixture\n")
        self.cli("test", "T01", "--stage", "red", "--note", "This successful run must not count as red.", expect=2)
        state = self.state()
        self.assertNotIn("test_checkpoint", state["tasks"]["T01"])
        self.assertEqual(state["checks"]["unit"]["exit_code"], 0)
        self.assertIn("0 errors", (self.wf / state["checks"]["unit"]["log"]).read_text())
        self.cli("done", "T01", "--result-file", self.result(), expect=2)

    def test_autonomous_scope_rejects_no_independent_reviewer_capacity(self):
        scope=self.scope();scope["max_agents"]=0
        self.put("scope.json",scope)
        self.assertIn("independent plan reviewer",self.cli("scope","settle",expect=2))
        self.assertEqual(self.state()["phase"],"SCOPING")

    def test_markdown_is_readable_and_json_payloads_need_no_files(self):
        self.accept()
        plan = (self.wf / "plan.md").read_text()
        self.assertIn("### T01: Overview", plan)
        self.assertIn("1. Explain the application.", plan)
        self.assertNotIn("```json", plan)
        self.assertNotIn('"tasks"', plan)
        (self.wf / "bad.md").write_text('# A Markdown document, never a JSON payload.\n')
        self.assertIn(".json", self.cli("closeout", "--file", str(self.wf / "bad.md"), expect=2))
        self.cli("note", "Unrelated optional article could be useful.")
        self.finish_task()
        review = dict(method="self", verdict="pass", summary="Verified requested overview.", findings=[],
                      requirements=[dict(id="R1", evidence="a.md:1; complete original request")])
        self.cli("review", "--file", "-", payload=review)
        self.cli("final")
        self.assertEqual(self.state()["phase"], "COMPLETE")
        root_files = {p.name for p in self.wf.iterdir() if p.is_file()}
        self.assertEqual(root_files - {"bad.md"}, {"request.md", "scope.json", "scope.md", "plan.json", "plan.md", "report.md", "metrics.json"})
        self.assertIn("observation", (self.wf / "report.md").read_text())

    def test_batch_preserves_success_and_stops_before_later_steps(self):
        self.accept()
        steps = [dict(argv=["start", "T01"]),
                 dict(argv=["done", "T01", "--result-file", "-"], input={"task":"T01", "summary":"Incomplete evidence", "acceptance":[]}),
                 dict(argv=["note", "must not execute"])]
        self.cli("batch", "--file", "-", payload=steps, expect=2)
        self.assertEqual(self.state()["tasks"]["T01"]["status"], "running")
        self.assertEqual(self.state()["notes"], [])
        result = dict(task="T01", summary="Complete", acceptance=[dict(criterion=1,evidence="Inspected source")])
        output = self.cli("batch", "--file", "-", payload=[dict(argv=["done", "T01", "--result-file", "-"],input=result)])
        self.assertIn("review:", output)
        self.assertEqual(self.state()["tasks"]["T01"]["status"], "done")

    def test_manager_runner_correction_retains_delivery_and_revalidates_without_dependency_deadlock(self):
        first = self.task()
        second = self.task("T02", "b.md", ["T01"])
        third = self.task("T03", "c.md", ["T02"])
        plan = self.plan([first, second, third])
        plan["checks"]["unit"] = dict(argv=[sys.executable, "-B", "-c", "print('original')"],workspace="app",reuse=True)
        first["checks"] = second["checks"] = ["unit"]
        plan["final_checks"] = ["unit"]
        self.accept(plan)
        for tid, path in [("T01","a.md"),("T02","b.md"),("T03","c.md")]:
            self.cli("start",tid)
            (self.app/path).write_text("Overview\n")
            self.cli("check","unit")
            self.cli("done",tid,"--result-file",self.result(tid))
        changed = json.loads((self.wf/"plan.json").read_text())
        changed["checks"]["unit"]["argv"][-1] = "print('corrected runner')"
        draft=self.put("draft.json",changed)
        self.cli("amend","--by","manager","--reason","Correct runner invocation; behavior and cases unchanged.","--plan-file",draft,expect=2)
        self.reviewer(purpose="amendment",aid="A2",plan_file="draft.json")
        self.cli("amend","--by","manager","--reason","Correct runner invocation; behavior and cases unchanged.","--plan-file",draft,"--agent","A2")
        state=self.state()
        self.assertTrue(all(t["status"]=="done" for t in state["tasks"].values()))
        self.assertEqual(set(state["verification_dirty"]),{"T01","T02","T03"})
        self.assertIn("revalidate",self.cli("next"))
        self.cli("check","unit")
        self.assertIn("review:",self.cli("next"))
        self.assertEqual(self.state()["verification_dirty"],{})
        self.assertEqual(sum(e["action"]=="done" for e in self.state()["history"]),3)
        self.cli("reopen","T01","--reason","Confirmed change to prerequisite.")
        self.assertEqual(self.state()["tasks"]["T02"]["status"],"done")
        self.assertIn("T02",self.state()["verification_dirty"])

    def test_manager_cannot_change_scope_acceptance_or_adopt_external_edits(self):
        self.accept()
        changed=json.loads((self.wf/"plan.json").read_text())
        changed["tasks"][0]["acceptance"]=["Weaker promise"]
        self.assertIn("acceptance",self.cli("amend","--by","manager","--reason","Routine","--plan-file",self.put("draft.json",changed),expect=2))
        (self.app/"other.txt").write_text("operator edit")
        self.assertIn("cannot adopt",self.cli("amend","--by","manager","--reason","Routine",expect=2))
        self.assertEqual((self.app/"other.txt").read_text(),"operator edit")

    def test_monitored_docs_exclude_archives_but_include_task_and_glob_inputs_with_additions_deletions(self):
        (self.app/"archive").mkdir(); (self.app/"archive/history.json").write_text("large history")
        (self.app/"source").mkdir(); (self.app/"source/one.py").write_text("one")
        (self.app/"readme.txt").write_text("reference")
        scope=self.scope();scope["workspaces"][0]["monitor"]=["readme.txt"]
        plan=self.plan();plan["checks"]["source"]=dict(argv=[sys.executable,"-c","print('pass')"],workspace="app",reuse=True,inputs={"app":["source/**/*.py"]})
        plan["tasks"][0]["checks"]=["source"]
        self.accept(plan,scope)
        self.cli("start","T01");self.cli("check","source")
        original=self.state()["checks"]["source"]["fingerprint"]
        (self.app/"archive/history.json").write_text("archive changed")
        self.assertIn("reused",self.cli("check","source"))
        (self.app/"source/new.py").write_text("new")
        self.cli("check","source");self.assertNotEqual(original,self.state()["checks"]["source"]["fingerprint"])
        (self.app/"source/new.py").unlink()
        self.cli("check","source");self.assertEqual(original,self.state()["checks"]["source"]["fingerprint"])
        (self.app/"a.md").write_text("planned write outside monitor still checked")
        self.cli("done","T01","--result-file",self.result())
        self.assertIn("app:a.md",self.state()["tasks"]["T01"]["changes"])

    def test_git_ignored_glob_inputs_remain_freshness_dependencies(self):
        subprocess.run(["git","init","-q",str(self.app)],check=True)
        (self.app/".gitignore").write_text("generated/\n")
        (self.app/"generated").mkdir()
        data=self.app/"generated/a.json";data.write_text("one")
        scope=self.scope();scope["workspaces"][0]["snapshot"]="git"
        plan=self.plan();plan["checks"]["unit"]=dict(argv=[sys.executable,"-c","print('ok')"],workspace="app",reuse=True,inputs={"app":["generated/**/*.json"]})
        plan["tasks"][0]["checks"]=["unit"]
        self.accept(plan,scope);self.cli("start","T01");self.cli("check","unit")
        first=self.state()["checks"]["unit"]["fingerprint"]
        data.write_text("two");self.cli("check","unit")
        self.assertNotEqual(first,self.state()["checks"]["unit"]["fingerprint"])
        second=self.state()["checks"]["unit"]["fingerprint"]
        (self.app/"generated/b.json").write_text("new");self.cli("check","unit")
        self.assertNotEqual(second,self.state()["checks"]["unit"]["fingerprint"])

    def test_scoped_check_retry_requires_diagnosis_and_never_pretends_a_pass(self):
        plan=self.automated(argv=[sys.executable,"-c","raise SystemExit(1)"])
        self.accept(plan);self.cli("start","T01")
        self.cli("check","unit",expect=2);self.cli("check","unit",expect=2)
        self.assertIn("diagnose",self.cli("check","unit",expect=2))
        self.cli("check","unit","--retry-reason","Readiness check confirms fixture cause under investigation",expect=2)
        self.assertNotEqual(self.state()["checks"]["unit"]["exit_code"],0)
        self.assertEqual(sum(e["action"]=="check" for e in self.state()["history"]),3)

    def test_semantic_test_mistake_is_repaired_without_human_approval_and_original_pin_is_archived(self):
        (self.app/"calc.py").write_text("def mul(a,b): return a+b\n")
        plan=self.plan();task=plan["tasks"][0]
        task.update(kind="code",adaptive=True,paths=["calc.py","test_calc.py"],checks=["unit"],verification=dict(mode="red-green",check="unit",test_paths=["test_calc.py"],reason="Catch incorrect multiplication"))
        plan["checks"]["unit"]=dict(argv=[sys.executable,"-B","-m","unittest","test_calc"],workspace="app",reuse=True)
        self.accept(plan);self.cli("start","T01")
        test=self.app/"test_calc.py"
        # Accidental wrong expectation. Corrected later with genuine baseline red.
        test.write_text("import unittest\nfrom calc import mul\nclass Test(unittest.TestCase):\n def test_mul(self): self.assertEqual(mul(2,3),7)\n")
        self.cli("test","T01","--stage","red","--note","Observed wrong multiplication behavior")
        original=copy.deepcopy(self.state()["tasks"]["T01"]["test_checkpoint"])
        test.write_text(test.read_text().replace(",7)",",6)"))
        baseline=self.base/"baseline";baseline.mkdir()
        (baseline/"calc.py").write_text("def mul(a,b): return a+b\n")
        (baseline/"test_calc.py").write_text(test.read_text())
        (baseline/"source-link").symlink_to(self.app/"calc.py")
        self.assertIn("symlinks",self.cli("correction-proof","T01","--baseline",str(baseline),"--identity","pre-fix source",expect=2))
        (baseline/"source-link").unlink()
        self.assertIn("isolated",self.cli("correction-proof","T01","--baseline",str(self.app),"--identity","invalid live baseline",expect=2))
        output=self.cli("correction-proof","T01","--baseline",str(baseline),"--identity","Exact pre-fix calc.py with a+b; corrected multiplication assertions")
        proof_id=output.split("Baseline proof recorded: ")[1].split(";")[0]
        receipt=self.state()["proofs"][proof_id]
        self.assertEqual(receipt["exit_code"],1)
        (self.app/"calc.py").write_text("def mul(a,b): return a*b\n")
        self.cli("check","unit")
        correction=dict(kind="correction",reason="Correct expected result 7 to 6 for multiplication.",evidence="Original request requires mathematical multiplication; corrected test fails on add implementation.",agent="A2",regression=dict(basis="reproduced",operation=proof_id,evidence="AssertionError 5 != 6, imports succeed."))
        self.assertIn("reviewer",self.cli("test-update","T01","--file","-",payload=correction,expect=2))
        self.reviewer(purpose="test-correction",aid="A2",task="T01",proof=proof_id,inputs={"app":["calc.py"]})
        reviewed_tests=test.read_text()
        test.write_text(reviewed_tests+"# Changed after independent review\n")
        self.cli("check","unit")
        self.assertIn("stale",self.cli("test-update","T01","--file","-",payload=correction,expect=2))
        test.write_text(reviewed_tests)
        self.cli("check","unit")
        fake=copy.deepcopy(correction);fake["regression"]["operation"]="made-up"
        self.assertIn("receipt",self.cli("test-update","T01","--file","-",payload=fake,expect=2))
        mislabeled=dict(kind="mechanical",reason="Claim mechanical",evidence="Claims cannot authorize weakening tests.")
        self.assertIn("reviewed",self.cli("test-update","T01","--file","-",payload=mislabeled,expect=2))
        self.cli("test-update","T01","--file","-",payload=correction)
        entry=self.state()["tasks"]["T01"]
        self.assertEqual(entry["test_updates"][0]["previous"],original)
        self.assertEqual(entry["test_checkpoint"]["log"],receipt["log"])
        self.assertTrue(self.state()["evidence_history"])
        self.cli("done","T01","--result-file",self.result())
        self.assertNotIn("amend",[e["action"] for e in self.state()["history"]])

    def test_next_recovers_detached_check_receipt_without_replaying_it(self):
        marker=self.base/"worker-started"
        plan=self.automated(argv=[sys.executable,"-B","-c",
             "from pathlib import Path; import time; Path("+repr(str(marker))+").touch(); time.sleep(0.5)"])
        self.accept(plan);self.cli("start","T01")
        process=subprocess.Popen([sys.executable,"-B",str(fixtures.SCRIPT),"-w",str(self.wf),"check","unit"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            deadline=time.monotonic()+5
            while not marker.exists() and time.monotonic()<deadline:
                time.sleep(0.02)
            self.assertTrue(marker.exists())
            process.kill();process.communicate(timeout=5)
            operation=next(iter(self.state()["operations"].values()))
            receipt=self.wf/operation["receipt"]
            deadline=time.monotonic()+5
            while not receipt.exists() and time.monotonic()<deadline:
                time.sleep(0.02)
            self.assertTrue(receipt.exists())
            self.cli("next")
            self.assertEqual(self.state()["checks"]["unit"]["exit_code"],0)
            self.assertEqual(sum(e["action"]=="check" for e in self.state()["history"]),1)
            self.cli("next")
            self.assertEqual(sum(e["action"]=="check" for e in self.state()["history"]),1)
        finally:
            if process.poll() is None:
                process.kill();process.communicate(timeout=5)

    def test_compact_checkpoint_store_deduplicates_and_status_is_read_only(self):
        for i in range(100):
            (self.app/f"source-{i}.txt").write_text("tracked evidence")
        self.accept()
        self.cli("start","T01")
        import sqlite3
        with sqlite3.connect(self.wf/".tp/snapshots.sqlite3") as db:
            self.assertEqual(db.execute("select count(*) from snapshots").fetchone()[0],1)
        before={str(p):p.stat().st_mtime_ns for p in self.wf.rglob("*")}
        self.cli("status");self.cli("packet","T01")
        self.assertEqual(before,{str(p):p.stat().st_mtime_ns for p in self.wf.rglob("*")})
        (self.app/"other.txt").write_text("out of contract")
        self.assertIn("outside",self.cli("done","T01","--result-file",self.result(),expect=2))


if __name__ == "__main__":
    unittest.main()
