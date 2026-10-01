"""Execution: what runs next, dispatching a step, recording its hand-back, and every gate
between steps — decided by this script, never by reading prose. Planning research lives in
research.py and end-of-pipeline review in review.py; this module routes to them."""
from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import briefs, docscheck, snapshot
from . import plan as planmod
from . import scope as scopemod
from .common import (TP_SCRIPT, TPError, Workflow, agent_minutes, limit, load_json, minutes_since, now_iso,
                     sha_file, words)

DONE_STATES = ("accepted", "skipped")
CHECK_TIMEOUT = 540

# Workflow-root paths the record and review gates never blame on an agent: tp.py itself
# writes them during a round — dispatch briefs, snapshots, findings and the result files
# every agent is mandated to produce under runs/, noticed.md appends made from a result's
# own `noticed` list during record, and plan.json, plan.approved.json and decisions.md
# rewritten by the manager's `tp amend` mid-flight. A workflow root that is also a task
# workspace (e.g. a Jira-filing pipeline whose only local deliverables are small record
# files) puts all of these inside the gate's diff. Plan tampering stays caught — harder —
# by the approved-sha check in `_loaded` on every command; noticed.md and decisions.md are
# tp-only by contract (see Workflow's docstring); report.md and halt.json are tp's edge
# outputs, written only with nothing in flight.
PIPELINE_OWNED = ("runs/**", "noticed.md", "decisions.md", "plan.json", "plan.approved.json",
                  "report.md", "halt.json")


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
            snapshot.save(snap_path, snapshot.take(root, [wf.root]))
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
            changed = snapshot.diff(snapshot.load(Path(base["snap"])), snapshot.take(root, [wf.root]))
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
            raise TPError(f"{Path(path).name} changed after approval: conventions are part of every brief's "
                          "contract. Restore it. To change conventions, edit the plan and use `tp amend`.")
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
            acts.append({"action": "human", "id": tid, "why": ts["blocked"]["summary"]})
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
        acts.append({"action": "final"})
    if not any(a["action"] in ("dispatch", "fix", "review", "final") for a in acts) and state["in_flight"]:
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
    "followup": "Decide {id} ({why}): pursue it (`tp research add ... --from {id}`, within the budget) or "
                "`tp research dismiss {id} --reason \"...\"`.",
    "human": "Stop and ask the human{about}: {why}. Record the answer with `tp resolve`.",
    "wait": "Wait for {ids} to hand back; end your turn if nothing else is actionable.",
    "halting": "Halt requested: record {ids} as they hand back; dispatch nothing new.",
    "halted": "Halted. Tell the human where work stopped (`halt.json`), then stop. `tp resume --answer \"...\"` "
              "continues.",
    "final": "`tp final` — package checks and the report.",
    "done": "Report to the human from report.md.",
}


def cmd_next(wf: Workflow, as_json: bool) -> str:
    state = wf.load()
    acts = actions(wf, state)
    spent = agent_minutes(wf, state)
    warnings = []
    if state["phase"] in ("SCOPING", "PLANNING") and spent > limit("planning_warn_minutes"):
        warnings.append(f"Planning has taken {spent:.0f} agent-min (target {limit('planning_warn_minutes')}): "
                        "submit what you have, with open questions for the human.")
    if as_json:
        return json.dumps({"phase": state["phase"], "actions": acts, "agent_minutes": round(spent, 1),
                           "budget_minutes": state.get("budget_minutes"), "warnings": warnings})
    out = [_headline(wf, state)] + [f"WARNING: {w}" for w in warnings]
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


def _headline(wf: Workflow, state: Dict[str, Any]) -> str:
    tasks = state["tasks"]
    done = sum(ts["status"] in DONE_STATES for ts in tasks.values())
    flight = ", ".join(f"{k} ({v['step']}, {minutes_since(v['since']):.0f}m)" for k, v in state["in_flight"].items())
    budget = state.get("budget_minutes")
    used = f"{agent_minutes(wf, state):.0f}" + (f" of {budget} agent-min" if budget else " agent-min")
    parts = [state["phase"], f"{done}/{len(tasks)} accepted" if tasks else None,
             f"in flight: {flight}" if flight else None, used]
    return " · ".join(p for p in parts if p)


# --- dispatch ---------------------------------------------------------------------------------

def _slots(state: Dict[str, Any]) -> None:
    if len(state["in_flight"]) >= limit("max_in_flight"):
        raise TPError(f"{limit('max_in_flight')} agents are already in flight ({', '.join(state['in_flight'])}) — "
                      "wait for one to hand back.")


