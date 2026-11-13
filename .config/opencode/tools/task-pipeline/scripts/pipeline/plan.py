"""The plan: one JSON file of small tasks, checked against the confirmed scope and the catalog;
its time estimate is reported against the budget, never enforced; rendered for the human; frozen
once approved."""
from __future__ import annotations

import json
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
# `tp publish` destinations: what the manager posts, from a reviewed `wf:` draft, after the human's OK.
PUBLISH_TARGETS = ("jira-comment", "jira-description", "jira-issue")
WHEN = ("after_review", "anytime")
# A transport agent's brief that asks it to write the content itself: content is a document task's.
_DRAFTING = re.compile(r"(?<![\w:/.-])(draft(s|ing)?|summari[sz](e[sd]?|ing)|write[- ]up|documenting)\b", re.I)


def is_integration(task: Dict[str, Any], scope: Dict[str, Any]) -> bool:
    return task_kind(task, scope) == "integration" or bool(task.get("publish"))


def is_publish(task: Dict[str, Any]) -> bool:
    return bool(task.get("publish"))


def wf_rel(path: str) -> Optional[str]:
    """`wf:<rel>` → rel; None for a workspace path."""
    return str(path)[3:] if str(path).startswith("wf:") else None


def review_batches(plan: Dict[str, Any], scope: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The end-of-pipeline review batches: the plan's, or one batch of every task. Integration
    tasks are never reviewed: they post content another task wrote and the review already saw."""
    if not scopemod.final_reviewers(scope):
        return []
    if plan.get("review_batches"):
        return plan["review_batches"]
    # By default code and documents are separate batches, so code review can start before the
    # documents are written, and the documents are reviewed against the reviewed code.
    work = [t for t in plan["tasks"] if not is_integration(t, scope)]
    groups = [[t["id"] for t in work if is_code(t, scope)], [t["id"] for t in work if not is_code(t, scope)]]
    return [{"id": f"B{i}", "tasks": ids} for i, ids in enumerate((g for g in groups if g), 1)]


def review_sessions(plan: Dict[str, Any], scope: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One session per batch and review unit (a packed lens session or a lone reviewer), over the
    batch's whole work. Every unit sees every batch: in a real run the doc reviewer caught wrong
    code comments, and the code lenses caught false claims in the documents. code: the batch is
    all code, so its review may start before the rest of the work is done."""
    tasks = {t["id"]: t for t in plan["tasks"]}
    out = []
    for b in review_batches(plan, scope):
        mine = [tid for tid in b.get("tasks", []) if tid in tasks and not is_integration(tasks[tid], scope)]
        if not mine:
            continue
        for unit in scopemod.review_units(scope):
            out.append({"sid": f"{b['id']}/{unit['name']}", "batch": b["id"], "reviewer": unit["agent"],
                        "lenses": unit["lenses"], "tasks": mine, "code": all(is_code(tasks[t], scope) for t in mine)})
    return out


def session_minutes(batch: Dict[str, Any], plan: Dict[str, Any], scope: Dict[str, Any]) -> int:
    """How long one reviewer needs for a batch: review time grows with what it reviews."""
    tasks = {t["id"]: t for t in plan["tasks"]}
    return sum(limit("review_minutes_per_code_task") if tid in tasks and is_code(tasks[tid], scope)
               else limit("review_minutes_per_doc_task") for tid in batch.get("tasks", []))


def review_tail(plan: Dict[str, Any], scope: Dict[str, Any]) -> Tuple[int, int]:
    """(review sessions, minutes they add after the last task): the sessions spread over the
    lanes, then one verification session each."""
    lengths = [session_minutes(s, plan, scope) for s in review_sessions(plan, scope)]
    if not lengths:
        return 0, 0
    lanes = limit("max_in_flight")
    review = max(max(lengths), math.ceil(sum(lengths) / lanes))
    return len(lengths), review + math.ceil(len(lengths) / lanes) * limit("verify_session_minutes")


def _validate_batches(plan: Dict[str, Any], scope: Dict[str, Any], frozen: Set[str] = frozenset()) -> List[str]:
    ids = [t.get("id") for t in plan["tasks"]]
    if plan.get("review_batches") and not scopemod.final_reviewers(scope):
        return ["review_batches need review 'final' in scope.json."]
    batches = review_batches(plan, scope)
    if not batches:
        return []
    errs = []
    seen: Dict[str, str] = {}
    by_id = {t.get("id"): t for t in plan["tasks"]}
    for b in batches:
        bid = str(b.get("id", ""))
        if not re.fullmatch(r"B\d+", bid):
            errs.append(f"review batch id {bid!r} must look like B1.")
        for tid in b.get("tasks", []):
            if tid not in ids:
                errs.append(f"{bid}: unknown task {tid}.")
            elif tid in seen:
                errs.append(f"{tid} is in two review batches ({seen[tid]}, {bid}).")
            elif is_integration(by_id[tid], scope) and tid not in frozen:
                errs.append(f"{bid}: {tid} is integration work, which is never reviewed — review the task that "
                            "writes its content, and leave the integration task out of review_batches.")
            seen[tid] = bid
    cap = limit("max_review_session_minutes")
    for s in review_sessions(plan, scope):
        minutes = session_minutes(s, plan, scope)
        if len(s["tasks"]) > limit("max_batch_tasks") or minutes > cap:
            errs.append(f"{s['sid']} needs about {minutes} min of review ({len(s['tasks'])} tasks); one session is "
                        f"at most {cap} min and {limit('max_batch_tasks')} tasks — split the work into smaller "
                        "review_batches.")
    for tid in ids:
        if tid not in seen and not is_integration(by_id[tid], scope):
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
    return int(task.get("estimate_min", 5 if task.get("publish") else 0)) + (REVIEW_MINUTES if reviewer_for(task, scope) else 0)


def critical_path(tasks: Dict[str, Dict[str, Any]], scope: Dict[str, Any]) -> Tuple[int, List[str]]:
    best: Dict[str, Tuple[int, List[str]]] = {}

    def longest(tid: str) -> Tuple[int, List[str]]:
        if tid not in best:
            deps = [longest(d) for d in tasks[tid].get("depends_on", []) if d in tasks]
            length, path = max(deps, default=(0, []))
            best[tid] = (length + lane_minutes(tasks[tid], scope), path + [tid])
        return best[tid]

    return max((longest(t) for t in tasks), default=(0, []))


CATCH_ALLS = (".", "./", "**", "**/*")


def path_errors(tid: str, p: Any) -> List[str]:
    """Why a task path is not one the task can own: it leaves the workspace (or, for `wf:<path>`,
    the workflow folder), or it names all of it (`.` once swept .git objects into a hand-back;
    `**` once swept ~1000 node_modules files)."""
    rel = wf_rel(str(p))
    if rel is not None:
        rp = PurePosixPath(rel)
        if not rel.strip() or rp.is_absolute() or ".." in rp.parts or rel.strip() in CATCH_ALLS \
                or any(ch in rel for ch in "*?["):
            return [f"{tid}: path {p} must name one file inside the workflow folder (`wf:drafts/x.md`)."]
        return []
    pp = PurePosixPath(str(p))
    if pp.is_absolute() or ".." in pp.parts or not str(p).strip():
        return [f"{tid}: path {p} leaves the workspace; paths are relative to it."]
    if str(p).strip() in CATCH_ALLS:
        return [f"{tid}: path {p!r} names the whole workspace — list the files the task writes (a directory "
                "path like `pkg/` is fine when its files exist at plan time)."]
    return []


def _role_errors(tid: str, t: Dict[str, Any], kind: Optional[str]) -> List[str]:
    """A task's files must be ones its author is built to write. A transport agent (a liaison)
    moves approved content and owns only `wf:` files; a document author never owns source code."""
    agent, paths = t.get("agent"), [str(p) for p in t.get("paths", [])]
    roles = scopemod.roles()
    if t.get("publish"):
        return []
    errs = []
    if scopemod.is_transport(agent):
        repo = [p for p in paths if wf_rel(p) is None]
        if repo:
            errs.append(f"{tid}: {agent} transports approved content and never writes repository files "
                        f"({', '.join(repo)}): give it only `wf:` paths (a receipt or a dry-run payload).")
        if _DRAFTING.search(str(t.get("brief", ""))):
            errs.append(f"{tid}: {agent} is asked to write content itself. Content is a document: a doc-author task "
                        "writes it to `wf:drafts/<name>.md` (reviewed like any document), and a `publish` task posts "
                        "it (`tp publish`, after the human's OK) — `tp schema plan` shows both.")
    if agent in roles.get("no_code", []):
        code = [p for p in paths if wf_rel(p) is None and scopemod.is_code_file(p)]
        if code:
            errs.append(f"{tid}: {agent} owns source code ({', '.join(code)}) — a code change, comments included, "
                        "belongs to a code task (its author writes the tests first, then the implementation); split those files out.")
    return errs


def _publish_errors(tid: str, t: Dict[str, Any], tasks: Dict[str, Dict[str, Any]], before: Set[str],
                    kinds: Optional[str]) -> List[str]:
    pub = t.get("publish") or {}
    errs = []
    if kinds != "integration":
        errs.append(f"{tid}: a publish task serves an integration deliverable.")
    if pub.get("to") not in PUBLISH_TARGETS:
        errs.append(f"{tid}: publish.to must be one of {', '.join(PUBLISH_TARGETS)}.")
    if not str(pub.get("target", "")).strip():
        errs.append(f"{tid}: publish.target names the issue key or PR number (for jira-issue: the parent).")
    if pub.get("to") == "jira-issue":
        for key in ("project", "type"):
            if not str(pub.get(key, "")).strip():
                errs.append(f"{tid}: a jira-issue publish names its {key} (for example project KUB, type Task).")
        if not isinstance(pub.get("labels", []), list):
            errs.append(f"{tid}: publish.labels is a list of label names.")
    body = str(pub.get("body", ""))
    writers = [o for o in before if body in [str(p) for p in tasks[o].get("paths", [])]]
    if wf_rel(body) is None or not writers:
        errs.append(f"{tid}: publish.body {body or '(missing)'} must be a `wf:` file that a task {tid} depends on "
                    "writes (a doc-author task drafts it; the review checks it before it is posted).")
    return errs


def validate(plan: Dict[str, Any], scope: Dict[str, Any], state: Dict[str, Any], wf_root: Path,
             frozen: Set[str] = frozenset()) -> List[str]:
    """frozen: tasks an amendment leaves exactly as approved. Rules added since a run was approved
    (role fit, integration out of review) judge only what the amendment adds or changes; a frozen
    task cannot change, so refusing it would make the run impossible to amend."""
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
        errs.append(f"{len(tasks_list)} tasks; the limit is {limit('max_tasks')} — merge small related tasks "
                    f"(target {limit('target_task_minutes')} min each), or ask the human to split the work into "
                    "phases, each its own run. Never drop agreed work to fit.")
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
    scope_reqs = {r["id"] for r in scope.get("requirements", [])}
    cited_reqs: Set[str] = set()
    computable = True  # ids, dependencies, and estimates are sound enough for the graph checks
    all_ids = {x.get("id") for x in tasks_list}
    for t in tasks_list:
        tid = str(t.get("id", ""))
        if not re.fullmatch(r"T\d{2,3}", tid) or tid in tasks:
            errs.append(f"task id {tid!r} must be unique and look like T01.")
            computable = False
            continue
        tasks[tid] = t
        publish = t.get("publish")
        required = ("title", "workspace", "serves", "publish") if publish else \
            ("title", "agent", "workspace", "paths", "brief", "acceptance", "serves")
        for key in required:
            if not t.get(key):
                errs.append(f"{tid}: needs `{key}`.")
        unknown = [d for d in t.get("serves", []) if d not in deliverables]
        for d in unknown:
            errs.append(f"{tid}: serves unknown deliverable {d}.")
        served |= set(t.get("serves", []))
        cited_reqs |= set(t.get("requirements", []))
        kind = task_kind(t, scope)
        if t.get("serves") and not unknown and kind is None:
            errs.append(f"{tid}: every deliverable a task serves must be of one kind.")
        agent = None if publish else t.get("agent")
        if agent and kind and (agent not in authors or kind not in scopemod.agent_kinds(agent, "author")):
            errs.append(f"{tid}: agent {agent} is not a confirmed author for {kind} in scope.json.")
        ws = wss.get(t.get("workspace", ""))
        if ws is None:
            errs.append(f"{tid}: workspace {t.get('workspace')!r} is not in scope.json.")
        elif ws["mode"] != "write":
            errs.append(f"{tid}: workspace {ws['name']} is read-only; deliverables go in a write workspace.")
        for p in t.get("paths", []):
            errs += path_errors(tid, p)
        errs += [] if tid in frozen else _role_errors(tid, t, kind)
        if t.get("when", "after_review") not in WHEN:
            errs.append(f"{tid}: when must be after_review (integration waits for the final review) or anytime.")
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
        est = t.get("estimate_min", 5 if publish else None)
        if not isinstance(est, int) or est < 1:
            errs.append(f"{tid}: estimate_min must be a whole number of minutes.")
            computable = False
        elif est > limit("max_task_minutes"):
            errs.append(f"{tid}: estimate_min {est} exceeds {limit('max_task_minutes')} — split the task. Never lower "
                        "an honest estimate, or trim the work, to pass: estimates forecast, they never compress work.")
        for dep in t.get("depends_on", []):
            if dep not in all_ids:
                errs.append(f"{tid}: depends on unknown {dep}.")
                computable = False
        if kind == "code":
            if not t.get("test_cmd"):
                errs.append(f"{tid}: a code task needs `test_cmd` (tests first, observed red, then green).")
            if t.get("test_mode", "red") not in ("red", "pin", "existing"):
                errs.append(f"{tid}: test_mode must be red (new behaviour), pin (characterize current "
                            "behaviour), or existing (current tests already prove the criterion).")
            if t.get("test_mode") == "existing" and scope.get("split_tests"):
                errs.append(f"{tid}: test_mode 'existing' needs the fused build round (split_tests runs use "
                            "red or pin: a separate test author has nothing to write).")
        req_ids = t.get("requirements", [])
        if scope.get("requirements"):
            if not req_ids:
                errs.append(f"{tid}: cite the requirements it serves in `requirements` (R# ids from scope).")
            else:
                unknown = [r for r in req_ids if r not in scope_reqs]
                if unknown:
                    errs.append(f"{tid}: cites unknown requirements {', '.join(unknown)}.")
        if scope.get("review") in ("per-task", "both") and t.get("review") is not False:
            rev = reviewer_for(t, scope)
            if rev is None or rev not in scopemod.participants(scope, "reviewer"):
                errs.append(f"{tid}: no confirmed reviewer for {kind} tasks.")
        if t.get("model") not in (None, "sonnet", "opus", "haiku"):
            errs.append(f"{tid}: model must be sonnet, opus, or haiku (or omitted).")

    for d in sorted(deliverables - served):
        errs.append(f"{d} is served by no task.")
    for r in sorted(scope_reqs - cited_reqs):
        errs.append(f"{r} ({next(x['text'] for x in scope['requirements'] if x['id'] == r)}) is served by no task.")
    if not computable:
        return errs

    try:
        ancestors = _ancestors(tasks)
    except TPError as exc:
        return errs + exc.lines
    for tid, t in tasks.items():
        if t.get("publish") and tid not in frozen:
            errs += _publish_errors(tid, t, tasks, ancestors[tid], kinds=task_kind(t, scope))
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

    errs += _validate_batches(plan, scope, frozen)
    # The budget never refuses a plan: a plan that runs past it is shown that way in plan.md and
    # the human approves it knowingly. Small tasks come from the per-task size limits above, not
    # from cutting or merging work to fit a number.
    return errs


def _serial_chains(tasks: Dict[str, Dict[str, Any]], scope: Dict[str, Any]) -> List[Tuple[List[str], str]]:
    """Runs of three or more code tasks, each depending on the one before, that write the same
    file: each one starts a fresh test author and code author who re-read that file from scratch."""
    shared: Dict[Tuple[str, str], Set[str]] = {}
    for tid, t in tasks.items():
        for dep in t.get("depends_on", []):
            if dep in tasks and is_code(t, scope) and is_code(tasks[dep], scope):
                common = set(map(str, t.get("paths", []))) & set(map(str, tasks[dep].get("paths", [])))
                if common:
                    shared[(dep, tid)] = common
    nxt: Dict[str, List[str]] = {}
    for a, b in shared:
        nxt.setdefault(a, []).append(b)
    has_prev = {b for _, b in shared}
    chains = []
    for start in sorted(a for a in nxt if a not in has_prev):
        chain, files = [start], None
        while chain[-1] in nxt:
            step = sorted(nxt[chain[-1]])[0]
            files = shared[(chain[-1], step)] if files is None else files & shared[(chain[-1], step)]
            if not files:
                break
            chain.append(step)
        if len(chain) >= 3 and files:
            chains.append((chain, sorted(files)[0]))
    return chains


def warnings(plan: Dict[str, Any], scope: Optional[Dict[str, Any]] = None) -> List[str]:
    """What a plan check cannot refuse but the manager should know before the run hits it."""
    out = []
    for t in plan.get("tasks", []):
        for p in t.get("paths", []):
            name = PurePosixPath(str(p)).name
            if "report" in PurePosixPath(name).stem.lower():
                out.append(f"{t.get('id')} writes {name}: in a real run the harness refused a sub-agent creating a new "
                           "report-like file (seen with report.md) — prefer a name such as README.md or synthesis.md.")
    if scope is None:
        return out
    tasks = {t["id"]: t for t in plan.get("tasks", [])}
    for chain, f in _serial_chains(tasks, scope):
        out.append(f"{' → '.join(chain)} write {f} one after another: each code task starts a fresh test author and "
                   "code author who re-read it. Merge them where the merged work honestly fits one task "
                   f"({limit('max_task_minutes')} min or less); never squeeze work or estimates to make it fit.")
    span, path = critical_path(tasks, scope)
    total = sum(lane_minutes(t, scope) for t in tasks.values())
    if len(path) >= 3 and total and span >= 0.8 * total:
        out.append(f"critical path {' → '.join(path)} holds {span} of {total} task-minutes: little runs in parallel "
                   f"(3 lanes). Split the work along disjoint files so tasks can run side by side.")
    return out


def render(plan: Dict[str, Any], scope: Dict[str, Any], wf: Workflow) -> str:
    tasks = {t["id"]: t for t in plan["tasks"]}
    total = sum(lane_minutes(t, scope) for t in tasks.values())
    span, _ = critical_path(tasks, scope)
    lanes = limit("max_in_flight")
    sessions, tail = review_tail(plan, scope)
    estimate = max(span, math.ceil(total / lanes)) + tail
    budget = scope.get("budget_minutes")
    out = [f"# Plan — {plan['title']}", "", plan.get("summary", ""), "",
           f"**{len(tasks)} tasks** · about {estimate} min of execution on "
           f"{lanes} lanes · budget {budget or 'none'} · scope: `scope.md`", ""]
    if budget and estimate > budget:
        out += [f"The estimate runs {estimate - budget} min past the budget. That is reported, not a reason to "
                "cut or merge work: the plan carries the work the scope needs.", ""]
    if plan.get("conventions"):
        out += ["**Conventions every brief starts from** (frozen with the plan): "
                + ", ".join(f"`{c}`" for c in plan["conventions"]), ""]
    if sessions:
        names = [s["sid"] + (f" ({', '.join(s['lenses'])})" if s["lenses"] else "") for s in review_sessions(plan, scope)]
        out += [f"**Review:** {sessions} review session{'s' if sessions > 1 else ''} — {'; '.join(names)} — each over "
                "its whole batch. An all-code batch is reviewed once its code is accepted; any other batch once "
                f"every task is accepted and the code reviews are done (document review once the code reviews are done). Then at most {sessions} verification session{'s' if sessions > 1 else ''} scoped "
                f"to what they find (about {tail} min). Integration tasks run after the review.", ""]
    out += [
           "| Task | Title | Agent | Review | Est | After | Writes |", "|---|---|---|---|---|---|---|"]
    for t in tasks.values():
        rev = reviewer_for(t, scope) or "—"
        deps = ", ".join(t.get("depends_on", [])) or "—"
        if t.get("publish"):
            pub = t["publish"]
            writes = f"{pub['to']} {pub['target']} ← `{pub['body']}`"
            agent = "tp publish"
        else:
            writes = f"{t['workspace']}: " + ", ".join(f"`{p}`" for p in t["paths"])
            agent = t["agent"]
        out.append(f"| {t['id']} | {t['title']} | {agent} | {rev} | {t.get('estimate_min', 5)}m | {deps} | {writes} |")
    # The request, requirement by requirement, and the tasks that carry each: this is what the
    # plan review verifies and the report re-checks — coverage the reader can see, not just trust.
    if scope.get("requirements"):
        by_req: Dict[str, List[str]] = {}
        for t in tasks.values():
            for r in t.get("requirements", []):
                by_req.setdefault(r, []).append(t["id"])
        out += ["", "## Requirements coverage", "", "| Requirement | Tasks |", "|---|---|"]
        for r in scope["requirements"]:
            who = by_req.get(r["id"], [])
            out.append(f"| {r['id']} — {r['text']} | {', '.join(who) if who else '**none — plan check refuses**'} |")
    # The coverage the human verifies at approval: every deliverable, and the tasks that serve it.
    # A deliverable with no tasks is a plan check error; this matrix makes the fit readable,
    # not just machine-checked, so revisions happen before approval instead of after execution.
    by_deliverable: Dict[str, List[str]] = {}
    for t in tasks.values():
        for d in t.get("serves", []):
            by_deliverable.setdefault(d, []).append(t["id"])
    out += ["", "## Deliverable coverage", "", "| Deliverable | Tasks |", "|---|---|"]
    for d in scope.get("deliverables", []):
        who = by_deliverable.get(d["id"], [])
        out.append(f"| {d['id']} — {d.get('what', '')} | {', '.join(who) if who else '**none — plan check refuses**'} |")
    out += [""]
    out += ["", "## Tasks"]
    for t in tasks.values():
        out += ["", f"### {t['id']} — {t['title']} (serves {', '.join(t['serves'])})", "",
                t.get("brief") or f"The manager posts `{t['publish']['body']}` with `tp publish {t['id']}` after the "
                                  "human's OK.", ""]
        out += [f"- [ ] {a}" for a in t.get("acceptance", [])]
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
    pr = state.get("plan_review") or {}
    fixing = state["phase"] == "AWAITING_APPROVAL" and pr.get("status") == "changes"
    if state["phase"] != "PLANNING" and not fixing:
        raise TPError(f"Plans are checked in PLANNING; the workflow is {state['phase']}.")
    plan, scope = _checked(wf, state)
    wf.event("plan_check", tasks=len(plan["tasks"]))
    return "\n".join([f"WARN: {w}" for w in warnings(plan, scope)]
                     + [f"plan ok — {len(plan['tasks'])} tasks; rendered {wf.root / 'plan.md'}. Next: `tp plan submit`."])


def cmd_submit(wf: Workflow) -> str:
    state = wf.load()
    pr = state.get("plan_review")
    resubmit = state["phase"] == "AWAITING_APPROVAL" and pr and pr.get("status") == "changes"
    if state["phase"] != "PLANNING" and not resubmit:
        raise TPError(f"Only a PLANNING workflow can be submitted; it is {state['phase']}."
                     + (" A plan in review is resubmitted only after its findings are triaged." if
                        state["phase"] == "AWAITING_APPROVAL" else ""))
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
    if pr is None:  # a new run; a resumed legacy run keeps its human-approval contract
        pr = state["plan_review"] = {"round": 0, "status": "pending", "agent": None, "agent_id": None,
                                     "sha": None, "findings": [], "dismissed": {}, "observations": []}
    pr.update(status="pending", sha=None)  # re-bind on the next review dispatch
    wf.save(state)
    wf.event("plan_submit", planning_min=round(minutes_since(state["created"]), 1))
    out = [f"submitted — {len(plan['tasks'])} tasks, planning took {minutes_since(state['created']):.0f} min.",
           f"Plan: {wf.root / 'plan.md'}"]
    if plan.get("questions"):
        out += ["Questions the plan leaves open (the plan reviewer checks they are answered):"] \
               + [f"  - {q}" for q in plan["questions"]]
    noticed = wf.noticed_items()
    if noticed:
        out += ["Noticed, not in plan (the reviewer sees them):"] + [f"  - {n}" for n in noticed]
    out.append("Next: the independent plan review — `tp next` says exactly what to send (`tp plan review`). "
               "No human approval: the human still decides anything material you put to them, and can "
               "interject with `tp revise --feedback \"<their words>\"` at any time.")
    return "\n".join(out)


def cmd_approve(wf: Workflow, answer: str) -> str:
    from . import run  # baseline capture lives with execution

    state = wf.load()
    if state["phase"] != "AWAITING_APPROVAL":
        raise TPError(f"Nothing awaits approval: the workflow is {state['phase']} (submit the plan first).")
    pr = state.get("plan_review")
    if pr is not None:  # the new contract: an independent, current, passing plan review enters execution
        if pr.get("status") != "pass":
            raise TPError(f"the plan review is {pr.get('status') or 'not run'} — `tp plan review` starts it; "
                          "only a passing review enters execution.")
        if pr.get("sha") != state.get("plan_submitted_sha"):
            raise TPError("the plan changed after its review passed — submit it again and re-review "
                          "(`tp plan review`).")
        answer = answer or (f"independent plan review passed (round {pr['round']}, agent {pr.get('agent')}"
                            + (f", {len(pr.get('dismissed', {}))} finding(s) dismissed with reasons" if
                               pr.get("dismissed") else "") + ")")
    elif not answer:
        raise TPError("this workflow predates plan review — the human's approval is needed: "
                      "`tp approve --answer \"<their words>\"`.")
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
    from . import review  # end-of-pipeline review sessions and their diff baseline
    # A re-approval (after `tp revise`) keeps the baselines of the first: the review must still
    # diff against the HEAD the run started from, not one that already holds its own work.
    state["readonly_baseline"] = run.readonly_baseline(wf, scope, keep=state.get("readonly_baseline"))
    state["write_baseline"] = {**review.write_baseline(scope), **state.get("write_baseline", {})}
    state["reviews"] = review.new_reviews(plan, scope, state.get("reviews", {}))
    state["integration"] = review.integration_ids(plan, scope)
    wf.save(state)
    wf.decision("plan approve", answer, who=None if pr is not None else "human")
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
                        f"Reopen it (`tp resolve --task {tid} --action reopen --by human|manager --answer \"...\"`), "
                        "or ask the human about `tp revise`.")
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


