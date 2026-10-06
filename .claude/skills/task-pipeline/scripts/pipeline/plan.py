"""The plan: one JSON file of small tasks, checked against the confirmed scope, the
catalog, and the time budget; rendered for the human; frozen once approved."""
from __future__ import annotations

import math
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Set, Tuple

from . import scope as scopemod
from .common import TPError, Workflow, limit, load_json, minutes_since, now_iso, sha_file, words

BUILTIN_TASK_CHECKS = {"docs": "every relative link resolves, and every code citation is written repo-relative "
                               "(`path/to/file.go:12`, `:12-20`) and points at a real line (a citation whose lines "
                               "do not name what its sentence claims is flagged for the manager's fact check)"}
BUILTIN_FINAL_CHECKS = {"docs-all": "links, citations, and reachability from index.md for the Markdown each write "
                                    "workspace gained or changed since approval (every file when it is not under git)"}
REVIEW_MINUTES = 8


def review_batches(plan: Dict[str, Any], scope: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The end-of-pipeline review batches: the plan's, or one batch of every task."""
    if not scopemod.final_reviewers(scope):
        return []
    return plan.get("review_batches") or [{"id": "B1", "tasks": [t["id"] for t in plan["tasks"]]}]


def session_minutes(batch: Dict[str, Any], plan: Dict[str, Any], scope: Dict[str, Any]) -> int:
    """How long one reviewer needs for a batch: review time grows with what it reviews."""
    tasks = {t["id"]: t for t in plan["tasks"]}
    return sum(limit("review_minutes_per_code_task") if tid in tasks and is_code(tasks[tid], scope)
               else limit("review_minutes_per_doc_task") for tid in batch.get("tasks", []))


def review_tail(plan: Dict[str, Any], scope: Dict[str, Any]) -> Tuple[int, int]:
    """(review sessions, minutes they add after the last task): the sessions spread over the
    lanes, then one verification session each."""
    reviewers = len(scopemod.final_reviewers(scope))
    lengths = [session_minutes(b, plan, scope) for b in review_batches(plan, scope) for _ in range(reviewers)]
    if not lengths:
        return 0, 0
    lanes = limit("max_in_flight")
    review = max(max(lengths), math.ceil(sum(lengths) / lanes))
    return len(lengths), review + math.ceil(len(lengths) / lanes) * limit("verify_session_minutes")


def _validate_batches(plan: Dict[str, Any], scope: Dict[str, Any]) -> List[str]:
    ids = [t.get("id") for t in plan["tasks"]]
    if plan.get("review_batches") and not scopemod.final_reviewers(scope):
        return ["review_batches need review 'final' in scope.json."]
    batches = review_batches(plan, scope)
    if not batches:
        return []
    errs = []
    seen: Dict[str, str] = {}
    for b in batches:
        bid = str(b.get("id", ""))
        if not re.fullmatch(r"B\d+", bid):
            errs.append(f"review batch id {bid!r} must look like B1.")
        for tid in b.get("tasks", []):
            if tid not in ids:
                errs.append(f"{bid}: unknown task {tid}.")
            elif tid in seen:
                errs.append(f"{tid} is in two review batches ({seen[tid]}, {bid}).")
            seen[tid] = bid
        minutes, cap = session_minutes(b, plan, scope), limit("max_review_session_minutes")
        if len(b.get("tasks", [])) > limit("max_batch_tasks") or minutes > cap:
            errs.append(f"{bid} needs about {minutes} min of review per reviewer ({len(b.get('tasks', []))} tasks); "
                        f"one session is at most {cap} min and {limit('max_batch_tasks')} tasks — split the work "
                        "into smaller review_batches.")
    for tid in ids:
        if tid not in seen:
            errs.append(f"{tid} is in no review batch.")
    return errs


def load_plan(wf: Workflow) -> Dict[str, Any]:
    data = load_json(wf.plan_json, "the plan")
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        raise TPError(f"{wf.plan_json} must be a JSON object with a `tasks` list.")
    return data


def task_kind(task: Dict[str, Any], scope: Dict[str, Any]) -> Optional[str]:
    kinds = {d["id"]: d["kind"] for d in scope["deliverables"]}
    served = {kinds[s] for s in task.get("serves", []) if s in kinds}
    return served.pop() if len(served) == 1 else None


def is_code(task: Dict[str, Any], scope: Dict[str, Any]) -> bool:
    return task_kind(task, scope) == "code"


def reviewer_for(task: Dict[str, Any], scope: Dict[str, Any]) -> Optional[str]:
    """The reviewer of a task, or None when this task gets no per-task review."""
    if scope.get("review") not in ("per-task", "both") or task.get("review") is False:
        return None
    if task.get("reviewer"):
        return task["reviewer"]
    kind = task_kind(task, scope)
    for agent in scopemod.participants(scope, "reviewer"):
        if kind in scopemod.agent_kinds(agent, "reviewer"):
            return agent
    return None


def tests_agent(task: Dict[str, Any], scope: Dict[str, Any]) -> str:
    tests = scopemod.participants(scope, "tests")
    return tests[0] if tests else task["agent"]


def _literal_prefix(glob: str) -> str:
    parts = []
    for part in PurePosixPath(glob).parts:
        if any(ch in part for ch in "*?["):
            break
        parts.append(part)
    return "/".join(parts)


def paths_overlap(a: str, b: str) -> bool:
    pa, pb = _literal_prefix(a), _literal_prefix(b)
    if pa == pb:
        return True
    a_glob, b_glob = pa != a, pb != b
    return (a_glob and (pb.startswith(pa + "/") or pa == "")) or (b_glob and (pa.startswith(pb + "/") or pb == ""))


def _ancestors(tasks: Dict[str, Dict[str, Any]]) -> Dict[str, Set[str]]:
    memo: Dict[str, Set[str]] = {}

    def walk(tid: str, stack: Tuple[str, ...]) -> Set[str]:
        if tid in memo:
            return memo[tid]
        if tid in stack:
            raise TPError("dependency cycle: " + " -> ".join(stack[stack.index(tid):] + (tid,)))
        found: Set[str] = set()
        for dep in tasks[tid].get("depends_on", []):
            if dep in tasks:
                found |= {dep} | walk(dep, stack + (tid,))
        memo[tid] = found
        return found

    for tid in tasks:
        walk(tid, ())
    return memo


def resolve_ref(ref: str, scope: Dict[str, Any], wf_root: Path) -> Optional[Path]:
    """`wf:<path>` (inside the workflow folder) or `<workspace>:<path>` as a path; None if it is neither."""
    prefix, _, rel = str(ref).partition(":")
    pp = PurePosixPath(rel)
    if not rel or pp.is_absolute() or ".." in pp.parts:
        return None
    if prefix == "wf":
        return wf_root / rel
    wss = scopemod.workspaces(scope)
    return Path(wss[prefix]["path"]) / rel if prefix in wss else None


def conventions(plan: Dict[str, Any], scope: Dict[str, Any], wf_root: Path) -> List[Path]:
    """The files every brief starts from (plan `conventions`)."""
    return [p for p in (resolve_ref(c, scope, wf_root) for c in plan.get("conventions", [])) if p is not None]


def conventions_shas(plan: Dict[str, Any], scope: Dict[str, Any], wf_root: Path) -> Dict[str, Optional[str]]:
    """Frozen with the plan at approval: a conventions file is part of every brief's contract."""
    return {str(p): sha_file(p) for p in conventions(plan, scope, wf_root)}


def lane_minutes(task: Dict[str, Any], scope: Dict[str, Any]) -> int:
    return int(task.get("estimate_min", 0)) + (REVIEW_MINUTES if reviewer_for(task, scope) else 0)


def critical_path(tasks: Dict[str, Dict[str, Any]], scope: Dict[str, Any]) -> Tuple[int, List[str]]:
    best: Dict[str, Tuple[int, List[str]]] = {}

    def longest(tid: str) -> Tuple[int, List[str]]:
        if tid not in best:
            deps = [longest(d) for d in tasks[tid].get("depends_on", []) if d in tasks]
            length, path = max(deps, default=(0, []))
            best[tid] = (length + lane_minutes(tasks[tid], scope), path + [tid])
        return best[tid]

    return max((longest(t) for t in tasks), default=(0, []))


def validate(plan: Dict[str, Any], scope: Dict[str, Any], state: Dict[str, Any], wf_root: Path,
             budget_check: bool = True) -> List[str]:
    errs: List[str] = []
    wss = scopemod.workspaces(scope)
    deliverables = {d["id"] for d in scope["deliverables"]}
    authors = set(scopemod.participants(scope, "author"))
    tasks_list = plan["tasks"]
    checks = dict(BUILTIN_TASK_CHECKS, **plan.get("checks", {}))

    if not plan.get("title"):
        errs.append("plan.json needs a `title`.")
    if words(plan.get("summary", "")) > 80:
        errs.append("summary is over 80 words.")
    if not tasks_list:
        errs.append("the plan has no tasks.")
    if len(tasks_list) > limit("max_tasks"):
        errs.append(f"{len(tasks_list)} tasks; the limit is {limit('max_tasks')} — merge or cut tasks "
                    f"(target {limit('target_task_minutes')} min each).")
    for name, spec in plan.get("checks", {}).items():
        if not isinstance(spec, dict) or not spec.get("cmd"):
            errs.append(f"check {name!r} needs a `cmd`.")
        elif spec.get("cwd") and spec["cwd"] not in wss:
            errs.append(f"check {name!r}: cwd {spec['cwd']!r} is not a workspace.")
    for name in plan.get("final_checks", []):
        if name not in BUILTIN_FINAL_CHECKS and name not in plan.get("checks", {}):
            errs.append(f"final check {name!r} is neither built in ({', '.join(BUILTIN_FINAL_CHECKS)}) "
                        "nor defined in `checks`.")
    for ref in plan.get("conventions", []):
        path = resolve_ref(ref, scope, wf_root)
        if path is None or not path.is_file():
            errs.append(f"conventions {ref!r} must name an existing file as `wf:<path in the workflow folder>` "
                        "or `<workspace>:<path>`.")

    tasks: Dict[str, Dict[str, Any]] = {}
    served: Set[str] = set()
    computable = True  # ids, dependencies, and estimates are sound enough for the graph checks
    all_ids = {x.get("id") for x in tasks_list}
    for t in tasks_list:
        tid = str(t.get("id", ""))
        if not re.fullmatch(r"T\d{2,3}", tid) or tid in tasks:
            errs.append(f"task id {tid!r} must be unique and look like T01.")
            computable = False
            continue
        tasks[tid] = t
        for key in ("title", "agent", "workspace", "paths", "brief", "acceptance", "serves"):
            if not t.get(key):
                errs.append(f"{tid}: needs `{key}`.")
        unknown = [d for d in t.get("serves", []) if d not in deliverables]
        for d in unknown:
            errs.append(f"{tid}: serves unknown deliverable {d}.")
        served |= set(t.get("serves", []))
        kind = task_kind(t, scope)
        if t.get("serves") and not unknown and kind is None:
            errs.append(f"{tid}: every deliverable a task serves must be of one kind.")
        agent = t.get("agent")
        if agent and kind and (agent not in authors or kind not in scopemod.agent_kinds(agent, "author")):
            errs.append(f"{tid}: agent {agent} is not a confirmed author for {kind} in scope.json.")
        ws = wss.get(t.get("workspace", ""))
        if ws is None:
            errs.append(f"{tid}: workspace {t.get('workspace')!r} is not in scope.json.")
        elif ws["mode"] != "write":
            errs.append(f"{tid}: workspace {ws['name']} is read-only; deliverables go in a write workspace.")
        for p in t.get("paths", []):
            pp = PurePosixPath(str(p))
            if pp.is_absolute() or ".." in pp.parts or not str(p).strip():
                errs.append(f"{tid}: path {p} leaves the workspace; paths are relative to it.")
        for src in t.get("sources", []):
            prefix, _, ref = str(src).partition(":")
            if prefix == "research":
                if state.get("recon", {}).get(ref, {}).get("status") != "done":
                    errs.append(f"{tid}: source {src} is not an answered research item.")
            elif prefix == "wf":
                path = resolve_ref(src, scope, wf_root)
                if path is None or not path.exists():
                    errs.append(f"{tid}: source {src} is not a file or folder inside the workflow folder.")
            elif not ref or prefix not in wss:
                errs.append(f"{tid}: source {src!r} must be `<workspace>:<path or glob>`, `wf:<path>`, or "
                            "`research:R#`.")
        if words(t.get("brief", "")) > limit("task_brief_words"):
            errs.append(f"{tid}: brief is {words(t['brief'])} words; the limit is {limit('task_brief_words')}.")
        if len(t.get("acceptance", [])) > limit("max_acceptance"):
            errs.append(f"{tid}: {len(t['acceptance'])} acceptance criteria; the limit is {limit('max_acceptance')}.")
        for c in t.get("checks", []):
            if c not in checks:
                errs.append(f"{tid}: unknown check {c!r} (built in: {', '.join(BUILTIN_TASK_CHECKS)}; "
                            "or define it in plan `checks`).")
        est = t.get("estimate_min")
        if not isinstance(est, int) or est < 1:
            errs.append(f"{tid}: estimate_min must be a whole number of minutes.")
            computable = False
        elif est > limit("max_task_minutes"):
            errs.append(f"{tid}: estimate_min {est} exceeds {limit('max_task_minutes')} — split the task.")
        for dep in t.get("depends_on", []):
            if dep not in all_ids:
                errs.append(f"{tid}: depends on unknown {dep}.")
                computable = False
        if kind == "code":
            if not t.get("test_cmd"):
                errs.append(f"{tid}: a code task needs `test_cmd` (tests first, observed red, then green).")
            if t.get("test_mode", "red") not in ("red", "pin"):
                errs.append(f"{tid}: test_mode must be red (new behaviour) or pin (characterize current behaviour).")
        if scope.get("review") in ("per-task", "both") and t.get("review") is not False:
            rev = reviewer_for(t, scope)
            if rev is None or rev not in scopemod.participants(scope, "reviewer"):
                errs.append(f"{tid}: no confirmed reviewer for {kind} tasks.")
        if t.get("model") not in (None, "sonnet", "opus", "haiku"):
            errs.append(f"{tid}: model must be sonnet, opus, or haiku (or omitted).")

    for d in sorted(deliverables - served):
        errs.append(f"{d} is served by no task.")
    if not computable:
        return errs

    try:
        ancestors = _ancestors(tasks)
    except TPError as exc:
        return errs + exc.lines
    ids = list(tasks)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            ta, tb = tasks[a], tasks[b]
            if ta.get("workspace") != tb.get("workspace") or a in ancestors[b] or b in ancestors[a]:
                continue
            for pa in ta.get("paths", []):
                for pb in tb.get("paths", []):
                    if paths_overlap(pa, pb):
                        errs.append(f"{a} and {b} overlap on {pa} / {pb} — order them with depends_on "
                                    "or split the paths (parallel tasks must write disjoint files).")

    errs += _validate_batches(plan, scope)
    budget = scope.get("budget_minutes")
    if budget and budget_check:
        left = budget - minutes_since(state.get("created"))
        total = sum(lane_minutes(t, scope) for t in tasks.values())
        span, chain = critical_path(tasks, scope)
        lanes = limit("max_in_flight")
        work = math.ceil(total / lanes)
        sessions, tail = review_tail(plan, scope)
        if max(span, work) + tail > left:
            what = (f"critical path is {span} min ({' -> '.join(chain)})" if span >= work
                    else f"work totals {total} lane-min = {work} min over {lanes} lanes")
            if tail:
                what += f", plus a {tail}-min review tail ({sessions} review sessions and their verification)"
            errs.append(f"{what}, but the budget leaves {left:.0f} of {budget} min — cut or merge tasks, "
                        "or fewer review lenses.")
    return errs


def warnings(plan: Dict[str, Any]) -> List[str]:
    """What a plan check cannot refuse but the manager should know before the run hits it."""
    out = []
    for t in plan.get("tasks", []):
        for p in t.get("paths", []):
            name = PurePosixPath(str(p)).name
            if "report" in PurePosixPath(name).stem.lower():
                out.append(f"{t.get('id')} writes {name}: Claude Code has refused a sub-agent creating a new "
                           "report-like file (seen with report.md) — prefer a name such as README.md or synthesis.md.")
    return out


def render(plan: Dict[str, Any], scope: Dict[str, Any], wf: Workflow) -> str:
    tasks = {t["id"]: t for t in plan["tasks"]}
    total = sum(lane_minutes(t, scope) for t in tasks.values())
    span, _ = critical_path(tasks, scope)
    lanes = limit("max_in_flight")
    sessions, tail = review_tail(plan, scope)
    out = [f"# Plan — {plan['title']}", "", plan.get("summary", ""), "",
           f"**{len(tasks)} tasks** · about {max(span, math.ceil(total / lanes)) + tail} min of execution on "
           f"{lanes} lanes · budget {scope.get('budget_minutes') or 'none'} · scope: `scope.md`", ""]
    if plan.get("conventions"):
        out += ["**Conventions every brief starts from** (frozen with the plan): "
                + ", ".join(f"`{c}`" for c in plan["conventions"]), ""]
    if sessions:
        nb, nr = len(review_batches(plan, scope)), len(scopemod.final_reviewers(scope))
        out += [f"**Review:** {nb} batch{'es' if nb > 1 else ''} × {nr} reviewer{'s' if nr > 1 else ''} = "
                f"{sessions} review session{'s' if sessions > 1 else ''} ({', '.join(scopemod.final_reviewers(scope))}), "
                f"run together after every task is accepted, plus at most {sessions} verification "
                f"session{'s' if sessions > 1 else ''} scoped to what they find (about {tail} min).", ""]
    out += [
           "| Task | Title | Agent | Review | Est | After | Writes |", "|---|---|---|---|---|---|---|"]
    for t in tasks.values():
        rev = reviewer_for(t, scope) or "—"
        deps = ", ".join(t.get("depends_on", [])) or "—"
        paths = ", ".join(f"`{p}`" for p in t["paths"])
        out.append(f"| {t['id']} | {t['title']} | {t['agent']} | {rev} | {t['estimate_min']}m | {deps} | "
                   f"{t['workspace']}: {paths} |")
    out += ["", "## Tasks"]
    for t in tasks.values():
        out += ["", f"### {t['id']} — {t['title']} (serves {', '.join(t['serves'])})", "", t["brief"], ""]
        out += [f"- [ ] {a}" for a in t["acceptance"]]
        checks = list(t.get("checks", []))
        if t.get("test_cmd"):
            checks.insert(0, f"tests first, then `{t['test_cmd']}` {'passes' if t.get('test_mode') == 'pin' else 'red → green'}")
        if checks:
            out.append(f"- Checks: {', '.join(checks)}")
    finals = plan.get("final_checks", [])
    out += ["", "## Final checks", ""] + ([f"- {c}" for c in finals] or ["- none"])
    for b in review_batches(plan, scope):
        out.append(f"- review batch {b['id']}: {', '.join(b['tasks'])}")
    if plan.get("questions"):
        out += ["", "## Questions for the human (non-blocking)", ""] + [f"- {q}" for q in plan["questions"]]
    noticed = wf.noticed_items()
    if noticed:
        out += ["", "## Noticed, not in plan", ""] + [f"- {n}" for n in noticed]
    return "\n".join(out) + "\n"


def _checked(wf: Workflow, state: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if state.get("scope_sha") != sha_file(wf.scope_json):
        raise TPError("scope.json changed after confirmation — scope changes need the human "
                      "(`tp revise --scope --feedback \"<their words>\"`), or restore it.")
    scope = scopemod.load_scope(wf)
    plan = load_plan(wf)
    errs = validate(plan, scope, state, wf.root)
    if errs:
        raise TPError(*errs)
    (wf.root / "plan.md").write_text(render(plan, scope, wf))
    return plan, scope


def cmd_check(wf: Workflow) -> str:
    state = wf.load()
    if state["phase"] != "PLANNING":
        raise TPError(f"Plans are checked in PLANNING; the workflow is {state['phase']}.")
    plan, _ = _checked(wf, state)
    wf.event("plan_check", tasks=len(plan["tasks"]))
    return "\n".join([f"WARN: {w}" for w in warnings(plan)]
                     + [f"plan ok — {len(plan['tasks'])} tasks; rendered {wf.root / 'plan.md'}. Next: `tp plan submit`."])


def cmd_submit(wf: Workflow) -> str:
    state = wf.load()
    if state["phase"] != "PLANNING":
        raise TPError(f"Only a PLANNING workflow can be submitted; it is {state['phase']}.")
    unsettled = []
    for rid, item in state.get("recon", {}).items():
        if item["status"] in ("pending", "in_flight"):
            unsettled.append(f"{rid} is {item['status'].replace('_', ' ')} — run and record it, or "
                             f"`tp research drop {rid} --reason \"...\"`.")
        for f in item.get("followups", []):
            if f["status"] == "open":
                unsettled.append(f"{f['id']} is undecided: `tp research add ... --from {f['id']}` or "
                                 f"`tp research dismiss {f['id']} --reason \"...\"`.")
    if unsettled:
        raise TPError(*unsettled)
    plan, scope = _checked(wf, state)
    state["plan_submitted_sha"] = sha_file(wf.plan_json)
    state["phase"] = "AWAITING_APPROVAL"
    state["submitted"] = now_iso()
    wf.save(state)
    wf.event("plan_submit", planning_min=round(minutes_since(state["created"]), 1))
    out = [f"submitted — {len(plan['tasks'])} tasks, planning took {minutes_since(state['created']):.0f} min.",
           f"Plan for the human: {wf.root / 'plan.md'}"]
    if plan.get("questions"):
        out += ["Questions to put to the human:"] + [f"  - {q}" for q in plan["questions"]]
    noticed = wf.noticed_items()
    if noticed:
        out += ["Noticed, not in plan (tell the human):"] + [f"  - {n}" for n in noticed]
    out.append("Ask the human to approve or revise (AskUserQuestion). Then `tp approve --answer \"<their words>\"` "
               "or `tp revise --feedback \"<their words>\"`.")
    return "\n".join(out)


def cmd_approve(wf: Workflow, answer: str) -> str:
    from . import run  # baseline capture lives with execution

    state = wf.load()
    if state["phase"] != "AWAITING_APPROVAL":
        raise TPError(f"Nothing awaits approval: the workflow is {state['phase']} (submit the plan first).")
    if sha_file(wf.plan_json) != state.get("plan_submitted_sha"):
        raise TPError("plan.json changed since it was submitted — run `tp plan check` and `tp plan submit` again.")
    plan = load_plan(wf)
    scope = scopemod.load_scope(wf)
    state["plan_approved_sha"] = state["plan_submitted_sha"]
    state["conventions_sha"] = conventions_shas(plan, scope, wf.root)
    state["phase"] = "EXECUTING"
    state["approved"] = now_iso()
    for t in plan["tasks"]:
        state["tasks"].setdefault(t["id"], run.new_task_state())
    state["readonly_baseline"] = run.readonly_baseline(wf, scope)
    from . import review  # end-of-pipeline review sessions and their diff baseline
    state["write_baseline"] = review.write_baseline(scope)
    state["reviews"] = review.new_reviews(plan, scope, state.get("reviews", {}))
    wf.save(state)
    wf.decision("plan approve", answer)
    wf.event("approve")
    return "approved — EXECUTING. Run `tp next` and keep going until it says final or human."


AMEND_JSON = "plan-amend.json"


def _amendment(approved: Dict[str, Any], draft: Dict[str, Any], scope: Dict[str, Any], state: Dict[str, Any],
               wf_root: Path) -> Tuple[List[str], List[str]]:
    """(what the draft changes, why it may not): only tasks never dispatched may change or go, and
    a review batch whose review has started keeps exactly its tasks."""
    old = {t["id"]: t for t in approved["tasks"]}
    new = {t.get("id"): t for t in draft["tasks"]}
    added = [t for t in new if t not in old]
    removed = [t for t in old if t not in new]
    changed = [t for t in old if t in new and new[t] != old[t]]
    errs = []
    for tid in changed + removed:
        ts = state["tasks"].get(tid, {})
        if ts.get("started") or ts.get("status", "pending") != "pending":
            errs.append(f"{tid} has started ({ts.get('status')}); only tasks not yet dispatched can change or go. "
                        f"Reopen it (`tp resolve --task {tid} --action reopen`), or ask the human about `tp revise`.")
    old_b = {b["id"]: sorted(b["tasks"]) for b in review_batches(approved, scope)}
    new_b = {b["id"]: sorted(b["tasks"]) for b in review_batches(draft, scope)}
    for bid in sorted(set(old_b) | set(new_b)):
        if old_b.get(bid) == new_b.get(bid):
            continue
        started = [sid for sid, s in state.get("reviews", {}).items() if s["batch"] == bid and s["status"] != "pending"]
        if started:
            errs.append(f"{bid}'s review has started ({', '.join(started)}): leave its tasks as they are and put new "
                        f"work in a new review batch (`review_batches`, e.g. B{len(new_b) + 1}).")
    changes = [f"{verb} {', '.join(ids)}" for verb, ids in (("added", added), ("changed", changed),
                                                             ("removed", removed)) if ids]
    changes += [f"review batches {', '.join(sorted(set(new_b) - set(old_b)))} new"] if set(new_b) - set(old_b) else []
    changes += [f"{key} changed" for key in ("title", "summary", "checks", "final_checks", "conventions", "questions")
                if approved.get(key) != draft.get(key)]
    if conventions_shas(draft, scope, wf_root) != state.get("conventions_sha", {}) and "conventions changed" not in changes:
        changes.append("conventions files changed")
    return changes, errs


def _remaining(plan: Dict[str, Any], scope: Dict[str, Any], state: Dict[str, Any]) -> List[str]:
    """The open work an amended plan leaves, against the budget's wall-clock minutes left: shown, not
    enforced — an amendment exists because the work outgrew the plan, and the human decides."""
    done = ("accepted", "skipped")
    tasks = {t["id"]: t for t in plan["tasks"] if state["tasks"].get(t["id"], {}).get("status") not in done}
    total = sum(lane_minutes(t, scope) for t in tasks.values())
    span, _ = critical_path(tasks, scope)
    reviews = state.get("reviews", {})
    open_batches = [b for b in review_batches(plan, scope)
                    if all(s["status"] == "pending" for s in reviews.values() if s["batch"] == b["id"])]
    tail = review_tail(dict(plan, review_batches=open_batches), scope)[1] if open_batches else 0
    remaining = max(span, math.ceil(total / limit("max_in_flight"))) + tail
    line = f"remaining work: about {remaining} min ({len(tasks)} open tasks" + (f", {tail}-min review tail" if tail else "") + ")"
    budget = scope.get("budget_minutes")
    if not budget:
        return [line + "."]
    left = budget - minutes_since(state["created"])
    out = [f"{line}; the budget has {left:.0f} of {budget} min left, wall-clock."]
    if remaining > left:
        out.append("WARN: the remaining work runs past the budget — say so when you ask the human.")
    return out


def cmd_amend(wf: Workflow, answer: Optional[str]) -> str:
    """Change the approved plan mid-run with the human's answer: add tasks, or change or remove tasks
    not yet dispatched. The draft lives in plan-amend.json, so plan.json stays the contract — and
    agents in flight can still be recorded — until the human agrees."""
    from . import review, run
    with wf.locked():
        state = wf.load()
        if state["phase"] != "EXECUTING":
            raise TPError(f"amend changes a plan mid-run; the workflow is {state['phase']}.")
        if sha_file(wf.plan_json) != state.get("plan_approved_sha"):
            raise TPError("plan.json changed after approval — restore it; an amendment goes in plan-amend.json.")
        approved, scope = load_plan(wf), scopemod.load_scope(wf)
        draft_path = wf.root / AMEND_JSON
        if not draft_path.exists():
            shutil.copyfile(wf.plan_json, draft_path)
            return (f"Draft started: {draft_path}, a copy of the approved plan. Add tasks, or change or remove tasks "
                    "not yet dispatched (new work needs a review batch whose review has not started). To change "
                    "conventions, write them to a new file and point `conventions` at it: the frozen file stays "
                    "as it is until the human agrees. Then `tp plan amend` to check it.")
        draft = load_json(draft_path, "the amended plan")
        if not isinstance(draft, dict) or not isinstance(draft.get("tasks"), list):
            raise TPError(f"{draft_path} must be a JSON object with a `tasks` list.")
        errs = validate(draft, scope, state, wf.root, budget_check=False)
        changes, refusals = _amendment(approved, draft, scope, state, wf.root)
        if errs or refusals:
            raise TPError(*(errs + refusals))
        if not changes:
            return f"{draft_path.name} changes nothing yet."
        remaining = _remaining(draft, scope, state)
        if answer is None:
            (wf.root / "plan-amend.md").write_text(render(draft, scope, wf))
            return "\n".join([f"amendment ok — {'; '.join(changes)}."] + remaining + [
                f"Show the human {wf.root / 'plan-amend.md'} and ask (AskUserQuestion); then "
                "`tp plan amend --answer \"<their words>\"`."])
        shutil.copyfile(draft_path, wf.plan_json)
        draft_path.replace(wf.meta / f"plan-amend-{len(state.get('amendments', [])) + 1}.json")
        (wf.root / "plan-amend.md").unlink(missing_ok=True)
        state["plan_approved_sha"] = state["plan_submitted_sha"] = sha_file(wf.plan_json)
        state["conventions_sha"] = conventions_shas(draft, scope, wf.root)
        ids = [t["id"] for t in draft["tasks"]]
        for tid in [t for t in state["tasks"] if t not in ids]:
            del state["tasks"][tid]
        for tid in ids:
            state["tasks"].setdefault(tid, run.new_task_state())
        state["reviews"] = review.new_reviews(draft, scope, state.get("reviews", {}))
        state.setdefault("amendments", []).append({"ts": now_iso(), "changes": changes, "answer": answer})
        wf.save(state)
        (wf.root / "plan.md").write_text(render(draft, scope, wf))
        wf.decision("plan amend", answer)
        wf.event("plan_amend", changes=changes)
        return "\n".join([f"amended — {'; '.join(changes)}."] + remaining + ["`tp next`."])


def cmd_revise(wf: Workflow, feedback: str, to_scope: bool) -> str:
    state = wf.load()
    if state["phase"] == "DONE":
        raise TPError("The workflow is DONE; start a new one for new work.")
    if state.get("in_flight"):
        raise TPError(f"agents in flight: {', '.join(state['in_flight'])} — record them first.")
    state["phase"] = "SCOPING" if to_scope else "PLANNING"
    for key in ("plan_submitted_sha", "plan_approved_sha"):
        state.pop(key, None)
    wf.save(state)
    wf.decision("revise scope" if to_scope else "revise plan", feedback)
    wf.event("revise", scope=to_scope)
    if to_scope:
        return "back to SCOPING — edit scope.json, `tp scope check`, and have the human confirm it again."
    return ("back to PLANNING — edit plan.json from the feedback, `tp plan check`, `tp plan submit`. "
            "Accepted tasks stay accepted.")