def _expand(ws: Path, patterns: List[str]) -> List[Path]:
    out: List[Path] = []
    for p in patterns:
        if any(ch in p for ch in "*?["):
            out += sorted(x for x in ws.glob(p) if x.is_file())
        elif (ws / p).is_file():
            out.append(ws / p)
        elif (ws / p).is_dir():
            out += sorted(x for x in (ws / p).rglob("*") if x.is_file())
    return out


def _context(wf: Workflow, task: Dict[str, Any], scope: Dict[str, Any], plan: Dict[str, Any],
             state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    wss = scopemod.workspaces(scope)
    ws = _ws(scope, task["workspace"])
    deliverables = {d["id"]: d for d in scope["deliverables"]}
    checks = []
    for c in task.get("checks", []):
        checks.append(planmod.BUILTIN_TASK_CHECKS.get(c) or f"`{plan['checks'][c]['cmd']}`")
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
        "decisions": decision_lines(state or wf.load(), [task["id"]]),
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
            text = briefs.fix(task, rnd, ctx, ts["findings"], result, same_agent=bool(act["agent_id"]))
            label = f"fix-{rnd}"
        else:
            brief, result = run / f"brief-{step}-{ts['round']}.md", run / f"result-{step}.json"
            text = briefs.author(task, step, ts["round"], ctx, result)
            label = f"{step}-{ts['round']}"
        if result.exists():
            result.unlink()
        brief.write_text(text)
        snap = run / f"snap-{label}.json"
        snapshot.save(snap, snapshot.take(_ws(scope, task["workspace"]), [wf.root]))
        for other in state["in_flight"].values():
            other.setdefault("concurrent", []).append(tid)
        state["in_flight"][tid] = {"step": step, "since": now_iso(), "snap": str(snap), "agent": act["agent"],
                                   "concurrent": list(state["in_flight"]), "from": ts["status"]}
        ts["status"], ts["step"] = "in_flight", step
        ts["started"] = ts["started"] or now_iso()
        wf.save(state)
        wf.event("dispatch", id=tid, step=step, agent=act["agent"], round=ts["round"])
        call = briefs.dispatch_line(act["agent"], f"{tid} {step}", briefs.prompt(brief, result),
                                    act["agent_id"], act.get("model"))
        return (f"DISPATCH {tid} · {step} · {act['agent']}\nbrief: {brief}\nsend: {call}\n"
                f"then, when it replies: tp record {tid} --agent-id <its agent id>")


# --- record ---------------------------------------------------------------------------------

def _validate_result(data: Any, tid: str, step: str) -> List[str]:
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
            raw = spec.get("cwd")
            if raw and Path(raw).is_absolute():
                cwd = Path(raw)
            else:
                cwd = _ws(scope, raw) if raw else ws
            ok, tail = _run_cmd(_expand_cmd(spec["cmd"], task, scope), cwd, log)
            if not ok:
                failures.append(f"Check `{name}` failed (log {log}): {tail}")
    return failures


def _tests_hash(task: Dict[str, Any], scope: Dict[str, Any]) -> Dict[str, Optional[str]]:
    ws = _ws(scope, task["workspace"])
    rels = task.get("tests_paths") or []
    return snapshot.hash_files(ws, [str(p.relative_to(ws)) for p in _expand(ws, rels)] or rels)


def _fail(wf: Workflow, ts: Dict[str, Any], tid: str, findings: List[str], fixing: str) -> str:
    ts["round"] += 1
    ts["fixing"] = fixing
    ts["findings"] = findings
    (wf.run_dir(tid) / f"findings-{ts['round']}.json").write_text(json.dumps(findings, indent=1))
    lines = [f"  - {f}" for f in findings]
    if ts["round"] > _cap(ts):
        ts["status"] = "blocked"
        ts["blocked"] = {"kind": "rounds", "summary": f"{tid} still fails after {_cap(ts)} fix rounds"}
        wf.event("blocked", id=tid, reason="rounds")
        return "\n".join([f"BLOCKED {tid}: still failing after {_cap(ts)} fix rounds — the human decides "
                          "(retry, skip, or revise the plan)."] + lines)
    ts["status"] = "needs_fix"
    return "\n".join([f"FAIL {tid} → fix round {ts['round']} of {_cap(ts)}:"] + lines)


def _sample(wf: Workflow, task: Dict[str, Any], scope: Dict[str, Any]) -> str:
    ws = _ws(scope, task["workspace"])
    files = _expand(ws, task["paths"])
    md = [f for f in files if f.suffix == ".md"]
    out = []
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


def cmd_record(wf: Workflow, tid: str, agent_id: Optional[str], trim_summary: bool = False,
               credit: float = 0.0) -> str:
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
            return _record_review(wf, state, scope, tasks, tid, fl, agent_id, credit=credit)
        effective = ts["fixing"] if step == "fix" else step
        if agent_id:
            ts["agents"][effective] = agent_id
        res_path = wf.run_dir(tid) / f"result-{step}.json"
        if not res_path.exists():
            raise TPError(f"{res_path} is missing — the agent must write it before you record.")
        data = load_json(res_path, "the agent's result")
        if trim_summary and isinstance(data, dict) and words(data.get("summary", "")) > 80:
            # A mechanical rejection (e.g. an 82-word summary) should not cost an agent
            # round-trip: cut the summary to the limit and record what remains.
            kept: List[str] = []
            n = 0
            for w in str(data["summary"]).split():
                if n + len(w) + 1 > 78 and n >= 40:
                    break
                kept.append(w)
                n += len(w) + 1
            data["summary"] = " ".join(kept).rstrip(" .,;:") + "."
            res_path.write_text(json.dumps(data, indent=1) + "\n")
        errs = _validate_result(data, tid, step)
        if errs:
            raise TPError(*[f"{res_path}: {e}" for e in errs],
                          "Ask the same agent to fix the file (resume it: a new `task` call with its task_id), "
                          "then record again.")
        for item in data.get("noticed", []):
            wf.noticed(tid, str(item))
        minutes = minutes_since(fl["since"])
        wait = max(0.0, credit) if minutes > 0 else 0.0
        wait = min(wait, minutes)  # a credit can never push the tally negative
        minutes -= wait
        if wait:
            wf.event("credit", id=tid, minutes=round(wait, 1))
        state["agent_minutes"] = round(agent_minutes(wf, state) + minutes, 1)
        if data["status"] != "done":
            del state["in_flight"][tid]
            ts["status"] = "blocked"
            asks = data.get("questions") or [data["summary"]]
            ts["blocked"] = {"kind": "input", "summary": f"{tid} {data['status']}: " + " | ".join(asks), "step": step,
                             "snap": fl["snap"]}
            wf.save(state)
            wf.event("record", id=tid, step=step, status=data["status"], minutes=round(minutes, 1))
            return "\n".join([f"{tid} {data['status']}{' (credited ' + format(wait, '.0f') + ' min of human-wait)' if wait else ''} — answer from scope.md / plan.json / decisions.md if they "
                              "settle it; otherwise ask the human. Then `tp resolve --task "
                              f"{tid} --action answer --answer \"...\"`:"] + [f"  - {q}" for q in asks])

        findings: List[str] = []
        msgs: List[str] = []
        if wait:
            msgs.append(f"credited {wait:.0f} min of human-wait.")
        ws = _ws(scope, task["workspace"])
        changed = snapshot.diff(snapshot.load(Path(fl["snap"])), snapshot.take(ws, [wf.root]))
        allowed = list(task["paths"]) + list(PIPELINE_OWNED)
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
        elif effective == "impl":
            if ts.get("tests_hash") and _tests_hash(task, scope) != ts["tests_hash"]:
                bad = [k for k, v in _tests_hash(task, scope).items() if ts["tests_hash"].get(k) != v]
                findings.append(f"The tests changed during implementation (tests changed: {', '.join(bad)}) — "
                                "restore them; the implementation must not weaken the tests.")
            ok, tail = _run_cmd(task["test_cmd"], ws, wf.run_dir(tid) / f"tests-{label}.log")
            if ok:
                msgs.append(f"green: `{task['test_cmd']}` passes.")
            else:
                findings.append(f"The tests are not green: `{task['test_cmd']}` failed: {tail}")
        if effective in ("author", "impl"):
            findings += _task_checks(wf, task, scope, plan, label)
        del state["in_flight"][tid]
        if findings:
            out = _fail(wf, ts, tid, findings, fixing=effective)
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
                   tid: str, fl: Dict[str, Any], agent_id: Optional[str], credit: float = 0.0) -> str:
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
    changed = snapshot.diff(snapshot.load(Path(fl["snap"])), snapshot.take(ws, [wf.root]))
    allowed: List[str] = list(PIPELINE_OWNED)   # tp's own writes; a reviewer edits nothing
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
    if findings:
        out = _fail(wf, ts, tid, findings, fixing=_authoring_step(task, scope))
    else:
        ts["status"] = "needs_check"
        minor = len(data["findings"])
        out = f"{tid} review {n} passed ({minor} non-blocking notes in {path.name}).\n" + _sample(wf, task, scope)
    wf.save(state)
    review_minutes = minutes_since(fl["since"])
    wait = min(max(0.0, credit), review_minutes)
    review_minutes -= wait
    if wait:
        wf.event("credit", id=tid, minutes=round(wait, 1))
    state["agent_minutes"] = round(agent_minutes(wf, state) + review_minutes, 1)
    wf.event("record", id=tid, step="review", status=ts["status"], minutes=round(review_minutes, 1))
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
        task_min = sum(e.get("minutes", 0.0) for e in wf.events() if e["kind"] == "record" and e.get("id") == tid)
        wf.event("accept", id=tid, minutes=round(task_min, 1))
        return f"accepted {tid} ({task_min:.0f} agent-min, {ts['round']} fix rounds). Next: `tp next`."


