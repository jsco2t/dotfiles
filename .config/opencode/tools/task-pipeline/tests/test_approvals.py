"""Fewer approvals, never a weaker one. The human still decides every substantive scope and plan
change, but one answer to a concrete, already-drafted change approves it (no second "please
approve" for the same thing), a scope change mid-run is one question, plumbing a scope amendment
cannot lose (no requirement, non-goal, term, workspace, shipping, or write-authority change)
settles without one, and small fix tasks can go ahead without a question only inside a delegation
the human chose when the scope was agreed."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from harness import Harness, git
from scenarios import Mixed

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

YES_TWO = {"allow": 2, "max_minutes": 15, "answer": "Yes — up to two small fixes, 15 minutes each."}
NO_FIXES = {"allow": 0, "answer": "No, ask me every time."}


def draft(h: Harness) -> dict:
    h.tp("plan", "amend")                                     # starts plan-amend.json as a copy
    return json.loads((h.wf / "plan-amend.json").read_text())


def write(h: Harness, name: str, data: dict) -> None:
    (h.wf / name).write_text(json.dumps(data, indent=2))


class OneAnswerPerAmendmentTest(unittest.TestCase):
    """Draft first, check it, ask once: that answer is the approval. An answer counts only for the
    draft the check rendered — never for one changed after it, or never checked."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def add_faq(self) -> None:
        d = draft(self.h)
        d["tasks"].insert(2, self.h.task("T04", "faq.md", brief="Write the FAQ.", estimate_min=10))
        write(self.h, "plan-amend.json", d)

    def test_the_check_renders_the_question_and_one_answer_applies_it(self) -> None:
        h = self.h
        self.add_faq()
        out = h.tp("plan", "amend").out
        self.assertIn("Ask the human once", out)
        self.assertIn("T04", out)
        self.assertIn("faq.md", out)
        self.assertIn("10 min", out)
        h.tp("plan", "amend", "--answer", "Yes, add the FAQ.")
        self.assertEqual(h.state()["tasks"]["T04"]["status"], "pending")
        self.assertRegex((h.wf / "decisions.md").read_text(), r"plan amend · human: Yes, add the FAQ\.")

    def test_an_answer_for_a_draft_that_changed_after_its_check_is_refused(self) -> None:
        h = self.h
        self.add_faq()
        h.tp("plan", "amend")
        d = json.loads((h.wf / "plan-amend.json").read_text())
        d["tasks"][2]["estimate_min"] = 25
        write(h, "plan-amend.json", d)
        text = h.tp("plan", "amend", "--answer", "Yes", expect=2).text
        self.assertIn("changed since", text)
        self.assertNotIn("T04", (h.wf / "plan.json").read_text())

    def test_an_answer_for_a_draft_never_checked_is_refused(self) -> None:
        h = self.h
        self.add_faq()
        self.assertIn("tp plan amend", h.tp("plan", "amend", "--answer", "Yes", expect=2).text)


