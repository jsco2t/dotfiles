"""Execution: what runs next, dispatching a step, recording its hand-back, and every gate
between steps — decided by this script, never by reading prose. Planning research lives in
research.py and end-of-pipeline review in review.py; this module routes to them."""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from . import briefs, docscheck, snapshot
from . import plan as planmod
from . import scope as scopemod
from .common import (TP_SCRIPT, TPError, Workflow, agent_context_tokens, gap_minutes, limit, load_json, minutes_since,
                     now_iso, sha_file, waiting_gaps, words)

DONE_STATES = ("accepted", "skipped")
# (The TP_* variables exist for the test suite, which cannot wait minutes for a timeout.)
CHECK_TIMEOUT = int(os.environ.get("TP_CHECK_TIMEOUT", 540))  # a task's tests and checks: a foreground `tp record`
# The final checks run in the background (`tp final`, the first publish dry run): a whole suite
# needs longer. Real runs' `make test` passed in 11 and 17 minutes after timing out at 540s.
FINAL_CHECK_TIMEOUT = int(os.environ.get("TP_FINAL_CHECK_TIMEOUT", 45 * 60))
SUMMARY_WORDS = 80      # what a hand-back summary is shown at
SUMMARY_CEILING = 300   # past this the agent rewrites it


def _research():
    from . import research
    return research


def _review():
    from . import review
    return review


# --- state helpers ---------------------------------------------------------------------

def new_task_state() -> Dict[str, Any]:
    return {"status": "pending", "step": None, "round": 0, "extra_rounds": 0, "reviews": 0, "agents": {},
            "fixing": None, "findings": [], "blocked": None, "started": None, "accepted": None,
            "tests_hash": None, "note": None}


def _take(wf: Workflow, root: Path, only: Optional[List[str]] = None) -> snapshot.Snapshot:
    """A snapshot of a workspace (the workflow folder left out) that reuses the hashes of files
    whose size and mtime have not changed since the last one: on a large repository a full
    re-hash costs seconds every dispatch, record, and digest."""
    root = Path(root).resolve()
    cache = wf.meta / "statcache" / (hashlib.sha1(str(root).encode()).hexdigest()[:16] + ".json")
    return snapshot.take(root, [wf.root], cache=cache, only=only, ignore=_ignored(wf))


def _ignored(wf: Workflow) -> List[str]:
    """scope.json `ignore`: workspace-relative patterns for files no task writes (a sandbox's
    per-command mount points), left out of every snapshot and read-only check."""
    if not wf.scope_json.exists():
        return []
    try:
        data = json.loads(wf.scope_json.read_text())
    except ValueError:
        return []
    pats = data.get("ignore") if isinstance(data, dict) else None
    return [str(p) for p in pats] if isinstance(pats, list) else []


def _write_aliases(scope: Dict[str, Any]) -> set:
    """Read workspaces that are the same directory as a write workspace: a reference alias for
    citations, written by the run's own tasks, so never read-only."""
    writable = {str(Path(w["path"]).resolve()) for w in scopemod.workspaces(scope).values() if w["mode"] == "write"}
    return {name for name, w in scopemod.workspaces(scope).items()
            if w["mode"] == "read" and str(Path(w["path"]).resolve()) in writable}


def readonly_baseline(wf: Workflow, scope: Dict[str, Any], keep: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """keep: baselines already recorded, kept as they are (a re-approval or scope amendment adds
    only the workspaces that have none)."""
    base: Dict[str, Any] = dict(keep or {})
    aliases = _write_aliases(scope)
    for name, ws in scopemod.workspaces(scope).items():
        if ws["mode"] != "read" or name in base or name in aliases:
            continue
        root = Path(ws["path"])
        porcelain = snapshot.git_porcelain(root)
        if porcelain is not None:
            base[name] = {"git": porcelain}
        else:
            snap_path = wf.meta / f"readonly-{name}.json"
            snapshot.save(snap_path, _take(wf, root))
            base[name] = {"snap": str(snap_path)}
    return base


def _readonly_changes(wf: Workflow, state: Dict[str, Any], scope: Dict[str, Any]) -> List[str]:
    out = []
    aliases = _write_aliases(scope)
    ignore = _ignored(wf)
    for name, base in state.get("readonly_baseline", {}).items():
        if name in aliases:
            continue
        root = Path(scopemod.workspaces(scope)[name]["path"])
        if "git" in base:
            now = snapshot.git_porcelain(root) or ""
            before = set(base["git"].splitlines())
            changed = [ln[3:] for ln in now.splitlines() if ln not in before]
        else:
            changed = snapshot.diff(snapshot.load(Path(base["snap"])), _take(wf, root))
        changed = [c for c in changed if not (ignore and snapshot.matches(c, ignore))]
        if changed:
            out.append(f"The read-only workspace {name} changed: {', '.join(changed[:8])} — restore it "
                       "(read-only means no edits, builds, or generated files there).")
    return out


def _loaded(wf: Workflow, state: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Dict[str, Any]]]:
    if state.get("plan_approved_sha") and sha_file(wf.plan_json) != state["plan_approved_sha"]:
        raise TPError("plan.json changed after approval. If you meant to amend the plan, `tp plan amend` makes your "
                      "edit the draft and restores the approved plan; otherwise restore it, or ask the human and run "
                      "`tp revise --feedback \"<their words>\"`.")
    plan = planmod.load_plan(wf)
    scope = scopemod.load_scope(wf)
    state.setdefault("integration", [t["id"] for t in plan["tasks"] if planmod.is_integration(t, scope)])
    for path, sha in state.get("conventions_sha", {}).items():
        if sha_file(Path(path)) != sha:
            raise TPError(f"{Path(path).name} changed after approval: conventions are part of every brief's contract. "
                          f"Restore {path}. To change conventions, write them to a new file, point plan-amend.json's "
                          "`conventions` at it, and `tp plan amend` (the human approves it).")
    return plan, scope, {t["id"]: t for t in plan["tasks"]}


def _ws(scope: Dict[str, Any], name: str) -> Path:
    return Path(scopemod.workspaces(scope)[name]["path"])


def _deps_open(task: Dict[str, Any], state: Dict[str, Any]) -> List[str]:
    return [d for d in task.get("depends_on", []) if state["tasks"][d]["status"] not in DONE_STATES]


def _authoring_step(task: Dict[str, Any], scope: Dict[str, Any], ts: Optional[Dict[str, Any]] = None) -> str:
    """Who a fix round goes to: the author; for code, the code author — the fused build author when
    the task ran fused (it owns its tests and its code alike)."""
    if not planmod.is_code(task, scope):
        return "author"
    return "build" if ts and ts.get("agents", {}).get("build") else "impl"


def _cap(ts: Dict[str, Any]) -> int:
    return limit("max_fix_rounds") + ts.get("extra_rounds", 0)


# --- next --------------------------------------------------------------------------------

def _integration_held(task: Dict[str, Any], scope: Dict[str, Any], state: Dict[str, Any]) -> bool:
    """External writes wait for the final review, so each is made once, with reviewed content:
    in a real run a Jira comment posted before review was edited three times after it."""
    if not planmod.is_integration(task, scope) or task.get("when", "after_review") == "anytime":
        return False
    if any("tasks" not in s for s in state.get("reviews", {}).values()):
        return False  # a workflow approved before this rule: its review batches still hold integration tasks
    others = [t for t in state["tasks"] if t not in state.get("integration", [])]
    if (any(state["tasks"][t]["status"] not in DONE_STATES for t in others)
            or any(s["status"] != "done" for s in state.get("reviews", {}).values())):
        return True
    return _awaits_checks(task, state)


def _awaits_checks(task: Dict[str, Any], state: Dict[str, Any]) -> bool:
    """Last of all, after the closeout and the final checks, so the human's answer ends the run:
    in a real run the post's question waited nine hours with the closeout, a fix task, its review,
    and the checks still to do — and the fix task had to keep the posted comment's line citations
    valid. A publish dry run runs the checks itself; `tp final` runs them before an agent's post.
    A dry run already shown is not taken back."""
    shown = (state["tasks"].get(task.get("id"), {}) or {}).get("publish")
    return not shown and not _prefinal_fresh(state)


def _work_sig(state: Dict[str, Any]) -> str:
    """Everything but the posts: the tasks, the reviews, and the closeout. A pre-post check of
    the finished work holds while none of it moves."""
    integ = set(state.get("integration", []))
    return hashlib.sha1(json.dumps([
        sorted((t, ts["status"], ts.get("round", 0)) for t, ts in state["tasks"].items() if t not in integ),
        sorted((sid, s.get("status"), s.get("round")) for sid, s in state.get("reviews", {}).items()),
        sorted((state.get("closeout") or {}).get("items", {})),
    ]).encode()).hexdigest()


def _prefinal_fresh(state: Dict[str, Any]) -> bool:
    pre = state.get("prefinal")
    return bool(pre) and pre.get("sig") == _work_sig(state)


def tp_command(wf: Workflow, *args: str) -> str:
    """A tp command for an agent to run, in the form the documented allow rule matches —
    `python3 ~/.claude/skills/task-pipeline/scripts/tp.py ...` — so an unattended code author's
    `tp red` is not stopped by a permission prompt. Elsewhere (a checkout, the tests): absolute."""
    home = Path("~").expanduser()
    script = str(TP_SCRIPT)
    try:
        script = "~/" + TP_SCRIPT.relative_to(home).as_posix() if (
            TP_SCRIPT.is_relative_to(home / ".claude")) else script
    except ValueError:
        pass
    return " ".join(["python3", script if script.startswith("~/") else shlex.quote(script), "-w",
                     shlex.quote(str(wf.root))] + [shlex.quote(a) for a in args])


def split_tests(scope: Dict[str, Any], state: Dict[str, Any]) -> bool:
    """Whether code tasks run as two agents (test author, then code author). New runs fuse them
    unless the scope asks for independent test authorship; older runs keep the split they had."""
    if "split_tests" in scope:
        return bool(scope["split_tests"])
    return int(state.get("contract", 1)) < 2


def _gate_waits_on(tid: str, tasks: Dict[str, Dict[str, Any]], state: Dict[str, Any]) -> List[str]:
    """What a gate still waits for before the human is asked: the tasks it depends on, then every
    review session over work upstream of it (the human signs off reviewed work)."""
    waits = _deps_open(tasks[tid], state)
    if waits:
        return waits
    upstream = planmod._ancestors(tasks).get(tid, set())
    return [sid for sid, s in state.get("reviews", {}).items()  # the whole-change review comes after every gate
            if s.get("status") != "done" and not s.get("whole") and upstream & set(s.get("tasks") or [])]