def cmd_reject(wf: Workflow, tid: str, reason: str) -> str:
    with wf.locked():
        state = wf.load()
        _, scope, tasks = _loaded(wf, state)
        ts = state["tasks"].get(tid)
        if ts is None or ts["status"] != "needs_check":
            raise TPError(f"{tid} is not awaiting your fact check.")
        out = _fail(wf, ts, tid, [f"Manager fact check: {reason}"], fixing=_authoring_step(tasks[tid], scope))
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
            ts["blocked"] = {"kind": "exception", "summary": summary, "prior": prior}
            ts["status"] = "blocked"
        else:
            state["blocked"] = {"kind": "exception", "summary": summary, "since": now_iso()}
        wf.save(state)
        wf.event("exception", id=tid, summary=summary)
        return "raised — stop and put it to the human; record their answer with `tp resolve`."


def _keep_decision(holder: Dict[str, Any], question: str, answer: str, by: Optional[str] = None) -> None:
    """Keep an answer with the question it settles on the task (or workflow) it settles, so every
    later brief for that work quotes it; decisions.md alone never reaches an agent."""
    holder.setdefault("decisions", []).append({"q": question, "a": answer, "by": by, "ts": now_iso()})


def decision_lines(state: Dict[str, Any], tids: List[str]) -> List[str]:
    """The decisions a brief for these tasks must carry: the workflow's, then each task's own."""
    out = []
    for prefix, holder in [("", state)] + [(f"{t}: ", state["tasks"].get(t, {})) for t in tids]:
        for d in holder.get("decisions", []):
            out.append(f"{prefix}{d['q']} → {d['a']}" + (f" ({d['by']})" if d.get("by") else ""))
    return out


