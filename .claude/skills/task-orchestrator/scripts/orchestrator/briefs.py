"""Dispatch briefs: the uniform prompt the orchestrator hands a roster agent.

A brief carries (1) the identity values the agent must echo in its result
block, (2) the files it must read in full — paths, never paraphrases, so every
agent works from the same full-fidelity context, (3) what its stage must
produce, and (4) its report path and result-block template. Each brief is
saved beside the reports it produces so the project-manager can audit whether
an agent was asked the right thing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import ops
from . import plan as planmod
from .common import ORCH_CLI, QUALITY_MANDATE, OrchError, write_text_atomic
from .gates import Context, final_workspaces, loop_tasks
from .roster import (
    AUTHORS,
    LIAISONS,
    RESEARCHERS,
    REVIEWERS,
    STAGES,
)

ORCH = f'python3 "{ORCH_CLI}"'

TASK_STAGES = {"readiness", "pm-start", "work", "fix", "pm-scope", "verification", "review", "pm-accept", "pm-resolution"}
LOOP_STAGES = {"pm-loop-entry", "pm-loop-exit"}
FINAL_STAGES = {"final-review", "final-fix", "final-verification", "pm-final"}
PLAN_STAGES = {"research", "pm-research", "plan", "test-plan", "plan-review", "pm-plan", "selftest"}
EVALUATING = {"pm-scope", "verification", "review", "pm-accept"}


# ---------------------------------------------------------------- stage text

def _work_text(agent: str, spec: planmod.TaskSpec) -> str:
    tid = spec.id
    if agent == "test-author":
        if spec.type == "test":
            return (
                "Write the tests this task specifies (its `## Test plan`), following the repository's "
                "existing test patterns. They characterize current behavior, so they must pass; a test "
                "that fails exposes a real defect — report it (status needs_input) instead of bending "
                "the test. Do not modify production code."
            )
        if spec.test_forward == "characterization":
            return (
                "Write characterization tests FIRST, before any production change: they pin today's "
                "behavior so the change can be proven safe. They must pass now. Then run "
                f"`{ORCH} evidence {tid} baseline` and include its log paths. Do not modify production code."
            )
        return (
            "TEST-FORWARD: write the tests from the task's `## Test plan` FIRST, before any production "
            "code exists. Each test must fail now for the RIGHT reason (the behavior is missing — not a "
            f"typo, not a missing import you could have added). Then run `{ORCH} evidence {tid} red` and, in "
            "your report, explain for each failing test why its failure is the expected one. Do not write "
            "or modify production code."
        )
    if agent == "code-author":
        return (
            "Implement the task so the tests written in this attempt pass without weakening them. Read "
            "test-author's work report and the red/baseline evidence first. Do not edit test files written "
            "in this attempt; if a test is wrong, stop and report it as a dispute (status needs_input) so "
            "test-author can fix it. Run the task's validation commands yourself before you finish."
        )
    if agent in RESEARCHERS:
        return (
            "Investigate what the task asks and write a complete, evidence-grounded findings report. "
            "Your report is the input doc-author turns into the deliverable, so include every fact, "
            "source, file:line reference, and uncertainty the deliverable needs."
        )
    if agent in LIAISONS:
        return (
            "Perform the external-system work the task describes. Reads need no approval. For ANY write: "
            "first run it with `--dry-run` and report the exact request, finishing with "
            "`\"external_action\": \"dry-run\"`; you will be resumed after the human confirms, and only "
            "then execute it and finish with `\"external_action\": \"executed\"`."
        )
    if agent == "doc-author" and spec.type == "research":
        return (
            "Turn the researcher's findings report (listed below) into the deliverable document the task "
            "specifies. Every claim must trace to the findings or to a source you verified yourself."
        )
    return (
        "Produce the deliverable exactly as the task specifies — every in-scope item, nothing out of "
        "scope. Ground every factual claim in its source. Run the task's validation commands before "
        "you finish."
    )


STAGE_TEXT: Dict[str, str] = {
    "readiness": (
        "MODE: readiness (task start verification). Decide whether this task can be worked NOW and has "
        "everything it needs: a complete, unambiguous task document (goal, in/out of scope, every "
        "acceptance criterion objective with a `Verified by`); dependencies ACCEPTED and their outputs "
        "present; validation commands runnable (paths/packages/tools exist); for red-green, the named "
        "tests do not already exist or pass. Establish the baseline: run "
        f"`{ORCH} gate run standard --task {{task}} --label baseline` and record any pre-existing failure. "
        "verdict pass = ready. verdict fail = not ready; classify every blocker as plan-defect, "
        "environment, dependency, or missing-input."
    ),
    "pm-start": (
        "MODE: start check. Before any work begins, confirm the process is set up correctly: the "
        "readiness report is sound and covered what it should; this is the right next task (dependencies "
        "accepted, loop open); authors and reviewers follow the task-type rules; the test-forward mode is "
        "right and justified; decisions.md entries that affect this task are reflected; a previous "
        "attempt's rejection findings (if any) are addressed. Do not re-do the readiness check — audit it."
    ),
    "fix": (
        "FIX ROUND {round}. Address EVERY blocking finding in the failing reports listed below "
        "(verification, reviews, PM). For each finding, report `fixed` (what changed, where) or "
        "`disputed` (concrete evidence it is wrong). Never weaken a test, an assertion, or a criterion to "
        "make a finding go away, and make no unrelated changes. Re-run the task's validation commands."
    ),
    "pm-scope": (
        "MODE: scope check (after an author pass, round {round}). Compare what the author CLAIMS "
        "(its report) with what ACTUALLY changed (changes.patch, changed-files.txt, scan.md). Fail on: "
        "significant unplanned work, out-of-scope files, weakened tests or criteria, findings claimed "
        "fixed that are not, disputes without evidence, or a test-forward sequence that was not followed."
    ),
    "verification": (
        "MODE: completion verification. Independently establish whether EVERY acceptance criterion is "
        "met at snapshot {snapshot}. Run `{orch} evidence {task} green` (test-forward tasks) and "
        "`{orch} gate run standard --task {task}` yourself. For each criterion record met true/false and "
        "concrete evidence (test name + what it asserts, command + result, file:line). Confirm the tests "
        "actually prove the criteria (not tautological, not asserting reachability only). Adjudicate "
        "every scan hit in scan.md as justified (cite the task/plan text) or violation. verdict pass only "
        "if every criterion is met with evidence and every gate is green."
    ),
    "review": (
        "Review ONLY this task's changes — the files in changed-files.txt / changes.patch. Other "
        "uncommitted work in the tree is context, not a review target. A finding is BLOCKING when its "
        "confidence is >= 85; record lower-confidence findings as non-blocking. If the author disputed "
        "earlier findings (see fix reports), rule on each dispute: withdraw it, or maintain it with "
        "evidence. verdict pass = zero blocking findings."
    ),
    "pm-accept": (
        "MODE: acceptance stamp — the external viewpoint. Did the work do what the task and plan asked, "
        "all of it and nothing else? Were the quality gates real and green at this snapshot? Did every "
        "reviewer review what it should have (right scope, right lens)? Were disputes resolved on "
        "evidence? Is every scan hit adjudicated and every non-blocking finding acceptable? Cite the scan "
        "digest you adjudicated in `scan_digest`."
    ),
    "pm-resolution": (
        "MODE: resolution review. This task exhausted its attempt budget. Review the orchestrator's "
        "resolution guidance (runs/{task}/resolution.orchestrator.md) against the full run history: does "
        "it diagnose the real root cause, propose a resolution that meets the task WITHOUT lowering the "
        "bar, and name what the human must decide? verdict pass = ready to put to the human."
    ),
    "pm-loop-entry": (
        "MODE: loop-entry check for loop {loop}. Confirm this loop's task set is ready to run: the prior "
        "loop closed cleanly; every task's dependencies are satisfied by accepted work or ordered within "
        "the loop; tasks marked parallel_safe really have disjoint expected_paths; decisions.md does not "
        "change any of these tasks' scope; nothing learned so far invalidates the plan."
    ),
    "pm-loop-exit": (
        "MODE: loop-exit check for loop {loop}. Every task is accepted — now judge the loop as a whole: "
        "read the loop diff; attribute every changed file to a task (flag unattributed changes); confirm "
        "the loop-level gate is green at this snapshot; look for cross-task inconsistencies and "
        "integration gaps; confirm status/index documents tell the truth."
    ),
    "final-review": (
        "Whole-package review, round {round}. Review the cumulative change (final/changes-*.patch) as ONE "
        "integrated change: integration defects across task boundaries, inconsistencies, regressions, "
        "dead or obsolete code, incomplete cleanup, missing regression coverage, accidental scope "
        "expansion. A finding is BLOCKING when its confidence is >= 85."
    ),
    "final-fix": (
        "FINAL FIX ROUND {round}. Address every blocking finding in the final-review / final-verification "
        "/ PM reports listed below that falls in your area. For each: fixed or disputed (with evidence). "
        "No unrelated changes, no weakening."
    ),
    "final-verification": (
        "MODE: final verification. Verify EVERY final acceptance criterion (FAC*) in plan.md at snapshot "
        "{snapshot}: run `{orch} gate run final --final --workspace <each workspace>` yourself and map "
        "each FAC to concrete evidence. verdict pass only if every FAC is met with evidence and every "
        "final gate is green."
    ),
    "pm-final": (
        "MODE: final acceptance. Trace every requirement (R*) and final criterion (FAC*) in plan.md to "
        "delivered, verified work; confirm every task was accepted on real evidence; confirm the final "
        "reviews and gates are green at this snapshot; list every recorded non-blocking concern the human "
        "should know about. Add a short 'Process observations' section: what in this process helped or "
        "got in the way."
    ),
    "research": (
        "Research topic: {topic}. Produce a complete, evidence-grounded research document the planner "
        "can build a plan from: facts with sources (file:line for code, URL/ticket for external), what "
        "exists today, constraints, risks, open questions, and what you could not confirm."
    ),
    "pm-research": (
        "MODE: research-sufficiency check. Read request.md and every research document. Is the research "
        "enough to write a plan with evidence-grounded claims, objective acceptance criteria, and no "
        "guessing? Name any missing research precisely (what question, which agent should answer it)."
    ),
    "plan": (
        "Write (or revise) the plan package in the workflow directory, following the task-orchestrator "
        "plan-package reference exactly: plan.md, architecture.md (when warranted), gate.json, and "
        "tasks/T###-<slug>.md. Ground every claim about existing code in file:line evidence from the "
        "research. Every requirement traces to tasks; every task has objective acceptance criteria with "
        "`Verified by`; code tasks are test-forward. Run `{orch} validate` and fix every error before you "
        "finish. {revision_note}"
    ),
    "test-plan": (
        "Run the /eng-test-planning skill against {plan} so it appends the `## Test plan` section, then "
        "make sure every code/test task document's `## Test plan` section carries its specific test "
        "cases. Unit-first, value-justified, reliable, self-cleaning tests only."
    ),
    "plan-review": (
        "Review the plan package ({mode_hint}). Findings with confidence >= 85 are blocking. Report "
        "`plan_hash` exactly as given — it pins which version of the plan you reviewed."
    ),
    "pm-plan": (
        "MODE: plan audit — the gate before the human sees the plan. Check: every requirement traced to "
        "tasks; every task has objective, checkable acceptance criteria with `Verified by`; task size "
        "<= 1.5 days; code tasks are test-forward with real test plans; reviewers meet type minimums; "
        "loops are ordered correctly; open questions are all surfaced; plan reviews were addressed; nothing "
        "in the plan quietly shrinks what the request asked for. Report `plan_hash` exactly as given."
    ),
    "selftest": (
        "SELFTEST. Do not do real work. (1) Say whether your context contains the text "
        "'TASK-ORCHESTRATOR CONTRACT' (injected by the SubagentStart hook) — set `contract_seen` true or "
        "false. (2) Write a one-line report to the report path. (3) Finish with the result block."
    ),
}


def _template(fields: Dict[str, Any]) -> str:
    return "```orch-result\n" + json.dumps(fields, indent=2) + "\n```"


def _next_number(folder: Path) -> int:
    briefs = folder / "briefs"
    return (len(list(briefs.glob("*.md"))) if briefs.is_dir() else 0) + 1


REPORT_NAME_RE = re.compile(r"^\d+-[a-z0-9-]+\.[a-z-]+\.md$")


def _existing_reports(folder: Path) -> List[Path]:
    """Agent reports only (`<nn>-<stage>.<agent>.md`), in dispatch order."""
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.glob("*.md") if REPORT_NAME_RE.match(p.name))


# ---------------------------------------------------------------- builder

def build(
    ctx: Context,
    stage: str,
    agent: str,
    task_id: Optional[str] = None,
    loop: Optional[int] = None,
    topic: Optional[str] = None,
    note: Optional[str] = None,
    mode_hint: Optional[str] = None,
) -> Tuple[str, Path]:
    spec_stage = STAGES.get(stage)
    if spec_stage is None:
        raise OrchError(f"unknown stage `{stage}`")
    if agent not in spec_stage["agents"]:
        allowed = ", ".join(sorted(spec_stage["agents"]))
        raise OrchError(f"agent `{agent}` cannot perform stage `{stage}` (allowed: {allowed})")
    state = ctx.state
    wf = ctx.wf
    fields: Dict[str, Any] = {
        "workflow": state["workflow_id"],
        "stage": stage,
        "status": "complete | needs_input | blocked",
        "verdict": "n/a" if stage not in {"readiness", "verification", "review", "final-review",
                                         "final-verification", "plan-review"} and not stage.startswith("pm-")
        else "pass | fail",
    }
    read: List[str] = [f"{wf.decisions}  (binding clarifications and human decisions)"]
    extra: List[str] = []
    fmt: Dict[str, Any] = {"orch": ORCH, "task": task_id or "", "loop": loop or "", "round": 0,
                           "snapshot": "", "topic": topic or "(given by the orchestrator below)",
                           "plan": str(wf.plan), "mode_hint": mode_hint or "", "revision_note": ""}

    if stage in TASK_STAGES:
        if not task_id:
            raise OrchError(f"stage `{stage}` needs a task id")
        spec = ctx.spec(task_id)
        info = ops.task_state(ctx, task_id)
        attempt = int(info.get("attempt") or 0)
        if info.get("status") not in ("IN_PROGRESS", "BLOCKED"):
            raise OrchError(f"task {task_id} is {info.get('status')}; start it first")
        rnd = int(info.get("round") or 0)
        folder = wf.run_dir(task_id, attempt)
        fmt.update(round=rnd)
        fields.update(task=task_id, attempt=attempt)
        if stage in ("work", "fix", "pm-scope", "verification", "review"):
            fields["round"] = rnd
        ws_path = ctx.ws_path(spec.workspace)
        extra.append(
            f"- Task: **{task_id} — {spec.title}** (type `{spec.type}`, loop {spec.loop}, attempt {attempt}, "
            f"round {rnd}, test-forward `{spec.test_forward}`)"
        )
        extra.append(f"- Workspace `{spec.workspace}`: `{ws_path}`")
        if spec.expected_paths:
            extra.append(f"- Expected paths: {', '.join(f'`{p}`' for p in spec.expected_paths)}")
        read += [f"{spec.path}  (the task — the contract for this work)", f"{wf.plan}", f"{wf.request}"]
        if wf.architecture.exists():
            read.append(f"{wf.architecture}")
        prior = _existing_reports(folder)
        read += [f"{p}  (earlier stage in this attempt)" for p in prior]
        if attempt > 1:
            prev = wf.run_dir(task_id, attempt - 1)
            read += [f"{p}  (previous attempt)" for p in _existing_reports(prev) if "pm-accept" in p.name or "pm-scope" in p.name]
        if stage in EVALUATING or stage == "fix":
            diff = ops.write_task_diff(ctx, task_id)
            read += [f"{diff['files']}  (files changed by this task)", f"{diff['patch']}  (the task diff)"]
            if stage in ("verification", "pm-accept", "pm-scope"):
                scan = ops.run_task_scan(ctx, task_id)
                read.append(f"{scan['report']}  (integrity scan — digest {scan['digest']})")
                if stage == "pm-accept":
                    fields["scan_digest"] = scan["digest"]
            fields["snapshot"] = diff["snapshot"]
            fmt["snapshot"] = diff["snapshot"]
        if stage == "readiness":
            deps = [ctx.spec(d) for d in spec.depends_on]
            for dep in deps:
                read.append(f"{dep.path}  (dependency {dep.id})")
        if stage == "work":
            text = _work_text(agent, spec)
            if agent == "doc-author" and spec.type == "research":
                findings = [p for p in prior if ".codebase-researcher." in p.name or ".domain-researcher." in p.name]
                if not findings:
                    raise OrchError("dispatch the researcher's work stage before doc-author")
        elif stage == "fix":
            text = STAGE_TEXT["fix"].format(**fmt)
            failing = [p for p in prior if any(k in p.name for k in ("verification", "review", "pm-scope", "pm-accept"))]
            extra.append("- Failing reports to address are among the earlier-stage files listed below "
                         "(latest verification / review / PM reports).")
            del failing
        elif stage == "review":
            text = STAGE_TEXT["review"]
            if agent == "code-reviewer":
                text += (
                    f" Invoke /reviewomatic with args: `local --confidence=80 -- scope is fixed to the task "
                    f"diff in {folder / 'changes.patch'} (files: {folder / 'changed-files.txt'}); raise findings "
                    f"only on those changes; other working-tree changes are context only; do not ask about scope`."
                )
        else:
            text = STAGE_TEXT[stage].format(**fmt)
        if agent in AUTHORS and stage in ("work", "fix"):
            fields["changed_files"] = ["<workspace-relative paths you changed>"]
        if agent in LIAISONS and stage == "work":
            fields["external_action"] = "none | dry-run | executed"
        if stage == "verification":
            fields["criteria"] = [{"id": c.id, "met": "true | false", "evidence": "<concrete evidence>"}
                                  for c in spec.criteria]
        if stage == "review":
            fields["findings"] = {"blocking": "<int>", "recorded": "<int>", "disputes_ruled": "<int>"}
        if stage == "readiness":
            fields["blockers"] = ["<plan-defect|environment|dependency|missing-input: detail>"]
        if stage == "pm-resolution":
            guidance = wf.runs_dir / task_id / "resolution.orchestrator.md"
            if not guidance.exists():
                raise OrchError(f"write {guidance} before requesting pm-resolution")
            read.append(f"{guidance}  (the guidance under review)")
            for attempt_dir in sorted((wf.runs_dir / task_id).glob("a*")):
                read += [f"{p}  ({attempt_dir.name})" for p in _existing_reports(attempt_dir)]
    elif stage in LOOP_STAGES:
        if not loop:
            raise OrchError(f"stage `{stage}` needs --loop N")
        folder = wf.loop_dir(loop)
        fields["loop"] = loop
        specs = loop_tasks(ctx, loop)
        extra.append(f"- Loop {loop} tasks: " + ", ".join(f"{s.id} ({s.type}, deps {s.depends_on or '—'})" for s in specs))
        read += [f"{wf.plan}", f"{wf.tasks_dir / 'index.md'}"] + [f"{s.path}" for s in specs]
        if stage == "pm-loop-exit":
            starts = (state.get("loops") or {}).get(str(loop), {}).get("start_snapshots") or {}
            info = ops.write_range_diffs(ctx, folder, starts, sorted({s.workspace for s in specs}), "loop-exit")
            fields["snapshot"] = info["composite"]
            read += [f"{p}  (loop diff)" for p in info["patches"].values()]
            for s in specs:
                runs = wf.runs_dir / s.id
                read += [f"{p}" for p in sorted(runs.glob("a*/[0-9]*-pm-accept*.md"))]
            gate_dir = folder / "gate"
            if gate_dir.is_dir():
                read += [f"{p}  (loop gate log)" for p in sorted(gate_dir.glob("*.log"))]
        text = STAGE_TEXT[stage].format(**fmt)
    elif stage in FINAL_STAGES:
        final = state.get("final") or {}
        if final.get("status") != "OPEN":
            raise OrchError("final review is not open; run `orch final start`")
        folder = wf.final_dir
        rnd = int(final.get("round") or 0)
        fmt["round"] = rnd
        fields["round"] = rnd
        starts = {k: v.get("snapshot") for k, v in (state.get("baselines") or {}).items()}
        info = ops.write_range_diffs(ctx, folder, starts, final_workspaces(ctx), "final")
        if stage != "final-fix":
            fields["snapshot"] = info["composite"]
            fmt["snapshot"] = info["composite"]
        read += [f"{wf.request}", f"{wf.plan}", f"{wf.tasks_dir / 'index.md'}"]
        read += [f"{p}  (cumulative diff)" for p in info["patches"].values()]
        read += [f"{p}  (earlier final-stage report)" for p in _existing_reports(folder)]
        if stage in ("final-review",) and agent in REVIEWERS:
            fields["findings"] = {"blocking": "<int>", "recorded": "<int>", "disputes_ruled": "<int>"}
        if stage == "final-verification":
            fields["criteria"] = [{"id": f, "met": "true | false", "evidence": "<concrete evidence>"}
                                  for f in ctx.pkg.plan.final_criteria]
        text = STAGE_TEXT[stage].format(**fmt)
    else:  # planning + selftest
        folder = wf.research_dir if stage == "research" else wf.reviews_dir / ("selftest" if stage == "selftest" else "plan")
        rev = int(state.get("plan_revision") or 1)
        if stage in ("plan", "test-plan", "plan-review"):
            fields["plan_revision"] = rev
        if stage in ("plan-review", "pm-plan"):
            fields["plan_hash"] = planmod.plan_hash(wf)
        read += [f"{wf.request}  (the request, verbatim)"]
        if stage != "research":
            read.append(f"{wf.research_dir / 'index.md'}  (research inputs — read every linked document)")
        if stage in ("test-plan", "plan-review", "pm-plan", "plan"):
            read += [f"{wf.plan}", f"{wf.gate}", f"{wf.tasks_dir}/T*.md (every task document)"]
            if wf.architecture.exists():
                read.append(f"{wf.architecture}")
            read += [f"{p}  (earlier plan-stage report)" for p in _existing_reports(wf.reviews_dir / "plan")]
        if stage == "plan" and rev > 1:
            fmt["revision_note"] = (f"This is plan revision {rev}: apply the human's revision request "
                                    "recorded at the end of decisions.md, and nothing else.")
        if stage == "research" and not topic:
            raise OrchError("research briefs need --topic")
        if stage == "selftest":
            fields["contract_seen"] = "true | false"
        text = STAGE_TEXT[stage].format(**fmt)

    number = _next_number(folder)
    stem = stage if stage in PLAN_STAGES or stage in LOOP_STAGES else f"{stage}-r{fmt['round']}"
    if stage == "research" and topic:
        from .common import slugify
        stem = f"research-{slugify(topic, 32)}"
    report = folder / f"{number:02d}-{stem}.{agent}.md"
    fields["report"] = str(report)
    if stage == "pm-accept":
        fields.setdefault("scan_digest", "")

    lines = [
        f"# Dispatch brief — `{stage}` · `{agent}`",
        "",
        f"You are the `{agent}` roster agent in task-orchestrator workflow `{state['workflow_id']}` "
        f"(directory `{wf.root}`).",
        "",
        QUALITY_MANDATE,
        "",
        "## Identity — copy these values into your result block",
        "",
        f"- workflow: `{state['workflow_id']}`",
        f"- stage: `{stage}`",
    ]
    for key in ("task", "attempt", "round", "loop", "snapshot", "plan_revision", "plan_hash", "scan_digest"):
        if key in fields and not str(fields[key]).startswith("<"):
            lines.append(f"- {key}: `{fields[key]}`")
    lines += extra
    lines += ["", "## Read these in full before you start", ""]
    lines += [f"- {item}" for item in read]
    lines += ["", "## What this stage must produce", "", text]
    if note:
        lines += ["", "## Orchestrator notes for this dispatch", "", note]
    lines += [
        "",
        "## Rules that always apply",
        "",
        "- You cannot talk to the user. If you need input, finish with `status: needs_input` and list the "
        "questions in your report; you will be resumed with answers.",
        "- Write only your report file (below) inside the workflow directory. Never edit `.orch/`, the plan "
        "documents, generated index files, or another agent's report.",
        "- If what you find contradicts the plan, do not work around it: say so, and finish with "
        "`status: blocked` and a `deviations` list.",
        "",
        "## Finish",
        "",
        f"Write your full report to `{report}`. Then finish with this block, every placeholder replaced "
        "(booleans as JSON true/false, counts as integers). If you hand back with SubagentHandback, end "
        "that message with the block; either way, also end your final text message with it:",
        "",
        _template(fields),
        "",
    ]
    text_out = "\n".join(lines)
    write_text_atomic(folder / "briefs" / f"{number:02d}-{stem}.{agent}.md", text_out)
    return text_out, report
