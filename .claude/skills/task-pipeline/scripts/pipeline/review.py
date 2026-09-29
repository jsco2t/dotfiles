"""End-of-pipeline review: once every task is accepted, one session per review batch and
reviewer runs over the completed work in bulk. The script routes each blocking finding to the
task that owns its path, the manager triages (accept, dismiss with a reason, or assign), the
owning authors fix, and each reviewer runs one verification session scoped to its findings.
Anything still blocking after that goes to the human."""
from __future__ import annotations

import json
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import briefs, snapshot
from . import plan as planmod
from . import run
from . import scope as scopemod
from .common import TPError, Workflow, limit, load_json, minutes_since, now_iso

CITE_TAIL = re.compile(r":\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*$")


def write_baseline(scope: Dict[str, Any]) -> Dict[str, str]:
    """HEAD of each write workspace under git, recorded at approval: what code review diffs against."""
    out = {}
    for name, w in scopemod.workspaces(scope).items():
        if w["mode"] != "write":
            continue
        head = subprocess.run(["git", "-C", w["path"], "rev-parse", "HEAD"], capture_output=True, text=True)
        if head.returncode == 0:
            out[name] = head.stdout.strip()
    return out


def new_reviews(plan: Dict[str, Any], scope: Dict[str, Any], existing: Dict[str, Any]) -> Dict[str, Any]:
    sessions = {}
    for b in planmod.review_batches(plan, scope):
        for reviewer in scopemod.final_reviewers(scope):
            sid = f"{b['id']}/{reviewer}"
            sessions[sid] = existing.get(sid) or {"batch": b["id"], "reviewer": reviewer, "status": "pending",
                                                  "round": 0, "agent_id": None, "findings": [], "accepted": [],
                                                  "dismissed": {}, "fix_tasks": [], "extra_rounds": 0}
    return sessions