class ScopeAmendTest(unittest.TestCase):
    """A scope change mid-run is one question: the manager drafts it, tp checks it (with the plan
    amendment it needs, if any), and the human's one answer applies both. The run keeps going."""

    def setUp(self) -> None:
        self.m = Mixed()
        m = self.m
        self.docs2 = m.h.root / "docs2"
        self.docs2.mkdir()
        m.approve([m.doc_task("T01")], m.scope(["docs"], ["docs", "doc-review"]))
        m.doc_done("T01", cite="calc.py:1-2")

    def tearDown(self) -> None:
        self.m.close()

    def scope_draft(self) -> dict:
        self.m.h.tp("scope", "amend")
        return json.loads((self.m.h.wf / "scope-amend.json").read_text())

    def test_adding_a_workspace_is_one_answer_and_execution_continues(self) -> None:
        h = self.m.h
        d = self.scope_draft()
        d["workspaces"].append({"name": "docs2", "path": str(self.docs2), "mode": "read"})
        d["non_goals"] = d["non_goals"] + ["No changes to calc's public API"]
        write(h, "scope-amend.json", d)
        out = h.tp("scope", "amend").out
        self.assertIn("Ask the human once", out)
        self.assertIn("docs2", out)
        self.assertIn("+ non_goals: No changes to calc's public API", out)    # the change, not the whole list
        self.assertNotIn("No changes to the calc repository", out)
        h.tp("scope", "amend", "--answer", "Yes, read docs2 too.")
        state = h.state()
        self.assertEqual(state["phase"], "EXECUTING")
        self.assertEqual(state["tasks"]["T01"]["status"], "accepted")
        self.assertIn("docs2", [w["name"] for w in h.read_json("scope.json")["workspaces"]])
        self.assertIn("docs2", state["readonly_baseline"])
        self.assertRegex((h.wf / "decisions.md").read_text(), r"scope amend · human: Yes, read docs2 too\.")
        self.assertFalse((h.wf / "scope-amend.json").exists())
        h.tp("next")                                             # the frozen scope matches: no tamper error

    def test_raising_a_limit_and_ignoring_a_path_mid_run_is_one_answer(self) -> None:
        # A run that outgrows a limit, or meets a new tool artefact, changes only `limits` or
        # `ignore`: the amendment must see that as a change and apply it.
        h = self.m.h
        d = self.scope_draft()
        d["limits"] = {"max_tasks": 62}
        d["ignore"] = ["e2e-out/**"]
        write(h, "scope-amend.json", d)
        out = h.tp("scope", "amend").out
        self.assertIn("Ask the human once", out)
        self.assertIn("limits", out)
        self.assertIn("ignore", out)
        h.tp("scope", "amend", "--answer", "Raise the cap and ignore the e2e output.")
        scope = h.read_json("scope.json")
        self.assertEqual(scope["limits"], {"max_tasks": 62})
        self.assertEqual(scope["ignore"], ["e2e-out/**"])
        h.tp("next")                                             # the frozen scope matches: no tamper error

    def test_a_new_deliverable_and_its_task_are_approved_by_the_same_answer(self) -> None:
        m, h = self.m, self.m.h
        d = self.scope_draft()
        d["deliverables"].append({"id": "D3", "kind": "docs", "what": "A FAQ for calc", "where": "app"})
        write(h, "scope-amend.json", d)
        self.assertIn("D3 is served by no task", h.tp("scope", "amend", expect=2).text)
        p = draft(h)
        p["tasks"].append(m.doc_task("T02", path="docs/faq.md", serves=["D3"]))
        p["review_batches"] = [{"id": "B1", "tasks": ["T01"]}, {"id": "B2", "tasks": ["T02"]}]
        write(h, "plan-amend.json", p)
        h.tp("plan", "amend")                                    # checked against the draft scope
        self.assertIn("apply both", h.tp("plan", "amend", "--answer", "ok", expect=2).text)
        out = h.tp("scope", "amend").out
        self.assertIn("D3", out)
        self.assertIn("T02", out)
        h.tp("scope", "amend", "--answer", "Yes, add the FAQ and its task.")
        self.assertEqual(h.state()["tasks"]["T02"]["status"], "pending")
        self.assertIn("D3", h.read_json("scope.json")["deliverables"][-1]["id"])
        self.assertFalse((h.wf / "plan-amend.json").exists())

    def test_an_answer_for_a_scope_draft_changed_after_its_check_is_refused(self) -> None:
        h = self.m.h
        d = self.scope_draft()
        d["workspaces"].append({"name": "docs2", "path": str(self.docs2), "mode": "read"})
        write(h, "scope-amend.json", d)
        h.tp("scope", "amend")
        d["non_goals"] = []
        write(h, "scope-amend.json", d)
        self.assertIn("changed since", h.tp("scope", "amend", "--answer", "Yes", expect=2).text)


