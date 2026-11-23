"""Self-correction — the pipeline settles its own mechanics instead of spending the manager's turns,
or the human's attention, repairing itself. Each test is a failure from the KUB-1217 run
(2026-11-22), where 6 of 13 questions to the human were pipeline noise and the manager made
~140 calls working around tp:

- a task answered after a block was charged with sibling work accepted while it waited, and the
  "revert them" fix round it got could not be overridden (a ten-call repair: lost, retry, dispute);
- the plan's sign-off and Jira filing lived in an unscheduled `manager_steps` list, so tp
  dispatched work before its preconditions and document review deadlocked against the sign-off;
- a plan review converging 11 → 2 → 1 findings went to the human at round 3;
- a scope amendment that only wrote the human's own answers into the ledger cost a question;
- hygiene noticed in passing cost a closeout question;
- the manager read tp's source 16 times to learn what an agent or `tp publish` can do."""
from __future__ import annotations

import json
import unittest

from harness import Harness
from scenarios import Mixed
from test_progress import FINAL_REVIEW, finish_index


def finding(fid: str, issue: str = "The build guide never says how to run the tests.") -> dict:
    return {"id": fid, "state": "missing", "requirement": "R1", "issue": issue, "fix": "Add it to T02's criteria."}


class ResumedTaskWindowTest(unittest.TestCase):
    """A task's write fence excuses every sibling that ran while it was out — the whole window from
    its first dispatch, including the time it waited on a question."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def block_t01_then_land_t02(self) -> None:
        h = self.h
        h.tp("dispatch", "T01")
        h.result("T01", "author", status="needs_input", questions=["Which heading style should the overview use?"])
        h.tp("record", "T01", "--agent-id", "a-1")
        h.author("T02", "build/guide.md")                                # runs and lands while T01 waits
        h.tp("accept", "T02", "--note", "citation holds")

    def finish_t01(self) -> str:
        h = self.h
        h.tp("resolve", "--task", "T01", "--action", "answer", "--answer", "Sentence-case headings.", "--by", "manager")
        h.good_article("architecture/overview.md")
        h.result("T01", "author", changed=["architecture/overview.md"])
        return h.tp("record", "T01", "--agent-id", "a-1").out

    def test_work_accepted_while_a_task_waited_on_its_question_is_not_charged_to_it(self) -> None:
        self.block_t01_then_land_t02()
        out = self.finish_t01()
        self.assertNotIn("outside this task's paths", out)
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "needs_check")

    def test_a_file_no_task_owns_is_still_flagged_after_the_wait(self) -> None:
        self.block_t01_then_land_t02()
        (self.h.kb / "scratch.md").write_text("# stray\n")
        self.assertIn("scratch.md", self.finish_t01())


class FalseGateOverrideTest(unittest.TestCase):
    """`tp record` dispatches the fix round a gate finding opens; when the manager proves the finding
    false before sending it, the override must still be reachable."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def test_an_unsent_gate_fix_round_can_be_overridden(self) -> None:
        h = self.h
        h.tp("dispatch", "T01")
        h.good_article("architecture/overview.md")
        (h.kb / "stray.md").write_text("# left by the human\n")
        h.result("T01", "author", changed=["architecture/overview.md"])
        self.assertIn("outside this task's paths", h.tp("record", "T01", "--agent-id", "a-1").out)
        h.tp("dispatch", "T01")                                          # the fix round, printed
        out = h.tp("accept", "T01", "--override", "--note",
                   "stray.md was written by the human during the run, never by the agent.").out
        self.assertIn("accepted T01", out)
        self.assertIn("TaskStop", out)                                   # if the call already went out
        st = h.state()
        self.assertEqual(st["tasks"]["T01"]["status"], "accepted")
        self.assertNotIn("T01", st["in_flight"])

    def test_a_fix_round_a_review_asked_for_is_still_not_overridable(self) -> None:
        h = self.h
        h.author("T01", "architecture/overview.md")
        h.tp("reject", "T01", "--reason", "The overview never names the build tool.")
        h.tp("dispatch", "T01")
        self.assertIn("not failing a gate", h.tp("accept", "T01", "--override", "--note",
                                                 "The overview names it in its second paragraph already.",
                                                 expect=2).text)