def _remaining(plan: Dict[str, Any], scope: Dict[str, Any], state: Dict[str, Any]) -> Tuple[List[str], bool]:
    """The open work an amended plan leaves, against the budget's wall-clock minutes left: shown, not
    enforced — an amendment exists because the work outgrew the plan, and the human decides.
    Returns (lines, whether it runs past the budget)."""
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
        return [line + "."], False
    left = budget - minutes_since(state["created"])
    out = [f"{line}; the budget has {left:.0f} of {budget} min left, wall-clock."]
    if remaining > left:
        out.append("WARN: the remaining work runs past the budget — say so when you ask the human.")
    return out, remaining > left


SCOPE_AMEND_JSON = "scope-amend.json"


def _task_line(mark: str, t: Dict[str, Any]) -> str:
    if t.get("publish"):
        what = f"tp publish → {t['publish'].get('to')} {t['publish'].get('target')} from `{t['publish'].get('body')}`"
    else:
        what = f"{t.get('agent')}, {t.get('workspace')}: " + ", ".join(f"`{p}`" for p in t.get("paths", []))
    return f"  {mark} {t.get('id')} {t.get('title')} — {what}, {t.get('estimate_min', 5)} min"


def _change_lines(approved: Dict[str, Any], draft: Dict[str, Any]) -> List[str]:
    """The amendment as the human should see it in the one question: every task added or changed."""
    old = {t["id"]: t for t in approved["tasks"]}
    out = []
    for t in draft["tasks"]:
        if t.get("id") not in old:
            out.append(_task_line("+", t))
        elif old[t["id"]] != t:
            out.append(_task_line("~", t))
    new_ids = {t.get("id") for t in draft["tasks"]}
    out += [f"  - {tid} {old[tid].get('title')} (removed)" for tid in old if tid not in new_ids]
    return out


