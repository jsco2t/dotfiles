"""Execution and recon: what runs next, dispatching a step, recording its hand-back, and
every gate between steps — decided by this script, never by reading prose."""
from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import briefs, docscheck, snapshot
from . import plan as planmod
from . import scope as scopemod
from .common import (TP_SCRIPT, TPError, Workflow, limit, load_json, minutes_since, now_iso, sha_file, words)

DONE_STATES = ("accepted", "skipped")
CHECK_TIMEOUT = 540
BANNED_RECON = [
    re.compile(r"\b(every|all)\s+(\w+\s+)?(files?|flags?|functions?|symbols?|packages?|commands?|fields?|"
               r"endpoints?|lines?|options?|types?)\b", re.I),
    re.compile(r"\bcomplete\s+(\w+\s+){0,2}(list|tree|inventory|reference|catalog(ue)?|walkthrough)\b", re.I),
    re.compile(r"\bexhaustive(ly)?\b", re.I),
    re.compile(r"\bend[- ]to[- ]end\b", re.I),
]


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


def actions(wf: Workflow, state: Dict[str, Any]) -> List[Dict[str, Any]]:
    phase = state["phase"]
    if phase == "SCOPING":
        if state.get("scope_checked_sha") and state["scope_checked_sha"] == sha_file(wf.scope_json):
            return [{"action": "human", "why": "confirm the scope in scope.md"}]
        return [{"action": "scope"}]
    if phase == "PLANNING":
        acts: List[Dict[str, Any]] = []
        busy = [r for r, v in state["recon"].items() if v["status"] == "in_flight"]
        free = limit("max_in_flight") - len(state["in_flight"])
        for rid, item in state["recon"].items():
            if item["status"] == "pending" and free > 0:
                acts.append({"action": "dispatch", "id": rid, "step": "recon", "agent": item["agent"],
                             "agent_id": None, "model": None})
                free -= 1
        if busy:
            acts.append({"action": "wait", "ids": busy})
        return acts + [{"action": "plan"}]
    if phase == "AWAITING_APPROVAL":
        return [{"action": "human", "why": "approve or revise the plan in plan.md"}]
    if phase == "DONE":
        return [{"action": "done"}]

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
    everything_done = all(ts["status"] in DONE_STATES for ts in state["tasks"].values())
    if everything_done and not state["in_flight"] and not state.get("blocked"):
        if _final_review_due(state, scope):
            if free > 0:
                acts.append({"action": "review", "id": "FINAL", "step": "review", "model": None, "agent_id": None,
                             "agent": scopemod.participants(scope, "reviewer")[0]})
        else:
            acts.append({"action": "final"})
    if not acts and state["in_flight"]:
        acts.append({"action": "wait", "ids": list(state["in_flight"])})
    return acts


def _final_review_due(state: Dict[str, Any], scope: Dict[str, Any]) -> bool:
    return scope.get("review") in ("final", "both") and not state.get("final_review_done")


GUIDE = {
    "scope": "Draft scope.json (SKILL.md › Scoping), then `tp scope check`, then confirm it with the human.",
    "plan": "Write plan.json (SKILL.md › Planning), `tp plan check`, then `tp plan submit`.",
    "dispatch": "`tp dispatch {id}`, then send the call it prints.",
    "fix": "`tp dispatch {id}` (fix round), then send the call it prints.",
    "review": "`tp dispatch {id}` (review), then send the call it prints.",
    "check": "Fact-check {id}: read the sample `tp record` printed (or `tp sample {id}`); then "
             "`tp accept {id} --note \"...\"` or `tp reject {id} --reason \"...\"`.",
    "human": "Stop and ask the human{about}: {why}. Record the answer with `tp resolve`.",
    "wait": "Wait for {ids} to hand back; end your turn if nothing else is actionable.",
    "final": "`tp final` — package checks and the report.",
    "done": "Report to the human from report.md.",
}