class DelegatedScopeAmendTest(unittest.TestCase):
    """Plumbing costs no question: when the check proves the amendment changes nothing the human
    agreed to — no requirement, non-goal, term, workspace, shipping decision, or write authority —
    the manager settles it with --delegated --note, recorded as theirs and listed in the report.
    A substantive change still costs exactly one question, and --delegated is refused with the
    reason. (The two shapes real runs hit: a routing fix — a liaison transports, a document author
    drafts — and a detail in-budget research discovered.)"""

    def setUp(self) -> None:
        self.m = Mixed()
        m = self.m
        DRAFT = "wf:drafts/kub-1-comment.md"
        self.scope = m.scope(["docs", "integration"], ["docs", "liaison"], review="none")
        self.tasks = [m.doc_task("T01", path=DRAFT, brief="Write the KUB-1 comment text, citing calc.py."),
                     {"id": "T02", "title": "Post the KUB-1 comment", "serves": ["D3"], "requirements": ["R3"],
                      "workspace": "app", "publish": {"to": "jira-comment", "target": "KUB-1", "body": DRAFT},
                      "acceptance": ["The comment is posted once and reads back as sent."],
                      "estimate_min": 5, "depends_on": ["T01"]}]
        m.approve(self.tasks, self.scope)

    def tearDown(self) -> None:
        self.m.close()

    def scope_draft(self) -> dict:
        self.m.h.tp("scope", "amend")
        return json.loads((self.m.h.wf / "scope-amend.json").read_text())

    def test_a_routing_fix_and_a_discovered_detail_settle_without_a_question(self) -> None:
        m, h = self.m, self.m.h
        d = self.scope_draft()
        for dl in d["deliverables"]:                       # the dependent ticket research named
            if dl["id"] == "D3":
                dl["what"] = ("One comment on KUB-1, drafted as wf:drafts/kub-1-comment.md by doc-author and "
                              "posted by the publish task after the human's OK")
        for p in d["participants"]:                        # the liaison transports; it never drafts
            if p["agent"] == "atlassian-liaison":
                p["role"] = "research"
                p["why"] = "Reads KUB-1 context; the plan's publish task posts the reviewed draft."
        write(h, "scope-amend.json", d)
        out = h.tp("scope", "amend").out
        self.assertIn("settle it yourself", out)
        self.assertNotIn("Ask the human once", out)
        h.tp("scope", "amend", "--delegated", "--note",
             "Routing fix: the liaison transports and doc-author drafts; research named the dependent ticket.")
        scope = h.read_json("scope.json")
        self.assertIn("posted by the publish task", [x["what"] for x in scope["deliverables"] if x["id"] == "D3"][0])
        self.assertEqual(["research"], [p["role"] for p in scope["participants"]
                                         if p["agent"] == "atlassian-liaison"])
        self.assertRegex((h.wf / "decisions.md").read_text(),
                         r"scope amend \(manager-settled plumbing\) · manager: Routing fix")
        self.assertFalse((h.wf / "scope-amend.json").exists())
        h.tp("next")                                             # the frozen scope matches: no tamper error

    def test_planning_phase_plumbing_settles_too(self) -> None:
        # The two real escalations of the KUB-1170 run happened while PLANNING, before any plan
        # existed: the same rule must hold there, where no plan amendment can ride along.
        m = Mixed()
        h = m.h
        try:
            h.confirmed(**m.scope(["docs", "integration"], ["docs", "liaison"], review="none"))
            h.tp("scope", "amend")
            d = json.loads((h.wf / "scope-amend.json").read_text())
            for dl in d["deliverables"]:
                if dl["id"] == "D3":
                    dl["what"] = "One comment on KUB-1, drafted by doc-author and posted by the publish task"
            for p in d["participants"]:
                if p["agent"] == "atlassian-liaison":
                    p["role"] = "research"
                    p["why"] = "Reads KUB-1 context; the publish task posts the reviewed draft."
            write(h, "scope-amend.json", d)
            out = h.tp("scope", "amend").out
            self.assertIn("settle it yourself", out)
            self.assertNotIn("Ask the human once", out)
            h.tp("scope", "amend", "--delegated", "--note",
                 "Routing fix before planning: the liaison transports, doc-author drafts.")
            scope = h.read_json("scope.json")
            self.assertEqual(["research"], [p["role"] for p in scope["participants"]
                                             if p["agent"] == "atlassian-liaison"])
            self.assertEqual(h.state()["phase"], "PLANNING")
        finally:
            m.close()

    def test_a_substantive_change_still_costs_its_one_question(self) -> None:
        h = self.m.h
        d = self.scope_draft()
        d["non_goals"] = ["No changes to calc's public API"]
        write(h, "scope-amend.json", d)
        out = h.tp("scope", "amend").out
        self.assertIn("Ask the human once", out)
        self.assertNotIn("settle it yourself", out)
        text = h.tp("scope", "amend", "--delegated", "--note", "Trust me, it is plumbing.", expect=2).text
        self.assertIn("Not plumbing", text)
        self.assertIn("non-goals", text)
        self.assertNotIn("public API", h.read_json("scope.json").get("non_goals") or [])
        h.tp("scope", "amend", "--answer", "Yes, add the non-goal.")
        self.assertIn("No changes to calc's public API", h.read_json("scope.json")["non_goals"])

    def test_a_delegated_fix_task_rides_along_inside_the_allowance(self) -> None:
        m = Mixed()
        h = m.h
        try:
            scope = m.scope(["docs"], ["docs"], review="none")
            scope["fix_tasks"] = YES_TWO
            m.approve([m.doc_task("T01", path="docs/calc.md")], scope)
            h.tp("scope", "amend")
            d = json.loads((h.wf / "scope-amend.json").read_text())
            d["deliverables"][0]["what"] += " (the note names the ticket it prepares)"
            write(h, "scope-amend.json", d)
            p = draft(h)
            p["tasks"].append(m.doc_task("T03", path="docs/follow-up.md", estimate_min=10, depends_on=["T01"],
                                          brief="Write the follow-up note."))
            write(h, "plan-amend.json", p)
            out = h.tp("scope", "amend").out
            self.assertIn("settle it yourself", out)
            h.tp("scope", "amend", "--delegated", "--note",
                 "Research named the ticket the note prepares for; one 10-minute follow-up rides along.")
            state = h.state()
            self.assertEqual(state["tasks"]["T03"]["status"], "pending")
            self.assertIn("T03", state["delegated"])
            self.assertRegex((h.wf / "decisions.md").read_text(),
                             r"plan amend \(fix-task delegation, 1 of 2\) · manager:")
        finally:
            m.close()

    def test_the_delegation_runs_out(self) -> None:
        m = Mixed()
        h = m.h
        try:
            scope = m.scope(["docs"], ["docs"], review="none")
            scope["limits"] = {"max_delegated_scope_amends": 1}
            m.approve([m.doc_task("T01", path="docs/calc.md")], scope)
            h.tp("scope", "amend")
            d = json.loads((h.wf / "scope-amend.json").read_text())
            d["deliverables"][0]["what"] += " (named)"
            write(h, "scope-amend.json", d)
            h.tp("scope", "amend")
            h.tp("scope", "amend", "--delegated", "--note", "First plumbing fix, within the cap of one.")
            h.tp("scope", "amend")
            d = json.loads((h.wf / "scope-amend.json").read_text())
            d["deliverables"][0]["what"] += " (renamed)"
            write(h, "scope-amend.json", d)
            out = h.tp("scope", "amend").out
            self.assertIn("Ask the human once", out)
            text = h.tp("scope", "amend", "--delegated", "--note", "Second plumbing fix, past the cap.",
                        expect=2).text
            self.assertIn("cap", text)
        finally:
            m.close()

    def test_flag_misuse_is_refused(self) -> None:
        h = self.m.h
        d = self.scope_draft()
        d["deliverables"][1]["what"] += " (renamed)"
        write(h, "scope-amend.json", d)
        h.tp("scope", "amend")
        self.assertIn("not both", h.tp("scope", "amend", "--delegated", "--note", "x y z w",
                                       "--answer", "both at once", expect=2).text)
        self.assertIn("--note", h.tp("scope", "amend", "--delegated", expect=2).text)

    def test_gained_write_authority_and_a_changed_deliverable_set_are_never_plumbing(self) -> None:
        from pipeline import plan as planmod
        base = {"deliverables": [{"id": "D1", "kind": "integration", "what": "One comment", "where": "jira:KUB-1"}],
                "participants": [{"agent": "atlassian-liaison", "role": "research", "why": "Reads tickets for us."}]}
        promoted = json.loads(json.dumps(base))
        promoted["participants"][0]["role"] = "author"           # the liaison would write content
        self.assertIn("write authority", "; ".join(planmod._scope_delegation_misfit(base, promoted)))
        grown = json.loads(json.dumps(base))
        grown["deliverables"].append({"id": "D2", "kind": "docs", "what": "A note", "where": "app"})
        self.assertIn("deliverable set", "; ".join(planmod._scope_delegation_misfit(base, grown)))

    def test_the_report_lists_what_the_manager_settled(self) -> None:
        m = Mixed()
        h = m.h
        try:
            m.approve([m.doc_task("T01", path="docs/calc.md")],
                      m.scope(["docs"], ["docs"], review="none"))
            h.tp("scope", "amend")
            d = json.loads((h.wf / "scope-amend.json").read_text())
            d["deliverables"][0]["what"] += " (the note names the KUB-1 comment it prepares)"
            write(h, "scope-amend.json", d)
            h.tp("scope", "amend")
            h.tp("scope", "amend", "--delegated", "--note",
                 "Routing fix: research named where the note lands; no requirement moved.")
            m.doc_done("T01", cite="calc.py:1-2")
            h.tp("final")
            report = (h.wf / "report.md").read_text()
            self.assertIn("Manager scope amendments", report)
            self.assertIn("Routing fix", report)
        finally:
            m.close()