class GateTaskTest(unittest.TestCase):
    """A human decision mid-run (a sign-off) is a task the scheduler sees: the review of the work
    before it runs first, the work after it waits, and its answer reaches every later brief."""

    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def gated_plan(self, **over) -> dict:
        h = self.h
        return h.plan([
            h.task("T01", "architecture/overview.md"),
            {"id": "T02", "title": "Sign-off on the overview", "serves": ["D1"], "workspace": "kb",
             "gate": {"ask": "Do you sign off architecture/overview.md before the build guide is written?"},
             "depends_on": ["T01"]},
            h.task("T03", "build/guide.md", depends_on=["T02"]),
        ], **over)

    def review_pass(self, sid: str, n: int = 1) -> None:
        h = self.h
        h.tp("dispatch", sid)
        batch, reviewer = sid.split("/")
        (h.wf / "runs" / batch).mkdir(parents=True, exist_ok=True)
        (h.wf / "runs" / batch / f"{reviewer}-{n}.json").write_text(
            json.dumps({"batch": batch, "verdict": "pass", "findings": []}))
        h.tp("record", sid, "--agent-id", f"rev-{batch}")

    def ids(self, action: str) -> list:
        return [a.get("id") for a in self.h.next()["actions"] if a["action"] == action]

    def test_the_plan_cannot_park_work_where_the_scheduler_cannot_see_it(self) -> None:
        h = self.h
        h.confirmed()
        plan = h.plan()
        plan["manager_steps"] = [{"id": "M1", "what": "Ask the human to sign off, then file the tickets."}]
        h.write_json("plan.json", plan)
        text = h.tp("plan", "check", expect=2).text
        self.assertIn("manager_steps", text)
        self.assertIn("gate", text)

    def test_a_gate_runs_after_its_upstream_review_and_holds_what_follows(self) -> None:
        h = self.h
        h.approved(self.gated_plan(), **FINAL_REVIEW)
        self.assertEqual(self.ids("dispatch"), ["T01"])                    # T03 waits behind the gate
        h.author("T01", "architecture/overview.md")
        h.tp("accept", "T01", "--note", "citation holds")
        self.assertEqual(self.ids("review"), ["B1/doc-reviewer"])          # reviewed before the sign-off
        self.assertEqual(self.ids("gate"), [])
        self.review_pass("B1/doc-reviewer")
        self.assertEqual(self.ids("gate"), ["T02"])
        self.assertEqual(self.ids("dispatch"), [])
        asked = h.tp("gate", "T02").out
        self.assertIn("Do you sign off architecture/overview.md", asked)
        self.assertEqual([a["action"] for a in h.next()["actions"]], ["asked"])   # never re-asked
        h.tp("gate", "T02", "--answer", "Signed off; keep the build guide short.")
        self.assertEqual(h.state()["tasks"]["T02"]["status"], "accepted")
        self.assertEqual(self.ids("dispatch"), ["T03"])
        h.tp("dispatch", "T03")
        self.assertIn("Signed off; keep the build guide short.", (h.run_dir("T03") / "brief-author-0.md").read_text())
        h.good_article("build/guide.md")
        h.result("T03", "author", changed=["build/guide.md"])
        h.tp("record", "T03", "--agent-id", "a-3")
        h.tp("accept", "T03", "--note", "citation holds")
        self.review_pass("B2/doc-reviewer")
        h.tp("final")
        report = (h.wf / "report.md").read_text()
        self.assertIn("Signed off; keep the build guide short.", report)

    def test_asking_for_changes_reopens_the_work_and_keeps_the_gate_closed(self) -> None:
        h = self.h
        h.approved(self.gated_plan(), review="none")
        h.author("T01", "architecture/overview.md")
        h.tp("accept", "T01", "--note", "citation holds")
        h.tp("gate", "T02")
        h.tp("gate", "T02", "--reopen", "T01", "--answer", "Not yet: say which build tool the repo uses.")
        st = h.state()
        self.assertEqual(st["tasks"]["T02"]["status"], "pending")
        self.assertEqual(st["tasks"]["T01"]["status"], "needs_fix")
        self.assertEqual(self.ids("dispatch"), [])
        self.assertEqual(self.ids("fix"), ["T01"])

    def two_gate_plan(self, **over) -> dict:
        h = self.h
        gate = lambda tid, dep, what: {"id": tid, "title": f"Sign-off on {what}", "serves": ["D1"], "workspace": "kb",
                                       "gate": {"ask": f"Do you sign off {what} before the next article is written?"},
                                       "depends_on": [dep]}
        return h.plan([h.task("T01", "architecture/overview.md"), gate("T02", "T01", "the overview"),
                       h.task("T03", "build/guide.md", depends_on=["T02"]), gate("T04", "T03", "the build guide"),
                       h.task("T05", "index.md", depends_on=["T04"], checks=[])], **over)

    def land(self, tid: str, rel: str) -> None:
        h = self.h
        h.tp("dispatch", tid)
        h.good_article(rel)
        h.result(tid, "author", changed=[rel])
        h.tp("record", tid, "--agent-id", f"a-{tid}")
        h.tp("accept", tid, "--note", "citation holds")

    def test_two_gates_in_a_row_each_get_reviewed_work_without_deadlock(self) -> None:
        h = self.h
        h.approved(self.two_gate_plan(), **FINAL_REVIEW)
        batches = {s: v["tasks"] for s, v in h.state()["reviews"].items()}
        self.assertEqual(batches, {"B1/doc-reviewer": ["T01"], "B2/doc-reviewer": ["T03"],
                                   "B3/doc-reviewer": ["T05"]})
        self.land("T01", "architecture/overview.md")
        self.review_pass("B1/doc-reviewer")
        h.tp("gate", "T02", "--answer", "Go ahead.")
        self.land("T03", "build/guide.md")
        self.assertEqual(self.ids("review"), ["B2/doc-reviewer"])          # not waiting on T05, behind T04
        self.review_pass("B2/doc-reviewer")
        self.assertEqual(self.ids("gate"), ["T04"])
        h.tp("gate", "T04", "--answer", "Go ahead with the index.")
        h.tp("dispatch", "T05")
        (h.kb / "index.md").write_text("# KB\n\n- [O](architecture/overview.md)\n- [B](build/guide.md)\n")
        h.result("T05", "author", changed=["index.md"])
        h.tp("record", "T05", "--agent-id", "a-T05")
        h.tp("accept", "T05", "--note", "links hold")
        self.review_pass("B3/doc-reviewer")
        h.tp("final")

    def test_a_batch_may_not_mix_work_behind_different_gates(self) -> None:
        h = self.h
        h.confirmed(**FINAL_REVIEW)
        h.write_json("plan.json", self.two_gate_plan(review_batches=[{"id": "B1", "tasks": ["T01"]},
                                                                      {"id": "B2", "tasks": ["T03", "T05"]}]))
        text = h.tp("plan", "check", expect=2).text
        self.assertIn("B2", text)
        self.assertIn("T04", text)

    def test_the_commands_the_manager_reads_say_when_a_gate_is_ready(self) -> None:
        # The manager learns what is next from accept and advance, then ends its turn: a ready gate
        # that only `tp next` mentions is never asked.
        h = self.h
        h.follow_on = True
        h.approved(self.gated_plan(), **FINAL_REVIEW)
        h.tp("dispatch", "T01")
        h.good_article("architecture/overview.md")
        h.result("T01", "author", changed=["architecture/overview.md"])
        h.tp("record", "T01", "--agent-id", "a-1")
        self.assertIn("B1/doc-reviewer", h.tp("accept", "T01", "--note", "citation holds").out)  # review dispatched
        (h.wf / "runs" / "B1").mkdir(parents=True, exist_ok=True)
        (h.wf / "runs" / "B1" / "doc-reviewer-1.json").write_text(
            json.dumps({"batch": "B1", "verdict": "pass", "findings": []}))
        self.assertIn("tp gate T02", h.tp("advance", "B1/doc-reviewer", "--agent-id", "rev-1").out)
        h.tp("gate", "T02")
        self.assertIn("tp gate T02 --answer", h.tp("next").out)          # a fresh session finds the answer path

    def test_accepting_the_last_upstream_task_announces_the_gate(self) -> None:
        h = self.h
        h.follow_on = True
        h.approved(self.gated_plan(), review="none")
        h.tp("dispatch", "T01")
        h.good_article("architecture/overview.md")
        h.result("T01", "author", changed=["architecture/overview.md"])
        h.tp("record", "T01", "--agent-id", "a-1")
        self.assertIn("tp gate T02", h.tp("accept", "T01", "--note", "citation holds").out)

    def test_commands_that_walk_every_task_survive_a_gate(self) -> None:
        h = self.h
        h.approved(self.gated_plan(), review="none", fix_tasks={"allow": 2, "max_minutes": 15, "answer": "Two."})
        self.land("T01", "architecture/overview.md")
        h.tp("gate", "T02")
        h.tp("digest")
        h.tp("status")
        self.assertIn("gate", h.tp("widen", "T02", "--path", "x.md", "--reason", "the fix needs it", expect=2).text)
        h.tp("widen", "T03", "--path", "build/notes.md", "--reason", "the guide links its notes page")
        d = h.read_json("plan.json")
        d["tasks"].append(h.task("T04", "faq.md", depends_on=["T01"], estimate_min=10))
        h.write_json("plan-amend.json", d)
        h.tp("plan", "amend")
        h.tp("plan", "amend", "--delegated", "--note", "A short FAQ the overview's readers asked for.")
        self.assertEqual(h.state()["tasks"]["T04"]["status"], "pending")

    def test_a_gate_is_asked_never_dispatched(self) -> None:
        h = self.h
        h.approved(self.gated_plan(), review="none")
        h.author("T01", "architecture/overview.md")
        h.tp("accept", "T01", "--note", "citation holds")
        self.assertIn("tp gate T02", h.tp("dispatch", "T02", expect=2).text)

    def test_a_gate_may_not_wait_on_writes_that_run_after_the_final_review(self) -> None:
        # Integration waits for every other task, the gate included: a gate behind it never opens.
        m = Mixed()
        try:
            draft = "wf:drafts/kub-1-comment.md"
            m.h.confirmed(**m.scope(["docs", "integration"], ["docs"], review="none"))
            m.h.write_json("plan.json", m.plan([
                m.doc_task("T01", path=draft, brief="Write the KUB-1 comment text, citing calc.py."),
                {"id": "T02", "title": "Post the KUB-1 comment", "serves": ["D3"], "workspace": "app",
                 "publish": {"to": "jira-comment", "target": "KUB-1", "body": draft},
                 "acceptance": ["The comment is posted once."], "estimate_min": 5, "depends_on": ["T01"]},
                {"id": "T03", "title": "Go-ahead after the post", "serves": ["D2"], "workspace": "app",
                 "gate": {"ask": "Is the posted KUB-1 comment what you wanted before the note is written?"},
                 "depends_on": ["T02"]},
                m.doc_task("T04", path="docs/calc.md", depends_on=["T03"])]))
            text = m.h.tp("plan", "check", expect=2).text
            self.assertIn("T03", text)
            self.assertIn("anytime", text)
        finally:
            m.close()

    def test_a_review_batch_may_not_straddle_a_gate(self) -> None:
        h = self.h
        h.confirmed(**FINAL_REVIEW)
        h.write_json("plan.json", self.gated_plan(review_batches=[{"id": "B1", "tasks": ["T01", "T03"]}]))
        text = h.tp("plan", "check", expect=2).text
        self.assertIn("B1", text)
        self.assertIn("T02", text)