def _action_for(tid: str, ts: Dict[str, Any], task: Dict[str, Any], scope: Dict[str, Any],
                state: Dict[str, Any], tasks: Optional[Dict[str, Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    status = ts["status"]
    act: Dict[str, Any] = {"id": tid, "model": task.get("model"), "agent_id": None}
    if status == "pending" and planmod.is_gate(task):
        if _gate_waits_on(tid, tasks or {tid: task}, state):
            return None
        return ({"action": "asked", "id": tid,
                 "why": f"gate {tid} (their reply: `tp gate {tid} --answer \"<their words>\"`)"} if ts.get("asked")
                else {"action": "gate", "id": tid})
    if status == "pending":
        if _deps_open(task, state) or _integration_held(task, scope, state):
            return None
        if planmod.is_publish(task):
            return {"action": "publish", "id": tid}
        code = planmod.is_code(task, scope)
        # Fused by default on new runs: one code author writes the tests, runs `tp red` (the pipeline
        # observes red before any production code), implements to green, and hands back once.
        split = code and split_tests(scope, state) and task.get("test_mode") != "existing"
        step = ("tests" if split else "build") if code else "author"
        act.update(action="dispatch", step=step,
                   agent=planmod.tests_agent(task, scope) if split else task["agent"])
    elif status == "needs_impl":
        act.update(action="dispatch", step="impl", agent=task["agent"])
    elif status == "needs_fix":
        fixing = ts["fixing"] or _authoring_step(task, scope, ts)
        agent = planmod.tests_agent(task, scope) if fixing == "tests" else task["agent"]
        # A fused task's one author wrote both its tests and its code: resume it for either.
        agent_id = ts["agents"].get(fixing) or (ts["agents"].get("build") if agent == task["agent"] else None)
        act.update(action="fix", step="fix", agent=agent, agent_id=agent_id)
    elif status == "needs_review":
        act.update(action="review", step="review", agent=planmod.reviewer_for(task, scope),
                   agent_id=ts["agents"].get("review"))
    else:
        return None
    return act


def _amend_action(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """An amendment review with the reviewer: the one way back to it, for `tp next` and a fresh session."""
    ar = state.get("amend_review") or {}
    if ar.get("status") != "in_flight":
        return []
    return [{"action": "amend_review", "id": f"amend/review:{ar.get('round')}", "why": ar.get("kind", "plan")}]


def actions(wf: Workflow, state: Dict[str, Any], ignore_halt: bool = False) -> List[Dict[str, Any]]:
    phase = state["phase"]
    if phase == "DONE":
        return [{"action": "done"}]
    if state.get("halt") and not ignore_halt:
        if state["in_flight"]:
            return [{"action": "halting", "ids": list(state["in_flight"])}]
        return [{"action": "halted"}]
    if phase == "SCOPING":
        if state.get("scope_checked_sha") and state["scope_checked_sha"] == sha_file(wf.scope_json):
            return [{"action": "human", "why": "confirm the scope in scope.md"}]
        return [{"action": "scope"}]
    if phase == "PLANNING":
        free = limit("max_in_flight") - len(state["in_flight"])
        return _research().actions(state, free) + _amend_action(state) + [{"action": "plan"}]
    if phase == "AWAITING_APPROVAL":
        pr = state.get("plan_review") if int(state.get("contract", 1)) >= 2 else None
        if pr is None:  # a workflow from before the plan review keeps its human approval
            return [{"action": "human", "why": "approve or revise the plan in plan.md"}]
        status = pr.get("status")
        if status == "in_flight":
            return [{"action": "wait", "ids": [f"plan review round {pr['round']}"]}]
        if status == "pass":
            return [{"action": "approve"}]
        if status == "needs_triage":
            return [{"action": "plan_triage", "id": f"round {pr['round']}"}]
        if status == "changes":
            return [{"action": "plan_fix"}]
        stop = planmod.plan_review_exhausted(pr)
        if stop:
            return [{"action": "human", "why": f"{stop} — show the human the open findings; `tp revise --feedback` "
                                              "with their words"}]
        return [{"action": "plan_review"}]

    plan, scope, tasks = _loaded(wf, state)
    acts = []
    if state.get("blocked"):
        acts.append({"action": "human", "why": state["blocked"]["summary"]})
    for tid, ts in state["tasks"].items():
        if ts["status"] == "blocked" and ts["blocked"].get("kind") == "sibling":
            # Waiting on a sibling's red tests, not on the human: re-check once they have all landed.
            if not _red_siblings(state, ts["blocked"].get("on", [])):
                acts.append({"action": "recheck", "id": tid})
            continue
        if ts["status"] == "blocked":
            lost = ts["blocked"].get("lost", 0)  # under the loss breaker, a re-run is the manager's call
            acts.append({"action": "rerun" if 0 < lost < limit("max_lost_retries") else "human", "id": tid,
                         "why": ts["blocked"]["summary"]})
    for tid, ts in state["tasks"].items():
        if ts["status"] == "needs_check":
            acts.append({"action": "check", "id": tid})
    free = limit("max_in_flight") - len(state["in_flight"])
    order = {"needs_fix": 0, "needs_review": 1, "needs_impl": 2, "pending": 3}
    ranked = sorted((order[ts["status"]], tid) for tid, ts in state["tasks"].items() if ts["status"] in order)
    for _, tid in ranked:
        act = _action_for(tid, state["tasks"][tid], tasks[tid], scope, state, tasks)
        if act and act["action"] in ("publish", "gate", "asked"):  # the manager's own work; no agent slot
            acts.append(act)
        elif act and free > 0:
            acts.append(act)
            free -= 1
    review_acts = _review().actions(state, free)
    reviews = _review().sessions(state)
    whole = [sid for sid, s in reviews.items() if s.get("whole") and s["status"] != "done"]
    if any(reviews[a["id"]].get("whole") and reviews[a["id"]]["round"] == 0 for a in review_acts
           if a["action"] == "review") and _closeout_pending(wf, state):
        # The whole-change review comes after the closeout, which can still add fix tasks.
        review_acts = [a for a in review_acts if not (a["action"] == "review" and reviews[a["id"]].get("whole"))]
    acts += review_acts + _amend_action(state)
    held = [tid for tid, ts in state["tasks"].items() if ts["status"] == "pending" and tid in tasks
            and _integration_held(tasks[tid], scope, state)]
    everything_done = all(ts["status"] in DONE_STATES or tid in held for tid, ts in state["tasks"].items())
    before_whole = [sid for sid in _review().open_sessions(state)
                    if not (sid in whole and reviews[sid]["status"] == "pending")]
    if (everything_done and not state["in_flight"] and not state.get("blocked") and not before_whole):
        pending = _closeout_pending(wf, state)
        posts = [t for t in held if planmod.is_publish(tasks[t])]
        agents = [t for t in held if t not in posts]
        if pending:
            acts.append({"action": "closeout", "why": pending})
        elif whole:
            pass  # the whole-change review is next (its review action is above)
        elif agents:
            acts.append({"action": "final", "why": f" Posts last: it runs the final checks now, before "
                                                   f"{', '.join(agents)}; the report then reuses their results."})
        elif posts:
            acts += [{"action": "publish", "id": t} for t in posts]
        else:
            acts.append({"action": "final"})
    if (not any(a["action"] in ("dispatch", "fix", "review", "final", "closeout", "rerun", "publish", "gate")
                for a in acts)
            and state["in_flight"]):
        acts.append({"action": "wait", "ids": list(state["in_flight"])})
    return acts


GUIDE = {
    "scope": "Draft scope.json (`tp schema scope`), then `tp scope check`, then confirm it with the human.",
    "plan": "Write plan.json (`tp schema plan`), `tp plan check`, then `tp plan submit`. Every question for the "
            "human is asked and answered first (`tp ask` / `tp answer`): after submit the run is hands-off.",
    "plan_review": "`tp plan review`, then send the call it prints: an independent reviewer checks the plan against "
                   "the request, the answers, and the requirements. Its verdict is the gate — no human approval.",
    "plan_triage": "Plan review {id}: verify each finding against the plan and the request, then `tp plan triage "
                   "--accept-all` or `--dismiss F#=\"<reason>\"` for any you overrule.",
    "plan_fix": "Fix plan.json for the accepted findings, then `tp plan check`, `tp plan submit`, `tp plan review`.",
    "approve": "`tp approve` — the current revision passed its independent review; execution starts now.",
    "dispatch": "`tp dispatch {id}`, then send the call it prints.",
    "fix": "`tp dispatch {id}` (fix round), then send the call it prints.",
    "review": "`tp dispatch {id}`, then send the call it prints.",
    "check": "Fact-check {id}: read the sample `tp record` printed (or `tp sample {id}`) — tp already ran its "
             "tests and checks, so do not run them again; then `tp accept {id} --note \"...\"` or `tp reject {id} "
             "--reason \"...\"`.",
    "triage": "Triage {id}: `tp show {id} --part blocking`, check each against the source, then "
              "`tp triage {id} --accept-all`, or `--dismiss F# --reason \"...\"` (repeat the pair for a reason "
              "each) and/or `--assign F#=T##`.",
    "followup": "Decide {id} ({why}): pursue it (`tp research add ... --from {id}`) or "
                "`tp research dismiss {id} --reason \"...\"`.",
    "human": "Needs a decision{about}: {why}. First settle it yourself if the scope, plan, answers, or evidence "
             "already do, or if it is routine mechanics — a reply to a blocked hand-back (`tp resolve --task {id} "
             "--action answer --answer \"...\" --by manager`), another round for a task out of rounds (`tp resolve "
             "--task {id} --action retry --answer \"...\" --by manager`), a test fix "
             "(`--action tests`), a test correction (`tp rebaseline-tests {id} --by manager`), a gate you have "
             "shown false (`tp accept {id} --override`, even once its fix round is printed), a file the fix needs "
             "(`tp widen`), a fix task inside the allowance (`tp plan amend --delegated`), plumbing scope (`tp scope "
             "amend --delegated`); what strengthens the run past that — a reviewer, more tests, a bigger fix — goes "
             "to an independent reviewer (`tp plan|scope amend --review`). Only what changes the outcome, drops work, "
             "an agent, or a check, or writes "
             "outside the run goes to the human: `tp ask --about {id} --question \"...\"`, put it to them in plain "
             "text, and keep working everything else — never AskUserQuestion while agents are in flight. If "
             "settling it changes the plan, draft and check the amendment first (`tp plan amend`) and show its "
             "change in that one question; the same answer then goes to `tp resolve` and `tp plan amend --answer`.",
    "rerun": "{why}. Check the workspace for stranded edits, then `tp resolve --task {id} --action retry "
             "--answer \"...\" --by manager` and `tp dispatch {id}` (a fresh agent).",
    "wait": "Wait for {ids} to hand back; end your turn if nothing else is actionable.",
    "recheck": "`tp recheck {id}`: the sibling tasks whose red tests were its only failures have landed, so its "
               "tests and checks run again (no agent, no fix round).",
    "halting": "Halt requested: record {ids} as they hand back; dispatch nothing new.",
    "halted": "Halted. Tell the human where work stopped (`halt.json`), then stop. `tp resume --answer \"...\"` "
              "continues.",
    "publish": "`tp publish {id}` (a dry run: renders the reviewed draft and runs the pre-flight checks; the "
               "first one runs the final checks too — run that one in the background, like `tp final`), then "
               "do what it prints: post a pre-approved one with `--preapproved`; otherwise show the human and ask "
               "once — batch every publish that is ready into the same question, in plain text if agents are in "
               "flight — then `tp publish {id} --answer \"<their words>\"`.",
    "gate": "`tp gate {id}` prints the human's decision with what it approves; ask it once — in the same "
            "question as every other ready gate and publish, in plain text if agents are in flight — and keep "
            "working the rest. Then `tp gate {id} --answer \"<their words>\"` (go ahead), or `--reopen T##` with "
            "their words (changes first).",
    "final": "`tp final` (run it in the background: the final checks may take many minutes) — package checks and "
             "the report.{why}",
    "closeout": "Closeout ({why}): `tp closeout` lists what was noticed; classify each (`tp closeout --items N,M "
                "--class deferred|followup|observation --note \"<the issue and its consequence>\"`). Fix gaps in this "
                "run's own deliverables yourself inside the allowance (`tp plan amend --delegated`); follow-ups go to "
                "the report unasked. Only deferred work goes to the human: draft and check its fix first (`tp plan "
                "amend`) so `tp closeout --ask` shows the cost, ask once, then `tp closeout --decide --answer` (and "
                "`tp plan amend --answer` if they chose the fix).",
    "amend_review": "{id} ({why} amendment) is with the independent reviewer: when it replies, `tp advance {id} "
                    "--agent-id <its id>` (or `tp {why} amend --record --agent-id <its id>`) — its verdict applies, "
                    "drops, or escalates the change.",
    "done": "Report to the human from report.md.",
    "asked": "Waiting on the human for {why} — asked already; keep working the rest.",
}


def _liveness_warning(wf: Workflow, acts: List[Dict[str, Any]]) -> Optional[str]:
    """The manager's own stall detector: two looks in a row (`tp next`) with no event between them
    (no dispatch, record, accept, resolve, ...) and the same actions mean the workflow has stopped
    changing — whatever the clock says. Say so, and for how long."""
    with wf.locked():
        state = wf.load()
        fp = "|".join([state["phase"], ",".join(sorted(state["in_flight"])),
                       ",".join(f"{a['action']}:{a.get('id', '')}" for a in acts)])
        events = len(wf.events())
        mark = state.get("next_check") or {}
        same = mark.get("fp") == fp and mark.get("events") == events
        since = mark["since"] if same else now_iso()
        state["next_check"] = {"fp": fp, "events": events, "since": since}
        wf.save(state)
    if not same:
        return None
    idle = minutes_since(since)
    if state["in_flight"]:
        return (f"no state change for {idle:.0f} min while {', '.join(state['in_flight'])} "
                f"{'is' if len(state['in_flight']) == 1 else 'are'} in flight — end your turn and wait for the "
                "hand-back; `tp digest` shows whether its writes are still moving.")
    return (f"no state change for {idle:.0f} min and nothing is in flight — do the action above, or put what "
            "blocks it to the human.")


def _questions():
    from . import questions
    return questions


def _collapse_asked(state: Dict[str, Any], acts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A human action whose question is already out prints as one short line, not the full guide:
    real runs reprinted a parked item on every call until the manager filtered it with grep."""
    out = []
    for a in acts:
        qids = _questions().open_about(state, a["id"]) if a["action"] == "human" and a.get("id") else []
        if not qids and a["action"] == "human" and not a.get("id"):
            qids = _questions().open_about(state, "workflow")
        out.append({"action": "asked", "id": a.get("id"), "why": ", ".join(qids)} if qids else a)
    return out


def cmd_next(wf: Workflow, as_json: bool, probe: bool = True) -> str:
    """probe: count this as a look for the liveness check (`tp status` only reads)."""
    state = wf.load()
    acts = actions(wf, state)
    elapsed = minutes_since(state["created"])
    warnings = []
    if probe and state["phase"] != "DONE":
        idle = _liveness_warning(wf, acts)
        if idle:
            warnings.append(idle)
    if as_json:
        return json.dumps({"phase": state["phase"], "actions": acts, "elapsed_min": round(elapsed, 1),
                           "budget_minutes": state.get("budget_minutes"), "warnings": warnings})
    out = [_headline(state)] + [f"WARNING: {w}" for w in warnings]
    if state["phase"] == "PLANNING":
        line = _research().summary(state, scopemod.load_scope(wf))
        out += [line] if line else []
    waiting = _questions().status_line(state)
    out += [waiting] if waiting else []
    for a in _collapse_asked(state, acts):
        what = a["action"]
        label = f"{what} {a.get('id', '')}".strip()
        if a.get("agent"):
            label += f" ({a['step']} · {a['agent']}" + (f" · resume {a['agent_id']}" if a.get("agent_id") else "") + ")"
        about = f" about {a['id']}" if a.get("id") else ""
        out.append(f"→ {label}: " + GUIDE[what].format(id=a.get("id", ""), why=a.get("why", ""), about=about,
                                                      ids=", ".join(a.get("ids", []))))
    ready = [a["id"] for a in acts if a["action"] in ("dispatch", "fix", "review")]
    if len(ready) > 1:
        out.append(f"→ all at once: `tp dispatch {' '.join(ready)}` (one Bash call — never chain dispatches "
                   "with separators), then send every printed call in one message.")
    return "\n".join(out)


def _clock(state: Dict[str, Any]) -> str:
    """Time used against the budget: reported everywhere, enforced nowhere."""
    budget = state.get("budget_minutes")
    waited = gap_minutes(state["created"], None, waiting_gaps(state))
    return (f"{minutes_since(state['created']):.0f}" + (f" of {budget}" if budget else "") + " min"
            + (f" ({waited:.0f} waiting on the human or halted)" if waited >= 1 else ""))


def _headline(state: Dict[str, Any]) -> str:
    tasks = state["tasks"]
    done = sum(ts["status"] in DONE_STATES for ts in tasks.values())
    flight = ", ".join(f"{k} ({v['step']}, {minutes_since(v['since']):.0f}m)" for k, v in state["in_flight"].items())
    parts = [state["phase"], f"{done}/{len(tasks)} accepted" if tasks else None,
             f"in flight: {flight}" if flight else None, _clock(state)]
    return " · ".join(p for p in parts if p)


_GROUP_LABEL = {"code": "coding", "tests": "coding", "build": "coding", "kb": "writing", "docs": "writing", "tutorial": "writing",
                "education": "writing"}


def _progress(wf: Workflow, scope: Dict[str, Any], tasks: Dict[str, Dict[str, Any]], tid: str,
              fl: Dict[str, Any]) -> str:
    """Evidence an in-flight agent is moving, independent of the clock: the files in its own paths
    it has changed since dispatch, and whether they moved between the manager's looks. A look
    counts as evidence only when other work moved since the previous one (the event log grew):
    two looks seconds apart say nothing about an agent that is thinking or running a long test,
    so a lone agent is never called stuck by this probe. Updates fl["probe"]. Researchers and
    reviewers write only at the end."""
    if tid not in tasks or fl["step"] == "review" or not fl.get("snap"):
        return "writes its result file when it finishes, so the workspace is not its progress signal"
    task = tasks[tid]
    # Only the task's own paths: both sides enumerated by the same walk rules and the same match.
    now = _take(wf, _ws(scope, task["workspace"]), only=task["paths"])
    then = {k: v for k, v in snapshot.load(Path(fl["snap"])).items() if snapshot.matches(k, task["paths"])}
    changed = snapshot.diff(then, now)
    fp = hashlib.sha1(json.dumps([[c, now.get(c)] for c in changed]).encode()).hexdigest()
    events = len(wf.events())
    last = fl.get("probe")
    if not last or last["fp"] != fp:
        fl["probe"] = {"fp": fp, "events": events, "still": 0}
        verdict = "first look" if not last else "moved since your last look"
    elif events > last.get("events", events):
        still = last.get("still", 0) + 1
        fl["probe"] = {"fp": fp, "events": events, "still": still}
        verdict = (f"no change across {still} look{'s' if still > 1 else ''} while other work moved"
                   + (" — possibly stuck" if still >= 2 else ""))
    else:
        verdict = "too soon to tell: nothing else has moved since your last look"
    head = (f"{len(changed)} file{'s' if len(changed) != 1 else ''} in its paths changed since dispatch"
            if changed else "no writes in its paths yet")
    return f"{head}; {verdict}"


def cmd_digest(wf: Workflow) -> str:
    """The human-digestable status: progress by group, agent time by group, and each in-flight
    agent's evidence of progress. The manager shows it after each dispatch wave settles and
    whenever the human asks — then keeps working."""
    with wf.locked():
        state = wf.load()
        if state["phase"] == "DONE":
            return f"DONE — report: {wf.root / 'report.md'}. Present it to the human (answer-first)."
        scope = scopemod.load_scope(wf) if wf.scope_json.exists() else {"deliverables": []}
        tasks: Dict[str, Dict[str, Any]] = {}
        if state["phase"] == "EXECUTING":
            _, scope, tasks = _loaded(wf, state)
        agents = agent_minutes(wf)
        groups: Dict[str, List[int]] = {}
        mins: Dict[str, float] = {}
        for tid, t in tasks.items():
            kind = planmod.task_kind(t, scope) or "other"
            label = _GROUP_LABEL.get(kind, kind)
            g = groups.setdefault(label, [0, 0])
            g[0] += state["tasks"].get(tid, {}).get("status") in DONE_STATES
            g[1] += 1
            mins[label] = mins.get(label, 0.0) + agents.get(tid, 0.0)
        research = [r for r in state.get("recon", {}).values() if r["status"] != "dropped"]
        if research:
            groups["research"] = [sum(r["status"] == "done" for r in research), len(research)]
            mins["research"] = sum(m for k, m in agents.items() if k.startswith("R"))
        reviews = state.get("reviews", {})
        if reviews:
            groups["review"] = [sum(s["status"] == "done" for s in reviews.values()), len(reviews)]
            mins["review"] = sum(m for k, m in agents.items() if "/" in k)
        done = sum(ts["status"] in DONE_STATES for ts in state["tasks"].values())
        head = [state["phase"], f"{done}/{len(tasks)} tasks accepted" if tasks else None, _clock(state)]
        lines = [" · ".join(p for p in head if p)]
        if groups:
            lines.append("Progress: " + " · ".join(f"{label} {ok}/{n}" for label, (ok, n) in groups.items()))
            lines.append("Agent time: " + " · ".join(f"{label} {m:.0f}m" for label, m in
                                                    sorted(mins.items(), key=lambda kv: (-kv[1], kv[0]))))
        if state["in_flight"]:
            lines.append("In flight:")
            for tid, fl in state["in_flight"].items():
                lines.append(f"  {tid} {fl['step']} · {fl.get('agent') or 'resumed agent'} · "
                             f"{minutes_since(fl['since']):.0f}m — {_progress(wf, scope, tasks, tid, fl)}")
            wf.save(state)
        lines.append("Next: `tp next`.")
        return "\n".join(lines)


# --- dispatch ---------------------------------------------------------------------------------

def _slots(state: Dict[str, Any]) -> None:
    if len(state["in_flight"]) >= limit("max_in_flight"):
        raise TPError(f"{limit('max_in_flight')} agents are already in flight ({', '.join(state['in_flight'])}) — "
                      "wait for one to hand back.")


# Directories that are never deliverables in any repository. Deliberately narrow: `build/` or
# `dist/` can be real content (a KB article on the build lives under kb/build/), so anything
# ambiguous is left to the workspace's own .gitignore.
_EXPAND_IGNORE_PARTS = {".git", "node_modules", "__pycache__", ".venv", ".pnpm", ".pnpm-store", ".tox",
                        ".mypy_cache", ".pytest_cache"}


def _git_ignored(ws: Path, rels: List[str]) -> set:
    """The paths the workspace's own .gitignore excludes (none when ws is not a repository root)."""
    if not (ws / ".git").exists() or not rels:
        return set()
    try:
        proc = subprocess.run(["git", "-C", str(ws), "check-ignore", "--stdin"], input="\n".join(rels),
                              capture_output=True, text=True, timeout=30)
        return set(proc.stdout.splitlines())
    except (OSError, subprocess.SubprocessError):
        return set()


def _expand(ws: Path, patterns: List[str], cap: bool = False) -> List[Path]:
    """The files a task's paths name — never ignored trees (.git, node_modules, build output): a
    bare catch-all once swept them into record and review git argvs. cap: refuse an expansion
    past max_path_expand (at dispatch, before any agent starts)."""
    out: List[Path] = []
    for p in patterns:
        if any(ch in p for ch in "*?["):
            matches = sorted(x for x in ws.glob(p) if x.is_file())
        elif (ws / p).is_file():
            matches = [ws / p]
        elif (ws / p).is_dir():
            matches = sorted(x for x in (ws / p).rglob("*") if x.is_file())
        else:
            matches = []
        out += [x for x in matches if not _EXPAND_IGNORE_PARTS & set(x.relative_to(ws).parts)]
    rels = [x.relative_to(ws).as_posix() for x in out]
    ignored = _git_ignored(ws, rels)
    out = [x for x, r in zip(out, rels) if r not in ignored]
    if cap and len(out) > limit("max_path_expand"):
        sample = ", ".join(sorted(x.relative_to(ws).as_posix() for x in out)[:5])
        raise TPError(f"the task's paths expand to {len(out)} files (the cap is {limit('max_path_expand')}), e.g. "
                      f"{sample} — name the files the task writes; a directory path only when its files exist "
                      "at plan time (`tp widen` adds a path; a plan amendment replaces them).")
    return out


def _git_head(ws: Path) -> Optional[str]:
    """The workspace's git HEAD, or None outside a git work tree."""
    try:
        proc = subprocess.run(["git", "-C", str(ws), "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=15)
        return proc.stdout.strip() if proc.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _context(wf: Workflow, task: Dict[str, Any], scope: Dict[str, Any], plan: Dict[str, Any],
             state: Dict[str, Any]) -> Dict[str, Any]:
    wss = scopemod.workspaces(scope)
    ws = _ws(scope, task["workspace"])
    deliverables = {d["id"]: d for d in scope["deliverables"]}
    checks = []
    for c in task.get("checks", []):
        checks.append(planmod.BUILTIN_TASK_CHECKS.get(c) or f"`{plan['checks'][c]['cmd']}`")
    _expand(ws, task["paths"], cap=True)  # a runaway expansion is refused before any brief is written
    sources = []
    for s in task.get("sources", []):
        name, _, rel = str(s).partition(":")
        if name == "research":
            sources.append(f"{wf.root / 'recon' / (rel + '.json')} (research findings: read `answers`)")
        elif name == "wf":
            sources.append(str(wf.root / rel))
        else:
            sources.append(str(Path(wss[name]["path"]) / rel) if name in wss else s)
    writable = {str(Path(w["path"]).resolve()) for w in wss.values() if w["mode"] == "write"}
    rel = planmod.wf_rel
    return {
        "serves": "; ".join(f"{d} — {deliverables[d]['what']}" for d in task["serves"] if d in deliverables),
        "scope_md": wf.root / "scope.md",
        "write_paths": [str(wf.root / rel(p)) if rel(p) is not None else str(ws / p) for p in task["paths"]],
        # A read alias of a write workspace is not read-only: the task writes its own paths there.
        "readonly": [w["path"] for w in wss.values() if w["mode"] == "read"
                     and str(Path(w["path"]).resolve()) not in writable],
        "sources": sources or [str(ws)],
        "checks": checks,
        "tests_paths": [str(ws / p) for p in task.get("tests_paths", task["paths"])],
        "decisions": decision_lines(state, [task["id"]]),
        "conventions": [str(p) for p in planmod.conventions(plan, scope, wf.root)],
        "kind": planmod.task_kind(task, scope),
        "logs": [log for d in task.get("depends_on", []) for log in task_logs(wf, d)] + task_logs(wf, task["id"]),
    }


def cmd_dispatch(wf: Workflow, tid: str) -> str:
    with wf.locked():
        state = wf.load()
        if state.get("halt"):
            raise TPError("A halt was requested: nothing new starts. Record agents as they hand back; "
                          "`tp resume --answer \"<the human's words>\"` continues.")
        if tid.startswith("R"):
            return _research().dispatch(wf, state, tid, _slots)
        if "/" in tid:
            return _review().dispatch(wf, state, tid)
        if state["phase"] != "EXECUTING":
            raise TPError(f"Tasks are dispatched while EXECUTING; the workflow is {state['phase']}.")
        plan, scope, tasks = _loaded(wf, state)
        if tid not in tasks:
            raise TPError(f"{tid} is not a task in the approved plan.")
        ts, task = state["tasks"][tid], tasks[tid]
        if planmod.is_publish(task):
            raise TPError(f"{tid} is posted by the manager, never by an agent: `tp publish {tid}` (a dry run), then "
                          f"`tp publish {tid} --answer \"<the human's words>\"`.")
        if planmod.is_gate(task):
            raise TPError(f"{tid} is a gate — the human's decision, never an agent's: `tp gate {tid}` prints it to ask, "
                          f"then `tp gate {tid} --answer \"<their words>\"`.")
        if ts["status"] == "pending" and _deps_open(task, state):
            raise TPError(f"{tid} waits on {', '.join(_deps_open(task, state))} (not accepted yet).")
        if ts["status"] == "pending" and _integration_held(task, scope, state):
            raise TPError(f"{tid} is integration work: it runs once every other task is accepted and the final review "
                          "is done, so the external system is written once (`\"when\": \"anytime\"` in the plan opts out).")
        act = _action_for(tid, ts, task, scope, state)
        if act is None:
            raise TPError(f"{tid} is {ts['status']}; there is nothing to dispatch.")
        _slots(state)
        fresh = fresh_note(act["agent_id"])
        if fresh:
            act["agent_id"] = None
        step, run = act["step"], wf.run_dir(tid)
        run.mkdir(parents=True, exist_ok=True)
        ctx = _context(wf, task, scope, plan, state)
        if step == "review":
            n = ts["reviews"] + 1
            brief, result = run / f"brief-review-{n}.md", run / f"review-{n}.json"
            fix_result = run / "result-fix.json"
            if fix_result.exists() and load_json(fix_result, "fix result").get("disputes"):
                ctx["disputes"] = str(fix_result)
            text = briefs.review(task, n, ctx, result)
            label = f"review-{n}"
        elif step == "fix":
            rnd = ts["round"]
            brief, result = run / f"brief-fix-{rnd}.md", run / "result-fix.json"
            ctx.update(cap=_cap(ts), fix_expect=ts.get("fix_expect"), fixing=ts.get("fixing"))
            text = briefs.fix(task, rnd, ctx, _stale_guard(wf, task, scope, rnd) + ts["findings"], result,
                              same_agent=bool(act["agent_id"]))
            label = f"fix-{rnd}"
        else:
            brief, result = run / f"brief-{step}-{ts['round']}.md", run / f"result-{step}.json"
            if step == "build":
                ctx["red_cmd"] = tp_command(wf, "red", tid)
                if task.get("test_mode") == "existing" and not ts.get("tests_hash"):
                    # The tests that already prove the criterion: the build may add, never weaken.
                    ts["tests_hash"] = _tests_hash(task, scope)
                    _freeze_tests_baseline(wf, task, scope)
            text = briefs.author(task, step, ts["round"], ctx, result)
            label = f"{step}-{ts['round']}"
        if result.exists():
            result.unlink()
        brief.write_text(text)
        snap = run / f"snap-{label}.json"
        snapshot.save(snap, _take(wf, _ws(scope, task["workspace"])))
        for other in state["in_flight"].values():
            other.setdefault("concurrent", []).append(tid)
        if step == "build" and not ts.get("build_snap"):
            ts["build_snap"] = str(snap)  # production as it stood before the task: `tp red` compares to it
        state["in_flight"][tid] = {"step": step, "since": now_iso(), "snap": str(snap), "agent": act["agent"],
                                   "concurrent": list(state["in_flight"]), "from": ts["status"],
                                   "head": _git_head(_ws(scope, task["workspace"])),
                                   "wf_hashes": _wf_hashes(wf, task),
                                   "evidence": step != "review",  # the brief asked for acceptance evidence
                                   "red_cmd": ctx.get("red_cmd")}
        ts["status"], ts["step"] = "in_flight", step
        ts["started"] = ts["started"] or now_iso()
        wf.save(state)
        wf.event("dispatch", id=tid, step=step, agent=act["agent"], round=ts["round"])
        call = briefs.dispatch_line(act["agent"], f"{tid} {step}", briefs.prompt(brief, result),
                                    act["agent_id"], act.get("model"))
        return (f"DISPATCH {tid} · {step} · {act['agent']}\n" + (f"{fresh}\n" if fresh else "")
                + f"brief: {brief}\nsend: {call}\nthen, when it replies: tp advance {tid} --agent-id <its agent id>")


# --- record ---------------------------------------------------------------------------------

def _evidence_errors(data: Dict[str, Any], criteria: int) -> List[str]:
    """Each of the task's `criteria` Done-when items needs its own evidence in `acceptance`."""
    given = data.get("acceptance")
    if not isinstance(given, list) or not given:
        return [f"`acceptance` is missing: give each of the {criteria} numbered Done-when items its evidence, "
                "as [{\"criterion\": 1, \"evidence\": \"...\"}, ...]."]
    have: Dict[int, str] = {}
    for e in given:
        if isinstance(e, dict) and str(e.get("criterion", "")).strip().isdigit():
            have[int(str(e["criterion"]).strip())] = str(e.get("evidence") or "").strip()
    missing = [str(n) for n in range(1, criteria + 1) if not have.get(n)]
    return [f"`acceptance` has no evidence for criterion {', '.join(missing)} (of {criteria})."] if missing else []


def _validate_result(data: Any, tid: str, step: str, criteria: int = 0) -> List[str]:
    """criteria: how many Done-when items need evidence (0: none asked of this hand-back)."""
    if not isinstance(data, dict):
        return ["the result must be a JSON object."]
    errs = []
    if data.get("task") != tid or data.get("step") != step:
        errs.append(f"result must say task {tid!r} and step {step!r}.")
    if data.get("status") not in ("done", "blocked", "needs_input"):
        errs.append("status must be done, blocked, or needs_input.")
    if not str(data.get("summary", "")).strip():
        errs.append("summary is empty.")
    elif words(data["summary"]) > SUMMARY_CEILING:
        # Over 80 words is trimmed where it is shown: sending it back costs a round trip to an
        # agent whose context is often past 200k tokens. Only a runaway summary goes back.
        errs.append(f"summary is {words(data['summary'])} words; keep it to about 80.")
    for key in ("changed", "noticed", "questions"):
        if not isinstance(data.get(key, []), list):
            errs.append(f"`{key}` must be a list.")
    if data.get("status") == "needs_input" and not data.get("questions"):
        errs.append("needs_input needs `questions`.")
    if criteria and data.get("status") == "done":
        errs += _evidence_errors(data, criteria)
    return errs


def _trimmed(text: str, limit: int = SUMMARY_WORDS) -> str:
    """A hand-back summary as shown: its first `limit` words."""
    ws = str(text).split()
    return " ".join(ws[:limit]) + (" …" if len(ws) > limit else "")


# Results run ahead of the workflow lock (`tp record --long`), by (command, cwd): the locked record
# takes them instead of running the command again.
_PRERUN: Dict[Tuple[str, str], Tuple[bool, str]] = {}


def _execute(cmd: str, cwd: Path, timeout: int) -> Tuple[bool, str]:
    try:
        proc = subprocess.run(["bash", "-c", cmd], cwd=str(cwd), capture_output=True, text=True,
                              timeout=timeout)
        return proc.returncode == 0, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"


def _run_cmd(cmd: str, cwd: Path, log: Path, timeout: Optional[int] = None) -> Tuple[bool, str]:
    pre = _PRERUN.pop((cmd, str(cwd)), None)
    ok, output = pre if pre is not None else _execute(cmd, cwd, timeout or CHECK_TIMEOUT)
    log.write_text(f"$ {cmd}\n(cwd {cwd})\n\n{output}")
    tail = "\n".join(output.strip().splitlines()[-12:])
    return ok, tail


def _repos(scope: Dict[str, Any]) -> Dict[str, Path]:
    """Where citations resolve: every workspace. Documents describe the code the run is changing,
    which lives in a write workspace."""
    return {n: Path(w["path"]) for n, w in scopemod.workspaces(scope).items()}


def _task_files(wf: Workflow, task: Dict[str, Any], scope: Dict[str, Any]) -> List[Path]:
    """The files a task's paths name: workspace files, plus `wf:` files that exist."""
    ws = _ws(scope, task["workspace"])
    repo = [p for p in task.get("paths", []) if planmod.wf_rel(p) is None]
    drafts = [wf.root / planmod.wf_rel(p) for p in task.get("paths", []) if planmod.wf_rel(p) is not None]
    return _expand(ws, repo) + [d for d in drafts if d.is_file()]


def _wf_hashes(wf: Workflow, task: Dict[str, Any]) -> Dict[str, Optional[str]]:
    return {p: sha_file(wf.root / planmod.wf_rel(p)) for p in task.get("paths", []) if planmod.wf_rel(p) is not None}


def task_logs(wf: Workflow, tid: str) -> List[str]:
    """The latest test log and the latest log of each check a task's steps produced."""
    latest: Dict[str, Path] = {}
    for log in sorted(wf.run_dir(tid).glob("*.log"), key=lambda p: p.stat().st_mtime):
        kind = re.sub(r"-(tests|impl|author|fix|recheck|build|rebaseline)-\d+$", "", log.stem)
        latest[kind] = log
    return [str(p) for p in latest.values()]


# Finding states that say the code does the wrong thing: a test should catch it before the fix.
BEHAVIOUR_STATES = ("wrong", "broken", "gap", "missing")


FIX_ROUTES = ("impl", "tests-green", "tests-red")
# A finding about words, not behaviour (a missing or stale comment, a typo): no failing test can
# prove it, so it never opens a red-test round (real runs forced red on comment-only findings).
_WORDING = re.compile(r"\b(comments?|docstrings?|godoc|doc comment|package doc\w*|typos?|spelling|wording|"
                      r"misspell\w*)\b", re.I)
# Go's package overview: by convention the file holds only the package comment.
_DOC_FILE = re.compile(r"(^|/)doc\.go$")


def fix_route(task: Dict[str, Any], scope: Dict[str, Any], finding: Dict[str, Any]) -> str:
    """Who fixes a review finding on a task: `author` for non-code work; for code, `tests-green`
    (a test file: the test author, tests still passing), `tests-red` (a behaviour bug: the test
    author writes a failing test, then the code author fixes it), or `impl` (the code author)."""
    if not planmod.is_code(task, scope):
        return "author"
    if finding.get("route") in FIX_ROUTES:  # the manager's triage call (`--route F#=...`) wins
        return finding["route"]
    where = re.sub(r":\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*$", "", str(finding.get("where", "")).strip().strip("`"))
    ws = str(_ws(scope, task["workspace"]))
    rel = where.split(":", 1)[1] if ":" in where and where.split(":", 1)[0] in scopemod.workspaces(scope) else where
    rel = rel[len(ws) + 1:] if rel.startswith(ws + "/") else rel.lstrip("./")
    if task.get("tests_paths") and snapshot.matches(rel, task["tests_paths"]):
        return "tests-green"
    if (finding.get("state") in BEHAVIOUR_STATES and task.get("tests_paths")
            and not _WORDING.search(str(finding.get("issue", ""))) and not _DOC_FILE.search(rel)):
        return "tests-red"
    return "impl"


def fresh_note(agent_id: Optional[str]) -> Optional[str]:
    """Why a round goes to a fresh agent instead of resuming agent_id, or None to resume it: every
    resumed turn re-reads the whole context, and past the threshold a full brief costs less."""
    tokens = agent_context_tokens(agent_id)
    cap = limit("max_resume_context_tokens")
    if tokens is None or tokens <= cap:
        return None
    return (f"fresh agent: {agent_id}'s context is {tokens // 1000}k tokens (over {cap // 1000}k), so this round "
            "starts a new agent with the full brief instead of resuming it.")


def _changed_md(root: Path, base: Optional[str]) -> Tuple[Optional[set], set]:
    """What the workflow did to root since base (the HEAD recorded at approval), as resolved paths:
    (Markdown added, changed, copied or renamed to, plus untracked Markdown; every path deleted or
    renamed away). The first is None, meaning judge every file, when the workspace has no
    baseline (it is not under git) or git cannot say what changed.

    -z keeps git from quoting names it finds unusual (non-ASCII, quotes, backslashes), and
    --relative keeps paths relative to root when root is a subdirectory of the repository."""
    if not base:
        return None, set()
    # surrogateescape round-trips a file name that is not valid UTF-8 (possible on Linux) into a
    # Path instead of failing the whole check.
    diff = subprocess.run(["git", "-C", str(root), "diff", "--name-status", "-z", "--relative", base],
                          capture_output=True, text=True, errors="surrogateescape")
    new = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--others", "--exclude-standard"],
                         capture_output=True, text=True, errors="surrogateescape")
    if diff.returncode != 0 or new.returncode != 0:
        return None, set()
    changed, removed = [], []
    fields = diff.stdout.split("\0")
    i = 0
    while i < len(fields) and fields[i]:
        status = fields[i][0]
        if status in "RC":                       # status, source, destination
            if status == "R":
                removed.append(fields[i + 1])
            changed.append(fields[i + 2])
            i += 3
        else:                                    # status, path
            (removed if status == "D" else changed).append(fields[i + 1])
            i += 2
    changed += [r for r in new.stdout.split("\0") if r]
    return ({(root / r).resolve() for r in changed if r.endswith(".md")},
            {(root / r).resolve() for r in removed})


def _expand_cmd(cmd: str, task: Optional[Dict[str, Any]], scope: Dict[str, Any]) -> str:
    wss = scopemod.workspaces(scope)
    out = cmd.replace("{tp}", f"{shlex.quote(sys.executable)} {shlex.quote(str(TP_SCRIPT))}")
    for name, w in wss.items():
        out = out.replace("{ws:" + name + "}", shlex.quote(w["path"]))
    if task is not None:
        ws = _ws(scope, task["workspace"])
        files = _expand(ws, task["paths"])
        out = out.replace("{paths}", " ".join(shlex.quote(str(f)) for f in files))
        out = out.replace("{files}", " ".join(shlex.quote(str(f)) for f in _task_files_for(cmd, task, scope)))
        out = out.replace("{dirs}", " ".join(shlex.quote(d) for d in _task_dirs(cmd, task, scope)))
    return out


# A Go tool in a check command, bare or behind a wrapper (`tools/with-toolchain go vet`).
_GO_CMD = re.compile(r"(?:^|[\s;&|/(])(?:go|gofmt|golangci-lint|staticcheck)\s")


def _task_files_for(cmd: str, task: Dict[str, Any], scope: Dict[str, Any]) -> List[Path]:
    """{files}: the files the task writes in its workspace (never a workflow draft: a Jira draft
    names its ticket, which a tracker check forbids in the code). A Go tool gets only the Go ones:
    `gofmt` fails on YAML and testdata. A real run's gofmt and tracker checks never had this
    substituted and passed 14 times having checked nothing."""
    ws = _ws(scope, task["workspace"])
    files = _expand(ws, [p for p in _writes(task) if planmod.wf_rel(p) is None])
    return [f for f in files if f.suffix == ".go"] if _GO_CMD.search(cmd) else files


def _task_dirs(cmd: str, task: Dict[str, Any], scope: Dict[str, Any]) -> List[str]:
    """{dirs}: the task's own package directories, so a per-task check (`go vet {dirs}`) is not
    failed by another in-flight task's red tests elsewhere in the repository."""
    ws = _ws(scope, task["workspace"])
    rels = [f.relative_to(ws) for f in _expand(ws, task["paths"])] + [
        Path(p) for p in task["paths"] if planmod.wf_rel(p) is None and not any(ch in p for ch in "*?[")]
    # A directory the task deleted is no package to check (`go vet ./gone` fails on it), and
    # neither is one without code: fixtures (`testdata/`), templates, docs (`go vet` fails with
    # "no Go files" — real runs looped fix rounds on it). A Go tool needs Go files: a real run
    # handed `go vet` a scripts folder and a JavaScript mock folder (two fix rounds, two overrides).
    code = (lambda c: c.suffix == ".go") if _GO_CMD.search(cmd) else (lambda c: scopemod.is_code_file(str(c)))
    return sorted({"./" + r.parent.as_posix() if r.parent != Path(".") else "." for r in rels
                   if (ws / r.parent).is_dir() and "testdata" not in r.parent.parts
                   and any(code(c) for c in (ws / r.parent).iterdir() if c.is_file())})


def _task_checks(wf: Workflow, task: Dict[str, Any], scope: Dict[str, Any], plan: Dict[str, Any],
                 label: str, timeout: Optional[int] = None) -> List[str]:
    failures = []
    ws = _ws(scope, task["workspace"])
    for name in task.get("checks", []):
        log = wf.run_dir(task["id"]) / f"check-{name}-{label}.log"
        if name == "docs":
            files = [f for f in _task_files(wf, task, scope) if f.suffix == ".md"]
            errors, warnings, stats = docscheck.check(files, _repos(scope))
            log.write_text("\n".join(errors + [f"WARN {w}" for w in warnings]) or f"ok: {stats}")
            if errors:
                failures.append(f"Check `docs` failed ({len(errors)} problems; log {log}): " + "; ".join(errors[:6]))
        else:
            spec = plan["checks"][name]
            cwd = _ws(scope, spec["cwd"]) if spec.get("cwd") else ws
            if "{dirs}" in spec["cmd"] and not _task_dirs(spec["cmd"], task, scope):
                # Run bare, `go vet` would check the working directory instead: nothing of this
                # task's is there to check.
                log.write_text(f"skipped: none of the task's directories holds code for `{spec['cmd']}`")
                continue
            if "{files}" in spec["cmd"] and not _task_files_for(spec["cmd"], task, scope):
                # Run bare, `gofmt -l` and `grep` read stdin instead: nothing of this task's to check.
                log.write_text(f"skipped: the task writes no file for `{spec['cmd']}`")
                continue
            ok, tail = _run_cmd(_expand_cmd(spec["cmd"], task, scope), cwd, log, timeout)
            if _timed_out(ok, tail):
                failures.append(f"Check `{name}` {tail} (log {log})")
            elif not ok:
                failures.append(f"Check `{name}` failed (log {log}): {tail}")
    return failures


_TIMED_OUT = "timed out after"
_SLOW_CHECK = re.compile(r"^Check `[^`]+` timed out after \d+s")


def _timed_out(ok: bool, tail: str) -> bool:
    """A run that hit its time limit (`_run_cmd` reports it in place of output): it neither passed
    nor failed, so it is never red, never green, and never a finding."""
    return not ok and tail.startswith(_TIMED_OUT)


# A failure location in test or build output: `path/file.go:12:3` or `File "/abs/file.py", line 4`.
_FAIL_LOC = re.compile(r'([^\s"\'():,]+\.[A-Za-z0-9]+)(?::\d+|", line \d+)')
_STILL_RED = DONE_STATES + ("needs_check", "needs_review")


def _verification_failure(finding: str) -> bool:
    return finding.startswith("The tests are not green") or finding.startswith("Check `")


def _red_siblings(state: Dict[str, Any], ids: List[str]) -> List[str]:
    """The tasks among ids whose tests are still red: recorded, but not yet implemented and checked."""
    return [o for o in ids if o in state["tasks"] and state["tasks"][o]["status"] not in _STILL_RED]


def _sibling_red(wf: Workflow, state: Dict[str, Any], tasks: Dict[str, Dict[str, Any]], tid: str, ws: Path,
                 label: str) -> List[str]:
    """The sibling tasks that explain every failure location in this step's test and check logs:
    their tests share this task's test run or build (one Go package, one test discovery) and are red
    until their own implementations land, or the location is in a file of theirs (never this
    task's) that their implementation is still changing — a live run's build failed in a store file
    a sibling was mid-way through changing. Empty when any location is this task's or nobody's."""
    logs = [wf.run_dir(tid) / f"tests-{label}.log"] + sorted(wf.run_dir(tid).glob(f"check-*-{label}.log"))
    root = ws.resolve()
    locs: set = set()
    for log in logs:
        if not log.exists():
            continue
        for m in _FAIL_LOC.finditer(log.read_text(errors="replace")):
            p = Path(m.group(1))
            if p.is_absolute():
                try:
                    p = p.resolve().relative_to(root)
                except ValueError:
                    continue  # the toolchain's own frames (stdlib, module cache) belong to no task
            locs.add(p.as_posix())
    if not locs:
        return []
    owners: Dict[str, List[str]] = {}
    for other in _red_siblings(state, [o for o in state["tasks"] if o != tid]):
        ot, ots = tasks.get(other), state["tasks"][other]
        if not ot or ot.get("workspace") != tasks[tid]["workspace"] or not ot.get("tests_paths") \
                or not ots.get("tests_hash"):
            continue
        if ots["status"] == "blocked" and (ots.get("blocked") or {}).get("kind") == "sibling":
            continue  # its implementation is in, so its red tests are a real failure, and two waits would deadlock
        hit = [loc for loc in locs if snapshot.matches(loc, ot["tests_paths"])
               or (snapshot.matches(loc, ot["paths"]) and not snapshot.matches(loc, tasks[tid]["paths"]))]
        if hit:
            owners[other] = hit
    explained = {loc for hits in owners.values() for loc in hits}
    return sorted(owners) if locs <= explained else []


def cmd_red(wf: Workflow, tid: str) -> str:
    """Run by the code author inside a fused build round, after writing the tests and before any
    production code: the pipeline itself runs the tests and records red (or, for pin, green against
    today's code). The proof is the pipeline's observation, never the agent's word or a log it wrote."""
    with wf.locked():
        state = wf.load()
        plan, scope, tasks = _loaded(wf, state)
        fl, ts, task = state["in_flight"].get(tid), state["tasks"].get(tid), tasks.get(tid)
        if task is None or fl is None:
            raise TPError(f"{tid} is not in flight.")
        effective = ts["fixing"] if fl["step"] == "fix" else fl["step"]
        if effective != "build":
            raise TPError(f"`tp red` belongs to a fused build round; {tid} is in its {effective} step.")
        mode = task.get("test_mode", "red")
        if mode == "existing":
            raise TPError(f"{tid} proves itself with the existing tests (test_mode existing): no red run; just keep "
                          f"`{task['test_cmd']}` green.")
        ws = _ws(scope, task["workspace"])
        base = snapshot.load(Path(ts.get("build_snap") or fl["snap"]))
        now = _take(wf, ws)
        changed = snapshot.diff(base, now)
        excused = _others_paths(wf, state, tasks, tid, fl) + _head_moved(state, task["workspace"], ws, fl.get("head"))
        tests_paths = task.get("tests_paths") or []
        prod = [c for c in changed if snapshot.matches(c, task["paths"]) and not snapshot.matches(c, tests_paths)
                and not snapshot.matches(c, excused)]
        if prod:
            raise TPError(f"production files differ from before this task: {', '.join(prod[:8])}. Red is observed "
                          "with the tests alone: set those files back (keep your work aside), run `tp red` again, "
                          "then restore them.")
        if not any(snapshot.matches(c, tests_paths) for c in changed) and mode == "red":
            raise TPError(f"no test file has changed yet ({', '.join(tests_paths)}): write the tests first.")
        label = f"red-{ts['round']}"
        log = wf.run_dir(tid) / f"tests-{label}.log"
        since = fl["since"]
    ok, tail = _run_cmd(task["test_cmd"], ws, log)  # outside the lock: a slow suite blocks nobody
    with wf.locked():
        state = wf.load()
        fl, ts = state["in_flight"].get(tid), state["tasks"][tid]
        if fl is None or fl["since"] != since:
            raise TPError(f"{tid} was recorded or re-dispatched while its tests ran; nothing was recorded.")
        if _timed_out(ok, tail):
            raise TPError(f"`{task['test_cmd']}` {tail}: a run that does not finish is neither red nor green, so "
                          "nothing was recorded. Hand back `blocked` saying the task's test_cmd is too slow to run "
                          "here; the manager narrows it to this task's tests, then you run `tp red` again.")
        if mode == "red" and ok:
            raise TPError(f"`{task['test_cmd']}` passes: the tests are not red, so they do not prove the new behaviour. "
                          f"Make them fail for the reason the task names (log {log}).")
        if mode == "pin" and not ok:
            raise TPError(f"`{task['test_cmd']}` fails against today's code, so it does not pin today's behaviour: "
                          f"{tail}")
        ts["red"] = {"ts": now_iso(), "log": str(log), "round": ts["round"], "mode": mode}
        ts["tests_hash"] = _tests_hash(task, scope)
        _freeze_tests_baseline(wf, task, scope)
        wf.save(state)
    wf.event("red", id=tid, mode=mode)
    return (f"{tid}: {'red' if mode == 'red' else 'pinned'} recorded by the pipeline ({log}). Now implement until "
            f"`{task['test_cmd']}` passes; you may add tests, never loosen one.")


def cmd_recheck(wf: Workflow, tid: str) -> str:
    """Run a sibling-waiting task's tests and checks again once the siblings have landed: a pass
    moves it on with no fix round spent; a failure of its own opens the fix round it now earns."""
    with wf.locked():
        state = wf.load()
        plan, scope, tasks = _loaded(wf, state)
        ts, task = state["tasks"].get(tid), tasks.get(tid)
        if ts is None or ts["status"] != "blocked" or (ts["blocked"] or {}).get("kind") != "sibling":
            raise TPError(f"{tid} is not waiting on sibling tasks.")
        still = _red_siblings(state, ts["blocked"].get("on", []))
        if still:
            raise TPError(f"{tid} still waits on {', '.join(still)}: their tests are red until they land.")
        effective = ts["blocked"].get("effective") or _authoring_step(task, scope, ts)
        ws = _ws(scope, task["workspace"])
        label = f"recheck-{ts['round']}"
        findings: List[str] = []
        if effective in ("impl", "build"):  # a fused build runs its tests too, as `tp record` did
            ok, tail = _run_cmd(task["test_cmd"], ws, wf.run_dir(tid) / f"tests-{label}.log")
            if not ok:
                findings.append(f"The tests are not green: `{task['test_cmd']}` failed: {tail}")
        findings += _task_checks(wf, task, scope, plan, label)
        _pause(ts, ts["blocked"].get("since"))
        ts["blocked"] = None
        waits_on = _sibling_red(wf, state, tasks, tid, ws, label) if findings and all(
            _verification_failure(f) for f in findings) else []
        if waits_on:
            ts["status"] = "blocked"
            ts["blocked"] = {"kind": "sibling", "on": waits_on, "step": effective, "effective": effective,
                             "since": now_iso(), "summary": f"{tid} waits on {', '.join(waits_on)}"}
            out = f"{tid} still fails only in {', '.join(waits_on)}'s red tests; it keeps waiting."
        elif findings:
            ts["status"] = "needs_check"
            ts["fix_source"] = "gate"
            out = _fail(wf, ts, tid, findings, fixing=effective, ws=ws)
        else:
            if planmod.reviewer_for(task, scope):
                ts["status"] = "needs_review"
                out = f"{tid} passed its checks on recheck (no fix round spent).\nNext: review."
            else:
                out = (f"{tid} passed its checks on recheck (no fix round spent).\n"
                       + _checked(wf, state, scope, tasks, tid))
        wf.save(state)
        wf.event("recheck", id=tid, status=ts["status"])
        return out


def _tests_hash(task: Dict[str, Any], scope: Dict[str, Any]) -> Dict[str, Optional[str]]:
    ws = _ws(scope, task["workspace"])
    rels = task.get("tests_paths") or []
    return snapshot.hash_files(ws, [str(p.relative_to(ws)) for p in _expand(ws, rels)] or rels)


def _freeze_tests_baseline(wf: Workflow, task: Dict[str, Any], scope: Dict[str, Any]) -> None:
    """Keep a copy of the task's tests as they stood when recorded, so the implementation gate can
    tell growth (a new test a review asked for) from weakening."""
    ws = _ws(scope, task["workspace"])
    base = wf.run_dir(task["id"]) / "tests-baseline"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    for p in _expand(ws, task.get("tests_paths") or []):
        dest = base / p.relative_to(ws)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dest)


# A whole-line comment: rewording one weakens nothing (real runs spent fix rounds on reworded doc
# comments). A line starting with a bare `*` is code (Go's `*p = v`), not a block-comment body.
_COMMENT_LINE = re.compile(r"^(//|#|/\*|\*/|<!--|--\s)")
# Comments that are assertions or decide what compiles: Go build constraints, and an example
# test's `// Output:` block (every comment line after it is expected output).
_LIVE_COMMENT = re.compile(r"^(//(go:|\s*\+build\b)|#!?\[)")  # and Rust attributes: #[test], #[cfg(test)]
_OUTPUT_START = re.compile(r"^//\s*(Unordered output|Output):")


def _assertion_lines(text: str) -> List[str]:
    """A test file's lines that can carry a check, whitespace-normalized (gofmt realigns columns
    when a field is added): comments drop out, except the ones that are assertions."""
    out, in_output = [], False
    for raw in text.splitlines():
        ln = " ".join(raw.split())
        if not ln:
            continue
        if _OUTPUT_START.match(ln):
            in_output = True
            out.append(ln)
            continue
        if in_output and ln.startswith("//"):
            out.append(ln)
            continue
        in_output = False
        if _COMMENT_LINE.match(ln) and not _LIVE_COMMENT.match(ln):
            continue
        out.append(ln)
    return out


def _tests_weakened(old: Path, new: Path) -> Optional[str]:
    """None when an edit to a test file only added lines, reformatted them, or reworded comments;
    otherwise the lines it dropped without re-adding them (deleted tests, gutted assertions)."""
    if not old.is_file():
        return None
    if not new.is_file():
        return "the whole file was deleted"
    kept = set(_assertion_lines(new.read_text()))
    dropped = [ln for ln in _assertion_lines(old.read_text()) if ln not in kept]
    return "; ".join(ln[:70] for ln in dropped[:5]) or None


def _stale_guard(wf: Workflow, task: Dict[str, Any], scope: Dict[str, Any], rnd: int) -> List[str]:
    """Findings were computed when the round failed; accepted concurrent work may have landed
    outside the task's paths since. Name those files so the fix agent never reverts them on the
    strength of an older finding (a real run's fix agent reverted accepted sibling work)."""
    failed = wf.run_dir(task["id"]) / f"snap-failed-{rnd}.json"
    if not failed.exists():
        return []
    ws = _ws(scope, task["workspace"])
    since = snapshot.diff(snapshot.load(failed), _take(wf, ws))
    others = [c for c in since if not snapshot.matches(c, task["paths"])]
    if not others:
        return []
    return [f"Since this round failed, these files outside your paths changed — most likely accepted concurrent "
            f"work: {', '.join(others[:10])}. Leave them as they are; never revert them on the strength of an "
            "older finding."]


def _fail(wf: Workflow, ts: Dict[str, Any], tid: str, findings: List[str], fixing: str,
          ws: Optional[Path] = None) -> str:
    """ws: the task's workspace, snapshotted as it stood at the failure (the fix brief's
    staleness guard compares against it)."""
    ts["round"] += 1
    ts["fixing"] = fixing
    ts["findings"] = findings
    run = wf.run_dir(tid)
    (run / f"findings-{ts['round']}.json").write_text(json.dumps(findings, indent=1))
    if ws is not None:
        snapshot.save(run / f"snap-failed-{ts['round']}.json", _take(wf, ws))
    lines = [f"  - {f}" for f in findings]
    if ts["round"] > _cap(ts):
        ts["status"] = "blocked"
        wf.event("blocked", id=tid, reason="rounds")
        prior = run / f"findings-{ts['round'] - 1}.json"
        if prior.is_file() and json.loads(prior.read_text()) == findings:
            # The loop stopped converging: the last two rounds found exactly the same things. That,
            # not the round count or the clock, is the stall — say so.
            ts["blocked"] = {"kind": "rounds", "since": now_iso(),
                             "summary": f"{tid} failed rounds {ts['round'] - 1} and {ts['round']} with the same "
                                        "findings — the fix loop is not converging"}
            return "\n".join([f"BLOCKED {tid}: the same findings as the previous round — the fix loop is not "
                              "converging; the human decides (retry with a different approach, skip, or revise "
                              "the plan)."] + lines)
        ts["blocked"] = {"kind": "rounds", "summary": f"{tid} still fails after {_cap(ts)} fix rounds",
                         "since": now_iso()}
        return "\n".join([f"BLOCKED {tid}: still failing after {_cap(ts)} fix rounds — the human decides "
                          "(retry, skip, or revise the plan)."] + lines)
    ts["status"] = "needs_fix"
    return "\n".join([f"FAIL {tid} → fix round {ts['round']} of {_cap(ts)}:"] + lines)


def add_fix(wf: Workflow, state: Dict[str, Any], tid: str, findings: List[str], fixing: str,
            expect: Optional[str] = None, queued: Optional[List[str]] = None) -> str:
    """Send findings from outside the task's own steps (review triage, a reopen) to its author.
    They join a fix round that has not been dispatched yet; otherwise they open a round of their
    own that does not count against the task's cap. Refused while the task is in flight or blocked:
    rewriting its state then would pull it from under the agent or skip the human.

    fixing "tests" with expect: a review-routed round for the test author — "green" (test files
    only, the tests still pass) or "red" (a failing test for a behaviour bug). queued: the code
    author's findings, opened as the next round once the test round is recorded."""
    ts = state["tasks"][tid]
    if tid in state["in_flight"]:
        raise TPError(f"{tid} is in flight ({state['in_flight'][tid]['step']}); send it more fixes once it has "
                      "handed back and been recorded.")
    if ts["status"] in ("pending", "needs_impl", "blocked"):
        raise TPError(f"{tid} is {ts['status']}; it takes fixes once it is authored and not waiting on the human.")
    shown = [f"  - {f}" for f in findings + [q for q in queued or [] if q not in findings]]
    ts["fix_source"] = "review"  # a reviewer's or the manager's finding, never a gate's — even merged
    if ts["status"] == "needs_fix":
        if ts.get("fixing") == fixing:
            ts["findings"] = list(ts["findings"]) + findings
            if expect:
                ts["fix_expect"] = "red" if "red" in (expect, ts.get("fix_expect")) else "green"
            ts["queued"] = list(ts.get("queued", [])) + list(queued or [])
        elif fixing == "tests" and ts.get("fixing") == "impl":
            # Tests go first: the waiting code round becomes the follow-up of this test round.
            ts["queued"] = list(ts["findings"]) + list(queued or [])
            ts.update(fixing="tests", findings=list(findings), fix_expect=expect or "green")
        elif fixing == "impl" and ts.get("fixing") == "tests" and ts.get("fix_expect"):
            ts["queued"] = list(ts.get("queued", [])) + findings
        else:
            raise TPError(f"{tid}'s waiting fix round is for its {ts.get('fixing')} step; send these after it.")
        (wf.run_dir(tid) / f"findings-{ts['round']}.json").write_text(json.dumps(ts["findings"], indent=1))
        return "\n".join([f"{tid}: added to fix round {ts['round']} ({ts['fixing']}), not dispatched yet:"] + shown)
    if ts["status"] == "accepted":  # it sat finished until now; that was not work on it
        _pause(ts, ts.get("accepted"))
    ts["extra_rounds"] = ts.get("extra_rounds", 0) + 1
    if expect:
        ts["fix_expect"] = expect
        ts["queued"] = list(queued or [])
    task = next(t for t in planmod.load_plan(wf)["tasks"] if t["id"] == tid)
    out = _fail(wf, ts, tid, findings, fixing, ws=_ws(scopemod.load_scope(wf), task["workspace"]))
    if expect:
        out += ("\n  → the test author goes first (" + ("a failing test" if expect == "red" else "test files only")
                + ")" + (f"; then the code author: {len(queued or [])} finding(s) queued." if queued else "."))
    return out


def _pause(ts: Dict[str, Any], since: Optional[str]) -> None:
    """A span the task spent waiting (on the human, or finished and idle), left out of its minutes."""
    if since:
        ts.setdefault("paused", []).append([since, now_iso()])


def task_minutes(state: Dict[str, Any], ts: Dict[str, Any]) -> float:
    """Wall time from first dispatch to acceptance, less the spans the task or the whole workflow
    spent waiting on the human, halted, or finished."""
    if not ts.get("started"):
        return 0.0
    end = ts.get("accepted") if ts["status"] in DONE_STATES else None
    return max(0.0, minutes_since(ts["started"], end)
               - gap_minutes(ts["started"], end, ts.get("paused", []) + waiting_gaps(state)))


def agent_minutes(wf: Workflow) -> Dict[str, float]:
    """Each task's or review session's agent time: the sum of its hand-backs' minutes in flight."""
    out: Dict[str, float] = {}
    for e in wf.events():
        if e["kind"] == "record" and "minutes" in e:
            out[e["id"]] = out.get(e["id"], 0.0) + e["minutes"]
    return out


def _evidence(wf: Workflow, task: Dict[str, Any]) -> Optional[Dict[int, str]]:
    """The latest authoring hand-back's evidence, by Done-when number; None when it gave none."""
    results = sorted((p for p in wf.run_dir(task["id"]).glob("result-*.json")
                      if p.stem in ("result-author", "result-impl", "result-fix")), key=lambda p: p.stat().st_mtime)
    given = load_json(results[-1], "the agent's result").get("acceptance") if results else None
    if not isinstance(given, list):
        return None
    return {int(str(e.get("criterion")).strip()): str(e.get("evidence") or "") for e in given
            if isinstance(e, dict) and str(e.get("criterion", "")).strip().isdigit()}


def evidence_lines(wf: Workflow, task: Dict[str, Any]) -> List[str]:
    """Every Done-when item with its evidence (`tp show T## --part acceptance`)."""
    by_n = _evidence(wf, task) or {}
    return [f"{n}. {a} — {by_n.get(n, '(none given)')}" for n, a in enumerate(task.get("acceptance", []), 1)]


_CITE = re.compile(r"([\w./-]+\.[A-Za-z0-9]+):(\d+)(?:-(\d+))?")


def _quote(wf: Workflow, scope: Dict[str, Any], text: str, limit_cites: int = 3) -> List[str]:
    """The source lines a piece of evidence cites, so the fact check needs no reads of its own."""
    repos = dict(_repos(scope), wf=wf.root)
    out = []
    for path, a, b in _CITE.findall(text)[:limit_cites]:
        src, _ = docscheck.resolve(path, repos)
        if src is None:
            continue
        lines = src.read_text(errors="replace").splitlines()
        lo, hi = int(a), int(b or a)
        out += [f"    {path}:{i}: {lines[i - 1]}" for i in range(lo, min(hi, lo + 5, len(lines)) + 1)]
    return out


def _evidence_sample(wf: Workflow, task: Dict[str, Any], scope: Dict[str, Any], seed: str) -> List[str]:
    """One Done-when item for the manager's fact check — one whose evidence cites lines, when any
    does — with those lines quoted. The rest stays behind `tp show T## --part acceptance`: printing
    every item's evidence on every hand-back filled the manager's context in a real run."""
    by_n = _evidence(wf, task)
    if not by_n:
        return []
    given = [n for n in range(1, len(task["acceptance"]) + 1) if by_n.get(n)]
    if not given:
        return []
    pool = [n for n in given if _CITE.search(by_n[n])] or given
    pick = random.Random(seed).choice(pool)
    return ([f"fact-check sample — criterion {pick} of {len(task['acceptance'])} (does the evidence hold up? every "
             f"item: `tp show {task['id']} --part acceptance`):",
             f"  {pick}. {task['acceptance'][pick - 1]} — {by_n[pick]}"] + _quote(wf, scope, by_n[pick]))


def _sample(wf: Workflow, task: Dict[str, Any], scope: Dict[str, Any]) -> str:
    ws = _ws(scope, task["workspace"])
    files = _task_files(wf, task, scope)
    md = [f for f in files if f.suffix == ".md"]
    out = _evidence_sample(wf, task, scope, seed=f"{task['id']}:{len(list(wf.run_dir(task['id']).glob('result-*')))}")
    if md:
        cites = docscheck.sample(md, _repos(scope), n=2, seed=task["id"])
        out += (["citation sample (does each source line say what the sentence claims?):"] + cites
                if cites else ["sample: no path:line citations in the deliverable — read one section against its source."])
    code = [f for f in files if f.suffix != ".md" and wf.root not in f.parents]
    if code:
        stat = subprocess.run(["git", "-C", str(ws), "diff", "--stat", "--", *[str(f) for f in code]],
                              capture_output=True, text=True).stdout.strip()
        out += ["diff:", stat or "(untracked files: " + ", ".join(str(f.relative_to(ws)) for f in code[:8]) + ")"]
    return "\n".join(out)


def cmd_record(wf: Workflow, tid: str, agent_id: Optional[str], long: bool = False) -> str:
    """long: run the task's tests and checks with the final checks' time limit — for a suite that ran
    past the foreground limit, re-recorded in the background. A timeout proves nothing either way, so
    it never opens a fix round: the hand-back stays unrecorded until a run finishes."""
    if tid.startswith("amend/"):
        # The reviewer hands back like any agent; its verdict settles the amendment it judged.
        kind = (wf.load().get("amend_review") or {}).get("kind")
        if kind not in ("scope", "plan"):
            raise TPError(f"no amendment review is in flight ({tid}).")
        return (planmod.cmd_scope_amend(wf, None, record=True, agent_id=agent_id) if kind == "scope"
                else planmod.cmd_amend(wf, None, record=True, agent_id=agent_id))
    if long:
        _prerun_long(wf, tid)
    try:
        return _record_locked(wf, tid, agent_id, long)
    finally:
        _PRERUN.clear()


def _prerun_long(wf: Workflow, tid: str) -> None:
    """`tp record --long`: run the task's suite and command checks before taking the workflow lock,
    which every tp command waits on — held for a 45-minute suite, it would stall every other agent's
    hand-back. The locked record then takes these results (the agent has handed back: its files
    stand still)."""
    state = wf.load()
    plan, scope, tasks = _loaded(wf, state)
    task = tasks.get(tid)
    if task is None or tid not in state["in_flight"]:
        return  # the locked record says why
    ws = _ws(scope, task["workspace"])
    cmds = [(task["test_cmd"], ws)] if task.get("test_cmd") else []
    for name in task.get("checks", []):
        spec = plan.get("checks", {}).get(name)
        if name == "docs" or not isinstance(spec, dict):
            continue
        if ("{dirs}" in spec["cmd"] and not _task_dirs(spec["cmd"], task, scope)) or \
                ("{files}" in spec["cmd"] and not _task_files_for(spec["cmd"], task, scope)):
            continue  # skipped by the checks themselves
        cmds.append((_expand_cmd(spec["cmd"], task, scope), _ws(scope, spec["cwd"]) if spec.get("cwd") else ws))
    for cmd, cwd in cmds:
        _PRERUN[(cmd, str(cwd))] = _execute(cmd, cwd, FINAL_CHECK_TIMEOUT)


def _record_locked(wf: Workflow, tid: str, agent_id: Optional[str], long: bool) -> str:
    with wf.locked():
        state = wf.load()
        if tid.startswith("R"):
            return _research().record(wf, state, tid)
        if "/" in tid:
            return _review().record(wf, state, tid, agent_id)
        plan, scope, tasks = _loaded(wf, state)
        fl = state["in_flight"].get(tid)
        if tid not in tasks or fl is None:
            raise TPError(f"{tid} is not in flight (status {state['tasks'].get(tid, {}).get('status')}).")
        ts, task, step = state["tasks"][tid], tasks[tid], fl["step"]
        if step == "review":
            return _record_review(wf, state, scope, tasks, tid, fl, agent_id)
        effective = ts["fixing"] if step == "fix" else step
        _own_agent(state, tid, agent_id)
        if agent_id:
            ts["agents"][effective] = agent_id
        res_path = wf.run_dir(tid) / f"result-{step}.json"
        if not res_path.exists():
            raise TPError(f"{res_path} is missing — the agent must write it before you record.")
        data = load_json(res_path, "the agent's result")
        # Evidence is asked of authoring and implementation hand-backs whose brief asked for it (an
        # agent briefed before evidence existed is not refused for leaving it out).
        criteria = (len(task["acceptance"]) if fl.get("evidence") and effective in ("author", "impl", "build")
                    else 0)
        errs = _validate_result(data, tid, step, criteria)
        if errs:
            raise TPError(*[f"{res_path}: {e}" for e in errs],
                          "Ask the same agent to fix the file (SendMessage), then record again.")
        if fl.get("noticed_from") != str(res_path.stat().st_mtime_ns):
            # Once per hand-back: a record that stops on a timed-out suite runs again for the same file.
            for item in data.get("noticed", []):
                wf.noticed(tid, str(item))
            fl["noticed_from"] = str(res_path.stat().st_mtime_ns)
        state.get("lost", {}).pop(tid, None)  # a real hand-back ends a run of lost dispatches
        minutes = minutes_since(fl["since"])
        if data["status"] != "done":
            del state["in_flight"][tid]
            ts["status"] = "blocked"
            asks = data.get("questions") or [_trimmed(data["summary"])]
            # The dispatch's window (its start and who ran beside it) outlives the wait: the snapshot
            # is still the first dispatch's, so siblings that land while it waits are excused too.
            ts["blocked"] = {"kind": "input", "summary": f"{tid} {data['status']}: " + " | ".join(asks), "step": step,
                             "snap": fl["snap"], "head": fl.get("head"), "evidence": fl.get("evidence"),
                             "window": fl.get("window") or fl.get("since"),
                             "concurrent": list(fl.get("concurrent") or []), "since": now_iso()}
            wf.save(state)
            wf.event("record", id=tid, step=step, status=data["status"], minutes=round(minutes, 1))
            return "\n".join([f"{tid} {data['status']} — answer from scope.md / plan.json / decisions.md only if they "
                              "settle it; your answer may clarify the task but never drop or loosen a Done-when item — "
                              "that, or anything they do not settle, is the human's. Then `tp resolve --task "
                              f"{tid} --action answer --answer \"...\" --by manager|human`:"] + [f"  - {q}" for q in asks])

        findings: List[str] = []
        msgs: List[str] = []
        ws = _ws(scope, task["workspace"])
        changed = snapshot.diff(snapshot.load(Path(fl["snap"])), _take(wf, ws))
        # Integration work lands in Jira or GitHub, so an untouched workspace says nothing there.
        drafted = any(sha_file(wf.root / planmod.wf_rel(p)) != h for p, h in (fl.get("wf_hashes") or {}).items())
        # A pin task's implementation step may rightly change nothing (the task only characterizes
        # current behaviour): its green tests are the evidence, not a diff.
        pinned_noop = effective in ("impl", "build") and task.get("test_mode") == "pin"
        if (step != "fix" and not changed and not drafted and not pinned_noop
                and planmod.task_kind(task, scope) != "integration"):
            if fl.get("head") and _git_head(ws) != fl["head"]:
                # A commit-only task: history moved, the tree did not (snapshots skip .git).
                msgs.append("the tree is unchanged, but git history advanced (a commit) — counted as work.")
            else:
                # An authoring hand-back that changed nothing is a stall or a misreport, and saying so
                # needs no clock: it cannot misfire on an agent that is slow but working. Fix rounds
                # may legitimately land nothing (a disputed finding); reviews never write.
                findings.append("The agent reports done but wrote nothing: the workspace is unchanged since "
                                "dispatch. Check whether it worked in the wrong place; the fix round must "
                                "produce the work.")
        others = _others_paths(wf, state, tasks, tid, fl)
        moved = _head_moved(state, task["workspace"], ws, fl.get("head"))
        allowed = _writes(task) + others + moved
        off = [c for c in changed if not snapshot.matches(c, allowed)]
        if off:
            findings.append(f"Changed files outside this task's paths: {', '.join(off[:10])} — revert them; if the "
                            "task cannot be done without them, hand back `blocked` and say why.")
        findings += _readonly_changes(wf, state, scope)
        findings += _role_fence(task, effective, step, [c for c in changed if c not in off], others + moved)
        label = f"{step}-{ts['round']}"
        expect = ts.get("fix_expect") if step == "fix" else None
        limit_s = FINAL_CHECK_TIMEOUT if long else CHECK_TIMEOUT
        slow: List[str] = []  # timed-out runs: they prove nothing, so they are never findings
        if effective == "tests" and expect == "green":
            ok, tail = _run_cmd(task["test_cmd"], ws, wf.run_dir(tid) / f"tests-{label}.log", limit_s)
            if _timed_out(ok, tail):
                slow.append(f"`{task['test_cmd']}` {tail}")
            elif ok:
                msgs.append(f"tests still pass: `{task['test_cmd']}`.")
            else:
                findings.append(f"A test-files-only fix must leave the tests passing, and `{task['test_cmd']}` now "
                                f"fails: {tail}")
            if not findings and not slow:
                ts["tests_hash"] = _tests_hash(task, scope)
                _freeze_tests_baseline(wf, task, scope)
        elif effective == "tests":
            ok, tail = _run_cmd(task["test_cmd"], ws, wf.run_dir(tid) / f"tests-{label}.log", limit_s)
            if _timed_out(ok, tail):
                slow.append(f"`{task['test_cmd']}` {tail}")
            elif expect == "red" or task.get("test_mode", "red") == "red":
                if ok:
                    findings.append(f"The tests pass before any implementation, so they are not red: they do not "
                                    f"prove the new behaviour. `{task['test_cmd']}` passed.")
                else:
                    msgs.append(f"red: `{task['test_cmd']}` fails as expected.")
            elif not ok:
                findings.append(f"The characterization tests must pass against current code: {tail}")
            else:
                msgs.append("pinned: characterization tests pass.")
            if not findings and not slow:
                ts["tests_hash"] = _tests_hash(task, scope)
                _freeze_tests_baseline(wf, task, scope)
        elif effective in ("impl", "build"):
            if (effective == "build" and task.get("test_mode", "red") in ("red", "pin")
                    and not ts.get("red")):
                findings.append(f"The red run was never recorded: after writing the tests and before any production "
                                f"code, run `{fl.get('red_cmd') or 'tp red ' + tid}` — the pipeline must see the tests "
                                + ("fail" if task.get("test_mode", "red") == "red" else "pass against today's code")
                                + " before the implementation lands.")
            now_hash = _tests_hash(task, scope)
            if ts.get("tests_hash") and now_hash != ts["tests_hash"]:
                grown, gutted = [], []  # adding tests is allowed; weakening them is not
                base = wf.run_dir(tid) / "tests-baseline"
                for rel, h in now_hash.items():
                    if ts["tests_hash"].get(rel) != h:
                        # No baseline (tests recorded before baselines existed): any change counts.
                        dropped = (_tests_weakened(base / rel, ws / rel) if base.is_dir()
                                   else "a change with no recorded baseline to compare against")
                        (grown if dropped is None else gutted).append((rel, dropped))
                if gutted:
                    detail = "; ".join(f"{rel} dropped: {dropped}" for rel, dropped in gutted[:3])
                    findings.append(f"The tests were weakened during implementation (tests changed: "
                                    f"{', '.join(rel for rel, _ in gutted)} — {detail}). Restore them; the "
                                    "implementation may add tests but never remove or loosen one.")
                elif grown:
                    msgs.append(f"tests grew ({', '.join(rel for rel, _ in grown)}): new tests are allowed, and "
                                "the baseline moves to them.")
                    ts["tests_hash"] = now_hash
                    _freeze_tests_baseline(wf, task, scope)
            ok, tail = _run_cmd(task["test_cmd"], ws, wf.run_dir(tid) / f"tests-{label}.log", limit_s)
            if _timed_out(ok, tail):
                slow.append(f"`{task['test_cmd']}` {tail}")
            elif ok:
                msgs.append(f"green: `{task['test_cmd']}` passes.")
            else:
                findings.append(f"The tests are not green: `{task['test_cmd']}` failed: {tail}")
        if effective in ("author", "impl", "build"):
            checked = _task_checks(wf, task, scope, plan, label, limit_s)
            slow += [f for f in checked if _SLOW_CHECK.match(f)]
            findings += [f for f in checked if not _SLOW_CHECK.match(f)]
        if slow and not findings:
            # Nothing failed; something did not finish. A fix round cannot make a suite faster (a real
            # run sent three, and the manager overrode each after timing the suite by hand).
            wf.save(state)  # in flight still: the same hand-back is recorded again
            wf.event("record_slow", id=tid, step=step, long=long or None)
            if not long:
                return (f"{tid} NOT recorded: {'; '.join(slow)[:400]}. Past the {CHECK_TIMEOUT}s foreground limit "
                        "a run proves nothing either way, so no fix round. Run `tp record " + tid + " --long` in the "
                        f"background (Bash run_in_background; it allows {FINAL_CHECK_TIMEOUT // 60} min), then "
                        "`tp next`. Nothing else about the hand-back changes.")
            return (f"{tid} NOT recorded: even with {FINAL_CHECK_TIMEOUT // 60} min, {'; '.join(slow)[:400]}. Narrow "
                    "the task's test_cmd to its own tests (`-run` over their names, its own packages) with `tp plan "
                    f"amend` (it says who decides), then `tp record {tid}` again.")
        del state["in_flight"][tid]
        waits_on = (_sibling_red(wf, state, tasks, tid, ws, label)
                    if findings and effective in ("author", "impl", "build")
                    and all(_verification_failure(f) for f in findings) else [])
        if waits_on:
            ts["status"] = "blocked"
            ts["blocked"] = {"kind": "sibling", "on": waits_on, "step": step, "effective": effective,
                             "since": now_iso(),
                             "summary": f"{tid} waits on {', '.join(waits_on)}: its only failures are in their "
                                        "still-red tests"}
            out = (f"{tid} waits on {', '.join(waits_on)}: every failure is in their tests or files, which stay red "
                   "until their implementations land — not this task's failure, so no fix round. `tp next` offers "
                   f"`tp recheck {tid}` once they land. {' '.join(msgs)}".rstrip())
        elif findings:
            ts["fix_source"] = "gate"
            out = _fail(wf, ts, tid, findings, fixing=effective, ws=ws)
        elif effective == "tests" and expect and ts.get("queued"):
            # The failing test is in; the code author fixes the behaviour against it. This round
            # was opened by the review, so it does not count against the task's own cap.
            queued = ts.pop("queued")
            ts.pop("fix_expect", None)
            ts["extra_rounds"] = ts.get("extra_rounds", 0) + 1
            out = (f"{tid} failing test recorded; " + " ".join(msgs) + " Next: the code author fixes it.\n"
                   + _fail(wf, ts, tid, queued, fixing="impl", ws=ws))
        elif effective == "tests" and expect:
            ts.pop("fix_expect", None)
            ts.pop("queued", None)
            if planmod.reviewer_for(task, scope):
                ts["status"] = "needs_review"
                out = f"{tid} test fix recorded. " + " ".join(msgs) + " Next: review."
            else:
                out = f"{tid} test fix recorded. " + " ".join(msgs) + "\n" + _checked(wf, state, scope, tasks, tid)
        elif effective == "tests":
            ts["status"] = "needs_impl"
            out = f"{tid} tests recorded; " + " ".join(msgs) + " Next: implementation."
        elif planmod.reviewer_for(task, scope):
            ts["status"] = "needs_review"
            out = f"{tid} passed its checks. " + " ".join(msgs) + " Next: review."
        else:
            out = f"{tid} passed its checks. " + " ".join(msgs) + "\n" + _checked(wf, state, scope, tasks, tid)
        if not findings and (changed or drafted):
            out += _stale_docs(wf, state, plan, scope, tasks, tid, ws, changed)
        wf.save(state)
        wf.event("record", id=tid, step=step, status=ts["status"], minutes=round(minutes, 1), round=ts["round"])
        return out


def _others_paths(wf: Workflow, state: Dict[str, Any], tasks: Dict[str, Dict[str, Any]], tid: str,
                  fl: Dict[str, Any]) -> List[str]:
    """Files another task in this workspace may have changed while this one ran: every task in
    flight at any moment of this dispatch — at dispatch, dispatched since, or in flight now — not
    only the tasks in flight at dispatch. Real runs charged a task with a sibling's edits whenever
    the sibling was dispatched later, or when this task was resumed after a question. Tasks that
    did not run in this window stay guarded: nothing else should touch their files."""
    ws = tasks[tid]["workspace"]
    ran = set(fl.get("concurrent", [])) | set(state["in_flight"])
    # `window`: the first dispatch's start, kept across a needs_input wait (the snapshot is that old).
    since = fl.get("window") or fl.get("since") or ""
    ran |= {e.get("id") for e in wf.events() if e.get("kind") == "dispatch" and e.get("ts", "") >= since}
    return [p for o in sorted(x for x in ran if isinstance(x, str)) if o != tid and o in tasks
            and tasks[o].get("workspace") == ws for p in _writes(tasks[o]) if planmod.wf_rel(p) is None]


def _writes(task: Dict[str, Any]) -> List[str]:
    """Every file a task may write: its `paths` and its `tests_paths`. The plan schema does not
    ask for a test file in both, and a real run (KUB-1339) listed them only in `tests_paths`:
    a fence of `paths` alone then charged every code task with its own tests and its siblings'."""
    return list(dict.fromkeys(list(task.get("paths") or []) + list(task.get("tests_paths") or [])))


def _head_moved(state: Dict[str, Any], ws_name: str, ws: Path, head: Optional[str]) -> List[str]:
    """Files a declared HEAD move brought in while the task ran (the human rebased the worktree):
    history, not this agent's edits. Only commits the manager recorded with `tp head-moved` count —
    nothing in the workspace (author dates, ref names) can vouch for a commit, since an agent can
    write those too. Empty when HEAD has not moved or no move was declared."""
    trusted = {sha for m in state.get("head_moves", []) if m.get("workspace") == ws_name for sha in m.get("shas", [])}
    now = _git_head(ws)
    if not trusted or not head or not now or now == head:
        return []
    log = subprocess.run(["git", "-C", str(ws), "rev-list", f"{head}..{now}"], capture_output=True, text=True)
    out: List[str] = []
    for sha in (log.stdout.split() if log.returncode == 0 else []):
        if sha not in trusted:
            continue
        files = subprocess.run(["git", "-C", str(ws), "diff-tree", "--no-commit-id", "--name-only", "-r",
                                "--relative", sha], capture_output=True, text=True)
        out += [f for f in files.stdout.splitlines() if f] if files.returncode == 0 else []
    return sorted(set(out))


def cmd_head_moved(wf: Workflow, ws_name: str, reason: str, answer: str = "") -> str:
    """Declare that a workspace's HEAD moved under the agents in flight (a rebase onto upstream, a
    commit the human made): the commits it brought in are excused from those tasks' write fences.
    Run it right after the move; later commits are not covered. Listed for the final review."""
    if words(reason) < 4:
        raise TPError("--reason must say what moved HEAD (a rebase onto main, the human's commit, ...).")
    if len(answer.strip()) < 2:
        raise TPError("--answer needs the human's words: a HEAD move is the human's act (they rebased or "
                      "committed), and only they can vouch that its commits are not an agent's.")
    with wf.locked():
        state = wf.load()
        _, scope, tasks = _loaded(wf, state)
        if ws_name not in scopemod.workspaces(scope):
            raise TPError(f"{ws_name} is not a workspace of this run.")
        ws = _ws(scope, ws_name)
        now = _git_head(ws)
        heads = {fl.get("head") for tid, fl in state["in_flight"].items()
                 if tid in tasks and tasks[tid]["workspace"] == ws_name and fl.get("head")}
        shas: List[str] = []
        for h in sorted(heads - {now}):
            log = subprocess.run(["git", "-C", str(ws), "rev-list", f"{h}..{now}"], capture_output=True, text=True)
            shas += log.stdout.split() if log.returncode == 0 else []
        if not shas:
            return f"{ws_name}: HEAD has not moved under any task in flight; nothing to excuse."
        shas = sorted(set(shas))
        state.setdefault("head_moves", []).append({"workspace": ws_name, "to": now, "shas": shas, "reason": reason,
                                                   "ts": now_iso()})
        wf.save(state)
    wf.decision(f"head moved in {ws_name}", f"{reason} ({len(shas)} commits up to {str(now)[:10]}) — {answer}",
                who="human")
    wf.event("head_moved", workspace=ws_name, commits=len(shas))
    return (f"{ws_name}: {len(shas)} commit(s) up to {str(now)[:10]} excused from the write fences of the tasks in "
            "flight; the report and the final review list them.")


def _own_agent(state: Dict[str, Any], tid: str, agent_id: Optional[str]) -> None:
    """An agent works one task. Sending a new task to an earlier task's agent (seen live: a Jira
    task at 348k tokens of context handed a second task) makes every turn re-read the old work."""
    if not agent_id:
        return
    for other, ts in state["tasks"].items():
        if other != tid and agent_id in ts.get("agents", {}).values():
            raise TPError(f"agent {agent_id} already worked {other}; {tid} needs a fresh agent — send the "
                          f"`Agent(...)` call `tp dispatch {tid}` printed, then record with that agent's id.")
    for sid, s in state.get("reviews", {}).items():
        if s.get("agent_id") == agent_id:
            raise TPError(f"agent {agent_id} is the {sid} reviewer; {tid} needs a fresh agent — send the "
                          f"`Agent(...)` call `tp dispatch {tid}` printed.")


def _role_fence(task: Dict[str, Any], effective: str, step: str, changed: List[str], concurrent: List[str]) -> List[str]:
    """Inside the task's own paths, each step still writes only its role's files: the test step
    writes tests, and a code author's fix round leaves the tests to the test author."""
    tests = task.get("tests_paths")
    if not tests:
        return []
    mine = [c for c in changed if not snapshot.matches(c, concurrent)]
    if effective == "tests":
        prod = [c for c in mine if not snapshot.matches(c, tests)]
        if prod:
            return [f"The test step writes only test files, and it changed {', '.join(prod[:8])} — revert them: "
                    "production code is the code author's next step."]
    elif effective == "impl" and step == "fix":
        touched = [c for c in mine if snapshot.matches(c, tests)]
        if touched:
            return [f"A code author's fix round changed test files ({', '.join(touched[:8])}); they belong to the "
                    "test author — revert them, and dispute a wrong test in `disputes` so the pipeline routes it "
                    "to the test author."]
    return []


def _doc_problems(wf: Workflow, task: Dict[str, Any], scope: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    md = [f for f in _task_files(wf, task, scope) if f.suffix == ".md"]
    if not md:
        return [], []
    errors, warnings, _ = docscheck.check(md, _repos(scope))
    return errors, warnings


def _stale_docs(wf: Workflow, state: Dict[str, Any], plan: Dict[str, Any], scope: Dict[str, Any],
                tasks: Dict[str, Dict[str, Any]], tid: str, ws: Path, changed: List[str]) -> str:
    """Accepted documents that cite a file this step just changed are checked again; one whose
    citations now break, or newly fail to support their sentences, is reopened at once — not left
    for the closeout (in a real run, a nine-task amendment existed largely to re-point them)."""
    touched = {(ws / c).resolve() for c in changed}
    out = []
    for other, ts in state["tasks"].items():
        task = tasks.get(other)
        if other == tid or task is None or ts["status"] != "accepted" or "docs" not in task.get("checks", []):
            continue
        md = [f for f in _task_files(wf, task, scope) if f.suffix == ".md"]
        cited = set()
        for doc in md:
            for c in docscheck.citations(doc, docscheck.prose_lines(doc.read_text(errors="replace"))):
                src, _ = docscheck.resolve(c.path, _repos(scope))
                if src is not None:
                    cited.add(src.resolve())
        hit = sorted(str(p.relative_to(ws)) for p in cited & touched)
        if not hit:
            continue
        errors, warnings = _doc_problems(wf, task, scope)
        new = errors + [w for w in warnings if w not in ts.get("doc_doubts", [])]
        if not new:
            continue
        note = (f"{tid}'s change to {', '.join(hit)} left citations here stale: " + "; ".join(new[:6])
                + " — re-point them at the lines that now say it.")
        try:
            out.append(add_fix(wf, state, other, [note], fixing=_authoring_step(task, scope, state["tasks"][other])))
        except TPError as exc:
            out.append(f"{other} cites {', '.join(hit)}, which {tid} changed, but could not be reopened: {exc}")
    return ("\nStale citations — reopened:\n" + "\n".join(out)) if out else ""


def _validate_review(data: Any, tid: str) -> List[str]:
    if not isinstance(data, dict) or data.get("task") != tid:
        return [f"the review must be a JSON object for task {tid!r}."]
    errs = []
    if data.get("verdict") not in ("pass", "changes"):
        errs.append("verdict must be pass or changes.")
    findings = data.get("findings", [])
    if not isinstance(findings, list):
        return errs + ["findings must be a list."]
    for f in findings:
        for key in ("id", "state", "where", "issue"):
            if not f.get(key):
                errs.append(f"finding {f.get('id', '?')} needs `{key}`.")
        if not isinstance(f.get("blocking"), bool):
            errs.append(f"finding {f.get('id', '?')} needs `blocking`: true or false.")
    blocking = [f.get("id") for f in findings if f.get("blocking") is True]
    if blocking and data.get("verdict") == "pass":
        errs.append(f"verdict 'pass' contradicts blocking finding {', '.join(map(str, blocking))}.")
    if not blocking and data.get("verdict") == "changes":
        errs.append("verdict 'changes' needs at least one blocking finding.")
    return errs


def _record_review(wf: Workflow, state: Dict[str, Any], scope: Dict[str, Any], tasks: Dict[str, Dict[str, Any]],
                   tid: str, fl: Dict[str, Any], agent_id: Optional[str]) -> str:
    ts, task = state["tasks"][tid], tasks[tid]
    n = ts["reviews"] + 1
    path = wf.run_dir(tid) / f"review-{n}.json"
    data = load_json(path, "the review")
    errs = _validate_review(data, tid)
    if errs:
        raise TPError(*[f"{path}: {e}" for e in errs], "Ask the reviewer to fix the file, then record again.")
    if agent_id:
        ts["agents"]["review"] = agent_id
    ts["reviews"] = n
    for item in data.get("noticed", []):
        wf.noticed(f"{tid} review", str(item))
    ws = _ws(scope, task["workspace"])
    changed = snapshot.diff(snapshot.load(Path(fl["snap"])), _take(wf, ws))
    allowed: List[str] = []
    for other in fl.get("concurrent", []):
        if other in tasks and tasks[other]["workspace"] == task["workspace"]:
            allowed += tasks[other]["paths"]
    edits = [c for c in changed if not snapshot.matches(c, allowed)]
    del state["in_flight"][tid]
    findings = [f"{path.name} {f['id']} ({f['state']}) at {f['where']}: {f['issue']}"
                + (f" Fix: {f['fix']}" if f.get("fix") else "") for f in data["findings"] if f["blocking"]]
    if edits:
        findings.append(f"The reviewer changed {', '.join(edits[:8])}; reviews must not edit — check that content "
                        "against the task and its sources.")
    state.get("lost", {}).pop(tid, None)  # a real hand-back ends a run of lost dispatches
    if findings:
        out = _fail(wf, ts, tid, findings, fixing=_authoring_step(task, scope, ts), ws=ws)
    else:
        ts["status"] = "needs_check"
        minor = len(data["findings"])
        out = f"{tid} review {n} passed ({minor} non-blocking notes in {path.name}).\n" + _sample(wf, task, scope)
    wf.save(state)
    wf.event("record", id=tid, step="review", status=ts["status"], minutes=round(minutes_since(fl["since"]), 1))
    return out


# --- manager verdicts and exceptions --------------------------------------------------------

OVERRIDABLE = ("needs_fix", "blocked")


def cmd_accept(wf: Workflow, tids: List[str], note: str, override: bool = False) -> str:
    """Accept fact-checked hand-backs — one call takes the whole wave, one note covers them all.

    override: accept a task whose gate findings the manager has shown to be false (a sandbox
    artefact, a sibling's edit, a check that cannot pass in this environment), with the evidence
    in the note. Real runs instead skipped seven finished tasks "manager-verified" after gate loops,
    or asked the human. Every override is listed in the report and read by the final review."""
    if isinstance(tids, str):
        tids = [tids]
    if override and words(note) < 8:
        raise TPError("--override needs --note with the evidence that the gate is wrong (what it flagged, and why "
                      "that is not a defect): the report and the final review show it.")
    with wf.locked():
        state = wf.load()
        _, scope, tasks = _loaded(wf, state)
        want = OVERRIDABLE if override else ("needs_check",)
        # A gate's fix round is dispatched the moment the gate fails (`tp advance` prints its call); the
        # manager who proves the finding false before sending that call must still reach the override —
        # a real run otherwise spent ten calls on lost/retry/dispute to free the task.
        unsent = {t for t in tids if override and (state["in_flight"].get(t) or {}).get("step") == "fix"
                  and state["tasks"].get(t, {}).get("fix_source") == "gate"}
        bad = [t for t in tids if (state["tasks"].get(t, {}).get("status") not in want and t not in unsent)
               or (override and t in state["in_flight"] and t not in unsent)
               or (override and state["tasks"][t].get("fix_source") != "gate")
               or (override and state["tasks"][t]["status"] == "blocked"
                   and (state["tasks"][t].get("blocked") or {}).get("kind") not in ("rounds", "sibling"))]
        if bad:
            raise TPError(*[f"{t} is not {'failing a gate (needs_fix from its own checks, or blocked on rounds) — a fix a review or you asked for is done, not overridden' if override else 'awaiting your fact check'} "
                            f"(status {state['tasks'].get(t, {}).get('status')})." for t in bad])
        out = []
        for tid in tids:
            ts = state["tasks"][tid]
            if override:
                state.setdefault("overrides", []).append({"task": tid, "ts": now_iso(), "note": note,
                                                          "findings": list(ts.get("findings") or [])})
                if ts["status"] == "blocked":
                    _pause(ts, (ts.get("blocked") or {}).get("since"))
                if tid in unsent:
                    state["in_flight"].pop(tid)
                ts.update(blocked=None, fixing=None, findings=[])
            out.append(_accept_one(wf, state, scope, tasks, tid, note, override=override)
                       + (" Its fix round is cancelled: if you already sent that call, TaskStop the agent."
                          if tid in unsent else ""))
        wf.save(state)
        if override:
            for tid in tids:
                wf.decision(f"accept {tid} over its gate findings", note, who="manager")
        return "\n".join(out)


def _accept_one(wf: Workflow, state: Dict[str, Any], scope: Dict[str, Any], tasks: Dict[str, Dict[str, Any]],
                tid: str, note: str, override: bool = False, auto: Optional[str] = None) -> str:
    """Mark one task accepted (the caller holds the lock and saves): the record every acceptance
    leaves, whether the manager fact-checked it, overrode its gate, or a review covers it (auto)."""
    ts = state["tasks"][tid]
    ts.update(status="accepted", accepted=now_iso(), note=note)
    task = tasks.get(tid)
    if task and "docs" in task.get("checks", []):
        # What the docs check already doubts at acceptance: a later code change is judged
        # only on doubts it adds (see _stale_docs).
        ts["doc_doubts"] = _doc_problems(wf, task, scope)[1]
    mins = task_minutes(state, ts)
    wf.event("accept", id=tid, minutes=round(mins, 1), wall=round(minutes_since(ts["started"]), 1),
             override=override or None, auto=auto)
    return (f"accepted {tid}{' over its gate findings' if override else ''} ({mins:.0f} min, "
            f"{ts['round']} fix rounds)" + (f" — no fact check needed: {auto} reviews it." if auto else "."))


def _covering_review(state: Dict[str, Any], scope: Dict[str, Any], task: Dict[str, Any]) -> Optional[str]:
    """The review session that will still read this code task's change: one that has not started
    (a batch review, or the whole-change review, which waits for every batch), or one waiting on this
    task's fix to verify it. None for documents and other non-code work, which no code lens reads."""
    if not planmod.is_code(task, scope) or os.environ.get("TP_AUTO_ACCEPT") == "0":  # 0: older test scenarios
        return None
    for sid, s in sorted(_review().sessions(state).items()):
        if task["id"] not in (s.get("tasks") or []):
            continue
        if s["status"] == "pending" or (s["status"] == "waiting_fixes" and task["id"] in s.get("fix_tasks", [])):
            return sid
    return None


def _checked(wf: Workflow, state: Dict[str, Any], scope: Dict[str, Any], tasks: Dict[str, Dict[str, Any]],
             tid: str) -> str:
    """A task whose gates all passed and that waits on no reviewer of its own: accepted at once when a
    review session will read it anyway, else left for the manager's fact check (with the sample).
    In a real run (KUB-1339) the manager re-read the diff and re-ran the tests of every code task
    before accepting it, at ~450k tokens of context a turn, and the batch reviews then read it again."""
    task = tasks[tid]
    sid = _covering_review(state, scope, task)
    if sid:
        return _accept_one(wf, state, scope, tasks, tid, f"auto-accepted: every gate passed; {sid} reviews it",
                           auto=sid)
    state["tasks"][tid]["status"] = "needs_check"
    return _sample(wf, task, scope)


def cmd_reject(wf: Workflow, tid: str, reason: str) -> str:
    with wf.locked():
        state = wf.load()
        _, scope, tasks = _loaded(wf, state)
        ts = state["tasks"].get(tid)
        if ts is None or ts["status"] != "needs_check":
            raise TPError(f"{tid} is not awaiting your fact check.")
        out = _fail(wf, ts, tid, [f"Manager fact check: {reason}"], fixing=_authoring_step(tasks[tid], scope, ts),
                    ws=_ws(scope, tasks[tid]["workspace"]))
        wf.save(state)
        wf.event("reject", id=tid)
        return out


def cmd_sample(wf: Workflow, tid: str) -> str:
    state = wf.load()
    _, scope, tasks = _loaded(wf, state)
    if tid not in tasks:
        raise TPError(f"{tid} is not a task in the plan.")
    return _sample(wf, tasks[tid], scope)


def cmd_exception(wf: Workflow, summary: str, tid: Optional[str]) -> str:
    with wf.locked():
        state = wf.load()
        if tid:
            ts = state["tasks"].get(tid)
            if ts is None:
                raise TPError(f"{tid} is not a task.")
            prior = ts["status"]
            if tid in state["in_flight"]:  # the manager stopped this agent: free its slot
                prior = state["in_flight"].pop(tid).get("from", "pending")
            ts["blocked"] = {"kind": "exception", "summary": summary, "prior": prior, "since": now_iso()}
            ts["status"] = "blocked"
        else:
            state["blocked"] = {"kind": "exception", "summary": summary, "since": now_iso()}
        wf.save(state)
        wf.event("exception", id=tid, summary=summary)
        return "raised — stop and put it to the human; record their answer with `tp resolve ... --by human`."


# The status that re-runs a dispatched step from the start.
_STEP_STATUS = {"tests": "pending", "build": "pending", "author": "pending", "impl": "needs_impl", "fix": "needs_fix",
                "review": "needs_review"}


def cmd_lost(wf: Workflow, tid: str, summary: str) -> str:
    """A dispatch that ended without a hand-back: the session restarted, the agent crashed, or the
    manager stopped it (TaskStop) on evidence it was stuck. Free the slot, keep the dead span out of
    the task's minutes, forget the agent (it is never resumed), and block the task until a re-run
    is decided. The manager may re-run it; after max_lost_retries losses in a row only the human
    may — a task that keeps dying needs a different approach, not another identical try."""
    with wf.locked():
        state = wf.load()
        ts = state["tasks"].get(tid)
        if ts is None:
            raise TPError(f"{tid} is not a task. A lost research or review agent keeps its slot: send the call "
                          f"`tp dispatch` printed for it to a fresh agent, then `tp record {tid}` as usual.")
        fl = state["in_flight"].get(tid)
        if fl is None:
            raise TPError(f"{tid} is not in flight (status {ts['status']}) — nothing to mark lost; "
                          f"`tp exception --task {tid} --summary \"...\"` covers everything else.")
        del state["in_flight"][tid]
        step = fl["step"]
        ts["agents"].pop(ts["fixing"] if step == "fix" else step, None)
        _pause(ts, fl["since"])
        streak = state.setdefault("lost", {})
        streak[tid] = n = streak.get(tid, 0) + 1
        cap = limit("max_lost_retries")
        ts["blocked"] = {"kind": "exception", "lost": n, "prior": fl.get("from") or _STEP_STATUS[step],
                         "since": now_iso(), "summary": f"{tid}'s {step} dispatch was lost ({n} in a row): {summary}"
                         + (" — the loss breaker leaves the next step to the human (resolve with --by human)"
                            if n >= cap else "")}
        ts["status"] = "blocked"
        wf.save(state)
        wf.event("lost", id=tid, step=step, streak=n, summary=summary)
        out = (f"{tid} marked lost — its slot is free and the {minutes_since(fl['since']):.0f} lost minutes stay out "
               f"of its time. Check the workspace for stranded edits, then `tp resolve --task {tid} --action retry "
               f"--answer \"...\" --by manager` and `tp dispatch {tid}`: the re-dispatch is fresh (a new agent and "
               "brief; the lost one is never resumed).")
        if n >= cap:
            out += (f"\nLOSS BREAKER: {tid} has been lost {n} times in a row. Stop re-running it: ask the human "
                    "(change the approach, split the task, or skip it) and resolve with --by human. A real "
                    "hand-back resets the count.")
        return out


def _keep_decision(holder: Dict[str, Any], question: str, answer: str, by: Optional[str]) -> None:
    """Keep an answer with its question on the task (or the workflow) it settles, so every later
    brief for that work quotes it; decisions.md alone never reaches an agent."""
    holder.setdefault("decisions", []).append({"q": question, "a": answer, "by": by, "ts": now_iso()})


def decision_lines(state: Dict[str, Any], tids: List[str]) -> List[str]:
    """The decisions a brief for these tasks must carry: the workflow's, then each task's own."""
    out = []
    for prefix, holder in [("", state)] + [(f"{t}: " if len(tids) > 1 else "", state["tasks"].get(t, {}))
                                           for t in tids]:
        for d in holder.get("decisions", []):
            out.append(f"{prefix}{d['q']} → {d['a']}" + (f" ({d['by']})" if d.get("by") else ""))
    return out


def cmd_rebaseline_tests(wf: Workflow, tid: str, answer: str, by: str) -> str:
    """A test change made outside the test step becomes the baseline the implementation gate
    compares against: an honest correction (a fixture import, a wrong expectation, tests of code the
    task deleted, a rename after an interface moved). The manager may make it — in real runs every
    such question to the human came back "yes", hours later. What guards against loosening a test
    to pass faulty work: the old baseline is kept, the reason is recorded, and the final review is
    told to judge each correction against it. A task whose only failure was that weakening finding
    is re-run at once."""
    if by not in ("human", "manager"):
        raise TPError("--by must be human or manager.")
    if by == "manager" and words(answer) < 6:
        raise TPError("--answer must say what was wrong with the old tests and why the change is a correction, "
                      "not a loosening (the final review checks it against the kept baseline).")
    with wf.locked():
        state = wf.load()
        plan, scope, tasks = _loaded(wf, state)
        task, ts = tasks.get(tid), state["tasks"].get(tid)
        if task is None or ts is None or not planmod.is_code(task, scope) or not task.get("tests_paths"):
            raise TPError(f"{tid} is not a code task with tests.")
        if tid in state["in_flight"]:
            raise TPError(f"{tid} is in flight; rebaseline once it has handed back and been recorded.")
        if not ts.get("tests_hash"):
            raise TPError(f"{tid}'s tests are not recorded yet; its test step sets the first baseline.")
        before, now = ts["tests_hash"], _tests_hash(task, scope)
        moved = sorted(rel for rel in set(before) | set(now) if before.get(rel) != now.get(rel))
        run = wf.run_dir(tid)
        n = len(state.get("test_corrections", [])) + 1
        kept = run / f"tests-baseline-before-{n}"
        if (run / "tests-baseline").is_dir() and not kept.exists():
            shutil.copytree(run / "tests-baseline", kept)
        ts["tests_hash"] = now
        _freeze_tests_baseline(wf, task, scope)
        state.setdefault("test_corrections", []).append({"task": tid, "files": moved, "reason": answer, "by": by,
                                                         "before": str(kept), "ts": now_iso()})
        out = [f"{tid}: the tests as they stand are the new baseline ({', '.join(moved) or 'unchanged'}); the old one "
               f"is kept at {kept} for the final review."]
        only_weakened = ts["status"] == "needs_fix" and ts.get("findings") and all(
            str(f).startswith("The tests were weakened") for f in ts["findings"])
        if only_weakened:
            ws = _ws(scope, task["workspace"])
            label = f"rebaseline-{ts['round']}"
            ok, tail = _run_cmd(task["test_cmd"], ws, run / f"tests-{label}.log")
            findings = [] if ok else [f"The tests are not green: `{task['test_cmd']}` failed: {tail}"]
            findings += _task_checks(wf, task, scope, plan, label)
            if findings:
                ts["fix_source"] = "gate"
                out.append(_fail(wf, ts, tid, findings, fixing=ts.get("fixing") or _authoring_step(task, scope, ts), ws=ws))
            else:
                ts.update(fixing=None, findings=[])
                if planmod.reviewer_for(task, scope):
                    ts["status"] = "needs_review"
                    tail_msg = ""
                else:
                    tail_msg = "\n" + _checked(wf, state, scope, tasks, tid)
                out.append(f"{tid}'s only failure was that weakening finding; re-run green, so no fix round is spent."
                           + tail_msg)
        wf.save(state)
        wf.decision(f"rebaseline tests {tid}", f"{answer} ({', '.join(moved) or 'no file changed'})", who=by)
        wf.event("rebaseline_tests", id=tid, files=moved, by=by)
        return "\n".join(out)


def cmd_resolve(wf: Workflow, tid: Optional[str], action: str, answer: str, by: Optional[str] = None) -> str:
    """by: who decided (human or manager); left out, the record attributes the decision to nobody."""
    with wf.locked():
        out = _resolve(wf, wf.load(), tid, action, answer, by)
        wf.decision(f"resolve {tid or 'workflow'} {action}", answer, who=by)  # only once it has taken effect
        return out


def _resolve(wf: Workflow, state: Dict[str, Any], tid: Optional[str], action: str, answer: str,
             by: Optional[str]) -> str:
    if not tid:
        blocked = state.pop("blocked", None)
        if blocked is None:
            raise TPError("Nothing is blocked at workflow level; pass --task for a task or --review for a "
                          "review session.")
        _keep_decision(state, blocked["summary"], answer, by)
        wf.save(state)
        return "resolved — continue with `tp next`."
    ts = state["tasks"].get(tid)
    if ts is None:
        raise TPError(f"{tid} is not a task.")
    lost = (ts.get("blocked") or {}).get("lost", 0) if ts["status"] == "blocked" else 0
    if lost >= limit("max_lost_retries") and by != "human":
        raise TPError(f"{tid} has been lost {lost} times in a row — the loss breaker leaves the next step to the "
                      "human. Ask them, then resolve with --by human.")
    if action == "reopen":
        if ts["status"] in ("pending", "needs_impl"):
            raise TPError(f"{tid} is {ts['status']}; there is no authored work to reopen.")
        _, scope, tasks = _loaded(wf, state)
        if ts["status"] == "blocked":  # the reopen is how this block is resolved
            _pause(ts, ts["blocked"].get("since"))
            ts.update(status="needs_check", blocked=None)
        note = "Reopened" + (f" by the {by}" if by else "") + f": {answer}"
        out = add_fix(wf, state, tid, [note], fixing=_authoring_step(tasks[tid], scope, ts))
        state.pop("final_failed", None)
        wf.save(state)
        return f"{tid} reopened. `tp next`.\n{out}"
    if action == "tests":
        # A test that must change after the test step goes to the test author as its own round:
        # the code author may not edit tests, and the impl gate reads any reworded line as weakening.
        _, scope, tasks = _loaded(wf, state)
        if not planmod.is_code(tasks[tid], scope) or not tasks[tid].get("tests_paths"):
            raise TPError(f"{tid} has no tests to route: --action tests applies to code tasks.")
        if ts["status"] in ("pending", "needs_impl") or not ts.get("tests_hash"):
            raise TPError(f"{tid}'s tests are not recorded yet; its test step writes them.")
        implemented = not (ts["status"] == "blocked" and (ts["blocked"] or {}).get("step") == "impl")
        if ts["status"] == "blocked":
            _pause(ts, ts["blocked"].get("since"))
            ts.update(status="needs_check", blocked=None)
        note = "Test change" + (f" ruled by the {by}" if by else "") + f": {answer}"
        queued = [] if implemented else [f"Implement against the corrected tests ({answer})."]
        out = add_fix(wf, state, tid, [note], fixing="tests", expect="green" if implemented else "red",
                      queued=queued)
        state.pop("final_failed", None)
        wf.save(state)
        return f"{tid}: the test change goes to the test author. `tp next`.\n{out}"
    if ts["status"] != "blocked":
        raise TPError(f"{tid} is not blocked (status {ts['status']}).")
    kind, since = ts["blocked"]["kind"], ts["blocked"].get("since")
    if action == "skip" and by != "human":
        raise TPError(f"skipping {tid} drops agreed work — only the human decides that. Ask them, then resolve with "
                      "--by human.")
    if action == "skip":
        _pause(ts, since)
        ts.update(status="skipped", blocked=None, note=answer)
    elif action == "retry" and kind == "rounds":
        _keep_decision(ts, ts["blocked"]["summary"], answer, by)
        _pause(ts, since)
        ts["extra_rounds"] += 1
        ts.update(status="needs_fix", blocked=None)
    elif action == "answer" and kind == "input":
        _slots(state)
        _keep_decision(ts, ts["blocked"]["summary"], answer, by)
        _pause(ts, since)
        step = ts["blocked"]["step"]
        blocked = ts["blocked"]
        state["in_flight"][tid] = {"step": step, "since": now_iso(), "snap": blocked["snap"],
                                   "window": blocked.get("window"),
                                   "agent": None,
                                   "concurrent": sorted(set(blocked.get("concurrent") or []) | set(state["in_flight"])),
                                   "from": _STEP_STATUS[step], "head": blocked.get("head"),
                                   "evidence": blocked.get("evidence")}
        ts.update(status="in_flight", blocked=None)
        effective = ts["fixing"] if step == "fix" else step
        agent_id = ts["agents"].get(effective)
        result = wf.run_dir(tid) / f"result-{step}.json"
        if result.exists():
            result.unlink()
        msg = (f"Answer: {answer} — continue your task, rewrite {result}, and reply with exactly one line: "
               f"RESULT {result}")
        wf.save(state)
        target = f"SendMessage(to={json.dumps(agent_id)}, message={json.dumps(msg)})" if agent_id else \
            f"(no agent id recorded — resend the brief with the answer) {json.dumps(msg)}"
        return f"{tid} back in flight.\nsend: {target}\nthen: tp record {tid}"
    elif action in ("answer", "retry") and kind == "exception":
        # Back to where it stood; a lost dispatch's step re-runs fresh (its agent was forgotten).
        _keep_decision(ts, ts["blocked"]["summary"], answer, by)
        _pause(ts, since)
        ts.update(status=ts["blocked"]["prior"], blocked=None)
    else:
        raise TPError(f"action {action!r} does not apply to a {kind} block; use "
                      + {"rounds": "retry or skip", "input": "answer or skip",
                         "exception": "answer, retry, or skip",
                         "sibling": "skip, or `tp recheck` once its siblings land"}.get(kind, "skip") + ".")
    wf.save(state)
    return f"{tid} resolved ({action}). `tp next`."


# --- gates ----------------------------------------------------------------------------------

def cmd_gate(wf: Workflow, tid: str, answer: Optional[str] = None, reopen: Optional[str] = None) -> str:
    """A human decision the plan scheduled (a sign-off): print it once the work before it is accepted
    and reviewed, then record the human's answer. Go-ahead opens it — every later brief quotes the
    answer; changes first (`--reopen`) sends their words to the named upstream tasks as a fix round and
    keeps it closed until those are accepted again."""
    with wf.locked():
        state = wf.load()
        if state["phase"] != "EXECUTING":
            raise TPError(f"gates are asked while EXECUTING; the workflow is {state['phase']}.")
        plan, scope, tasks = _loaded(wf, state)
        task, ts = tasks.get(tid), state["tasks"].get(tid)
        if task is None or not planmod.is_gate(task):
            raise TPError(f"{tid} is not a gate task (plan.json: `\"gate\": {{\"ask\": \"...\"}}`).")
        if ts["status"] in DONE_STATES:
            raise TPError(f"{tid} is already decided — {ts.get('note')}.")
        waits = _gate_waits_on(tid, tasks, state)
        if waits:
            raise TPError(f"{tid} is not ready to ask: it waits on {', '.join(waits)}. `tp next` offers it once they "
                          "are done — the human signs off accepted, reviewed work.")
        ask = str(task["gate"].get("ask", "")).strip()
        upstream = sorted(planmod._ancestors(tasks)[tid])
        if answer is None:
            if reopen:
                raise TPError("--reopen needs --answer \"<the human's words>\": their words are the fix round's finding.")
            first = not ts.get("asked")
            ts.setdefault("asked", now_iso())
            wf.save(state)
            if first:
                wf.event("gate_ask", id=tid)
            files = [f"`{p}`" for u in upstream for p in tasks[u].get("paths", [])]
            reviewed = [sid for sid, s in state.get("reviews", {}).items() if set(upstream) & set(s.get("tasks") or [])]
            return "\n".join([
                f"GATE {tid} — {task['title']}",
                f"Ask the human: {ask}",
                f"It decides on {', '.join(upstream)}" + (f" ({', '.join(files[:8])})" if files else "")
                + (f", reviewed in {', '.join(reviewed)}." if reviewed else "."),
                "Ask once: put every ready gate and publish in the same question — AskUserQuestion only while nothing "
                "is in flight, otherwise plain text at the end of your turn — and keep working the rest.",
                f"Go ahead: `tp gate {tid} --answer \"<their words>\"`. Changes first: `tp gate {tid} --reopen "
                f"{upstream[-1] if upstream else 'T##'} --answer \"<their words>\"` (a fix round for the named tasks; "
                "the gate is offered again once they are accepted)."])
        if not answer.strip():
            raise TPError("--answer needs the human's words, verbatim.")
        if reopen:
            ids = [x.strip() for x in reopen.split(",") if x.strip()]
            bad = [x for x in ids if x not in upstream]
            if bad:
                raise TPError(f"--reopen {', '.join(bad)}: only the work {tid} decides on can be reopened "
                              f"({', '.join(upstream) or 'none'}).")
            outs = [add_fix(wf, state, x, [f"Gate {tid} — the human asked for changes: {answer}"],
                            fixing=_authoring_step(tasks[x], scope, state["tasks"][x])) for x in ids]
            ts.pop("asked", None)
            _keep_decision(state, f"Gate {tid}: {ask}", f"changes first — {answer}", "human")
            wf.save(state)
            wf.decision(f"gate {tid}: changes first ({', '.join(ids)})", answer, who="human")
            wf.event("gate", id=tid, reopened=ids)
            return "\n".join([f"{tid} stays closed: {', '.join(ids)} reopened with the human's words."] + outs)
        ts.update(status="accepted", accepted=now_iso(), note=f"the human: {answer}")
        ts.pop("asked", None)
        _keep_decision(state, f"Gate {tid}: {ask}", answer, "human")  # every later brief quotes it
        wf.save(state)
        wf.decision(f"gate {tid}: {ask}", answer, who="human")
        wf.event("gate", id=tid)
        return f"{tid} open — the human: {answer}"


# --- final ----------------------------------------------------------------------------------

# --- closeout -------------------------------------------------------------------------------

CLOSEOUT_CLASSES = ("deferred", "followup", "observation")
_UNDECIDED = "deferred work awaits the human's decision"


def _noticed_text(raw: str) -> str:
    """A noticed item without its `(source, ×N)` marker, normalized: the key its class is kept under."""
    m = re.match(r"\([^)]*\) (.*)$", raw, re.S)
    return " ".join((m.group(1) if m else raw).split())


# Notes agents leave about their own work, which never need the human: classified by the script.
_CHATTER = re.compile(r"^\s*implementation note\b|\bsibling task\b.*\b(left|untouched|unstaged|not mine)\b|"
                      r"\bleft (it |them )?untouched\b|^\s*(fyi|for the record)\b", re.I)


def _closeout_marks(state: Dict[str, Any], wf: Optional[Workflow] = None) -> Dict[str, Dict[str, Any]]:
    """The class of each noticed item: the manager's, else the script's for plain chatter."""
    marks = dict(state.get("closeout", {}).get("items", {}))
    if wf is not None:
        for raw in wf.noticed_items():
            text = _noticed_text(raw)
            if text not in marks and _CHATTER.search(text):
                marks[text] = {"class": "observation", "auto": True}
    return marks


def _closeout_unclassified(wf: Workflow, state: Dict[str, Any]) -> int:
    return len({_noticed_text(r) for r in wf.noticed_items()} - set(_closeout_marks(state, wf)))


def _closeout_pending(wf: Workflow, state: Dict[str, Any]) -> Optional[str]:
    """What still keeps the report back, or None: noticed items nobody classified, or deferred work
    without the human's recorded answer. A follow-up (outside this run's scope) is a suggestion the
    report lists — no question: a real run spent its last two questions on hygiene noticed in passing."""
    unclassified = _closeout_unclassified(wf, state)
    if unclassified:
        return f"{unclassified} noticed item(s) unclassified"
    open_ = {_noticed_text(r) for r in wf.noticed_items()}
    if (any(v.get("class") == "deferred" for k, v in _closeout_marks(state, wf).items() if k in open_)
            and not state.get("closeout", {}).get("decision")):
        return _UNDECIDED
    return None


def _item_numbers(spec: str, count: int) -> List[int]:
    """`1,3,5-7` → [1, 3, 5, 6, 7]."""
    out: List[int] = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        lo, _, hi = part.partition("-")
        if not lo.isdigit() or (hi and not hi.isdigit()):
            raise TPError(f"--items {spec!r}: give numbers and ranges, e.g. 1,3,5-7.")
        out += list(range(int(lo), int(hi or lo) + 1))
    bad = [n for n in out if not 1 <= n <= count]
    if bad:
        raise TPError(f"there is no noticed item #{bad[0]} ({count} open) — `tp closeout` lists them.")
    return sorted(set(out))


def _closeout_amendment(wf: Workflow, state: Dict[str, Any]) -> List[str]:
    """The drafted fix, when one is checked, for the closeout's one question: the human then decides
    with its cost in view, and one answer settles the closeout and approves the amendment."""
    draft = wf.root / planmod.AMEND_JSON
    if not draft.exists():
        return ["", "To offer fixing them now, draft and check the amendment first (`tp plan amend`), then run "
                "`--ask` again: the question then shows the fix and its cost, and one answer approves it."]
    if (state.get("amend_checked") or {}).get("sha") != sha_file(draft):
        return ["", "plan-amend.json is not checked as it stands: `tp plan amend`, then `--ask` again."]
    try:
        approved, plan_draft, scope, changes, _ = planmod._checked_draft(wf, state)
    except TPError as exc:
        return ["", "The drafted amendment does not check: " + "; ".join(exc.lines[:3])]
    remaining, _ = planmod._remaining(plan_draft, scope, state)
    return (["", f"The fix, as drafted and checked — {'; '.join(changes)}:"] + planmod._change_lines(approved, plan_draft)
            + remaining + ["If they choose it, the same answer goes to `tp closeout --decide --answer` and `tp plan "
                           "amend --answer` — one question, both gates."])


def cmd_closeout(wf: Workflow, item: Optional[int] = None, cls: Optional[str] = None, note: Optional[str] = None,
                 decide: bool = False, answer: Optional[str] = None, ask: bool = False,
                 items_spec: Optional[str] = None, show_all: bool = False) -> str:
    """The gate between the last acceptance and the report: classify every noticed item, and put
    deferred or follow-up work to the human once, their answer recorded. Without it, ticket-scope
    gaps found mid-run rest as noticed lines and go silently undone. A deferred or follow-up item's
    note is what the human reads when deciding, so it states the issue and its consequence."""
    with wf.locked():
        state = wf.load()
        if state["phase"] != "EXECUTING":
            raise TPError(f"closeout applies while EXECUTING; the workflow is {state['phase']}.")
        items = wf.noticed_items()
        marks = _closeout_marks(state, wf)
        open_ = {_noticed_text(r) for r in items}
        chosen = sorted(((text, e) for text, e in marks.items()
                         if text in open_ and e.get("class") == "deferred"), key=lambda kv: kv[1]["class"])
        if ask or decide:
            if decide and not answer:
                raise TPError("--decide needs --answer \"<the human's words>\".")
            if state.get("closeout", {}).get("decision") and ask:
                raise TPError("the human's decision is already recorded — `tp final` writes the report.")
            unclassified = _closeout_unclassified(wf, state)
            if unclassified:
                raise TPError(f"{unclassified} noticed item(s) unclassified — classify them first (`tp closeout`).")
            if not chosen:
                raise TPError("nothing is deferred, so no human decision is needed — `tp final` (follow-ups are "
                              "listed in the report as suggestions).")
        if ask:
            fx = scopemod.fix_tasks(scopemod.load_scope(wf))
            left = int(fx.get("allow") or 0) - len(state.get("delegated", []))
            out = [f"DEFERRAL DECISION — {len(chosen)} noticed item(s) are requested work this run did not do. How "
                   "should they be handled: fix them now, file them as tickets, or accept them as recorded?", ""]
            if left > 0:
                out += [f"First: {left} fix task(s) of your standing allowance remain. A gap in this run's own "
                        "deliverables is yours to fix without asking (`tp plan amend --delegated`); class it an "
                        "observation that names the fix. Ask only about work the allowance cannot cover.", ""]
            for i, (text, e) in enumerate(chosen, 1):
                out += [f"{i}. [{e['class']}] {text}", f"   Why it matters: {e.get('note')}"]
            out += _closeout_amendment(wf, state)
            out += ["", "Offer exactly these: fix them now (a plan amendment, `tp plan amend`); file them as tickets "
                    "(an integration task the human approves); or accept them as recorded (the report lists them). "
                    "Never offer to park them in a local file or drafts folder.",
                    "Ask this once with AskUserQuestion, then record their words verbatim:",
                    "tp closeout --decide --answer \"<the human's words>\""]
            return "\n".join(out)
        if decide:
            state.setdefault("closeout", {})["decision"] = {"ts": now_iso(), "answer": answer}
            wf.save(state)
            wf.decision("closeout: deferred and follow-up work", str(answer), who="human")
            wf.event("closeout_decision")
            return "the human's decision is recorded. `tp final` writes the report."
        if item is not None or items_spec:
            if cls not in CLOSEOUT_CLASSES:
                raise TPError(f"--class must be one of {', '.join(CLOSEOUT_CLASSES)}.")
            if cls != "observation" and (not note or words(note) < 4):
                raise TPError(f"--class {cls} needs --note in plain language: what the issue is and the consequence "
                              "of leaving it (the note is what the human reads when deciding) — never a bare file "
                              "path or ticket shorthand.")
            numbers = _item_numbers(items_spec, len(items)) if items_spec else [item]
            if item is not None and not 1 <= item <= len(items):
                raise TPError(f"there is no noticed item #{item} ({len(items)} open) — `tp closeout` lists them.")
            entry = {"class": cls, **({"note": " ".join(note.split())} if note else {})}
            for n in numbers:
                state.setdefault("closeout", {}).setdefault("items", {})[_noticed_text(items[n - 1])] = dict(entry)
            if cls == "deferred":
                state["closeout"].pop("decision", None)  # new deferred work needs its own answer
            wf.save(state)
            wf.event("closeout_class", cls=cls, items=len(numbers))
            pending = _closeout_pending(wf, state)
            tail = ("`tp closeout --ask` renders the question for the human." if pending == _UNDECIDED
                    else "`tp final` writes the report." if pending is None else "`tp closeout` lists the rest.")
            which = f"item #{numbers[0]}" if len(numbers) == 1 else f"items {', '.join(f'#{n}' for n in numbers)}"
            return f"{which} classified {cls}" + (f" — {entry['note']}" if note else "") + f". {tail}"
        if not items:
            return "nothing was noticed outside the plan — `tp final` writes the report."
        auto = sum(1 for r in items if marks.get(_noticed_text(r), {}).get("auto"))
        done = sum(_noticed_text(r) in marks for r in items)
        out = [f"CLOSEOUT — {len(items)} noticed item(s), {done} classified ({auto} classified automatically as "
               f"observations: notes about an agent's own work)" + ("" if show_all else "; unclassified ones below "
                                                                     "(`--all` lists every item)") + ":"]
        for n, raw in enumerate(items, 1):
            e = marks.get(_noticed_text(raw), {})
            if show_all or not e:
                out.append(f"  {n}. [{e.get('class', 'UNCLASSIFIED')}] {raw}" + (f" — {e['note']}" if e.get("note") else ""))
        out += ["Classify them, several at a time: tp closeout --items 1,3,5-7 --class deferred|followup|observation "
                "--note \"<the issue and its consequence>\". deferred: requested work this run leaves undone — the "
                "only class the human decides (tp closeout --ask, once). A gap in this run's own deliverables is not "
                "deferred: fix it inside the fix-task allowance (`tp plan amend --delegated`) and class it observation, "
                "naming the fix. followup: outside this run's scope, worth its own ticket — the report suggests it, "
                "no question. observation: no action."]
        return "\n".join(out)


def _run_final_checks(wf: Workflow, state: Dict[str, Any], plan: Dict[str, Any],
                      scope: Dict[str, Any], skip: Optional[Dict[str, str]] = None
                      ) -> Tuple[List[Tuple[str, str]], List[str]]:
    """Run the plan's final checks: ([(baseline key, failure)], result lines). The key says which
    failure it is across runs: a docs-all problem by its own text (deterministic), a command check
    by its name (its output shifts run to run). skip: {check name: its waived key} — a command
    check the human waived on this very tree is not run again; its waived failure stands."""
    failures: List[Tuple[str, str]] = []
    results: List[str] = []
    for name in plan.get("final_checks", []):
        log = wf.meta / f"final-{name}.log"
        if name in (skip or {}):
            results.append(f"{name}: waived by the human on this tree — not run again (last log {log})")
            failures.append((skip[name], f"final check {name} waived by the human (last log {log})"))
            continue
        if name == "docs-all":
            for wname, w in scopemod.workspaces(scope).items():
                if w["mode"] != "write":
                    continue
                root = Path(w["path"])
                # Only index.md is an index. A README is a landing page: a code repository's
                # README links what its authors chose, not every document under it.
                index = root / "index.md" if (root / "index.md").exists() else None
                docs = [d for d in docscheck.md_files([root]) if wf.root not in d.parents]
                # Under git, judge what this workflow wrote; documents it never touched are
                # not its to answer for, except where it broke their links by removing a file.
                # Every document still feeds the link graph.
                changed, removed = _changed_md(root, state.get("write_baseline", {}).get(wname))
                errors, warnings, stats = docscheck.check(docs, _repos(scope), index, report_only=changed,
                                                          removed=removed)
                log.write_text("\n".join(errors + [f"WARN {w}" for w in warnings]) or f"ok: {stats}")
                judged = "changed since approval" if changed is not None else "every file"
                results.append(f"docs-all {wname} ({judged}): {'ok' if not errors else f'{len(errors)} problems'}, "
                               f"{len(warnings)} doubtful citations (log {log}) {stats}")
                failures += [(f"docs-all:{wname}:{e}", e) for e in errors]
        else:
            spec = plan["checks"][name]
            cwd = _ws(scope, spec["cwd"]) if spec.get("cwd") else Path(next(
                w["path"] for w in scopemod.workspaces(scope).values() if w["mode"] == "write"))
            ok, tail = _run_cmd(_expand_cmd(spec["cmd"], None, scope), cwd, log, timeout=FINAL_CHECK_TIMEOUT)
            results.append(f"{name}: {'ok' if ok else 'failed'}")
            if not ok:
                failures.append((check_key(name, tail), f"final check {name} failed (log {log}): {tail}"))
    return failures, results


# The lines a failing check prints to name what failed, in the formats test runners and make share:
# Go (`--- FAIL: TestX`, `FAIL <pkg>`), TAP (`not ok 3 - name`), node's spec reporter (`✖ name`),
# Python unittest (`FAIL: test_x (mod.Class)`, `ERROR: ...`), and make's own `*** ... Error N`.
_FAIL_LINE = re.compile(r"^(--- FAIL: \S+.*|FAIL[ \t]+\S+.*|FAIL: .*|ERROR: .*|not ok \d+.*|\s*[✖✗✕] .*|"
                        r"make(\[\d+\])?: \*\*\* .*)$", re.M)
_DURATION = re.compile(r"\s*\(\d+(\.\d+)?\s*(ms|s|m)\)|[ \t]+\d+(\.\d+)?s\b|\(cached\)")


def failure_signature(text: str, roots: List[str]) -> Set[str]:
    """What a failing check names as failed, comparable across two runs in two directories: durations
    dropped, the directory each ran in replaced by `<ws>`, TAP's test numbers dropped."""
    out: Set[str] = set()
    for m in _FAIL_LINE.finditer(text):
        line = m.group(1).strip()
        if "Waiting for unfinished jobs" in line:
            continue  # make -jN prints it or not depending on timing
        line = re.sub(r"^make\[\d+\]", "make", line)  # the recursion depth differs between a -k run and not
        for root in roots:
            line = line.replace(root.rstrip("/"), "<ws>")
        line = _DURATION.sub("", line)
        line = re.sub(r"^not ok \d+", "not ok", line)
        out.add(" ".join(line.split()))
    return out


def _clean_copy(ws: Path, sha: str, dest: Path) -> Tuple[Optional[Path], str]:
    """A checkout of sha in dest, sharing ws's objects (nothing is written to ws's repository, so it
    works where a sandbox makes `.git/worktrees` read-only): (the copy's ws directory, error)."""
    top = subprocess.run(["git", "-C", str(ws), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top.returncode != 0:
        return None, "the workspace is not under git"
    rel = Path(ws).resolve().relative_to(Path(top.stdout.strip()).resolve())
    shutil.rmtree(dest, ignore_errors=True)
    for cmd in (["git", "clone", "-q", "--shared", "--no-checkout", top.stdout.strip(), str(dest)],
                ["git", "-C", str(dest), "checkout", "-q", "--detach", sha]):
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            return None, (res.stderr or res.stdout).strip()[-300:]
    return dest / rel, ""


def _probe_base(wf: Workflow, state: Dict[str, Any], plan: Dict[str, Any], scope: Dict[str, Any],
                name: str) -> Dict[str, Any]:
    """Run final check `name` once on a clean copy of the commit the run was approved on, so tp can
    tell a failure the run caused from one that was already there (a sandbox that refuses unix
    sockets, breakage on the branch). Cached per check and commit: it never runs twice.
    In a real run (KUB-1339) nothing could say so: `make test` ran four times in 31 minutes on an
    unchanged tree, the human was asked, and their answer still did not let `tp final` finish."""
    spec = plan["checks"][name]
    wname = spec.get("cwd") or next(n for n, w in scopemod.workspaces(scope).items() if w["mode"] == "write")
    sha = (state.get("write_baseline") or {}).get(wname)
    if not sha:
        return {"error": f"no approval commit recorded for {wname}"}
    probes = state.setdefault("base_probes", {})
    key = f"{name}@{sha}"
    if key in probes:
        return probes[key]
    ws = _ws(scope, wname)
    dest = wf.meta / "base-copy"
    copy, err = _clean_copy(ws, sha, dest)
    log = wf.meta / f"final-{name}-base.log"
    if copy is None:
        probes[key] = {"error": f"could not check out {sha[:12]}: {err}", "sha": sha}
    else:
        # make -k: without it, a parallel make stops starting recipes at the first failure, so which
        # others ran is timing; keeping going makes this run's failures a superset to compare against.
        cmd = ('export MAKEFLAGS="-k${MAKEFLAGS:+ $MAKEFLAGS}"; '
               + _expand_cmd(spec["cmd"], None, scope).replace(str(ws), str(copy)))
        ok, tail = _run_cmd(cmd, copy, log, timeout=FINAL_CHECK_TIMEOUT)
        text = log.read_text(errors="replace")
        probes[key] = {"sha": sha, "ok": ok, "log": str(log), "timed_out": _timed_out(ok, tail),
                       "signature": sorted(failure_signature(text, [str(copy), str(dest)]))}
    shutil.rmtree(dest, ignore_errors=True)
    wf.event("base_probe", check=name, sha=sha[:12], ok=probes[key].get("ok"), error=probes[key].get("error"))
    return probes[key]


def _prove_preexisting(wf: Workflow, state: Dict[str, Any], plan: Dict[str, Any], scope: Dict[str, Any],
                       stopping: List[Tuple[str, str]]) -> Tuple[List[str], List[str]]:
    """Of the final-check failures that would stop the run, the ones a clean copy of the approval
    commit fails in exactly the same places: (their keys, a line of evidence per check probed). Only a
    command check that failed — not a timeout, not docs-all — and only when every failure line the
    run's log names also appears in the approval commit's run; anything new, or a log that names no
    failure tp can read, still stops the run."""
    proven, notes = [], []
    for key, _ in stopping:
        parts = key.split(":")
        if len(parts) != 2 or parts[0] != "check" or parts[1] not in plan.get("checks", {}):
            continue
        name = parts[1]
        log = wf.meta / f"final-{name}.log"
        wname = plan["checks"][name].get("cwd")
        roots = [str(_ws(scope, wname))] if wname else [w["path"] for w in scopemod.workspaces(scope).values()]
        mine = failure_signature(log.read_text(errors="replace") if log.exists() else "", roots)
        if not mine:
            notes.append(f"{name}: its log names no failure tp can compare (log {log}) — not probed.")
            continue
        probe = _probe_base(wf, state, plan, scope, name)
        if probe.get("error") or probe.get("timed_out"):
            notes.append(f"{name}: the approval commit could not be checked "
                         f"({probe.get('error') or 'its run timed out'}).")
            continue
        new = sorted(mine - set(probe.get("signature", [])))
        if new:
            notes.append(f"{name}: fails at the approval commit {probe['sha'][:12]} too, but not in "
                         f"{len(new)} place(s) — this run's: " + "; ".join(new[:5]) + f" (base log {probe['log']}).")
            continue
        proven.append(key)
        state.setdefault("proven_preexisting", {})[key] = {"sha": probe["sha"], "failures": sorted(mine),
                                                          "log": probe["log"], "ts": now_iso()}
        notes.append(f"{name}: every failure ({len(mine)}) also fails on a clean copy of the approval commit "
                     f"{probe['sha'][:12]} (log {probe['log']}) — pre-existing, not this run's; the report lists it.")
        wf.event("preexisting_proven", check=name, sha=probe["sha"][:12], failures=len(mine))
    return proven, notes


def _left_keys(state: Dict[str, Any]) -> Set[str]:
    """Final-check failures the run finishes over: the ones the human chose to leave at the baseline,
    the ones a clean copy of the approval commit reproduced, and the ones the human waived after
    they failed — while the workspaces are as they were then (final_checks sets `valid`)."""
    waived = state.get("final_waived") or {}
    return (set((state.get("baseline_left") or {}).get("keys", [])) | set(state.get("proven_preexisting") or {})
            | (set(waived.get("keys", [])) if waived.get("valid") else set()))


def cmd_final_waive(wf: Workflow, answer: str) -> str:
    """The human accepts the final-check failures `tp final` just stopped on (the manager showed them
    an outside-sandbox run, say). They stand for the tree as it was when they failed: `tp final`
    finishes over them without running those checks again, and any change to the workspaces, or a
    new failure, stops it again. In a real run (KUB-1339) the human accepted the manager's outside-
    sandbox run, and `tp final` still re-ran `make test` and failed the same way, twice."""
    if words(answer) < 2:
        raise TPError("--answer needs the human's words, verbatim.")
    with wf.locked():
        state = wf.load()
        if state["phase"] != "EXECUTING":
            raise TPError(f"final runs while EXECUTING; the workflow is {state['phase']}.")
        keys, tree = state.get("final_failed_keys"), state.get("final_failed_tree")
        if not keys or not tree:
            raise TPError("no final-check failure to waive: run `tp final` first; it records what failed.")
        state["final_waived"] = {"keys": list(keys), "answer": answer, "tree": tree, "ts": now_iso()}
        wf.save(state)
        wf.decision(f"waive the final-check failures {', '.join(keys)}", answer, who="human")
        wf.event("final_waived", keys=keys)
        return (f"waived: {', '.join(keys)}. `tp final` (in the background) now finishes over them without running "
                "them again, while the workspaces stay as they are; a change to them, or a new failure, stops it.")


def final_failure_advice(keys: List[str], baseline: Set[str], readonly: bool = False) -> str:
    """What `tp final` tells the manager to do about the failures it stopped on (keys from check_key)."""
    if keys and not readonly and all(k in baseline for k in keys):
        return ("Every failure above pre-dates this run (`tp baseline`): ask the human once whether to fix it in this "
                "run or leave it. Leave → `tp baseline --leave --answer \"<their words>\"`, then `tp final` finishes "
                "and reports it.")
    out = []
    slow = [k.split(":")[1] for k in keys if k.endswith(":timeout")]
    if slow:
        out.append(f"{', '.join(slow)} ran past the {FINAL_CHECK_TIMEOUT // 60}-minute limit, which proves nothing "
                   "either way. First make sure nothing else is loading the machine (another run's tests) and that "
                   "`tp final` runs in the background. A slow check needs no code change: run it under the repo's "
                   "pinned toolchain (the survey's env prefix) or with more parallel jobs (`make -jN <the same "
                   "targets>`) — either is yours, `tp plan amend --delegated`; any other "
                   "rewrite — a narrower command — is a check change the plan reviewer or the human decides (`tp plan "
                   "amend` says which).")
    if any(not k.endswith(":timeout") for k in keys) or readonly:
        out.append("These are the run's to fix, not the human's: a failure in work a task delivered is a fix task "
                   "(`tp plan amend`; inside the fix-task allowance `--delegated`, past it the check says who decides); "
                   "a failure from the machine — a toolchain or tool the repo pins to another version — is a pinned "
                   "check (`tp plan amend --delegated`, an env prefix only).")
    out.append("Then `tp final` again. Only what neither settles goes to the human: ask them once, with your "
               "evidence (a run outside the sandbox, say); on their OK `tp final --waive --answer \"<their words>\"` "
               "— `tp final` then finishes over exactly these failures without running them again.")
    return " ".join(out)


def check_key(name: str, tail: str) -> str:
    """Which failure a command check is, across runs: by its name (its output shifts run to run),
    except that a timeout is its own kind — it proves nothing, so it never matches a known failure."""
    return f"check:{name}:timeout" if "timed out after" in tail else f"check:{name}"


def cmd_baseline(wf: Workflow, leave: Optional[str] = None) -> str:
    """Record which final checks already fail before this run touches anything (machine quirks,
    sandbox limits, breakage already on the branch), so `tp final` can name them pre-existing
    instead of presenting them as the run's own. Run it right after approval, and put any failure
    to the human then, while they are still there — not at the end of the run, when they are not.
    `leave`: the human's words choosing to leave the recorded failures; `tp final` then finishes
    over them (a new failure, or a timeout, still stops it) and the report lists them."""
    if leave is not None:
        return _leave_baseline(wf, leave)
    with wf.locked():
        state = wf.load()
        if state["phase"] != "EXECUTING":
            raise TPError(f"baseline runs while EXECUTING; the workflow is {state['phase']}.")
        if state["in_flight"]:
            raise TPError(f"agents are in flight ({', '.join(state['in_flight'])}) — record them before baselining.")
        landed = [t for t, ts in state["tasks"].items() if ts.get("started") or ts.get("status") != "pending"]
        if landed:
            raise TPError(f"work has already landed ({', '.join(landed[:6])}): a baseline is taken before the first "
                          "dispatch, or it would record the run's own breakage as pre-existing. A failure found now "
                          "is the run's to fix — unless the same checks fail on a clean copy of the approval commit, "
                          "which is evidence to show the human with the failure.")
        plan, scope, _ = _loaded(wf, state)
        failures, results = _run_final_checks(wf, state, plan, scope)
        state["final_baseline"] = sorted({key for key, _ in failures})
        state.pop("baseline_left", None)  # a new baseline needs a new decision
        wf.save(state)
        wf.event("baseline", failures=len(state["final_baseline"]))
        n = len(state["final_baseline"])
        if not n:
            return "\n".join(["baseline recorded: every final check passes right now."]
                             + [f"  - {r}" for r in results])
        timeouts = [k for k in state["final_baseline"] if k.endswith(":timeout")]
        return "\n".join(
            [f"baseline recorded: {n} final-check failure(s) pre-date this run."] + [f"  - {r}" for r in results]
            + [f"  ! {f}" for _, f in failures[:10]]
            + (["A timed-out check proves nothing either way: make it finish (a narrower command, the repo's pinned "
                "toolchain) before you rely on it."] if timeouts else [])
            + ["A failure from the machine — a toolchain or tool the repo pins to another version (the survey's "
               "TOOLCHAIN line) — is not breakage: pin the check (`tp plan amend --delegated`, an env prefix only) "
               "and baseline again.",
               "Anything left is the branch's own. Ask the human now, while they are here — not at the end: leave it "
               "(the report lists it; `tp final` finishes over it, and still stops on any new failure) or fix it in "
               "this run (a plan amendment). Say that while a check fails it proves nothing past its failure point; "
               "each task's own test_cmd still runs. Leave → `tp baseline --leave --answer \"<their words>\"`."])


def _leave_baseline(wf: Workflow, answer: str) -> str:
    if not answer.strip():
        raise TPError("--answer needs the human's words, verbatim.")
    with wf.locked():
        state = wf.load()
        if state["phase"] != "EXECUTING":
            raise TPError(f"baseline runs while EXECUTING; the workflow is {state['phase']}.")
        known = [k for k in state.get("final_baseline", []) if not k.endswith(":timeout")]
        if not known:
            raise TPError("nothing failed at the recorded baseline, so there is nothing to leave — `tp baseline` "
                          "first (before any work lands); a failure that appears later is the run's to fix.")
        state["baseline_left"] = {"keys": known, "answer": answer, "ts": now_iso()}
        wf.save(state)
        wf.decision("leave the final-check failures that pre-date the run", answer, who="human")
        wf.event("baseline_left", keys=known)
        return (f"left as pre-existing: {', '.join(known)} — `tp final` finishes over them and the report lists them; "
                "a new failure, or a timeout, still stops it.")


def cmd_final(wf: Workflow) -> str:
    with wf.locked():
        state = wf.load()
        if state["phase"] != "EXECUTING":
            raise TPError(f"final runs while EXECUTING; the workflow is {state['phase']}.")
        plan, scope, tasks = _loaded(wf, state)
        held = _held_posts(state, scope, tasks)
        keyed, results = final_checks(wf, state, plan, scope, held)
        if held:
            return (f"Final checks pass on the finished work ({'; '.join(results) or 'no final checks'}). "
                    f"Now the posts, last: {', '.join(held)} (`tp next`). Then `tp final` writes the report from "
                    "these results.")
        state["final_left"] = [f for key, f in keyed if key in _left_keys(state)]
        state["phase"] = "DONE"
        state["done"] = now_iso()
        state.pop("final_failed", None)
        wf.save(state)
        (wf.root / "report.md").write_text(_report_md(wf, state, plan, scope, results))
        wf.event("done")
        return f"DONE — report: {wf.root / 'report.md'}. Present it to the human (answer-first)."


def _held_posts(state: Dict[str, Any], scope: Dict[str, Any], tasks: Dict[str, Dict[str, Any]]) -> List[str]:
    return [t for t, ts in state["tasks"].items() if ts["status"] == "pending" and t in tasks
            and _integration_held(tasks[t], scope, state)]


def final_checks(wf: Workflow, state: Dict[str, Any], plan: Dict[str, Any], scope: Dict[str, Any],
                 held: List[str]) -> Tuple[List[Tuple[str, str]], List[str]]:
    """The final checks on finished work: refused while work, review, or the closeout is open;
    raises on a failure. With posts still held (`held`) they run before the posts and are
    recorded; after the posts, that record is reused while nothing has moved."""
    open_ = [f"{t} ({ts['status']})" for t, ts in state["tasks"].items()
             if ts["status"] not in DONE_STATES and t not in held]
    if open_ or state["in_flight"]:
        raise TPError(f"open tasks: {', '.join(open_ or list(state['in_flight']))}.")
    pending = _closeout_pending(wf, state)  # first: the whole-change review waits on it
    if pending:
        raise TPError(f"the closeout is open: {pending}. `tp closeout` lists the noticed items; classify each, "
                      "and put deferred or follow-up work to the human (`tp closeout --ask`, then "
                      "`tp closeout --decide --answer \"...\"`).")
    reviews_open = _review().open_sessions(state)
    if reviews_open:
        raise TPError(f"review sessions still open: {', '.join(reviews_open)} — `tp next`.")
    pre = state.get("prefinal") or {}
    waived = state.get("final_waived")
    tree = _tree_sig(wf, scope) if (held or pre or waived) else ""
    lapsed = []
    if waived:
        # A waiver covers the tree the human saw fail; once any workspace file moves it covers nothing.
        waived["valid"] = waived.get("tree") == tree
        if not waived["valid"]:
            lapsed = [f"the human's waiver of {', '.join(waived['keys'])} lapsed: the workspaces changed since "
                      "those checks failed, so they ran again."]
    skip = {k.split(":")[1]: k for k in (waived or {}).get("keys", [])
            if waived.get("valid") and k.startswith("check:") and k.split(":")[1] in plan.get("checks", {})}
    if not held and pre.get("tree") == tree and pre.get("sig") == _work_sig(state):
        # Checked before the post and nothing moved since: the post changed no workspace file.
        keyed, results = [(k[0], k[1]) for k in pre.get("keyed", [])], list(pre.get("results", []))
    else:
        keyed, results = _run_final_checks(wf, state, plan, scope, skip)
    results = results + lapsed
    baseline = set(state.get("final_baseline", []))
    stopping = [(key, f) for key, f in keyed if key not in _left_keys(state)]
    proven, probe_notes = _prove_preexisting(wf, state, plan, scope, stopping) if stopping else ([], [])
    stopping = [(key, f) for key, f in stopping if key not in proven]
    results = results + [f"probe: {n}" for n in probe_notes]
    failures = [f + (" [pre-existing: it failed at the recorded baseline too]" if key in baseline else "")
                for key, f in stopping] + _readonly_changes(wf, state, scope)
    if failures:
        state["final_failed"] = failures[:50]
        # What a human waiver (`tp final --waive`) would cover: these checks, on the tree as the
        # checks left it (a check may write into the workspace).
        state["final_failed_keys"] = [key for key, _ in stopping]
        state["final_failed_tree"] = _tree_sig(wf, scope)
        wf.save(state)
        readonly_only = len(stopping) != len(failures)
        raise TPError(*failures[:40], *[f"probe: {n}" for n in probe_notes], *lapsed,
                      final_failure_advice([key for key, _ in stopping], baseline, readonly=readonly_only))
    if proven or waived:
        wf.save(state)
    if held:
        # The tree as the checks left it: a check that writes into the workspace (coverage, build
        # output) must not make the run after the post look changed.
        tree = _tree_sig(wf, scope)
        state["prefinal"] = {"sig": _work_sig(state), "tree": tree, "keyed": [list(k) for k in keyed],
                             "results": results, "ts": now_iso()}
        state.pop("final_failed", None)
        wf.save(state)
        wf.event("prefinal", held=held)
    return keyed, results


def _tree_sig(wf: Workflow, scope: Dict[str, Any]) -> str:
    """The write workspaces' content, for reusing a check run: the same snapshot every record takes."""
    snaps = {name: _take(wf, Path(w["path"])) for name, w in sorted(scopemod.workspaces(scope).items())
             if w["mode"] == "write"}
    return hashlib.sha1(json.dumps(snaps, sort_keys=True).encode()).hexdigest()


def _published_to(task: Dict[str, Any]) -> str:
    """What a publish task writes, in place of the files other tasks list."""
    pub = task.get("publish") or {}
    return f"{pub.get('to', 'publish')} {pub.get('target', '')}".strip()


def _task_rows(wf: Workflow, state: Dict[str, Any], tasks: Dict[str, Dict[str, Any]]) -> List[str]:
    """Active min: first dispatch to acceptance, less waits on the human, halts, and time spent
    finished. Agent min: the agents' own time in flight."""
    agents = agent_minutes(wf)
    rows = ["| Task | Title | Status | Active min | Agent min | Est | Fix rounds | Reviews |",
            "|---|---|---|---|---|---|---|---|"]
    for tid, ts in state["tasks"].items():
        rows.append(f"| {tid} | {tasks[tid]['title'] if tid in tasks else '?'} | {ts['status']} | "
                    f"{task_minutes(state, ts):.0f} | {agents.get(tid, 0):.0f} | "
                    f"{tasks.get(tid, {}).get('estimate_min', '?')} | {ts['round']} | {ts['reviews']} |")
    return rows


def _execution(wf: Workflow, state: Dict[str, Any]) -> str:
    """Execution time three ways: wall clock (what the budget measures), the part that was work,
    and the agents' own time."""
    start, end = state.get("approved"), state.get("done")
    wall = minutes_since(start, end)
    waited = gap_minutes(start, end, waiting_gaps(state))
    agents = agent_minutes(wf)
    return (f"{wall:.0f} min wall-clock: {wall - waited:.0f} min of work and {waited:.0f} min halted or waiting on "
            f"the human. Agents worked {sum(agents.values()):.0f} min across "
            f"{sum(1 for e in wf.events() if e['kind'] == 'record' and 'minutes' in e)} hand-backs")


def manager_calls(state: Dict[str, Any], tids: Optional[List[str]] = None) -> List[str]:
    """What the manager settled without the human that loosened a gate: test corrections, gates
    accepted over their findings, widened write sets. The report lists them, and the final review is
    told to judge each one — autonomy that nobody independent reads is a weakening path."""
    keep = (lambda t: True) if tids is None else (lambda t: t in tids)
    out = [f"{c['task']}: tests re-baselined by the {c['by']} ({', '.join(c['files']) or 'no file'}): {c['reason']} "
           f"— the old baseline is at `{c['before']}`; judge whether this corrects the tests or loosens them."
           for c in state.get("test_corrections", []) if keep(c["task"])]
    out += [f"{o['task']}: accepted over its gate findings — {o['note']} (the findings: "
            + "; ".join(str(f)[:160] for f in o.get("findings", [])[:3]) + ")"
            for o in state.get("overrides", []) if keep(o["task"])]
    out += [f"{tid}: write set widened by {', '.join(ts['widened'])}" for tid, ts in state.get("tasks", {}).items()
            if ts.get("widened") and keep(tid)]
    if tids is None:
        out += [f"{m['workspace']}: HEAD move declared ({len(m['shas'])} commits up to {str(m['to'])[:10]}): "
                f"{m['reason']}" for m in state.get("head_moves", [])]
    return out


def _report_md(wf: Workflow, state: Dict[str, Any], plan: Dict[str, Any], scope: Dict[str, Any],
               results: List[str]) -> str:
    tasks = {t["id"]: t for t in plan["tasks"]}
    planning = minutes_since(state["created"], state.get("approved"))
    budget = scope.get("budget_minutes")
    out = [f"# Report — {plan['title']}", "",
           f"All {len(tasks)} tasks finished: {sum(ts['status'] == 'accepted' for ts in state['tasks'].values())} "
           f"accepted, {sum(ts['status'] == 'skipped' for ts in state['tasks'].values())} skipped. "
           f"Planning took {planning:.0f} min and execution took {_execution(wf, state)}"
           + (f". The budget was {budget} min, wall-clock, planning included." if budget else "."),
           "", "## Deliverables", ""]
    for d in scope["deliverables"]:
        served = [t for t in tasks.values() if d["id"] in t["serves"]]
        out.append(f"- {d['id']} — {d['what']}: " + ", ".join(
            f"{t['id']} (`{', '.join(t.get('paths') or [_published_to(t)])}`)" for t in served))
    ledger = [r for r in scope.get("requirements") or [] if isinstance(r, dict)]
    if ledger:
        out += ["", "## Requirement coverage", "", "| Requirement | Tasks | Status |", "|---|---|---|"]
        for r in ledger:
            served = [t for t in tasks.values() if r["id"] in (t.get("requirements") or [])]
            how = ", ".join(f"{t['id']} {state['tasks'].get(t['id'], {}).get('status', '?')}" for t in served)
            out.append(f"| {r['id']} — {r.get('text', '')} | {', '.join(t['id'] for t in served) or '—'} | "
                       f"{how or '**no task**'} |")
    waits = _questions().waiting_lines(state)
    if waits:
        out += ["", "## Waiting on the human", ""] + [f"- {w}" for w in waits]
    out += ["", "## Tasks", ""] + _task_rows(wf, state, tasks)
    calls = manager_calls(state)
    if calls:
        out += ["", "## Gates the manager settled (each read by the final review)", ""] + [f"- {c}" for c in calls]
    by_note: Dict[str, List[str]] = {}
    for tid, ts in state["tasks"].items():  # one note for a wave accepted together prints once
        if ts.get("note"):
            by_note.setdefault(ts["note"], []).append(tid)
    notes = [f"- {', '.join(tids)}: {note}" for note, tids in by_note.items()]
    if notes:
        out += ["", "## Manager fact-check notes", ""] + notes
    delegated = [a for a in state.get("amendments", []) if a.get("delegated")]
    if delegated:
        out += ["", "## Fix tasks added under your standing delegation", "",
                "Added by the manager without a question, inside the fix-task allowance you gave at scope time:", ""]
        out += [f"- {', '.join(f'{tid} — ' + (tasks[tid]['title'] if tid in tasks else '?') for tid in a['tasks'])}: "
                f"{a.get('note')}" for a in delegated if a.get("tasks")]
    reviewed = ([f"- {', '.join(a.get('tasks') or []) or 'plan'}: {a.get('note')} — the reviewer: {a.get('reason')}"
                 for a in state.get("amendments", []) if a.get("reviewed")]
                + [f"- scope: {a.get('note')} — the reviewer: {a.get('reason')}"
                   for a in state.get("scope_amendments", []) if a.get("reviewed")])
    if reviewed:
        out += ["", "## Changes an independent reviewer approved", "",
                "Each strengthened the run without changing what it delivers; the reviewer judged it in your place:",
                ""] + reviewed
    plumbing = [a for a in state.get("scope_amendments", []) if a.get("delegated")]
    if plumbing:
        out += ["", "## Scope plumbing the manager settled", "",
                "Nothing you agreed changed — wording, rationale, or less write authority:", ""]
        out += [f"- {a.get('note')} ({'; '.join(c.strip() for c in a.get('changes', []))})" for a in plumbing]
    review_lines = _review().report_lines(state)
    if review_lines:
        out += ["", "## Review", ""] + review_lines
    research = _research().summary(state, scope)
    if research:
        out += ["", "## Research", "", f"- {research}"]
    out += ["", "## Final checks", ""] + ([f"- {r}" for r in results] or ["- none planned"])
    if state.get("final_left"):
        left = state.get("baseline_left") or {}
        why = [f"the human chose to leave them: \u201c{left['answer']}\u201d"] if left.get("answer") else []
        why += [f"{key.split(':')[1]} failed in the same places on a clean copy of the approval commit "
                f"{p['sha'][:12]} (log {p['log']})" for key, p in (state.get("proven_preexisting") or {}).items()]
        waived = state.get("final_waived") or {}
        if waived.get("valid"):
            why.append(f"the human waived {', '.join(waived['keys'])}: “{waived['answer']}”")
        out += ["", "Left as pre-existing \u2014 they failed before the run began (" + "; ".join(why) + "):", ""] + [
            f"- {f.splitlines()[0][:300]}" for f in state["final_left"]]
    groups: Dict[str, List[str]] = {c: [] for c in CLOSEOUT_CLASSES + ("unclassified",)}
    for raw in wf.noticed_items():
        e = _closeout_marks(state, wf).get(_noticed_text(raw), {})
        groups[e.get("class", "unclassified")].append(f"- {raw}" + (f" — {e['note']}" if e.get("note") else ""))
    titles = {"deferred": "Deferred with the human's OK (their decision is in `decisions.md`)",
              "followup": "Suggested follow-ups (outside this run's scope — file them if you agree)",
              "observation": "Observations — no action taken",
              "unclassified": "Noticed, not in plan (for you to decide)"}
    if groups["observation"]:
        # Nobody acts on an observation: a real run's ran to 39KB of an 85KB report. They keep
        # their own file, beside the report.
        (wf.root / "observations.md").write_text("# Observations — no action taken\n\n"
                                                 + "\n".join(groups["observation"]) + "\n")
        n = len(groups["observation"])
        groups["observation"] = [f"- {n} observation{'s' if n != 1 else ''}, each with the manager's note: "
                                 "`observations.md`."]
    for cls, lines in groups.items():
        if lines:
            out += ["", f"## {titles[cls]}", ""] + lines
    out += ["", "Every decision, with who made it where recorded, is in `decisions.md`; every brief, result, review, "
            "and check log is under `runs/`."]
    return "\n".join(out) + "\n"


def cmd_report(wf: Workflow) -> str:
    state = wf.load()
    planning = minutes_since(state["created"], state.get("approved"))
    out = [f"planning: {planning:.0f} min (start → approval)" + ("" if state.get("approved") else ", still open")]
    if state.get("approved"):
        out.append(f"execution: {_execution(wf, state)}")
    plan_tasks: Dict[str, Dict[str, Any]] = {}
    if wf.plan_json.exists():
        plan_tasks = {t["id"]: t for t in planmod.load_plan(wf)["tasks"]}
    out += _task_rows(wf, state, plan_tasks)
    steps: Dict[str, List[float]] = {}
    for e in wf.events():
        if e["kind"] == "record" and "minutes" in e:
            steps.setdefault(e.get("step", "?"), []).append(e["minutes"])
    for step, mins in steps.items():
        out.append(f"{step}: {len(mins)} hand-backs, mean {sum(mins) / len(mins):.1f} min, max {max(mins):.1f} min")
    return "\n".join(out)


def cmd_status(wf: Workflow, as_json: bool) -> str:
    state = wf.load()
    if as_json:
        return json.dumps({"phase": state["phase"], "title": state["title"],
                           "tasks": {t: v["status"] for t, v in state["tasks"].items()},
                           "in_flight": state["in_flight"], "blocked": state.get("blocked"),
                           "elapsed_min": round(minutes_since(state["created"]), 1)})
    out = [f"{state['title']} — {_headline(state)}", f"dir: {wf.root}"]
    by: Dict[str, List[str]] = {}
    for tid, ts in state["tasks"].items():
        by.setdefault(ts["status"], []).append(tid)
    for status, ids in by.items():
        out.append(f"  {status}: {', '.join(ids[:20])}" + (" …" if len(ids) > 20 else ""))
    if state.get("blocked"):
        out.append(f"BLOCKED: {state['blocked']['summary']}")
    if state.get("halt"):
        out.append(f"HALT {'complete' if state['halt'].get('halted') else 'requested'}: {state['halt']['reason']}")
    research = state.get("recon", {})
    if research:
        out.append("  research: " + ", ".join(f"{rid} {r['status']}" for rid, r in list(research.items())[:12]))
    for a in _amend_action(state):
        out.append(f"  amendment review: {a['id']} ({a['why']}) with the reviewer — `tp {a['why']} amend --record "
                   "--agent-id <its id>`")
    reviews = state.get("reviews", {})
    if reviews:
        def _wait(s: Dict[str, Any]) -> str:
            w = _review().waits_on(state, s)
            return f" (waits on {', '.join(w[:8])}{' …' if len(w) > 8 else ''})" if w else ""
        out.append("  reviews: " + ", ".join(f"{sid} {s['status']}{_wait(s)}" for sid, s in reviews.items()))
    out.append(cmd_next(wf, False, probe=False).splitlines()[-1])  # status looks; it never counts as a look
    return "\n".join(out[:24])


# --- halt and resume ------------------------------------------------------------------------

def _halt_record(wf: Workflow, state: Dict[str, Any]) -> str:
    """Once nothing is in flight after a halt request: record where the work stopped."""
    halt = state["halt"]
    halt["halted"] = halt.get("halted") or now_iso()
    by_status: Dict[str, List[str]] = {}
    for tid, ts in state["tasks"].items():
        by_status.setdefault(ts["status"], []).append(tid)
    record = {
        "requested": halt["requested"], "halted": halt["halted"], "reason": halt["reason"], "phase": state["phase"],
        "elapsed_min": round(minutes_since(state["created"]), 1), "budget_minutes": state.get("budget_minutes"),
        "tasks": by_status,
        "research": {rid: i["status"] for rid, i in state.get("recon", {}).items()},
        "reviews": {sid: s["status"] for sid, s in state.get("reviews", {}).items()},
        "next_on_resume": [{k: a[k] for k in ("action", "id", "step", "agent") if a.get(k)}
                           for a in actions(wf, state, ignore_halt=True)],
    }
    (wf.root / "halt.json").write_text(json.dumps(record, indent=1))
    wf.save(state)
    wf.event("halted")
    counts = ", ".join(f"{len(v)} {k}" for k, v in by_status.items())
    nxt = "; ".join(f"{a['action']} {a.get('id', '')}".strip() for a in record["next_on_resume"][:6])
    return (f"HALTED at a clean point — nothing in flight. Recorded in {wf.root / 'halt.json'}.\n"
            f"{state['phase']}{' · ' + counts if counts else ''}. On resume: {nxt or 'nothing pending'}.\n"
            "Tell the human; `tp resume --answer \"<their words>\"` continues.")


def after_record(wf: Workflow, out: str) -> str:
    """Called after every recorded hand-back: completes a pending halt once the last agent is in."""
    state = wf.load()
    if state.get("halt") and not state["in_flight"] and not state["halt"].get("halted"):
        return out + "\n" + _halt_record(wf, state)
    if state.get("halt") and state["in_flight"]:
        return out + f"\nHalting: still waiting for {', '.join(state['in_flight'])}."
    return out


def follow_on(wf: Workflow, always: bool = False) -> str:
    """After any state change: dispatch every step that is now ready and list what else waits, so
    accept, triage, resolve, and the rest each end in the calls to send. In real runs each of them
    printed "Next: `tp next`" and cost two more calls (about three per hand-back)."""
    if not always and os.environ.get("TP_FOLLOW_ON") == "0":  # the test suite's older scenarios step by hand
        return ""
    state = wf.load()
    if state.get("halt") or state["phase"] in ("SCOPING", "DONE"):
        return ""
    out = []
    ready = [a["id"] for a in actions(wf, state) if a["action"] in ("dispatch", "fix", "review")]
    for rid in ready:
        try:
            out.append(cmd_dispatch(wf, rid))
            wf.event("auto_dispatch", id=rid)
        except TPError as exc:
            out.append("\n".join(f"not dispatched: {rid}: {ln}" for ln in exc.lines))
    if ready:
        out.append("Send every call above in one message.")
    state = wf.load()
    waiting = _questions().status_line(state)
    out += [waiting] if waiting else []
    for a in _collapse_asked(state, [a for a in actions(wf, state) if a["action"] not in ("dispatch", "fix", "review")]):
        about = f" about {a['id']}" if a.get("id") else ""
        out.append(f"→ {a['action']} {a.get('id') or ''}".rstrip() + ": " + GUIDE[a["action"]].format(
            id=a.get("id") or "", why=a.get("why", ""), about=about, ids=", ".join(a.get("ids", []))))
    return "\n\n".join(out)


def cmd_advance(wf: Workflow, tid: str, agent_id: Optional[str], long: bool = False) -> str:
    """Record a hand-back, then dispatch every step that is ready because of it, in one call: the
    manager's turns each re-read its whole context, and record → next → dispatch took three."""
    first = after_record(wf, cmd_record(wf, tid, agent_id, long=long))
    if wf.load().get("halt"):
        return first
    rest = follow_on(wf, always=True)
    return first + ("\n\n" + rest if rest else "")


def cmd_halt(wf: Workflow, reason: str) -> str:
    with wf.locked():
        state = wf.load()
        if state["phase"] == "DONE":
            raise TPError("The workflow is DONE; there is nothing to halt.")
        if state.get("halt"):
            return f"Already halting (requested {state['halt']['requested']}). `tp next` shows what is left."
        state["halt"] = {"requested": now_iso(), "reason": reason, "halted": None}
        wf.save(state)
        wf.decision("halt", reason)
        wf.event("halt_requested")
        if not state["in_flight"]:
            return _halt_record(wf, state)
        flying = ", ".join(f"{k} ({v['step']})" for k, v in state["in_flight"].items())
        return (f"Halt requested. Nothing new will start. Let the agents in flight finish their current step — "
                f"{flying} — and record each one as it hands back; the halt completes when the last is in.")


def cmd_resume(wf: Workflow, answer: str) -> str:
    with wf.locked():
        state = wf.load()
        halt = state.pop("halt", None)
        if halt is None:
            raise TPError("Nothing is halted.")
        state.setdefault("halts", []).append(dict(halt, resumed=now_iso()))
        wf.save(state)
        wf.decision("resume", answer)
        wf.event("resume")
        return "resumed. Run `tp next`."