class LegacyScopeTest(unittest.TestCase):
    """A run confirmed before the fix-task question keeps working: its scope allows no delegated
    fix tasks, and amending or revising it never forces that question on the human mid-run."""

    def setUp(self) -> None:
        self.m = Mixed()
        m = self.m
        m.approve([m.doc_task("T01")], m.scope(["docs"], ["docs", "doc-review"]))
        scope = m.h.read_json("scope.json")
        scope.pop("fix_tasks")
        write(m.h, "scope.json", scope)
        from pipeline.common import sha_file
        state = m.h.state()
        state["scope_sha"] = state["scope_checked_sha"] = sha_file(m.h.wf / "scope.json")
        (m.h.wf / ".tp" / "state.json").write_text(json.dumps(state))
        self.docs2 = m.h.root / "docs2"
        self.docs2.mkdir()

    def tearDown(self) -> None:
        self.m.close()

    def test_a_scope_amendment_of_a_legacy_scope(self) -> None:
        h = self.m.h
        h.tp("scope", "amend")
        d = h.read_json("scope-amend.json")
        d["workspaces"].append({"name": "docs2", "path": str(self.docs2), "mode": "read"})
        write(h, "scope-amend.json", d)
        h.tp("scope", "amend")
        h.tp("scope", "amend", "--answer", "Yes, read docs2.")
        self.assertIn("docs2", [w["name"] for w in h.read_json("scope.json")["workspaces"]])

    def test_a_revision_of_a_legacy_scope(self) -> None:
        h = self.m.h
        h.tp("revise", "--scope", "--feedback", "Read docs2 too.")
        scope = h.read_json("scope.json")
        scope["workspaces"].append({"name": "docs2", "path": str(self.docs2), "mode": "read"})
        write(h, "scope.json", scope)
        h.tp("scope", "check")
        h.tp("scope", "confirm", "--answer", "Confirm")
        self.assertEqual(h.state()["phase"], "EXECUTING")


