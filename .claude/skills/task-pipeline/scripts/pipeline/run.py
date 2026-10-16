"""Execution: what runs next, dispatching a step, recording its hand-back, and every gate
between steps — decided by this script, never by reading prose. Planning research lives in
research.py and end-of-pipeline review in review.py; this module routes to them."""
from __future__ import annotations

import hashlib
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import briefs, docscheck, snapshot
from . import plan as planmod
from . import scope as scopemod
from .common import (TP_SCRIPT, TPError, Workflow, gap_minutes, limit, load_json, minutes_since, now_iso, sha_file,
                     waiting_gaps, words)

DONE_STATES = ("accepted", "skipped")
CHECK_TIMEOUT = 540


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
    return snapshot.take(root, [wf.root], cache=cache, only=only)


def readonly_baseline(wf: Workflow, scope: Dict[str, Any]) -> Dict[str, Any]:
    base: Dict[str, Any] = {}
    for name, ws in scopemod.workspaces(scope).items():
        if ws["mode"] != "read":
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
    for name, base in state.get("readonly_baseline", {}).items():
        root = Path(scopemod.workspaces(scope)[name]["path"])
        if "git" in base:
            now = snapshot.git_porcelain(root) or ""
            before = set(base["git"].splitlines())
            changed = [ln[3:] for ln in now.splitlines() if ln not in before]
        else:
            changed = snapshot.diff(snapshot.load(Path(base["snap"])), _take(wf, root))
        if changed:
            out.append(f"The read-only workspace {name} changed: {', '.join(changed[:8])} — restore it "
                       "(read-only means no edits, builds, or generated files there).")
    return out


def _loaded(wf: Workflow, state: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Dict[str, Any]]]:
    if state.get("plan_approved_sha") and sha_file(wf.plan_json) != state["plan_approved_sha"]:
        raise TPError("plan.json changed after approval — restore it, or ask the human and run "
                      "`tp revise --feedback \"<their words>\"`.")
    plan = planmod.load_plan(wf)
    scope = scopemod.load_scope(wf)
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


def _authoring_step(task: Dict[str, Any], scope: Dict[str, Any]) -> str:
    return "impl" if planmod.is_code(task, scope) else "author"


def _cap(ts: Dict[str, Any]) -> int:
    return limit("max_fix_rounds") + ts.get("extra_rounds", 0)


# --- next --------------------------------------------------------------------------------

