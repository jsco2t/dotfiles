"""Exactly what was asked: the confirmed scope, scope proposals the human decides, the
out-of-plan footprint, the research window, and the limits on notes and parallel research."""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from harness import SCOPE_MD, TEMPLATE_RE, Harness

from orchestrator.common import QUALITY_MANDATE, Workflow, path_matches
from orchestrator import plan as planmod

READ = {"file_path": "/tmp/anything"}


def minutes_ago(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def edit_state(h: Harness, **fields) -> None:
    path = h.wf / ".orch" / "state.json"
    state = json.loads(path.read_text())
    state.update(fields)
    path.write_text(json.dumps(state))


class ScopeCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.init(confirm_scope=False)

    def tearDown(self) -> None:
        self.h.close()

    def test_research_waits_for_the_scope_the_human_confirmed(self) -> None:
        h = self.h
        self.assertIn("draft scope.md", h.orch("status"))
        self.assertIn("scope ok", h.add_research_item(expect=2))
        # The orchestrator drafts scope.md; no agent may.
        self.assertIsNone(h.pretool("Write", {"file_path": str(h.wf / "scope.md")}))
        self.assertIn("only the orchestrator", h.pretool("Write", {"file_path": str(h.wf / "scope.md")},
                                                         agent="planning-author"))
        (h.wf / "scope.md").write_text(SCOPE_MD.replace("- [x] Q1: Integers only? — Answer: any numbers.",
                                                        "- [ ] Q1: Integers only?"))
        h.orch("scope", "submit")
        self.assertIn("WAITING FOR THE HUMAN", h.orch("status"))
        h.human("/task-orchestrator scope ok")
        self.assertIn("no answer yet", h.orch("scope", "confirm", expect=2))  # its question is still open
        (h.wf / "scope.md").write_text(SCOPE_MD)
        self.assertIn("changed since", h.orch("scope", "confirm", expect=2))
        h.orch("scope", "submit")
        self.assertIn("human confirms", h.orch("scope", "confirm", expect=2))  # no `scope ok` since this submit
        h.human("/task-orchestrator scope ok")
        h.orch("scope", "confirm")
        self.assertIn("scope confirmed", (h.wf / "decisions.md").read_text())
        item = h.add_research_item()
        self.assertTrue(item.startswith("R"))
        # Changing the confirmed scope needs the human again.
        with open(h.wf / "scope.md", "a") as handle:
            handle.write("- D2: something more\n")
        self.assertIn("changed after the human confirmed", h.orch("status"))

    def test_scope_documents_are_checked(self) -> None:
        h = self.h
        (h.wf / "scope.md").write_text("# Scope\n\n## Significant terms\n- S1: Rust — the language.\n")
        out = h.orch("scope", "submit", expect=2)
        self.assertIn("no `- D1: ...` deliverables", out)
        self.assertIn("Not:", out)
        self.assertIn("Non-goals", out)

    def test_research_items_cite_the_scope(self) -> None:
        h = self.h
        h.confirm_scope()
        self.assertIn("does not have: D9", h.add_research_item(serves="D9", expect=2))
        item = h.add_research_item(serves="D1,S1")
        h.approve_research(item)
        brief = h.orch("brief", "--plan", "research", "--item", item, "--agent", "codebase-researcher")
        for expected in ("Serves: D1, S1", "## Confirmed scope", "S1: calc — the flat Python module",
                         "Not: a new package", "No division", "DO NOT DO MORE"):
            self.assertIn(expected, brief)


class PlanTraceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.init()
        self.h.write_plan()

    def tearDown(self) -> None:
        self.h.close()

    def errors(self):
        return planmod.validate(Workflow(self.h.wf)).errors

    def test_the_valid_plan_traces_to_the_scope(self) -> None:
        self.assertEqual(self.errors(), [])

    def test_requirements_must_serve_the_confirmed_scope(self) -> None:
        plan = self.h.wf / "plan.md"
        plan.write_text(plan.read_text().replace(" — Serves: D1", ""))
        self.assertTrue(any("no `Serves: D#`" in e for e in self.errors()))
        self.assertTrue(any("deliverable D1 is served by no requirement" in e for e in self.errors()))
        plan.write_text(plan.read_text().replace("returning the product.", "returning the product. — Serves: D7"))
        self.assertTrue(any("serves D7" in e for e in self.errors()))

    def test_tasks_that_write_declare_their_footprint(self) -> None:
        self.h.write_plan(expected_paths=[])
        self.assertTrue(any("declare `expected_paths`" in e for e in self.errors()))
        self.h.write_plan(expected_paths=["."])
        self.assertTrue(any("whole workspace" in e for e in self.errors()))


class ProposalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def propose(self, brief_args, agent, blocking: bool, status: str = "complete"):
        proposal = {"what": "also document the build cache", "why": "D1 readers will need it", "blocking": blocking}
        return self.h.agent(brief_args, agent, status=status,
                            mutate=lambda f: f.update(scope_proposals=[proposal]))

    def test_planning_proposals_are_decided_by_the_human_before_approval(self) -> None:
        h = self.h
        h.init()
        item = h.add_research_item()
        h.approve_research(item)
        entry = self.propose(["research", "--item", item], "codebase-researcher", blocking=False)
        self.assertTrue(entry["valid"], entry["errors"])
        pid = f"P{entry['seq']}-1"
        self.assertIn(pid, h.orch("proposal", "list"))
        h.agent(["pm-research"], "project-manager")
        h.agent(["plan"], "planning-author", work=h.write_plan)
        h.agent(["test-plan"], "test-planner")
        h.agent(["plan-review"], "doc-reviewer")
        h.agent(["pm-plan"], "project-manager")
        h.orch("submit")
        self.assertIn(pid, h.orch("status"))
        h.human("/task-orchestrator approve")
        self.assertIn("scope proposals await", h.orch("approve", expect=2))
        self.assertIn("only the human decides", h.orch("proposal", "decide", pid, expect=2))
        h.human(f"/task-orchestrator proposal reject {pid} not needed for this change")
        h.orch("proposal", "decide", pid)
        self.assertIn("rejected", (h.wf / "decisions.md").read_text())
        h.human("/task-orchestrator approve")
        h.orch("approve")
        self.assertEqual(h.state()["phase"], "EXECUTING")

    def test_an_accepted_planning_proposal_needs_the_plan_rewritten(self) -> None:
        h = self.h
        h.init()
        item = h.add_research_item()
        h.approve_research(item)
        h.agent(["research", "--item", item], "codebase-researcher")
        h.agent(["pm-research"], "project-manager")
        h.agent(["plan"], "planning-author", work=h.write_plan)
        entry = self.propose(["test-plan"], "test-planner", blocking=False)
        pid = f"P{entry['seq']}-1"
        h.human(f"/task-orchestrator proposal accept {pid} yes, include it")
        h.orch("proposal", "decide", pid)
        self.assertIn("fold in the accepted proposal", h.orch("status"))
        # The accepted proposal can now be cited.
        self.assertTrue(h.add_research_item(serves=pid).startswith("R"))

    def test_a_blocking_proposal_during_execution_stops_for_the_human(self) -> None:
        h = self.h
        h.plan_to_approval()
        h.agent(["--loop", "1", "pm-loop-entry"], "project-manager")
        h.orch("loop", "open", "1")
        h.orch("task", "start", "T001")
        h.agent(["T001", "readiness"], "task-verifier")
        h.agent(["T001", "pm-start"], "project-manager")
        entry = self.propose(["T001", "work"], "test-author", blocking=True, status="blocked")
        self.assertTrue(entry["valid"], entry["errors"])
        pid = f"P{entry['seq']}-1"
        self.assertIn("SCOPE PROPOSAL (blocking)", h.orch("status"))
        self.assertIn("proposal", h.orch("task", "status", "T001"))
        h.orch("needs-human", "--kind", "scope_change", "--summary", "test-author needs a build-cache doc")
        self.assertIn(f"`/task-orchestrator proposal accept|reject {pid} <notes>`", h.orch("status"))
        edit_state(h, research_window_started_at=minutes_ago(500))  # the first round's research long ago
        h.human(f"/task-orchestrator proposal accept {pid} add it to the plan")
        out = h.orch("proposal", "decide", pid)
        self.assertIn("plan revision 2 is open", out)
        state = h.state()
        self.assertEqual((state["phase"], state["plan_revision"]), ("PLANNING", 2))
        # The revision gets a fresh research window.
        self.assertNotIn("research_window_started_at", state)
        item = h.add_research_item(serves=pid)
        h.approve_research(item)
        h.orch("brief", "--plan", "research", "--item", item, "--agent", "codebase-researcher")

    def test_a_rejected_blocking_proposal_returns_to_the_work(self) -> None:
        h = self.h
        h.plan_to_approval()
        h.agent(["--loop", "1", "pm-loop-entry"], "project-manager")
        h.orch("loop", "open", "1")
        h.orch("task", "start", "T001")
        entry = self.propose(["T001", "readiness"], "task-verifier", blocking=True, status="blocked")
        pid = f"P{entry['seq']}-1"
        h.orch("needs-human", "--kind", "scope_change", "--summary", "x")
        h.human(f"/task-orchestrator proposal reject {pid} stay with the plan")
        h.orch("proposal", "decide", pid)
        self.assertEqual(h.state()["phase"], "EXECUTING")

    def test_malformed_proposals_are_invalid(self) -> None:
        h = self.h
        h.init()
        entry = h.agent(["pm-research"], "project-manager",
                        mutate=lambda f: f.update(scope_proposals=[{"what": "x"}]))
        self.assertFalse(entry["valid"])
        self.assertIn("scope_proposals", " ".join(entry["errors"]))


class FootprintTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.plan_to_approval()
        h = self.h
        h.agent(["--loop", "1", "pm-loop-entry"], "project-manager")
        h.orch("loop", "open", "1")
        h.orch("task", "start", "T001")
        h.agent(["T001", "readiness"], "task-verifier")
        h.agent(["T001", "pm-start"], "project-manager")

        def tests_then_red() -> None:
            h.write_test()
            h.orch("evidence", "T001", "red")
        h.agent(["T001", "work"], "test-author", work=tests_then_red)
        h.agent(["T001", "pm-scope"], "project-manager")

    def tearDown(self) -> None:
        self.h.close()

    def implement_with_extra_file(self) -> None:
        self.h.implement()
        (self.h.ws / "helpers.py").write_text("def unused():\n    return 1\n")

    def footprint(self):
        self.h.orch("task", "scan", "T001")
        return next(line for line in self.h.orch("task", "status", "T001").splitlines() if "planned or declared" in line)

    def test_an_undeclared_out_of_plan_file_fails_the_task(self) -> None:
        self.h.agent(["T001", "work"], "code-author", work=self.implement_with_extra_file)
        line = self.footprint()
        self.assertIn("[!]", line)
        self.assertIn("1 file(s) outside expected_paths", line)
        self.assertIn("out_of_plan_undeclared", (self.h.wf / "runs" / "T001" / "a1" / "scan.md").read_text())

    def test_a_declared_out_of_plan_file_goes_to_the_pm_for_a_ruling(self) -> None:
        declaration = [{"paths": "helpers*.py", "reason": "AC1 needs a helper for the product"}]
        self.h.agent(["T001", "work"], "code-author", work=self.implement_with_extra_file,
                     mutate=lambda f: f.update(out_of_plan=declaration))
        self.assertIn("[x]", self.footprint())
        scan = (self.h.wf / "runs" / "T001" / "a1" / "scan.md").read_text()
        self.assertIn("out_of_plan_declared", scan)
        self.assertIn("AC1 needs a helper", scan)
        brief = self.h.orch("brief", "T001", "pm-scope", "--agent", "project-manager")
        self.assertIn("necessary consequence", brief)

    def test_path_patterns(self) -> None:
        self.assertTrue(path_matches("pkg/a/b.go", "pkg/**/*.go"))
        self.assertTrue(path_matches("pkg/b.go", "pkg/**/*.go"))
        self.assertTrue(path_matches("pkg/a/b.go", "pkg"))
        self.assertTrue(path_matches(".github/workflows/ci.yml", ".github/workflows"))
        self.assertFalse(path_matches("pkgx/b.go", "pkg"))
        self.assertFalse(path_matches("cmd/main.go", "pkg/**/*.go"))


class LimitsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.init()
        self.item = self.h.add_research_item()
        self.h.approve_research(self.item)

    def tearDown(self) -> None:
        self.h.close()

    def test_the_mandate_is_two_sided(self) -> None:
        self.assertIn("DO NOT SKIP STEPS", QUALITY_MANDATE)
        self.assertIn("DO NOT DO MORE than was asked", QUALITY_MANDATE)
        self.assertIn("scope proposal", QUALITY_MANDATE)

    def test_notes_are_short_context(self) -> None:
        h = self.h
        long_note = " ".join(["context"] * 151)
        self.assertIn("max 150", h.orch("brief", "--plan", "pm-research", "--agent", "project-manager",
                                        "--note", long_note, expect=2))
        h.orch("brief", "--plan", "pm-research", "--agent", "project-manager", "--note", "pins in decisions.md")

    def test_the_research_window_closes_planning_research(self) -> None:
        h = self.h
        brief = h.orch("brief", "--plan", "research", "--item", self.item, "--agent", "codebase-researcher")
        self.assertIn("research window 0 of 90", h.orch("status"))
        h.budget("Read", READ, "codebase-researcher", "r1")
        edit_state(h, research_window_started_at=minutes_ago(91))
        self.assertIn("RESEARCH WINDOW IS USED", h.budget("Read", READ, "codebase-researcher", "r1"))
        self.assertIn("window is used", h.orch("brief", "--plan", "research", "--item", self.item, "--agent",
                                               "codebase-researcher", expect=2))
        # The agent hands back its interim report under the brief it was dispatched with.
        fields = json.loads(TEMPLATE_RE.findall(brief)[-1])
        interim = Path(fields["report"]).parent / "interim" / Path(fields["report"]).name
        interim.parent.mkdir(parents=True, exist_ok=True)
        interim.write_text("Answered Q1; the window closed.\n")
        fields.update(status="interim", report=str(interim))
        h.hook({"hook_event_name": "SubagentStop", "agent_type": "codebase-researcher", "agent_id": "r1",
                "last_assistant_message": "```orch-result\n" + json.dumps(fields) + "\n```"})
        entry = h.ledger()[-1]
        self.assertTrue(entry["valid"], entry["errors"])
        self.assertEqual(entry["interim_reason"], "window")
        self.assertIn("research_window", h.orch("status"))
        h.orch("needs-human", "--kind", "research_window", "--summary", "one item still open")
        h.human("/task-orchestrator resolve continue 30 finish that one item")
        h.orch("resolve", "--action", "continue")
        self.assertEqual(h.state()["budgets"]["research_window_minutes"], 120)
        self.assertIn("extended the research window", h.orch("agent", "continue", "r1"))
        self.assertIsNone(h.budget("Read", READ, "codebase-researcher", "r1"))

    def test_time_waiting_on_the_human_does_not_use_the_window(self) -> None:
        h = self.h
        h.orch("brief", "--plan", "research", "--item", self.item, "--agent", "codebase-researcher")
        h.budget("Read", READ, "codebase-researcher", "r1")
        (h.wf / "HALT").touch()
        h.hook({"hook_event_name": "Stop", "background_tasks": []})
        self.assertEqual(h.state()["phase"], "HALTED")
        # Research ran for 2 minutes, then the workflow sat halted overnight.
        edit_state(h, research_window_started_at=minutes_ago(600), halted_at=minutes_ago(598))
        h.human("/task-orchestrator resume")
        h.orch("resume")
        self.assertIn("research window 2 of 90", h.orch("status"))
        self.assertNotIn("WINDOW", h.budget("Read", READ, "codebase-researcher", "r1") or "")

    def test_the_parallel_limit_is_counted_when_briefs_are_made(self) -> None:
        h = self.h
        items = [self.item] + [h.add_research_item(title=f"area {n}") for n in range(7)]
        h.approve_research(*items[1:])
        for item in items[:7]:
            h.orch("brief", "--plan", "research", "--item", item, "--agent", "codebase-researcher")
        self.assertIn("already out", h.orch("brief", "--plan", "research", "--item", items[7], "--agent",
                                            "codebase-researcher", expect=2))
        # Re-briefing an item already out (e.g. after an interruption) takes no new slot.
        h.orch("brief", "--plan", "research", "--item", items[0], "--agent", "codebase-researcher")
        h.agent(["research", "--item", items[0]], "codebase-researcher")
        h.orch("brief", "--plan", "research", "--item", items[7], "--agent", "codebase-researcher")

    def test_at_most_seven_research_agents_run_at_once(self) -> None:
        h = self.h
        for n in range(7):
            h.budget("Read", READ, "domain-researcher", f"d{n}")
        brief = h.orch("brief", "--plan", "research", "--item", self.item, "--agent", "codebase-researcher")
        self.assertIn("already running", h.pretool("Agent", {"subagent_type": "codebase-researcher",
                                                             "prompt": brief}))
        h.hook({"hook_event_name": "SubagentStop", "agent_type": "domain-researcher", "agent_id": "d0",
                "last_assistant_message": "no block"})
        self.assertIsNone(h.pretool("Agent", {"subagent_type": "codebase-researcher", "prompt": brief}))

    def test_helper_sub_agents_get_the_scope_line(self) -> None:
        text, _ = self.h.hook({"hook_event_name": "SubagentStart", "agent_type": "general-purpose",
                               "agent_id": "helper1"})
        context = json.loads(text)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("TASK-ORCHESTRATOR SCOPE", context)
        self.assertIn("Answer only the question your parent gave you", context)


if __name__ == "__main__":
    unittest.main()