class PlanReviewConvergenceTest(unittest.TestCase):
    """The round cap stops a review that is going nowhere, not one that is converging."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.confirmed()
        self.h.write_json("plan.json", self.h.plan())
        self.h.tp("plan", "check")
        self.h.tp("plan", "submit")

    def tearDown(self) -> None:
        self.h.close()

    def rounds(self, counts, dismiss_last: bool = False) -> None:
        h = self.h
        for i, n in enumerate(counts):
            h.plan_review_pass(verdict="changes", findings=[finding(f"F{k}", f"Gap number {k} in the plan is open.")
                                                            for k in range(1, n + 1)])
            if dismiss_last and i == len(counts) - 1:
                h.tp("plan", "triage", "--dismiss", "F1=The reviewer misread T02, which already covers it.")
            else:
                h.tp("plan", "triage", "--accept-all")
            h.tp("plan", "check")
            h.tp("plan", "submit")

    def test_a_converging_review_continues_without_the_human(self) -> None:
        h = self.h
        self.rounds([3, 2, 1])                                           # the KUB-1217 shape: 11 → 2 → 1
        self.assertEqual(h.next()["actions"][0]["action"], "plan_review")
        h.plan_review_pass()                                             # round 4 runs and passes
        self.assertEqual(h.state()["plan_review"]["round"], 4)
        h.tp("approve")

    def test_a_review_that_stops_shrinking_goes_to_the_human(self) -> None:
        self.rounds([2, 2, 2])
        self.assertEqual(self.h.next()["actions"][0]["action"], "human")
        self.assertIn("not converging", self.h.tp("plan", "review", expect=2).text)

    def test_a_disputed_last_round_goes_to_the_human(self) -> None:
        self.rounds([3, 2, 1], dismiss_last=True)
        self.assertEqual(self.h.next()["actions"][0]["action"], "human")

    def test_the_ceiling_holds_even_while_converging(self) -> None:
        self.rounds([5, 4, 3, 2, 1])
        self.assertEqual(self.h.next()["actions"][0]["action"], "human")
        self.assertIn("5 independent review rounds", self.h.tp("plan", "review", expect=2).text)


class PlumbingScopeAmendTest(unittest.TestCase):
    """A scope amendment that changes nothing the human agreed to — or only writes their own recorded
    answers into the ledger — is the manager's to settle; anything else still costs one question."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.confirmed()                                               # PLANNING, as at 05:01 in the run

    def tearDown(self) -> None:
        self.h.close()

    def draft(self) -> dict:
        self.h.tp("scope", "amend")
        return self.h.read_json("scope-amend.json")

    def write(self, d: dict) -> None:
        (self.h.wf / "scope-amend.json").write_text(json.dumps(d, indent=2))

    def ask_and_answer(self, by: str = "human") -> None:
        h = self.h
        h.tp("ask", "--question", "Should the build guide cover Windows builds too?")
        h.tp("answer", "Q1", "--answer", "Yes, cover Windows builds as well.", "--by", by)

    def windows_requirement(self, source: str) -> dict:
        d = self.draft()
        d["requirements"].append({"id": "R2", "text": "The build guide covers Windows builds", "source": source,
                                  "deliverables": ["D1"]})
        return d

    def test_a_refined_deliverable_is_settled_without_a_question(self) -> None:
        h = self.h
        d = self.draft()
        d["deliverables"][0]["what"] = "A KB covering calc's code and build, one article per area"
        self.write(d)
        out = h.tp("scope", "amend").out
        self.assertIn("settle it yourself", out)
        self.assertNotIn("Ask the human once", out)
        h.tp("scope", "amend", "--delegated", "--note", "Deliverable wording only: one article per area.")
        self.assertIn("one article per area", h.read_json("scope.json")["deliverables"][0]["what"])
        self.assertRegex((h.wf / "decisions.md").read_text(), r"scope amend \(manager-settled plumbing\)")
        self.assertFalse((h.wf / "scope-amend.json").exists())

    def test_an_added_requirement_goes_to_independent_review(self) -> None:
        # The reviewer, not a string match on its source, judges whether it is what the human asked for.
        h = self.h
        self.ask_and_answer()
        self.write(self.windows_requirement("Q1: Yes, cover Windows builds as well."))
        out = h.tp("scope", "amend").out
        self.assertIn("independent review", out)
        self.assertNotIn("Ask the human once", out)
        text = h.tp("scope", "amend", "--delegated", "--note", "Q1 becomes R2.", expect=2).text
        self.assertIn("R2", text)

    def test_rewriting_an_agreed_requirement_goes_to_the_human(self) -> None:
        h = self.h
        d = self.draft()
        d["requirements"][0]["text"] = "A KB for the calc build only"
        self.write(d)
        self.assertIn("Ask the human once", h.tp("scope", "amend").out)
        self.assertIn("goes to the human", h.tp("scope", "amend", "--review", "--note",
                                                "R1 narrowed to the build, which is all that matters.", expect=2).text)

    def test_a_deliverable_changing_kind_or_destination_asks(self) -> None:
        h = self.h
        d = self.draft()
        d["deliverables"][0]["where"] = "jira:KUB-1"
        self.write(d)
        self.assertIn("Ask the human once", h.tp("scope", "amend").out)

    def test_dropping_the_test_author_or_an_unknown_field_asks(self) -> None:
        h = self.h
        d = self.draft()
        d["split_tests"] = False                                         # the separate test author goes
        self.write(d)
        self.assertIn("Ask the human once", h.tp("scope", "amend").out)
        d = self.h.read_json("scope.json")
        d["flavour"] = "something tp has never heard of"
        self.write(d)
        self.assertIn("Ask the human once", h.tp("scope", "amend").out)

    def test_dropping_a_reviewer_asks_and_narrowing_a_role_is_reviewed(self) -> None:
        m = Mixed()
        try:
            scope = m.scope(["code", "docs", "integration"],
                            ["tests", "code", "docs", "liaison", "correctness", "doc-review"], review="final")
            m.h.confirmed(**scope)
            m.h.tp("scope", "amend")
            d = m.h.read_json("scope-amend.json")
            d["participants"] = [p for p in d["participants"] if p["agent"] != "correctness-reviewer"]
            (m.h.wf / "scope-amend.json").write_text(json.dumps(d))
            self.assertIn("Ask the human once", m.h.tp("scope", "amend").out)
            d["participants"] = [p if p["agent"] != "atlassian-liaison" else
                                 dict(p, role="research", why="Reads KUB-1; the publish task posts the draft.")
                                 for p in m.h.read_json("scope.json")["participants"]]
            (m.h.wf / "scope-amend.json").write_text(json.dumps(d))
            self.assertIn("independent review", m.h.tp("scope", "amend").out)   # the routing fix: less authority
        finally:
            m.close()

    def test_dropping_a_non_goal_still_asks(self) -> None:
        h = self.h
        d = self.draft()
        d["non_goals"] = []
        self.write(d)
        self.assertIn("Ask the human once", h.tp("scope", "amend").out)
        text = h.tp("scope", "amend", "--delegated", "--note", "Trust me, it is plumbing.", expect=2).text
        self.assertIn("non-goals", text)

    def test_granting_a_role_goes_to_independent_review(self) -> None:
        # The 05:08 question of the run: the liaison, listed for research, needed to author Jira writes.
        m = Mixed()
        try:
            scope = m.scope(["docs", "integration"], ["docs", "liaison"], review="none")
            scope["participants"][1] = dict(scope["participants"][1], role="research")
            m.h.confirmed(**scope)
            m.h.tp("scope", "amend")
            d = m.h.read_json("scope-amend.json")
            d["participants"][1]["role"] = "author"
            (m.h.wf / "scope-amend.json").write_text(json.dumps(d))
            out = m.h.tp("scope", "amend").out
            self.assertIn("independent review", out)
            self.assertNotIn("Ask the human once", out)
            text = m.h.tp("scope", "amend", "--delegated", "--note", "The liaison files the tickets.", expect=2).text
            self.assertIn("write authority", text)
        finally:
            m.close()