class AskOnceWhereTheQuestionStartsTest(unittest.TestCase):
    """The double ask started where the first question was asked — a closeout, a blocked task —
    before any amendment existed. There, tp now says to draft and check it first, and carries the
    checked change into that one question, so its answer approves both."""

    def setUp(self) -> None:
        self.h = Harness()
        h = self.h
        h.approved(plan=h.plan([h.task("T01", "architecture/overview.md")], final_checks=[]))
        h.tp("dispatch", "T01")
        h.good_article("architecture/overview.md")
        h.result("T01", "author", changed=["architecture/overview.md"],
                 noticed=["build/guide.md still says Add takes floats; it takes ints."])
        h.tp("record", "T01", "--agent-id", "a-1")
        h.tp("accept", "T01", "--note", "ok")

    def tearDown(self) -> None:
        self.h.close()

    def test_closeout_carries_the_drafted_amendment_into_its_one_question(self) -> None:
        h = self.h
        h.tp("closeout", "--item", "1", "--class", "followup", "--note", "readers of the guide pass floats and fail")
        guide = h.tp("next").out
        self.assertIn("draft", guide.lower())
        d = draft(h)
        d["tasks"].append(h.task("T02", "build/guide.md", brief="Say Add takes ints.", estimate_min=10))
        write(h, "plan-amend.json", d)
        h.tp("plan", "amend")
        ask = h.tp("closeout", "--ask").out
        self.assertIn("T02", ask)
        self.assertIn("same answer", ask)
        answer = "Fix it now: add T02 to correct the guide."
        h.tp("closeout", "--decide", "--answer", answer)
        h.tp("plan", "amend", "--answer", answer)
        self.assertEqual(h.state()["tasks"]["T02"]["status"], "pending")
        decisions = (h.wf / "decisions.md").read_text()
        self.assertEqual(decisions.count(answer), 2)                     # one answer, both gates

    def test_the_amend_check_says_not_to_ask_twice(self) -> None:
        h = self.h
        d = draft(h)
        d["tasks"].append(h.task("T02", "build/guide.md", brief="Say Add takes ints.", estimate_min=10))
        write(h, "plan-amend.json", d)
        out = h.tp("plan", "amend").out
        self.assertIn("already chose this exact change", out)

    def test_a_blocked_task_question_says_to_draft_first(self) -> None:
        h = self.h
        h.tp("exception", "--task", "T01", "--summary", "T01 needs a second article to be complete")
        out = h.tp("next").out
        self.assertIn("draft and check the amendment first", out)


