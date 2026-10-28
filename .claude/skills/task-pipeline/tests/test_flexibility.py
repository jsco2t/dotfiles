"""Flexibility a real run (KUB-1131 run 1) needed: the worktree as its own reference copy,
sandbox artefacts that are not edits, sibling red tests that are not a task's failure, human-approved
test changes, per-workflow limits, package-scoped checks, Jira issues as a publish target, and the
small bugs and the state rollback that cost the run time."""
from __future__ import annotations

import json
import os
import shutil
import sys
import unittest
from pathlib import Path

from harness import Harness
from scenarios import CALC_MUL_PY, FakeCli, Mixed, TEST_PY
from test_execute import FINAL_REVIEW, S1, statuses

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pipeline import run as runmod  # noqa: E402
from pipeline import snapshot  # noqa: E402

OTHER_TEST_PY = ("import unittest\nfrom other import thing\n\n\nclass O(unittest.TestCase):\n"
                 "    def test_thing(self):\n        self.assertEqual(thing(), 1)\n")
ALL_TESTS = "python3 -m unittest discover -q -p 'test_*.py'"


class ReadAliasOfTheWorktreeTest(unittest.TestCase):
    """(1) Listing the worktree a second time as a read workspace is how citations resolved; a
    task writing its own paths there is not a change to a read-only workspace."""

    def test_writing_the_write_workspace_through_a_read_alias_is_not_a_readonly_change(self) -> None:
        m = Mixed()
        try:
            m.approve([m.code_task("T01")], m.scope(["code"], ["tests", "code", "correctness"], extra_workspaces=[
                {"name": "appsrc", "path": str(m.app), "mode": "read"}]))
            m.red()
            out = m.green()
            self.assertNotIn("read-only workspace", out)
            self.assertEqual(m.status("T01"), "needs_check")
        finally:
            m.close()


class SandboxArtefactsTest(unittest.TestCase):
    """(2) Sandbox mount points appear in the worktree as device files and placeholder dirs while a
    sandboxed command runs; they are not edits."""

    def test_a_snapshot_skips_files_that_are_not_regular(self) -> None:
        h = Harness()
        try:
            (h.kb / "real.md").write_text("x\n")
            os.mkfifo(h.kb / ".bashrc")
            snap = snapshot.take(h.kb)
            self.assertIn("real.md", snap)
            self.assertNotIn(".bashrc", snap)
        finally:
            h.close()

    def test_scope_ignore_patterns_keep_artefacts_out_of_the_paths_gate(self) -> None:
        m = Mixed()
        try:
            scope = m.scope(["code"], ["tests", "code", "correctness"])
            scope["ignore"] = ["$HOME/**", ".mcp.json"]
            m.approve([m.code_task("T01")], scope)
            m.h.tp("dispatch", "T01")
            (m.app / "test_calc.py").write_text(TEST_PY)
            (m.app / "$HOME").mkdir()
            (m.app / "$HOME" / ".ssh").write_text("")
            (m.app / ".mcp.json").write_text("{}")
            m.h.result("T01", "tests", changed=["test_calc.py"])
            out = m.h.tp("record", "T01", "--agent-id", "ta-1").out
            self.assertNotIn("outside this task's paths", out)
            self.assertEqual(m.status("T01"), "needs_impl")
        finally:
            m.close()

    def test_scope_ignore_must_be_a_list_of_patterns(self) -> None:
        h = Harness()
        try:
            h.init()
            h.write_json("scope.json", h.scope(ignore="*.tmp"))
            self.assertIn("ignore", h.tp("scope", "check", expect=2).text)
        finally:
            h.close()