def sessions(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return state.get("reviews", {})


def open_sessions(state: Dict[str, Any]) -> List[str]:
    return [sid for sid, s in sessions(state).items() if s["status"] != "done"]


def _batch_tasks(plan: Dict[str, Any], scope: Dict[str, Any], bid: str) -> List[Dict[str, Any]]:
    tasks = {t["id"]: t for t in plan["tasks"]}
    for b in planmod.review_batches(plan, scope):
        if b["id"] == bid:
            return [tasks[t] for t in b["tasks"]]
    raise TPError(f"{bid} is not a review batch in the plan.")


def _all_accepted(state: Dict[str, Any], ids: Optional[List[str]] = None) -> bool:
    tasks = state["tasks"]
    ids = list(tasks) if ids is None else ids
    return all(tasks[t]["status"] in run.DONE_STATES for t in ids) and not any(t in state["in_flight"] for t in ids)


def actions(state: Dict[str, Any], free: int) -> List[Dict[str, Any]]:
    acts: List[Dict[str, Any]] = []
    everything = _all_accepted(state)
    for sid, s in sessions(state).items():
        if s["status"] == "blocked":
            acts.append({"action": "human", "id": sid, "why": s.get("summary", f"{sid} is blocked")})
        elif s["status"] == "needs_triage":
            acts.append({"action": "triage", "id": sid})
    for sid, s in sessions(state).items():
        ready = (s["status"] == "pending" and everything) or \
                (s["status"] == "waiting_fixes" and _all_accepted(state, s["fix_tasks"]))
        if ready and free > 0:
            acts.append({"action": "review", "id": sid, "step": "review" if s["round"] == 0 else "verify",
                         "agent": s["reviewer"], "agent_id": s["agent_id"] if s["round"] else None, "model": None})
            free -= 1
    return acts


def _changes(wf: Workflow, state: Dict[str, Any], scope: Dict[str, Any], tasks: List[Dict[str, Any]],
             bid: str) -> Dict[str, Any]:
    files: List[str] = []
    abs_paths: Dict[str, List[str]] = {}
    pathspecs: Dict[str, List[str]] = {}
    for t in tasks:
        ws = run._ws(scope, t["workspace"])
        found = [str(p.relative_to(ws)) for p in run._expand(ws, t["paths"])]
        files += [f"{t['workspace']}:{r}" for r in found]
        abs_paths[t["id"]] = [str(ws / r) for r in found] or [str(ws / p) for p in t["paths"]]
        pathspecs.setdefault(t["workspace"], []).extend(t["paths"])
    diff, untracked = {}, {}
    for name, specs in pathspecs.items():
        base = state.get("write_baseline", {}).get(name)
        if not base:
            continue
        root = run._ws(scope, name)
        quoted = " ".join(shlex.quote(p) for p in sorted(set(specs)))
        diff[name] = f"git -C {shlex.quote(str(root))} diff {base} -- {quoted}"
        listed = subprocess.run(["git", "-C", str(root), "ls-files", "--others", "--exclude-standard", "--",
                                 *sorted(set(specs))], capture_output=True, text=True)
        untracked[name] = [ln for ln in listed.stdout.splitlines() if ln]
    data = {"batch": bid, "files": sorted(set(files)), "diff": diff, "untracked": untracked}
    out = wf.run_dir(bid) / "changes.json"
    out.write_text(json.dumps(data, indent=1))
    return {"changes": str(out), "paths": abs_paths}


def dispatch(wf: Workflow, state: Dict[str, Any], sid: str) -> str:
    s = sessions(state).get(sid)
    if s is None:
        raise TPError(f"{sid} is not a review session in the approved plan.")
    plan, scope, _ = run._loaded(wf, state)
    if s["status"] == "pending":
        if not _all_accepted(state):
            open_ = [t for t, ts in state["tasks"].items() if ts["status"] not in run.DONE_STATES]
            raise TPError(f"Review starts once every task is accepted; still open: {', '.join(open_)}.")
    elif s["status"] == "waiting_fixes":
        if not _all_accepted(state, s["fix_tasks"]):
            raise TPError(f"{sid} verifies once {', '.join(s['fix_tasks'])} are accepted again.")
    else:
        raise TPError(f"{sid} is {s['status']}; there is nothing to dispatch.")
    run._slots(state)
    n = s["round"] + 1
    tasks = _batch_tasks(plan, scope, s["batch"])
    rdir = wf.run_dir(s["batch"])
    rdir.mkdir(parents=True, exist_ok=True)
    ctx = _changes(wf, state, scope, tasks, s["batch"])
    ctx["sources"] = [w["path"] for w in scopemod.workspaces(scope).values() if w["mode"] == "read"] or ["the deliverables' own sources"]
    brief, result = rdir / f"brief-{s['reviewer']}-{n}.md", rdir / f"{s['reviewer']}-{n}.json"
    if result.exists():
        result.unlink()
    agent_id = s["agent_id"] if n > 1 else None
    if n == 1:
        brief.write_text(briefs.batch_review(s["batch"], s["reviewer"], tasks, ctx, result))
    else:
        accepted = [f for f in s["findings"] if f["id"] in s["accepted"]]
        brief.write_text(briefs.verify(s["batch"], s["reviewer"], accepted, ctx, result, same_agent=bool(agent_id)))
    snaps = {}
    for name in sorted({t["workspace"] for t in tasks}):
        snap = rdir / f"snap-{s['reviewer']}-{n}-{name}.json"
        snapshot.save(snap, snapshot.take(run._ws(scope, name), [wf.root]))
        snaps[name] = str(snap)
    for other in state["in_flight"].values():
        other.setdefault("concurrent", []).append(sid)
    state["in_flight"][sid] = {"step": "review", "since": now_iso(), "agent": s["reviewer"], "snaps": snaps,
                               "concurrent": list(state["in_flight"]), "from": s["status"]}
    s.update(status="in_flight", round=n)
    wf.save(state)
    wf.event("dispatch", id=sid, step="review" if n == 1 else "verify", agent=s["reviewer"], round=n)
    call = briefs.dispatch_line(s["reviewer"], f"{sid} {'review' if n == 1 else 'verify'}",
                                briefs.prompt(brief, result), agent_id, None)
    return (f"DISPATCH {sid} · {'review' if n == 1 else 'verification'} · {s['reviewer']}\nbrief: {brief}\n"
            f"send: {call}\nthen, when it replies: tp record {sid} --agent-id <its agent id>")


def _validate(data: Any) -> List[str]:
    if not isinstance(data, dict):
        return ["the review must be a JSON object."]
    errs = []
    if data.get("verdict") not in ("pass", "changes"):
        errs.append("verdict must be pass or changes.")
    findings = data.get("findings", [])
    if not isinstance(findings, list):
        return errs + ["findings must be a list."]
    ids = set()
    for f in findings:
        if not isinstance(f, dict):
            errs.append("each finding must be an object.")
            continue
        for key in ("id", "state", "where", "issue"):
            if not f.get(key):
                errs.append(f"finding {f.get('id', '?')} needs `{key}`.")
        if not isinstance(f.get("blocking"), bool):
            errs.append(f"finding {f.get('id', '?')} needs `blocking`: true or false.")
        if f.get("id") in ids:
            errs.append(f"finding id {f['id']} is used twice.")
        ids.add(f.get("id"))
    blocking = [f.get("id") for f in findings if isinstance(f, dict) and f.get("blocking") is True]
    if blocking and data.get("verdict") == "pass":
        errs.append(f"verdict 'pass' contradicts blocking finding {', '.join(map(str, blocking))}.")
    if not blocking and data.get("verdict") == "changes":
        errs.append("verdict 'changes' needs at least one blocking finding.")
    return errs


def _owner(f: Dict[str, Any], tasks: List[Dict[str, Any]], scope: Dict[str, Any]) -> Optional[str]:
    """The task whose paths contain the file a finding points at; the reviewer's label only as a fallback."""
    where = CITE_TAIL.sub("", str(f.get("where", "")).strip().strip("`"))
    wss = scopemod.workspaces(scope)
    ws_name = None
    if ":" in where and where.split(":", 1)[0] in wss:
        ws_name, where = where.split(":", 1)
    for t in tasks:
        root = str(run._ws(scope, t["workspace"]))
        rel = where[len(root) + 1:] if where.startswith(root + "/") else where.lstrip("./")
        if (ws_name in (None, t["workspace"])) and snapshot.matches(rel, t["paths"]):
            return t["id"]
    label = f.get("task")
    return label if label in {t["id"] for t in tasks} else None


def record(wf: Workflow, state: Dict[str, Any], sid: str, agent_id: Optional[str]) -> str:
    s = sessions(state).get(sid)
    fl = state["in_flight"].get(sid)
    if s is None or fl is None:
        raise TPError(f"{sid} is not in flight.")
    plan, scope, _ = run._loaded(wf, state)
    n = s["round"]
    path = wf.run_dir(s["batch"]) / f"{s['reviewer']}-{n}.json"
    data = load_json(path, "the review")
    errs = _validate(data)
    if errs:
        raise TPError(*[f"{path}: {e}" for e in errs], "Ask the reviewer to fix the file, then record again.")
    if agent_id:
        s["agent_id"] = agent_id
    for item in data.get("noticed", []):
        wf.noticed(f"{sid} review", str(item))
    tasks = _batch_tasks(plan, scope, s["batch"])
    edits = []
    for name, snap in fl.get("snaps", {}).items():
        changed = snapshot.diff(snapshot.load(Path(snap)), snapshot.take(run._ws(scope, name), [wf.root]))
        edits += [f"{name}:{c}" for c in changed]
    minutes = minutes_since(fl["since"])
    del state["in_flight"][sid]
    for f in data["findings"]:
        f["task"] = _owner(f, tasks, scope) if f["blocking"] else f.get("task")
    s["findings"] = data["findings"]
    blocking = [f for f in data["findings"] if f["blocking"]]
    lines = [f"  {f['id']} → {f['task'] or '? (no task owns this path: --assign or --dismiss)'} ({f['state']}) "
             f"at {f['where']}: {f['issue']}" for f in blocking]
    if edits:
        s.update(status="blocked", summary=f"the reviewer of {sid} edited {', '.join(edits[:6])} — inspect and revert")
        out = f"BLOCKED {sid}: the reviewer edited files ({', '.join(edits[:6])}). Reviews never edit; ask the human."
    elif not blocking:
        s["status"] = "done"
        out = f"{sid} {'passed' if n == 1 else 'verified'} ({len(data['findings'])} non-blocking notes in {path.name})."
    elif n == 1 or n < limit("max_review_rounds") + s.get("extra_rounds", 0):
        s["status"] = "needs_triage"
        out = "\n".join([f"{sid} review {n}: {len(blocking)} blocking — triage each (tp triage {sid} ...):"] + lines)
    else:
        s.update(status="blocked", summary=f"{sid} still has {len(blocking)} blocking findings after verification")
        out = "\n".join([f"BLOCKED {sid}: still blocking after verification — the human decides "
                         f"(`tp resolve --review {sid} --action accept|retry`):"] + lines)
    wf.save(state)
    wf.event("record", id=sid, step="review" if n == 1 else "verify", status=s["status"], minutes=round(minutes, 1),
             blocking=len(blocking))
    return out


def cmd_triage(wf: Workflow, sid: str, accept_all: bool, dismiss: List[str], reason: Optional[str],
               assign: List[str]) -> str:
    with wf.locked():
        state = wf.load()
        s = sessions(state).get(sid)
        if s is None or s["status"] != "needs_triage":
            raise TPError(f"{sid} is not awaiting triage.")
        if not (accept_all or dismiss or assign):
            raise TPError("Say what you decided: --accept-all, and/or --dismiss F# --reason \"...\", and/or --assign F#=T##.")
        if dismiss and not reason:
            raise TPError("--dismiss needs --reason: why the finding is not a real problem.")
        plan, scope, _ = run._loaded(wf, state)
        batch_ids = {t["id"] for t in _batch_tasks(plan, scope, s["batch"])}
        blocking = {f["id"]: f for f in s["findings"] if f["blocking"]}
        errs = [f"{fid} is not a blocking finding of {sid}." for fid in dismiss if fid not in blocking]
        for spec in assign:
            fid, _, tid = spec.partition("=")
            if fid not in blocking or tid not in batch_ids:
                errs.append(f"--assign {spec}: need a blocking finding and a task in {s['batch']}.")
            else:
                blocking[fid]["task"] = tid
        kept = [f for fid, f in blocking.items() if fid not in dismiss]
        errs += [f"{f['id']} matches no task path in {s['batch']} — `--assign {f['id']}=T##` or "
                 f"`--dismiss {f['id']} --reason \"...\"`." for f in kept if not f.get("task")]
        if errs:
            raise TPError(*errs)
        for fid in dismiss:
            s["dismissed"][fid] = reason
        if dismiss:
            wf.decision(f"triage {sid} dismiss {', '.join(dismiss)}", str(reason), who="manager")
        by_task: Dict[str, List[str]] = {}
        result_name = f"{s['reviewer']}-{s['round']}.json"
        for f in kept:
            by_task.setdefault(f["task"], []).append(
                f"{result_name} {f['id']} ({f['state']}) at {f['where']}: {f['issue']}"
                + (f" Fix: {f['fix']}" if f.get("fix") else ""))
        out = []
        for tid, lines in sorted(by_task.items()):
            ts = state["tasks"][tid]
            ts["extra_rounds"] = ts.get("extra_rounds", 0) + 1   # a review fix is not one of the task's own rounds
            out.append(run._fail(wf, ts, tid, lines, fixing=run._authoring_step(plan_task(plan, tid), scope)))
        s["accepted"] = sorted(set(s["accepted"]) | {f["id"] for f in kept})
        s["fix_tasks"] = sorted(by_task)
        s["status"] = "waiting_fixes" if kept else "done"
        wf.save(state)
        wf.event("triage", id=sid, accepted=len(kept), dismissed=len(dismiss))
        head = (f"{sid}: {len(kept)} accepted → {', '.join(sorted(by_task))}; {len(dismiss)} dismissed."
                if kept else f"{sid}: every blocking finding dismissed — session done.")
        return "\n".join([head] + out)


def plan_task(plan: Dict[str, Any], tid: str) -> Dict[str, Any]:
    return next(t for t in plan["tasks"] if t["id"] == tid)


def resolve(wf: Workflow, state: Dict[str, Any], sid: str, action: str, answer: str) -> str:
    s = sessions(state).get(sid)
    if s is None or s["status"] != "blocked":
        raise TPError(f"{sid} is not blocked.")
    if action == "accept":
        s.update(status="done", accepted_as_is=answer)
    elif action == "retry":
        s["extra_rounds"] = s.get("extra_rounds", 0) + 1
        s["status"] = "needs_triage"
    else:
        raise TPError("a blocked review session takes --action accept (ship as is) or retry (one more fix and "
                      "verification round).")
    wf.save(state)
    wf.decision(f"resolve {sid} {action}", answer)
    return f"{sid} → {s['status']}. `tp next`."


def show(state: Dict[str, Any], sid: str, part: Optional[str]) -> str:
    s = sessions(state).get(sid)
    if s is None:
        raise TPError(f"{sid} is not a review session.")
    findings = s["findings"] if part == "findings" else [f for f in s["findings"] if f["blocking"]]
    if part in ("findings", "blocking"):
        return "\n".join(f"{f['id']} → {f.get('task') or '?'} ({f['state']}{', blocking' if f['blocking'] else ''}"
                         f"{', confidence ' + str(f['confidence']) if f.get('confidence') is not None else ''}) "
                         f"at {f['where']}: {f['issue']}" for f in findings) or "none."
    return (f"{sid}: {s['status']}, round {s['round']}, {sum(f['blocking'] for f in s['findings'])} blocking of "
            f"{len(s['findings'])} findings, {len(s['accepted'])} accepted, {len(s['dismissed'])} dismissed — "
            "parts: blocking, findings")


def report_lines(state: Dict[str, Any]) -> List[str]:
    ss = sessions(state)
    if not ss:
        return []
    out = [f"{len(ss)} review session{'s' if len(ss) != 1 else ''}, after every task was accepted:", ""]
    for sid, s in ss.items():
        out.append(f"- {sid}: {s['status']} after {s['round']} round{'s' if s['round'] != 1 else ''}; "
                   f"{len(s['accepted'])} findings fixed ({', '.join(s['fix_tasks']) or 'none'}), "
                   f"{len(s['dismissed'])} dismissed by the manager"
                   + (f"; accepted as is by the human: {s['accepted_as_is']}" if s.get("accepted_as_is") else ""))
    return out