def _delegation_misfit(approved: Dict[str, Any], draft: Dict[str, Any], scope: Dict[str, Any],
                       state: Dict[str, Any], changes: List[str]) -> List[str]:
    """Why this amendment falls outside the human's standing fix-task delegation; [] when it fits.
    Inside it means only new tasks — none integration, each within the size the human set, within
    the count they allowed across the run. The time budget plays no part: it is an estimate,
    reported, and never a gate (nor a reason to shrink a task to fit)."""
    fx = scopemod.fix_tasks(scope)
    allow = int(fx.get("allow") or 0)
    if not allow:
        return ["the human allowed no fix tasks without asking: ask them"]
    out = [f"it {c}" for c in changes if not (c.startswith("added ") or c.startswith("review batches "))]
    old = {t["id"] for t in approved["tasks"]}
    added = [t for t in draft["tasks"] if t.get("id") not in old]
    for t in added:
        if is_integration(t, scope):
            out.append(f"{t['id']} writes to an external system, which the human always approves")
        if int(t.get("estimate_min", 0)) > int(fx.get("max_minutes", 0)):
            out.append(f"{t['id']} is {t.get('estimate_min')} min; the human allowed fix tasks of {fx.get('max_minutes')} "
                       "min or less")
    used = len(state.get("delegated", []))
    if used + len(added) > allow:
        out.append(f"the human allowed {allow} fix task{'s' if allow != 1 else ''}; {used} used, and this adds "
                   f"{len(added)}")
    return out


