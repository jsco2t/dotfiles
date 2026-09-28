"""Keeping agents on track and recoverable: time budgets and interim reports, pausing,
focused research items, resuming in a new session, and the roster agent definitions."""
from __future__ import annotations

import json
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

from harness import ORCH, PY, SCRIPTS, TEMPLATE_RE, Harness

import orch  # scripts/orch.py — the harness puts scripts/ on sys.path
from orchestrator import hooks, ledger
from orchestrator.common import Workflow, interim_path
from orchestrator.roster import AGENTS, REVIEWERS

AGENTS_DIR = Path(__file__).resolve().parents[3] / "agents"  # <.claude>/agents beside <.claude>/skills
READ = {"file_path": "/tmp/anything"}


def minutes_ago(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def interim_result(h: Harness, brief_args, agent: str, agent_id: str) -> Dict[str, Any]:
    """The agent writes its interim report and hands back with status `interim`."""
    def mutate(fields: Dict[str, Any]) -> None:
        fields["report"] = str(interim_path(Path(fields["report"])))
    return h.agent(brief_args, agent, status="interim", mutate=mutate, agent_id=agent_id)


def over_budget(h: Harness, agent: str, agent_id: str, minutes: int) -> str:
    """Open a segment, age it, and make the call the budget hook refuses."""
    h.budget("Read", READ, agent, agent_id)
    h.age_agent(agent_id, minutes)
    reason = h.budget("Read", READ, agent, agent_id)
    assert reason is not None, "expected the budget hook to stop the agent"
    return reason


class TimeBudgetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.init()
        self.item = self.h.add_research_item()
        self.h.approve_research(self.item)

    def tearDown(self) -> None:
        self.h.close()

    def test_budget_hook_sees_every_call_and_stops_the_agent_past_its_budget(self) -> None:
        h = self.h
        h.subagent_start("codebase-researcher", "r1")
        self.assertIsNone(h.budget("Read", READ, "codebase-researcher", "r1"))
        # Tools the global PreToolUse matcher never sees still pass through the budget hook.
        self.assertIsNone(h.budget("WebFetch", {"url": "https://example.com/x"}, "codebase-researcher", "r1"))
        h.age_agent("r1", 31)
        reason = h.budget("Grep", {"pattern": "def "}, "codebase-researcher", "r1")
        self.assertIn("TIME BUDGET REACHED", reason)
        self.assertIn("31 of your 30 active minutes", reason)
        report = h.wf / "research" / "01-research-r01-calc-module-map.codebase-researcher.md"
        # Once stopped, only the interim report and the hand-back get through.
        self.assertIsNone(h.budget("Write", {"file_path": str(interim_path(report))}, "codebase-researcher", "r1"))
        self.assertIsNone(h.budget("SubagentHandback", {"message": "interim"}, "codebase-researcher", "r1"))
        self.assertIsNotNone(h.budget("Write", {"file_path": str(report)}, "codebase-researcher", "r1"))
        self.assertIsNotNone(h.budget("Read", READ, "codebase-researcher", "r1"))
        log = h.orch("agents", "r1", "--calls")
        self.assertIn("WebFetch url=https://example.com/x", log)
        self.assertIn("REFUSED", log)

    def test_unbudgeted_roles_are_logged_but_not_limited(self) -> None:
        h = self.h
        h.budget("Read", READ, "planning-author", "p1")
        h.age_agent("p1", 600)
        self.assertIsNone(h.budget("Read", READ, "planning-author", "p1"))
        self.assertIn("planning-author", h.orch("agents"))

    def test_an_interim_report_goes_to_the_pm_before_the_agent_gets_more_time(self) -> None:
        h = self.h
        h.subagent_start("codebase-researcher", "r1")
        over_budget(h, "codebase-researcher", "r1", 31)
        entry = interim_result(h, ["research", "--item", self.item], "codebase-researcher", "r1")
        self.assertTrue(entry["valid"], entry["errors"])
        self.assertEqual(entry["interim_reason"], "time")
        self.assertIn("pm-interim --of r1", h.orch("status"))
        self.assertIn("INTERIM", h.orch("research", "list"))
        self.assertIn("has not reviewed", h.orch("agent", "continue", "r1", expect=2))
        # The research index does not treat the interim report as findings.
        self.assertNotIn("interim", (h.wf / "research" / "index.md").read_text().split("## Research documents")[-1])

        pm = h.agent(["pm-interim", "--of", "r1"], "project-manager", verdict="fail",
                     mutate=lambda f: f.update(decision="redirect", grant_minutes=15))
        self.assertTrue(pm["valid"], pm["errors"])
        out = h.orch("agent", "continue", "r1")
        self.assertIn("decided `redirect`", out)
        self.assertIn("15 more active minute", out)
        self.assertIn("status\": \"complete", out)
        # Resumed, it is judged afresh with the grant: 31 minutes used of 30 + 15.
        self.assertIsNone(h.budget("Read", READ, "codebase-researcher", "r1"))
        done = h.agent(["research", "--item", self.item], "codebase-researcher", agent_id="r1")
        self.assertTrue(done["valid"], done["errors"])
        self.assertIn("DONE", h.orch("research", "list"))
        self.assertIn("PM research-sufficiency", h.orch("status"))

    def test_extensions_are_capped_and_then_the_human_decides(self) -> None:
        h = self.h
        for n, minutes in enumerate((31, 11, 11)):
            over_budget(h, "codebase-researcher", "r1", minutes)
            interim_result(h, ["research", "--item", self.item], "codebase-researcher", "r1")
            h.agent(["pm-interim", "--of", "r1"], "project-manager", verdict="pass",
                    mutate=lambda f: f.update(decision="continue", grant_minutes=10))
            if n < 2:
                self.assertIn("CONTINUE", h.orch("agent", "continue", "r1"))
        self.assertIn("needs-human --kind time_budget", h.orch("agent", "continue", "r1", expect=2))
        h.orch("needs-human", "--kind", "time_budget", "--agent", "r1", "--summary", "third extension")
        self.assertEqual(h.state()["phase"], "NEEDS_HUMAN")
        h.orch("resolve", "--action", "continue", expect=2)  # the human has not decided yet
        h.human("/task-orchestrator resolve continue 20 it is close")
        h.orch("resolve", "--action", "continue")
        self.assertIn("20 more active minute", h.orch("agent", "continue", "r1"))

    def test_pm_interim_results_are_validated(self) -> None:
        h = self.h
        over_budget(h, "codebase-researcher", "r1", 31)
        interim_result(h, ["research", "--item", self.item], "codebase-researcher", "r1")
        bad = h.agent(["pm-interim", "--of", "r1"], "project-manager",
                      mutate=lambda f: f.update(decision="keep going", grant_minutes=0))
        self.assertFalse(bad["valid"])
        errors = " ".join(bad["errors"])
        self.assertIn("decision", errors)
        self.assertIn("grant_minutes", errors)

    def test_an_interim_result_must_point_at_the_interim_folder(self) -> None:
        h = self.h
        entry = h.agent(["research", "--item", self.item], "codebase-researcher", status="interim")
        self.assertFalse(entry["valid"])
        self.assertIn("interim/", " ".join(entry["errors"]))

    def test_the_frontmatter_command_reaches_the_budget_hook(self) -> None:
        h = self.h
        h.orch("halt")
        payload = {"hook_event_name": "PreToolUse", "session_id": h.session, "tool_name": "Read",
                   "tool_input": READ, "agent_type": "codebase-researcher", "agent_id": "r7"}
        proc = subprocess.run([PY, str(SCRIPTS / "hook.py"), "budget"], input=json.dumps(payload), env=h.env,
                              capture_output=True, text=True)
        self.assertIn("PAUSED", proc.stdout)
        # Without the argument the same payload goes to the global handlers, which allow a Read.
        proc = subprocess.run([PY, str(SCRIPTS / "hook.py")], input=json.dumps(payload), env=h.env,
                              capture_output=True, text=True)
        self.assertEqual(proc.stdout.strip(), "")


class PauseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.plan_to_approval()  # EXECUTING

    def tearDown(self) -> None:
        self.h.close()

    def test_pause_stops_read_only_agents_and_new_dispatches_but_lets_authors_finish(self) -> None:
        h = self.h
        h.subagent_start("code-reviewer", "rv1")
        h.subagent_start("code-author", "ca1")
        h.orch("halt")
        self.assertIn("PAUSED", h.budget("Read", READ, "code-reviewer", "rv1"))
        self.assertIsNone(h.budget("Edit", {"file_path": str(h.ws / "calc.py")}, "code-author", "ca1"))
        self.assertIn("paused", h.pretool("Agent", {"subagent_type": "task-verifier", "prompt": "x"}))
        status = h.orch("status")
        self.assertIn("PAUSE REQUESTED", status)
        self.assertIn("safe to exit: not yet", status)


class TaskStageInterimTest(unittest.TestCase):
    """A time stop inside a task: the rest of the task cannot be split off into research."""

    def test_split_is_refused_for_task_stages(self) -> None:
        h = Harness()
        self.addCleanup(h.close)
        h.plan_to_approval()
        path = h.wf / ".orch" / "state.json"
        state = json.loads(path.read_text())
        state["budgets"]["agent_minutes"]["test-author"] = 30
        path.write_text(json.dumps(state))
        h.agent(["--loop", "1", "pm-loop-entry"], "project-manager")
        h.orch("loop", "open", "1")
        h.orch("task", "start", "T001")
        h.agent(["T001", "readiness"], "task-verifier")
        h.agent(["T001", "pm-start"], "project-manager")
        over_budget(h, "test-author", "ta1", 31)
        entry = interim_result(h, ["T001", "work"], "test-author", "ta1")
        self.assertTrue(entry["valid"], entry["errors"])
        self.assertIn("pm-interim --of ta1", h.orch("status", "--task", "T001"))
        brief = h.orch("brief", "pm-interim", "--of", "ta1", "--agent", "project-manager")
        self.assertIn("decide `continue` or `redirect` only", brief)
        h.agent(["pm-interim", "--of", "ta1"], "project-manager", verdict="fail",
                mutate=lambda f: f.update(decision="split", grant_minutes=5))
        self.assertIn("cannot be handed off", h.orch("agent", "continue", "ta1", expect=2))


class PauseDuringPlanningTest(unittest.TestCase):
    def test_a_paused_agent_resumes_without_a_pm_review(self) -> None:
        h = Harness()
        self.addCleanup(h.close)
        h.init()
        item = h.add_research_item()
        h.approve_research(item)
        h.subagent_start("codebase-researcher", "r1")
        h.budget("Read", READ, "codebase-researcher", "r1")
        (h.wf / "HALT").touch()
        self.assertIn("PAUSED", h.budget("Read", READ, "codebase-researcher", "r1"))
        entry = interim_result(h, ["research", "--item", item], "codebase-researcher", "r1")
        self.assertEqual(entry["interim_reason"], "pause")
        h.hook({"hook_event_name": "Stop", "background_tasks": []})
        self.assertEqual(h.state()["phase"], "HALTED")
        self.assertIn("safe to exit: yes", h.orch("status"))
        self.assertIn("still paused", h.orch("agent", "continue", "r1", expect=2))
        h.human("/task-orchestrator resume")
        h.orch("resume")
        self.assertIn("orch agent continue r1", h.orch("status"))
        self.assertIn("no PM review", h.orch("brief", "pm-interim", "--of", "r1", "--agent", "project-manager",
                                             expect=2))
        self.assertIn("RESUME", h.orch("agent", "continue", "r1"))
        self.assertIsNone(h.budget("Read", READ, "codebase-researcher", "r1"))


class ResearchItemTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.init()

    def tearDown(self) -> None:
        self.h.close()

    def test_items_are_small_by_construction(self) -> None:
        h = self.h
        self.assertIn("at most 3", h.add_research_item(questions=("a?", "b?", "c?", "d?"), expect=2))
        self.assertIn("--done-when", h.add_research_item(done_when=" ".join(["word"] * 60), expect=2))
        self.assertIn("codebase-researcher only",
                      h.add_research_item(agent="domain-researcher", extra=("--mode", "map"), expect=2))
        self.assertIn("research items are for", h.add_research_item(agent="code-reviewer", expect=2))
        context = h.tmp / "context.md"
        context.write_text("pin " * 200)
        self.assertIn("context note", h.add_research_item(extra=("--context-file", str(context)), expect=2))
        self.assertIn("No research items", h.orch("research", "list"))

    def test_nothing_is_dispatched_before_the_pm_approves_it(self) -> None:
        h = self.h
        item = h.add_research_item()
        brief = ["brief", "--plan", "research", "--item", item, "--agent", "codebase-researcher"]
        self.assertIn("PROPOSED", h.orch(*brief, expect=2))
        self.assertIn("pm-research-plan", h.orch("status"))
        self.assertIn("approved research item",
                      h.orch("brief", "--plan", "research", "--topic", "everything", "--agent",
                             "codebase-researcher", expect=2))
        h.approve_research(item)
        self.assertIn("context-file", h.orch(*brief, "--note", "also audit every doc claim", expect=2))
        self.assertIn(f"--item {item}", h.orch("status"))
        text = h.orch(*brief)
        for expected in ("Where is calc defined", "Done when: The planner knows", '"item": "R01"',
                         "If you are stopped", "30 active minutes", "Noticed, not investigated",
                         "MODE `investigate`"):
            self.assertIn(expected, text)

    def test_rejected_items_block_planning_until_reworked(self) -> None:
        h = self.h
        item = h.add_research_item(title="grade every doc claim against the code")
        entry = h.agent(["pm-research-plan"], "project-manager", verdict="fail",
                        mutate=lambda f: f.update(approved=[], rejected=[
                            {"id": item, "reason": "an audit the request did not ask for"}]))
        self.assertTrue(entry["valid"], entry["errors"])
        self.assertIn("rework", h.orch("status"))
        h.orch("research", "drop", item, "--reason", "rejected by the PM")
        narrower = h.add_research_item()
        self.assertIn("pm-research-plan", h.orch("status"))
        h.approve_research(narrower)
        self.assertIn(f"--item {narrower}", h.orch("status"))
        listing = h.orch("research", "list")
        self.assertIn("DROPPED", listing)
        self.assertIn("APPROVED", listing)

    def test_a_pass_with_rejections_is_invalid(self) -> None:
        h = self.h
        item = h.add_research_item()
        entry = h.agent(["pm-research-plan"], "project-manager", verdict="pass",
                        mutate=lambda f: f.update(approved=[], rejected=[{"id": item, "reason": "too wide"}]))
        self.assertFalse(entry["valid"])

    def test_research_results_must_name_their_item(self) -> None:
        h = self.h
        item = h.add_research_item()
        h.approve_research(item)
        entry = h.agent(["research", "--item", item], "codebase-researcher", mutate=lambda f: f.pop("item"))
        self.assertFalse(entry["valid"])
        self.assertIn("requires `item`", " ".join(entry["errors"]))

    def test_pm_sees_report_sizes(self) -> None:
        h = self.h
        (h.wf / "research" / "07-research-big.codebase-researcher.md").write_text("finding\n" * 900)
        brief = h.orch("brief", "--plan", "pm-research", "--agent", "project-manager")
        self.assertIn("900 lines — over the target", brief)


def make_legacy(h: Harness) -> None:
    """Strip what workflows created before kinds and research items do not have."""
    path = h.wf / ".orch" / "state.json"
    state = json.loads(path.read_text())
    del state["research_items"], state["kind"]
    del state["budgets"]["agent_minutes"], state["budgets"]["time_grants"]
    path.write_text(json.dumps(state))


class UpgradeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def old_result(self, stage: str, agent: str, name: str, **extra: Any) -> None:
        """A result recorded by the old code (no research item), as its SubagentStop left it."""
        report = self.h.wf / ("research" if stage == "research" else "reviews/plan") / name
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("finding\n" * 1200)
        result = {"workflow": self.h.state()["workflow_id"], "stage": stage, "status": "complete",
                  "report": str(report), **extra}
        ledger.append(Workflow(self.h.wf), {"kind": "agent_result", "agent_type": agent, "agent_id": name,
                                            "valid": True, "errors": [], "result": result})

    def test_a_legacy_workflow_in_planning_is_upgraded_by_the_human(self) -> None:
        h = self.h
        h.init(confirm_scope=False)
        make_legacy(h)
        self.old_result("research", "codebase-researcher", "01-research-everything.codebase-researcher.md", verdict="n/a")
        self.old_result("pm-research", "project-manager", "02-pm-research.project-manager.md", verdict="fail")
        self.assertIn("UPGRADE NEEDED", h.orch("status"))
        self.assertIn("UPGRADE NEEDED", h.orch("brief", "--plan", "pm-research", "--agent", "project-manager",
                                               expect=2))
        self.assertIn("human's call", h.orch("upgrade", "--kind", "kb", expect=2))
        h.human("/task-orchestrator upgrade docs")  # a different kind does not authorize kb
        h.orch("upgrade", "--kind", "kb", expect=2)
        h.human("/task-orchestrator upgrade kb")
        self.assertIn("1 earlier research result", h.orch("upgrade", "--kind", "kb"))
        state = h.state()
        self.assertEqual((state["kind"], state["research_items"]), ("kb", {}))
        self.assertEqual(state["budgets"]["agent_minutes"]["codebase-researcher"], 30)
        self.assertIn("upgrade to kind `kb`", (h.wf / "decisions.md").read_text())
        status = h.orch("status")
        self.assertIn("kind kb", status)
        self.assertIn("scope confirmed by the human", status)  # the scope check comes before anything else
        h.confirm_scope()
        self.assertIn("PM research-sufficiency", h.orch("status"))  # the pre-upgrade check no longer counts
        brief = h.orch("brief", "--plan", "pm-research", "--agent", "project-manager")
        self.assertIn("Do not change, fix, test", brief)
        self.assertIn("1200 lines — over the target", brief)
        # Further research is a focused item the PM approves first.
        item = h.add_research_item()
        self.assertIn("pm-research-plan", h.orch("status"))
        self.assertIn("PROPOSED", h.orch("brief", "--plan", "research", "--item", item, "--agent",
                                         "codebase-researcher", expect=2))
        self.assertIn("nothing to upgrade", h.orch("upgrade", "--kind", "kb", expect=2))

    def test_a_legacy_workflow_already_executing_carries_on_without_upgrading(self) -> None:
        h = self.h
        h.plan_to_approval()
        make_legacy(h)
        self.assertIn("LOOP 1", h.orch("status"))
        entry = h.agent(["--loop", "1", "pm-loop-entry"], "project-manager")
        self.assertTrue(entry["valid"], entry["errors"])
        # The budget hook falls back to the default budgets.
        over_budget(h, "codebase-researcher", "r1", 31)


class DocKindTest(unittest.TestCase):
    def test_kb_briefs_carry_non_goals_map_mode_and_planning_depth(self) -> None:
        h = Harness()
        self.addCleanup(h.close)
        h.init(kind="kb")
        item = h.add_research_item()
        self.assertIn("mode map", h.orch("research", "list"))
        h.approve_research(item)
        brief = h.orch("brief", "--plan", "research", "--item", item, "--agent", "codebase-researcher")
        for expected in ("MODE `map`", "Do NOT invoke /code-sleuth", "Do not change, fix, test",
                         "Noticed, not investigated", "the map, not the documentation's content", "answer-first"):
            self.assertIn(expected, brief)
        contract = h.subagent_start("codebase-researcher", "r9")
        for expected in ("Do not change, fix, test", "confidence score", "answer-first", "Record, don't investigate"):
            self.assertIn(expected, contract)


class ResumeAcrossSessionsTest(unittest.TestCase):
    SECOND = "second-session"

    def setUp(self) -> None:
        self.h = Harness()
        self.h.plan_to_approval()

    def tearDown(self) -> None:
        self.h.close()

    def orch2(self, *args: str, expect: int = 0) -> str:
        env = dict(self.h.env, CLAUDE_CODE_SESSION_ID=self.SECOND)
        proc = subprocess.run([PY, str(ORCH), *args], env=env, capture_output=True, text=True)
        text = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, expect, text)
        return text

    def test_list_offers_workflows_independently_of_bindings(self) -> None:
        rows = json.loads(self.orch2("list", "--json"))
        self.assertEqual((rows[0]["workflow_dir"], rows[0]["phase"]), (str(self.h.wf), "EXECUTING"))
        self.assertEqual(rows[0]["bound"], f"session {self.h.session[:8]}")
        self.assertIn("LOOP 1", rows[0]["next"])
        self.h.orch("unbind")
        rows = json.loads(self.orch2("list", "--json"))
        self.assertEqual(rows[0]["bound"], "none")
        self.assertIn("1. ", self.orch2("list"))

    def test_bind_refuses_a_recently_active_session_unless_taking_over(self) -> None:
        self.assertIn("--take-over", self.orch2("bind", str(self.h.wf), expect=2))
        self.orch2("bind", self.h.state()["workflow_id"], "--take-over")  # by workflow id
        self.assertEqual(self.h.state()["session_id"], self.SECOND)
        self.assertIn("not bound", self.h.orch("status", expect=2))

    def test_a_resume_typed_in_a_fresh_session_is_captured(self) -> None:
        h = self.h
        (h.wf / "HALT").touch()
        h.hook({"hook_event_name": "Stop", "background_tasks": []})
        self.assertEqual(h.state()["phase"], "HALTED")
        hooks.dispatch({"hook_event_name": "UserPromptExpansion", "expansion_type": "slash_command",
                        "session_id": self.SECOND, "command_name": "task-orchestrator",
                        "command_args": f"resume {h.wf}"})
        human = [e for e in h.ledger() if e.get("kind") == "human"][-1]
        self.assertEqual(human["verb"], "resume")
        self.assertIn("unbound", human["via"])
        self.orch2("bind", str(h.wf), "--take-over")
        self.orch2("resume")  # no second `/task-orchestrator resume` needed
        self.assertEqual(h.state()["phase"], "EXECUTING")

    def test_other_prompts_in_an_unbound_session_are_ignored(self) -> None:
        before = len(self.h.ledger())
        hooks.dispatch({"hook_event_name": "UserPromptSubmit", "session_id": "x", "prompt": "/task-orchestrator approve"})
        hooks.dispatch({"hook_event_name": "UserPromptSubmit", "session_id": "x",
                        "prompt": "/task-orchestrator resume /no/such/workflow"})
        hooks.dispatch({"hook_event_name": "UserPromptSubmit", "session_id": "x", "source": "system",
                        "prompt": f"/task-orchestrator resume {self.h.wf}"})
        self.assertEqual(len(self.h.ledger()), before)

    def test_an_agent_cut_off_by_a_restart_shows_as_interrupted(self) -> None:
        h = self.h
        h.subagent_start("task-verifier", "tv1")
        h.budget("Read", READ, "task-verifier", "tv1")
        self.orch2("bind", str(h.wf), "--take-over")
        listing = self.orch2("agents")
        self.assertIn("tv1", listing)
        self.assertIn("INTERRUPTED", listing)
        self.assertIn("INTERRUPTED — task-verifier tv1", self.orch2("status"))
        self.assertIn("RESUME", self.orch2("agent", "continue", "tv1"))
        self.assertNotIn("INTERRUPTED", self.orch2("status"))  # acknowledged

    def test_claude_resume_keeps_the_session_id_but_its_dead_agents_are_still_found(self) -> None:
        h = self.h
        h.budget("Read", READ, "codebase-researcher", "r1")
        path = h.wf / ".orch" / "agents" / "r1.json"
        info = json.loads(path.read_text())
        info["segments"][-1]["start"] = minutes_ago(120)
        info["last_call_at"] = minutes_ago(119)
        path.write_text(json.dumps(info))
        text, _ = h.hook({"hook_event_name": "SessionStart", "source": "resume"})  # same session id
        self.assertIn("INTERRUPTED: r1", text)
        self.assertIn("INTERRUPTED — codebase-researcher r1", h.orch("status"))
        self.assertIn("RESUME", h.orch("agent", "continue", "r1"))
        self.assertNotIn("INTERRUPTED", h.orch("status"))
        self.assertIsNone(h.budget("Read", READ, "codebase-researcher", "r1"))  # 1 active minute, not 120

    def test_compaction_does_not_mark_live_agents_interrupted(self) -> None:
        h = self.h
        h.budget("Read", READ, "codebase-researcher", "r1")
        h.hook({"hook_event_name": "SessionStart", "source": "compact"})
        self.assertIn("RUNNING", h.orch("agents"))
        self.assertNotIn("INTERRUPTED", h.orch("status"))

    def test_downtime_after_a_restart_does_not_count_against_the_budget(self) -> None:
        h = self.h
        h.budget("Read", READ, "codebase-researcher", "r1")
        path = h.wf / ".orch" / "agents" / "r1.json"
        info = json.loads(path.read_text())
        info["segments"][-1]["start"] = minutes_ago(120)  # started before the machine went down...
        info["last_call_at"] = minutes_ago(119)            # ...and was last heard from a minute later
        path.write_text(json.dumps(info))
        self.orch2("bind", str(h.wf), "--take-over")
        self.orch2("agent", "continue", "r1")
        text, _ = hooks.dispatch_budget({"hook_event_name": "PreToolUse", "session_id": self.SECOND,
                                         "tool_name": "Read", "tool_input": READ,
                                         "agent_type": "codebase-researcher", "agent_id": "r1"})
        self.assertIsNone(text)  # 1 active minute, not the 2 hours the machine was down
        self.assertEqual(json.loads(path.read_text())["session_id"], self.SECOND)