def cmd_resolve(wf: Workflow, tid: Optional[str], action: str, answer: str, exception: bool = False,
                noticed: Optional[int] = None, by: Optional[str] = None) -> str:
    if noticed is not None:
        with wf.locked():
            item = wf.noticed_resolve(noticed, answer)
            if item is None:
                raise TPError(f"no noticed item #{noticed}; `tp noticed` lists the open ones.")
            wf.decision(f"resolve noticed #{noticed}", answer, who=by)
            return f"noticed #{noticed} resolved — it no longer shows as open in submit output or the report."
    if exception:
        with wf.locked():
            state = wf.load()
            blocked = state.pop("blocked", None)
            if blocked is None or blocked.get("kind") != "exception":
                raise TPError("No workflow-level exception block to resolve (`tp exception --task` "
                              "ones resolve per task).")
            wf.decision("resolve workflow exception", answer, who=by)
            _keep_decision(state, blocked["summary"], answer, by)
            wf.save(state)
            return "exception resolved — continue with `tp next`."
    with wf.locked():
        state = wf.load()
        wf.decision(f"resolve {tid or 'workflow'} {action}", answer, who=by)
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
        if action == "reopen":
            if ts["status"] not in DONE_STATES + ("blocked",):
                raise TPError(f"{tid} is {ts['status']}; reopen applies to accepted, skipped, or blocked tasks.")
            _, scope, tasks = _loaded(wf, state)
            ts["extra_rounds"] += 1
            ts.update(status="needs_fix", fixing=_authoring_step(tasks[tid], scope), blocked=None,
                      findings=[f"Reopened by the human: {answer}"])
            _keep_decision(ts, "task reopened", answer, by)
            state.pop("final_failed", None)
            wf.save(state)
            return f"{tid} reopened for a fix round. `tp next`."
        if ts["status"] != "blocked":
            raise TPError(f"{tid} is not blocked (status {ts['status']}).")
        kind = ts["blocked"]["kind"]
        if action == "skip":
            ts.update(status="skipped", blocked=None, note=answer)
        elif action == "retry" and kind == "rounds":
            _keep_decision(ts, ts["blocked"]["summary"], answer, by)
            ts["extra_rounds"] += 1
            ts.update(status="needs_fix", blocked=None)
        elif action == "answer" and kind == "input":
            _keep_decision(ts, ts["blocked"]["summary"], answer, by)
            _slots(state)
            step = ts["blocked"]["step"]
            state["in_flight"][tid] = {"step": step, "since": now_iso(), "snap": ts["blocked"]["snap"],
                                       "agent": None, "concurrent": list(state["in_flight"])}
            ts.update(status="in_flight", blocked=None)
            effective = ts["fixing"] if step == "fix" else step
            agent_id = ts["agents"].get(effective)
            result = wf.run_dir(tid) / f"result-{step}.json"
            if result.exists():
                result.unlink()
            msg = (f"Answer: {answer} — continue your task, rewrite {result}, and reply with exactly one line: "
                   f"RESULT {result}")
            wf.save(state)
            target = f"task(task_id={json.dumps(agent_id)}, prompt={json.dumps(msg)})" if agent_id else \
                f"(no agent id recorded — dispatch fresh with the brief and the answer) {json.dumps(msg)}"
            return f"{tid} back in flight.\nsend: {target}\nthen: tp record {tid}"
        elif action == "answer" and kind == "exception":
            _keep_decision(ts, ts["blocked"]["summary"], answer, by)
            ts.update(status=ts["blocked"]["prior"], blocked=None)
        elif action == "retry" and kind == "exception":
            # A task-blocked exception over a stale check or count usually means: run the
            # round again with the human's correction in hand.
            _keep_decision(ts, ts["blocked"]["summary"], answer, by)
            ts["extra_rounds"] += 1
            ts.update(status="needs_fix", fixing=ts["blocked"].get("prior") or ts["fixing"], blocked=None)
        else:
            raise TPError(f"action {action!r} does not apply to a {kind} block; use "
                          + {"rounds": "retry or skip", "input": "answer or skip",
                             "exception": "answer, retry, or skip"}[kind] + ".")
        wf.save(state)
        return f"{tid} resolved ({action}). `tp next`."


