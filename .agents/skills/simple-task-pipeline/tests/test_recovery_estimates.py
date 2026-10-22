"""Fresh-process regressions: saved workflows survive interruption and time is advisory."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from harness import Harness


RESEARCH = [
    {"agent": "kb-author", "role": "author", "why": "Writes every article for D1."},
    {"agent": "codebase-researcher", "role": "research", "why": "Finds the source evidence for D1."},
]
FINAL = [
    {"agent": "kb-author", "role": "author", "why": "Writes every article for D1."},
    {"agent": "doc-reviewer", "role": "reviewer", "why": "Checks D1 against its sources."},
]
ESTIMATES = {"scope": 12, "research": 65, "planning": 40,
             "execution": 240, "review": 90, "closeout": 15}


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.h = Harness()

    def tearDown(self):
        self.h.close()

    def add_research(self, minutes=15):
        q = self.h.root / "questions.txt"
        q.write_text("Where is Add implemented?\n")
        self.h.tp("research", "add", "R1", "--agent", "codebase-researcher", "--purpose", "investigate",
                  "--questions-file", str(q), "--done-when", "The implementation is located.",
                  "--minutes", str(minutes))

    def tree(self):
        return {str(p.relative_to(self.h.wf)): p.read_bytes()
                for p in self.h.wf.rglob("*") if p.is_file()}

    def resume(self):
        return self.h.tp("resume", "--answer", "Resume this saved pipeline.", "--json").json()


class AdvisoryEstimatesTest(WorkflowTest):
    def test_long_task_is_valid_and_reported(self):
        h = self.h
        h.confirmed()
        h.write_json("plan.json", h.plan([h.task("T01", "a.md", estimate_min=4000)]))
        h.tp("plan", "check")
        self.assertIn("4000", (h.wf / "plan.md").read_text())

    def test_research_item_has_an_estimate_without_a_duration_cap(self):
        self.h.confirmed(participants=RESEARCH)
        self.add_research(minutes=65)
        self.assertEqual(self.h.state()["recon"]["R1"]["minutes"], 65)
        self.assertEqual(self.h.tp("noticed").out.strip(), "no open noticed items.")

    def test_estimates_need_not_fit_other_estimates(self):
        h = self.h
        h.init()
        h.write_json("scope.json", h.scope(participants=RESEARCH, budget_minutes=2,
                     research={"budget_minutes": 4000, "why": "Several source areas need investigation."}))
        h.tp("scope", "check")
        h.tp("scope", "confirm", "--answer", "Confirmed.")
        h.tp("budget", "extend", "--minutes", "10000", "--note", "Re-estimate the work.")
        self.assertEqual(h.read_json("scope.json")["budget_minutes"], 10002)

    def test_review_is_not_capped_by_minutes(self):
        h = self.h
        h.confirmed(participants=FINAL, review="final")
        tasks = [h.task(f"T{i:02}", f"a{i}.md") for i in range(1, 7)]
        h.write_json("plan.json", h.plan(tasks))
        h.tp("plan", "check")

    def test_solo_tasks_can_share_paths_without_invented_dependencies(self):
        h = self.h
        h.approved(h.plan([h.task("T01", "shared.md"), h.task("T02", "shared.md")], final_checks=[]))
        h.tp("dispatch", "T01")
        h.tp("dispatch", "T02", expect=2)
        h.good_article("shared.md")
        h.result("T01", "author", changed=["shared.md"])
        h.tp("record", "T01")
        h.tp("accept", "T01", "--note", "Verified the first change.")
        h.tp("dispatch", "T02")
        with (h.kb / "shared.md").open("a") as f:
            f.write("\nThe second change preserves the first.\n")
        h.result("T02", "author", changed=["shared.md"])
        h.tp("record", "T02")
        h.tp("accept", "T02", "--note", "Verified both changes together.")
        h.tp("final")

    def test_elapsed_planning_time_does_not_instruct_early_submission(self):
        h = self.h
        h.confirmed()
        st = h.state()
        st["agent_minutes"] = 5000
        h.write_json(".tp/state.json", st)
        self.assertEqual(h.next()["warnings"], [])

    def test_major_stage_and_total_estimates_are_reported(self):
        h = self.h
        h.confirmed(estimates=ESTIMATES)
        data = h.tp("status", "--json").json()
        self.assertEqual(data["estimates"]["stages"], ESTIMATES)
        self.assertEqual(data["estimates"]["total_min"], sum(ESTIMATES.values()))
        h.write_json("plan.json", h.plan([h.task("T01", "a.md", estimate_min=75)]))
        h.tp("plan", "check")
        h.tp("plan", "submit")
        h.tp("approve", "--answer", "Approved.")
        data = h.next()["estimates"]
        self.assertEqual(data["stages"]["execution"], 75)
        self.assertEqual(data["stages"]["review"], 0)
        self.assertEqual(data["total_min"], 207)
        for command in ("status", "digest", "report"):
            self.assertIn("207", h.tp(command).out)
        self.assertIn("207", (h.wf / "plan.md").read_text())


class ResumeTest(WorkflowTest):
    def test_resume_accepts_an_unhalted_session_after_context_loss(self):
        self.h.confirmed()
        self.h.tp("resume", "--answer", "Continue after the session was lost.")
        self.assertEqual(self.h.state()["phase"], "PLANNING")

    def test_scoping_without_a_draft_is_readable_and_resumable(self):
        self.h.init()
        before = self.tree()
        self.h.tp("status")
        self.h.tp("status", "--json")
        self.assertEqual(self.tree(), before)
        data = self.resume()
        self.assertEqual(data["phase"], "SCOPING")
        self.assertEqual(data["actions"][0]["action"], "scope")

    def test_status_is_read_only_including_its_liveness_marker(self):
        self.h.approved()
        self.h.next()
        before = self.tree()
        self.h.tp("status")
        self.h.tp("status", "--json")
        self.assertEqual(self.tree(), before)

    def test_interrupted_planning_keeps_existing_draft_and_completed_research(self):
        h = self.h
        h.confirmed(participants=RESEARCH)
        self.add_research()
        h.tp("dispatch", "R1")
        h.write_json("recon/R1.json", {"answers": [{"q": "Where is Add implemented?", "a": "calc/calc.go:5",
                     "evidence": ["src:calc/calc.go:5"]}], "followups": [], "unknowns": []})
        h.tp("record", "R1")
        h.write_json("plan.json", h.plan())
        before = self.tree()
        data = self.resume()
        self.assertEqual(data["phase"], "PLANNING")
        self.assertEqual(data["research"], {"R1": "done"})
        self.assertEqual(data["artifacts"]["plan"], str(h.wf / "plan.json"))
        self.assertEqual(h.state()["recon"]["R1"]["status"], "done")
        for name, contents in before.items():
            if name not in (".tp/state.json", ".tp/events.jsonl", "decisions.md"):
                self.assertEqual(self.tree()[name], contents)
        self.assertIn("existing", h.tp("next").out.lower())
        h.tp("plan", "check")
        h.tp("plan", "submit")

    def test_interrupted_research_exposes_checkpoint_and_does_not_offer_replanning(self):
        h = self.h
        h.confirmed(participants=RESEARCH)
        self.add_research()
        h.tp("dispatch", "R1")
        result = h.wf / "recon/R1.json"
        result.write_text('{"answers": []}')
        state = h.state()
        for name in ("brief", "result"):
            state["in_flight"]["R1"].pop(name, None)
        h.write_json(".tp/state.json", state)
        before = h.state()["in_flight"]
        data = self.resume()
        self.assertEqual(data["in_flight"], before)
        checkpoint = data["checkpoints"]["R1"]
        self.assertEqual(checkpoint["brief"], str(h.wf / "recon/R1.brief.md"))
        self.assertEqual(checkpoint["result"], str(result))
        self.assertTrue(checkpoint["result_exists"])
        self.assertNotIn("plan", [a["action"] for a in data["actions"]])
        self.assertEqual(result.read_text(), '{"answers": []}')

    def test_interrupted_task_retains_snapshot_result_partial_edits_and_accepted_siblings(self):
        h = self.h
        h.approved()
        h.author("T01", "architecture/overview.md")
        h.tp("accept", "T01", "--note", "Verified.")
        h.tp("dispatch", "T02")
        h.good_article("build/guide.md")
        h.result("T02", "author", changed=["build/guide.md"])
        state = h.state()
        for name in ("brief", "result"):
            state["in_flight"]["T02"].pop(name, None)
        h.write_json(".tp/state.json", state)
        original = h.state()
        data = self.resume()
        self.assertEqual(data["in_flight"], original["in_flight"])
        self.assertEqual(h.state()["tasks"], original["tasks"])
        self.assertEqual(h.state()["write_baseline"], original["write_baseline"])
        self.assertTrue(data["checkpoints"]["T02"]["result_exists"])
        self.assertEqual(data["checkpoints"]["T02"]["brief"], str(h.run_dir("T02") / "brief-author-0.md"))
        h.tp("record", "T02")
        h.tp("accept", "T02", "--note", "Recovered and verified.")
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "accepted")

    def test_interrupted_final_review_retains_round_and_result(self):
        h = self.h
        h.approved(h.plan([h.task("T01", "a.md")], final_checks=[]), participants=FINAL, review="final")
        h.author("T01", "a.md")
        h.tp("accept", "T01", "--note", "Verified.")
        sid = "B1/doc-reviewer"
        h.tp("dispatch", sid)
        h.write_json("runs/B1/doc-reviewer-1.json", {"batch": "B1", "verdict": "pass", "findings": []})
        state = h.state()
        for name in ("brief", "result"):
            state["in_flight"][sid].pop(name, None)
        h.write_json(".tp/state.json", state)
        original = h.state()["reviews"]
        data = self.resume()
        self.assertEqual(h.state()["reviews"], original)
        self.assertTrue(data["checkpoints"][sid]["result_exists"])
        h.tp("record", sid)
        h.tp("final")

    def test_resume_does_not_approve_pending_scope_or_plan(self):
        h = self.h
        h.confirmed()
        h.write_json("plan.json", h.plan())
        h.tp("plan", "submit")
        data = self.resume()
        self.assertEqual(data["phase"], "AWAITING_APPROVAL")
        self.assertEqual(data["actions"][0]["action"], "human")
        h.tp("dispatch", "T01", expect=2)

    def test_resume_preserves_pending_exception_and_task_blocks(self):
        h = self.h
        h.approved()
        h.tp("exception", "--summary", "Which output format should be used?")
        original = h.state()["blocked"]
        data = self.resume()
        self.assertEqual(data["blocked"], original)
        self.assertEqual(data["actions"][0]["action"], "human")
        h.tp("dispatch", "T01", expect=2)

    def test_halt_saves_an_unfinished_step_without_requiring_completion(self):
        h = self.h
        h.approved()
        h.tp("dispatch", "T01")
        (h.kb / "architecture").mkdir()
        (h.kb / "architecture/overview.md").write_text("# Partial work\n")
        original = h.state()["in_flight"]
        h.tp("halt", "--reason", "Stop now.")
        saved = h.read_json("halt.json")
        self.assertEqual(saved["in_flight"], original)
        self.assertEqual(h.next()["actions"], [{"action": "halted"}])
        self.resume()
        self.assertEqual(h.state()["in_flight"], original)
        self.assertEqual((h.kb / "architecture/overview.md").read_text(), "# Partial work\n")

    def test_status_reports_contract_drift_without_rewriting_it(self):
        h = self.h
        h.approved()
        with h.wf.joinpath("plan.json").open("a") as f:
            f.write("\n")
        before = self.tree()
        data = h.tp("status", "--json").json()
        self.assertTrue(data["drift"])
        self.assertIn("plan.json", h.tp("status").out)
        self.assertEqual(self.tree(), before)
        h.tp("dispatch", "T01", expect=2)


class CommandWiringTest(WorkflowTest):
    def test_documented_baseline_command_is_callable(self):
        h = self.h
        h.approved(h.plan([h.task("T01", "a.md")], final_checks=[]))
        h.tp("baseline")
        self.assertEqual(h.state()["final_baseline"], [])

    def test_all_supported_commands_have_cli_help(self):
        commands = "init status next digest closeout survey roster scope survey-issue research recon show triage halt hault resume schema plan amend widen budget lost clock baseline approve revise dispatch sample record accept reject exception resolve noticed note final report check-docs".split()
        for command in commands:
            with self.subTest(command=command):
                self.h.tp(command, "--help", wf=False)


class RecoveryBoundaryTest(WorkflowTest):
    def test_resume_with_scope_drift_cannot_start_work(self):
        h = self.h
        h.approved()
        scope = h.read_json("scope.json")
        scope["workspaces"][1]["mode"] = "write"
        h.write_json("scope.json", scope)
        self.assertTrue(self.resume()["drift"])
        h.tp("dispatch", "T01", expect=2)

    def test_final_cannot_advance_a_halted_or_blocked_pipeline(self):
        h = self.h
        h.approved(h.plan([h.task("T01", "a.md")], final_checks=[]))
        h.author("T01", "a.md")
        h.tp("accept", "T01", "--note", "Verified.")
        h.tp("halt", "--reason", "Wait for my next session.")
        h.tp("final", expect=2)
        self.resume()
        h.tp("exception", "--summary", "Confirm the delivery destination.")
        h.tp("final", expect=2)
        h.tp("resolve", "--exception", "--action", "answer", "--answer", "The approved destination.")
        h.tp("final")

    def test_noticed_resolution_numbers_follow_the_open_listing(self):
        h = self.h
        h.init()
        h.tp("note", "First unrelated finding.")
        h.tp("note", "Second unrelated finding.")
        h.tp("resolve", "--noticed", "1", "--action", "answer", "--answer", "First is settled.")
        self.assertIn("1. (manager) Second", h.tp("noticed").out)
        h.tp("resolve", "--noticed", "1", "--action", "answer", "--answer", "Second is settled.")
        self.assertEqual(h.tp("noticed").out.strip(), "no open noticed items.")

    def test_relocated_skill_recovers_a_saved_pipeline_from_another_cwd(self):
        from harness import SKILL
        h = self.h
        h.approved()
        h.tp("dispatch", "T01")
        h.good_article("architecture/overview.md")
        h.result("T01", "author", changed=["architecture/overview.md"])
        copied = h.root / "another agent" / "simple-task-pipeline"
        shutil.copytree(SKILL / "scripts", copied / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(SKILL / "references", copied / "references")
        result = subprocess.run([sys.executable, str(copied / "scripts/tp.py"), "-w", str(h.wf),
                                 "resume", "--answer", "Continue in this host.", "--json"],
                                cwd=str(h.root), capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["checkpoints"]["T01"]["result_exists"])
        h.tp("record", "T01")
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_check")


class DecisionGuidanceTest(WorkflowTest):
    def test_scope_confirmation_and_plan_approval_use_their_actual_commands(self):
        h = self.h
        h.init()
        h.write_json("scope.json", h.scope())
        h.tp("scope", "check")
        self.assertIn("tp scope confirm", h.tp("next").out)
        h.tp("scope", "confirm", "--answer", "Confirmed.")
        h.write_json("plan.json", h.plan())
        h.tp("plan", "submit")
        self.assertIn("tp approve", h.tp("next").out)

    def test_workflow_exception_blocks_planning_until_resolved(self):
        h = self.h
        h.confirmed()
        h.tp("exception", "--summary", "Which requirement applies?")
        self.assertEqual([a["action"] for a in h.next()["actions"]], ["human"])
        h.tp("resolve", "--exception", "--action", "answer", "--answer", "Use the confirmed scope.")
        self.assertEqual([a["action"] for a in h.next()["actions"]], ["plan"])


class RemainingCommandTest(WorkflowTest):
    def backdate(self, tid, minutes=10):
        from datetime import datetime, timedelta, timezone
        state = self.h.state()
        state["in_flight"][tid]["since"] = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.h.write_json(".tp/state.json", state)

    def test_sample_and_clock_operate_on_a_recorded_task(self):
        h = self.h
        h.approved()
        h.tp("dispatch", "T01")
        self.backdate("T01")
        h.good_article("architecture/overview.md")
        h.result("T01", "author", changed=["architecture/overview.md"])
        h.tp("record", "T01")
        self.assertIn("calc/calc.go:5", h.tp("sample", "T01").out)
        before = h.next()["agent_minutes"]
        h.tp("clock", "T01", "--dead-minutes", "3", "--note", "Backend stalled for three minutes.")
        self.assertAlmostEqual(h.next()["agent_minutes"], before - 3, delta=0.1)
        h.tp("clock", "T01", "--dead-minutes", "3", "--note", "A further three minutes were idle.")
        self.assertAlmostEqual(h.next()["agent_minutes"], before - 6, delta=0.1)

    def test_partial_dead_time_is_deducted_once_at_record(self):
        h = self.h
        h.approved()
        h.tp("dispatch", "T01")
        self.backdate("T01")
        h.good_article("architecture/overview.md")
        h.result("T01", "author", changed=["architecture/overview.md"])
        h.tp("record", "T01", "--dead-minutes", "3")
        self.assertAlmostEqual(h.next()["agent_minutes"], 7, delta=0.1)

    def test_lost_time_does_not_erase_previously_recorded_work(self):
        h = self.h
        h.approved()
        h.tp("dispatch", "T01")
        self.backdate("T01")
        h.good_article("architecture/overview.md")
        h.result("T01", "author", changed=["architecture/overview.md"])
        h.tp("record", "T01")
        h.tp("accept", "T01", "--note", "Verified.")
        before = h.next()["agent_minutes"]
        h.tp("dispatch", "T02")
        self.backdate("T02", 20)
        h.tp("lost", "T02", "--summary", "This step is unrecoverable.")
        self.assertAlmostEqual(h.next()["agent_minutes"], before, delta=0.1)

    def test_recon_alias_keeps_the_legacy_default_purpose(self):
        h = self.h
        h.confirmed(participants=RESEARCH)
        questions = h.root / "q.txt"
        questions.write_text("Where is Add implemented?\n")
        h.tp("recon", "add", "R1", "--agent", "codebase-researcher", "--questions-file", str(questions),
             "--done-when", "The source location is known.")
        self.assertEqual(h.state()["recon"]["R1"]["purpose"], "map")
        h.tp("recon", "drop", "R1", "--reason", "The saved source already answers this.")
        self.assertEqual(h.state()["recon"]["R1"]["status"], "dropped")


class CodeStepRecoveryTest(WorkflowTest):
    def test_resume_preserves_red_tests_implementation_fix_and_review_checkpoints(self):
        from harness import git
        h = self.h
        app = h.root / "app"
        app.mkdir()
        (app / "calc.py").write_text("def mul(a, b):\n    return 0\n")
        git(app, "init", "-q", "-b", "main")
        git(app, "add", "-A")
        git(app, "commit", "-q", "-m", "base")
        scope = dict(deliverables=[{"id": "D1", "kind": "code", "what": "Multiply integers."}],
                     workspaces=[{"name": "app", "path": str(app), "mode": "write"}], review="per-task",
                     participants=[{"agent": "code-author", "role": "author", "why": "Implements multiplication for D1."},
                                   {"agent": "test-author", "role": "tests", "why": "Tests multiplication for D1."},
                                   {"agent": "correctness-reviewer", "role": "reviewer", "why": "Checks D1 multiplication edge cases."}])
        task = h.task("T01", "calc.py", agent="code-author", workspace="app", paths=["calc.py", "test_calc.py"],
                      sources=["app:calc.py"], tests_paths=["test_calc.py"], acceptance=["mul(2, 3) returns 6."],
                      test_cmd="python3 -m unittest -q test_calc")
        h.approved(h.plan([task], final_checks=[]), **scope)
        h.tp("dispatch", "T01")
        (app / "test_calc.py").write_text("import unittest\nfrom calc import mul\nclass T(unittest.TestCase):\n"
                                        "    def test_mul(self):\n        self.assertEqual(mul(2, 3), 6)\n")
        self.assertEqual(self.resume()["checkpoints"]["T01"]["step"], "tests")
        h.result("T01", "tests", changed=["test_calc.py"])
        self.assertIn("red", h.tp("record", "T01").out)
        pinned = h.state()["tasks"]["T01"]["tests_hash"]
        h.tp("dispatch", "T01")
        (app / "calc.py").write_text("def mul(a, b):\n    return a * b\n")
        self.assertEqual(self.resume()["checkpoints"]["T01"]["step"], "impl")
        self.assertEqual(h.state()["tasks"]["T01"]["tests_hash"], pinned)
        h.result("T01", "impl", changed=["calc.py"])
        self.assertIn("green", h.tp("record", "T01").out)
        h.tp("dispatch", "T01")
        data = self.resume()
        self.assertEqual(data["checkpoints"]["T01"]["step"], "review")
        h.review("T01", 1, "changes", [{"id": "F1", "state": "missing", "blocking": True,
                                       "where": "calc.py:1", "issue": "The function has no docstring."}])
        h.tp("record", "T01")
        h.tp("dispatch", "T01")
        (app / "calc.py").write_text('def mul(a, b):\n    """Return the product of two integers."""\n    return a * b\n')
        data = self.resume()
        self.assertEqual(data["checkpoints"]["T01"]["step"], "fix")
        self.assertEqual(h.state()["tasks"]["T01"]["tests_hash"], pinned)
        h.result("T01", "fix", changed=["calc.py"])
        h.tp("record", "T01")
        h.tp("dispatch", "T01")
        h.review("T01", 2, "pass")
        h.tp("record", "T01")
        h.tp("accept", "T01", "--note", "Reviewed the code, tests, and fixed docstring.")
        h.tp("final")
        self.assertEqual(self.resume()["phase"], "DONE")
        self.assertEqual(self.resume()["actions"], [{"action": "done"}])


class CommandRecoveryEdgesTest(WorkflowTest):
    def test_halt_preserves_work_even_when_a_plan_edit_is_unfinished(self):
        h = self.h
        h.approved()
        h.tp("dispatch", "T01")
        original = h.state()["in_flight"]
        h.wf.joinpath("plan.json").write_text('{"tasks": [')
        h.tp("halt", "--reason", "Preserve this session now.")
        self.assertEqual(h.read_json("halt.json")["in_flight"], original)
        self.assertTrue(self.resume()["drift"])
        self.assertEqual(h.state()["in_flight"], original)

    def test_amend_resolves_conventions_from_the_saved_workflow(self):
        h = self.h
        h.confirmed()
        h.wf.joinpath("rules.md").write_text("# Rules\n\nUse the confirmed terms.\n")
        plan = h.plan(conventions=["wf:rules.md"])
        h.write_json("plan.json", plan)
        h.tp("plan", "submit")
        h.tp("approve", "--answer", "Approved with these conventions.")
        self.resume()
        plan["tasks"][0]["brief"] += " Include the confirmed terminology."
        h.write_json("plan.json", plan)
        h.tp("amend", "--reason", "Clarify the task brief.")
        self.assertEqual(h.state()["phase"], "EXECUTING")

    def test_amend_cannot_silently_replace_approved_acceptance(self):
        h = self.h
        h.approved()
        plan = h.read_json("plan.json")
        plan["tasks"][0]["acceptance"] = ["Write any text without checking sources."]
        h.write_json("plan.json", plan)
        h.tp("amend", "--reason", "Mechanical cleanup.", expect=2)

    def test_budget_extend_does_not_adopt_other_scope_changes(self):
        h = self.h
        h.approved()
        approved = h.state()["scope_sha"]
        scope = h.read_json("scope.json")
        scope["deliverables"][0]["what"] = "A different unapproved output."
        h.write_json("scope.json", scope)
        h.tp("budget", "extend", "--minutes", "60", "--note", "More time needed.", expect=2)
        self.assertEqual(h.state()["scope_sha"], approved)


class LegacyDraftRecoveryTest(WorkflowTest):
    def test_incomplete_plan_draft_preserves_known_scope_estimates(self):
        h = self.h
        h.confirmed(estimates=ESTIMATES)
        h.wf.joinpath("plan.json").write_text('{"tasks": [')
        data = self.resume()
        self.assertEqual(data["estimates"]["stages"], ESTIMATES)
        self.assertEqual(h.wf.joinpath("plan.json").read_text(), '{"tasks": [')
        self.assertEqual(data["phase"], "PLANNING")

    def test_legacy_approved_plan_can_be_recovered_then_mechanically_amended(self):
        h = self.h
        h.approved()
        h.wf.joinpath("plan.approved.json").unlink()
        tasks = h.state()["tasks"]
        self.resume()
        self.assertEqual(h.state()["tasks"], tasks)
        self.assertTrue(h.wf.joinpath("plan.approved.json").is_file())
        plan = h.read_json("plan.json")
        plan["tasks"][0]["estimate_min"] = 90
        h.write_json("plan.json", plan)
        h.tp("amend", "--reason", "Updated advisory duration estimate.")
        h.tp("dispatch", "T01")


class LegacyRoleRecoveryTest(WorkflowTest):
    def test_legacy_agent_id_does_not_replace_a_complete_local_fix_contract(self):
        h = self.h
        h.approved(h.plan([h.task("T01", "a.md")], final_checks=[]))
        h.author("T01", "a.md", agent_id="old-host-session")
        h.tp("reject", "T01", "--reason", "Explain the source evidence more clearly.")
        self.resume()
        h.tp("dispatch", "T01")
        brief = h.run_dir("T01").joinpath("brief-fix-1.md").read_text()
        self.assertIn(str(h.kb / "a.md"), brief)
        self.assertIn("Explains what Add does, citing src path:line.", brief)
        self.assertIn(str(h.wf / "scope.md"), brief)