def verdict(h: Harness, n: int, what: str,
            reason: str = "It adds an independent check the request's accuracy needs, and nothing else.") -> None:
    d = h.wf / "runs" / "amend"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"result-review-{n}.json").write_text(json.dumps(
        {"review": "amendment", "round": n, "verdict": what, "reason": reason, "concerns": []}))


class AmendmentReviewTest(unittest.TestCase):
    """A change that strengthens the run — another reviewer, more tests, a task beyond the allowance —
    is judged by an independent reviewer, not the human. Only a change to what is delivered, or the
    removal of an agent or a check, goes to the human."""

    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def add_reviewer(self) -> None:
        h = self.h
        h.confirmed()
        h.tp("scope", "amend")
        d = h.read_json("scope-amend.json")
        d["review"] = "final"
        d["participants"].append({"agent": "doc-reviewer", "role": "reviewer", "why": "Checks the KB against the code."})
        (h.wf / "scope-amend.json").write_text(json.dumps(d))
        self.assertIn("independent review", h.tp("scope", "amend").out)

    def test_an_added_reviewer_is_approved_by_the_reviewer_not_the_human(self) -> None:
        h = self.h
        self.add_reviewer()
        out = h.tp("scope", "amend", "--review", "--note",
                   "The KB cites code paths; an accuracy review catches wrong citations before delivery.").out
        self.assertIn('Agent(subagent_type="plan-reviewer"', out)
        brief = (h.wf / "runs" / "amend" / "brief-review-1.md").read_text()
        self.assertIn("Build a KB for the calc repo.", brief)             # judged against the request
        self.assertIn("doc-reviewer", brief)                              # and the change itself
        verdict(h, 1, "approve")
        out = h.tp("scope", "amend", "--record", "--agent-id", "amend-rev-1").out
        self.assertIn("scope amended", out)
        self.assertIn("doc-reviewer", [p["agent"] for p in h.read_json("scope.json")["participants"]])
        self.assertIn("independent review", (h.wf / "decisions.md").read_text())

    def test_a_rejected_change_is_not_applied(self) -> None:
        h = self.h
        self.add_reviewer()
        h.tp("scope", "amend", "--review", "--note", "An accuracy review would catch wrong citations early.")
        verdict(h, 1, "reject", "The request asks for no review and the KB is two short articles; it adds cost only.")
        out = h.tp("scope", "amend", "--record", "--agent-id", "amend-rev-1").out
        self.assertIn("adds cost only", out)
        self.assertNotIn("doc-reviewer", [p["agent"] for p in h.read_json("scope.json")["participants"]])
        self.assertTrue((h.wf / "scope-amend.json").exists())

    def test_an_escalated_change_goes_to_the_human(self) -> None:
        h = self.h
        self.add_reviewer()
        h.tp("scope", "amend", "--review", "--note", "An accuracy review would catch wrong citations early.")
        verdict(h, 1, "escalate", "Whether the KB is reviewed at all is a delivery choice the requester made.")
        self.assertIn("Ask the human once", h.tp("scope", "amend", "--record", "--agent-id", "amend-rev-1").out)
        self.assertNotIn("doc-reviewer", [p["agent"] for p in h.read_json("scope.json")["participants"]])
        h.tp("scope", "amend", "--answer", "Yes, add the review.")
        self.assertIn("doc-reviewer", [p["agent"] for p in h.read_json("scope.json")["participants"]])

    def test_a_draft_changed_under_review_is_not_applied(self) -> None:
        h = self.h
        self.add_reviewer()
        h.tp("scope", "amend", "--review", "--note", "An accuracy review would catch wrong citations early.")
        d = h.read_json("scope-amend.json")
        d["non_goals"] = []
        (h.wf / "scope-amend.json").write_text(json.dumps(d))
        verdict(h, 1, "approve")
        self.assertIn("changed", h.tp("scope", "amend", "--record", "--agent-id", "amend-rev-1", expect=2).text)
        self.assertNotIn("doc-reviewer", [p["agent"] for p in h.read_json("scope.json")["participants"]])

    def test_more_work_beyond_the_allowance_is_reviewed_not_asked(self) -> None:
        h = self.h
        h.approved()                                                     # fix_tasks: none without asking
        d = h.read_json("plan.json")
        d["tasks"].append(h.task("T04", "build/troubleshooting.md", depends_on=["T02"], estimate_min=10,
                                 brief="Document the build failures the guide's readers hit."))
        h.write_json("plan-amend.json", d)
        out = h.tp("plan", "amend").out
        self.assertIn("independent review", out)
        h.tp("plan", "amend", "--review", "--note", "The guide's own review found readers hit three build failures.")
        verdict(h, 1, "approve")
        h.tp("plan", "amend", "--record", "--agent-id", "amend-rev-1")
        self.assertEqual(h.state()["tasks"]["T04"]["status"], "pending")

    def test_a_reviewer_added_mid_run_reviews_the_work_and_the_run_finishes(self) -> None:
        # The user's own example: during delivery the manager decides the work needs a reviewer.
        h = self.h
        h.approved()                                                     # review: none
        for tid, rel in (("T01", "architecture/overview.md"), ("T02", "build/guide.md")):
            h.author(tid, rel)
            h.tp("accept", tid, "--note", "citation holds")
        h.tp("scope", "amend")
        d = h.read_json("scope-amend.json")
        d["review"] = "final"
        d["participants"].append({"agent": "doc-reviewer", "role": "reviewer", "why": "Checks the KB against the code."})
        (h.wf / "scope-amend.json").write_text(json.dumps(d))
        self.assertIn("independent review", h.tp("scope", "amend").out)
        h.tp("scope", "amend", "--review", "--note", "Both articles cite code lines; nobody has checked a citation.")
        self.assertIn("scope amend --record", h.tp("next").out)          # a fresh session finds the way back
        self.assertIn("amend/review:1", h.tp("status").out)
        verdict(h, 1, "approve")
        out = h.tp("advance", "amend/review:1", "--agent-id", "amend-rev-1").out
        self.assertIn("on the reviewer's approval", out)
        self.assertIn("T03", out)                                        # advance dispatched what is now ready
        (h.kb / "index.md").write_text("# KB\n\n- [O](architecture/overview.md)\n- [B](build/guide.md)\n")
        h.result("T03", "author", changed=["index.md"])
        h.tp("record", "T03", "--agent-id", "a-3")
        h.tp("accept", "T03", "--note", "links hold")
        self.assertEqual([a["id"] for a in h.next()["actions"] if a["action"] == "review"], ["B1/doc-reviewer"])
        h.tp("dispatch", "B1/doc-reviewer")
        (h.wf / "runs" / "B1" / "doc-reviewer-1.json").write_text(
            json.dumps({"batch": "B1", "verdict": "pass", "findings": []}))
        h.tp("record", "B1/doc-reviewer", "--agent-id", "rev-1")
        h.tp("final")
        self.assertIn("Changes an independent reviewer approved", (h.wf / "report.md").read_text())

    def test_a_rejected_draft_cannot_be_sent_to_another_reviewer_unchanged(self) -> None:
        h = self.h
        self.add_reviewer()
        h.tp("scope", "amend", "--review", "--note", "An accuracy review would catch wrong citations early.")
        verdict(h, 1, "reject", "The request asks for no review and the KB is two short articles; it adds cost only.")
        h.tp("scope", "amend", "--record", "--agent-id", "amend-rev-1")
        h.tp("scope", "amend")
        text = h.tp("scope", "amend", "--review", "--note", "Asking again in case another reviewer agrees.",
                    expect=2).text
        self.assertIn("rejected", text)
        d = h.read_json("scope-amend.json")
        d["participants"][-1]["why"] = "Checks the three citations the overview makes against calc.go."
        (h.wf / "scope-amend.json").write_text(json.dumps(d))
        h.tp("scope", "amend")
        h.tp("scope", "amend", "--review", "--note", "Narrowed to the three citations the overview makes.")
        self.assertIn("adds cost only", (h.wf / "runs" / "amend" / "brief-review-2.md").read_text())  # it sees round 1

    def test_removing_agreed_work_or_a_check_goes_to_the_human(self) -> None:
        h = self.h
        h.approved()
        d = h.read_json("plan.json")
        d["tasks"] = [t for t in d["tasks"] if t["id"] != "T02"]
        for t in d["tasks"]:
            t["depends_on"] = [x for x in t.get("depends_on", []) if x != "T02"]
        h.write_json("plan-amend.json", d)
        self.assertIn("Ask the human once", h.tp("plan", "amend").out)
        self.assertIn("goes to the human", h.tp("plan", "amend", "--review", "--note",
                                                "The build guide duplicates the README now.", expect=2).text)
        d = h.read_json("plan.json")
        d["tasks"][0]["acceptance"] = []
        d["tasks"][0]["checks"] = []
        h.write_json("plan-amend.json", d)
        out = h.tp("plan", "amend", expect=None).text
        self.assertNotIn("independent review", out)