# --- final ----------------------------------------------------------------------------------

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
        failures: List[str] = []
        results: List[str] = []
        for name in plan.get("final_checks", []):
            log = wf.meta / f"final-{name}.log"
            if name == "docs-all":
                for wname, w in scopemod.workspaces(scope).items():
                    if w["mode"] != "write":
                        continue
                    root = Path(w["path"])
                    index = next((root / n for n in ("index.md", "README.md") if (root / n).exists()), None)
                    docs = [d for d in docscheck.md_files([root]) if wf.root not in d.parents]
                    errors, warnings, stats = docscheck.check(docs, _repos(scope), index)
                    log.write_text("\n".join(errors + [f"WARN {w}" for w in warnings]) or f"ok: {stats}")
                    results.append(f"docs-all {wname}: {'ok' if not errors else f'{len(errors)} problems'}, "
                                   f"{len(warnings)} doubtful citations (log {log}) {stats}")
                    failures += errors
            else:
                spec = plan["checks"][name]
                cwd = _ws(scope, spec["cwd"]) if spec.get("cwd") else Path(next(
                    w["path"] for w in scopemod.workspaces(scope).values() if w["mode"] == "write"))
                ok, tail = _run_cmd(_expand_cmd(spec["cmd"], None, scope), cwd, log)
                results.append(f"{name}: {'ok' if ok else 'failed'}")
                if not ok:
                    failures.append(f"final check {name} failed (log {log}): {tail}")
        failures += _readonly_changes(wf, state, scope)
        if failures:
            state["final_failed"] = failures[:50]
            wf.save(state)
            raise TPError(*failures[:40], "Fix path: `tp exception --summary ...` and ask the human, or "
                          "`tp resolve --task T## --action reopen --answer ...` if the human already decided.")
        state["phase"] = "DONE"
        state["done"] = now_iso()
        state.pop("final_failed", None)
        wf.save(state)
        (wf.root / "report.md").write_text(_report_md(wf, state, plan, scope, results))
        wf.event("done")
        return f"DONE — report: {wf.root / 'report.md'}. Present it to the human (answer-first)."