def _apply_amendment(wf: Workflow, state: Dict[str, Any], draft: Dict[str, Any], scope: Dict[str, Any],
                     changes: List[str], record: Dict[str, Any]) -> None:
    """Make plan-amend.json the approved plan and bring the run's state in line with it."""
    from . import review, run
    draft_path = wf.root / AMEND_JSON
    shutil.copyfile(draft_path, wf.plan_json)
    draft_path.replace(wf.meta / f"plan-amend-{len(state.get('amendments', [])) + 1}.json")
    (wf.root / "plan-amend.md").unlink(missing_ok=True)
    state.pop("amend_checked", None)
    state["plan_approved_sha"] = state["plan_submitted_sha"] = sha_file(wf.plan_json)
    state["conventions_sha"] = conventions_shas(draft, scope, wf.root)
    ids = [t["id"] for t in draft["tasks"]]
    for tid in [t for t in state["tasks"] if t not in ids]:
        del state["tasks"][tid]
    for tid in ids:
        state["tasks"].setdefault(tid, run.new_task_state())
    state["reviews"] = review.new_reviews(draft, scope, state.get("reviews", {}))
    state["integration"] = review.integration_ids(draft, scope)
    state.setdefault("amendments", []).append(dict({"ts": now_iso(), "changes": changes}, **record))
    (wf.root / "plan.md").write_text(render(draft, scope, wf))


def _amend_scope(wf: Workflow) -> Tuple[Dict[str, Any], bool]:
    """The scope a plan amendment is judged against: a pending scope amendment's draft, when there
    is one (the two are approved together), else the confirmed scope."""
    pending = wf.root / SCOPE_AMEND_JSON
    if pending.exists():
        data = load_json(pending, "the amended scope")
        if isinstance(data, dict):
            return data, True
    return scopemod.load_scope(wf), False


def _checked_draft(wf: Workflow, state: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any],
                                                                 List[str], Set[str]]:
    """(approved, draft, scope, changes, frozen) for a plan-amend.json that validates."""
    approved = load_plan(wf)
    scope, _ = _amend_scope(wf)
    draft_path = wf.root / AMEND_JSON
    draft = load_json(draft_path, "the amended plan")
    if not isinstance(draft, dict) or not isinstance(draft.get("tasks"), list):
        raise TPError(f"{draft_path} must be a JSON object with a `tasks` list.")
    new = {t.get("id"): t for t in draft["tasks"]}
    frozen = {t["id"] for t in approved["tasks"] if new.get(t["id"]) == t}
    errs = validate(draft, scope, state, wf.root, frozen)
    changes, refusals = _amendment(approved, draft, scope, state, wf.root)
    if errs or refusals:
        raise TPError(*(errs + refusals))
    return approved, draft, scope, changes, frozen


