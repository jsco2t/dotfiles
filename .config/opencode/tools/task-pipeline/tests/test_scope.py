"""Scoping: a minimal, human-confirmed set of participants, and a scope that freezes once
the human confirms it."""
from __future__ import annotations

import unittest
from datetime import date

from harness import Harness


class RosterSuggestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def test_kb_suggestion_is_one_author_and_one_optional_reviewer(self) -> None:
        out = self.h.tp("roster", "suggest", "--kinds", "kb", wf=False).out
        self.assertIn("kb: author    kb-author", out)
        self.assertIn("doc-reviewer", out)
        self.assertIn("only with a research budget", out)
        for absent in ("architecture-reviewer", "code-reviewer", "security-reviewer", "project-manager",
                       "test-planner"):
            self.assertNotIn(absent, out)

    def test_code_suggestion_is_test_forward(self) -> None:
        out = self.h.tp("roster", "suggest", "--kinds", "code", wf=False).out
        self.assertIn("test-author", out)
        self.assertIn("code-author", out)


class InitTest(unittest.TestCase):
    """The location the human names is a parent: the workflow always creates, and owns, its
    own `<date>-<slug>` folder beneath it."""

    def setUp(self) -> None:
        self.h = Harness()
        self.loc = self.h.root / "planning"

    def tearDown(self) -> None:
        self.h.close()

    def init(self, title: str, *extra: str, expect: int = 0, loc=None):
        return self.h.tp("init", str(loc or self.loc), "--title", title, "--request-file", str(self.h.request),
                         *extra, expect=expect, wf=False)

    def test_init_creates_a_dated_slugged_folder_it_owns(self) -> None:
        out = self.init("Stratum KB: v1.0 (draft)!").out
        wf = self.loc.resolve() / f"{date.today().isoformat()}-stratum-kb-v1-0-draft"   # tp reports resolved paths
        self.assertEqual(out.splitlines()[0], f"workflow: {wf}")
        self.assertTrue((wf / ".tp" / "state.json").exists())
        self.assertTrue((wf / "request.md").exists())
        self.assertFalse((self.loc / ".tp").exists())             # the location itself is untouched
        self.assertIn(f"-w {wf}", out)                           # every later command uses the new folder

    def test_the_same_title_on_the_same_day_gets_its_own_folder(self) -> None:
        first = self.init("Calc KB").out.splitlines()[0]
        second = self.init("Calc KB").out.splitlines()[0]
        self.assertNotEqual(first, second)
        self.assertTrue(second.endswith("-calc-kb-2"))

    def test_the_old_w_form_still_creates_the_sub_folder(self) -> None:
        out = self.h.tp("-w", str(self.loc), "init", "--title", "Calc KB", "--request-file", str(self.h.request),
                        wf=False).out
        self.assertIn(f"{date.today().isoformat()}-calc-kb", out.splitlines()[0])
        self.assertFalse((self.loc / ".tp").exists())

    def test_a_missing_location_is_created(self) -> None:
        self.init("Calc KB", loc=self.h.root / "new" / "deeper")
        self.assertEqual(len(list((self.h.root / "new" / "deeper").iterdir())), 1)

    def test_a_workflow_folder_is_not_a_location(self) -> None:
        wf = self.init("Calc KB").out.splitlines()[0].split("workflow: ", 1)[1]
        self.assertIn("workflow", self.init("Another", loc=wf, expect=2).text)

    def test_long_titles_make_short_slugs(self) -> None:
        wf = self.init("A " + "very long title " * 12).out.splitlines()[0]
        self.assertLessEqual(len(wf.rsplit("/", 1)[1]), len("2026-09-29-") + 48)
        self.assertFalse(wf.endswith("-"))


class ScopeCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.init()

    def tearDown(self) -> None:
        self.h.close()

    def check(self, expect: int = 0, **over):
        self.h.write_json("scope.json", self.h.scope(**over))
        return self.h.tp("scope", "check", expect=expect)

    def test_valid_scope_renders_a_short_scope_md(self) -> None:
        self.check()
        md = (self.h.wf / "scope.md").read_text()
        self.assertIn("kb-author", md)
        self.assertIn("D1", md)
        self.assertLess(len(md.encode()), 4000)

    def test_architecture_review_of_documents_is_refused(self) -> None:
        # Regression: the orchestrator planned an architecture review of internal documents.
        res = self.check(expect=2, review="per-task", participants=[
            {"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."},
            {"agent": "architecture-reviewer", "role": "reviewer", "why": "Reviews the KB's structure."},
        ])
        self.assertIn("architecture-reviewer", res.text)
        self.assertIn("kb", res.text)

    def test_orchestrator_only_agents_are_refused(self) -> None:
        res = self.check(expect=2, participants=[
            {"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."},
            {"agent": "project-manager", "role": "reviewer", "why": "Audits each stage transition."},
        ])
        self.assertIn("project-manager", res.text)

    def test_every_participant_needs_a_reason(self) -> None:
        res = self.check(expect=2, participants=[{"agent": "kb-author", "role": "author", "why": ""}])
        self.assertIn("why", res.text)

    def test_participant_cap(self) -> None:
        reviewers = ["code-reviewer", "correctness-reviewer", "security-reviewer", "api-compat-reviewer",
                     "test-reviewer", "architecture-reviewer", "ux-reviewer"]
        many = [{"agent": a, "role": r, "why": "Needed for the code deliverable D1 here."}
                for a, r in [("code-author", "author"), ("test-author", "tests")] + [(x, "reviewer") for x in reviewers]]
        res = self.check(expect=2, review="final", participants=many,
                         deliverables=[{"id": "D1", "kind": "code", "what": "mul()", "where": "kb"}])
        self.assertIn("9 participants", res.text)
        self.assertIn("7 reviewers", res.text)

    def test_specific_reviewers_fit_within_the_caps(self) -> None:
        picks = [("code-author", "author"), ("test-author", "tests"), ("correctness-reviewer", "reviewer"),
                 ("security-reviewer", "reviewer"), ("test-reviewer", "reviewer")]
        self.check(review="final", participants=[{"agent": a, "role": r, "why": "Needed for the D1 code change."}
                                                 for a, r in picks],
                   deliverables=[{"id": "D1", "kind": "code", "what": "mul()", "where": "kb"}])

    def test_every_deliverable_kind_needs_an_author(self) -> None:
        res = self.check(expect=2, review="per-task", participants=[
            {"agent": "doc-reviewer", "role": "reviewer", "why": "Checks the accuracy of the articles."}])
        self.assertIn("author", res.text)

    def test_a_reviewer_the_review_mode_never_uses_is_refused(self) -> None:
        res = self.check(expect=2, review="none", participants=[
            {"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."},
            {"agent": "doc-reviewer", "role": "reviewer", "why": "Checks the accuracy of the articles."},
        ])
        self.assertIn("review", res.text)

    def test_a_review_mode_without_a_reviewer_is_refused(self) -> None:
        res = self.check(expect=2, review="per-task")
        self.assertIn("reviewer", res.text)

    def test_research_needs_an_agreed_budget_and_a_researcher(self) -> None:
        kb = {"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."}
        liaison = {"agent": "atlassian-liaison", "role": "research", "why": "Reads the epic's child issues for D1."}
        self.assertIn("research budget", self.check(expect=2, participants=[kb, liaison]).text)
        self.assertIn("research participant", self.check(
            expect=2, participants=[kb], research={"budget_minutes": 45, "why": "Epic children are thin."}).text)
        self.check(participants=[kb, liaison], research={"budget_minutes": 45, "why": "Epic children are thin."})
        self.assertIn("Research budget:** 45 agent-min", (self.h.wf / "scope.md").read_text())

    def test_research_budget_must_fit_the_whole_budget(self) -> None:
        kb = {"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."}
        liaison = {"agent": "atlassian-liaison", "role": "research", "why": "Reads the epic's child issues for D1."}
        res = self.check(expect=2, participants=[kb, liaison], budget_minutes=60,
                         research={"budget_minutes": 400, "why": "Everything."})
        self.assertIn("research budget", res.text)

    def test_legacy_recon_role_still_reads_as_research(self) -> None:
        self.check(participants=[{"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."},
                                 {"agent": "codebase-researcher", "role": "recon", "why": "Maps dash/ for D1."}],
                   research={"budget_minutes": 15, "why": "dash/ is opaque to the survey."})

    def test_workspace_paths_must_exist(self) -> None:
        res = self.check(expect=2, workspaces=[{"name": "kb", "path": "/nonexistent/kb", "mode": "write"}])
        self.assertIn("/nonexistent/kb", res.text)


class ScopeConfirmTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.init()

    def tearDown(self) -> None:
        self.h.close()

    def test_confirm_needs_a_checked_scope(self) -> None:
        self.h.tp("scope", "confirm", "--answer", "ok", expect=2)

    def test_confirm_moves_to_planning_and_logs_the_human_answer(self) -> None:
        self.h.write_json("scope.json", self.h.scope())
        self.h.tp("scope", "check")
        self.h.tp("scope", "confirm", "--answer", "Looks right, go.")
        self.assertEqual(self.h.state()["phase"], "PLANNING")
        self.assertIn("Looks right, go.", (self.h.wf / "decisions.md").read_text())

    def test_scope_is_frozen_after_confirmation(self) -> None:
        # Regression: deliverables D2-D5 were added mid-research. After confirmation the
        # scope cannot grow without the human.
        self.h.write_json("scope.json", self.h.scope())
        self.h.tp("scope", "check")
        self.h.tp("scope", "confirm", "--answer", "ok")
        grown = self.h.scope(deliverables=[
            {"id": "D1", "kind": "kb", "what": "A KB", "where": "kb"},
            {"id": "D2", "kind": "kb", "what": "Security finding records", "where": "kb"}])
        self.h.write_json("scope.json", grown)
        self.h.write_json("plan.json", self.h.plan())
        res = self.h.tp("plan", "check", expect=2)
        self.assertIn("scope.json changed after confirmation", res.text)


if __name__ == "__main__":
    unittest.main()


class RoleKindsTest(unittest.TestCase):
    """The catalog's `kinds` is one list per agent; architecture-reviewer reviews code AND authors
    an architecture review of an existing codebase (a research deliverable). `role_kinds` overrides
    `kinds` per role so one agent can hold two; jira-reviewer reviews integration deliverables."""

    def test_architecture_reviewer_authors_a_review_of_an_existing_codebase(self) -> None:
        h = Harness()
        try:
            h.init()
            scope = h.scope()
            scope["deliverables"] = [{"id": "D1", "kind": "research", "what": "an architecture review"}]
            scope["participants"] = [{"agent": "doc-author", "role": "author", "why": "D1 needs an author"},
                                     {"agent": "architecture-reviewer", "role": "author",
                                      "why": "D1 reviews the codebase architecture"}]
            h.write_json("scope.json", scope)
            out = h.tp("scope", "check", expect=0).out
            self.assertNotIn("does not apply", out)
        finally:
            h.close()

    def test_architecture_reviewer_still_never_reviews_documents_or_writes_code(self) -> None:
        h = Harness()
        try:
            h.init()
            scope = h.scope()
            scope["deliverables"] = [{"id": "D1", "kind": "docs", "what": "a guide"}]
            scope["participants"] = [{"agent": "doc-author", "role": "author", "why": "D1 needs an author"},
                                     {"agent": "architecture-reviewer", "role": "reviewer",
                                      "why": "D1 structure needs review"}]
            h.write_json("scope.json", scope)
            out = h.tp("scope", "check", expect=2).text
            self.assertIn("does not apply", out)
        finally:
            h.close()
