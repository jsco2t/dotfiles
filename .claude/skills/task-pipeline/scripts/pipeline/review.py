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
from typing import Any, Dict, List, Optional, Tuple

from . import briefs, snapshot
from . import plan as planmod
from . import run
from . import scope as scopemod
from .common import SKILL, TPError, Workflow, limit, load_json, minutes_since, now_iso

AGENTS = SKILL.parents[1] / "agents"
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
    """The review sessions the plan implies (planmod.review_sessions). A session already started
    keeps running as it is, even when the plan would now shape it differently. A run approved
    before packed, batch-scoped sessions keeps its shape (one session per batch and reviewer)."""
    if any("tasks" not in s for s in existing.values()):
        legacy = dict(existing)
        for b in planmod.review_batches(plan, scope):
            for reviewer in scopemod.final_reviewers(scope):
                legacy.setdefault(f"{b['id']}/{reviewer}", {
                    "batch": b["id"], "reviewer": reviewer, "status": "pending", "round": 0, "agent_id": None,
                    "findings": [], "accepted": [], "dismissed": {}, "fix_tasks": [], "extra_rounds": 0})
        return legacy
    sessions = {}
    for spec in planmod.review_sessions(plan, scope):
        cur = existing.get(spec["sid"])
        if cur is None:
            cur = {"batch": spec["batch"], "reviewer": spec["reviewer"], "status": "pending", "round": 0,
                   "agent_id": None, "findings": [], "accepted": [], "dismissed": {}, "fix_tasks": [],
                   "extra_rounds": 0}
        if cur["status"] == "pending":
            cur.update(lenses=spec["lenses"], tasks=spec["tasks"], code=spec["code"])
        sessions[spec["sid"]] = cur
    for sid, s in existing.items():
        if sid not in sessions and s["status"] != "pending":
            sessions[sid] = s
    return sessions


def integration_ids(plan: Dict[str, Any], scope: Dict[str, Any]) -> List[str]:
    return [t["id"] for t in plan["tasks"] if planmod.is_integration(t, scope)]


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


def _ready(state: Dict[str, Any], s: Dict[str, Any]) -> bool:
    """Whether a session can be dispatched now. Code review starts once its own tasks are accepted;
    document review waits for every non-integration task and every code review, so the documents
    it judges already describe the final code. Sessions from before kind-aware review wait for
    every task, as they always did."""
    if s["status"] == "waiting_fixes":
        return _all_accepted(state, s["fix_tasks"])
    if s["status"] != "pending":
        return False
    if "tasks" not in s:
        return _all_accepted(state)
    if not _all_accepted(state, s["tasks"]):
        return False
    if s.get("code"):
        return True
    work = [t for t in state["tasks"] if t not in state.get("integration", [])]
    return _all_accepted(state, work) and all(o["status"] == "done" for o in sessions(state).values()
                                              if o.get("code"))


def actions(state: Dict[str, Any], free: int) -> List[Dict[str, Any]]:
    acts: List[Dict[str, Any]] = []
    for sid, s in sessions(state).items():
        if s["status"] == "blocked":
            acts.append({"action": "human", "id": sid, "why": s.get("summary", f"{sid} is blocked")})
        elif s["status"] == "needs_triage":
            acts.append({"action": "triage", "id": sid})
    for sid, s in sessions(state).items():
        ready = _ready(state, s)
        if ready and free > 0:
            acts.append({"action": "review", "id": sid, "step": "review" if s["round"] == 0 else "verify",
                         "agent": s["reviewer"], "agent_id": s["agent_id"] if s["round"] else None, "model": None})
            free -= 1
    return acts


DIFF_CAP = 2_000_000