def _action_for(tid: str, ts: Dict[str, Any], task: Dict[str, Any], scope: Dict[str, Any],
                state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    status = ts["status"]
    act: Dict[str, Any] = {"id": tid, "model": task.get("model"), "agent_id": None}
    if status == "pending":
        if _deps_open(task, state):
            return None
        code = planmod.is_code(task, scope)
        step = "tests" if code else "author"
        act.update(action="dispatch", step=step,
                   agent=planmod.tests_agent(task, scope) if code else task["agent"])
    elif status == "needs_impl":
        act.update(action="dispatch", step="impl", agent=task["agent"])
    elif status == "needs_fix":
        fixing = ts["fixing"] or _authoring_step(task, scope)
        agent = planmod.tests_agent(task, scope) if fixing == "tests" else task["agent"]
        act.update(action="fix", step="fix", agent=agent, agent_id=ts["agents"].get(fixing))
    elif status == "needs_review":
        act.update(action="review", step="review", agent=planmod.reviewer_for(task, scope),
                   agent_id=ts["agents"].get("review"))
    else:
        return None
    return act


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
        return _research().actions(state, free) + [{"action": "plan"}]
    if phase == "AWAITING_APPROVAL":
        return [{"action": "human", "why": "approve or revise the plan in plan.md"}]

    plan, scope, tasks = _loaded(wf, state)
    acts = []
    if state.get("blocked"):
        acts.append({"action": "human", "why": state["blocked"]["summary"]})
    for tid, ts in state["tasks"].items():
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
        if free <= 0:
            break
        act = _action_for(tid, state["tasks"][tid], tasks[tid], scope, state)
        if act:
            acts.append(act)
            free -= 1
    review_acts = _review().actions(state, free)
    acts += review_acts
    everything_done = all(ts["status"] in DONE_STATES for ts in state["tasks"].values())
    if (everything_done and not state["in_flight"] and not state.get("blocked")
            and not _review().open_sessions(state)):
        pending = _closeout_pending(wf, state)
        acts.append({"action": "closeout", "why": pending} if pending else {"action": "final"})
    if (not any(a["action"] in ("dispatch", "fix", "review", "final", "closeout", "rerun") for a in acts)
            and state["in_flight"]):
        acts.append({"action": "wait", "ids": list(state["in_flight"])})
    return acts


GUIDE = {
    "scope": "Draft scope.json (`tp schema scope`), then `tp scope check`, then confirm it with the human.",
    "plan": "Write plan.json (`tp schema plan`), `tp plan check`, then `tp plan submit`.",
    "dispatch": "`tp dispatch {id}`, then send the call it prints.",
    "fix": "`tp dispatch {id}` (fix round), then send the call it prints.",
    "review": "`tp dispatch {id}`, then send the call it prints.",
    "check": "Fact-check {id}: read the sample `tp record` printed (or `tp sample {id}`); then "
             "`tp accept {id} --note \"...\"` or `tp reject {id} --reason \"...\"`.",
    "triage": "Triage {id}: `tp show {id} --part blocking`, check each against the source, then "
              "`tp triage {id} --accept-all`, or `--dismiss F# --reason \"...\"` and/or `--assign F#=T##`.",
    "followup": "Decide {id} ({why}): pursue it (`tp research add ... --from {id}`) or "
                "`tp research dismiss {id} --reason \"...\"`.",
    "human": "Stop and ask the human{about}: {why}. Record the answer with `tp resolve ... --by human`.",
    "rerun": "{why}. Check the workspace for stranded edits, then `tp resolve --task {id} --action retry "
             "--answer \"...\" --by manager` and `tp dispatch {id}` (a fresh agent).",
    "wait": "Wait for {ids} to hand back; end your turn if nothing else is actionable.",
    "halting": "Halt requested: record {ids} as they hand back; dispatch nothing new.",
    "halted": "Halted. Tell the human where work stopped (`halt.json`), then stop. `tp resume --answer \"...\"` "
              "continues.",
    "final": "`tp final` — package checks and the report.",
    "closeout": "Closeout ({why}): `tp closeout` lists what was noticed; classify each (`tp closeout --item N "
                "--class deferred|followup|observation --note \"<the issue and its consequence>\"`), then "
                "`tp closeout --ask`, ask it once, and `tp closeout --decide --answer \"<their words>\"`.",
    "done": "Report to the human from report.md.",
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
    for a in acts:
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


_GROUP_LABEL = {"code": "coding", "tests": "coding", "kb": "writing", "docs": "writing", "tutorial": "writing",
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
    return {
        "serves": "; ".join(f"{d} — {deliverables[d]['what']}" for d in task["serves"] if d in deliverables),
        "scope_md": wf.root / "scope.md",
        "write_paths": [str(ws / p) for p in task["paths"]],
        "readonly": [w["path"] for w in wss.values() if w["mode"] == "read"],
        "sources": sources or [str(ws)],
        "checks": checks,
        "tests_paths": [str(ws / p) for p in task.get("tests_paths", task["paths"])],
        "decisions": decision_lines(state, [task["id"]]),
        "conventions": [str(p) for p in planmod.conventions(plan, scope, wf.root)],
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
        if ts["status"] == "pending" and _deps_open(task, state):
            raise TPError(f"{tid} waits on {', '.join(_deps_open(task, state))} (not accepted yet).")
        act = _action_for(tid, ts, task, scope, state)
        if act is None:
            raise TPError(f"{tid} is {ts['status']}; there is nothing to dispatch.")
        _slots(state)
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
            ctx["cap"] = _cap(ts)
            text = briefs.fix(task, rnd, ctx, _stale_guard(wf, task, scope, rnd) + ts["findings"], result,
                              same_agent=bool(act["agent_id"]))
            label = f"fix-{rnd}"
        else:
            brief, result = run / f"brief-{step}-{ts['round']}.md", run / f"result-{step}.json"
            text = briefs.author(task, step, ts["round"], ctx, result)
            label = f"{step}-{ts['round']}"
        if result.exists():
            result.unlink()
        brief.write_text(text)
        snap = run / f"snap-{label}.json"
        snapshot.save(snap, _take(wf, _ws(scope, task["workspace"])))
        for other in state["in_flight"].values():
            other.setdefault("concurrent", []).append(tid)
        state["in_flight"][tid] = {"step": step, "since": now_iso(), "snap": str(snap), "agent": act["agent"],
                                   "concurrent": list(state["in_flight"]), "from": ts["status"],
                                   "head": _git_head(_ws(scope, task["workspace"])),
                                   "evidence": step != "review"}  # the brief asked for acceptance evidence
        ts["status"], ts["step"] = "in_flight", step
        ts["started"] = ts["started"] or now_iso()
        wf.save(state)
        wf.event("dispatch", id=tid, step=step, agent=act["agent"], round=ts["round"])
        call = briefs.dispatch_line(act["agent"], f"{tid} {step}", briefs.prompt(brief, result),
                                    act["agent_id"], act.get("model"))
        return (f"DISPATCH {tid} · {step} · {act['agent']}\nbrief: {brief}\nsend: {call}\n"
                f"then, when it replies: tp record {tid} --agent-id <its agent id>")


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
    elif words(data["summary"]) > 80:
        errs.append(f"summary is {words(data['summary'])} words; the limit is 80.")
    for key in ("changed", "noticed", "questions"):
        if not isinstance(data.get(key, []), list):
            errs.append(f"`{key}` must be a list.")
    if data.get("status") == "needs_input" and not data.get("questions"):
        errs.append("needs_input needs `questions`.")
    if criteria and data.get("status") == "done":
        errs += _evidence_errors(data, criteria)
    return errs


def _run_cmd(cmd: str, cwd: Path, log: Path) -> Tuple[bool, str]:
    try:
        proc = subprocess.run(["bash", "-c", cmd], cwd=str(cwd), capture_output=True, text=True,
                              timeout=CHECK_TIMEOUT)
        output, ok = proc.stdout + proc.stderr, proc.returncode == 0
    except subprocess.TimeoutExpired:
        output, ok = f"timed out after {CHECK_TIMEOUT}s", False
    log.write_text(f"$ {cmd}\n(cwd {cwd})\n\n{output}")
    tail = "\n".join(output.strip().splitlines()[-12:])
    return ok, tail


def _repos(scope: Dict[str, Any]) -> Dict[str, Path]:
    return {n: Path(w["path"]) for n, w in scopemod.workspaces(scope).items() if w["mode"] == "read"}


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
        files = _expand(_ws(scope, task["workspace"]), task["paths"])
        out = out.replace("{paths}", " ".join(shlex.quote(str(f)) for f in files))
    return out


def _task_checks(wf: Workflow, task: Dict[str, Any], scope: Dict[str, Any], plan: Dict[str, Any],
                 label: str) -> List[str]:
    failures = []
    ws = _ws(scope, task["workspace"])
    for name in task.get("checks", []):
        log = wf.run_dir(task["id"]) / f"check-{name}-{label}.log"
        if name == "docs":
            files = [f for f in _expand(ws, task["paths"]) if f.suffix == ".md"]
            errors, warnings, stats = docscheck.check(files, _repos(scope))
            log.write_text("\n".join(errors + [f"WARN {w}" for w in warnings]) or f"ok: {stats}")
            if errors:
                failures.append(f"Check `docs` failed ({len(errors)} problems; log {log}): " + "; ".join(errors[:6]))
        else:
            spec = plan["checks"][name]
            cwd = _ws(scope, spec["cwd"]) if spec.get("cwd") else ws
            ok, tail = _run_cmd(_expand_cmd(spec["cmd"], task, scope), cwd, log)
            if not ok:
                failures.append(f"Check `{name}` failed (log {log}): {tail}")
    return failures


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


def _tests_weakened(old: Path, new: Path) -> Optional[str]:
    """None when an edit to a test file only added or reformatted lines; otherwise the lines it
    dropped without re-adding them (deleted tests, gutted assertions)."""
    if not old.is_file():
        return None
    if not new.is_file():
        return "the whole file was deleted"
    kept = {ln.strip() for ln in new.read_text().splitlines()}
    dropped = [ln.strip() for ln in old.read_text().splitlines() if ln.strip() and ln.strip() not in kept]
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


def add_fix(wf: Workflow, state: Dict[str, Any], tid: str, findings: List[str], fixing: str) -> str:
    """Send findings from outside the task's own steps (review triage, a reopen) to its author.
    They join a fix round that has not been dispatched yet; otherwise they open a round of their
    own that does not count against the task's cap. Refused while the task is in flight or blocked:
    rewriting its state then would pull it from under the agent or skip the human."""
    ts = state["tasks"][tid]
    if tid in state["in_flight"]:
        raise TPError(f"{tid} is in flight ({state['in_flight'][tid]['step']}); send it more fixes once it has "
                      "handed back and been recorded.")
    if ts["status"] in ("pending", "needs_impl", "blocked"):
        raise TPError(f"{tid} is {ts['status']}; it takes fixes once it is authored and not waiting on the human.")
    if ts["status"] == "needs_fix":
        if ts.get("fixing") != fixing:
            raise TPError(f"{tid}'s waiting fix round is for its {ts.get('fixing')} step; send these after it.")
        ts["findings"] = list(ts["findings"]) + findings
        (wf.run_dir(tid) / f"findings-{ts['round']}.json").write_text(json.dumps(ts["findings"], indent=1))
        return "\n".join([f"{tid}: added to fix round {ts['round']}, not dispatched yet:"] + [f"  - {f}" for f in findings])
    if ts["status"] == "accepted":  # it sat finished until now; that was not work on it
        _pause(ts, ts.get("accepted"))
    ts["extra_rounds"] = ts.get("extra_rounds", 0) + 1
    task = next(t for t in planmod.load_plan(wf)["tasks"] if t["id"] == tid)
    return _fail(wf, ts, tid, findings, fixing, ws=_ws(scopemod.load_scope(wf), task["workspace"]))


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


def _evidence_lines(wf: Workflow, task: Dict[str, Any]) -> List[str]:
    """The latest authoring hand-back's evidence for each Done-when item, for the manager to check."""
    results = sorted((p for p in wf.run_dir(task["id"]).glob("result-*.json")
                      if p.stem in ("result-author", "result-impl", "result-fix")), key=lambda p: p.stat().st_mtime)
    given = load_json(results[-1], "the agent's result").get("acceptance") if results else None
    if not isinstance(given, list):
        return []
    by_n = {int(str(e.get("criterion")).strip()): e.get("evidence") for e in given
            if isinstance(e, dict) and str(e.get("criterion", "")).strip().isdigit()}
    return (["acceptance evidence (check each holds up):"]
            + [f"  {n}. {a} — {by_n.get(n, '(none given)')}" for n, a in enumerate(task["acceptance"], 1)])


def _sample(wf: Workflow, task: Dict[str, Any], scope: Dict[str, Any]) -> str:
    ws = _ws(scope, task["workspace"])
    files = _expand(ws, task["paths"])
    md = [f for f in files if f.suffix == ".md"]
    out = _evidence_lines(wf, task)
    if md:
        cites = docscheck.sample(md, _repos(scope), n=3, seed=task["id"])
        out += (["sample for your fact check (does each source line say what the sentence claims?):"] + cites
                if cites else ["sample: no path:line citations in the deliverable — read one section against its source."])
    code = [f for f in files if f.suffix != ".md"]
    if code:
        stat = subprocess.run(["git", "-C", str(ws), "diff", "--stat", "--", *[str(f) for f in code]],
                              capture_output=True, text=True).stdout.strip()
        out += ["diff:", stat or "(untracked files: " + ", ".join(str(f.relative_to(ws)) for f in code[:8]) + ")"]
    return "\n".join(out)


def cmd_record(wf: Workflow, tid: str, agent_id: Optional[str]) -> str:
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
        if agent_id:
            ts["agents"][effective] = agent_id
        res_path = wf.run_dir(tid) / f"result-{step}.json"
        if not res_path.exists():
            raise TPError(f"{res_path} is missing — the agent must write it before you record.")
        data = load_json(res_path, "the agent's result")
        # Evidence is asked of authoring and implementation hand-backs whose brief asked for it (an
        # agent briefed before evidence existed is not refused for leaving it out).
        criteria = len(task["acceptance"]) if fl.get("evidence") and effective in ("author", "impl") else 0
        errs = _validate_result(data, tid, step, criteria)
        if errs:
            raise TPError(*[f"{res_path}: {e}" for e in errs],
                          "Ask the same agent to fix the file (SendMessage), then record again.")
        for item in data.get("noticed", []):
            wf.noticed(tid, str(item))
        state.get("lost", {}).pop(tid, None)  # a real hand-back ends a run of lost dispatches
        minutes = minutes_since(fl["since"])
        if data["status"] != "done":
            del state["in_flight"][tid]
            ts["status"] = "blocked"
            asks = data.get("questions") or [data["summary"]]
            ts["blocked"] = {"kind": "input", "summary": f"{tid} {data['status']}: " + " | ".join(asks), "step": step,
                             "snap": fl["snap"], "head": fl.get("head"), "evidence": fl.get("evidence"),
                             "since": now_iso()}
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
        if step != "fix" and not changed and planmod.task_kind(task, scope) != "integration":
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
        allowed = list(task["paths"])
        for other in fl.get("concurrent", []):
            if other in tasks and tasks[other]["workspace"] == task["workspace"]:
                allowed += tasks[other]["paths"]
        off = [c for c in changed if not snapshot.matches(c, allowed)]
        if off:
            findings.append(f"Changed files outside this task's paths: {', '.join(off[:10])} — revert them; if the "
                            "task cannot be done without them, hand back `blocked` and say why.")
        findings += _readonly_changes(wf, state, scope)
        label = f"{step}-{ts['round']}"
        if effective == "tests":
            ok, tail = _run_cmd(task["test_cmd"], ws, wf.run_dir(tid) / f"tests-{label}.log")
            if task.get("test_mode", "red") == "red":
                if ok:
                    findings.append(f"The tests pass before any implementation, so they are not red: they do not "
                                    f"prove the new behaviour. `{task['test_cmd']}` passed.")
                else:
                    msgs.append(f"red: `{task['test_cmd']}` fails as expected.")
            elif not ok:
                findings.append(f"The characterization tests must pass against current code: {tail}")
            else:
                msgs.append("pinned: characterization tests pass.")
            if not findings:
                ts["tests_hash"] = _tests_hash(task, scope)
                _freeze_tests_baseline(wf, task, scope)
        elif effective == "impl":
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
            ok, tail = _run_cmd(task["test_cmd"], ws, wf.run_dir(tid) / f"tests-{label}.log")
            if ok:
                msgs.append(f"green: `{task['test_cmd']}` passes.")
            else:
                findings.append(f"The tests are not green: `{task['test_cmd']}` failed: {tail}")
        if effective in ("author", "impl"):
            findings += _task_checks(wf, task, scope, plan, label)
        del state["in_flight"][tid]
        if findings:
            out = _fail(wf, ts, tid, findings, fixing=effective, ws=ws)
        elif effective == "tests":
            ts["status"] = "needs_impl"
            out = f"{tid} tests recorded; " + " ".join(msgs) + " Next: implementation."
        elif planmod.reviewer_for(task, scope):
            ts["status"] = "needs_review"
            out = f"{tid} passed its checks. " + " ".join(msgs) + " Next: review."
        else:
            ts["status"] = "needs_check"
            out = f"{tid} passed its checks. " + " ".join(msgs) + "\n" + _sample(wf, task, scope)
        wf.save(state)
        wf.event("record", id=tid, step=step, status=ts["status"], minutes=round(minutes, 1), round=ts["round"])
        return out


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
        out = _fail(wf, ts, tid, findings, fixing=_authoring_step(task, scope), ws=ws)
    else:
        ts["status"] = "needs_check"
        minor = len(data["findings"])
        out = f"{tid} review {n} passed ({minor} non-blocking notes in {path.name}).\n" + _sample(wf, task, scope)
    wf.save(state)
    wf.event("record", id=tid, step="review", status=ts["status"], minutes=round(minutes_since(fl["since"]), 1))
    return out


# --- manager verdicts and exceptions --------------------------------------------------------

def cmd_accept(wf: Workflow, tid: str, note: str) -> str:
    with wf.locked():
        state = wf.load()
        _loaded(wf, state)
        ts = state["tasks"].get(tid)
        if ts is None or ts["status"] != "needs_check":
            raise TPError(f"{tid} is not awaiting your fact check (status {ts and ts['status']}).")
        ts.update(status="accepted", accepted=now_iso(), note=note)
        wf.save(state)
        mins = task_minutes(state, ts)
        wf.event("accept", id=tid, minutes=round(mins, 1), wall=round(minutes_since(ts["started"]), 1))
        return f"accepted {tid} ({mins:.0f} min, {ts['round']} fix rounds). Next: `tp next`."


def cmd_reject(wf: Workflow, tid: str, reason: str) -> str:
    with wf.locked():
        state = wf.load()
        _, scope, tasks = _loaded(wf, state)
        ts = state["tasks"].get(tid)
        if ts is None or ts["status"] != "needs_check":
            raise TPError(f"{tid} is not awaiting your fact check.")
        out = _fail(wf, ts, tid, [f"Manager fact check: {reason}"], fixing=_authoring_step(tasks[tid], scope),
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
_STEP_STATUS = {"tests": "pending", "author": "pending", "impl": "needs_impl", "fix": "needs_fix",
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
        out = add_fix(wf, state, tid, [note], fixing=_authoring_step(tasks[tid], scope))
        state.pop("final_failed", None)
        wf.save(state)
        return f"{tid} reopened. `tp next`.\n{out}"
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
        state["in_flight"][tid] = {"step": step, "since": now_iso(), "snap": ts["blocked"]["snap"],
                                   "agent": None, "concurrent": list(state["in_flight"]),
                                   "from": _STEP_STATUS[step], "head": ts["blocked"].get("head"),
                                   "evidence": ts["blocked"].get("evidence")}
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
                         "exception": "answer, retry, or skip"}[kind] + ".")
    wf.save(state)
    return f"{tid} resolved ({action}). `tp next`."


# --- final ----------------------------------------------------------------------------------

# --- closeout -------------------------------------------------------------------------------

CLOSEOUT_CLASSES = ("deferred", "followup", "observation")
_UNDECIDED = "deferred or follow-up work awaits the human's decision"


def _noticed_text(raw: str) -> str:
    """A noticed item without its `(source, ×N)` marker, normalized: the key its class is kept under."""
    m = re.match(r"\([^)]*\) (.*)$", raw, re.S)
    return " ".join((m.group(1) if m else raw).split())


def _closeout_marks(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return state.get("closeout", {}).get("items", {})


def _closeout_unclassified(wf: Workflow, state: Dict[str, Any]) -> int:
    return len({_noticed_text(r) for r in wf.noticed_items()} - set(_closeout_marks(state)))


def _closeout_pending(wf: Workflow, state: Dict[str, Any]) -> Optional[str]:
    """What still keeps the report back, or None: noticed items nobody classified, or deferred or
    follow-up work without the human's recorded answer."""
    unclassified = _closeout_unclassified(wf, state)
    if unclassified:
        return f"{unclassified} noticed item(s) unclassified"
    open_ = {_noticed_text(r) for r in wf.noticed_items()}
    if (any(v.get("class") in ("deferred", "followup") for k, v in _closeout_marks(state).items() if k in open_)
            and not state.get("closeout", {}).get("decision")):
        return _UNDECIDED
    return None


def cmd_closeout(wf: Workflow, item: Optional[int] = None, cls: Optional[str] = None, note: Optional[str] = None,
                 decide: bool = False, answer: Optional[str] = None, ask: bool = False) -> str:
    """The gate between the last acceptance and the report: classify every noticed item, and put
    deferred or follow-up work to the human once, their answer recorded. Without it, ticket-scope
    gaps found mid-run rest as noticed lines and go silently undone. A deferred or follow-up item's
    note is what the human reads when deciding, so it states the issue and its consequence."""
    with wf.locked():
        state = wf.load()
        if state["phase"] != "EXECUTING":
            raise TPError(f"closeout applies while EXECUTING; the workflow is {state['phase']}.")
        items = wf.noticed_items()
        marks = _closeout_marks(state)
        open_ = {_noticed_text(r) for r in items}
        chosen = sorted(((text, e) for text, e in marks.items()
                         if text in open_ and e.get("class") in ("deferred", "followup")), key=lambda kv: kv[1]["class"])
        if ask or decide:
            if decide and not answer:
                raise TPError("--decide needs --answer \"<the human's words>\".")
            if state.get("closeout", {}).get("decision") and ask:
                raise TPError("the human's decision is already recorded — `tp final` writes the report.")
            unclassified = _closeout_unclassified(wf, state)
            if unclassified:
                raise TPError(f"{unclassified} noticed item(s) unclassified — classify them first (`tp closeout`).")
            if not chosen:
                raise TPError("nothing is deferred or a follow-up, so no human decision is needed — `tp final`.")
        if ask:
            out = [f"DEFERRAL DECISION — {len(chosen)} noticed item(s) are work this run did not do. How should they "
                   "be handled: accept the deferral, file follow-up tasks, or extend the run?", ""]
            for i, (text, e) in enumerate(chosen, 1):
                out += [f"{i}. [{e['class']}] {text}", f"   Why it matters: {e.get('note')}"]
            out += ["", "Ask this once with AskUserQuestion, then record their words verbatim:",
                    "tp closeout --decide --answer \"<the human's words>\""]
            return "\n".join(out)
        if decide:
            state.setdefault("closeout", {})["decision"] = {"ts": now_iso(), "answer": answer}
            wf.save(state)
            wf.decision("closeout: deferred and follow-up work", str(answer), who="human")
            wf.event("closeout_decision")
            return "the human's decision is recorded. `tp final` writes the report."
        if item is not None:
            if cls not in CLOSEOUT_CLASSES:
                raise TPError(f"--class must be one of {', '.join(CLOSEOUT_CLASSES)}.")
            if cls != "observation" and (not note or words(note) < 4):
                raise TPError(f"--class {cls} needs --note in plain language: what the issue is and the consequence "
                              "of leaving it (the note is what the human reads when deciding) — never a bare file "
                              "path or ticket shorthand.")
            if not 1 <= item <= len(items):
                raise TPError(f"there is no noticed item #{item} ({len(items)} open) — `tp closeout` lists them.")
            entry = {"class": cls, **({"note": " ".join(note.split())} if note else {})}
            state.setdefault("closeout", {}).setdefault("items", {})[_noticed_text(items[item - 1])] = entry
            if cls != "observation":
                state["closeout"].pop("decision", None)  # new deferred work needs its own answer
            wf.save(state)
            wf.event("closeout_class", cls=cls)
            pending = _closeout_pending(wf, state)
            tail = ("`tp closeout --ask` renders the question for the human." if pending == _UNDECIDED
                    else "`tp final` writes the report." if pending is None else "`tp closeout` lists the rest.")
            return f"item #{item} classified {cls}" + (f" — {entry['note']}" if note else "") + f". {tail}"
        if not items:
            return "nothing was noticed outside the plan — `tp final` writes the report."
        out = [f"CLOSEOUT — {len(items)} noticed item(s), "
               f"{sum(_noticed_text(r) in marks for r in items)} classified:"]
        for n, raw in enumerate(items, 1):
            e = marks.get(_noticed_text(raw), {})
            out.append(f"  {n}. [{e.get('class', 'UNCLASSIFIED')}] {raw}" + (f" — {e['note']}" if e.get("note") else ""))
        out += ["Classify each: tp closeout --item N --class deferred|followup|observation --note \"<the issue and "
                "its consequence>\" (deferred: work left undone; followup: its own task to file; observation: no "
                "action). Then, if anything is deferred or a follow-up: tp closeout --ask, and ask the human once."]
        return "\n".join(out)


def _run_final_checks(wf: Workflow, state: Dict[str, Any], plan: Dict[str, Any],
                      scope: Dict[str, Any]) -> Tuple[List[Tuple[str, str]], List[str]]:
    """Run the plan's final checks: ([(baseline key, failure)], result lines). The key says which
    failure it is across runs: a docs-all problem by its own text (deterministic), a command check
    by its name (its output shifts run to run)."""
    failures: List[Tuple[str, str]] = []
    results: List[str] = []
    for name in plan.get("final_checks", []):
        log = wf.meta / f"final-{name}.log"
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
            ok, tail = _run_cmd(_expand_cmd(spec["cmd"], None, scope), cwd, log)
            results.append(f"{name}: {'ok' if ok else 'failed'}")
            if not ok:
                failures.append((f"check:{name}", f"final check {name} failed (log {log}): {tail}"))
    return failures, results


def cmd_baseline(wf: Workflow) -> str:
    """Record which final checks already fail before this run touches anything (machine quirks,
    sandbox limits, breakage already on the branch), so `tp final` can name them pre-existing
    instead of presenting them as the run's own. Run it right after approval."""
    with wf.locked():
        state = wf.load()
        if state["phase"] != "EXECUTING":
            raise TPError(f"baseline runs while EXECUTING; the workflow is {state['phase']}.")
        if state["in_flight"]:
            raise TPError(f"agents are in flight ({', '.join(state['in_flight'])}) — record them before baselining.")
        plan, scope, _ = _loaded(wf, state)
        failures, results = _run_final_checks(wf, state, plan, scope)
        state["final_baseline"] = sorted({key for key, _ in failures})
        wf.save(state)
        wf.event("baseline", failures=len(state["final_baseline"]))
        n = len(state["final_baseline"])
        head = (f"baseline recorded: {n} final-check failure(s) pre-date this run." if n
                else "baseline recorded: every final check passes right now.")
        return "\n".join([head] + [f"  - {r}" for r in results]
                         + ["`tp final` names these as pre-existing; the human still decides what to do with them."])


def cmd_final(wf: Workflow) -> str:
    with wf.locked():
        state = wf.load()
        if state["phase"] != "EXECUTING":
            raise TPError(f"final runs while EXECUTING; the workflow is {state['phase']}.")
        plan, scope, tasks = _loaded(wf, state)
        open_ = [f"{t} ({ts['status']})" for t, ts in state["tasks"].items() if ts["status"] not in DONE_STATES]
        if open_ or state["in_flight"]:
            raise TPError(f"open tasks: {', '.join(open_ or list(state['in_flight']))}.")
        reviews_open = _review().open_sessions(state)
        if reviews_open:
            raise TPError(f"review sessions still open: {', '.join(reviews_open)} — `tp next`.")
        pending = _closeout_pending(wf, state)
        if pending:
            raise TPError(f"the closeout is open: {pending}. `tp closeout` lists the noticed items; classify each, "
                          "and put deferred or follow-up work to the human (`tp closeout --ask`, then "
                          "`tp closeout --decide --answer \"...\"`).")
        keyed, results = _run_final_checks(wf, state, plan, scope)
        baseline = set(state.get("final_baseline", []))
        failures = [f + (" [pre-existing: it failed at the recorded baseline too]" if key in baseline else "")
                    for key, f in keyed] + _readonly_changes(wf, state, scope)
        if failures:
            state["final_failed"] = failures[:50]
            wf.save(state)
            pre_only = all(key in baseline for key, _ in keyed) and len(keyed) == len(failures)
            raise TPError(*failures[:40], "Every failure above pre-dates this run (`tp baseline`): ask the human "
                          "whether to fix it in this run or leave it." if pre_only else
                          "Fix path: `tp exception --summary ...` and ask the human, or "
                          "`tp resolve --task T## --action reopen --answer ... --by human` if the human already "
                          "decided.")
        state["phase"] = "DONE"
        state["done"] = now_iso()
        state.pop("final_failed", None)
        wf.save(state)
        (wf.root / "report.md").write_text(_report_md(wf, state, plan, scope, results))
        wf.event("done")
        return f"DONE — report: {wf.root / 'report.md'}. Present it to the human (answer-first)."


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
            f"{t['id']} (`{', '.join(t['paths'])}`)" for t in served))
    out += ["", "## Tasks", ""] + _task_rows(wf, state, tasks)
    notes = [f"- {tid}: {ts['note']}" for tid, ts in state["tasks"].items() if ts.get("note")]
    if notes:
        out += ["", "## Manager fact-check notes", ""] + notes
    review_lines = _review().report_lines(state)
    if review_lines:
        out += ["", "## Review", ""] + review_lines
    research = _research().summary(state, scope)
    if research:
        out += ["", "## Research", "", f"- {research}"]
    out += ["", "## Final checks", ""] + ([f"- {r}" for r in results] or ["- none planned"])
    groups: Dict[str, List[str]] = {c: [] for c in CLOSEOUT_CLASSES + ("unclassified",)}
    for raw in wf.noticed_items():
        e = _closeout_marks(state).get(_noticed_text(raw), {})
        groups[e.get("class", "unclassified")].append(f"- {raw}" + (f" — {e['note']}" if e.get("note") else ""))
    titles = {"deferred": "Deferred with the human's OK (their decision is in `decisions.md`)",
              "followup": "Follow-ups this run did not do (the human's decision is in `decisions.md`)",
              "observation": "Observations — no action taken",
              "unclassified": "Noticed, not in plan (for you to decide)"}
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
    reviews = state.get("reviews", {})
    if reviews:
        out.append("  reviews: " + ", ".join(f"{sid} {s['status']}" for sid, s in reviews.items()))
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