def cmd_next(wf: Workflow, as_json: bool) -> str:
    state = wf.load()
    acts = actions(wf, state)
    elapsed = minutes_since(state["created"])
    warnings = []
    if state["phase"] in ("SCOPING", "PLANNING") and elapsed > limit("planning_warn_minutes"):
        warnings.append(f"Planning has taken {elapsed:.0f} min (target {limit('planning_warn_minutes')}): "
                        "submit what you have, with open questions for the human.")
    if as_json:
        return json.dumps({"phase": state["phase"], "actions": acts, "elapsed_min": round(elapsed, 1),
                           "budget_minutes": state.get("budget_minutes"), "warnings": warnings})
    out = [_headline(state)] + [f"WARNING: {w}" for w in warnings]
    for a in acts:
        what = a["action"]
        label = f"{what} {a.get('id', '')}".strip()
        if a.get("agent"):
            label += f" ({a['step']} · {a['agent']}" + (f" · resume {a['agent_id']}" if a.get("agent_id") else "") + ")"
        about = f" about {a['id']}" if a.get("id") else ""
        out.append(f"→ {label}: " + GUIDE[what].format(id=a.get("id", ""), why=a.get("why", ""), about=about,
                                                      ids=", ".join(a.get("ids", []))))
    return "\n".join(out)


def _headline(state: Dict[str, Any]) -> str:
    tasks = state["tasks"]
    done = sum(ts["status"] in DONE_STATES for ts in tasks.values())
    flight = ", ".join(f"{k} ({v['step']}, {minutes_since(v['since']):.0f}m)" for k, v in state["in_flight"].items())
    budget = state.get("budget_minutes")
    used = f"{minutes_since(state['created']):.0f}" + (f" of {budget}" if budget else "") + " min"
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