def cmd_amend(wf: Workflow, answer: Optional[str], delegated: bool = False, note: Optional[str] = None) -> str:
    """Change the approved plan mid-run: add tasks, or change or remove tasks not yet dispatched.
    The draft lives in plan-amend.json, so plan.json stays the contract — and agents in flight can
    still be recorded — until it is approved. Draft first, then check it (`tp plan amend`), which
    renders the one question to put to the human; their answer approves exactly the checked draft.
    Inside the human's standing fix-task delegation (scope `fix_tasks`), `--delegated --note`
    applies it without a question, recorded as the manager's."""
    with wf.locked():
        state = wf.load()
        if state["phase"] != "EXECUTING":
            raise TPError(f"amend changes a plan mid-run; the workflow is {state['phase']}.")
        if sha_file(wf.plan_json) != state.get("plan_approved_sha"):
            raise TPError("plan.json changed after approval — restore it; an amendment goes in plan-amend.json.")
        draft_path = wf.root / AMEND_JSON
        if not draft_path.exists():
            shutil.copyfile(wf.plan_json, draft_path)
            return (f"Draft started: {draft_path}, a copy of the approved plan. Add tasks, or change or remove tasks "
                    "not yet dispatched (new work needs a review batch whose review has not started). To change "
                    "conventions, write them to a new file and point `conventions` at it: the frozen file stays "
                    "as it is until the human agrees. Then `tp plan amend` to check it — before you ask anything.")
        approved, draft, scope, changes, _ = _checked_draft(wf, state)
        if not changes:
            return f"{draft_path.name} changes nothing yet."
        remaining, _ = _remaining(draft, scope, state)
        _, scope_pending = _amend_scope(wf)
        misfit = _delegation_misfit(approved, draft, scope, state, changes)
        if scope_pending:
            misfit = misfit + ["a scope amendment is pending: the human approves both together"]
        if answer is None and not delegated:
            (wf.root / "plan-amend.md").write_text(render(draft, scope, wf))
            state["amend_checked"] = {"sha": sha_file(draft_path), "ts": now_iso()}
            wf.save(state)
            allow = int(scopemod.fix_tasks(scope).get("allow") or 0)
            if scope_pending:
                tail = [f"A scope amendment is pending: `tp scope amend` checks both, and the human's one answer "
                        "approves both (`tp scope amend --answer`)."]
            else:
                tail = [f"Ask the human once, showing this change (full plan: {wf.root / 'plan-amend.md'}); their "
                        "answer approves it — do not ask again: `tp plan amend --answer \"<their words>\"`. If the "
                        "human already chose this exact change in answer to a question that showed it (a closeout, "
                        "a blocked task), pass those words; do not ask twice. A change to plan-amend.json after this "
                        "check needs a new check and a new answer."]
                if allow and not misfit:
                    used = len(state.get("delegated", []))
                    tail.append(f"Or, inside the human's standing delegation ({used} of {allow} fix tasks used): "
                                "`tp plan amend --delegated --note \"<what is wrong and why it needs fixing>\"` — no "
                                "question; the report lists it.")
                elif allow:
                    tail.append("This is not within the standing delegation: " + "; ".join(misfit) + ".")
            return "\n".join([f"amendment ok — {'; '.join(changes)}:"] + _change_lines(approved, draft) + remaining
                             + tail)
        checked = state.get("amend_checked") or {}
        if checked.get("sha") != sha_file(draft_path):
            raise TPError("plan-amend.json changed since its check, or was never checked: run `tp plan amend`, show the "
                          "human what it prints, and ask again — an answer approves only the draft it was shown."
                          if checked else "plan-amend.json was never checked: run `tp plan amend` first, then ask the "
                          "human about what it prints.")
        if delegated:
            if misfit:
                raise TPError("Not within the human's standing fix-task delegation: " + "; ".join(misfit) + ".",
                              "Ask the human (one question, showing this change), then `tp plan amend --answer "
                              "\"<their words>\"` — never shrink an estimate or split the work to make it fit.")
            if not note or words(note) < 4:
                raise TPError("--delegated needs --note: what is wrong and why it needs fixing, in plain words (the "
                              "report shows it to the human).")
            added = [t["id"] for t in draft["tasks"] if t["id"] not in {a["id"] for a in approved["tasks"]}]
            state["delegated"] = list(state.get("delegated", [])) + added
            allow = int(scopemod.fix_tasks(scope).get("allow") or 0)
            label = f"plan amend (fix-task delegation, {len(state['delegated'])} of {allow})"
            _apply_amendment(wf, state, draft, scope, changes, {"delegated": True, "note": " ".join(note.split()),
                                                                "tasks": added})
            wf.save(state)
            wf.decision(label, note, who="manager")
            wf.event("plan_amend", changes=changes, delegated=True)
            return "\n".join([f"amended under the standing delegation — {'; '.join(changes)}."] + remaining
                             + ["`tp next`."])
        if scope_pending:
            raise TPError("A scope amendment is pending: apply both with one answer — `tp scope amend` checks them "
                          "together, then `tp scope amend --answer \"<their words>\"`.")
        _apply_amendment(wf, state, draft, scope, changes, {"answer": answer})
        wf.save(state)
        wf.decision("plan amend", str(answer))
        wf.event("plan_amend", changes=changes)
        return "\n".join([f"amended — {'; '.join(changes)}."] + remaining + ["`tp next`."])


def _scope_diff(old: Dict[str, Any], new: Dict[str, Any]) -> List[str]:
    """A scope change as the human should see it in the one question."""
    out = []
    for key, label in (("deliverables", "deliverable"), ("workspaces", "workspace")):
        ident = "id" if key == "deliverables" else "name"
        before = {x.get(ident): x for x in old.get(key, []) if isinstance(x, dict)}
        after = {x.get(ident): x for x in new.get(key, []) if isinstance(x, dict)}
        for k, v in after.items():
            desc = v.get("what") if key == "deliverables" else f"{v.get('path')} ({v.get('mode')})"
            if k not in before:
                out.append(f"  + {label} {k}: {desc}")
            elif before[k] != v:
                out.append(f"  ~ {label} {k}: {desc}")
        out += [f"  - {label} {k}" for k in before if k not in after]
    before = {(p.get("agent"), p.get("role")) for p in old.get("participants", [])}
    after = {(p.get("agent"), p.get("role")) for p in new.get("participants", [])}
    out += [f"  + participant {a} ({r})" for a, r in sorted(after - before)]
    out += [f"  - participant {a} ({r})" for a, r in sorted(before - after)]
    for key in ("non_goals", "terms"):
        before_items = [json.dumps(x) if not isinstance(x, str) else x for x in old.get(key) or []]
        after_items = [json.dumps(x) if not isinstance(x, str) else x for x in new.get(key) or []]
        out += [f"  + {key}: {x}" for x in after_items if x not in before_items]
        out += [f"  - {key}: {x}" for x in before_items if x not in after_items]
    # limits and ignore change what the gates enforce, so the human sees them like any other field.
    for key in ("title", "output", "review", "budget_minutes", "research", "fix_tasks", "limits", "ignore"):
        if old.get(key) != new.get(key):
            out.append(f"  ~ {key}: {json.dumps(new.get(key))[:300]}")
    return out


# What the human agreed to at scope time, verbatim: an amendment that touches any of it is
# theirs to approve, never the manager's to settle alone. Budgets are deliberately absent —
# they are the manager's own reporting metadata (tp budget extend / research extend change
# them without a question already). Gate-ignore patterns are handled separately below: adding
# one only stops a false positive (the harness's own artefacts, gitignored build noise) and is
# plumbing; removing one stops the gates watching something, and is the human's.
_DELEGATION_FROZEN = ("title", "output", "requirements", "terms", "non_goals", "ship", "answers",
                      "limits", "fix_tasks", "review", "workspaces")


def _scope_delegation_misfit(old: Dict[str, Any], new: Dict[str, Any]) -> List[str]:
    """Why this scope amendment is the human's to approve; [] when it is plumbing the manager may
    settle alone. Mechanical rule: nothing they agreed changes (the requirement ledger, non-goals,
    terms, workspaces, shipping, their answers, what the gates enforce, the review mode, the
    fix-task allowance, title, output), the deliverable set is fixed — each one's description,
    kind, or destination may be refined, and the frozen requirements still map onto the same ids —
    no agent gains write authority (an author or tests role), and gate-ignore patterns are only
    ever added, never removed. Covers the shapes real runs hit: a routing fix (a liaison
    transports, a document author drafts), a detail in-budget research discovered (the dependent
    ticket's id), and build noise the fence misread as task work (an added ignore pattern)."""
    labels = {"title": "the title", "output": "the output summary", "requirements": "the requirement ledger",
              "terms": "the significant terms", "non_goals": "the non-goals", "ship": "shipping",
              "answers": "the human's recorded answers", "limits": "what the gates enforce (limits)",
              "ignore": "what the gates ignore", "fix_tasks": "the fix-task allowance",
              "review": "the review mode", "workspaces": "the workspaces"}
    out = []
    changed = [labels[k] for k in _DELEGATION_FROZEN if old.get(k) != new.get(k)]
    if changed:
        out.append("it changes " + ", ".join(changed))
    old_ig = {str(p) for p in old.get("ignore") or []}
    new_ig = {str(p) for p in new.get("ignore") or []}
    if old_ig != new_ig and not new_ig >= old_ig:
        out.append("it removes gate-ignore patterns — what the gates stop watching is the human's call")
    ids = lambda s: {d.get("id") for d in s.get("deliverables", []) if isinstance(d, dict)}
    if ids(old) != ids(new):
        out.append("the deliverable set changes — work is added or dropped")
    before = {(p.get("agent"), scopemod.role_of(p)) for p in old.get("participants", []) if isinstance(p, dict)}
    after = {(p.get("agent"), scopemod.role_of(p)) for p in new.get("participants", []) if isinstance(p, dict)}
    gained = [f"{a} as {r}" for a, r in sorted(after - before) if r in ("author", "tests")]
    if gained:
        out.append("it grants write authority (" + ", ".join(gained) + ")")
    return out