class SiblingRedTestsTest(unittest.TestCase):
    """(3) Two tasks whose tests share one test run: a check that fails only on the other task's
    still-red tests is not this task's failure. It waits, costs no fix round, and is re-checked
    once the sibling lands."""

    # T02 runs only its own tests unless a test shares the whole run between both tasks.
    T02_CMD = {"test_a_waiting_task_cannot_explain_a_siblings_failure": ALL_TESTS}

    def setUp(self) -> None:
        self.m = m = Mixed()
        t1 = m.code_task("T01", test_cmd=ALL_TESTS)
        t2 = m.code_task("T02", title="other", paths=["other.py", "test_other.py"], sources=["app:calc.py"],
                         brief="Add other.thing().", acceptance=["thing() == 1"],
                         test_cmd=self.T02_CMD.get(self._testMethodName, "python3 -m unittest -q test_other"),
                         tests_paths=["test_other.py"])
        m.approve([t1, t2], m.scope(["code"], ["tests", "code", "correctness"]))

    def tearDown(self) -> None:
        self.m.close()

    def sibling_red(self) -> None:
        h = self.m.h
        h.tp("dispatch", "T02")
        (self.m.app / "test_other.py").write_text(OTHER_TEST_PY)
        h.result("T02", "tests", changed=["test_other.py"])
        h.tp("record", "T02", "--agent-id", "ta-2")

    def test_a_failure_only_in_a_siblings_red_tests_waits_without_a_fix_round(self) -> None:
        m, h = self.m, self.m.h
        h.tp("dispatch", "T01")
        self.sibling_red()
        (m.app / "test_calc.py").write_text(TEST_PY)
        h.result("T01", "tests", changed=["test_calc.py"])
        h.tp("record", "T01", "--agent-id", "ta-1")
        out = m.green("T01")
        self.assertIn("T02", out)
        ts = h.state()["tasks"]["T01"]
        self.assertEqual(ts["status"], "blocked")
        self.assertEqual(ts["blocked"]["kind"], "sibling")
        self.assertEqual(ts["round"], 0)
        self.assertIsNone(h.state().get("idle_since"))  # a sibling wait is not a wait on the human
        self.assertNotIn("recheck", [a["action"] for a in m.actions()])
        h.tp("dispatch", "T02")
        (m.app / "other.py").write_text("def thing():\n    return 1\n")
        h.result("T02", "impl", changed=["other.py"])
        h.tp("record", "T02", "--agent-id", "ca-2")
        self.assertIn({"action": "recheck", "id": "T01"},
                      [{"action": a["action"], "id": a.get("id")} for a in m.actions()])
        out = h.tp("recheck", "T01").out
        self.assertIn("passed", out)
        self.assertEqual(m.status("T01"), "needs_check")
        self.assertEqual(h.state()["tasks"]["T01"]["round"], 0)

    def test_a_failure_in_the_tasks_own_files_is_still_a_fix_round(self) -> None:
        m, h = self.m, self.m.h
        h.tp("dispatch", "T01")
        self.sibling_red()
        (m.app / "test_calc.py").write_text(TEST_PY)
        h.result("T01", "tests", changed=["test_calc.py"])
        h.tp("record", "T01", "--agent-id", "ta-1")
        h.tp("dispatch", "T01")
        (m.app / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a + b\n")
        h.result("T01", "impl", changed=["calc.py"])
        h.tp("record", "T01", "--agent-id", "ca-1")
        self.assertEqual(m.status("T01"), "needs_fix")

    def wait_on_t02(self) -> None:
        m, h = self.m, self.m.h
        h.tp("dispatch", "T01")
        self.sibling_red()
        (m.app / "test_calc.py").write_text(TEST_PY)
        h.result("T01", "tests", changed=["test_calc.py"])
        h.tp("record", "T01", "--agent-id", "ta-1")
        m.green("T01")
        self.assertEqual(m.status("T01"), "blocked")

    def test_a_waiting_task_cannot_explain_a_siblings_failure(self) -> None:
        # T02's implementation breaks T01's tests. T01 is itself waiting, so blaming its tests would
        # leave both tasks waiting on each other with nothing for `tp next` to offer.
        m, h = self.m, self.m.h
        self.wait_on_t02()
        h.tp("dispatch", "T02")
        (m.app / "other.py").write_text("import calc\n\ncalc.mul.__code__ = (lambda a, b: 0).__code__\n\n\n"
                                       "def thing():\n    return 1\n")
        h.result("T02", "impl", changed=["other.py"])
        h.tp("record", "T02", "--agent-id", "ca-2")
        self.assertEqual(m.status("T02"), "needs_fix")
        self.assertEqual(m.status("T01"), "blocked")

    def test_a_recheck_that_fails_in_the_tasks_own_files_opens_a_fix_round(self) -> None:
        m, h = self.m, self.m.h
        self.wait_on_t02()
        (m.app / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a + b\n")
        h.tp("dispatch", "T02")
        (m.app / "other.py").write_text("def thing():\n    return 1\n")
        h.result("T02", "impl", changed=["other.py"])
        h.tp("record", "T02", "--agent-id", "ca-2")
        self.assertNotIn("passed", h.tp("recheck", "T01").out)
        self.assertEqual(m.status("T01"), "needs_fix")
        self.assertEqual(h.state()["tasks"]["T01"]["round"], 1)


class ApprovedTestChangesTest(unittest.TestCase):
    """(4) A test that must change after the test step reaches the test author, or, when the human
    approves a change already made, becomes the new baseline."""

    def setUp(self) -> None:
        self.m = m = Mixed()
        m.approve([m.code_task("T01")], m.scope(["code"], ["tests", "code", "correctness"]))
        m.red()

    def tearDown(self) -> None:
        self.m.close()

    def test_resolve_routes_a_test_change_to_the_test_author(self) -> None:
        m, h = self.m, self.m.h
        h.tp("dispatch", "T01")
        h.result("T01", "impl", status="needs_input", questions=["The test pins the wrong name."])
        h.tp("record", "T01", "--agent-id", "ca-1")
        h.tp("resolve", "--task", "T01", "--action", "tests", "--answer", "The test names mul wrongly; fix it.",
             "--by", "manager")
        act = [a for a in m.actions() if a.get("id") == "T01"][0]
        self.assertEqual((act["action"], act["agent"]), ("fix", "test-author"))
        self.assertEqual(h.state()["tasks"]["T01"]["fixing"], "tests")

    def test_a_human_approved_test_change_becomes_the_baseline(self) -> None:
        m, h = self.m, self.m.h
        h.tp("dispatch", "T01")
        (m.app / "calc.py").write_text(CALC_MUL_PY)
        (m.app / "test_calc.py").write_text(TEST_PY.replace("assertEqual(mul(2, 3), 6)", "assertEqual(6, mul(3, 2))"))
        h.result("T01", "impl", changed=["calc.py", "test_calc.py"])
        self.assertIn("weakened", h.tp("record", "T01", "--agent-id", "ca-1").out)
        h.tp("rebaseline-tests", "T01", "--answer", "Approve the reordered assertion", "--by", "manager", expect=2)
        h.tp("rebaseline-tests", "T01", "--answer", "Approve the reordered assertion", "--by", "human")
        h.tp("dispatch", "T01")
        h.result("T01", "fix", changed=[])
        out = h.tp("record", "T01").out
        self.assertNotIn("weakened", out)
        self.assertEqual(m.status("T01"), "needs_check")
        self.assertIn("Approve the reordered assertion", (h.wf / "decisions.md").read_text())


class WorkflowLimitsTest(unittest.TestCase):
    """(5) The human can raise or lower a limit for one workflow in scope.json."""

    def test_a_scope_limit_overrides_the_catalog(self) -> None:
        h = Harness()
        try:
            h.confirmed(limits={"max_tasks": 2})
            h.write_json("plan.json", h.plan())
            self.assertIn("the limit is 2", h.tp("plan", "check", expect=2).text)
        finally:
            h.close()

    def test_an_unknown_limit_is_refused(self) -> None:
        h = Harness()
        try:
            h.init()
            h.write_json("scope.json", h.scope(limits={"max_taskz": 40}))
            self.assertIn("max_taskz", h.tp("scope", "check", expect=2).text)
        finally:
            h.close()

    def test_scope_md_shows_the_human_what_they_confirm(self) -> None:
        # A raised limit or an ignored path changes what the gates enforce: it belongs in scope.md.
        h = Harness()
        try:
            h.init()
            h.write_json("scope.json", h.scope(limits={"max_tasks": 40}, ignore=["$HOME/**"]))
            h.tp("scope", "check")
            md = (h.wf / "scope.md").read_text()
            self.assertRegex(md, r"max_tasks 40 \(default 30\)")
            self.assertIn("`$HOME/**`", md)
        finally:
            h.close()


class PackageScopedChecksTest(unittest.TestCase):
    """(6) `{dirs}` names the task's package directories, so a per-task check can stay in them."""

    def test_dirs_expands_to_the_task_directories(self) -> None:
        h = Harness()
        try:
            for rel in ("internal/hub/hub.go", "internal/hub/routes.go", "internal/api/x.go"):
                (h.kb / rel).parent.mkdir(parents=True, exist_ok=True)
                (h.kb / rel).write_text("package x\n")
            scope = h.scope()
            task = {"id": "T01", "workspace": "kb", "paths": ["internal/hub/*.go", "internal/api/x.go"]}
            self.assertEqual(runmod._expand_cmd("go vet {dirs}", task, scope), "go vet ./internal/api ./internal/hub")
        finally:
            h.close()

    def test_dirs_leaves_out_a_directory_the_task_deleted(self) -> None:
        # `go vet ./internal/gone` fails on a missing directory: deleting a package is not a vet failure.
        h = Harness()
        try:
            (h.kb / "internal/hub").mkdir(parents=True)
            (h.kb / "internal/hub/hub.go").write_text("package hub\n")
            task = {"id": "T01", "workspace": "kb", "paths": ["internal/hub/hub.go", "internal/gone/old.go"]}
            self.assertEqual(runmod._expand_cmd("go vet {dirs}", task, h.scope()), "go vet ./internal/hub")
        finally:
            h.close()


class JiraIssuePublishTest(unittest.TestCase):
    """(7) A follow-up ticket is a publish task too: drafted, reviewed, dry-run, approved, created
    once and read back. (8) The report renders publish tasks."""

    def setUp(self) -> None:
        self.m = m = Mixed()
        self.jira = FakeCli(m.h.root)
        self.draft = "wf:drafts/followup.md"
        scope = m.scope(["docs", "integration"], ["docs"], review="none")
        tasks = [m.doc_task("T01", path=self.draft, brief="Draft the follow-up ticket."),
                 {"id": "T02", "title": "File the follow-up", "serves": ["D3"], "workspace": "app",
                  "publish": {"to": "jira-issue", "target": "KUB-1", "project": "KUB", "type": "Task",
                              "labels": ["product:stratum-pro"], "body": self.draft},
                  "acceptance": ["The issue exists and reads back."], "estimate_min": 5, "depends_on": ["T01"]}]
        m.approve(tasks, scope)

    def tearDown(self) -> None:
        self.jira.restore()
        self.m.close()

    def test_a_jira_issue_is_created_once_under_its_parent(self) -> None:
        m, h = self.m, self.m.h
        h.tp("dispatch", "T01")
        draft = h.wf / "drafts" / "followup.md"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text("Harden member reads\n\nThe probe follows redirects (`calc.py:1`).\n")
        h.result("T01", "author", changed=[str(draft)])
        h.tp("record", "T01", "--agent-id", "da-1")
        h.tp("accept", "T01", "--note", "ok")
        out = h.tp("publish", "T02").out
        self.assertIn("create", out)
        self.assertEqual(self.jira.writes(), [])
        out = h.tp("publish", "T02", "--answer", "Create it").out
        created = [c for c in self.jira.calls() if c["args"][:2] == ["issue", "create"]]
        self.assertEqual(len(created), 1)
        args = created[0]["args"]
        for flag, value in (("--project", "KUB"), ("--type", "Task"), ("--parent", "KUB-1"),
                            ("--summary", "Harden member reads"), ("--label", "product:stratum-pro")):
            self.assertEqual(args[args.index(flag) + 1], value)
        self.assertIn("KUB-900", out)
        self.assertEqual(m.status("T02"), "accepted")
        h.tp("final")
        self.assertTrue((h.wf / "report.md").exists())


class WidenOntoFinishedTaskTest(unittest.TestCase):
    """(8) A file owned by a finished task may join another task's write set: the widen orders the
    two tasks instead of refusing."""

    def test_widen_onto_a_finished_tasks_file_adds_the_dependency(self) -> None:
        m = Mixed()
        try:
            t2 = m.code_task("T02", title="other", paths=["other.py", "test_other.py"], tests_paths=["test_other.py"],
                             test_cmd="python3 -m unittest -q test_other")
            m.approve([m.code_task("T01"), t2], m.scope(["code"], ["tests", "code", "correctness"]))
            m.code_done("T01")
            m.h.tp("widen", "T02", "--path", "calc.py", "--reason", "other() reuses add")
            t2 = [t for t in m.h.read_json("plan.json")["tasks"] if t["id"] == "T02"][0]
            self.assertIn("calc.py", t2["paths"])
            self.assertIn("T01", t2["depends_on"])
        finally:
            m.close()


class TriageReasonsTest(unittest.TestCase):
    """(8) Several findings dismissed in one triage, each with its own reason."""

    def test_each_dismissed_finding_keeps_its_own_reason(self) -> None:
        h = Harness()
        try:
            plan = h.plan(review_batches=[{"id": "B1", "tasks": ["T01", "T02"]}, {"id": "B2", "tasks": ["T03"]}])
            h.approved(plan=plan, **FINAL_REVIEW)
            for tid, rel in (("T01", "architecture/overview.md"), ("T02", "build/guide.md")):
                h.author(tid, rel, agent_id=f"author-{tid}")
                h.tp("accept", tid, "--note", "ok")
            h.tp("dispatch", "T03")
            (h.kb / "index.md").write_text("# KB\n\n- [O](architecture/overview.md)\n- [B](build/guide.md)\n")
            h.result("T03", "author", changed=["index.md"])
            h.tp("record", "T03", "--agent-id", "author-T03")
            h.tp("accept", "T03", "--note", "ok")
            h.tp("dispatch", S1)
            d = h.wf / "runs" / "B1"
            findings = [{"id": f, "state": "wrong", "blocking": True, "where": w, "issue": f"{f} wrong", "fix": "x"}
                        for f, w in (("F1", "build/guide.md:3"), ("F2", "architecture/overview.md:1"))]
            (d / "doc-reviewer-1.json").write_text(json.dumps({"batch": "B1", "verdict": "changes",
                                                               "findings": findings}))
            h.tp("record", S1)
            h.tp("triage", S1, "--dismiss", "F1", "--reason", "first reason", "--dismiss", "F2", "--reason",
                 "second reason")
            self.assertEqual(statuses(h)["T01"], "accepted")
            self.assertEqual(statuses(h)["T02"], "accepted")
            dismissed = h.state()["reviews"][S1]["dismissed"]
            self.assertEqual(dismissed, {"F1": "first reason", "F2": "second reason"})
        finally:
            h.close()


class StateRollbackTest(unittest.TestCase):
    """(9) A workflow folder copied back over itself rolls state back silently; tp refuses it."""

    def test_an_older_state_file_is_refused(self) -> None:
        h = Harness()
        try:
            h.approved()
            old = h.root / "state-old.json"
            shutil.copy(h.wf / ".tp" / "state.json", old)
            h.tp("dispatch", "T01")
            shutil.copy(old, h.wf / ".tp" / "state.json")
            self.assertIn("rolled back", h.tp("next", expect=2).text)
        finally:
            h.close()

    def test_a_deleted_workflow_recreated_at_the_same_path_starts_clean(self) -> None:
        h = Harness()
        try:
            h.approved()
            first = h.wf
            shutil.rmtree(first)
            h.init()
            self.assertEqual(h.wf, first)                    # same date and title: the same folder
            h.tp("status")
        finally:
            h.close()


if __name__ == "__main__":
    unittest.main()