class SelftestTest(unittest.TestCase):
    def test_selftest_passes_when_every_hook_does_its_part(self) -> None:
        h = Harness()
        self.addCleanup(h.close)
        out = h.orch("selftest")
        h.wf = Path(out.splitlines()[0])
        brief = out[out.index("# Dispatch brief"):]
        fields = json.loads(TEMPLATE_RE.findall(brief)[-1])
        contract = h.subagent_start("project-manager", "st1")
        self.assertIn("TASK-ORCHESTRATOR CONTRACT", contract)
        h.pretool("Bash", {"command": "true"})  # the global PreToolUse hook
        self.assertIn("TIME BUDGET", h.budget("Read", {"file_path": str(h.wf / "request.md")}, "project-manager", "st1"))
        interim = interim_path(Path(fields["report"]))
        self.assertIn(str(interim), brief)
        self.assertIsNone(h.budget("Write", {"file_path": str(interim)}, "project-manager", "st1"))
        interim.parent.mkdir(parents=True, exist_ok=True)
        interim.write_text("Stopped by the budget hook, as the selftest expects.\n")
        fields.update(status="interim", report=str(interim), contract_seen=True, budget_stopped=True)
        h.hook({"hook_event_name": "SubagentStop", "agent_type": "project-manager", "agent_id": "st1",
                "last_assistant_message": "```orch-result\n" + json.dumps(fields) + "\n```"})
        h.human("/task-orchestrator status")
        check = h.orch("selftest", "--check")
        self.assertIn("SELFTEST PASSED", check)
        self.assertIn("[x] the budget hook stopped it", check)