def merge_baselines(wf: Workflow, state: Dict[str, Any], scope: Dict[str, Any]) -> None:
    """Baselines for workspaces a scope change adds; existing ones keep their original values, so
    the review still diffs against the HEAD recorded at the first approval."""
    from . import review, run
    names = scopemod.workspaces(scope)
    state["readonly_baseline"] = {k: v for k, v in run.readonly_baseline(wf, scope, keep=state.get("readonly_baseline"))
                                  .items() if k in names and names[k]["mode"] == "read"}
    state["write_baseline"] = {k: v for k, v in {**review.write_baseline(scope), **state.get("write_baseline", {})}
                               .items() if k in names and names[k]["mode"] == "write"}


def cmd_scope_amend(wf: Workflow, answer: Optional[str], delegated: bool = False,
                    note: Optional[str] = None) -> str:
    """Change the confirmed scope mid-run: draft scope-amend.json, check it here (with the plan
    amendment it needs, if any, in plan-amend.json), then either ask the human once — their one
    answer applies both — or, when the check itself proves the change is plumbing (nothing the
    human agreed changes, no write authority gained), settle it with --delegated --note, recorded
    as the manager's and listed in the report. The run stays where it is."""
    from . import review
    with wf.locked():
        state = wf.load()
        if state["phase"] not in ("PLANNING", "EXECUTING"):
            raise TPError(f"scope amend applies once the scope is confirmed (PLANNING or EXECUTING); the workflow is "
                          f"{state['phase']} — edit scope.json and `tp scope check`.")
        draft_path = wf.root / SCOPE_AMEND_JSON
        if not draft_path.exists():
            shutil.copyfile(wf.scope_json, draft_path)
            return (f"Draft started: {draft_path}, a copy of the confirmed scope. Edit it; if the plan must change "
                    "too (a new deliverable needs its task), draft that with `tp plan amend`. Then `tp scope amend` "
                    "checks both — before you ask anything.")
        old = scopemod.load_scope(wf)
        draft = load_json(draft_path, "the amended scope")
        if not isinstance(draft, dict):
            raise TPError(f"{draft_path} must hold a JSON object.")
        errs = scopemod.validate(draft, require_fix_tasks="fix_tasks" in old)
        plan_draft = None
        executing = state["phase"] == "EXECUTING"
        if executing and not errs:
            if (wf.root / AMEND_JSON).exists():
                approved, plan_draft, _, plan_changes, _ = _checked_draft(wf, state)
            else:
                approved = load_plan(wf)
                plan_errs = validate(approved, draft, state, wf.root, {t["id"] for t in approved["tasks"]})
                if plan_errs:
                    errs += plan_errs + ["The approved plan does not fit this scope: draft the plan amendment it "
                                         "needs (`tp plan amend`), then `tp scope amend` checks both together."]
        if errs:
            raise TPError(*errs)
        diff = _scope_diff(old, draft)
        if not diff and plan_draft is None:
            return f"{draft_path.name} changes nothing yet."
        misfit = _scope_delegation_misfit(old, draft)
        if plan_draft is not None:
            misfit += _delegation_misfit(approved, plan_draft, draft, state, plan_changes)
        cap = limit("max_delegated_scope_amends")
        used = len([a for a in state.get("scope_amendments", []) if a.get("delegated")])
        if used >= cap:
            misfit.append(f"the run already settled {used} scope amendment"
                          f"{'s' if used != 1 else ''} without a question (the cap is {cap}) — this one goes to the "
                          "human")
        plan_sha = sha_file(wf.root / AMEND_JSON) if plan_draft is not None else None
        if answer is None and not delegated:
            (wf.root / "scope-amend.md").write_text(scopemod.render(draft))
            state["scope_amend_checked"] = {"sha": sha_file(draft_path), "plan_sha": plan_sha, "ts": now_iso()}
            wf.save(state)
            out = ["scope amendment ok:"] + diff
            if plan_draft is not None:
                remaining, _ = _remaining(plan_draft, draft, state)
                out += [f"with the plan amendment — {'; '.join(plan_changes)}:"] + _change_lines(approved, plan_draft)
                out += remaining
            if misfit:
                out.append(f"Ask the human once, showing this change (full scope: {wf.root / 'scope-amend.md'}); "
                           "their answer approves the scope"
                           + (" and the plan amendment together" if plan_draft is not None else "")
                           + " — do not ask again: `tp scope amend --answer \"<their words>\"`. A change to either "
                           "draft after this check needs a new check and a new answer.")
            else:
                out.append("This is plumbing — no requirement, non-goal, term, workspace, shipping, or "
                           "gate-enforcement change, no write authority gained, and any gate-ignore patterns "
                           "only added — so settle it yourself: `tp scope amend --delegated --note "
                           f"\"<what changed and why, in plain words>\"` ({used} of {cap} used; recorded as yours, "
                           "listed in the report). Or ask once with `--answer` — the human always overrules.")
            return "\n".join(out)
        checked = state.get("scope_amend_checked") or {}
        if checked.get("sha") != sha_file(draft_path) or checked.get("plan_sha") != plan_sha:
            raise TPError("scope-amend.json (or plan-amend.json) changed since the check, or was never checked: run "
                          "`tp scope amend`, show the human what it prints, and ask again — an answer approves only "
                          "the change it was shown."
                          if not delegated else
                          "scope-amend.json (or plan-amend.json) changed since its check, or was never checked: run "
                          "`tp scope amend` and read what it prints before settling anything.")
        if delegated and answer:
            raise TPError("pass either --answer (the human's words) or --delegated (settle it yourself), not both.")
        if delegated:
            if misfit:
                raise TPError("Not plumbing the manager may settle: " + "; ".join(misfit) + ".",
                              "Ask the human once, showing what `tp scope amend` printed, then "
                              "`tp scope amend --answer \"<their words>\"`.")
            if not note or words(note) < 4:
                raise TPError("--delegated needs --note: what changed and why, in plain words (the report shows it "
                              "to the human).")
        wf.scope_json.write_text(json.dumps(draft, indent=2) + "\n")
        (wf.root / "scope.md").write_text(scopemod.render(draft))
        n = len([p for p in wf.meta.glob("scope-amend-*.json")]) + 1
        draft_path.replace(wf.meta / f"scope-amend-{n}.json")
        (wf.root / "scope-amend.md").unlink(missing_ok=True)
        state.pop("scope_amend_checked", None)
        state["scope_sha"] = state["scope_checked_sha"] = sha_file(wf.scope_json)
        state["budget_minutes"] = draft.get("budget_minutes")
        allow = 0
        if executing:
            merge_baselines(wf, state, draft)
            if plan_draft is not None:
                if delegated:
                    # The plan side rides along only inside the standing fix-task delegation, which
                    # _delegation_misfit already proved (misfit is empty here).
                    added = [t["id"] for t in plan_draft["tasks"]
                             if t["id"] not in {a["id"] for a in approved["tasks"]}]
                    state["delegated"] = list(state.get("delegated", [])) + added
                    allow = int(scopemod.fix_tasks(draft).get("allow") or 0)
                    _apply_amendment(wf, state, plan_draft, draft, plan_changes,
                                     {"delegated": True, "note": " ".join(note.split()), "tasks": added,
                                      "with_scope": True})
                else:
                    _apply_amendment(wf, state, plan_draft, draft, plan_changes, {"answer": answer, "with_scope": True})
            else:
                plan = load_plan(wf)
                state["reviews"] = review.new_reviews(plan, draft, state.get("reviews", {}))
                state["integration"] = review.integration_ids(plan, draft)
                (wf.root / "plan.md").write_text(render(plan, draft, wf))
        state.setdefault("scope_amendments", []).append(
            {"ts": now_iso(), "changes": diff, "delegated": bool(delegated), "note": " ".join((note or "").split())})
        wf.save(state)
        if delegated:
            wf.decision("scope amend (manager-settled plumbing)", note, who="manager")
        else:
            wf.decision("scope amend", str(answer))
        if plan_draft is not None:
            if delegated:
                wf.decision(f"plan amend (fix-task delegation, {len(state['delegated'])} of {allow})", note,
                            who="manager")
            else:
                wf.decision("plan amend (approved with the scope amendment)", str(answer))
        wf.event("scope_amend", changes=diff, plan=plan_draft is not None, delegated=bool(delegated))
        head = "scope amended" + (" — plumbing settled by the manager" if delegated else "") + ":"
        return "\n".join([head] + diff + (["and the plan amendment applied."] if plan_draft else []) + ["`tp next`."])


