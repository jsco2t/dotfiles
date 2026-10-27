"""Work goes to the agent built for it. A liaison transports approved content and never writes or
verifies it; external writes happen once, after review; review fixes on tests go to the test
author, behaviour fixes go tests-first; and a task's files match its author's role."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from scenarios import CALC_MUL_PY, TEST_PY, FakeCli, Mixed

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

DRAFT = "wf:drafts/kub-1-comment.md"


class PublishTest(unittest.TestCase):
    """The comment text is a document (doc-author, reviewed like one); posting it is a script
    step the manager runs after the human's OK: no agent drafts, re-verifies, or hand-builds ADF."""

    def setUp(self) -> None:
        self.m = m = Mixed()
        self.jira = FakeCli(m.h.root)
        self.scope = m.scope(["code", "docs", "integration"],
                             ["tests", "code", "docs", "correctness", "doc-review"])
        self.draft_task = m.doc_task("T02", path=DRAFT, depends_on=["T01"],
                                     brief="Write the KUB-1 comment text about mul, citing calc.py.")
        self.publish = {"id": "T03", "title": "Post the KUB-1 comment", "serves": ["D3"], "workspace": "app",
                        "publish": {"to": "jira-comment", "target": "KUB-1", "body": DRAFT},
                        "acceptance": ["The comment is posted once and reads back as sent."],
                        "estimate_min": 5, "depends_on": ["T02"]}

    def tearDown(self) -> None:
        self.jira.restore()
        self.m.close()

    def approve(self, publish=None) -> None:
        self.m.approve([self.m.code_task("T01"), self.draft_task, publish or self.publish], self.scope)

    def write_draft(self, text: str = "") -> None:
        m = self.m
        m.h.tp("dispatch", "T02")
        draft = m.h.wf / "drafts" / "kub-1-comment.md"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text(text or "## Fixed\n\n- `mul` multiplies (`calc.py:5-6`).\n- Tests: **red** then green.\n")
        m.h.result("T02", "author", changed=[str(draft)])
        m.h.tp("record", "T02", "--agent-id", "da-1")
        m.h.tp("accept", "T02", "--note", "citation holds")

    def finish_reviews(self) -> None:
        m = self.m
        for _ in range(6):
            ready = [a["id"] for a in m.actions() if a["action"] == "review"]
            if not ready:
                return
            for sid in ready:
                m.h.tp("dispatch", sid)
                m.review_file(sid, 1, "pass")
                m.h.tp("record", sid)

    def test_publish_waits_for_review_then_dry_runs_then_posts_once(self) -> None:
        m = self.m
        self.approve()
        m.code_done("T01")
        self.write_draft()
        self.assertNotIn("publish", [a["action"] for a in m.actions()])     # review comes first
        self.finish_reviews()
        act = [a for a in m.actions() if a.get("id") == "T03"][0]
        self.assertEqual(act["action"], "publish")
        m.h.tp("dispatch", "T03", expect=2)                                  # no agent posts it
        out = m.h.tp("publish", "T03").out
        self.assertIn("KUB-1", out)
        self.assertIn("sha256", out)
        self.assertEqual(self.jira.writes(), [])                             # a dry run writes nothing
        payload = json.loads((m.h.run_dir("T03") / "payload.json").read_text())
        self.assertEqual(payload["type"], "doc")
        out = m.h.tp("publish", "T03", "--answer", "Post it").out
        writes = self.jira.writes()
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0]["args"][:3], ["issue", "comment", "KUB-1"])
        self.assertIn("--adf", writes[0]["args"])
        self.assertEqual(json.loads(writes[0]["stdin"]), payload)
        self.assertIn("read back", out)
        self.assertEqual(m.status("T03"), "accepted")
        self.assertRegex((m.h.wf / "decisions.md").read_text(), r"publish T03 · human: Post it")
        m.h.tp("publish", "T03", "--answer", "Post it", expect=2)            # once only

    def test_the_draft_must_not_change_between_the_dry_run_and_the_post(self) -> None:
        m = self.m
        self.approve()
        m.code_done("T01")
        self.write_draft()
        self.finish_reviews()
        m.h.tp("publish", "T03")
        (m.h.wf / "drafts" / "kub-1-comment.md").write_text("## Changed after the human saw it\n")
        self.assertIn("dry run", m.h.tp("publish", "T03", "--answer", "Post it", expect=2).text)
        self.assertEqual(self.jira.writes(), [])

    def test_a_new_comment_by_someone_else_stops_the_post(self) -> None:
        m = self.m
        self.approve()
        m.code_done("T01")
        self.write_draft()
        self.finish_reviews()
        m.h.tp("publish", "T03")
        self.jira.seed([{"id": "7", "body": {"type": "doc", "version": 1, "content": []}}])
        self.assertIn("comments", m.h.tp("publish", "T03", "--answer", "Post it", expect=2).text)
        self.assertEqual(self.jira.writes(), [])

    def test_editing_an_existing_comment(self) -> None:
        m = self.m
        self.jira.seed([{"id": "42", "body": {"type": "doc", "version": 1, "content": []}}])
        self.approve(dict(self.publish, publish=dict(self.publish["publish"], comment_id="42")))
        m.code_done("T01")
        self.write_draft()
        self.finish_reviews()
        m.h.tp("publish", "T03")
        m.h.tp("publish", "T03", "--answer", "Edit it in place")
        writes = self.jira.writes()
        self.assertEqual(writes[0]["args"][writes[0]["args"].index("--id") + 1], "42")
        self.assertEqual(len(self.jira.comments()), 1)

    def test_replacing_an_issue_description(self) -> None:
        m = self.m
        self.approve(dict(self.publish, publish={"to": "jira-description", "target": "KUB-1", "body": DRAFT}))
        m.code_done("T01")
        self.write_draft()
        self.finish_reviews()
        m.h.tp("publish", "T03")
        m.h.tp("publish", "T03", "--answer", "Replace the description")
        self.assertEqual(self.jira.description()["type"], "doc")
        self.assertEqual(m.status("T03"), "accepted")

    def test_the_body_must_come_from_a_task_it_depends_on(self) -> None:
        m = self.m
        m.h.confirmed(**self.scope)
        orphan = dict(self.publish, depends_on=["T01"])
        m.h.write_json("plan.json", m.plan([m.code_task("T01"), self.draft_task, orphan]))
        self.assertIn(DRAFT, m.h.tp("plan", "check", expect=2).text)


class LiaisonTransportsOnlyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.m = Mixed()
        self.scope = self.m.scope(["code", "integration"], ["tests", "code", "liaison", "correctness"])

    def tearDown(self) -> None:
        self.m.close()

    def liaison_task(self, **over):
        t = {"id": "T02", "title": "Attach the PDF", "serves": ["D3"], "agent": "atlassian-liaison",
             "workspace": "app", "paths": ["wf:receipts/attach.json"], "sources": ["app:calc.py"],
             "brief": "Attach report.pdf to KUB-1, dry run first, then after the human's OK.",
             "acceptance": ["The attachment is on KUB-1."], "estimate_min": 5, "depends_on": ["T01"]}
        t.update(over)
        return t

    def check(self, task) -> str:
        m = self.m
        m.h.confirmed(**self.scope)
        m.h.write_json("plan.json", m.plan([m.code_task("T01"), task]))
        return m.h.tp("plan", "check", expect=None).text

    def test_a_liaison_asked_to_draft_a_summary_is_refused(self) -> None:
        text = self.check(self.liaison_task(
            brief="Draft one comment for KUB-1 summarizing the fix as executed, then post it after the OK."))
        self.assertIn("ERROR", text)
        self.assertIn("doc-author", text)
        self.assertIn("publish", text)

    def test_a_liaison_owning_repository_files_is_refused(self) -> None:
        text = self.check(self.liaison_task(paths=["notes/kub-1.md"]))
        self.assertIn("ERROR", text)
        self.assertIn("wf:", text)

    def test_a_transport_task_passes(self) -> None:
        self.assertIn("plan ok", self.check(self.liaison_task()))

    def test_creating_an_issue_with_a_summary_is_transport(self) -> None:
        brief = ("Create one Bug under KUB-416 with summary 'Collector drops CSS-only chunks' and the description "
                 "in wf:drafts/bug.md; compose the exact command, dry run first, then create it after the OK.")
        self.assertIn("plan ok", self.check(self.liaison_task(brief=brief)))

    def test_the_liaison_brief_forbids_building_and_testing(self) -> None:
        m = self.m
        m.approve([m.code_task("T01"), self.liaison_task(when="anytime", depends_on=[])], self.scope)
        m.h.tp("dispatch", "T02")
        brief = (m.h.run_dir("T02") / "brief-author-0.md").read_text()
        self.assertIn("transport", brief.lower())
        self.assertIn("never run builds, tests", brief)

    def test_integration_waits_for_review_unless_marked_anytime(self) -> None:
        m = self.m
        m.approve([m.code_task("T01"), self.liaison_task(depends_on=[])], self.scope)
        self.assertNotIn("T02", [a.get("id") for a in m.actions() if a["action"] == "dispatch"])
        m.close()
        self.m = m = Mixed()
        self.scope = m.scope(["code", "integration"], ["tests", "code", "liaison", "correctness"])
        m.approve([m.code_task("T01"), self.liaison_task(depends_on=[], when="anytime")], self.scope)
        self.assertIn("T02", [a.get("id") for a in m.actions() if a["action"] == "dispatch"])


