"""Bugs a real run hit: citations into the write workspace, `wf:` write paths, a conventions file
listed twice, and doc citations that go stale when later fixes move the code they cite."""
from __future__ import annotations

import unittest

from scenarios import Mixed


class DocsCiteTheWriteWorkspaceTest(unittest.TestCase):
    """Docs describe the code the run is changing, which lives in the write workspace. The docs
    check once resolved citations against read workspaces only, so a real run had to add a
    read-only alias of its own worktree (and every brief then called that worktree read-only)."""

    def setUp(self) -> None:
        self.m = Mixed()

    def tearDown(self) -> None:
        self.m.close()

    def test_a_citation_into_the_write_workspace_passes_the_docs_check(self) -> None:
        m = self.m
        m.approve([m.doc_task("T01", sources=["app:calc.py"])],
                  m.scope(["docs"], ["docs", "doc-review"]))
        m.h.tp("dispatch", "T01")
        (m.app / "docs").mkdir()
        (m.app / "docs" / "calc.md").write_text("# add\n\n`add` returns the sum (`calc.py:1-2`).\n")
        m.h.result("T01", "author", changed=["docs/calc.md"])
        out = m.h.tp("record", "T01").out
        self.assertNotIn("Check `docs` failed", out)
        self.assertEqual(m.status("T01"), "needs_check")

    def test_a_read_alias_of_the_write_workspace_is_not_called_read_only(self) -> None:
        m = self.m
        m.approve([m.doc_task("T01")], m.scope(["docs"], ["docs", "doc-review"], extra_workspaces=[
            {"name": "appsrc", "path": str(m.app), "mode": "read"},
            {"name": "src", "path": str(m.h.src), "mode": "read"}]))
        m.h.tp("dispatch", "T01")
        brief = (m.h.run_dir("T01") / "brief-author-0.md").read_text()
        readonly = [ln for ln in brief.splitlines() if ln.startswith("Read-only")][0]
        self.assertIn(str(m.h.src), readonly)
        self.assertNotIn(f"`{m.app}`", readonly)


class WorkflowFolderPathsTest(unittest.TestCase):
    """A task may write a draft into the workflow folder (`wf:<path>`): its brief names that file,
    and writing it counts as work."""

    def setUp(self) -> None:
        self.m = Mixed()
        m = self.m
        self.task = m.doc_task("T01", path="wf:drafts/kub-1-comment.md", checks=["docs"],
                               brief="Draft the KUB-1 comment about mul, citing calc.py.")
        self.scope = m.scope(["docs"], ["docs", "doc-review"])

    def tearDown(self) -> None:
        self.m.close()

    def test_the_brief_names_the_file_in_the_workflow_folder(self) -> None:
        m = self.m
        m.approve([self.task], self.scope)
        m.h.tp("dispatch", "T01")
        brief = (m.h.run_dir("T01") / "brief-author-0.md").read_text()
        self.assertIn(f"`{m.h.wf / 'drafts' / 'kub-1-comment.md'}`", brief)
        self.assertNotIn("wf:drafts", brief.split("## Write only")[1].split("##")[0])

    def test_writing_the_draft_counts_as_work_and_is_docs_checked(self) -> None:
        m = self.m
        m.approve([self.task], self.scope)
        m.h.tp("dispatch", "T01")
        draft = m.h.wf / "drafts" / "kub-1-comment.md"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text("# KUB-1\n\n`add` returns the sum (`calc.py:9`).\n")
        m.h.result("T01", "author", changed=[str(draft)])
        out = m.h.tp("record", "T01").out
        self.assertNotIn("wrote nothing", out)
        self.assertIn("past the end", out)              # the docs check read the draft
        draft.write_text("# KUB-1\n\n`add` returns the sum (`calc.py:1-2`).\n")
        m.h.tp("dispatch", "T01")
        m.h.result("T01", "fix", changed=[str(draft)])
        m.h.tp("record", "T01")
        self.assertEqual(m.status("T01"), "needs_check")

    def test_a_wf_path_that_leaves_the_workflow_folder_is_refused(self) -> None:
        m = self.m
        m.h.confirmed(**self.scope)
        bad = dict(self.task, paths=["wf:../escape.md"])
        m.h.write_json("plan.json", m.plan([bad]))
        self.assertIn("wf:../escape.md", m.h.tp("plan", "check", expect=2).text)


class ConventionsListedOnceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.m = Mixed()

    def tearDown(self) -> None:
        self.m.close()

    def test_a_conventions_file_also_named_as_a_source_appears_once(self) -> None:
        m = self.m
        m.h.confirmed(**m.scope(["docs"], ["docs", "doc-review"]))
        (m.h.wf / "conventions.md").write_text("# Conventions\n\nCite repo-relative paths.\n")
        task = m.doc_task("T01", sources=["wf:conventions.md", "app:calc.py"])
        m.h.write_json("plan.json", m.plan([task], conventions=["wf:conventions.md"]))
        m.h.tp("plan", "check")
        m.h.tp("plan", "submit")
        m.h.tp("approve", "--answer", "approve")
        m.h.tp("dispatch", "T01")
        brief = (m.h.run_dir("T01") / "brief-author-0.md").read_text()
        start = brief.split("## Start from")[1].split("##")[0]
        self.assertEqual(start.count(str(m.h.wf / "conventions.md")), 1)


class StaleCitationsTest(unittest.TestCase):
    """Accepted docs cite code; a later fix that moves that code reopens the doc, instead of the
    stale citation surfacing as a closeout item (or not at all)."""

    def setUp(self) -> None:
        self.m = Mixed()
        m = self.m
        m.approve([m.code_task("T01"), m.doc_task("T02", depends_on=["T01"])],
                  m.scope(["code", "docs"], ["tests", "code", "docs", "correctness", "doc-review"]))
        m.code_done("T01")
        m.doc_done("T02", cite="calc.py:5-6")

    def tearDown(self) -> None:
        self.m.close()

    def refix_code(self, text: str) -> str:
        m = self.m
        m.h.tp("resolve", "--task", "T01", "--action", "reopen", "--answer", "tidy calc.py", "--by", "manager")
        m.h.tp("dispatch", "T01")
        (m.app / "calc.py").write_text(text)
        m.h.result("T01", "fix", changed=["calc.py"])
        return m.h.tp("record", "T01").out

    def test_a_fix_that_breaks_a_citation_reopens_the_doc(self) -> None:
        m = self.m
        out = self.refix_code("def mul(a, b): return a * b\ndef add(a, b): return a + b\n")
        self.assertEqual(m.status("T02"), "needs_fix")
        self.assertIn("T02", out)
        findings = m.h.state()["tasks"]["T02"]["findings"]
        self.assertTrue(any("calc.py" in f and "T01" in f for f in findings), findings)

    def test_a_fix_that_leaves_the_citation_true_leaves_the_doc_alone(self) -> None:
        m = self.m
        self.refix_code("def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return b * a\n")
        self.assertEqual(m.status("T02"), "accepted")

    def test_a_fix_that_moves_the_cited_code_away_reopens_the_doc(self) -> None:
        m = self.m
        padding = "".join(f"def f{i}(a):\n    return a\n\n\n" for i in range(12))
        self.refix_code("def add(a, b):\n    return a + b\n\n\n" + padding + "def mul(a, b):\n    return a * b\n")
        self.assertEqual(m.status("T02"), "needs_fix")


if __name__ == "__main__":
    unittest.main()