def _changes(wf: Workflow, state: Dict[str, Any], scope: Dict[str, Any], tasks: List[Dict[str, Any]],
             bid: str, label: str, whole_batch: bool = True) -> Dict[str, Any]:
    """The change under review, as two files: a structured one (files, and each workspace's diff
    command) and the diff itself — tracked changes against the approval baseline, then new files
    and `wf:` drafts in full — so no reviewer runs git, and none re-reads what another listed."""
    files: List[str] = []
    abs_paths: Dict[str, List[str]] = {}
    pathspecs: Dict[str, List[str]] = {}
    drafts: List[Path] = []
    for t in tasks:
        ws = run._ws(scope, t["workspace"])
        repo = [p for p in t.get("paths", []) if planmod.wf_rel(p) is None]
        mine = [wf.root / planmod.wf_rel(p) for p in t.get("paths", []) if planmod.wf_rel(p) is not None]
        found = [str(p.relative_to(ws)) for p in run._expand(ws, repo)]
        files += [f"{t['workspace']}:{r}" for r in found] + [f"wf:{f.relative_to(wf.root)}" for f in mine]
        abs_paths[t["id"]] = ([str(ws / r) for r in found] or [str(ws / p) for p in repo]) + [str(f) for f in mine]
        if repo:
            pathspecs.setdefault(t["workspace"], []).extend(repo)
        drafts += [f for f in mine if f.is_file()]
    diff, untracked = {}, {}
    text: List[str] = []
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
        shown = subprocess.run(["git", "-C", str(root), "diff", base, "--", *sorted(set(specs))],
                               capture_output=True, text=True, errors="replace")
        text += [f"=== {name}: {diff[name]}", shown.stdout]
        text += [f"=== {name}: new file {rel}\n" + (root / rel).read_text(errors="replace")
                 for rel in untracked[name] if (root / rel).is_file()]
    text += [f"=== wf: {d.relative_to(wf.root)}\n" + d.read_text(errors="replace") for d in drafts]
    data = {"batch": bid, "files": sorted(set(files)), "diff": diff, "untracked": untracked}
    out = wf.run_dir(bid) / ("changes.json" if whole_batch else f"changes-{label}.json")
    out.write_text(json.dumps(data, indent=1))
    diff_file = wf.run_dir(bid) / f"{label}-change.diff"
    body = "\n".join(text)
    diff_file.write_text(body[:DIFF_CAP] + ("\n[... cut at 2 MB: read the remaining files directly]" if len(body) > DIFF_CAP else ""))
    return {"changes": str(out), "paths": abs_paths, "diff_file": str(diff_file)}


def _lens_texts(lenses: List[str]) -> List[Tuple[str, str]]:
    """Each packed reviewer's own definition (its body, without frontmatter): the lens in full."""
    out = []
    for name in lenses:
        path = AGENTS / f"{name}.md"
        text = path.read_text() if path.exists() else f"Review through the {name} lens."
        if text.startswith("---"):
            text = text.split("---", 2)[2]
        out.append((name, text))
    return out


def session_tasks(plan: Dict[str, Any], scope: Dict[str, Any], s: Dict[str, Any]) -> List[Dict[str, Any]]:
    """What a session reviews: its own tasks, or, for sessions from before kind-aware review, the batch."""
    if s.get("tasks"):
        by_id = {t["id"]: t for t in plan["tasks"]}
        return [by_id[t] for t in s["tasks"] if t in by_id]
    return _batch_tasks(plan, scope, s["batch"])