class RevisedScopeKeepsTheApprovedPlanTest(unittest.TestCase):
    """`tp revise --scope` once cost three answers (revise, confirm the scope, re-approve a plan
    that had not changed). Confirming the revised scope now restores an unchanged, still-valid
    approved plan, so the run continues; review keeps diffing against the original baseline."""

    def setUp(self) -> None:
        self.m = Mixed()
        m = self.m
        m.approve([m.code_task("T01"), m.doc_task("T02", depends_on=["T01"])],
                  m.scope(["code", "docs"], ["tests", "code", "docs", "correctness", "doc-review"]))
        self.base = m.h.state()["write_baseline"]["app"]
        m.code_done("T01")
        git(m.app, "add", "-A")
        git(m.app, "commit", "-q", "-m", "T01")

    def tearDown(self) -> None:
        self.m.close()

    def revise(self, change) -> None:
        h = self.m.h
        h.tp("revise", "--scope", "--feedback", "Read docs2 as well; nothing else changes.")
        scope = h.read_json("scope.json")
        change(scope)
        write(h, "scope.json", scope)
        h.tp("scope", "check")
        h.tp("scope", "confirm", "--answer", "Confirm")

    def test_an_unchanged_valid_plan_is_restored_without_a_second_approval(self) -> None:
        h = self.m.h
        docs2 = h.root / "docs2"
        docs2.mkdir()
        self.revise(lambda s: s["workspaces"].append({"name": "docs2", "path": str(docs2), "mode": "read"}))
        state = h.state()
        self.assertEqual(state["phase"], "EXECUTING")
        self.assertEqual(state["tasks"]["T01"]["status"], "accepted")
        self.assertEqual(state["write_baseline"]["app"], self.base)
        self.assertIn("unchanged", (h.wf / "decisions.md").read_text().splitlines()[-1])

    def test_a_plan_the_new_scope_breaks_goes_back_to_planning(self) -> None:
        h = self.m.h
        self.revise(lambda s: s["deliverables"].append(
            {"id": "D3", "kind": "docs", "what": "A FAQ for calc", "where": "app"}))
        self.assertEqual(h.state()["phase"], "PLANNING")

    def test_reapproval_keeps_the_original_review_baseline(self) -> None:
        m, h = self.m, self.m.h
        self.revise(lambda s: s["deliverables"].append(
            {"id": "D3", "kind": "docs", "what": "A FAQ for calc", "where": "app"}))
        plan = h.read_json("plan.json")
        plan["tasks"].append(m.doc_task("T03", path="docs/faq.md", serves=["D3"], depends_on=["T01"]))
        write(h, "plan.json", plan)
        h.tp("plan", "check")
        h.tp("plan", "submit")
        h.plan_review_pass()
        h.tp("approve")
        self.assertEqual(h.state()["write_baseline"]["app"], self.base)
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "accepted")