def cmd_widen(wf: Workflow, tid: str, paths: List[str], reason: str, answer: Optional[str] = None) -> str:
    """Add a file the same deliverable needs to one task's write set while EXECUTING — the one
    mechanical correction a fix round needs when a finding lands just outside the task's paths,
    which would otherwise loop on 'changed files outside this task's paths' until the task blocks.
    Allowed on accepted tasks; the task's deliverable, brief, and acceptance stay frozen. Single
    files only, and at most max_widen_paths per task on the manager's say-so: past that the work
    is growing, and that is the human's call (answer)."""
    with wf.locked():
        state = wf.load()
        if state["phase"] != "EXECUTING":
            raise TPError(f"widen applies while EXECUTING; the workflow is {state['phase']}.")
        if sha_file(wf.plan_json) != state.get("plan_approved_sha"):
            raise TPError("plan.json changed after approval — restore it first.")
        plan, scope = load_plan(wf), scopemod.load_scope(wf)
        task = next((t for t in plan["tasks"] if t["id"] == tid), None)
        if task is None or tid not in state["tasks"]:
            raise TPError(f"{tid} is not a task in the approved plan.")
        if task.get("publish"):
            raise TPError(f"{tid} is a publish task: it writes no files.")
        added = [p for p in dict.fromkeys(str(p).strip() for p in paths) if p and p not in task["paths"]]
        if not added:
            raise TPError("no new paths: every path is already in the task's write set.")
        ws = Path(scopemod.workspaces(scope)[task["workspace"]]["path"])
        errs = [e for p in added for e in path_errors(tid, p)]
        errs += [f"{p}: widen adds one file at a time — not a folder or a glob (a wider change is a plan "
                 "amendment for the human)." for p in added
                 if p.endswith("/") or any(ch in p for ch in "*?[") or (ws / p).is_dir()]
        widened = state["tasks"][tid].get("widened", [])
        cap = limit("max_widen_paths")
        if not answer and len(widened) + len(added) > cap:
            errs.append(f"{tid} already has {len(widened)} widened file(s); the manager may add {cap} per task. Past "
                        "that the work is growing — ask the human, then repeat with --answer \"<their words>\". Only "
                        "files the same deliverable needs; changing what a task delivers is a plan amendment.")
        # Finished tasks count too: plan checks refuse unordered overlaps whatever their status, so
        # one here would refuse every later amendment. A finding about another task's file belongs
        # to that task.
        ancestors = _ancestors({t["id"]: t for t in plan["tasks"]})
        unordered = [o for o in plan["tasks"] if o["id"] != tid and o["workspace"] == task["workspace"]
                     and o["id"] not in ancestors[tid] and tid not in ancestors[o["id"]]]
        clashes = [(o, p, q) for o in unordered for p in added for q in o.get("paths", []) if paths_overlap(p, q)]
        # A finished owner is ordered before this task instead: its work is done, so the overlap is
        # this task building on it (which the plan checks accept once the two are ordered).
        done = {"accepted", "skipped"}
        after = sorted({o["id"] for o, _, _ in clashes if state["tasks"].get(o["id"], {}).get("status") in done})
        errs += [f"{p} overlaps {o['id']}'s {q}, and the two tasks are not ordered — route the finding to "
                 f"{o['id']} (reopen it) or amend the plan." for o, p, q in clashes if o["id"] not in after]
        if errs:
            raise TPError(*errs)
        if after:
            task["depends_on"] = list(dict.fromkeys(list(task.get("depends_on", [])) + after))
        task["paths"] = task["paths"] + added
        wf.plan_json.write_text(json.dumps(plan, indent=2) + "\n")
        draft = wf.root / AMEND_JSON
        if draft.exists():  # an open amendment draft copied the old paths: keep it in step
            data = load_json(draft, "the amended plan")
            for t in data.get("tasks", []):
                if t.get("id") == tid:
                    t["paths"] = list(dict.fromkeys(list(t.get("paths", [])) + added))
                    t["depends_on"] = list(dict.fromkeys(list(t.get("depends_on", [])) + after))
            draft.write_text(json.dumps(data, indent=2) + "\n")
        state["plan_approved_sha"] = state["plan_submitted_sha"] = sha_file(wf.plan_json)
        state["tasks"][tid]["widened"] = widened + added
        wf.save(state)
        (wf.root / "plan.md").write_text(render(plan, scope, wf))
        wf.decision(f"widen {tid} paths", f"{', '.join(added)} — {reason}" + (f" — {answer}" if answer else "")
                    + (f" (now after {', '.join(after)}, which already owns it and is finished)" if after else ""),
                    who="human" if answer else "manager")
        wf.event("widen", id=tid, paths=added, reason=reason)
        return (f"widen {tid}: + {', '.join(added)}. The write set grew in plan.json and plan.md; the reason is in "
                "decisions.md. `tp next`.")


def cmd_revise(wf: Workflow, feedback: str, to_scope: bool) -> str:
    state = wf.load()
    if state["phase"] == "DONE":
        raise TPError("The workflow is DONE; start a new one for new work.")
    if state.get("in_flight"):
        raise TPError(f"agents in flight: {', '.join(state['in_flight'])} — record them first.")
    if to_scope and state["phase"] == "EXECUTING":
        # If the confirmed scope still fits this exact plan, its approval stands (scope confirm).
        state["revised_from"] = {"plan_sha": state.get("plan_approved_sha"), "ts": now_iso()}
    state["phase"] = "SCOPING" if to_scope else "PLANNING"
    for key in ("plan_submitted_sha", "plan_approved_sha"):
        state.pop(key, None)
    pr = state.get("plan_review")
    if pr is not None:
        # A revision restarts the review contract: the new plan gets the full round allowance
        # again (a round counter that survived the revise would dead-end the next review at
        # the cap). The reviewer stays attached — its context of the old plan is useful.
        pr.update(round=0, status="pending", sha=None, findings=[], dismissed={}, observations=[])
    wf.save(state)
    wf.decision("revise scope" if to_scope else "revise plan", feedback)
    wf.event("revise", scope=to_scope)
    if to_scope:
        return "back to SCOPING — edit scope.json, `tp scope check`, and have the human confirm it again."
    return ("back to PLANNING — edit plan.json from the feedback, `tp plan check`, `tp plan submit`. "
            "Accepted tasks stay accepted.")

# --- independent plan review -----------------------------------------------------------------

def _plan_reviewer(scope: Dict[str, Any]) -> str:
    who = [a for a in scopemod.participants(scope, "plan")]
    if not who:
        raise TPError("no plan-role participant in scope.json — the independent plan reviewer "
                      "(plan-reviewer) must be confirmed with the scope.")
    return who[0]


def _finding_line(f: Dict[str, Any]) -> str:
    """A finding the way a reader needs it — not a raw dict the reviewer's JSON produced."""
    return (f"{f.get('id', '?')} ({f.get('state', '?')}) {f.get('requirement', '?')}: {f.get('issue', '')}"
            + (f" Fix: {f['fix']}" if f.get("fix") else ""))


def cmd_plan_review(wf: Workflow) -> str:
    """Dispatch the independent plan review: one read-only reviewer gets the request, the scope,
    and the plan bound to this exact revision. The manager never reviews its own plan."""
    from . import briefs
    state = wf.load()
    if state["phase"] != "AWAITING_APPROVAL":
        raise TPError(f"the plan review runs after submit; the workflow is {state['phase']}.")
    pr = state.get("plan_review")
    if pr is None:
        raise TPError("this workflow predates plan review — the human approves it: "
                      "`tp approve --answer \"<their words>\"`.")
    if pr["status"] == "in_flight":
        raise TPError(f"round {pr['round']} is in flight — record it: `tp plan record --agent-id <its id>`.")
    if pr["status"] == "pass":
        raise TPError(f"round {pr['round']} already passed — `tp approve` enters execution.")
    if pr["status"] == "needs_triage":
        raise TPError(f"round {pr['round']} has findings to triage first: `tp plan triage`.")
    if pr["round"] >= limit("max_review_rounds"):
        raise TPError(f"the plan has failed {pr['round']} independent review rounds. Put it to the human: "
                      "`tp revise --feedback \"<their words>\"` restarts planning with their input.")
    plan, scope = _checked(wf, state)  # the plan under review must itself be clean
    pr["round"] += 1
    rnd = pr["round"]
    if pr["status"] == "pending" or not pr.get("agent"):
        pr["agent"] = _plan_reviewer(scope)
    run = wf.root / "runs" / "plan"
    run.mkdir(parents=True, exist_ok=True)
    brief, result = run / f"brief-review-{rnd}.md", run / f"result-review-{rnd}.json"
    if result.exists():
        result.unlink()
    reqs = [{"id": r["id"], "text": r["text"], "deliverables": r["deliverables"]}
            for r in scope.get("requirements", [])]
    ctx = {"plan_md": wf.root / "plan.md", "plan_json": wf.plan_json, "scope_md": wf.root / "scope.md",
           "request": (wf.root / "request.md").read_text(errors="replace") if (wf.root / "request.md").exists() else "",
           "requirements": reqs, "questions": plan.get("questions", []),
           "noticed": [str(n) for n in wf.noticed_items()],
           "prior_findings": [_finding_line(f) for f in pr.get("findings", [])] if rnd > 1 else []}
    brief.write_text(briefs.plan_review(rnd, ctx, result))
    pr.update(status="in_flight", sha=state.get("plan_submitted_sha"), findings=[], dismissed={})
    wf.save(state)
    wf.event("plan_review", round=rnd, agent=pr["agent"])
    call = briefs.dispatch_line(pr["agent"], f"plan review {rnd}",
                                briefs.prompt(brief, result), pr.get("agent_id"), None)
    return (f"PLAN REVIEW · round {rnd} · {pr['agent']}\nbrief: {brief}\nsend: {call}\n"
            f"then, when it replies: tp plan record --agent-id <its agent id>")