def _task_rows(wf: Workflow, state: Dict[str, Any], tasks: Dict[str, Dict[str, Any]]) -> List[str]:
    rows = ["| Task | Title | Status | Min | Est | Fix rounds | Reviews |", "|---|---|---|---|---|---|---|"]
    # per-task agent-minutes from the record events (wall-clock spans idle time between messages)
    per_task: Dict[str, float] = {}
    for e in wf.events():
        if e["kind"] == "record" and "minutes" in e:
            per_task[e.get("id", "?")] = per_task.get(e.get("id", "?"), 0.0) + e["minutes"]
    for tid, ts in state["tasks"].items():
        mins = per_task.get(tid, 0.0)
        rows.append(f"| {tid} | {tasks[tid]['title'] if tid in tasks else '?'} | {ts['status']} | {mins:.0f} | "
                    f"{tasks.get(tid, {}).get('estimate_min', '?')} | {ts['round']} | {ts['reviews']} |")
    return rows


def _report_md(wf: Workflow, state: Dict[str, Any], plan: Dict[str, Any], scope: Dict[str, Any],
               results: List[str]) -> str:
    tasks = {t["id"]: t for t in plan["tasks"]}
    spent = agent_minutes(wf, state)
    budget = scope.get("budget_minutes")
    out = [f"# Report — {plan['title']}", "",
           f"All {len(tasks)} tasks finished: {sum(ts['status'] == 'accepted' for ts in state['tasks'].values())} "
           f"accepted, {sum(ts['status'] == 'skipped' for ts in state['tasks'].values())} skipped by the human. "
           f"Agent-minutes spent: {spent:.0f}"
           + (f", against a budget of {budget}." if budget else "."), "", "## Deliverables", ""]
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
    noticed = wf.noticed_items()
    if noticed:
        out += ["", "## Noticed, not in plan (for you to decide)", ""] + [f"- {n}" for n in noticed]
    out += ["", "Human decisions are in `decisions.md`; every brief, result, review, and check log is under `runs/`."]
    return "\n".join(out) + "\n"


def cmd_report(wf: Workflow) -> str:
    state = wf.load()
    planning = minutes_since(state["created"], state.get("approved"))
    out = [f"planning: {planning:.0f} min (start → approval)" + ("" if state.get("approved") else ", still open")]
    if state.get("approved"):
        out.append(f"execution: {minutes_since(state['approved'], state.get('done')):.0f} min")
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
    out = [f"{state['title']} — {_headline(wf, state)}", f"dir: {wf.root}"]
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
    out.append(cmd_next(wf, False).splitlines()[-1])
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
        "elapsed_min": round(minutes_since(state["created"]), 1), "agent_minutes": round(agent_minutes(wf, state), 1),
        "budget_minutes": state.get("budget_minutes"),
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


def add_fix(wf: Workflow, state: Dict[str, Any], tid: str, findings: List[str], fixing: str) -> str:
    """Send findings from outside the task's own steps (review triage, a reopen) to its author.
    They join a fix round that has not been dispatched yet; otherwise they open a round of their
    own that does not count against the task's cap. Refused while the task is in flight, not yet
    authored, or blocked: rewriting its state then would pull it from under the agent or skip the
    human."""
    ts = state["tasks"][tid]
    if tid in state["in_flight"]:
        raise TPError(f"{tid} is in flight ({state['in_flight'][tid]['step']}); send it more fixes once it has "
                      "handed back and been recorded.")
    if ts["status"] in ("pending", "needs_impl", "blocked"):
        raise TPError(f"{tid} is {ts['status']}; it takes fixes once it is authored and not waiting on the human.")
    if ts["status"] == "needs_fix":
        if ts.get("fixing") != fixing:
            raise TPError(f"{tid}'s waiting fix round is for its {ts.get('fixing')} step; send these after it.")
        ts["findings"] = list(ts.get("findings", [])) + findings
        (wf.run_dir(tid) / f"findings-{ts['round']}.json").write_text(json.dumps(ts["findings"], indent=1))
        return "\n".join([f"{tid}: added to fix round {ts['round']}, not dispatched yet:"]
                         + [f"  - {f}" for f in findings])
    ts["extra_rounds"] = ts.get("extra_rounds", 0) + 1
    return _fail(wf, ts, tid, findings, fixing=fixing)