def dispatch(wf: Workflow, state: Dict[str, Any], sid: str) -> str:
    s = sessions(state).get(sid)
    if s is None:
        raise TPError(f"{sid} is not a review session in the approved plan.")
    plan, scope, _ = run._loaded(wf, state)
    if s["status"] == "pending":
        if not _ready(state, s):
            open_ = [t for t, ts in state["tasks"].items() if ts["status"] not in run.DONE_STATES
                     and t not in state.get("integration", [])]
            raise TPError(f"{sid} is not ready: " + (
                "code review starts once its tasks are accepted" if s.get("code") else
                "document review starts once every task is accepted and the code reviews are done")
                + (f"; still open: {', '.join(open_)}." if open_ else "; a code review is still open."))
    elif s["status"] == "waiting_fixes":
        if not _all_accepted(state, s["fix_tasks"]):
            raise TPError(f"{sid} verifies once {', '.join(s['fix_tasks'])} are accepted again.")
    else:
        raise TPError(f"{sid} is {s['status']}; there is nothing to dispatch.")
    run._slots(state)
    n = s["round"] + 1
    tasks = session_tasks(plan, scope, s)
    batch = _batch_tasks(plan, scope, s["batch"])
    rdir = wf.run_dir(s["batch"])
    rdir.mkdir(parents=True, exist_ok=True)
    ctx = _changes(wf, state, scope, tasks, s["batch"], s["reviewer"],
                   whole_batch=[t["id"] for t in tasks] == [t["id"] for t in batch])
    ctx["sources"] = [w["path"] for w in scopemod.workspaces(scope).values()] or ["the deliverables' own sources"]
    ctx["decisions"] = run.decision_lines(state, [t["id"] for t in tasks])  # so the reviewer does not flag them
    ctx["conventions"] = [str(p) for p in planmod.conventions(plan, scope, wf.root)]
    ctx["lenses"] = _lens_texts(s.get("lenses") or [])
    ctx["full_floor"], ctx["near_floor"] = limit("review_full_finding_floor"), limit("review_near_miss_floor")
    # The logs tp wrote when it ran each task's own tests and checks: reviewers read them instead
    # of re-running the suite. Nothing is run in a workspace on their behalf — snapshots would
    # blame that run's build output on whichever agent is in flight.
    ctx["logs"] = [log for t in (tasks if n == 1 else [x for x in tasks if x["id"] in s["fix_tasks"]])
                   for log in run.task_logs(wf, t["id"])]
    brief, result = rdir / f"brief-{s['reviewer']}-{n}.md", rdir / f"{s['reviewer']}-{n}.json"
    if result.exists():
        result.unlink()
    agent_id = s["agent_id"] if n > 1 else None
    fresh = run.fresh_note(agent_id)
    if fresh:
        agent_id = None
    if n == 1:
        brief.write_text(briefs.batch_review(s["batch"], s["reviewer"], tasks, ctx, result))
    else:
        accepted = [f for f in s["findings"] if f["id"] in s["accepted"]]
        brief.write_text(briefs.verify(s["batch"], s["reviewer"], accepted, ctx, result, same_agent=bool(agent_id)))
    snaps = {}
    for name in sorted({t["workspace"] for t in tasks}):
        snap = rdir / f"snap-{s['reviewer']}-{n}-{name}.json"
        snapshot.save(snap, run._take(wf, run._ws(scope, name)))
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
    lenses = f" ({', '.join(s['lenses'])})" if s.get("lenses") else ""
    return (f"DISPATCH {sid} · {'review' if n == 1 else 'verification'} · {s['reviewer']}{lenses}\n"
            + (f"{fresh}\n" if fresh else "") + f"brief: {brief}\nsend: {call}\n"
            f"then, when it replies: tp record {sid} --agent-id <its agent id>")


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
    if not isinstance(data.get("near_misses", []), list):
        errs.append("near_misses must be a list of one-line strings.")
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