class OlderWorkflowsKeepRunningTest(unittest.TestCase):
    """A workflow approved before integration waited for review kept its liaison task inside a
    review batch; it must not deadlock (the task waiting on the review, the review on the task)."""

    def test_a_liaison_task_in_an_old_review_batch_still_dispatches(self) -> None:
        m = Mixed()
        try:
            scope = m.scope(["code", "integration"], ["tests", "code", "liaison", "correctness"])
            liaison = {"id": "T02", "title": "Attach the PDF", "serves": ["D3"], "agent": "atlassian-liaison",
                       "workspace": "app", "paths": ["wf:receipts/attach.json"], "sources": ["app:calc.py"],
                       "brief": "Attach report.pdf to KUB-1, dry run first.", "acceptance": ["Attached."],
                       "estimate_min": 5, "depends_on": ["T01"]}
            m.approve([m.code_task("T01"), liaison], scope)
            state = m.h.state()
            # The shape such a workflow has on disk: no integration list, sessions without their tasks.
            state.pop("integration", None)
            for sess in state["reviews"].values():
                for key in ("tasks", "code", "lenses"):
                    sess.pop(key, None)
            (m.h.wf / ".tp" / "state.json").write_text(json.dumps(state))
            m.code_done("T01")
            self.assertIn("T02", [a.get("id") for a in m.actions() if a["action"] == "dispatch"])
        finally:
            m.close()


class AmendUnderOldRulesTest(unittest.TestCase):
    """A run approved before the routing rules keeps its frozen tasks as they were: an amendment
    is judged on what it adds, or the manager could never amend that run again."""

    def test_adding_a_task_to_a_plan_approved_under_the_old_rules(self) -> None:
        m = Mixed()
        try:
            scope = m.scope(["code", "docs", "integration"], ["tests", "code", "docs", "liaison", "doc-review",
                                                               "correctness"])
            liaison = {"id": "T03", "title": "KUB-1 comment", "serves": ["D3"], "agent": "atlassian-liaison",
                       "workspace": "app", "paths": ["wf:receipts/kub-1.json"], "sources": ["app:calc.py"],
                       "brief": "Attach report.pdf to KUB-1, dry run first.", "acceptance": ["Posted."],
                       "estimate_min": 10, "depends_on": ["T02"]}
            m.approve([m.code_task("T01"), m.doc_task("T02", depends_on=["T01"]), liaison], scope)
            # Rewrite the approved plan and state into the shape an older run has on disk.
            plan = m.h.read_json("plan.json")
            plan["tasks"][1]["paths"] = ["docs/calc.md", "tools/check.go"]        # docs author owning code
            plan["tasks"][2].update(paths=["notes/kub-1.md"],
                                    brief="Draft one comment for KUB-1 summarizing the fix, then post it.")
            plan["review_batches"] = [{"id": "B1", "tasks": ["T01"]}, {"id": "B2", "tasks": ["T02", "T03"]}]
            m.h.write_json("plan.json", plan)
            from pipeline.common import sha_file
            state = m.h.state()
            state["plan_approved_sha"] = state["plan_submitted_sha"] = sha_file(m.h.wf / "plan.json")
            state.pop("integration", None)
            state["reviews"] = {f"{b}/{r}": {"batch": b, "reviewer": r, "status": "done" if b == "B1" else "pending",
                                             "round": 1 if b == "B1" else 0, "agent_id": None, "findings": [],
                                             "accepted": [], "dismissed": {}, "fix_tasks": [], "extra_rounds": 0}
                                for b in ("B1", "B2") for r in ("correctness-reviewer", "doc-reviewer")}
            (m.h.wf / ".tp" / "state.json").write_text(json.dumps(state))
            m.h.tp("plan", "amend")
            draft = m.h.read_json("plan-amend.json")
            draft["tasks"].append(m.doc_task("T04", path="docs/more.md", depends_on=["T02"]))
            draft["review_batches"].append({"id": "B3", "tasks": ["T04"]})
            m.h.write_json("plan-amend.json", draft)
            m.h.tp("plan", "amend")
            m.h.tp("plan", "amend", "--answer", "Add the extra note")
            reviews = m.h.state()["reviews"]
            self.assertIn("B2/correctness-reviewer", reviews)               # old sessions keep their shape
            self.assertIn("B3/doc-reviewer", reviews)
        finally:
            m.close()