class AgentDefinitionsTest(unittest.TestCase):
    def test_every_roster_agent_pins_model_effort_budget_hook_and_style(self) -> None:
        if not AGENTS_DIR.is_dir():
            self.skipTest(f"no agent definitions beside this skill ({AGENTS_DIR})")
        for name in sorted(AGENTS):
            with self.subTest(agent=name):
                path = AGENTS_DIR / f"{name}.md"
                self.assertEqual(orch.agent_definition_problems(path, name), [])
                text = path.read_text(encoding="utf-8")
                self.assertIn("answer-first.md", text)
                if name in REVIEWERS:
                    self.assertIn("confidence score", text)
        pm = (AGENTS_DIR / "project-manager.md").read_text(encoding="utf-8")
        for mode in ("pm-research-plan", "pm-interim"):
            self.assertIn(f"**{mode}**", pm)

    def test_problems_are_reported(self) -> None:
        h = Harness()
        self.addCleanup(h.close)
        bad = h.tmp / "code-author.md"
        bad.write_text("---\nname: code-author\nmodel: sonnet\n---\nbody\n")
        problems = " ".join(orch.agent_definition_problems(bad, "code-author"))
        self.assertIn("model should be `opus`", problems)
        self.assertIn("effort should be `xhigh`", problems)
        self.assertIn("no budget hook", problems)


if __name__ == "__main__":
    unittest.main()