class FixTaskDelegationTest(unittest.TestCase):
    """At scope time the human is asked whether the manager may add small fix tasks without asking,
    and how many and how big. Inside that answer a fix task needs no question; outside it, it does.
    Every delegated task is recorded as the manager's and listed in the report."""

    def test_scope_check_requires_the_humans_answer_on_fix_tasks(self) -> None:
        h = Harness()
        try:
            h.init()
            scope = h.scope()
            scope.pop("fix_tasks")
            write(h, "scope.json", scope)
            text = h.tp("scope", "check", expect=2).text
            self.assertIn("fix_tasks", text)
            self.assertIn("Ask the human", text)
            write(h, "scope.json", h.scope(fix_tasks={"allow": 2, "max_minutes": 15}))
            self.assertIn("answer", h.tp("scope", "check", expect=2).text)
            write(h, "scope.json", h.scope(fix_tasks=YES_TWO))
            h.tp("scope", "check")
            md = (h.wf / "scope.md").read_text()
            self.assertIn("up to 2 fix tasks", md)
            self.assertIn(YES_TWO["answer"], md)
        finally:
            h.close()

    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def approve(self, fix_tasks=YES_TWO, budget=180) -> None:
        h = self.h
        h.approved(plan=h.plan([h.task("T01", "architecture/overview.md")], final_checks=[]),
                   fix_tasks=fix_tasks, budget_minutes=budget)

    def add(self, *tasks) -> None:
        d = draft(self.h)
        d["tasks"] += list(tasks)
        write(self.h, "plan-amend.json", d)

    def fix(self, tid: str, rel: str, minutes: int = 10) -> dict:
        return self.h.task(tid, rel, brief=f"Clarify the statement in {rel}.", estimate_min=minutes)

    def test_a_small_fix_inside_the_delegation_needs_no_question(self) -> None:
        h = self.h
        self.approve()
        self.add(self.fix("T02", "build/guide.md"))
        out = h.tp("plan", "amend").out
        self.assertIn("standing delegation", out)
        self.assertIn("--delegated", out)
        h.tp("plan", "amend", "--delegated", "--note", "build/guide.md says int where the code takes int64.")
        self.assertEqual(h.state()["tasks"]["T02"]["status"], "pending")
        self.assertEqual(h.state()["delegated"], ["T02"])
        self.assertRegex((h.wf / "decisions.md").read_text(),
                         r"plan amend \(fix-task delegation, 1 of 2\) · manager: build/guide\.md says int")
        h.author("T01", "architecture/overview.md")
        h.tp("accept", "T01", "--note", "ok")
        h.author("T02", "build/guide.md")
        h.tp("accept", "T02", "--note", "ok")
        h.tp("final")
        report = (h.wf / "report.md").read_text()
        self.assertIn("Fix tasks added under your standing delegation", report)
        self.assertIn("T02", report.split("standing delegation")[1])

    def test_more_fix_tasks_than_allowed_go_to_the_human(self) -> None:
        h = self.h
        self.approve(fix_tasks={"allow": 1, "max_minutes": 15, "answer": "One small fix, no more."})
        self.add(self.fix("T02", "a.md"), self.fix("T03", "b.md"))
        out = h.tp("plan", "amend").out
        self.assertIn("not within the standing delegation", out)
        text = h.tp("plan", "amend", "--delegated", "--note", "two small doc fixes are needed", expect=2).text
        self.assertIn("1 fix task", text)

    def test_a_fix_task_larger_than_allowed_goes_to_the_human(self) -> None:
        h = self.h
        self.approve()
        self.add(self.fix("T02", "a.md", minutes=25))
        h.tp("plan", "amend")
        self.assertIn("15 min", h.tp("plan", "amend", "--delegated", "--note", "a bigger doc fix", expect=2).text)

    def test_the_delegation_never_covers_changes_to_approved_work(self) -> None:
        h = self.h
        self.approve()
        d = draft(h)
        d["tasks"][0]["brief"] = "Write the article about something else."
        d["tasks"].append(self.fix("T02", "a.md"))
        write(h, "plan-amend.json", d)
        h.tp("plan", "amend")
        self.assertIn("changed T01", h.tp("plan", "amend", "--delegated", "--note", "tweak T01 too",
                                          expect=2).text)

    def test_no_delegation_means_every_fix_is_asked(self) -> None:
        h = self.h
        self.approve(fix_tasks=NO_FIXES)
        self.add(self.fix("T02", "a.md"))
        h.tp("plan", "amend")
        self.assertIn("ask", h.tp("plan", "amend", "--delegated", "--note", "a small doc fix", expect=2).text)

    def test_the_budget_is_reported_never_a_gate(self) -> None:
        # Time budgets are estimates: running past one is reported, and never changes who approves
        # a fix or pushes anyone to shrink it.
        h = self.h
        self.approve(budget=15)
        self.add(self.fix("T02", "a.md", minutes=15))
        out = h.tp("plan", "amend").out
        self.assertIn("runs past the budget", out)
        h.tp("plan", "amend", "--delegated", "--note", "a.md contradicts what the code does")
        self.assertEqual(h.state()["tasks"]["T02"]["status"], "pending")

    def test_a_fix_too_big_for_the_delegation_is_asked_never_shrunk(self) -> None:
        h = self.h
        self.approve()
        self.add(self.fix("T02", "a.md", minutes=25))
        h.tp("plan", "amend")
        text = h.tp("plan", "amend", "--delegated", "--note", "a bigger doc fix is needed", expect=2).text
        self.assertIn("never shrink", text)

    def test_the_count_spans_amendments(self) -> None:
        h = self.h
        self.approve(fix_tasks={"allow": 1, "max_minutes": 15, "answer": "One small fix, no more."})
        self.add(self.fix("T02", "a.md"))
        h.tp("plan", "amend")
        h.tp("plan", "amend", "--delegated", "--note", "a.md contradicts the code")
        self.add(self.fix("T03", "b.md"))
        h.tp("plan", "amend")
        h.tp("plan", "amend", "--delegated", "--note", "b.md contradicts the code", expect=2)


class EstimatesNeverCompressWorkTest(unittest.TestCase):
    """Time budgets and estimates forecast; a task too big for the cap is split, never squeezed."""

    def test_a_research_estimate_past_the_budget_is_reported_not_refused(self) -> None:
        h = Harness()
        try:
            h.init()
            write(h, "scope.json", h.scope(
                budget_minutes=30, research={"budget_minutes": 160, "why": "calc's layout is unknown to the manager"},
                participants=[{"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."},
                              {"agent": "codebase-researcher", "role": "research", "why": "Maps calc for the split."}]))
            out = h.tp("scope", "check").out
            self.assertIn("WARN", out)
            self.assertIn("never shrink the research to fit", out)
            self.assertNotIn("shrink it", out)
        finally:
            h.close()

    def test_an_oversized_task_is_told_to_split_never_to_lower_its_estimate(self) -> None:
        h = Harness()
        try:
            h.confirmed()
            h.write_json("plan.json", h.plan([h.task("T01", "a.md", estimate_min=45)]))
            text = h.tp("plan", "check", expect=2).text
            self.assertIn("split the task", text)
            self.assertIn("Never lower", text)
        finally:
            h.close()


if __name__ == "__main__":
    unittest.main()