def cmd_plan_record(wf: Workflow, agent_id: Optional[str]) -> str:
    """Validate the reviewer's hand-back: verdict, grounded findings, and one coverage entry per
    scope requirement. Uncovered requirements and unresolved issues become findings themselves;
    `pass` requires every requirement covered and nothing unresolved."""
    state = wf.load()
    if state["phase"] != "AWAITING_APPROVAL":
        raise TPError(f"the workflow is {state['phase']}; a plan review records while the plan awaits review.")
    pr = state.get("plan_review")
    if not pr or pr["status"] != "in_flight":
        raise TPError(f"no plan review round is in flight (status {pr and pr.get('status')}).")
    rnd = pr["round"]
    result = wf.root / "runs" / "plan" / f"result-review-{rnd}.json"
    if not result.exists():
        raise TPError(f"{result} is missing — the reviewer must write it before you record. Resume its "
                      "`task` call and ask it to write the file.")
    if agent_id:
        pr["agent_id"] = agent_id
    data = load_json(result, "the plan review")
    scope = scopemod.load_scope(wf)
    errs: List[str] = []
    if not isinstance(data, dict):
        raise TPError("the plan review result must be a JSON object.")
    if data.get("review") != "plan" or data.get("round") != rnd:
        errs.append(f"result must say review 'plan' and round {rnd}.")
    if data.get("verdict") not in ("pass", "changes"):
        errs.append("verdict must be pass or changes.")
    findings = data.get("findings")
    if not isinstance(findings, list):
        errs.append("findings must be a list.")
    seen_ids: Set[str] = set()
    for f in findings or []:
        if not isinstance(f, dict):
            errs.append("each finding must be a JSON object.")
            continue
        fid = str(f.get("id", "")).strip()
        if not fid:
            errs.append("each finding needs an `id` (F1, F2, ...).")
        elif fid in seen_ids:
            errs.append(f"finding ids must be unique: {fid} appears twice.")
        else:
            seen_ids.add(fid)
        if not str(f.get("requirement", "")).strip():
            errs.append(f"{fid or '(unnamed)'}: each finding names the requirement (R#) or request line "
                        "it is about.")
        if not str(f.get("issue", "")).strip():
            errs.append(f"{fid or '(unnamed)'}: each finding needs a complete `issue` sentence.")
    if data.get("verdict") == "changes" and isinstance(findings, list) and not findings:
        errs.append("verdict 'changes' must name at least one finding — the reviewer's reason for "
                     "refusing the plan is exactly what triage needs.")
    req_ids = [r["id"] for r in scope.get("requirements", [])]
    coverage = data.get("coverage")
    if req_ids and not isinstance(coverage, list):
        errs.append("coverage must be a list with one entry per scope requirement.")
    covered: Dict[str, Optional[str]] = {r: None for r in req_ids}
    for c in coverage or []:
        if isinstance(c, dict) and c.get("requirement") in covered:
            covered[c["requirement"]] = bool(c.get("covered"))
    missing = [r for r, v in covered.items() if v is None]
    if missing:
        errs.append(f"coverage is missing entries for {', '.join(missing)}.")
    if errs:
        raise TPError(*[f"{result}: {e}" for e in errs],
                      "Resume the reviewer's `task` call and have it fix the file, then record again.")
    # An uncovered requirement or an unresolved question is a finding, whatever the verdict says.
    found = list(findings or [])
    for f in found:
        f["blocking"] = True
    for rid, ok in covered.items():
        if not ok:
            text = next((r["text"] for r in scope["requirements"] if r["id"] == rid), "")
            found.append({"id": f"F{len(found) + 1}", "state": "missing",
                          "requirement": rid,
                          "issue": f"{rid} ({text}) is not covered: no task's acceptance "
                                   "criteria can fail if it is unmet.",
                          "fix": "serve it with a task whose criteria prove it, or settle it "
                                 "with the human if it is not wanted.", "blocking": True})
    pr["findings"] = found
    pr["observations"] = [str(o) for o in data.get("observations", []) if str(o).strip()]
    for o in pr["observations"]:
        wf.noticed("plan review", o)
    if data["verdict"] == "pass" and not pr["findings"] and not data.get("unresolved"):
        pr["status"] = "pass"
        wf.save(state)
        wf.event("plan_review_record", round=rnd, verdict="pass", findings=0)
        return (f"plan review round {rnd} passed — every requirement covered. `tp approve` enters execution. "
                "No human approval is needed; they can still interject with `tp revise`.")
    pr["status"] = "needs_triage"
    wf.save(state)
    wf.event("plan_review_record", round=rnd, verdict=data["verdict"], findings=len(pr["findings"]))
    return (f"plan review round {rnd} returned {data['verdict']} with {len(pr['findings'])} finding(s).\n"
            + "\n".join(f"  {f['id']} ({f.get('state')}) {f['requirement']}: {f['issue']}" for f in pr["findings"])
            + "\nVerify each against the plan, then `tp plan triage --accept-all`, or "
            "`--dismiss F#=\"<reason>\"` for each you overrule (recorded, and shown at the report).")


def cmd_plan_triage(wf: Workflow, accept_all: bool, dismiss: List[str]) -> str:
    """Accept the confirmed findings (fix the plan, resubmit, re-review) or overrule them with a
    recorded reason. Dismissals are manager decisions — the report carries them verbatim."""
    state = wf.load()
    pr = state.get("plan_review")
    if not pr or pr["status"] != "needs_triage":
        raise TPError(f"no plan-review findings await triage (status {pr and pr.get('status')}).")
    if not pr["findings"]:  # malformed rounds are refused at record; triage never sees an empty set
        raise TPError(f"round {pr['round']} has no findings to triage — `tp plan review` if a round is due.")
    reason_of = {}
    for spec in dismiss:
        fid, _, reason = spec.partition("=")
        if not reason.strip():
            raise TPError(f"--dismiss {spec}: use --dismiss F#=reason (or --accept-all).")
        reason_of[fid] = reason
    kept = [f for f in pr["findings"] if f["id"] not in reason_of]
    if not (accept_all or reason_of):
        raise TPError("Say what you decided: --accept-all, or --dismiss F#=\"reason\" for each finding you "
                      "overrule.")
    unknown = [fid for fid in reason_of if fid not in {f["id"] for f in pr["findings"]}]
    if unknown:
        raise TPError(f"{', '.join(unknown)} are not findings of round {pr['round']}.")
    if kept and not accept_all:
        raise TPError(f"{', '.join(f['id'] for f in kept)} are undismissed: --accept-all, or dismiss them too.")
    pr["dismissed"].update(reason_of)
    for fid, reason in reason_of.items():
        wf.decision(f"plan review round {pr['round']} dismiss {fid}", reason, who="manager")
    if kept:  # fix the plan, resubmit, re-review (the same reviewer, resumed)
        pr["status"] = "changes"
        wf.save(state)
        wf.event("plan_triage", round=pr["round"], accepted=len(kept), dismissed=len(reason_of))
        return ("Fix the plan for every accepted finding, then `tp plan check` and `tp plan submit` — "
                "the review re-runs (round " + str(pr["round"] + 1) + ", the same reviewer resumed).\n"
                + "\n".join(f"  {f['id']} ({f.get('state')}) {f['requirement']}: {f['issue']}"
                            + (f" Fix: {f['fix']}" if f.get("fix") else "") for f in kept))
    pr["status"] = "pass"  # every finding overruled with a recorded reason
    wf.save(state)
    wf.event("plan_triage", round=pr["round"], accepted=0, dismissed=len(reason_of))
    return ("All findings dismissed with recorded reasons — the review stands passed. `tp approve` "
            "enters execution.")

