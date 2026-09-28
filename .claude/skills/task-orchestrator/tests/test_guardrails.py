"""Hook guardrails, Stop-hook continuation/wait logic, scan, snapshots, plan validation."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from harness import PY, Harness, git

from orchestrator import plan as planmod
from orchestrator import scan as scanmod
from orchestrator import snapshot as snapmod
from orchestrator import waits
from orchestrator.common import Workflow


class PreToolUseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.plan_to_approval()  # phase EXECUTING

    def tearDown(self) -> None:
        self.h.close()

    def test_control_files_are_off_limits_to_everyone(self) -> None:
        state = str(self.h.wf / ".orch" / "state.json")
        self.assertIsNotNone(self.h.pretool("Edit", {"file_path": state}))
        self.assertIsNotNone(self.h.pretool("Write", {"file_path": state}, agent="code-author"))
        self.assertIsNotNone(self.h.pretool("Bash", {"command": f"cat {state}"}))
        self.assertIsNotNone(self.h.pretool("Bash", {"command": "echo {} >> .orch/ledger.jsonl"}))
        self.assertIsNone(self.h.pretool("Bash", {"command": f'python3 "/x/orch.py" status'}))

    def test_frozen_plan_after_approval(self) -> None:
        reason = self.h.pretool("Edit", {"file_path": str(self.h.wf / "tasks" / "T001-add-mul.md")},
                                agent="planning-author")
        self.assertIn("frozen", reason)

    def test_generated_files_and_decisions_log(self) -> None:
        self.assertIn("generated", self.h.pretool("Write", {"file_path": str(self.h.wf / "index.md")}))
        self.assertIn("orch note", self.h.pretool("Edit", {"file_path": str(self.h.wf / "decisions.md")}))

    def test_orchestrator_delegates_workspace_edits(self) -> None:
        self.assertIn("delegates", self.h.pretool("Edit", {"file_path": str(self.h.ws / "calc.py")}))
        self.assertIsNone(self.h.pretool("Edit", {"file_path": str(self.h.ws / "calc.py")}, agent="code-author"))

    def test_readonly_roles_cannot_touch_workspaces(self) -> None:
        for agent in ("code-reviewer", "project-manager", "task-verifier", "codebase-researcher"):
            self.assertIn("read-only", self.h.pretool("Write", {"file_path": str(self.h.ws / "x.py")}, agent=agent))

    def test_authors_stay_inside_workspaces(self) -> None:
        outside = Path(tempfile.gettempdir()) / "elsewhere.py"
        self.assertIn("declared workspaces", self.h.pretool("Write", {"file_path": str(outside)}, agent="code-author"))

    def test_agents_write_only_their_own_reports(self) -> None:
        own = self.h.wf / "runs" / "T001" / "a1" / "05-review-r0.code-reviewer.md"
        other = self.h.wf / "runs" / "T001" / "a1" / "06-pm-accept-r0.project-manager.md"
        self.assertIsNone(self.h.pretool("Write", {"file_path": str(own)}, agent="code-reviewer"))
        self.assertIsNotNone(self.h.pretool("Write", {"file_path": str(other)}, agent="code-reviewer"))
        self.assertIsNotNone(self.h.pretool("Write", {"file_path": str(other)}))  # orchestrator can't forge

    def test_roster_only_and_no_workflow_tool(self) -> None:
        self.assertIn("roster", self.h.pretool("Agent", {"subagent_type": "general-purpose", "prompt": "x"}))
        # Roster agents may fan out to their skills' own sub-agents.
        self.assertIsNone(self.h.pretool("Agent", {"subagent_type": "general-purpose"}, agent="code-reviewer"))
        self.assertIn("Workflow", self.h.pretool("Workflow", {"script": "x"}))

    def test_dispatch_must_carry_a_saved_brief_verbatim(self) -> None:
        h = self.h
        h.agent(["--loop", "1", "pm-loop-entry"], "project-manager")
        h.orch("loop", "open", "1")
        h.orch("task", "start", "T001")
        brief = h.orch("brief", "T001", "readiness", "--agent", "task-verifier")
        self.assertIsNone(h.pretool("Agent", {"subagent_type": "task-verifier", "prompt": brief}))
        self.assertIsNone(h.pretool("Agent", {"subagent_type": "task-verifier", "prompt": "Context first.\n\n" + brief}))
        self.assertIn("orch brief", h.pretool("Agent", {"subagent_type": "task-verifier", "prompt": "verify T001 please"}))
        self.assertIn("different agent", h.pretool("Agent", {"subagent_type": "code-reviewer", "prompt": brief}))
        edited = brief.replace("MODE: readiness", "MODE: skim quickly")
        self.assertIn("verbatim", h.pretool("Agent", {"subagent_type": "task-verifier", "prompt": edited}))

    def test_subagents_cannot_run_orchestrator_transitions(self) -> None:
        cli = 'python3 "/Users/x/.claude/skills/task-orchestrator/scripts/orch.py"'
        self.assertIsNotNone(self.h.pretool("Bash", {"command": f"{cli} task accept T001"}, agent="code-author"))
        self.assertIsNotNone(self.h.pretool("Bash", {"command": f"{cli} approve"}, agent="project-manager"))
        self.assertIsNone(self.h.pretool("Bash", {"command": f"{cli} evidence T001 red"}, agent="test-author"))
        self.assertIsNone(self.h.pretool("Bash", {"command": f"{cli} task diff T001"}, agent="task-verifier"))

    def test_documented_orch_variable_form_is_policed(self) -> None:
        define = "ORCH='python3 \"$HOME/.claude/skills/task-orchestrator/scripts/orch.py\"'"
        for sep in ("\n", "; ", " && "):
            with self.subTest(sep=repr(sep)):
                self.assertIsNotNone(self.h.pretool("Bash", {"command": f'{define}{sep}$ORCH note "user said skip"'},
                                                    agent="code-author"))
                self.assertIsNotNone(self.h.pretool("Bash", {"command": f"{define}{sep}${{ORCH}} task fail T001 --reason x"},
                                                    agent="code-author"))
                self.assertIsNone(self.h.pretool("Bash", {"command": f"{define}{sep}$ORCH evidence T001 red"},
                                                 agent="test-author"))
                self.assertIsNone(self.h.pretool("Bash", {"command": f"{define}{sep}$ORCH task diff T001 --since-checkpoint"},
                                                 agent="task-verifier"))
        self.assertIsNotNone(self.h.pretool("Bash", {"command": f"{define}"}, agent="code-author"))
        # Mentioning the CLI does not exempt a write to the control files.
        forged = f"echo x >> {self.h.wf}/.orch/ledger.jsonl # orch.py status"
        self.assertIsNotNone(self.h.pretool("Bash", {"command": forged}))
        self.assertIsNotNone(self.h.pretool("Bash", {"command": "cd x && cat .orch/state.json"}, agent="project-manager"))

    def test_unbound_sessions_are_untouched(self) -> None:
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Edit", "session_id": "someone-else",
                   "tool_input": {"file_path": str(self.h.wf / ".orch" / "state.json")}}
        from orchestrator import hooks
        self.assertEqual(hooks.dispatch(payload), (None, 0))


class PlanningWritesTest(unittest.TestCase):
    def test_planning_roles(self) -> None:
        h = Harness()
        try:
            h.init()
            plan = str(h.wf / "plan.md")
            self.assertIsNone(h.pretool("Write", {"file_path": plan}, agent="planning-author"))
            self.assertIsNone(h.pretool("Edit", {"file_path": plan}, agent="test-planner"))
            self.assertIsNotNone(h.pretool("Write", {"file_path": plan}))  # orchestrator delegates planning
            self.assertIsNone(h.pretool("Write", {"file_path": str(h.wf / "request.md")}))
            self.assertIsNotNone(h.pretool("Write", {"file_path": plan}, agent="code-reviewer"))
        finally:
            h.close()


class StopHookTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.plan_to_approval()

    def tearDown(self) -> None:
        self.h.close()

    def stop(self, **extra):
        text, _ = self.h.hook(dict({"hook_event_name": "Stop"}, **extra))
        return json.loads(text) if text else None

    def test_active_workflow_forces_continuation_with_next_action(self) -> None:
        result = self.stop(background_tasks=[])
        self.assertEqual(result["decision"], "block")
        self.assertIn("NEXT:", result["reason"])
        self.assertIn("QUALITY MANDATE", result["reason"])
        self.assertEqual(self.h.state()["stop_continuations"], 1)

    def test_waiting_on_background_agents_is_allowed_and_free(self) -> None:
        running = [{"id": "a1", "type": "subagent", "status": "running"}]
        self.assertIsNone(self.stop(background_tasks=running))
        state = self.h.state()
        self.assertEqual(state["stop_continuations"], 0)
        self.assertEqual(state["last_wait"]["consecutive_waits"], 1)

    def test_waits_without_progress_are_capped(self) -> None:
        running = [{"id": "a1", "type": "subagent", "status": "running"}]
        state_path = self.h.wf / ".orch" / "state.json"
        state = json.loads(state_path.read_text())
        state["max_consecutive_waits"] = 2
        state_path.write_text(json.dumps(state))
        self.assertIsNone(self.stop(background_tasks=running))
        self.assertIsNone(self.stop(background_tasks=running))
        result = self.stop(background_tasks=running)
        self.assertEqual(result["decision"], "block")
        self.assertIn("no recorded progress", result["reason"])

    def test_plan_drift_forces_plan_change_required(self) -> None:
        with open(self.h.wf / "plan.md", "a") as handle:
            handle.write("\nsneaky scope cut\n")
        result = self.stop(background_tasks=[])
        self.assertEqual(result["decision"], "block")
        self.assertEqual(self.h.state()["phase"], "PLAN_CHANGE_REQUIRED")
        self.assertIsNone(self.stop(background_tasks=[]))  # stop phase now

    def test_halt_file(self) -> None:
        (self.h.wf / "HALT").touch()
        self.assertIsNone(self.stop(background_tasks=[]))
        self.assertEqual(self.h.state()["phase"], "HALTED")
        self.h.orch("resume", expect=2)
        self.h.human("/task-orchestrator resume")
        self.h.orch("resume")
        self.assertEqual(self.h.state()["phase"], "EXECUTING")

    def edit_state(self, **fields) -> None:
        state_path = self.h.wf / ".orch" / "state.json"
        state = json.loads(state_path.read_text())
        state.update(fields)
        state_path.write_text(json.dumps(state))

    def halt_and_resume(self, h: Harness) -> None:
        (h.wf / "HALT").touch()
        h.hook({"hook_event_name": "Stop", "background_tasks": []})
        self.assertEqual(h.state()["phase"], "HALTED")
        h.human("/task-orchestrator resume")
        h.orch("resume")

    def test_halt_during_planning_resumes_to_planning(self) -> None:
        h = Harness()
        self.addCleanup(h.close)
        h.init()
        self.halt_and_resume(h)
        state = h.state()
        self.assertEqual(state["phase"], "PLANNING")
        self.assertIsNone(state["block_reason"])

    def test_halt_during_needs_human_keeps_the_pending_decision(self) -> None:
        need = {"kind": "final_review_budget", "summary": "x", "raised_at": "2026-01-01T00:00:00.000Z"}
        self.edit_state(phase="NEEDS_HUMAN", resume_phase="FINAL", needs_human=need)
        self.halt_and_resume(self.h)
        state = self.h.state()
        self.assertEqual(state["phase"], "NEEDS_HUMAN")
        self.assertEqual(state["resume_phase"], "FINAL")
        self.assertEqual(state["needs_human"], need)

    def test_halt_during_plan_change_required_restores_its_reason(self) -> None:
        self.edit_state(phase="PLAN_CHANGE_REQUIRED", resume_phase="EXECUTING", block_reason="scope drift")
        self.halt_and_resume(self.h)
        state = self.h.state()
        self.assertEqual((state["phase"], state["resume_phase"]), ("PLAN_CHANGE_REQUIRED", "EXECUTING"))
        self.assertEqual(state["block_reason"], "scope drift")

    def test_repeated_halt_does_not_forget_where_it_came_from(self) -> None:
        (self.h.wf / "HALT").touch()
        self.stop(background_tasks=[])
        (self.h.wf / "HALT").touch()
        self.stop(background_tasks=[])
        self.h.human("/task-orchestrator resume")
        self.h.orch("resume")
        self.assertEqual(self.h.state()["phase"], "EXECUTING")

    def test_legacy_halt_without_a_record(self) -> None:
        # Halted by an older version, from a stop phase: nothing says where to go back to.
        self.edit_state(phase="HALTED", halted_from=None, resume_phase=None,
                        halted_at="2026-01-01T00:00:00.000Z")
        self.h.human("/task-orchestrator resume")
        self.assertIn("cannot be inferred", self.h.orch("resume", expect=2))
        self.assertEqual(self.h.state()["phase"], "HALTED")
        self.edit_state(approved_at=None)
        self.h.orch("resume")
        self.assertEqual(self.h.state()["phase"], "PLANNING")

    def test_subagent_stop_payloads_are_ignored(self) -> None:
        self.assertIsNone(self.stop(agent_id="abc", background_tasks=[]))

    def test_finished_agent_lingering_in_payload_is_not_waited_on(self) -> None:
        now = datetime.now(timezone.utc)
        stamp = lambda minutes: (now - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")  # noqa: E731
        transcript = Path(tempfile.mkstemp(suffix=".jsonl")[1])
        self.addCleanup(transcript.unlink)
        transcript.write_text("\n".join(json.dumps(r) for r in [
            {"type": "user", "timestamp": stamp(5), "toolUseResult": {"isAsync": True, "agentId": "a9"}},
            {"type": "queue-operation", "operation": "enqueue", "timestamp": stamp(1),
             "content": '<agent-message from="a9">\n[Subagent hand-back] done'},
        ]) + "\n")
        lingering = [{"id": "a9", "type": "subagent", "status": "running"}]
        result = self.stop(background_tasks=lingering, transcript_path=str(transcript))
        self.assertEqual(result["decision"], "block")
        self.assertIn("SKILL.md", result["reason"])


class HumanPromptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.init(confirm_scope=False)

    def tearDown(self) -> None:
        self.h.close()

    def humans(self):
        return [e for e in self.h.ledger() if e.get("kind") == "human"]

    def test_machine_injected_prompts_are_not_human(self) -> None:
        for source in ("system", "loop_wakeup", "schedule_wakeup", "poll_event"):
            self.h.hook({"hook_event_name": "UserPromptSubmit", "prompt": "/task-orchestrator approve",
                         "source": source})
        self.assertEqual(self.humans(), [])
        self.h.hook({"hook_event_name": "UserPromptSubmit", "prompt": "/task-orchestrator approve", "source": "user"})
        self.assertEqual([e["verb"] for e in self.humans()], ["approve"])

    def test_xml_slash_command_form(self) -> None:
        prompt = ("<command-message>task-orchestrator is running…</command-message>\n"
                  "<command-name>/task-orchestrator</command-name>\n<command-args>resolve retry T001 go</command-args>")
        self.h.hook({"hook_event_name": "UserPromptSubmit", "prompt": prompt})
        entry = self.humans()[-1]
        self.assertEqual((entry["verb"], entry["args"]), ("resolve", ["retry", "T001", "go"]))

    def test_expansion_hook_and_dedupe(self) -> None:
        self.h.hook({"hook_event_name": "UserPromptExpansion", "expansion_type": "slash_command",
                     "command_name": "task-orchestrator", "command_args": "approve", "prompt": "..."})
        self.h.hook({"hook_event_name": "UserPromptSubmit", "prompt": "/task-orchestrator approve", "source": "user"})
        self.assertEqual([e["verb"] for e in self.humans()], ["approve"])
        self.h.hook({"hook_event_name": "UserPromptExpansion", "expansion_type": "mcp_prompt",
                     "command_name": "task-orchestrator", "command_args": "close"})
        self.assertEqual(len(self.humans()), 1)


class WaitTranscriptTest(unittest.TestCase):
    def _write(self, records):
        handle = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
        for record in records:
            handle.write(json.dumps(record) + "\n")
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def ts(self, minutes):
        return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    def handback(self, agent, minutes):
        text = f'<agent-message from="{agent}">\n[Subagent hand-back] report'
        return {"type": "queue-operation", "operation": "enqueue", "timestamp": self.ts(minutes), "content": text}

    def test_dispatch_handback_resume_cycle(self) -> None:
        dispatch = {"type": "user", "timestamp": self.ts(10),
                    "toolUseResult": {"isAsync": True, "status": "async_launched", "agentId": "a1"}}
        path = self._write([dispatch])
        self.assertEqual(waits.pending_from_transcript(path), ["a1"])
        path = self._write([dispatch, self.handback("a1", 8)])
        self.assertEqual(waits.pending_from_transcript(path), [])
        resume = {"type": "user", "timestamp": self.ts(6), "toolUseResult": {"success": True, "resumedAgentId": "a1"}}
        path = self._write([dispatch, self.handback("a1", 8), resume])
        self.assertEqual(waits.pending_from_transcript(path), ["a1"])
        attach = {"type": "attachment", "timestamp": self.ts(4),
                  "attachment": {"type": "queued_command",
                                 "prompt": "<task-notification>\n<task-id>a1</task-id>\n<status>completed</status>"}}
        path = self._write([dispatch, self.handback("a1", 8), resume, attach])
        self.assertEqual(waits.pending_from_transcript(path), [])

    def test_stale_dispatch_is_not_waited_on(self) -> None:
        dispatch = {"type": "user", "timestamp": self.ts(120),
                    "toolUseResult": {"isAsync": True, "agentId": "old"}}
        self.assertEqual(waits.pending_from_transcript(self._write([dispatch])), [])

    def test_payload_list_wins(self) -> None:
        self.assertEqual(waits.pending({"background_tasks": [{"id": "x", "status": "running"}]}), ["x"])
        self.assertEqual(waits.pending({"background_tasks": []}), [])


class ScanTest(unittest.TestCase):
    def test_detects_cheapening_patterns(self) -> None:
        diff = "\n".join([
            "diff --git a/pkg/a_test.go b/pkg/a_test.go",
            "--- a/pkg/a_test.go", "+++ b/pkg/a_test.go",
            "-func TestImportant(t *testing.T) {",
            "-\trequire.Equal(t, 1, got)",
            "-\tassert.NoError(t, err)",
            "+\tt.Skip(\"flaky\")",
            "diff --git a/pkg/a.go b/pkg/a.go",
            "--- a/pkg/a.go", "+++ b/pkg/a.go",
            "+\t// TODO: handle errors later",
            "+\tx := y //nolint:errcheck",
            "diff --git a/.golangci.yml b/.golangci.yml",
            "--- a/.golangci.yml", "+++ b/.golangci.yml",
            "-  - errcheck",
        ])
        result = scanmod.scan(diff, expected_paths=["pkg/"])
        cats = result["by_category"]
        for category in ("test_removed", "test_skip_added", "assertions_reduced", "deferral_marker_added",
                         "lint_suppression_added", "gate_config_changed", "out_of_plan_undeclared"):
            self.assertIn(category, cats, category)
        self.assertEqual(len(result["digest"]), 16)

    def test_clean_diff_has_no_hits(self) -> None:
        diff = "diff --git a/a.go b/a.go\n--- a/a.go\n+++ b/a.go\n+func Add(a, b int) int { return a + b }\n"
        self.assertEqual(scanmod.scan(diff)["hits"], [])


class SnapshotTest(unittest.TestCase):
    def test_git_snapshot_ignores_workflow_dir_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "repo"
            ws.mkdir()
            (ws / "a.txt").write_text("a\n")
            git(ws, "init", "-q")
            git(ws, "add", "-A")
            git(ws, "commit", "-qm", "init")
            wf = Workflow(ws / "plans" / "wf")
            wf.control.mkdir(parents=True)
            one = snapmod.take(wf, "code", ws)
            (wf.root / "plan.md").write_text("plan inside the workspace\n")
            (ws / "__pycache__").mkdir()
            (ws / "__pycache__" / "x.pyc").write_text("junk")
            self.assertEqual(one.id, snapmod.take(wf, "code", ws).id)
            (ws / "a.txt").write_text("changed\n")
            two = snapmod.take(wf, "code", ws)
            self.assertNotEqual(one.id, two.id)
            self.assertEqual([c["path"] for c in snapmod.name_status(one, two)], ["a.txt"])
            # The user's real index is untouched: nothing staged by the snapshot.
            self.assertEqual(git(ws, "diff", "--cached", "--name-only").strip(), "")

    def test_git_snapshot_ignores_workflow_files_already_in_the_index(self) -> None:
        # An auto-sync commits and stages the workflow's own files; they must not reach
        # the snapshot, and an empty workspace must not take the repository's tree id.
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "notebook"
            ws = repo / "projects" / "p"
            ws.mkdir(parents=True)
            (repo / "other.txt").write_text("o\n")
            wf = Workflow(ws / "wf")
            wf.control.mkdir(parents=True)
            (wf.root / "plan.md").write_text("v1\n")
            git(repo, "init", "-q")
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "sync")
            (wf.root / "plan.md").write_text("v2\n")
            git(repo, "add", "-A")
            (wf.root / "plan.md").write_text("v3\n")  # staged, then edited again
            index_before = git(repo, "ls-files", "-s")
            one = snapmod.take(wf, "kb", ws)
            self.assertEqual(one.id, "g:empty")
            self.assertEqual(git(repo, "ls-files", "-s"), index_before)
            (repo / "other.txt").write_text("changed\n")
            git(repo, "add", "-A")
            self.assertEqual(snapmod.take(wf, "kb", ws).id, "g:empty")
            (ws / "kb").mkdir()
            (ws / "kb" / "a.md").write_text("# A\n")
            two = snapmod.take(wf, "kb", ws)
            self.assertNotEqual(two.id, "g:empty")
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "sync")
            self.assertEqual(snapmod.take(wf, "kb", ws).id, two.id)
            self.assertEqual(snapmod.name_status(one, two), [{"status": "A", "path": "kb/a.md"}])

    def test_shadow_snapshot_for_plain_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "docs"
            ws.mkdir()
            (ws / "a.md").write_text("# A\n")
            wf = Workflow(Path(tmp) / "wf")
            wf.control.mkdir(parents=True)
            one = snapmod.take(wf, "docs", ws)
            self.assertTrue(one.id.startswith("s:"))
            (ws / "b.md").write_text("# B\n")
            two = snapmod.take(wf, "docs", ws)
            self.assertEqual(snapmod.name_status(one, two), [{"status": "A", "path": "b.md"}])
            self.assertFalse((ws / ".git").exists())

    def test_scoped_snapshot_ignores_changes_outside_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "docs"
            (ws / "a").mkdir(parents=True)
            (ws / "b").mkdir()
            (ws / "a" / "x.md").write_text("x\n")
            wf = Workflow(Path(tmp) / "wf")
            wf.control.mkdir(parents=True)
            one = snapmod.take(wf, "docs", ws, scope=["a"])
            (ws / "b" / "y.md").write_text("y\n")
            self.assertEqual(one.id, snapmod.take(wf, "docs", ws, scope=["a"]).id)


class PlanValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.init()

    def tearDown(self) -> None:
        self.h.close()

    def errors(self, **overrides):
        self.h.write_plan(**overrides)
        return planmod.validate(Workflow(self.h.wf)).errors

    def test_valid_package(self) -> None:
        self.assertEqual(self.errors(), [])

    def test_rules(self) -> None:
        cases = {
            "estimated_days": (2.5, "split the task"),
            "reviewers": (["code-reviewer"], "must include"),
            "authors": (["code-author"], "not an allowed sequence"),
            "test_forward": ("not-applicable", "test_forward_justification"),
            "requirements": ([], "traces to no requirement"),
            "depends_on": (["T009"], "unknown task"),
            "parallel_safe": (True, "parallel_safe is only allowed"),
        }
        for key, (value, expect) in cases.items():
            with self.subTest(key=key):
                found = self.errors(**{key: value})
                self.assertTrue(any(expect in e for e in found), (key, found))

    def test_criterion_needs_verified_by(self) -> None:
        self.h.write_plan()
        path = self.h.wf / "tasks" / "T001-add-mul.md"
        path.write_text(path.read_text().replace(" — Verified by: test `test_mul.TestMul.test_product`", ""))
        errors = planmod.validate(Workflow(self.h.wf)).errors
        self.assertTrue(any("Verified by" in e for e in errors), errors)

    def test_uncovered_requirement(self) -> None:
        self.h.write_plan()
        plan = self.h.wf / "plan.md"
        plan.write_text(plan.read_text().replace("- R1: calc", "- R2: calc divides.\n- R1: calc"))
        errors = planmod.validate(Workflow(self.h.wf)).errors
        self.assertTrue(any("R2" in e for e in errors), errors)

    def test_unresolved_question_blocks_approval_only(self) -> None:
        self.h.write_plan()
        plan = self.h.wf / "plan.md"
        plan.write_text(plan.read_text().replace("- [x] Q1: Integers only? — Resolution: any numbers.",
                                                 "- [ ] Q1: Integers only?"))
        wf = Workflow(self.h.wf)
        self.assertEqual(planmod.validate(wf).errors, [])
        self.assertTrue(planmod.validate(wf, for_approval=True).errors)


class CliMiscTest(unittest.TestCase):
    def test_one_workflow_per_session(self) -> None:
        h = Harness()
        try:
            h.init()
            out = h.orch("init", str(h.tmp / "plans"), "--title", "second", "--kind", "code", expect=2)
            self.assertIn("already drives", out)
        finally:
            h.close()

    def test_non_git_workspace_end_to_end_snapshot(self) -> None:
        h = Harness(git_workspace=False)
        try:
            h.init()
            out = h.orch("snapshot", "--workspace", "code")
            self.assertTrue(out.strip().startswith("s:"))
        finally:
            h.close()


if __name__ == "__main__":
    unittest.main()
