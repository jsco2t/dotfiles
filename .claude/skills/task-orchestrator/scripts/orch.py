#!/usr/bin/env python3
"""orch — the task-orchestrator state CLI.

Owns all workflow state. The model never edits state by hand: a PreToolUse
hook blocks direct edits of <workflow>/.orch/, and every transition below
refuses to run until its gate checklist is met. Run `orch <command> -h`.

Python 3.9+, stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from orchestrator import briefs, gates, ledger, ops, render  # noqa: E402
from orchestrator import plan as planmod  # noqa: E402
from orchestrator import snapshot as snapmod  # noqa: E402
from orchestrator.common import (  # noqa: E402
    ORCH_CLI,
    SCHEMA,
    OrchError,
    Workflow,
    clear_binding,
    current_session_id,
    file_lock,
    get_binding,
    list_bindings,
    orch_home,
    read_json,
    resolve_workflow,
    set_binding,
    slugify,
    today,
    utcnow,
    write_json_atomic,
    write_text_atomic,
)
from orchestrator.roster import (  # noqa: E402
    AGENTS,
    DEFAULT_BUDGETS,
    RESOLVE_ACTIONS,
    ROSTER,
)

HOOK_EVENTS = ("SessionStart", "UserPromptSubmit", "UserPromptExpansion", "PreToolUse", "SubagentStart",
               "SubagentStop", "Stop")


# ================================================================ helpers


def out(text: str = "") -> None:
    print(text)


def state_lock(wf: Workflow):
    return file_lock(wf.control / "state.lock")


def transition(wf: Workflow, what: str, to: str, **fields: Any) -> Dict[str, Any]:
    entry = {"kind": "transition", "what": what, "to": to}
    entry.update({k: v for k, v in fields.items() if v is not None})
    return ledger.append(wf, entry)


def safe_render(wf: Workflow) -> None:
    try:
        render.render_all(wf)
    except Exception as exc:  # never fail a command because of rendering
        print(f"(note: index rendering failed: {exc})", file=sys.stderr)


def append_decision(wf: Workflow, source: str, text: str) -> None:
    existing = wf.decisions.read_text(encoding="utf-8") if wf.decisions.exists() else "# Decisions log\n"
    block = f"\n## {utcnow()} — {source}\n\n{text.strip()}\n"
    write_text_atomic(wf.decisions, existing.rstrip("\n") + "\n" + block)


def require_phase(state: Dict[str, Any], *phases: str) -> None:
    if state.get("phase") not in phases:
        raise OrchError(f"workflow phase is {state.get('phase')}; this needs {' or '.join(phases)}")


def print_reqs(reqs: List[gates.Req]) -> None:
    for req in reqs:
        out("  " + req.line())
    req = gates.first_unmet(reqs)
    if req:
        out(f"NEXT: {req.label}: {req.action}")


def consume(wf: Workflow, token: Dict[str, Any], by: str) -> None:
    ledger.append(wf, {"kind": "consume", "ref": token["seq"], "by": by})


def human_token(entries, verb: str, after: Optional[str], action: Optional[str] = None,
                task: Optional[str] = None) -> Optional[Dict[str, Any]]:
    def matches(entry: Dict[str, Any]) -> bool:
        args = [a.strip(",.;:").upper() if re.match(r"^[tT]\d+", a) else a.strip(",.;:").lower()
                for a in entry.get("args") or []]
        if action and (not args or args[0] != action):
            return False
        if task and task.upper() not in args:
            return False
        return True
    return ledger.find_human_token(entries, verb, after_ts=after, predicate=matches)


# ================================================================ lifecycle


def cmd_init(args: argparse.Namespace) -> int:
    session = current_session_id()
    if not session and not args.no_bind:
        raise OrchError("CLAUDE_CODE_SESSION_ID is not set; run this from a Claude Code session")
    if session and not args.no_bind:
        bound = get_binding(session)
        if bound and Workflow(Path(bound["workflow_dir"])).exists():
            other = Workflow(Path(bound["workflow_dir"])).load_state()
            if other.get("phase") != "CLOSED":
                raise OrchError(
                    f"this session already drives workflow {other.get('workflow_id')} ({bound['workflow_dir']}); "
                    "a session drives one workflow at a time"
                )
    root = Path(args.plan_root).expanduser().resolve()
    base = f"{today()}-{slugify(args.slug or args.title)}"
    candidate, n = base, 2
    while (root / candidate).exists():
        candidate, n = f"{base}-{n:02d}", n + 1
    wf = Workflow(root / candidate)
    try:
        for folder in (wf.control, wf.tasks_dir, wf.research_dir, wf.reviews_dir / "plan", wf.runs_dir,
                       wf.loops_dir, wf.final_dir):
            folder.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        raise OrchError(
            f"cannot create {wf.root}: {exc}. The Claude Code Bash sandbox may not allow writes there; "
            "choose a location inside the project or add it to sandbox.filesystem.allowWrite"
        ) from exc
    workspaces: Dict[str, Any] = {}
    for item in args.workspace or []:
        if "=" not in item:
            raise OrchError(f"--workspace takes name=path, got {item!r}")
        name, path = item.split("=", 1)
        ws = Path(path).expanduser().resolve()
        if not ws.is_dir():
            raise OrchError(f"workspace path {ws} is not a directory")
        workspaces[name.strip()] = {"path": str(ws), "standard": [], "final": [], "snapshot_exclude": [], "notes": ""}
    write_json_atomic(wf.gate, {"schema": SCHEMA, "workspaces": workspaces})
    if args.request_file:
        text = Path(args.request_file).expanduser().read_text(encoding="utf-8")
        write_text_atomic(wf.request, text if text.endswith("\n") else text + "\n")
    else:
        write_text_atomic(wf.request, "")
    write_text_atomic(wf.decisions, f"# Decisions log — {args.title}\n\nAppend-only. Written by `orch note` and `orch resolve`.\n")
    state = {
        "schema": SCHEMA,
        "workflow_id": candidate,
        "title": args.title,
        "workflow_dir": str(wf.root),
        "created_at": utcnow(),
        "updated_at": utcnow(),
        "phase": "PLANNING",
        "resume_phase": None,
        "iteration": 1,
        "plan_revision": 1,
        "submitted_plan_sha256": None,
        "submitted_at": None,
        "approved_plan_sha256": None,
        "approved_at": None,
        "approved_seq": None,
        "completed_at": None,
        "closed_at": None,
        "baselines": {},
        "tasks": {},
        "loops": {},
        "final": {"status": "PENDING", "round": 0, "budget": DEFAULT_BUDGETS["final_review_passes"]},
        "budgets": dict(DEFAULT_BUDGETS),
        "needs_human": None,
        "halt_requested": False,
        "block_reason": None,
        "stop_continuations": 0,
        "max_stop_continuations": 150,
        "last_wait": None,
        "max_consecutive_waits": 40,
        "revision_history": [],
        "session_id": None if args.no_bind else session,
    }
    wf.save_state(state)
    transition(wf, "workflow", "PLANNING", title=args.title)
    if session and not args.no_bind:
        set_binding(session, wf.root, candidate)
    safe_render(wf)
    out(str(wf.root))
    out(f"Workflow {candidate} initialized (phase PLANNING). Write the verbatim request to {wf.request} "
        "if --request-file was not given, then follow the planning stage.")
    return 0


def cmd_bind(args: argparse.Namespace) -> int:
    session = current_session_id()
    if not session:
        raise OrchError("CLAUDE_CODE_SESSION_ID is not set")
    wf = resolve_workflow(args.workflow_dir)
    bound = get_binding(session)
    if bound and Path(bound["workflow_dir"]).resolve() != wf.root:
        raise OrchError(f"this session already drives {bound['workflow_dir']}; `orch unbind` first")
    with state_lock(wf):
        state = wf.load_state()
        previous = state.get("session_id")
        if previous and previous != session:
            clear_binding(previous)
        state["session_id"] = session
        wf.save_state(state)
    set_binding(session, wf.root, state["workflow_id"])
    transition(wf, "binding", session, previous=previous)
    out(f"Session bound to {state['workflow_id']} ({wf.root}), phase {state['phase']}.")
    return 0


def cmd_unbind(args: argparse.Namespace) -> int:
    session = current_session_id()
    if session:
        clear_binding(session)
    out("Session unbound.")
    return 0


def cmd_where(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    out(str(wf.root))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    ctx = gates.Context(wf, fast=args.fast)
    state = ctx.state
    if args.json:
        out(json.dumps(state, indent=2))
        return 0
    if args.task:
        out(f"{args.task} — {ctx.spec(args.task).title}")
        print_reqs(gates.task_checklist(ctx, args.task))
        return 0
    out(f"{state['workflow_id']} — {state['title']}")
    out(f"phase {state['phase']} · iteration {state.get('iteration')} · plan revision {state.get('plan_revision')}")
    out(f"directory {wf.root}")
    if state.get("tasks"):
        counts: Dict[str, int] = {}
        for info in state["tasks"].values():
            counts[info["status"]] = counts.get(info["status"], 0) + 1
        out("tasks " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    out("NEXT: " + gates.next_action(ctx))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    state = wf.load_state()
    pkg = planmod.validate(wf, state, for_approval=args.for_approval)
    for warning in pkg.warnings:
        out(f"warning: {warning}")
    for error in pkg.errors:
        out(f"error: {error}")
    out(f"{len(pkg.errors)} error(s), {len(pkg.warnings)} warning(s); {len(pkg.tasks)} task(s); plan hash {planmod.plan_hash(wf)}")
    return 1 if pkg.errors else 0


def cmd_plan_hash(args: argparse.Namespace) -> int:
    out(planmod.plan_hash(resolve_workflow(args.wf)))
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    render.render_all(wf)
    out(f"rendered {wf.root / 'index.md'}")
    return 0


# ================================================================ planning -> approval


def cmd_submit(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    with state_lock(wf):
        ctx = gates.Context(wf)
        state = ctx.state
        require_phase(state, "PLANNING")
        current = planmod.plan_hash(wf)
        reqs = [r for r in gates.planning_checklist(ctx, current) if r.key != "submit"]
        if gates.first_unmet(reqs):
            out("Cannot submit the plan yet:")
            print_reqs(reqs)
            return 1
        state["submitted_plan_sha256"] = current
        state["submitted_at"] = utcnow()
        state["phase"] = "AWAITING_APPROVAL"
        wf.save_state(state)
    transition(wf, "workflow", "AWAITING_APPROVAL", plan_hash=current)
    safe_render(wf)
    pkg = planmod.validate(wf, state, for_approval=True)
    open_q = [q for q in pkg.plan.questions if not q["resolved"]]
    out(f"Plan submitted for approval (hash {current[:12]}). Present {wf.root / 'index.md'} to the human.")
    if open_q:
        out("Unresolved open questions (approval is blocked until the human answers them):")
        for q in open_q:
            out(f"  {q['id']}: {q['text']}")
    out("The human approves by typing `/task-orchestrator approve` (or revises with `/task-orchestrator revise <feedback>`).")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    with state_lock(wf):
        ctx = gates.Context(wf)
        state = ctx.state
        require_phase(state, "AWAITING_APPROVAL")
        pkg = planmod.validate(wf, state, for_approval=True)
        if pkg.errors:
            out("Cannot approve — the plan package does not validate for approval:")
            for error in pkg.errors:
                out(f"  error: {error}")
            return 1
        current = planmod.plan_hash(wf)
        if current != state.get("submitted_plan_sha256"):
            raise OrchError("the plan changed after it was submitted; it must go back through the planning "
                            "checklist (`/task-orchestrator revise`) before approval")
        pm = ctx.latest_result("pm-plan")
        if not (pm and gates._passed(pm) and (pm.get("result") or {}).get("plan_hash") == current):
            raise OrchError("no passing PM plan audit for this exact plan")
        token = human_token(ctx.entries, "approve", state.get("submitted_at"))
        if token is None:
            raise OrchError("no human approval recorded. Approval must come from the human typing "
                            "`/task-orchestrator approve` after the plan was submitted — never infer it")
        closed_loops = {int(k) for k, v in (state.get("loops") or {}).items() if v.get("status") == "CLOSED"}
        for spec in pkg.tasks.values():
            if spec.id not in (state.get("tasks") or {}) and spec.loop in closed_loops:
                raise OrchError(f"new task {spec.id} is in loop {spec.loop}, which is already closed")
        consume(wf, token, "approve")
        baselines = dict(state.get("baselines") or {})
        for name in planmod.gate_workspaces(pkg.gate):
            if name in baselines:
                continue
            snap = ctx.take(name)
            ops.record_snapshot(ctx, snap, "baseline")
            head = None
            if snap.mode == "git":
                head = snapmod._run_git(["rev-parse", "HEAD"], Path(snap.toplevel), check=False).strip() or None
            baselines[name] = {"snapshot": snap.to_dict(), "head": head, "at": utcnow()}
        tasks = dict(state.get("tasks") or {})
        budgets = state.get("budgets") or DEFAULT_BUDGETS
        for spec in pkg.ordered_tasks():
            info = tasks.get(spec.id)
            if info is None:
                tasks[spec.id] = {
                    "status": "PENDING",
                    "attempt": 0,
                    "attempt_budget": budgets["task_attempts"],
                    "round": 0,
                    "review_budget": budgets["review_passes"],
                    "loop": spec.loop,
                }
            elif info.get("status") != "ACCEPTED":
                info["status"] = "PENDING"
                info["loop"] = spec.loop
                if int(info.get("attempt") or 0) >= int(info.get("attempt_budget") or 0):
                    info["attempt_budget"] = int(info.get("attempt") or 0) + 1
        loops = dict(state.get("loops") or {})
        for loop in pkg.loops():
            loops.setdefault(str(loop), {"status": "PENDING"})
        state.update(
            tasks=tasks,
            loops=loops,
            baselines=baselines,
            approved_plan_sha256=current,
            approved_at=utcnow(),
            phase="EXECUTING",
            needs_human=None,
            block_reason=None,
            stop_continuations=0,
            halt_requested=False,
        )
        state["final"] = {"status": "PENDING", "round": 0, "budget": budgets["final_review_passes"]}
        wf.save_state(state)
        entry = transition(wf, "workflow", "EXECUTING", plan_hash=current, human_seq=token["seq"])
        state["approved_seq"] = entry["seq"]
        wf.save_state(state)
    safe_render(wf)
    out(f"Plan approved and frozen (hash {current[:12]}). Execution begins now — do not stop to ask.")
    out("NEXT: " + gates.next_action(gates.Context(wf, fast=True)))
    return 0


def cmd_revise(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    with state_lock(wf):
        ctx = gates.Context(wf)
        state = ctx.state
        require_phase(state, "AWAITING_APPROVAL", "PLAN_CHANGE_REQUIRED", "DONE", "NEEDS_HUMAN")
        after = {
            "AWAITING_APPROVAL": state.get("submitted_at"),
            "PLAN_CHANGE_REQUIRED": state.get("phase_since"),
            "DONE": state.get("completed_at"),
            "NEEDS_HUMAN": (state.get("needs_human") or {}).get("raised_at"),
        }.get(state["phase"]) or state.get("created_at")
        token = human_token(ctx.entries, "revise", after)
        if token is None:
            raise OrchError("no human revision request recorded; the human types `/task-orchestrator revise <feedback>`")
        consume(wf, token, "revise")
        feedback = " ".join(token.get("args") or []) or "(no feedback text)"
        if state["phase"] == "DONE":
            state.setdefault("revision_history", []).append(
                {"iteration": state.get("iteration", 1), "completed_at": state.get("completed_at"),
                 "reason": feedback})
            state["iteration"] = int(state.get("iteration", 1)) + 1
            state["completed_at"] = None
            state["final"] = {"status": "PENDING", "round": 0,
                              "budget": (state.get("budgets") or DEFAULT_BUDGETS)["final_review_passes"]}
        for info in (state.get("tasks") or {}).values():
            if info.get("status") == "IN_PROGRESS":
                info["status"] = "PENDING"
        state["plan_revision"] = int(state.get("plan_revision", 1)) + 1
        state.update(phase="PLANNING", needs_human=None, submitted_plan_sha256=None, block_reason=None,
                     resume_phase=None, phase_since=utcnow())
        wf.save_state(state)
    append_decision(wf, f"human revision request (plan revision {state['plan_revision']})", token.get("raw") or feedback)
    transition(wf, "workflow", "PLANNING", plan_revision=state["plan_revision"], human_seq=token["seq"])
    safe_render(wf)
    out(f"Revision {state['plan_revision']} opened. Resume planning-author with the feedback (recorded in decisions.md), "
        "re-run the plan reviews and PM audit, then `orch submit`.")
    return 0


# ================================================================ tasks


def _paths_overlap(a: List[str], b: List[str]) -> bool:
    for x in a:
        for y in b:
            x2, y2 = x.strip("/"), y.strip("/")
            if not x2 or not y2 or x2 == y2 or x2.startswith(y2 + "/") or y2.startswith(x2 + "/"):
                return True
    return False


def cmd_task(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    handler = {
        "start": task_start,
        "round": task_round,
        "accept": task_accept,
        "fail": task_fail,
        "diff": task_diff,
        "scan": task_scan,
        "status": task_status,
    }[args.task_cmd]
    return handler(wf, args)


def task_start(wf: Workflow, args: argparse.Namespace) -> int:
    tid = args.task_id.upper()
    with state_lock(wf):
        ctx = gates.Context(wf)
        state = ctx.state
        require_phase(state, "EXECUTING")
        spec = ctx.spec(tid)
        info = ops.task_state(ctx, tid)
        if info["status"] != "PENDING":
            raise OrchError(f"{tid} is {info['status']}")
        loop = (state.get("loops") or {}).get(str(spec.loop), {})
        if loop.get("status") != "OPEN":
            raise OrchError(f"loop {spec.loop} is not open (`orch loop open {spec.loop}` after its PM entry check)")
        waiting = [d for d in spec.depends_on if state["tasks"].get(d, {}).get("status") != "ACCEPTED"]
        if waiting:
            raise OrchError(f"{tid} depends on unaccepted task(s): {', '.join(waiting)}")
        others = [t for t, i in state["tasks"].items() if i.get("status") == "IN_PROGRESS"]
        for other in others:
            ospec = ctx.spec(other)
            if not (spec.parallel_safe and ospec.parallel_safe and ospec.loop == spec.loop):
                raise OrchError(f"{other} is in progress; writes are single-threaded unless both tasks are "
                                "parallel_safe document tasks in the same loop")
            if ospec.workspace == spec.workspace and _paths_overlap(spec.expected_paths, ospec.expected_paths):
                raise OrchError(f"{tid} and {other} have overlapping expected_paths; they cannot run in parallel")
        if int(info.get("attempt") or 0) >= int(info.get("attempt_budget") or 0):
            info["status"] = "BLOCKED"
            wf.save_state(state)
            raise OrchError(f"{tid} has used its attempt budget; it needs resolution guidance and a human decision")
        info["attempt"] = int(info.get("attempt") or 0) + 1
        info["round"] = 0
        info["review_budget"] = (state.get("budgets") or DEFAULT_BUDGETS)["review_passes"]
        info["status"] = "IN_PROGRESS"
        info["started_at"] = utcnow()
        wf.run_dir(tid, info["attempt"]).mkdir(parents=True, exist_ok=True)
        snap = ctx.take(spec.workspace, ctx.scope(spec))
        ops.record_snapshot(ctx, snap, "start", task=tid, attempt=info["attempt"])
        info["start_snapshot"] = snap.to_dict()
        entry = transition(wf, "task", "IN_PROGRESS", task=tid, attempt=info["attempt"])
        info["start_seq"] = entry["seq"]
        wf.save_state(state)
    safe_render(wf)
    out(f"{tid} attempt {info['attempt']} started at snapshot {snap.id}.")
    out(f"NEXT: `orch brief {tid} readiness --agent task-verifier`, then dispatch task-verifier.")
    return 0


def task_round(wf: Workflow, args: argparse.Namespace) -> int:
    tid = args.task_id.upper()
    with state_lock(wf):
        ctx = gates.Context(wf)
        state = ctx.state
        info = ops.task_state(ctx, tid)
        if info["status"] != "IN_PROGRESS":
            raise OrchError(f"{tid} is {info['status']}")
        failed = [r for r in gates.task_checklist(ctx, tid) if r.failed]
        if not failed:
            raise OrchError(f"{tid} has no failing verdict at the current snapshot; no fix round is needed")
        nxt = int(info.get("round") or 0) + 1
        if nxt >= int(info.get("review_budget") or 0):
            summary = f"{tid} still fails after {info.get('review_budget')} verification/review passes: " + \
                "; ".join(f"{r.label} ({r.detail})" for r in failed)
            state["resume_phase"] = state["phase"]
            state["phase"] = "NEEDS_HUMAN"
            state["needs_human"] = {"kind": "review_budget", "task": tid, "summary": summary, "raised_at": utcnow()}
            wf.save_state(state)
            transition(wf, "workflow", "NEEDS_HUMAN", task=tid, reason="review_budget")
            safe_render(wf)
            out(f"Review budget exhausted — the human must weigh in. {summary}")
            out(gates.needs_human_text(state))
            return 3
        info["round"] = nxt
        wf.save_state(state)
        transition(wf, "task-round", str(nxt), task=tid, attempt=info.get("attempt"),
                   failed=[r.key for r in failed])
    safe_render(wf)
    out(f"{tid} fix round {nxt} of {int(info['review_budget']) - 1}. Failing: " + "; ".join(r.label for r in failed))
    out(f"NEXT: resume the author(s) via SendMessage with `orch brief {tid} fix --agent <author>`.")
    return 0


def task_accept(wf: Workflow, args: argparse.Namespace) -> int:
    tid = args.task_id.upper()
    with state_lock(wf):
        ctx = gates.Context(wf)
        state = ctx.state
        info = ops.task_state(ctx, tid)
        if info["status"] != "IN_PROGRESS":
            raise OrchError(f"{tid} is {info['status']}")
        reqs = gates.task_checklist(ctx, tid)
        if gates.first_unmet(reqs):
            out(f"Cannot accept {tid}:")
            print_reqs(reqs)
            return 1
        spec = ctx.spec(tid)
        snap = ctx.take(spec.workspace, ctx.scope(spec))
        info.update(status="ACCEPTED", accepted_at=utcnow(), accepted_snapshot=snap.id, doc_sha256=spec.sha256)
        wf.save_state(state)
        ledger.append(wf, {"kind": "accept", "task": tid, "attempt": info["attempt"], "snapshot": snap.to_dict()})
    safe_render(wf)
    out(f"{tid} ACCEPTED at {snap.id}.")
    out("NEXT: " + gates.next_action(gates.Context(wf, fast=True)))
    return 0


def task_fail(wf: Workflow, args: argparse.Namespace) -> int:
    tid = args.task_id.upper()
    with state_lock(wf):
        ctx = gates.Context(wf)
        state = ctx.state
        info = ops.task_state(ctx, tid)
        if info["status"] != "IN_PROGRESS":
            raise OrchError(f"{tid} is {info['status']}")
        exhausted = int(info.get("attempt") or 0) >= int(info.get("attempt_budget") or 0)
        info["status"] = "BLOCKED" if exhausted else "PENDING"
        info.setdefault("failures", []).append({"attempt": info.get("attempt"), "reason": args.reason, "at": utcnow()})
        wf.save_state(state)
        transition(wf, "task", info["status"], task=tid, attempt=info.get("attempt"), reason=args.reason)
    safe_render(wf)
    if exhausted:
        out(f"{tid} BLOCKED after {info['attempt']} attempt(s). Write resolution guidance to "
            f"{wf.runs_dir / tid / 'resolution.orchestrator.md'}, get it reviewed "
            f"(`orch brief {tid} pm-resolution --agent project-manager`), then "
            f"`orch needs-human --kind task_budget --task {tid} --summary ...`.")
    else:
        out(f"{tid} attempt {info['attempt']} failed ({args.reason}). Start the next attempt with `orch task start {tid}`; "
            "feed the rejection findings into it.")
    return 0


def task_diff(wf: Workflow, args: argparse.Namespace) -> int:
    ctx = gates.Context(wf)
    result = ops.write_task_diff(ctx, args.task_id.upper(), since="checkpoint" if args.since_checkpoint else None)
    out(f"snapshot {result['snapshot']} — {len(result['changes'])} file(s) changed")
    for change in result["changes"]:
        out(f"  {change['status']} {change['path']}")
    out(f"patch: {result['patch']}")
    return 0


def task_scan(wf: Workflow, args: argparse.Namespace) -> int:
    ctx = gates.Context(wf)
    entry = ops.run_task_scan(ctx, args.task_id.upper())
    out(f"scan digest {entry['digest']} — {entry['hit_count']} hit(s) {entry['by_category']}")
    out(f"report: {entry['report']}")
    return 0


def task_status(wf: Workflow, args: argparse.Namespace) -> int:
    ctx = gates.Context(wf, fast=args.fast)
    tid = args.task_id.upper()
    out(f"{tid} — {ctx.spec(tid).title} — {ops.task_state(ctx, tid).get('status')}")
    print_reqs(gates.task_checklist(ctx, tid))
    return 0


# ================================================================ evidence / gates / snapshots


def launch_detached(wf: Workflow, argv: List[str]) -> int:
    """Re-run this command in a detached background process; `orch wait` collects it.

    Test suites can outlast the Bash tool's 10-minute limit; the detached run
    records its evidence exactly as a foreground run would.
    """
    jobs = wf.control / "jobs"
    jobs.mkdir(parents=True, exist_ok=True)
    job = f"job-{time.time_ns()}"
    log, exit_file = jobs / f"{job}.log", jobs / f"{job}.exit"
    cmd = [sys.executable, str(ORCH_CLI), "--wf", str(wf.root)] + [a for a in argv if a != "--detach"]
    shell = f"{shlex.join(cmd)} > {shlex.quote(str(log))} 2>&1; echo $? > {shlex.quote(str(exit_file))}"
    proc = subprocess.Popen(["/bin/bash", "-c", shell], start_new_session=True, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    write_json_atomic(jobs / f"{job}.json", {"id": job, "argv": cmd, "pid": proc.pid, "started": utcnow(),
                                             "log": str(log), "exit_file": str(exit_file)})
    out(f"{job} started in the background: orch {' '.join(a for a in argv if a != '--detach')}")
    out(f"Collect it with `orch wait {job}` (Bash timeout 600000); re-run the wait if it reports still running.")
    return 0


def cmd_wait(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    job = read_json(wf.control / "jobs" / f"{args.job}.json")
    if not isinstance(job, dict):
        raise OrchError(f"no such job {args.job}")
    deadline = time.time() + args.timeout
    exit_file = Path(job["exit_file"])
    while time.time() < deadline:
        if exit_file.exists() and exit_file.read_text().strip():
            code = int(exit_file.read_text().strip() or 1)
            out(Path(job["log"]).read_text(encoding="utf-8", errors="replace"))
            out(f"{args.job} finished with exit {code}")
            return code
        time.sleep(3)
    out(f"{args.job} is still running after {args.timeout}s of waiting; run `orch wait {args.job}` again.")
    return 75


def cmd_evidence(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    if args.detach:
        return launch_detached(wf, args.raw_argv)
    ctx = gates.Context(wf)
    entry = ops.run_evidence(ctx, args.task_id.upper(), args.phase, args.timeout)
    verdict = "PASSED" if entry["passed"] else "DID NOT PASS"
    expectation = "every command must FAIL (tests written before the implementation)" if args.phase == "red" \
        else "every command must pass"
    out(f"{args.phase} evidence {verdict} ({expectation}) at snapshot {entry['snapshot']['id']}")
    for result in entry["commands"]:
        out(f"  exit {result['exit']:>3}  {result['command']}  ({result['log']})")
    if entry.get("drift"):
        out("  WARNING: the workspace changed while the commands ran (generated files or a formatter). "
            "Add build artifacts to gate.json snapshot_exclude via a plan revision, or fix the command.")
    if entry.get("changed_since_start"):
        non_test = [c["path"] for c in entry["changed_since_start"] if c.get("test_file") == "no"]
        if non_test:
            out("  NOTE for the PM: non-test files changed before this checkpoint: " + ", ".join(non_test))
    safe_render(wf)
    return 0 if entry["passed"] else 1


def cmd_gate(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    if args.detach:
        return launch_detached(wf, args.raw_argv)
    ctx = gates.Context(wf)
    if args.task:
        tid = args.task.upper()
        spec = ctx.spec(tid)
        entry = ops.run_gate(ctx, args.level, "task", spec.workspace, task_id=tid, label=args.label,
                             timeout=args.timeout)
        entries = [entry]
    elif args.loop:
        spaces = [args.workspace] if args.workspace else sorted({t.workspace for t in gates.loop_tasks(ctx, args.loop)})
        entries = [ops.run_gate(ctx, args.level, "loop", w, loop=args.loop, label=args.label, timeout=args.timeout)
                   for w in spaces if planmod.gate_commands(ctx.pkg.gate, w, args.level)]
    elif args.final:
        spaces = [args.workspace] if args.workspace else gates.final_workspaces(ctx)
        entries = [ops.run_gate(ctx, args.level, "final", w, label=args.label, timeout=args.timeout) for w in spaces
                   if planmod.gate_commands(ctx.pkg.gate, w, args.level) or planmod.gate_commands(ctx.pkg.gate, w, "standard")]
    else:
        raise OrchError("gate run needs --task T, --loop N, or --final")
    ok = True
    for entry in entries:
        ok = ok and entry["passed"]
        out(f"{entry['scope']} gate {entry['level']} [{entry['workspace']}] {'PASSED' if entry['passed'] else 'FAILED'} "
            f"at {entry['snapshot']['id']}")
        for result in entry["commands"]:
            out(f"  exit {result['exit']:>3}  {result['command']}  ({result['log']})")
        if entry.get("drift"):
            out("  WARNING: the workspace changed while the gate ran; see gate.json snapshot_exclude.")
    safe_render(wf)
    return 0 if ok else 1


def cmd_snapshot(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    ctx = gates.Context(wf)
    if args.task:
        snap = ops.current_task_snapshot(ctx, args.task.upper(), "manual")
    elif args.workspace:
        snap = ctx.take(args.workspace)
        ops.record_snapshot(ctx, snap, "manual")
    else:
        raise OrchError("snapshot needs --task T or --workspace NAME")
    out(snap.id)
    return 0


# ================================================================ loops / final


def cmd_loop(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    n = int(args.number)
    with state_lock(wf):
        ctx = gates.Context(wf)
        state = ctx.state
        require_phase(state, "EXECUTING")
        loop = (state.get("loops") or {}).get(str(n))
        if loop is None:
            raise OrchError(f"loop {n} is not in the approved plan")
        if args.loop_cmd == "open":
            if loop.get("status") != "PENDING":
                raise OrchError(f"loop {n} is {loop.get('status')}")
            reqs = gates.loop_open_checklist(ctx, n)
        else:
            if loop.get("status") != "OPEN":
                raise OrchError(f"loop {n} is {loop.get('status')}")
            reqs = gates.loop_close_checklist(ctx, n)
        if gates.first_unmet(reqs):
            out(f"Cannot {args.loop_cmd} loop {n}:")
            print_reqs(reqs)
            return 1
        if args.loop_cmd == "open":
            starts = {}
            for name in sorted({t.workspace for t in gates.loop_tasks(ctx, n)}):
                snap = ctx.take(name)
                ops.record_snapshot(ctx, snap, "loop-start", loop=n)
                starts[name] = snap.to_dict()
            loop.update(status="OPEN", opened_at=utcnow(), start_snapshots=starts)
        else:
            loop.update(status="CLOSED", closed_at=utcnow())
        wf.save_state(state)
        transition(wf, "loop", loop["status"], loop=n)
    safe_render(wf)
    out(f"Loop {n} {loop['status']}.")
    out("NEXT: " + gates.next_action(gates.Context(wf, fast=True)))
    return 0


def cmd_final(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    with state_lock(wf):
        ctx = gates.Context(wf)
        state = ctx.state
        final = state.setdefault("final", {"status": "PENDING", "round": 0, "budget": 3})
        if args.final_cmd == "start":
            require_phase(state, "EXECUTING")
            open_loops = [k for k, v in (state.get("loops") or {}).items() if v.get("status") != "CLOSED"]
            if open_loops:
                raise OrchError(f"loops not closed: {', '.join(sorted(open_loops))}")
            starts = {k: v.get("snapshot") for k, v in (state.get("baselines") or {}).items()}
            info = ops.write_range_diffs(ctx, wf.final_dir, starts, gates.final_workspaces(ctx), "final-start")
            final.update(status="OPEN", round=0, started_at=utcnow(), doc_files_changed=info["doc_files_changed"])
            state["phase"] = "FINAL"
            wf.save_state(state)
            transition(wf, "workflow", "FINAL")
            msg = "Final whole-package review opened."
        elif args.final_cmd == "round":
            require_phase(state, "FINAL")
            failed = [r for r in gates.final_checklist(ctx) if r.failed]
            if not failed:
                raise OrchError("no failing final verdict at the current snapshot; no fix round is needed")
            nxt = int(final.get("round") or 0) + 1
            if nxt >= int(final.get("budget") or 3):
                state["resume_phase"] = "FINAL"
                state["phase"] = "NEEDS_HUMAN"
                state["needs_human"] = {"kind": "final_review_budget", "summary": "; ".join(r.label for r in failed),
                                        "raised_at": utcnow()}
                wf.save_state(state)
                transition(wf, "workflow", "NEEDS_HUMAN", reason="final_review_budget")
                safe_render(wf)
                out(gates.needs_human_text(state))
                return 3
            final["round"] = nxt
            wf.save_state(state)
            transition(wf, "final-round", str(nxt), failed=[r.key for r in failed])
            msg = f"Final fix round {nxt}."
        else:  # accept
            require_phase(state, "FINAL")
            reqs = gates.final_checklist(ctx)
            if gates.first_unmet(reqs):
                out("Cannot accept the package:")
                print_reqs(reqs)
                return 1
            comp, _ = ctx.composite(gates.final_workspaces(ctx))
            final.update(status="DONE", accepted_at=utcnow(), snapshot=comp)
            state.update(phase="DONE", completed_at=utcnow())
            wf.save_state(state)
            transition(wf, "workflow", "DONE", snapshot=comp)
            msg = ("Package DONE. Report to the human; they run acceptance testing, then "
                   "`/task-orchestrator close` or `/task-orchestrator revise <feedback>`.")
    safe_render(wf)
    out(msg)
    return 0


# ================================================================ human boundaries


def cmd_needs_human(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    kind = args.kind
    if kind not in RESOLVE_ACTIONS:
        raise OrchError(f"unknown kind {kind}; one of {', '.join(RESOLVE_ACTIONS)}")
    with state_lock(wf):
        ctx = gates.Context(wf)
        state = ctx.state
        tid = args.task.upper() if args.task else None
        if kind == "task_budget":
            if not tid or state["tasks"].get(tid, {}).get("status") != "BLOCKED":
                raise OrchError("task_budget needs --task for a BLOCKED task")
            guidance = wf.runs_dir / tid / "resolution.orchestrator.md"
            if not guidance.exists():
                raise OrchError(f"write the resolution guidance first: {guidance}")
            review = ctx.latest_result("pm-resolution", task=tid)
            if not (review and review["ts"] > (state["tasks"][tid].get("failures") or [{}])[-1].get("at", "")
                    and gates._passed(review)):
                raise OrchError("the guidance needs a passing PM review (`orch brief T pm-resolution --agent project-manager`)")
            args.report = args.report or str(guidance)
        if kind == "external_write":
            if not tid:
                raise OrchError("external_write needs --task")
            attempt = state["tasks"][tid].get("attempt")
            dry = [e for e in ctx.results("work", task=tid, attempt=attempt)
                   if (e.get("result") or {}).get("external_action") == "dry-run"]
            if not dry:
                raise OrchError("no dry-run result from the liaison for this attempt")
            args.report = args.report or (dry[-1].get("result") or {}).get("report")
        if state["phase"] != "NEEDS_HUMAN":
            state["resume_phase"] = state["phase"]
        state["phase"] = "NEEDS_HUMAN"
        state["needs_human"] = {"kind": kind, "task": tid, "summary": args.summary, "report": args.report,
                                "raised_at": utcnow()}
        wf.save_state(state)
    transition(wf, "workflow", "NEEDS_HUMAN", reason=kind, task=tid)
    safe_render(wf)
    out(gates.needs_human_text(state))
    out("Present this to the human clearly (what happened, what you recommend, what they must decide), then end the turn.")
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    action = args.action
    with state_lock(wf):
        ctx = gates.Context(wf)
        state = ctx.state
        require_phase(state, "NEEDS_HUMAN")
        need = state.get("needs_human") or {}
        kind = need.get("kind")
        if action not in RESOLVE_ACTIONS.get(kind, ()):
            raise OrchError(f"`{action}` does not resolve `{kind}`; allowed: {', '.join(RESOLVE_ACTIONS.get(kind, ()))}")
        tid = need.get("task")
        if action == "answer":
            token = ledger.find_human_token(ctx.entries, None, after_ts=need.get("raised_at"))
        else:
            token = human_token(ctx.entries, "resolve", need.get("raised_at"), action=action, task=tid)
        if token is None:
            example = f"/task-orchestrator resolve {action}{' ' + tid if tid else ''} <notes>"
            raise OrchError(f"no matching human decision recorded after this was raised; the human types `{example}`"
                            if action != "answer" else "the human has not replied since this was raised")
        consume(wf, token, f"resolve:{action}")
        grant = args.grant
        numbers = [int(a) for a in token.get("args") or [] if str(a).isdigit()]
        if numbers:
            grant = numbers[0]
        resolution: Dict[str, Any] = {"kind": "resolution", "action": action, "task": tid, "human_seq": token["seq"],
                                      "need": kind}
        info = state["tasks"].get(tid) if tid else None
        if info is not None:
            resolution["attempt"] = info.get("attempt")
        if action == "continue":
            if kind == "final_review_budget":
                state["final"]["budget"] = int(state["final"].get("budget") or 3) + (grant or 3)
            elif kind == "continuation_budget":
                state["stop_continuations"] = 0
            elif info is not None:
                info["review_budget"] = int(info.get("review_budget") or 3) + (grant or 3)
        elif action == "waive":
            if kind == "final_review_budget":
                comp, _ = ctx.composite(gates.final_workspaces(ctx))
                failing = [r.key.split(":", 1)[1] for r in gates.final_checklist(ctx)
                           if r.key.startswith("final-review:") and not r.ok]
                resolution.update(scope="final", snapshot=comp, reviewers=failing)
            else:
                spec = ctx.spec(tid)
                snap = ctx.take(spec.workspace, ctx.scope(spec))
                failing = [r.key.split(":", 1)[1] for r in gates.task_checklist(ctx, tid)
                           if r.key.startswith("review:") and not r.ok]
                resolution.update(snapshot=snap.to_dict(), reviewers=failing)
        elif action == "retry":
            if info is not None:
                if kind == "task_budget":
                    info["attempt_budget"] = int(info.get("attempt_budget") or 0) + (grant or 1)
                    info["status"] = "PENDING"
                elif kind == "review_budget" and info.get("status") == "IN_PROGRESS":
                    info["status"] = "PENDING"
                    if int(info.get("attempt") or 0) >= int(info.get("attempt_budget") or 0):
                        info["attempt_budget"] = int(info.get("attempt") or 0) + 1
        resolution["grant"] = grant
        state["phase"] = state.get("resume_phase") or "EXECUTING"
        state["resume_phase"] = None
        state["needs_human"] = None
        wf.save_state(state)
    ledger.append(wf, resolution)
    append_decision(wf, f"human decision: {action}{' ' + tid if tid else ''} (resolving {kind})", token.get("raw") or action)
    transition(wf, "workflow", state["phase"], reason=f"resolved {kind} with {action}", task=tid)
    safe_render(wf)
    out(f"Resolved {kind} with `{action}`. The human's words are recorded in decisions.md — every later brief carries them.")
    out("NEXT: " + gates.next_action(gates.Context(wf, fast=True)))
    return 0


def cmd_deviation(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    with state_lock(wf):
        state = wf.load_state()
        state["resume_phase"] = state["phase"]
        state["phase"] = "PLAN_CHANGE_REQUIRED"
        state["block_reason"] = args.summary
        state["phase_since"] = utcnow()
        wf.save_state(state)
    transition(wf, "workflow", "PLAN_CHANGE_REQUIRED", reason=args.summary, task=args.task)
    append_decision(wf, "deviation raised (plan change required)", args.summary)
    safe_render(wf)
    out("PLAN_CHANGE_REQUIRED recorded. Explain the deviation to the human and stop; they decide with "
        "`/task-orchestrator revise <feedback>`.")
    return 0


def cmd_halt(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    with state_lock(wf):
        state = wf.load_state()
        state["halt_requested"] = True
        wf.save_state(state)
    transition(wf, "halt-requested", "HALTED")
    out("Halt requested; it takes effect at the next turn boundary.")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    with state_lock(wf):
        ctx = gates.Context(wf)
        state = ctx.state
        if state["phase"] != "HALTED":
            out(f"phase is {state['phase']}; nothing to un-halt.")
            out("NEXT: " + gates.next_action(gates.Context(wf, fast=True)))
            return 0
        token = human_token(ctx.entries, "resume", state.get("halted_at"))
        if token is None:
            raise OrchError("resuming a halted workflow is the human's call: they type `/task-orchestrator resume`")
        consume(wf, token, "resume")
        state["phase"] = state.get("resume_phase") or "EXECUTING"
        state["resume_phase"] = None
        state["halt_requested"] = False
        wf.save_state(state)
    transition(wf, "workflow", state["phase"], reason="resumed by the human")
    safe_render(wf)
    out(f"Resumed ({state['phase']}).")
    out("NEXT: " + gates.next_action(gates.Context(wf, fast=True)))
    return 0


def cmd_close(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    with state_lock(wf):
        ctx = gates.Context(wf)
        state = ctx.state
        require_phase(state, "DONE")
        token = human_token(ctx.entries, "close", state.get("completed_at"))
        if token is None:
            raise OrchError("closing is the human's call after acceptance testing: they type `/task-orchestrator close`")
        consume(wf, token, "close")
        state.update(phase="CLOSED", closed_at=utcnow())
        wf.save_state(state)
    transition(wf, "workflow", "CLOSED")
    session = state.get("session_id")
    if session:
        clear_binding(session)
    safe_render(wf)
    out(f"Workflow {state['workflow_id']} CLOSED. Its directory is the permanent record; the session is unbound.")
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    append_decision(wf, f"orchestrator note{' — ' + args.title if args.title else ''}", args.text)
    ledger.append(wf, {"kind": "note", "title": args.title, "text": args.text[:2000]})
    out(f"noted in {wf.decisions}")
    return 0


# ================================================================ briefs / views


def cmd_brief(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    positional = list(args.target)
    task_id = None
    if positional and re.match(r"^[Tt]\d{3,}$", positional[0]):
        task_id = positional.pop(0).upper()
    if len(positional) != 1:
        raise OrchError("usage: orch brief [T###] <stage> --agent <agent> [--loop N | --final | --plan]")
    stage = positional[0]
    ctx = gates.Context(wf)
    text, report = briefs.build(ctx, stage, args.agent, task_id=task_id, loop=args.loop, topic=args.topic,
                                note=args.note, mode_hint=args.mode)
    safe_render(wf)
    out(text)
    return 0


def cmd_ledger(args: argparse.Namespace) -> int:
    wf = resolve_workflow(args.wf)
    entries = ledger.read(wf)
    if args.task:
        entries = [e for e in entries if e.get("task") == args.task.upper()
                   or (e.get("result") or {}).get("task") == args.task.upper()]
    if args.kind:
        entries = [e for e in entries if e.get("kind") == args.kind]
    for entry in entries[-args.tail:]:
        out(json.dumps(entry, sort_keys=True) if args.json else render._describe(entry))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    rows = list_bindings()
    if not rows:
        out("No session bindings.")
    for row in rows:
        wf = Workflow(Path(row["workflow_dir"]))
        phase = wf.load_state().get("phase") if wf.exists() else "MISSING"
        out(f"{row['workflow_id']}  {phase}  {row['workflow_dir']}  (session {row['session_id'][:8]})")
    return 0


# ================================================================ doctor / selftest


def _settings_hooks() -> Dict[str, bool]:
    settings = read_json(Path.home() / ".claude" / "settings.json", default={}) or {}
    hooks = settings.get("hooks") or {}
    found = {}
    for event in HOOK_EVENTS:
        groups = hooks.get(event) or []
        found[event] = any(
            "task-orchestrator/scripts/hook.py" in (h.get("command") or "")
            for g in groups if isinstance(g, dict) for h in g.get("hooks") or [] if isinstance(h, dict)
        )
    return found


def cmd_doctor(args: argparse.Namespace) -> int:
    problems = 0
    out(f"python {sys.version.split()[0]} ({sys.executable})")
    out(f"cli {ORCH_CLI}")
    out(f"registry {orch_home()}")
    session = current_session_id()
    out(f"session {session or 'NOT SET (run inside Claude Code)'}")
    binding = get_binding(session)
    out(f"binding {binding['workflow_dir'] if binding else 'none'}")
    agents_dir = Path.home() / ".claude" / "agents"
    missing = [name for name in sorted(AGENTS) if not (agents_dir / f"{name}.md").is_file()]
    out(f"roster {len(AGENTS) - len(missing)}/{len(AGENTS)} agent definitions present")
    for name in missing:
        problems += 1
        out(f"  MISSING agent definition: {agents_dir / (name + '.md')}")
    for event, ok in _settings_hooks().items():
        out(f"hook {event}: {'registered' if ok else 'NOT REGISTERED'}")
        problems += 0 if ok else 1
    beat = read_json(orch_home() / "heartbeat.json", default={}) or {}
    for event in HOOK_EVENTS:
        out(f"last {event}: {beat.get(event, 'never (while bound)')}")
    if shutil.which("git") is None:
        problems += 1
        out("git NOT FOUND (snapshots need git)")
    out("OK" if problems == 0 else f"{problems} problem(s)")
    return 0 if problems == 0 else 1


def cmd_selftest(args: argparse.Namespace) -> int:
    session = current_session_id()
    if not session:
        raise OrchError("run the selftest inside a Claude Code session")
    root = orch_home() / "selftest"
    if not args.check:
        bound = get_binding(session)
        if bound:
            raise OrchError(f"this session is bound to {bound['workflow_dir']}; the selftest needs an unbound session")
        ns = argparse.Namespace(plan_root=str(root), title="selftest", slug="selftest", workspace=None,
                                request_file=None, no_bind=False)
        cmd_init(ns)
        wf = resolve_workflow(None)
        write_text_atomic(wf.request, "Selftest of the task-orchestrator hook wiring.\n")
        ctx = gates.Context(wf)
        text, _ = briefs.build(ctx, "selftest", "project-manager")
        out("")
        out("SELFTEST STEP 1 — dispatch the project-manager agent (Agent tool, subagent_type "
            "project-manager) with exactly this brief as the prompt:")
        out("-" * 72)
        out(text)
        out("-" * 72)
        out("SELFTEST STEP 2 — ask the human to type exactly `/task-orchestrator status` (this proves the "
            "human-command hook captures what they type).")
        out("SELFTEST STEP 3 — then run: orch selftest --check")
        return 0
    wf = resolve_workflow(None)
    state = wf.load_state()
    if state.get("title") != "selftest":
        raise OrchError("the bound workflow is not a selftest workflow")
    entries = ledger.read(wf)
    results = ledger.select(entries, "agent_result")
    checks = []
    got = ledger.latest(results)
    checks.append(("SubagentStop recorded a roster agent result", got is not None))
    checks.append(("agent_type came from the harness (project-manager)", bool(got) and got.get("agent_type") == "project-manager"))
    checks.append(("result block validated", bool(got) and bool(got.get("valid"))))
    checks.append(("SubagentStart injected the contract", bool(got) and (got.get("result") or {}).get("contract_seen") is True))
    beat = read_json(orch_home() / "heartbeat.json", default={}) or {}
    checks.append(("PreToolUse hook active", "PreToolUse" in beat))
    human = [e for e in entries if e.get("kind") == "human"]
    typed = [e for e in human if e.get("verb") == "status"]
    checks.append(("the human's `/task-orchestrator status` was captured as a command", bool(typed)))
    for label, ok in checks:
        out(f"[{'x' if ok else ' '}] {label}")
    if got and not got.get("valid"):
        out("  errors: " + "; ".join(got.get("errors") or []))
    if got:
        out(f"  agent_type={got.get('agent_type')} agent_id={got.get('agent_id')}")
    for entry in human[-3:]:
        out(f"  human prompt via {entry.get('via')} source={entry.get('source')} verb={entry.get('verb')} "
            f"raw={entry.get('raw', '')[:160]!r}")
    passed = all(ok for _, ok in checks)
    clear_binding(session)
    if passed:
        shutil.rmtree(wf.root, ignore_errors=True)
    out("SELFTEST PASSED" if passed else f"SELFTEST FAILED (workflow kept for inspection: {wf.root}; session unbound)")
    return 0 if passed else 1


# ================================================================ parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orch", description=__doc__.split("\n\n")[0])
    parser.add_argument("--wf", help="workflow directory (default: this session's binding)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create a workflow directory and bind this session")
    p.add_argument("plan_root", help="where the user wants the planning/task documents")
    p.add_argument("--title", required=True)
    p.add_argument("--slug")
    p.add_argument("--workspace", action="append", help="name=path of a workspace the work changes (repeatable)")
    p.add_argument("--request-file", help="file holding the verbatim request")
    p.add_argument("--no-bind", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("bind", help="bind this session to an existing workflow (e.g. after a restart)")
    p.add_argument("workflow_dir")
    p.set_defaults(func=cmd_bind)
    sub.add_parser("unbind", help="remove this session's binding").set_defaults(func=cmd_unbind)
    sub.add_parser("where", help="print the bound workflow directory").set_defaults(func=cmd_where)

    p = sub.add_parser("status", help="workflow status and the next required action")
    p.add_argument("--task")
    p.add_argument("--json", action="store_true")
    p.add_argument("--fast", action="store_true", help="use recorded snapshots (no git work)")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("validate", help="validate the plan package")
    p.add_argument("--for-approval", action="store_true")
    p.set_defaults(func=cmd_validate)
    sub.add_parser("plan-hash", help="hash of the frozen planning artifacts").set_defaults(func=cmd_plan_hash)
    sub.add_parser("render", help="regenerate index/status files").set_defaults(func=cmd_render)
    sub.add_parser("submit", help="PLANNING -> AWAITING_APPROVAL (planning checklist must be met)").set_defaults(func=cmd_submit)
    sub.add_parser("approve", help="freeze the plan and start execution (needs the human's /task-orchestrator approve)").set_defaults(func=cmd_approve)
    sub.add_parser("revise", help="open a plan revision (needs the human's /task-orchestrator revise)").set_defaults(func=cmd_revise)

    p = sub.add_parser("task", help="task transitions and views")
    tsub = p.add_subparsers(dest="task_cmd", required=True)
    for name, help_text in (("start", "start the next attempt"), ("round", "open a fix round after a failing verdict"),
                            ("accept", "accept (all gates must be met)"), ("diff", "write the task diff"),
                            ("scan", "run the integrity scan"), ("status", "show the task's gate checklist")):
        tp = tsub.add_parser(name, help=help_text)
        tp.add_argument("task_id")
        if name == "status":
            tp.add_argument("--fast", action="store_true")
        if name == "diff":
            tp.add_argument("--since-checkpoint", action="store_true",
                            help="diff from the red/baseline checkpoint instead of the task start")
    tp = tsub.add_parser("fail", help="end the current attempt (e.g. the PM rejected it)")
    tp.add_argument("task_id")
    tp.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_task)

    p = sub.add_parser("evidence", help="run the task's frozen red_green commands and record the result")
    p.add_argument("task_id")
    p.add_argument("phase", choices=("red", "baseline", "green"))
    p.add_argument("--timeout", type=int, default=3600)
    p.add_argument("--detach", action="store_true", help="run in the background; collect with `orch wait`")
    p.set_defaults(func=cmd_evidence)

    p = sub.add_parser("wait", help="wait for a --detach job and print its output")
    p.add_argument("job")
    p.add_argument("--timeout", type=int, default=540, help="seconds to wait before returning (default 540)")
    p.set_defaults(func=cmd_wait)

    p = sub.add_parser("gate", help="run gate.json commands and record the result")
    gsub = p.add_subparsers(dest="gate_cmd", required=True)
    gp = gsub.add_parser("run")
    gp.add_argument("level", choices=("standard", "final"))
    gp.add_argument("--task")
    gp.add_argument("--loop", type=int)
    gp.add_argument("--final", action="store_true")
    gp.add_argument("--workspace")
    gp.add_argument("--label")
    gp.add_argument("--timeout", type=int, default=3600)
    gp.add_argument("--detach", action="store_true", help="run in the background; collect with `orch wait`")
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("snapshot", help="record a snapshot")
    p.add_argument("--task")
    p.add_argument("--workspace")
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("loop", help="open/close an orchestration loop")
    p.add_argument("loop_cmd", choices=("open", "close"))
    p.add_argument("number")
    p.set_defaults(func=cmd_loop)

    p = sub.add_parser("final", help="whole-package review: start | round | accept")
    p.add_argument("final_cmd", choices=("start", "round", "accept"))
    p.set_defaults(func=cmd_final)

    p = sub.add_parser("needs-human", help="stop for a human decision")
    p.add_argument("--kind", required=True, choices=sorted(RESOLVE_ACTIONS))
    p.add_argument("--summary", required=True)
    p.add_argument("--task")
    p.add_argument("--report")
    p.set_defaults(func=cmd_needs_human)

    p = sub.add_parser("resolve", help="apply the human's decision (needs their /task-orchestrator resolve ...)")
    p.add_argument("--action", required=True, choices=("answer", "continue", "waive", "retry", "confirm"))
    p.add_argument("--grant", type=int, default=0)
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("deviation", help="record that the approved plan cannot be followed as written")
    p.add_argument("--summary", required=True)
    p.add_argument("--task")
    p.set_defaults(func=cmd_deviation)

    sub.add_parser("halt", help="request a halt at the next turn boundary").set_defaults(func=cmd_halt)
    sub.add_parser("resume", help="un-halt (needs the human's /task-orchestrator resume)").set_defaults(func=cmd_resume)
    sub.add_parser("close", help="DONE -> CLOSED (needs the human's /task-orchestrator close)").set_defaults(func=cmd_close)

    p = sub.add_parser("note", help="append a clarification to decisions.md")
    p.add_argument("text")
    p.add_argument("--title")
    p.set_defaults(func=cmd_note)

    p = sub.add_parser("brief", help="generate a dispatch brief for a roster agent")
    p.add_argument("target", nargs="+", help="[T###] <stage>")
    p.add_argument("--agent", required=True, choices=sorted(ROSTER))
    p.add_argument("--loop", type=int)
    p.add_argument("--final", action="store_true")
    p.add_argument("--plan", action="store_true")
    p.add_argument("--topic", help="research topic (research briefs)")
    p.add_argument("--mode", help="mode hint (e.g. 'plan' or 'code' for architecture-reviewer)")
    p.add_argument("--note", help="extra context for this dispatch")
    p.set_defaults(func=cmd_brief)

    p = sub.add_parser("ledger", help="show ledger entries")
    p.add_argument("--task")
    p.add_argument("--kind")
    p.add_argument("--tail", type=int, default=30)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ledger)

    sub.add_parser("list", help="list session bindings").set_defaults(func=cmd_list)
    sub.add_parser("doctor", help="check installation and hook wiring").set_defaults(func=cmd_doctor)
    p = sub.add_parser("selftest", help="end-to-end hook check (run, dispatch the brief, then --check)")
    p.add_argument("--check", action="store_true")
    p.set_defaults(func=cmd_selftest)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    raw = list(argv) if argv is not None else sys.argv[1:]
    args = parser.parse_args(raw)
    args.raw_argv = raw
    try:
        return int(args.func(args) or 0)
    except OrchError as exc:
        print(f"orch: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