class FixRoutingTest(unittest.TestCase):
    """Review fixes go to the author of what is wrong: test files to the test author; a behaviour
    bug gets a failing test from the test author first, then the code author's fix."""

    def setUp(self) -> None:
        self.m = m = Mixed()
        m.approve([m.code_task("T01")], m.scope(["code"], ["tests", "code", "correctness"]))
        m.code_done("T01")
        self.sid = "B1/correctness-reviewer"
        m.h.tp("dispatch", self.sid)

    def tearDown(self) -> None:
        self.m.close()

    def triage(self, finding) -> None:
        m = self.m
        m.review_file(self.sid, 1, "changes", [finding])
        m.h.tp("record", self.sid, "--agent-id", "rev-1")
        m.h.tp("triage", self.sid, "--accept-all")

    def fix_action(self):
        return [a for a in self.m.actions() if a.get("id") == "T01"][0]

    def test_a_finding_on_a_test_file_goes_to_the_test_author_and_stays_green(self) -> None:
        m = self.m
        self.triage(m.finding("F1", "test_calc.py:6", state="unclear"))
        act = self.fix_action()
        self.assertEqual((act["action"], act["agent"]), ("fix", "test-author"))
        m.h.tp("dispatch", "T01")
        brief = (m.h.run_dir("T01") / "brief-fix-1.md").read_text()
        self.assertIn("must still pass", brief)
        (m.app / "test_calc.py").write_text(TEST_PY.replace("def test_mul", "# mul multiplies.\n    def test_mul"))
        m.h.result("T01", "fix", changed=["test_calc.py"])
        m.h.tp("record", "T01", "--agent-id", "ta-2")
        self.assertEqual(m.status("T01"), "needs_check")

    def test_a_behaviour_bug_goes_tests_first_then_to_the_code_author(self) -> None:
        m = self.m
        self.triage(m.finding("F1", "calc.py:6", state="wrong"))
        act = self.fix_action()
        self.assertEqual(act["agent"], "test-author")
        m.h.tp("dispatch", "T01")
        brief = (m.h.run_dir("T01") / "brief-fix-1.md").read_text()
        self.assertIn("fails on the current code", brief)
        (m.app / "test_calc.py").write_text(TEST_PY + "\n    def test_mul_negative(self):\n"
                                            "        self.assertEqual(mul(-2, 3), -7)\n")
        m.h.result("T01", "fix", changed=["test_calc.py"])
        out = m.h.tp("record", "T01", "--agent-id", "ta-2").out
        self.assertIn("red", out)
        act = self.fix_action()
        self.assertEqual((act["action"], act["agent"]), ("fix", "code-author"))
        self.assertIn("F1", " ".join(m.h.state()["tasks"]["T01"]["findings"]))
        m.h.tp("dispatch", "T01")
        (m.app / "calc.py").write_text(CALC_MUL_PY.replace("return a * b",
                                                           "return a * b if a >= 0 else a * b - 1"))
        m.h.result("T01", "fix", changed=["calc.py"])
        out = m.h.tp("record", "T01", "--agent-id", "ca-2").out
        self.assertIn("green", out)
        self.assertEqual(m.status("T01"), "needs_check")

    def test_a_wording_finding_in_code_goes_straight_to_the_code_author(self) -> None:
        self.triage(self.m.finding("F1", "calc.py:5", state="unclear"))
        self.assertEqual(self.fix_action()["agent"], "code-author")

    def test_the_code_author_may_not_edit_tests_in_a_fix_round(self) -> None:
        m = self.m
        self.triage(m.finding("F1", "calc.py:5", state="unclear"))
        m.h.tp("dispatch", "T01")
        (m.app / "test_calc.py").write_text(TEST_PY + "\n# touched by the code author\n")
        m.h.result("T01", "fix", changed=["test_calc.py"])
        out = m.h.tp("record", "T01", "--agent-id", "ca-2").out
        self.assertIn("test author", out)
        self.assertEqual(m.status("T01"), "needs_fix")


class RoleFitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.m = Mixed()

    def tearDown(self) -> None:
        self.m.close()

    def test_a_doc_author_owning_source_code_is_refused(self) -> None:
        m = self.m
        m.h.confirmed(**m.scope(["docs"], ["docs", "doc-review"]))
        m.h.write_json("plan.json", m.plan([m.doc_task("T01", paths=["README.md", "calc.py"])]))
        text = m.h.tp("plan", "check", expect=2).text
        self.assertIn("calc.py", text)
        self.assertIn("code task", text)

    def test_the_test_step_may_write_only_test_files(self) -> None:
        m = self.m
        m.approve([m.code_task("T01")], m.scope(["code"], ["tests", "code", "correctness"]))
        m.h.tp("dispatch", "T01")
        (m.app / "test_calc.py").write_text(TEST_PY)
        (m.app / "calc.py").write_text(CALC_MUL_PY)          # production code from the test author
        m.h.result("T01", "tests", changed=["test_calc.py", "calc.py"])
        out = m.h.tp("record", "T01").out
        self.assertIn("calc.py", out)
        self.assertEqual(m.status("T01"), "needs_fix")


class ResearchNeverWritesTest(unittest.TestCase):
    """Research reads; a researcher that changed a workspace (built into it, left files) is
    refused at record until the workspace is restored."""

    def test_a_research_item_that_changed_a_workspace_is_refused(self) -> None:
        m = Mixed()
        try:
            scope = m.scope(["code"], ["tests", "code", "correctness"])
            scope["participants"] = scope["participants"] + [
                {"agent": "codebase-researcher", "role": "research", "why": "Maps calc for the plan split."}]
            m.h.confirmed(research={"budget_minutes": 30, "why": "calc's layout is unknown to the manager"}, **scope)
            q = m.h.root / "q.txt"
            q.write_text("Which modules does calc have?\n")
            m.h.tp("research", "add", "R1", "--agent", "codebase-researcher", "--purpose", "map",
                   "--questions-file", str(q), "--done-when", "each module is named")
            m.h.tp("dispatch", "R1")
            (m.app / "scratch.txt").write_text("left behind by the researcher\n")
            (m.h.wf / "recon").mkdir(exist_ok=True)
            (m.h.wf / "recon" / "R1.json").write_text(json.dumps(
                {"answers": [{"q": "Which modules?", "a": "calc only.", "evidence": ["calc.py:1"]}],
                 "followups": [], "unknowns": [], "areas": []}))
            text = m.h.tp("record", "R1", expect=2).text
            self.assertIn("scratch.txt", text)
            (m.app / "scratch.txt").unlink()
            m.h.tp("record", "R1")
        finally:
            m.close()


class OneTaskOneAgentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.m = Mixed()

    def tearDown(self) -> None:
        self.m.close()

    def test_an_agent_of_one_task_cannot_be_recorded_for_another(self) -> None:
        m = self.m
        m.approve([m.doc_task("T01"), m.doc_task("T02", path="docs/other.md")],
                  m.scope(["docs"], ["docs", "doc-review"]))
        m.doc_done("T01", cite="calc.py:1-2", agent_id="da-1")
        m.h.tp("dispatch", "T02")
        m.note("docs/other.md", cite="calc.py:1-2")
        m.h.result("T02", "author", changed=["docs/other.md"])
        text = m.h.tp("record", "T02", "--agent-id", "da-1", expect=2).text
        self.assertIn("T01", text)
        self.assertIn("fresh", text)
        m.h.tp("record", "T02", "--agent-id", "da-2")


if __name__ == "__main__":
    unittest.main()