class CloseoutTest(unittest.TestCase):
    """Only requested work left undone needs the human at closeout; hygiene noticed in passing goes
    to the report as a suggested follow-up, with no question."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def test_a_follow_up_is_reported_not_asked(self) -> None:
        h = self.h
        h.tp("dispatch", "T01")
        h.good_article("architecture/overview.md")
        h.result("T01", "author", changed=["architecture/overview.md"],
                 noticed=["calc/calc.go:3 says the package is deprecated, which nothing else supports."])
        h.tp("record", "T01", "--agent-id", "a-1")
        h.tp("accept", "T01", "--note", "ok")
        h.author("T02", "build/guide.md")
        h.tp("accept", "T02", "--note", "ok")
        finish_index(h)
        h.tp("closeout", "--items", "1", "--class", "followup", "--note",
             "A stale deprecation comment outside this run; worth a one-line hygiene ticket.")
        self.assertEqual(h.next()["actions"][0]["action"], "final")
        h.tp("final")
        report = (h.wf / "report.md").read_text()
        self.assertIn("Suggested follow-ups", report)
        self.assertIn("stale deprecation comment", report)


class GuidanceTest(unittest.TestCase):
    """What the manager needs to know is printed by tp, never reverse-engineered from its source."""

    def tearDown(self) -> None:
        self.h.close()

    def test_the_capability_map_answers_what_each_agent_and_publish_can_do(self) -> None:
        self.h = Harness()
        out = self.h.tp("roster", "describe", wf=False).out
        self.assertIn("atlassian-liaison", out)
        self.assertRegex(out, r"atlassian-liaison.*research.*author")
        self.assertIn("jira-comment", out)                               # what `tp publish` posts
        self.assertIn("transition", out)                                 # and what it cannot do
        self.assertIn("gate", out)

    def test_a_waiting_review_says_what_it_waits_on(self) -> None:
        # At 06:27 in the run the manager grepped review.py five times to learn why B3 had not started.
        self.h = h = Harness()
        h.approved(h.plan(), **FINAL_REVIEW)
        h.author("T01", "architecture/overview.md")
        h.tp("accept", "T01", "--note", "citation holds")
        self.assertIn("B1/doc-reviewer pending (waits on T02, T03)", h.tp("status").out)

    def test_an_open_question_says_how_to_record_the_answer(self) -> None:
        # A fresh session resuming the run must find the answer path in `tp next` alone.
        self.h = Harness()
        self.h.confirmed()
        self.h.tp("ask", "--question", "Should the build guide cover Windows builds too?")
        out = self.h.tp("next").out
        self.assertIn("Q1", out)
        self.assertIn("tp answer Q1", out)


if __name__ == "__main__":
    unittest.main()