def _context(wf: Workflow, task: Dict[str, Any], scope: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    wss = scopemod.workspaces(scope)
    ws = _ws(scope, task["workspace"])
    deliverables = {d["id"]: d for d in scope["deliverables"]}
    checks = []
    for c in task.get("checks", []):
        checks.append(planmod.BUILTIN_TASK_CHECKS.get(c) or f"`{plan['checks'][c]['cmd']}`")
    sources = []
    for s in task.get("sources", []):
        name, _, rel = str(s).partition(":")
        sources.append(str(Path(wss[name]["path"]) / rel) if name in wss else s)
    return {
        "serves": "; ".join(f"{d} — {deliverables[d]['what']}" for d in task["serves"] if d in deliverables),
        "scope_md": wf.root / "scope.md",
        "write_paths": [str(ws / p) for p in task["paths"]],
        "readonly": [w["path"] for w in wss.values() if w["mode"] == "read"],
        "sources": sources or [str(ws)],
        "checks": checks,
        "tests_paths": [str(ws / p) for p in task.get("tests_paths", task["paths"])],
    }


def cmd_dispatch(wf: Workflow, tid: str) -> str:
    with wf.locked():
        state = wf.load()
        if tid.startswith("R"):
            return _dispatch_recon(wf, state, tid)
        if tid == "FINAL":
            return _dispatch_final_review(wf, state)
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
        ctx = _context(wf, task, scope, plan)
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
            cwd = _ws(scope, spec["cwd"]) if spec.get("cwd") else ws
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


def cmd_record(wf: Workflow, tid: str, agent_id: Optional[str]) -> str:
    with wf.locked():
        state = wf.load()
        if tid.startswith("R"):
            return _record_recon(wf, state, tid)
        if tid == "FINAL":
            return _record_final_review(wf, state, agent_id)
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
        errs = _validate_result(data, tid, step)
        if errs:
            raise TPError(*[f"{res_path}: {e}" for e in errs],
                          "Ask the same agent to fix the file (SendMessage), then record again.")
        for item in data.get("noticed", []):
            wf.noticed(tid, str(item))
        minutes = minutes_since(fl["since"])
        if data["status"] != "done":
            del state["in_flight"][tid]
            ts["status"] = "blocked"
            asks = data.get("questions") or [data["summary"]]
            ts["blocked"] = {"kind": "input", "summary": f"{tid} {data['status']}: " + " | ".join(asks), "step": step,
                             "snap": fl["snap"]}
            wf.save(state)
            wf.event("record", id=tid, step=step, status=data["status"], minutes=round(minutes, 1))
            return "\n".join([f"{tid} {data['status']} — answer from scope.md / plan.json / decisions.md if they "
                              "settle it; otherwise ask the human. Then `tp resolve --task "
                              f"{tid} --action answer --answer \"...\"`:"] + [f"  - {q}" for q in asks])

        findings: List[str] = []
        msgs: List[str] = []
        ws = _ws(scope, task["workspace"])
        changed = snapshot.diff(snapshot.load(Path(fl["snap"])), snapshot.take(ws, [wf.root]))
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
    changed = snapshot.diff(snapshot.load(Path(fl["snap"])), snapshot.take(ws, [wf.root]))
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
    if findings:
        out = _fail(wf, ts, tid, findings, fixing=_authoring_step(task, scope))
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
        wf.event("accept", id=tid, minutes=round(minutes_since(ts["started"]), 1))
        return f"accepted {tid} ({minutes_since(ts['started']):.0f} min, {ts['round']} fix rounds). Next: `tp next`."


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


def cmd_resolve(wf: Workflow, tid: Optional[str], action: str, answer: str) -> str:
    with wf.locked():
        state = wf.load()
        wf.decision(f"resolve {tid or 'workflow'} {action}", answer)
        if not tid:
            blocked = state.pop("blocked", None)
            if blocked is None:
                raise TPError("Nothing is blocked at workflow level; pass --task for a task.")
            if action == "accept":
                state["final_review_done"] = True
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
            state["final_review_done"] = False
            state.pop("final_failed", None)
            wf.save(state)
            return f"{tid} reopened for a fix round. `tp next`."
        if ts["status"] != "blocked":
            raise TPError(f"{tid} is not blocked (status {ts['status']}).")
        kind = ts["blocked"]["kind"]
        if action == "skip":
            ts.update(status="skipped", blocked=None, note=answer)
        elif action == "retry" and kind == "rounds":
            ts["extra_rounds"] += 1
            ts.update(status="needs_fix", blocked=None)
        elif action == "answer" and kind == "input":
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
            target = f"SendMessage(to={json.dumps(agent_id)}, message={json.dumps(msg)})" if agent_id else \
                f"(no agent id recorded — resend the brief with the answer) {json.dumps(msg)}"
            return f"{tid} back in flight.\nsend: {target}\nthen: tp record {tid}"
        elif action == "answer" and kind == "exception":
            ts.update(status=ts["blocked"]["prior"], blocked=None)
        else:
            raise TPError(f"action {action!r} does not apply to a {kind} block; use "
                          + {"rounds": "retry or skip", "input": "answer or skip",
                             "exception": "answer or skip"}[kind] + ".")
        wf.save(state)
        return f"{tid} resolved ({action}). `tp next`."


# --- final ----------------------------------------------------------------------------------

def _dispatch_final_review(wf: Workflow, state: Dict[str, Any]) -> str:
    plan, scope, tasks = _loaded(wf, state)
    if not _final_review_due(state, scope) or not all(t["status"] in DONE_STATES for t in state["tasks"].values()):
        raise TPError("The final review runs once every task is accepted, and only if the scope asks for it.")
    _slots(state)
    run = wf.run_dir("FINAL")
    run.mkdir(parents=True, exist_ok=True)
    n = state.get("final_reviews", 0) + 1
    brief, result = run / f"brief-review-{n}.md", run / f"review-{n}.json"
    pseudo = {"id": "FINAL", "title": plan["title"], "brief": "Review the whole package as one set: consistency "
              "between deliverables, gaps against the scope's deliverables, and anything that would mislead a reader.",
              "acceptance": [f"{d['id']}: {d['what']}" for d in scope["deliverables"]]}
    paths = []
    for t in tasks.values():
        paths += [str(_ws(scope, t["workspace"]) / p) for p in t["paths"]]
    ctx = {"write_paths": paths, "sources": [w["path"] for w in scopemod.workspaces(scope).values() if w["mode"] == "read"]}
    if result.exists():
        result.unlink()
    brief.write_text(briefs.review(pseudo, n, ctx, result))
    agent = scopemod.participants(scope, "reviewer")[0]
    state["in_flight"]["FINAL"] = {"step": "review", "since": now_iso(), "agent": agent, "concurrent": []}
    wf.save(state)
    call = briefs.dispatch_line(agent, "final review", briefs.prompt(brief, result), None, None)
    return f"DISPATCH FINAL · review · {agent}\nbrief: {brief}\nsend: {call}\nthen: tp record FINAL"


def _record_final_review(wf: Workflow, state: Dict[str, Any], agent_id: Optional[str]) -> str:
    if "FINAL" not in state["in_flight"]:
        raise TPError("The final review is not in flight.")
    n = state.get("final_reviews", 0) + 1
    path = wf.run_dir("FINAL") / f"review-{n}.json"
    data = load_json(path, "the final review")
    errs = _validate_review(data, "FINAL")
    if errs:
        raise TPError(*[f"{path}: {e}" for e in errs])
    del state["in_flight"]["FINAL"]
    state["final_reviews"] = n
    blocking = [f for f in data["findings"] if f["blocking"]]
    if blocking:
        state["blocked"] = {"kind": "final_review", "summary": f"the final review found {len(blocking)} blocking "
                            f"problems ({path}) — the human decides: reopen tasks (`tp resolve --task T## --action "
                            "reopen`) or accept as is (`tp resolve --action accept`)"}
        out = "FINAL review: changes needed —\n" + "\n".join(f"  - {f['id']} at {f['where']}: {f['issue']}" for f in blocking)
    else:
        state["final_review_done"] = True
        out = f"FINAL review passed ({len(data['findings'])} non-blocking notes). Next: `tp final`."
    wf.save(state)
    return out


def cmd_final(wf: Workflow) -> str:
    with wf.locked():
        state = wf.load()
        if state["phase"] != "EXECUTING":
            raise TPError(f"final runs while EXECUTING; the workflow is {state['phase']}.")
        plan, scope, tasks = _loaded(wf, state)
        open_ = [f"{t} ({ts['status']})" for t, ts in state["tasks"].items() if ts["status"] not in DONE_STATES]
        if open_ or state["in_flight"]:
            raise TPError(f"open tasks: {', '.join(open_ or list(state['in_flight']))}.")
        if _final_review_due(state, scope):
            raise TPError("the scope asks for a final review first: `tp dispatch FINAL`.")
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
    for tid, ts in state["tasks"].items():
        mins = minutes_since(ts["started"], ts.get("accepted")) if ts["started"] else 0
        rows.append(f"| {tid} | {tasks[tid]['title'] if tid in tasks else '?'} | {ts['status']} | {mins:.0f} | "
                    f"{tasks.get(tid, {}).get('estimate_min', '?')} | {ts['round']} | {ts['reviews']} |")
    return rows


def _report_md(wf: Workflow, state: Dict[str, Any], plan: Dict[str, Any], scope: Dict[str, Any],
               results: List[str]) -> str:
    tasks = {t["id"]: t for t in plan["tasks"]}
    planning = minutes_since(state["created"], state.get("approved"))
    execution = minutes_since(state.get("approved"), state.get("done"))
    budget = scope.get("budget_minutes")
    out = [f"# Report — {plan['title']}", "",
           f"All {len(tasks)} tasks finished: {sum(ts['status'] == 'accepted' for ts in state['tasks'].values())} "
           f"accepted, {sum(ts['status'] == 'skipped' for ts in state['tasks'].values())} skipped by the human. "
           f"Planning took {planning:.0f} min and execution {execution:.0f} min"
           + (f", against a budget of {budget} min." if budget else "."), "", "## Deliverables", ""]
    for d in scope["deliverables"]:
        served = [t for t in tasks.values() if d["id"] in t["serves"]]
        out.append(f"- {d['id']} — {d['what']}: " + ", ".join(
            f"{t['id']} (`{', '.join(t['paths'])}`)" for t in served))
    out += ["", "## Tasks", ""] + _task_rows(wf, state, tasks)
    notes = [f"- {tid}: {ts['note']}" for tid, ts in state["tasks"].items() if ts.get("note")]
    if notes:
        out += ["", "## Manager fact-check notes", ""] + notes
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
    out = [f"{state['title']} — {_headline(state)}", f"dir: {wf.root}"]
    by: Dict[str, List[str]] = {}
    for tid, ts in state["tasks"].items():
        by.setdefault(ts["status"], []).append(tid)
    for status, ids in by.items():
        out.append(f"  {status}: {', '.join(ids[:20])}" + (" …" if len(ids) > 20 else ""))
    if state.get("blocked"):
        out.append(f"BLOCKED: {state['blocked']['summary']}")
    for rid, r in state.get("recon", {}).items():
        out.append(f"  recon {rid}: {r['status']} ({r['agent']})")
    out.append(cmd_next(wf, False).splitlines()[-1])
    return "\n".join(out[:24])


# --- recon ----------------------------------------------------------------------------------

def cmd_recon_add(wf: Workflow, rid: str, agent: str, questions_file: Path, done_when: str) -> str:
    with wf.locked():
        state = wf.load()
        if state["phase"] != "PLANNING":
            raise TPError(f"Recon happens only while PLANNING; the workflow is {state['phase']}.")
        scope = scopemod.load_scope(wf)
        errs = []
        if not re.fullmatch(r"R\d+", rid) or rid in state["recon"]:
            errs.append(f"recon id {rid!r} must be new and look like R1.")
        if agent not in scopemod.participants(scope, "recon"):
            errs.append(f"{agent} is not a confirmed recon participant in scope.json — ask the human first.")
        questions = [q.strip() for q in Path(questions_file).read_text().splitlines() if q.strip()]
        if not questions:
            errs.append("no questions.")
        if len(questions) > limit("max_recon_questions"):
            errs.append(f"{len(questions)} questions; at most {limit('max_recon_questions')} per recon item — "
                        "breadth comes from the survey, not bigger items.")
        for i, q in enumerate(questions, 1):
            if words(q) > 40:
                errs.append(f"question {i} is {words(q)} words; keep it under 40.")
            for pat in BANNED_RECON:
                m = pat.search(q)
                if m:
                    errs.append(f"question {i} asks for content, not a map: \"{m.group(0)}\" — planning recon "
                                "maps the work; the task that writes the content researches it.")
        if len(state["recon"]) >= limit("max_recon_items"):
            errs.append(f"already {len(state['recon'])} recon items; the limit is {limit('max_recon_items')}.")
        if errs:
            raise TPError(*errs)
        state["recon"][rid] = {"agent": agent, "questions": questions, "done_when": done_when, "status": "pending"}
        wf.save(state)
        wf.event("recon_add", id=rid, agent=agent)
        return f"recon {rid} added. `tp dispatch {rid}` when ready (max {limit('max_in_flight')} agents at once)."


def _dispatch_recon(wf: Workflow, state: Dict[str, Any], rid: str) -> str:
    if state["phase"] != "PLANNING":
        raise TPError(f"Recon happens only while PLANNING; the workflow is {state['phase']}.")
    item = state["recon"].get(rid)
    if item is None or item["status"] != "pending":
        raise TPError(f"{rid} is not a pending recon item.")
    _slots(state)
    rdir = wf.root / "recon"
    rdir.mkdir(exist_ok=True)
    brief, result = rdir / f"{rid}.brief.md", rdir / f"{rid}.json"
    if result.exists():
        result.unlink()
    surveys = sorted((wf.root / "survey").glob("*.json")) if (wf.root / "survey").exists() else []
    brief.write_text(briefs.recon(rid, item, wf.root / "scope.md", surveys, result))
    item["status"] = "in_flight"
    state["in_flight"][rid] = {"step": "recon", "since": now_iso(), "agent": item["agent"], "concurrent": []}
    wf.save(state)
    wf.event("dispatch", id=rid, step="recon", agent=item["agent"])
    call = briefs.dispatch_line(item["agent"], f"{rid} recon", briefs.prompt(brief, result), None, None)
    return (f"DISPATCH {rid} · recon · {item['agent']} (time box {limit('recon_minutes')} min)\nbrief: {brief}\n"
            f"send: {call}\nthen: tp record {rid}")


def _record_recon(wf: Workflow, state: Dict[str, Any], rid: str) -> str:
    item = state["recon"].get(rid)
    if item is None or rid not in state["in_flight"]:
        raise TPError(f"{rid} is not in flight.")
    path = wf.root / "recon" / f"{rid}.json"
    if not path.exists():
        raise TPError(f"{path} is missing — the agent must write it.")
    size = path.stat().st_size
    if size > limit("recon_output_bytes"):
        raise TPError(f"{path.name} is {size} bytes; the cap is {limit('recon_output_bytes')} — ask the same agent "
                      "to cut it to the map (SendMessage), then record again.")
    data = load_json(path, "recon output")
    answers = data.get("answers") if isinstance(data, dict) else None
    if not isinstance(answers, list) or not answers or not all(isinstance(a, dict) and a.get("a") for a in answers):
        raise TPError(f"{path}: needs `answers`: a list of {{q, a, evidence}} objects.")
    minutes = minutes_since(state["in_flight"][rid]["since"])
    del state["in_flight"][rid]
    item.update(status="done", minutes=round(minutes, 1))
    wf.save(state)
    wf.event("record", id=rid, step="recon", minutes=round(minutes, 1))
    over = f" — over its {limit('recon_minutes')}-min box" if minutes > limit("recon_minutes") else ""
    return (f"{rid} done in {minutes:.0f} min{over}: {len(answers)} answers, {len(data.get('areas', []))} areas, "
            f"{len(data.get('unknowns', []))} unknowns. Read {path} and fact-check one answer before you rely on it.")