def _outcome(s: Dict[str, Any], sid: str, n: int, blocking: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Where a recorded review goes on its findings alone."""
    if not blocking:
        return {"status": "done"}
    if n == 1 or n < limit("max_review_rounds") + s.get("extra_rounds", 0):
        return {"status": "needs_triage"}
    return {"status": "blocked", "block": "rounds",
            "summary": f"{sid} still has {len(blocking)} blocking findings after verification"}


def _settle(s: Dict[str, Any], outcome: Dict[str, Any]) -> None:
    for key in ("block", "held", "summary"):
        s.pop(key, None)
    s.update(outcome)


HELD_NEXT = {"done": "the session is done", "needs_triage": "its findings go on to triage",
             "blocked": "its findings go to the human, as after any verification"}


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
        if not re.search(r":\s*no issues found\.?$", str(item), re.I):  # a packed lens reporting in
            wf.noticed(f"{sid} review", str(item))
    s["near_misses"] = [str(x) for x in data.get("near_misses", [])]
    tasks = _batch_tasks(plan, scope, s["batch"])  # a finding routes to whichever batch task owns its file
    # Fix rounds dispatched while the reviewer worked write their own paths, as run.py allows for tasks.
    plan_tasks = {t["id"]: t for t in plan["tasks"]}
    allowed: Dict[str, List[str]] = {}
    for other in fl.get("concurrent", []):
        if other in plan_tasks:
            allowed.setdefault(plan_tasks[other]["workspace"], []).extend(plan_tasks[other]["paths"])
    edits = []
    for name, snap in fl.get("snaps", {}).items():
        changed = snapshot.diff(snapshot.load(Path(snap)), run._take(wf, run._ws(scope, name)))
        edits += [f"{name}:{c}" for c in changed if not snapshot.matches(c, allowed.get(name, []))]
    minutes = minutes_since(fl["since"])
    del state["in_flight"][sid]
    for f in data["findings"]:
        f["task"] = _owner(f, tasks, scope) if f["blocking"] else f.get("task")
    s["findings"] = data["findings"]
    blocking = [f for f in data["findings"] if f["blocking"]]
    lines = [f"  {f['id']} → {f['task'] or '? (no task owns this path: --assign or --dismiss)'} ({f['state']}) "
             f"at {f['where']}: {f['issue']}" for f in blocking]
    outcome = _outcome(s, sid, n, blocking)
    if edits:  # the findings are held, not lost, until someone decides about the edits
        _settle(s, {"status": "blocked", "block": "edits", "held": outcome,
                    "summary": f"files changed while {sid} ran and no concurrent task owns them "
                               f"({', '.join(edits[:6])}); {len(blocking)} blocking findings held"})
        out = "\n".join(
            [f"BLOCKED {sid}: files changed while the reviewer worked and no concurrent task owns them "
             f"({', '.join(edits[:6])}). Reviews never edit — inspect those files. {len(blocking)} blocking "
             "findings are held:"] + lines +
            [f"Not the reviewer's edits: `tp resolve --review {sid} --action clear --by <who> --answer \"...\"` "
             f"({HELD_NEXT[outcome['status']]}). `--action accept` ships the batch as is; it is refused while "
             "blocking findings are held, unless --force."])
    else:
        _settle(s, outcome)
        if outcome["status"] == "done":
            out = f"{sid} {'passed' if n == 1 else 'verified'} ({len(data['findings'])} non-blocking notes in {path.name})."
        elif outcome["status"] == "needs_triage":
            out = "\n".join([f"{sid} review {n}: {len(blocking)} blocking — triage each (tp triage {sid} ...):"] + lines)
        else:
            out = "\n".join([f"BLOCKED {sid}: still blocking after verification — the human decides "
                             f"(`tp resolve --review {sid} --action accept|retry --by human --answer \"...\"`):"]
                            + lines)
    wf.save(state)
    wf.event("record", id=sid, step="review" if n == 1 else "verify", status=s["status"], minutes=round(minutes, 1),
             blocking=len(blocking))
    return out


def _dismissals(dismiss: List[str], reasons: List[str]) -> Dict[str, str]:
    """{finding id: reason}. Each --dismiss flag may name several ids (comma-separated); one
    --reason covers them all, or one --reason per --dismiss flag pairs them in order."""
    groups = [[x.strip() for x in str(d).split(",") if x.strip()] for d in dismiss]
    groups = [g for g in groups if g]
    reasons = [r for r in reasons if r and str(r).strip()]
    if not groups:
        return {}
    if not reasons:
        raise TPError("--dismiss needs --reason: why the finding is not a real problem.")
    if len(reasons) == 1:
        return {fid: reasons[0] for g in groups for fid in g}
    if len(reasons) != len(groups):
        raise TPError(f"{len(groups)} --dismiss flags but {len(reasons)} --reason flags: give one reason for all, "
                      "or one per --dismiss, in the same order.")
    return {fid: r for g, r in zip(groups, reasons) for fid in g}


def cmd_triage(wf: Workflow, sid: str, accept_all: bool, dismiss_flags: List[str], reasons: Any,
               assign: List[str]) -> str:
    if isinstance(reasons, str) or reasons is None:  # older callers pass one reason
        reasons = [reasons] if reasons else []
    if isinstance(dismiss_flags, str):
        dismiss_flags = [dismiss_flags]
    with wf.locked():
        state = wf.load()
        s = sessions(state).get(sid)
        if s is None or s["status"] != "needs_triage":
            raise TPError(f"{sid} is not awaiting triage.")
        reason_of = _dismissals(dismiss_flags, list(reasons))
        dismiss = list(reason_of)
        if not (accept_all or dismiss or assign):
            raise TPError("Say what you decided: --accept-all, and/or --dismiss F# --reason \"...\", and/or --assign F#=T##.")
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
            s["dismissed"][fid] = reason_of[fid]
        by_task = _route(wf, state, plan, scope, s, kept)
        s["accepted"] = sorted(set(s["accepted"]) | {f["id"] for f in kept})
        s["fix_tasks"] = sorted(by_task)
        s["status"] = "waiting_fixes" if kept else "done"
        wf.save(state)
        for fid in dismiss:
            wf.decision(f"triage {sid} dismiss {fid}", str(reason_of[fid]), who="manager")
        out = list(by_task.values())
        for tid in sorted(by_task):
            # A blocked hand-back may have parked its work as a patch: the fix round can verify and
            # adopt it instead of starting over.
            patches = sorted(p.name for p in wf.run_dir(tid).glob("*.patch"))
            if patches:
                out.append(f"NOTE {tid}: a parked patch exists from an earlier round ({', '.join(patches[:3])}) — "
                           "say in the fix round's message that it may verify and adopt it.")
        wf.event("triage", id=sid, accepted=len(kept), dismissed=len(dismiss))
        head = (f"{sid}: {len(kept)} accepted → {', '.join(sorted(by_task))}; {len(dismiss)} dismissed."
                if kept else f"{sid}: every blocking finding dismissed — session done.")
        return "\n".join([head] + out)


def plan_task(plan: Dict[str, Any], tid: str) -> Dict[str, Any]:
    return next(t for t in plan["tasks"] if t["id"] == tid)


def _route(wf: Workflow, state: Dict[str, Any], plan: Dict[str, Any], scope: Dict[str, Any], s: Dict[str, Any],
           findings: List[Dict[str, Any]]) -> Dict[str, str]:
    """Send each finding (its `task` already decided) to the owning author: {task id: what happened}."""
    result_name = f"{s['reviewer']}-{s['round']}.json"
    by_task: Dict[str, List[str]] = {}
    for f in findings:
        by_task.setdefault(f["task"], []).append(
            f"{result_name} {f['id']} ({f['state']}) at {f['where']}: {f['issue']}"
            + (f" Fix: {f['fix']}" if f.get("fix") else ""))
    out = {}
    for tid in sorted(by_task):
        task = plan_task(plan, tid)
        routes: Dict[str, List[str]] = {}
        for f, line in zip([f for f in findings if f["task"] == tid], by_task[tid]):
            routes.setdefault(run.fix_route(task, scope, f), []).append(line)
        tests = routes.get("tests-red", []) + routes.get("tests-green", [])
        if tests:
            # Test files are the test author's; a behaviour bug gets its failing test first, and
            # the code author fixes it next, against that test.
            queued = routes.get("tests-red", []) + routes.get("impl", [])
            out[tid] = run.add_fix(wf, state, tid, tests, fixing="tests",
                                   expect="red" if routes.get("tests-red") else "green", queued=queued)
        else:
            step = "impl" if routes.get("impl") else run._authoring_step(task, scope)
            out[tid] = run.add_fix(wf, state, tid, routes.get("impl", []) + routes.get("author", []), fixing=step)
    return out


def _reopen(wf: Workflow, state: Dict[str, Any], sid: str, s: Dict[str, Any], fids: List[str], assign: List[str],
            answer: str, by: Optional[str]) -> str:
    """Send a done session's findings (dismissed, dropped, or non-blocking) back to their authors,
    counted as this session's accepted findings, with its verification round to follow."""
    if s["status"] != "done":
        raise TPError(f"{sid} is {s['status']}; reopen applies to a done session (a blocked one takes clear, "
                      "accept, or retry).")
    if not fids:
        raise TPError("reopen needs --findings F1,F2: the findings to send back to their authors.")
    plan, scope, _ = run._loaded(wf, state)
    tasks = _batch_tasks(plan, scope, s["batch"])
    batch_ids = {t["id"] for t in tasks}
    found = {f["id"]: f for f in s["findings"]}
    errs = [f"{fid} is not a finding of {sid} ({', '.join(found) or 'it has none'})." for fid in fids if fid not in found]
    owners: Dict[str, Optional[str]] = {}
    for spec in assign:
        fid, _, tid = spec.partition("=")
        if fid not in fids or tid not in batch_ids:
            errs.append(f"--assign {spec}: need one of the reopened findings and a task in {s['batch']}.")
        owners[fid] = tid
    for fid in fids:
        if fid in found and fid not in owners:
            label = found[fid].get("task")
            owners[fid] = label if label in batch_ids else _owner(found[fid], tasks, scope)
            if not owners[fid]:
                errs.append(f"{fid} matches no task path in {s['batch']} — add `--assign {fid}=T##`.")
    if errs:
        raise TPError(*errs)
    for fid in fids:
        found[fid]["task"] = owners[fid]
        s["dismissed"].pop(fid, None)
    by_task = _route(wf, state, plan, scope, s, [found[fid] for fid in fids])
    s["accepted"] = sorted(set(s["accepted"]) | set(fids))
    s["fix_tasks"] = sorted(by_task)
    s["status"] = "waiting_fixes"
    s.setdefault("reopened", []).append({"findings": fids, "by": by, "answer": answer})
    return "\n".join([f"{sid}: reopened {', '.join(fids)} → {', '.join(sorted(by_task))}; it verifies them once "
                      "those tasks are accepted again."] + list(by_task.values()))


def resolve(wf: Workflow, state: Dict[str, Any], sid: str, action: str, answer: str, by: Optional[str] = None,
            force: bool = False, fids: Optional[List[str]] = None, assign: Optional[List[str]] = None) -> str:
    s = sessions(state).get(sid)
    if s is None:
        raise TPError(f"{sid} is not a review session.")
    if action == "reopen":
        out = _reopen(wf, state, sid, s, fids or [], assign or [], answer, by)
    else:
        if s["status"] != "blocked":
            raise TPError(f"{sid} is not blocked (status {s['status']})"
                          + ("; `--action reopen --findings F#` sends its findings back to their authors."
                             if s["status"] == "done" else "."))
        kind = s.get("block", "rounds")  # sessions blocked before blocks had kinds: as after verification
        held = [f["id"] for f in s["findings"] if f["blocking"]]
        if action == "clear" and kind == "edits":
            _settle(s, s.get("held") or {"status": "needs_triage" if held else "done"})
        elif action == "accept":
            if by != "human":
                raise TPError(f"accepting {sid} as is ships its work without the fixes its review asked for — only the "
                              "human decides that. Ask them, then resolve with --by human.")
            if kind == "edits" and held and not force:
                raise TPError(f"{sid} holds {len(held)} blocking findings nobody has triaged ({', '.join(held)}); "
                              "accepting would drop them.",
                              f"Edits not the reviewer's: `tp resolve --review {sid} --action clear --by <who>`. To "
                              "ship without "
                              "these findings, add --force.")
            _settle(s, {"status": "done", "accepted_as_is": answer, "accepted_by": by})
        elif action == "retry" and kind == "rounds":
            s["extra_rounds"] = s.get("extra_rounds", 0) + 1
            _settle(s, {"status": "needs_triage"})
        else:
            raise TPError(f"{sid} is blocked by " + (
                "edits; it takes --action clear (they were not the reviewer's: its findings go on) or accept "
                "(ship as is)." if kind == "edits" else
                "findings still open after verification; it takes --action accept (ship as is) or retry (one "
                "more fix and verification round)."))
        out = f"{sid} → {s['status']}. `tp next`."
    wf.save(state)
    wf.decision(f"resolve {sid} {action}", answer, who=by)
    return out


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
        reopened = "".join(f"; reopened {', '.join(r['findings'])}{_by(r.get('by'))}: {r['answer']}"
                           for r in s.get("reopened", []))
        out.append(f"- {sid}: {s['status']} after {s['round']} round{'s' if s['round'] != 1 else ''}; "
                   f"{len(s['accepted'])} findings fixed ({', '.join(s['fix_tasks']) or 'none'}), "
                   f"{len(s['dismissed'])} dismissed by the manager" + reopened
                   + (f"; accepted as is{_by(s.get('accepted_by'))}: {s['accepted_as_is']}"
                      if s.get("accepted_as_is") else ""))
    return out


def _by(who: Optional[str]) -> str:
    """Attribution only where `tp resolve --by` recorded one."""
    return f" by the {who}" if who else ""
