"""Independent final review must represent an actual current, whole-change assignment."""
import copy
import sys
import unittest

import test_autonomous as fixtures


class FinalReviewTest(unittest.TestCase):
    setUp = fixtures.AutonomousTest.setUp
    tearDown = fixtures.AutonomousTest.tearDown
    cli = fixtures.AutonomousTest.cli
    put = fixtures.AutonomousTest.put
    state = fixtures.AutonomousTest.state
    scope = fixtures.AutonomousTest.scope
    task = fixtures.AutonomousTest.task
    plan = fixtures.AutonomousTest.plan
    result = fixtures.AutonomousTest.result
    settle = fixtures.AutonomousTest.settle
    reviewer = fixtures.AutonomousTest.reviewer
    finish_reviewer = fixtures.AutonomousTest.finish_reviewer
    accept = fixtures.AutonomousTest.accept
    finish_task = fixtures.AutonomousTest.finish_task

    def prepare(self):
        scope = self.scope()
        scope["review"] = "independent"
        self.accept(scope=scope)
        self.finish_task()

    def review_result(self, **changes):
        result = dict(method="independent", agent="A2", agent_id="scripted-independent-A2",
                      verdict="pass", summary="Verified the whole change and request coverage.", findings=[],
                      requirements=[dict(id="R1", evidence="Compared a.md with request.md and the source.")])
        result.update(changes)
        return result

    def record(self, result=None, expect=0):
        return self.cli("review", "--file", "-", payload=result or self.review_result(), expect=expect)

    def test_invented_or_plan_reviewer_identity_cannot_clear_final_gate(self):
        self.prepare()
        self.record(expect=2)
        self.record(self.review_result(agent="A1", agent_id="scripted-independent-A1"), expect=2)
        self.assertIsNone(self.state()["review"])
        self.cli("final", expect=2)

    def test_completed_current_assignment_permits_final_and_binds_identity(self):
        self.prepare()
        self.reviewer(purpose="final", aid="A2")
        self.record(self.review_result(agent_id="someone-else"), expect=2)
        self.record()
        self.cli("final")
        self.assertEqual(self.state()["phase"], "COMPLETE")

    def test_unfinished_rejected_and_unresolved_reviews_cannot_pass(self):
        self.prepare()
        self.reviewer(purpose="final", aid="A2", finish=False)
        self.record(expect=2)
        self.finish_reviewer("A2", accepted=False, unresolved=["Incorrect description"])
        self.record(expect=2)
        self.reviewer(purpose="final", aid="A3", finish=False)
        self.finish_reviewer("A3", unresolved=["Missing source verification"])
        self.record(self.review_result(agent="A3", agent_id="scripted-independent-A3"), expect=2)

    def test_final_reviewer_return_requires_explicit_unresolved_list(self):
        self.prepare()
        self.reviewer(purpose="final", aid="A2", finish=False)
        result = dict(accepted=True, summary="Inspected change.", evidence=["a.md"], validation="Fixture only.")
        for value in ("missing", None, False, {}, "", [""]):
            with self.subTest(value=value):
                payload = copy.deepcopy(result)
                if value != "missing":
                    payload["unresolved"] = value
                self.cli("agent", "finish", "--id", "A2", "--file", "-", payload=payload, expect=2)
                self.assertEqual(self.state()["agents"]["A2"]["status"], "running")
        self.finish_reviewer("A2")
        self.record()

    def test_source_repair_invalidates_completed_review_and_new_review_can_finish(self):
        self.prepare()
        self.reviewer(purpose="final", aid="A2")
        self.cli("reopen", "T01", "--reason", "Correct inaccurate source citation.")
        self.cli("start", "T01")
        (self.app / "a.md").write_text("Corrected source citation.\n")
        self.cli("done", "T01", "--result-file", self.result())
        self.assertIn("source", self.record(expect=2))
        self.reviewer(purpose="final", aid="A3")
        self.record(self.review_result(agent="A3", agent_id="scripted-independent-A3"))
        self.cli("final")

    def test_changed_request_invalidates_review_even_when_source_is_unchanged(self):
        self.prepare()
        self.reviewer(purpose="final", aid="A2")
        for name in ("request.md", "plan.md"):
            with self.subTest(name=name):
                path = self.wf / name
                original = path.read_text()
                path.write_text(original + "Use the current source revision.\n")
                self.assertIn("stale", self.record(expect=2))
                path.write_text(original)

    def test_request_edit_after_recording_review_blocks_completion(self):
        self.prepare()
        self.reviewer(purpose="final", aid="A2")
        self.record()
        for name in ("request.md", "plan.md"):
            with self.subTest(name=name):
                path = self.wf / name
                original = path.read_text()
                path.write_text(original + "Use the current source revision.\n")
                self.assertIn("review", self.cli("next"))
                self.cli("final", expect=2)
                path.write_text(original)

    def test_confirmed_findings_reopen_owner_without_requiring_a_clean_review(self):
        self.prepare()
        self.reviewer(purpose="final", aid="A2", finish=False)
        self.finish_reviewer("A2", unresolved=["Incorrect source citation"])
        self.record(self.review_result(verdict="changes", findings=[dict(
            task="T01", issue="Incorrect source citation", evidence="a.md:2 contradicts source.")]))
        self.assertEqual(self.state()["tasks"]["T01"]["status"], "pending")
        self.cli("final", expect=2)

    def test_final_assignment_cannot_narrow_source_or_requirements(self):
        self.prepare()
        brief = dict(role="review", purpose="final", requirements=["R1"],
                     paths=[str(self.app)], question="Review whole change.", done_when="Return evidence.")
        for changes in (dict(inputs={"app": ["a.md"]}), dict(requirements=[]), dict(task="T01"), dict(role="research")):
            with self.subTest(changes=changes):
                self.cli("agent", "reserve", "--id", "A2", "--capacity", "2", "--file", "-",
                         payload=dict(brief, **changes), expect=2)

    def test_final_assignment_waits_for_tasks_and_actual_final_check(self):
        scope = self.scope()
        scope["review"] = "independent"
        plan = self.plan()
        plan["checks"] = dict(unit=dict(argv=[sys.executable, "-B", "-c", "print('verified')"], workspace="app"))
        plan["final_checks"] = ["unit"]
        self.accept(plan, scope)
        brief = dict(role="review", purpose="final", requirements=["R1"],
                     paths=[str(self.app)], question="Review whole change.", done_when="Return evidence.")
        self.cli("agent", "reserve", "--id", "A2", "--capacity", "2", "--file", "-", payload=brief, expect=2)
        self.finish_task()
        self.cli("agent", "reserve", "--id", "A2", "--capacity", "2", "--file", "-", payload=brief, expect=2)
        self.cli("check", "unit")
        self.reviewer(purpose="final", aid="A2")
        self.record()
        self.cli("final")

    def test_dirty_task_only_verification_must_be_current_before_final_assignment(self):
        scope = self.scope()
        scope["review"] = "independent"
        plan = self.plan()
        second = self.task("T02", "b.md", ["T01"])
        second.update(checks=["unit"], verification=dict(mode="existing", check="unit", reason="Verify overview."))
        plan["tasks"].append(second)
        plan["checks"] = dict(unit=dict(argv=[sys.executable, "-B", "-c", "print('verified')"], workspace="app"))
        self.accept(plan, scope)
        self.finish_task()
        self.cli("start", "T02")
        (self.app / "b.md").write_text("Companion overview.\n")
        self.cli("done", "T02", "--verify", "--result-file", self.result("T02"))
        self.cli("reopen", "T01", "--reason", "Update citation.")
        self.cli("start", "T01")
        (self.app / "a.md").write_text("Corrected overview.\n")
        self.cli("done", "T01", "--result-file", self.result())
        brief = dict(role="review", purpose="final", requirements=["R1"],
                     paths=[str(self.app)], question="Review whole change.", done_when="Return evidence.")
        output = self.cli("agent", "reserve", "--id", "A2", "--capacity", "2", "--file", "-", payload=brief, expect=2)
        self.assertIn("revalidate T02", output)
        self.cli("check", "unit")
        self.reviewer(purpose="final", aid="A2")
        self.record()
        self.cli("final")

    def test_final_assignment_rejects_unresolved_effect_and_unadopted_drift(self):
        scope = self.scope()
        scope["review"] = "independent"
        self.accept(scope=scope)
        self.cli("start", "T01")
        self.cli("operation", "begin", "--id", "E1", "--kind", "commit", "--task", "T01",
                 "--intent", "Disposable fixture receipt only.", "--authority", "Scripted test; no external effect.")
        brief = dict(role="review", purpose="final", requirements=["R1"],
                     paths=[str(self.app)], question="Review whole change.", done_when="Return evidence.")
        output = self.cli("agent", "reserve", "--id", "A2", "--capacity", "2", "--file", "-", payload=brief, expect=2)
        self.assertIn("recover", output)
        self.cli("operation", "finish", "--id", "E1", "--file", "-", payload=dict(
            status="cancelled", evidence="Fixture created no external effect."))
        self.cli("done", "T01", "--result-file", self.result())
        (self.app / "unexpected.md").write_text("Unadopted edit.\n")
        output = self.cli("agent", "reserve", "--id", "A2", "--capacity", "2", "--file", "-", payload=brief, expect=2)
        self.assertIn("between tasks", output)


if __name__ == "__main__":
    unittest.main()
