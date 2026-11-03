#!/usr/bin/env python3
"""Codex task-pipeline bookkeeping. No agent launch, installation, or external API calls.

Approvals record operator words supplied by Codex; this is not an authentication boundary.
Exit 2 means a gate refused the operation. Checks run only approved argv, without a shell.
"""
import argparse
import copy
import fcntl
import json
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

sys.dont_write_bytecode = True
from snapshot import changed, digest, take  # noqa: E402
import checks as check_runtime  # noqa: E402

VERSION = "codex-task-pipeline-v1"
KINDS = {"code", "tests", "docs", "kb", "tutorial", "education", "research", "pm", "integration"}


class Gate(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise Gate(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def strings(value, empty=False):
    return isinstance(value, list) and (empty or bool(value)) and all(text(v) for v in value)


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Gate(f"Cannot read JSON {path}: {exc}") from exc


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, indent=2, ensure_ascii=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    os.replace(temporary, path)


def validate_scope(scope, root):
    need(isinstance(scope, dict), "scope must be an object")
    need(text(scope.get("title")), "scope.title is required")
    for key in ("constraints", "non_goals"):
        need(strings(scope.get(key), empty=True), f"scope.{key} must be a list of strings")
    deliveries = scope.get("deliverables")
    need(isinstance(deliveries, list) and deliveries, "scope.deliverables is required")
    ids = set()
    for delivery in deliveries:
        need(isinstance(delivery, dict), "deliverables must be objects")
        did = delivery.get("id")
        need(text(did) and re.fullmatch(r"D[1-9][0-9]*", did) and did not in ids,
             "deliverable ids must be unique D1, D2, ...")
        ids.add(did)
        need(delivery.get("kind") in KINDS, f"{did}: unsupported kind")
        need(text(delivery.get("what")) and text(delivery.get("where")), f"{did}: what/where required")
    # Optional for workflows approved by earlier versions; new scopes use this ledger.
    if "requirements" in scope:
        requirements = scope["requirements"]
        need(isinstance(requirements, list) and requirements, "scope.requirements must be a nonempty list")
        seen, covered = set(), set()
        for requirement in requirements:
            need(isinstance(requirement, dict), "requirements must be objects")
            rid = requirement.get("id")
            need(text(rid) and re.fullmatch(r"R[1-9][0-9]*", rid) and rid not in seen,
                 "requirement ids must be unique R1, R2, ...")
            seen.add(rid)
            need(text(requirement.get("text")), f"{rid}: requirement text is required")
            targets = requirement.get("deliverables")
            need(strings(targets) and set(targets) <= ids, f"{rid}: map to existing deliverables")
            covered.update(targets)
        need(covered == ids, "every deliverable must trace to a request requirement")
    workspaces = scope.get("workspaces")
    need(isinstance(workspaces, list) and workspaces, "scope.workspaces is required")
    names, paths = set(), set()
    for workspace in workspaces:
        need(isinstance(workspace, dict), "workspaces must be objects")
        name, raw = workspace.get("name"), workspace.get("path")
        need(text(name) and re.fullmatch(r"[a-z][a-z0-9_-]*", name) and name not in names,
             "workspace names must be unique lowercase identifiers")
        need(text(raw) and Path(raw).is_absolute(), f"{name}: use an absolute workspace path")
        path = Path(raw)
        need(path == path.resolve(), f"{name}: use the resolved workspace path")
        need(path not in paths, "workspace roots must be distinct")
        need(path != root and root not in path.parents, "workspaces must be outside the workflow folder")
        need(workspace.get("mode") in ("read", "write"), f"{name}: mode must be read or write")
        need(workspace.get("snapshot", "walk") in ("walk", "git"), f"{name}: snapshot must be walk or git")
        need(not path.exists() or path.is_dir(), f"{name}: workspace is not a directory")
        need(workspace["mode"] != "read" or path.is_dir(), f"{name}: read workspace must exist")
        names.add(name)
        paths.add(path)
    need(scope.get("review") in ("self", "independent", "none"), "review must be self, independent, or none")
    need(scope.get("review") != "none" or not any(d["kind"] in ("code", "tests") for d in deliveries),
         "code and test deliverables require final review")
    count = scope.get("max_agents", 0)
    need(type(count) is int and 0 <= count <= 3, "max_agents must be 0, 1, 2, or 3")
    need(scope["review"] != "independent" or count > 0, "independent review requires an agent allowance")
    estimate = scope.get("estimate_minutes")
    need(estimate is None or type(estimate) is int and estimate > 0, "estimate_minutes must be positive or null")


def path_in(scope, task, relative, root):
    need(text(relative), "task paths must be strings")
    pure = PurePosixPath(relative)
    need(not pure.is_absolute() and relative == pure.as_posix() and pure.parts
         and all(part not in ("..", ".git", ".tp") for part in pure.parts)
         and not any(char in relative for char in "*?[]\\"), f"not a concrete relative file: {relative}")
    workspaces = {w["name"]: w for w in scope["workspaces"]}
    workspace = workspaces.get(task.get("workspace"))
    need(workspace is not None and workspace["mode"] == "write", f"{task['id']}: workspace must be writable")
    base = Path(workspace["path"])
    path = base / relative
    need(path.resolve() == path, f"symlink or escaping task path: {relative}")
    need(path != root and root not in path.parents, "task files cannot be pipeline metadata")
    need(not path.is_dir(), f"name individual files, not directory {relative}")
    for other in workspaces.values():
        other_root = Path(other["path"])
        if other_root != base and base in other_root.parents:
            need(path != other_root and other_root not in path.parents,
                 f"{relative} belongs to nested workspace {other['name']}")
    return path


def validate_plan(plan, scope, root):
    need(isinstance(plan, dict) and text(plan.get("summary")), "plan.summary is required")
    tasks, checks = plan.get("tasks"), plan.get("checks")
    need(isinstance(tasks, list) and tasks, "plan.tasks is required")
    need(isinstance(checks, dict), "plan.checks must be an object (possibly empty)")
    workspaces = {w["name"]: w for w in scope["workspaces"]}
    for name, check in checks.items():
        need(re.fullmatch(r"[a-zA-Z0-9_-]+", name), "check names must be simple identifiers")
        need(isinstance(check, dict) and strings(check.get("argv")), f"{name}: argv must be a nonempty string list")
        need(check.get("workspace") in workspaces, f"{name}: unknown workspace")
        need(workspaces[check["workspace"]]["mode"] == "write", f"{name}: run checks in a write workspace")
        need(type(check.get("timeout_seconds", 300)) is int and check.get("timeout_seconds", 300) > 0,
             f"{name}: timeout_seconds must be a positive integer")
        need(type(check.get("reuse", False)) is bool, f"{name}: reuse must be true or false")
        if "inputs" in check:
            inputs = check["inputs"]
            need(isinstance(inputs, dict) and inputs, f"{name}: inputs must map workspaces to patterns")
            for workspace_name, patterns in inputs.items():
                need(workspace_name in workspaces and strings(patterns), f"{name}: unknown input workspace or empty patterns")
                for pattern in patterns:
                    need(not PurePosixPath(pattern).is_absolute() and not {"..", ".git", ".tp"}.intersection(PurePosixPath(pattern).parts)
                         and "\\" not in pattern, f"{name}: input patterns must stay within a workspace")
        need(strings(check.get("environment", []), empty=True), f"{name}: environment must name variables")
    need(strings(plan.get("final_checks"), empty=True), "plan.final_checks must be a list")
    need(all(c in checks for c in plan["final_checks"]), "unknown final check")
    deliveries = {d["id"] for d in scope["deliverables"]}
    requirements = {r["id"]: set(r["deliverables"]) for r in scope.get("requirements", [])}
    covered_requirements = set()
    ids, covered = set(), set()
    for task in tasks:
        need(isinstance(task, dict), "tasks must be objects")
        tid = task.get("id")
        need(text(tid) and re.fullmatch(r"T[0-9]+", tid) and tid not in ids, "task ids must be unique T01, T02, ...")
        ids.add(tid)
        need(text(task.get("title")) and task.get("kind") in KINDS, f"{tid}: title/kind required")
        need(strings(task.get("serves")) and set(task["serves"]) <= deliveries, f"{tid}: unknown or missing deliverable")
        covered.update(task["serves"])
        if requirements:
            targets = task.get("requirements")
            need(strings(targets) and set(targets) <= requirements.keys(), f"{tid}: name existing request requirements")
            need(all(requirements[r] & set(task["serves"]) for r in targets),
                 f"{tid}: requirement must map to a deliverable this task serves")
            covered_requirements.update(targets)
        need(strings(task.get("acceptance")), f"{tid}: acceptance criteria required")
        need(type(task.get("adaptive", False)) is bool, f"{tid}: adaptive must be true or false")
        need(strings(task.get("paths"), empty=task["kind"] in ("research", "integration") or task.get("adaptive", False)),
             f"{tid}: paths required")
        need(len(set(task["paths"])) == len(task["paths"]), f"{tid}: duplicate paths")
        for relative in task["paths"]:
            path_in(scope, task, relative, root)
        need(task.get("workspace") in workspaces, f"{tid}: unknown workspace")
        need(strings(task.get("depends_on"), empty=True), f"{tid}: depends_on must be a list")
        need(strings(task.get("checks"), empty=True) and all(c in checks for c in task["checks"]), f"{tid}: unknown checks")
        verification = task.get("verification", {})
        mode = verification.get("mode") if isinstance(verification, dict) else None
        need(mode in ("red-green", "characterization", "existing", "manual"), f"{tid}: verification.mode required")
        need(text(verification.get("reason")), f"{tid}: verification.reason required")
        if mode != "manual":
            need(verification.get("check") in task["checks"], f"{tid}: verification.check must be a task check")
        if mode in ("red-green", "characterization"):
            need(strings(verification.get("test_paths")) and set(verification["test_paths"]) <= set(task["paths"]),
                 f"{tid}: test_paths must be a nonempty subset of paths")
        if task["kind"] in ("code", "tests"):
            need(scope["review"] != "none", "code and tests require review")
    need(covered == deliveries, f"uncovered deliverables: {sorted(deliveries - covered)}")
    need(covered_requirements == requirements.keys(),
         f"uncovered request requirements: {sorted(requirements.keys() - covered_requirements)}")
    by_id = {t["id"]: t for t in tasks}
    visiting, visited = set(), set()

    def visit(tid):
        need(tid in by_id, f"unknown dependency {tid}")
        need(tid not in visiting, f"dependency cycle at {tid}")
        if tid in visited:
            return
        visiting.add(tid)
        for dependency in by_id[tid]["depends_on"]:
            visit(dependency)
        visiting.remove(tid)
        visited.add(tid)

    for tid in by_id:
        visit(tid)


class Workflow:
    timestamp = staticmethod(now)
    write_json = staticmethod(write)
    read_json = staticmethod(read)

    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.meta = self.root / ".tp"
        self.state_path = self.meta / "state.json"
        self.state = read(self.state_path)
        need(self.state.get("version") == VERSION,
             "Incompatible workflow. Use its original client or request an explicit migration.")

    def event(self, action, **values):
        self.state["history"].append(dict(at=now(), action=action, **values))

    def save(self):
        write(self.state_path, self.state)

    def contract(self):
        scope = read(self.root / "scope.json")
        validate_scope(scope, self.root)
        if self.state.get("scope") is not None:
            need(scope == self.state["scope"], "scope.json differs from its confirmation; use an approved amendment")
        plan = read(self.root / "plan.json")
        validate_plan(plan, scope, self.root)
        if self.state.get("plan") is not None:
            need(plan == self.state["plan"], "plan.json differs from its approval; use an approved amendment")
        return scope, plan

    def snapshot(self, scope, plan):
        cache_path = self.meta / "fingerprints.json"
        cache = read(cache_path) if cache_path.exists() else {}
        roots = {w["name"]: Path(w["path"]) for w in scope["workspaces"]}
        explicit_inputs = [dict(workspace=workspace, paths=[pattern])
                           for check in plan.get("checks", {}).values()
                           for workspace, patterns in check.get("inputs", {}).items()
                           for pattern in patterns if not any(c in pattern for c in "*?[]")
                           and ((roots[workspace] / pattern).is_file() or (roots[workspace] / pattern).is_symlink())]
        result = take(scope["workspaces"], self.root, plan["tasks"] + explicit_inputs, cache)
        write(cache_path, cache)
        return result

    def current(self):
        scope, plan = self.contract()
        return scope, plan, self.snapshot(scope, plan)

    def capture_baseline(self, scope, plan):
        """Keep original planned files so review can separate our edits from existing ones."""
        originals = self.state.setdefault("baseline_files", {})
        directory = self.meta / "baseline"
        directory.mkdir(mode=0o700, exist_ok=True)
        for task in plan["tasks"]:
            for relative in task["paths"]:
                key = f"{task['workspace']}:{relative}"
                if key in originals:
                    continue
                source = path_in(scope, task, relative, self.root)
                if source.is_file():
                    target = directory / digest(key)
                    shutil.copyfile(source, target)
                    target.chmod(0o600)
                    originals[key] = str(target.relative_to(self.root))
                else:
                    originals[key] = None

    def runnable(self):
        need(self.state["phase"] == "EXECUTING", "execution requires approval and a non-halted run")
        need(not self.state.get("question"), "operator input is pending; resolve or amend first")

    def pin_files(self, task, hashes):
        """Keep each pinned revision for inspection; a correction never erases its evidence."""
        files = {}
        for key, value in hashes.items():
            relative = key.split(":", 1)[1]
            source = path_in(self.state["scope"], task, relative, self.root)
            target = self.meta / "test-baseline" / task["id"] / digest([key, value])
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copyfile(source, target)
                target.chmod(0o600)
            files[key] = str(target.relative_to(self.root))
        return files

    def tasks(self):
        return self.state["tasks"]

    def task(self, tid):
        scope, plan = self.contract()
        found = next((t for t in plan["tasks"] if t["id"] == tid), None)
        need(found is not None, f"unknown task {tid}")
        return scope, plan, found

    def edits(self, scope, plan, task, before):
        after = self.snapshot(scope, plan)
        changes = changed(before, after)
        allowed = {f"{task['workspace']}:{p}" for p in task["paths"]}
        unexpected = set(changes) - allowed
        need(not unexpected, f"changes outside {task['id']}'s write paths: {sorted(unexpected)}; inspect, do not auto-revert")
        return after, changes

    def reopen(self, tid, reason):
        targets = {tid}
        while True:
            dependents = {t["id"] for t in self.state["plan"]["tasks"] if targets.intersection(t["depends_on"])}
            expanded = targets | dependents
            if expanded == targets:
                break
            targets = expanded
        for target in targets:
            self.tasks()[target] = {"status": "pending"}
        self.state["review"] = None
        self.state["checks"] = {}
        self.event("reopen", tasks=sorted(targets), reason=reason)

    def idle_checkpoint(self, snapshot):
        if not any(t["status"] == "running" for t in self.tasks().values()):
            unexpected = changed(self.state["checkpoint"], snapshot)
            need(not unexpected, f"workspace changed between tasks: {unexpected}; inspect and ask before adopting edits")

    def run_check(self, name, scope, plan):
        return check_runtime.run(self, name, scope, plan)


def render(root, name, data):
    # JSON fences retain the exact complete contract while keeping operator docs readable.
    (root / f"{name}.md").write_text(f"# {name.title()}\n\n```json\n" +
                                    json.dumps(data, indent=2, ensure_ascii=False) + "\n```\n", encoding="utf-8")


def initialize(args):
    location = Path(args.location).expanduser().resolve()
    need(not (location / ".tp" / "state.json").exists(), "location is already a workflow; use its parent or resume")
    request = Path(args.request_file).read_text(encoding="utf-8")
    need(request.strip() and args.title.strip(), "request and title must not be blank")
    slug = re.sub(r"[^a-z0-9]+", "-", args.title.lower()).strip("-")[:48].rstrip("-") or "workflow"
    base = datetime.now(timezone.utc).date().isoformat() + "-" + slug
    location.mkdir(parents=True, exist_ok=True)
    root = location / base
    suffix = 1
    while True:
        try:
            root.mkdir()
            break
        except FileExistsError:
            suffix += 1
            root = location / f"{base}-{suffix}"
    (root / "request.md").write_text(request, encoding="utf-8")
    created = now()
    write(root / ".tp" / "state.json", dict(version=VERSION, title=args.title, created=created,
          phase="SCOPING", scope=None, plan=None, tasks={}, checks={}, notes=[], review=None,
          history=[], question=None, active_activity=dict(category="bookkeeping", label="Scope preparation",
                                                         started=created, automatic=True, task=None)))
    args.created_workflow = root
    return f"workflow: {root}\nNext: draft scope.json, then scope check and scope confirm."


def fresh(check, snapshot, definition=None):
    return bool(check and check["exit_code"] == 0 and check["stable"] and
                check["fingerprint"] == check_runtime.fingerprint(snapshot, definition or {}))


def retain_checks(state, snapshot, plan):
    return {name: result for name, result in state["checks"].items()
            if "inputs" in plan["checks"].get(name, {}) and fresh(result, snapshot, plan["checks"][name])}


def next_action(wf):
    state = wf.state
    if state["phase"] == "HALTED":
        return "halted: resume only on the operator's instruction"
    if state.get("question"):
        return "human: " + state["question"]
    unresolved = [op["id"] for op in state.get("operations", {}).values() if op["status"] in ("running", "unknown")]
    if unresolved:
        return "recover: inspect operation receipts before advancing: " + ", ".join(unresolved)
    if state["phase"] == "SCOPING":
        return "scope: draft/check scope.json and obtain operator confirmation"
    if state["phase"] == "PLANNING":
        return "plan: draft/check plan.json and obtain operator approval"
    if state["phase"] == "COMPLETE":
        return "complete: report.md"
    scope, plan, snapshot = wf.current()
    wf.idle_checkpoint(snapshot)
    for task in plan["tasks"]:
        status = wf.tasks()[task["id"]]["status"]
        if status == "running":
            return f"continue: {task['id']} (inspect partial edits after an interruption)"
    for task in plan["tasks"]:
        if wf.tasks()[task["id"]]["status"] == "pending" and all(
                wf.tasks()[d]["status"] == "done" for d in task["depends_on"]):
            return f"start: {task['id']} — {task['title']}"
    if any(t["status"] != "done" for t in wf.tasks().values()):
        return "human: no ready task; inspect task/dependency state"
    active_agents = [a["id"] for a in state.get("agents", {}).values() if a["status"] in ("reserved", "running", "unknown")]
    if active_agents:
        return "agents: collect/validate or cancel assignments before final delivery: " + ", ".join(active_agents)
    for name in plan["final_checks"]:
        if not fresh(state["checks"].get(name), snapshot, plan["checks"][name]):
            return f"check: {name}"
    if scope["review"] != "none" and not (state.get("review") and
            state["review"]["fingerprint"] == digest(snapshot) and state["review"]["verdict"] == "pass"):
        return f"review: complete change ({scope['review']})"
    if any(not item.get("classification") for item in state["notes"]):
        return "closeout: classify noticed items and obtain any required operator decisions"
    return "final: write the verified completion report"


def status(wf):
    state = wf.state
    counts = {name: sum(t["status"] == name for t in state["tasks"].values())
              for name in ("pending", "running", "done")}
    drift = [name for name in ("scope", "plan") if state.get(name) is not None
             and read(wf.root / f"{name}.json") != state[name]]
    return (f"{state['title']}: {state['phase']}\nTasks: {counts}\n"
            f"Question: {state.get('question') or 'none'}\n"
            f"Contract drift: {', '.join(drift) or 'none'}\nWorkflow: {wf.root}")


def execute(wf, args):
    state, command = wf.state, args.command
    if command == "show":
        _, _, task = wf.task(args.task)
        entry = wf.tasks().get(args.task, {"status": "unapproved"})
        return json.dumps(dict(task=task, status=entry["status"], started=entry.get("started"),
                               result=entry.get("result"), checks=entry.get("checks", {})), indent=2)
    if command == "next":
        return next_action(wf)
    if command == "halt":
        need(state["phase"] != "COMPLETE", "completed workflow cannot be halted")
        if state["phase"] != "HALTED":
            state["resume_phase"], state["phase"] = state["phase"], "HALTED"
            check_runtime.cancel(wf)
            import tracking
            tracking.pause(wf, "operator halt")
            wf.event("halt", reason=args.reason)
        return "Halted. Partial edits and approval are preserved."
    import tracking
    if command in tracking.COMMANDS:
        return tracking.execute(wf, args, sys.modules[__name__])
    need(not any(op["status"] in ("running", "unknown") for op in state.get("operations", {}).values()),
         "an operation is unresolved; inspect/recover it before advancing")
    if command == "resume":
        need(state["phase"] == "HALTED", "workflow is not halted; use next to continue")
        state["phase"] = state.pop("resume_phase")
        running = next((tid for tid, entry in state["tasks"].items() if entry["status"] == "running"), None)
        tracking.switch(wf, "implementation" if running else "bookkeeping", "Inspect resumed checkpoint", running)
        wf.event("resume", answer=args.answer)
        return "Resumed. Run next."
    need(state["phase"] not in ("HALTED", "COMPLETE"), "workflow is halted or complete")
    if command == "block":
        need(not state.get("question"), "a question is already pending; resolve or amend it first")
        state["question"] = args.question
        tracking.switch(wf, "waiting", "Operator decision: " + args.question)
        wf.event("question", question=args.question)
        return "Operator input required: " + args.question
    if command == "resolve":
        need(state.get("question"), "no question is pending")
        need(args.by != "manager" or text(args.evidence), "manager resolution needs --evidence from saved decisions")
        tracking.switch(wf, "bookkeeping", "Apply settled decision")
        wf.event("answer", question=state["question"], answer=args.answer, by=args.by, evidence=args.evidence)
        state["question"] = None
        return "Clarification recorded; contract unchanged. Run next."
    if command == "scope":
        need(state["phase"] in ("SCOPING", "PLANNING"), "scope already confirmed; use amend")
        scope = read(wf.root / "scope.json")
        validate_scope(scope, wf.root)
        need(state["scope"] is None or scope == state["scope"], "confirmed scope changed; use amend")
        render(wf.root, "scope", scope)
        if args.action == "confirm":
            need(not state["question"], "resolve pending questions before confirmation")
            need(text(args.answer), "confirmation needs --answer with the operator's words")
            state["scope"], state["phase"] = scope, "PLANNING"
            tracking.switch(wf, "research", "Research and plan approved outcomes")
            wf.event("scope-confirm", answer=args.answer, scope=scope)
        elif state["phase"] == "SCOPING":
            tracking.switch(wf, "waiting", "Scope confirmation")
        return "scope ok: scope.md"
    if command in ("plan", "approve"):
        need(state["phase"] == "PLANNING", "confirm scope before planning; use amend after approval")
        scope, plan = wf.contract()
        render(wf.root, "plan", plan)
        if command == "approve":
            need(not state["question"], "resolve pending questions before approval")
            state["plan"], state["phase"] = plan, "EXECUTING"
            state["tasks"] = {t["id"]: {"status": "pending"} for t in plan["tasks"]}
            state["baseline"] = wf.snapshot(scope, plan)
            state["checkpoint"] = state["baseline"]
            wf.capture_baseline(scope, plan)
            tracking.switch(wf, "bookkeeping", "Begin approved plan")
            wf.event("approve", answer=args.answer, scope=scope, plan=plan)
        else:
            tracking.switch(wf, "waiting", "Concrete plan approval")
        return "plan ok: plan.md" if command == "plan" else "Approved. Run next."
    if command == "amend":
        need(state["scope"] is not None, "confirm an initial scope first")
        scope = read(args.scope_file) if args.scope_file else copy.deepcopy(state["scope"])
        plan = read(args.plan_file) if args.plan_file else copy.deepcopy(state["plan"])
        validate_scope(scope, wf.root)
        old_roots = {w["name"]: w["path"] for w in state["scope"]["workspaces"]}
        need(all(w["name"] not in old_roots or w["path"] == old_roots[w["name"]] for w in scope["workspaces"]),
             "use a new workspace name for a changed root so baseline provenance remains unambiguous")
        if plan is not None:
            validate_plan(plan, scope, wf.root)
        old_plan = state["plan"] or {"tasks": []}
        old_tasks = {t["id"]: t for t in old_plan["tasks"]}
        new_snapshot = wf.snapshot(scope, plan) if plan is not None else None
        adopted = changed(state.get("checkpoint", {}), new_snapshot) if new_snapshot is not None else []
        new_tasks = {}
        for task in (plan or {"tasks": []})["tasks"]:
            previous = state["tasks"].get(task["id"], {})
            touched = any(f"{task['workspace']}:{path}" in adopted for path in task["paths"])
            same = task == old_tasks.get(task["id"]) and scope == state["scope"] and not touched
            new_tasks[task["id"]] = previous if same and previous.get("status") == "done" else {"status": "pending"}
        # An unchanged dependent still needs re-verification if its prerequisite changed.
        while True:
            affected = [t["id"] for t in (plan or {"tasks": []})["tasks"]
                        if new_tasks[t["id"]]["status"] == "done" and any(
                            new_tasks[d]["status"] != "done" for d in t["depends_on"])]
            if not affected:
                break
            for tid in affected:
                new_tasks[tid] = {"status": "pending"}
        changes = []
        for key in sorted(set(state["scope"]) | set(scope)):
            if state["scope"].get(key) != scope.get(key):
                changes.append(f"Scope {key}: {json.dumps(state['scope'].get(key))} -> {json.dumps(scope.get(key))}")
        new_ids = {t["id"] for t in (plan or {"tasks": []})["tasks"]}
        changes += [f"Removed task {tid}: {old_tasks[tid]['title']}" for tid in sorted(set(old_tasks) - new_ids)]
        changes += [f"Added/changed task {t['id']}: {json.dumps(old_tasks.get(t['id']))} -> {json.dumps(t)}"
                    for t in (plan or {"tasks": []})["tasks"] if t != old_tasks.get(t["id"])]
        if plan is not None:
            changes += [f"Plan {key}: {json.dumps(old_plan.get(key))} -> {json.dumps(plan.get(key))}"
                        for key in sorted(set(old_plan) | set(plan)) if key != "tasks" and old_plan.get(key) != plan.get(key)]
        if adopted:
            changes.append(f"Adopted workspace changes: {json.dumps(adopted)}")
        state.update(scope=scope, plan=plan, tasks=new_tasks, checks={}, review=None, question=None,
                     phase="EXECUTING" if plan is not None else "PLANNING")
        write(wf.root / "scope.json", scope)
        render(wf.root, "scope", scope)
        if plan is not None:
            write(wf.root / "plan.json", plan)
            render(wf.root, "plan", plan)
            state["checkpoint"] = new_snapshot
            wf.capture_baseline(scope, plan)
        tracking.switch(wf, "bookkeeping", "Apply approved amendment")
        wf.event("amend", answer=args.answer, changes=changes, scope=scope, plan=plan)
        return "Amendment recorded; affected work and final verification reopen. Inspect partial edits, then next."
    wf.runnable()
    scope, plan = wf.contract()
    if command == "refine":
        _, _, task = wf.task(args.task)
        entry = wf.tasks()[args.task]
        need(task.get("adaptive", False), "refine requires adaptive: true in the approved task")
        need(entry["status"] in ("pending", "running"), "reopen completed work before refining it")
        need(not any(tid != args.task and t["status"] == "running" for tid, t in wf.tasks().items()),
             "finish the active task before refining another task")
        spec = read(args.file)
        need(isinstance(spec, dict) and spec and set(spec) <= {"paths", "checks", "verification"},
             "refine fields are paths, checks, verification only; outcomes require an amendment")
        updated = copy.deepcopy(plan)
        new_task = next(t for t in updated["tasks"] if t["id"] == args.task)
        added = spec.get("paths", [])
        need(strings(added, empty=True), "refine paths must be concrete files")
        for relative in added:
            path_in(scope, task, relative, wf.root)
        new_task["paths"] += [p for p in dict.fromkeys(added) if p not in task["paths"]]
        checks = spec.get("checks", {})
        need(isinstance(checks, dict), "refine checks must be check definitions")
        for name, definition in checks.items():
            need(name not in plan["checks"] or definition == plan["checks"][name], "refine cannot replace an approved check")
            need(isinstance(definition, dict) and definition.get("workspace") == task["workspace"],
                 "refined checks must run in the task's existing workspace")
            updated["checks"][name] = definition
            if name not in new_task["checks"]:
                new_task["checks"].append(name)
        if "verification" in spec:
            verification = spec["verification"]
            need(not entry.get("test_checkpoint"), "test-first strategy is already pinned; use an approved amendment")
            need(task["verification"]["mode"] in ("manual", "existing"),
                 "refine cannot replace an approved test-first strategy")
            need(isinstance(verification, dict) and verification.get("mode") in ("red-green", "characterization"),
                 "refined verification must establish a test-first strategy")
            new_task["verification"] = verification
        validate_plan(updated, scope, wf.root)
        if entry["status"] == "running":
            snapshot, _ = wf.edits(scope, plan, task, entry["before"])
        else:
            snapshot = wf.snapshot(scope, plan)
            wf.idle_checkpoint(snapshot)
        need(wf.snapshot(scope, updated) == snapshot,
             "new paths expose previously untracked contents; inspect and use an approved amendment")
        need(updated != plan, "refinement changes nothing")
        wf.capture_baseline(scope, updated)
        state.update(plan=updated, checks=retain_checks(state, snapshot, updated), review=None)
        write(wf.root / "plan.json", updated)
        render(wf.root, "plan", updated)
        wf.event("refine", task=args.task, detail=spec, reason=args.reason, by="manager")
        return f"Refined {args.task}; outcomes and checkpoints preserved. Run its test-first phase before production edits."
    if command == "test-update":
        _, _, task = wf.task(args.task)
        entry = wf.tasks()[args.task]
        need(task.get("adaptive", False), "test-update requires adaptive: true in the approved task")
        need(entry["status"] == "running", "start and pin this task first")
        target = entry
        if args.repair:
            target = next((r for r in entry.get("repairs", []) if r["id"] == args.repair), None)
            need(target is not None, "unknown repair step")
        need(target.get("test_checkpoint"), "start and pin this task/repair first")
        correction = read(args.file)
        need(isinstance(correction, dict) and set(correction) == {"kind", "reason", "evidence"}
             and correction.get("kind") == "mechanical"
             and text(correction.get("reason")) and text(correction.get("evidence")),
             "only documented mechanical corrections qualify; changed strategy requires an approved amendment")
        checkpoint = target["test_checkpoint"]
        need(checkpoint.get("files"), "original pinned copies unavailable; use an approved amendment")
        snapshot, _ = wf.edits(scope, plan, task, entry["before"])
        hashes = {p: snapshot.get(p) for p in checkpoint["hashes"]}
        need(all(hashes.values()) and hashes != checkpoint["hashes"], "pinned tests must exist and have a correction")
        verification = target["verification"] if args.repair else task["verification"]
        need(fresh(state["checks"].get(verification["check"]), snapshot, plan["checks"][verification["check"]]),
             "run the verification check on current contents before recording a correction")
        target.setdefault("test_updates", []).append(dict(previous=copy.deepcopy(checkpoint), **correction))
        target["test_checkpoint"] = dict(checkpoint, hashes=hashes, files=wf.pin_files(task, hashes))
        state["review"] = None
        wf.event("test-update", task=args.task, previous=checkpoint["hashes"], current=hashes,
                 detail=correction, reason=correction["reason"], repair=args.repair, by="manager")
        return "Mechanical correction recorded; original tests and test-first evidence preserved."
    if command == "widen":
        _, _, task = wf.task(args.task)
        entry = wf.tasks()[args.task]
        need(entry["status"] in ("pending", "running"), "reopen completed work before widening it")
        need(not any(tid != args.task and t["status"] == "running" for tid, t in wf.tasks().items()),
             "finish the active task before widening another task")
        need(args.deliverable in task["serves"], "widen must serve one of this task's approved deliverables")
        added = [p for p in dict.fromkeys(args.path) if p not in task["paths"]]
        need(added, "no new paths to add")
        for relative in added:
            path_in(scope, task, relative, wf.root)
        # Widen before editing: do not use it to adopt concurrent or out-of-contract edits.
        if entry["status"] == "running":
            snapshot, _ = wf.edits(scope, plan, task, entry["before"])
        else:
            snapshot = wf.snapshot(scope, plan)
            wf.idle_checkpoint(snapshot)
        updated = copy.deepcopy(plan)
        new_task = next(t for t in updated["tasks"] if t["id"] == args.task)
        new_task["paths"] += added
        validate_plan(updated, scope, wf.root)
        need(wf.snapshot(scope, updated) == snapshot,
             "new paths expose previously untracked contents; inspect and use an approved amendment")
        wf.capture_baseline(scope, updated)
        state.update(plan=updated, checks=retain_checks(state, snapshot, updated), review=None)
        write(wf.root / "plan.json", updated)
        render(wf.root, "plan", updated)
        wf.event("widen", task=args.task, paths=added, deliverable=args.deliverable,
                 reason=args.reason, by="manager")
        return f"Widened {args.task}: {added}. Criteria and scope unchanged; run required checks again."
    if command == "start":
        _, _, task = wf.task(args.task)
        need(not any(t["status"] == "running" for t in wf.tasks().values()), "only one main-session writer may run")
        need(wf.tasks()[args.task]["status"] == "pending", "task is not pending")
        need(all(wf.tasks()[d]["status"] == "done" for d in task["depends_on"]), "dependencies are unfinished")
        snapshot = wf.snapshot(scope, plan)
        wf.idle_checkpoint(snapshot)
        wf.tasks()[args.task] = dict(status="running", before=snapshot, started=now())
        state["review"] = None
        category = "research" if task["kind"] == "research" or (task.get("adaptive") and task["verification"]["mode"] == "manual") else "implementation"
        tracking.switch(wf, category, task["title"], args.task)
        wf.event("start", task=args.task)
        return f"Started {args.task}: {task['title']}. Main session writes {task['paths']}."
    if command == "check":
        snapshot = wf.snapshot(scope, plan)
        wf.idle_checkpoint(snapshot)
        previous = state["checks"].get(args.name)
        if plan["checks"].get(args.name, {}).get("reuse", False) and not args.force and fresh(previous, snapshot, plan["checks"][args.name]):
            wf.event("check-reuse", check=args.name, log=previous["log"])
            return f"PASS {args.name} (reused unchanged contents): {previous['log']}"
        result = wf.run_check(args.name, scope, plan)
        need(result["exit_code"] == 0 and result["stable"],
             f"check {args.name} failed or changed source artifacts; inspect {result['log']}")
        return f"PASS {args.name}: {result['log']}"
    if command in ("test", "done"):
        _, _, task = wf.task(args.task)
        entry = wf.tasks()[args.task]
        need(entry["status"] == "running", "start this task first")
        snapshot, changes = wf.edits(scope, plan, task, entry["before"])
        verification = task["verification"]
        if command == "test":
            need(not entry.get("test_checkpoint"), "tests are already pinned; inspect and amend instead of repinning")
            expected_mode = "red-green" if args.stage == "red" else "characterization"
            need(verification["mode"] == expected_mode, "test stage disagrees with the approved verification mode")
            tests = {f"{task['workspace']}:{p}" for p in verification["test_paths"]}
            need(set(changes) <= tests, "production files changed before the test-first checkpoint")
            need(tests <= snapshot.keys(), "all planned test files must exist")
            result = wf.run_check(verification["check"], scope, plan)
            wf.runnable()
            state = wf.state
            entry = wf.tasks()[args.task]
            success = result["exit_code"] > 0 if args.stage == "red" else result["exit_code"] == 0
            need(success and result["exit_code"] not in (124, 127, 130) and result["stable"],
                 "test stage did not produce the expected stable failure/pass; inspect the log")
            hashes = {p: snapshot[p] for p in tests}
            entry["test_checkpoint"] = dict(stage=args.stage, hashes=hashes, note=args.note,
                                           files=wf.pin_files(task, hashes), log=result["log"])
            wf.event("test", task=args.task, stage=args.stage, note=args.note)
            return f"Recorded {args.stage} tests for {args.task}; preserve them during implementation."
        result = read(args.result_file)
        need(isinstance(result, dict) and result.get("task") == args.task and text(result.get("summary")),
             "result needs this task id and a nonempty summary")
        evidence = result.get("acceptance")
        need(isinstance(evidence, list), "result.acceptance must be a list")
        criteria = []
        for item in evidence:
            need(isinstance(item, dict) and type(item.get("criterion")) is int and text(item.get("evidence")),
                 "each acceptance entry needs an integer criterion and evidence")
            criteria.append(item["criterion"])
        need(sorted(criteria) == list(range(1, len(task["acceptance"]) + 1)), "every criterion needs exactly one evidence entry")
        for name in task["checks"]:
            need(fresh(state["checks"].get(name), snapshot, plan["checks"][name]), f"required check {name} is missing, failed, or stale")
        if entry.get("repairs"):
            import repairs
            repairs.validate_done(wf, task, entry, snapshot, sys.modules[__name__])
        if verification["mode"] in ("red-green", "characterization"):
            checkpoint = entry.get("test_checkpoint")
            need(checkpoint and all(snapshot.get(p) == value for p, value in checkpoint["hashes"].items()),
                 "test checkpoint missing or pinned tests changed; ask before correcting the approved test strategy")
        entry.update(status="done", result=result, changes=changes, ended=now(),
                     checks={c: copy.deepcopy(state["checks"][c]) for c in task["checks"]})
        entry.pop("before", None)
        state["checkpoint"] = snapshot
        tracking.switch(wf, "verification" if all(t["status"] == "done" for t in wf.tasks().values()) else "bookkeeping",
                        "Integrate and review delivered outcomes")
        wf.event("done", task=args.task, result=result, changes=changes)
        return f"Accepted {args.task}. Run next."
    if command == "reopen":
        need(args.task in wf.tasks() and wf.tasks()[args.task]["status"] == "done", "only completed tasks can reopen")
        need(not any(t["status"] == "running" for t in wf.tasks().values()), "finish or amend the active task first")
        wf.reopen(args.task, args.reason)
        return "Task and completed dependents reopened. Run next."
    if command == "note":
        state["notes"].append(dict(id=len(state["notes"]) + 1, text=args.text))
        wf.event("note", text=args.text)
        return f"Noted item {len(state['notes'])}."
    if command == "closeout":
        decisions = read(args.file)
        need(isinstance(decisions, list) and decisions, "closeout file must contain a nonempty list")
        seen = set()
        for decision in decisions:
            need(isinstance(decision, dict) and type(decision.get("id")) is int, "closeout item id required")
            number = decision["id"]
            need(1 <= number <= len(state["notes"]) and number not in seen, "unknown or duplicate closeout id")
            seen.add(number)
            need(decision.get("classification") in ("observation", "deferred", "followup") and text(decision.get("reason")),
                 "each item needs a classification and a concrete reason/consequence")
            need(decision["classification"] == "observation" or text(args.answer), "deferral/followup requires the operator's --answer")
        for decision in decisions:
            state["notes"][decision["id"] - 1].update(decision, answer=args.answer)
        wf.event("closeout", decisions=decisions, answer=args.answer)
        return "Closeout decisions recorded."
    if command == "review":
        need(all(t["status"] == "done" for t in wf.tasks().values()), "finish all tasks before final review")
        snapshot = wf.snapshot(scope, plan)
        wf.idle_checkpoint(snapshot)
        need(all(fresh(state["checks"].get(c), snapshot, plan["checks"][c]) for c in plan["final_checks"]), "run final checks before review")
        result = read(args.file)
        need(isinstance(result, dict) and result.get("method") == scope["review"] and scope["review"] != "none",
             "review method differs from approved scope")
        need(result.get("verdict") in ("pass", "changes") and text(result.get("summary")), "review verdict/summary required")
        need(isinstance(result.get("findings"), list), "review.findings must be a list")
        need(bool(result["findings"]) == (result["verdict"] == "changes"), "pass must have no findings; changes must have findings")
        need(scope["review"] != "independent" or text(result.get("agent_id")), "identify the actual independent reviewer")
        if scope.get("requirements"):
            coverage = result.get("requirements")
            need(isinstance(coverage, list) and all(isinstance(r, dict) and text(r.get("id"))
                 and text(r.get("evidence")) for r in coverage),
                 "review needs requirement coverage with evidence against the original request")
            need(sorted(r.get("id", "") for r in coverage) == sorted(r["id"] for r in scope["requirements"]),
                 "review must cover every request requirement exactly once")
        for finding in result["findings"]:
            need(isinstance(finding, dict) and finding.get("task") in wf.tasks()
                 and text(finding.get("issue")) and text(finding.get("evidence")), "finding needs an owning task, issue, and evidence")
        for finding in result["findings"]:
            wf.reopen(finding["task"], finding["issue"])
        state["review"] = dict(result, fingerprint=digest(snapshot), at=now())
        tracking.switch(wf, "bookkeeping", "Close out review decisions")
        wf.event("review", result=state["review"])
        return "Review recorded. Run next."
    if command == "final":
        action = next_action(wf)
        need(action.startswith("final:"), "completion gate: " + action)
        state["phase"], state["completed"] = "COMPLETE", now()
        tracking.pause(wf, "workflow complete")
        elapsed = (datetime.fromisoformat(state["completed"]) - datetime.fromisoformat(state["created"])).total_seconds() / 60
        estimate = f"{scope['estimate_minutes']} minutes" if scope.get("estimate_minutes") is not None else "not supplied"
        report = [f"# {state['title']}", "", "All approved tasks and required verification completed.", "",
                  f"Started: {state['created']}", f"Completed: {state['completed']}",
                  f"Estimate: {estimate} (reporting only).",
                  f"Wall elapsed: {elapsed:.1f} minutes, including operator waits and halts.",
                  "Token usage: not measured by this helper.", "", "## Delivered"]
        for task in plan["tasks"]:
            entry = wf.tasks()[task["id"]]
            report += [f"- {task['id']}: {entry['result']['summary']}"]
            report += [f"  - Criterion {item['criterion']}: {item['evidence']}" for item in entry["result"]["acceptance"]]
            report += [f"  - Check {name}: PASS ({check['log']})" for name, check in entry["checks"].items()]
            report += [f"  - Verification: {task['verification']['mode']} — {task['verification']['reason']}"]
            for repair in entry.get("repairs", []):
                report += [f"  - Repair {repair['id']} (criteria {repair['criteria']}): {repair['result']['summary']}",
                           f"    - {repair['result']['evidence']}",
                           f"    - Original {repair['test_checkpoint']['stage']}: {repair['test_checkpoint']['log']}"]
        report += ["", "## Request coverage"]
        for requirement in scope.get("requirements", []):
            owners = [t["id"] for t in plan["tasks"] if requirement["id"] in t.get("requirements", [])]
            report += [f"- {requirement['id']}: {requirement['text']} — {', '.join(requirement['deliverables'])}; tasks {', '.join(owners)}."]
        if state["review"]:
            report += [f"  - {r['id']}: {r['evidence']}" for r in state["review"].get("requirements", [])]
        report += ["", "## Final checks"]
        report += [f"- {c}: PASS ({state['checks'][c]['log']})" for c in plan["final_checks"]] or ["- None required by the approved plan."]
        report += ["", "## Review", "", state["review"]["summary"] + f" ({scope['review']})." if state["review"] else "None required by approved scope.",
                   "", "## Scope decisions"]
        for event in state["history"]:
            if event["action"] in ("scope-confirm", "approve", "amend", "answer", "widen", "refine", "test-update"):
                report += [f"- {event['action']} ({event.get('by', 'operator')}): {event.get('answer', event.get('reason'))}"]
                if event["action"] in ("refine", "test-update"):
                    report += [f"  - {event['task']}: {json.dumps(event['detail'])}"]
                if event["action"] == "widen":
                    report += [f"  - {event['task']} for {event['deliverable']}: {', '.join(event['paths'])}"]
                if event.get("evidence"):
                    report += [f"  - Decision evidence: {event['evidence']}"]
                report += [f"  - {change}" for change in event.get("changes", [])]
        report += ["", "## Delegation and effects"]
        for agent in state.get("agents", {}).values():
            report += [f"- {agent['id']}: {agent['model']} / {agent['reasoning']}; actual model: {agent.get('actual_model') or 'unreported'}; "
                       f"{agent['status']}; accepted: {agent.get('accepted', False)}. {agent['model_reason']}"]
        for operation in state.get("operations", {}).values():
            if operation["kind"] != "check":
                report += [f"- {operation['id']} ({operation['kind']}): {operation['status']}; {operation.get('evidence', 'no outcome evidence')}."]
        report += ["", "## Noticed items"]
        report += [f"- {n['classification']}: {n['text']} — {n['reason']}" for n in state["notes"]] or ["- None."]
        report += ["", "Full request: request.md. Approval, check, and revision history: .tp/state.json.",
                   "Original planned file contents: .tp/baseline/ (baseline_files maps each workspace:path; null means it did not exist)."]
        (wf.root / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        with (wf.root / "report.md").open("a") as stream:
            stream.write("\nMeasured progress and overhead: metrics.json. Overlapping durations are not additive.\n")
        wf.event("final")
        return "Complete: " + str(wf.root / "report.md")
    raise Gate(f"unknown command {command}")


SCHEMAS = {
    "scope": dict(title="Add multiplication", deliverables=[dict(id="D1", kind="code", what="Add mul(a,b)", where="app/calc.py")],
                  requirements=[dict(id="R1", text="Add multiplication with zero and negative operand support.", deliverables=["D1"])],
                  workspaces=[dict(name="app", path="/absolute/path/to/app", mode="write")],
                  constraints=["Follow repository instructions; preserve existing edits."], non_goals=["No unrelated cleanup."],
                  review="self", max_agents=3, estimate_minutes=30),
    "plan": dict(summary="Add and verify multiplication.", tasks=[dict(id="T01", title="Multiply", kind="code", serves=["D1"], requirements=["R1"],
                 workspace="app", paths=["calc.py", "test_calc.py"], depends_on=[], acceptance=["mul(2,3) returns 6; cover zero and negatives."],
                 checks=["unit"], verification=dict(mode="red-green", check="unit", test_paths=["test_calc.py"], reason="New behavior needs regression coverage."))],
                 checks=dict(unit=dict(argv=["python3", "-B", "-m", "unittest", "test_calc"], workspace="app", timeout_seconds=300)), final_checks=["unit"]),
    "result": dict(task="T01", summary="Multiplication handles positive, negative, and zero inputs.",
                   acceptance=[dict(criterion=1, evidence="test_calc.py:8; unit check PASS.")]),
    "refine": dict(paths=["calc.py", "test_calc.py"], checks=dict(unit=dict(
                   argv=["python3", "-B", "-m", "unittest", "test_calc"], workspace="app", reuse=True)),
                   verification=dict(mode="red-green", check="unit", test_paths=["test_calc.py"],
                                     reason="Reproduce the validated bug before changing production.")),
    "test-update": dict(kind="mechanical", reason="Spell the permission literal in octal for lint.",
                        evidence="Pinned test diff changes 0 to 0o0 only; values, cases and assertions are identical. Original red log retained."),
    "repair": dict(id="F1", reason="Reproduced incorrect multiplication, required by criterion 1.", criteria=[1],
                   paths=["calc.py", "test_mul_regression.py"], checks=dict(unit=dict(
                       argv=["python3", "-B", "-m", "unittest", "discover"], workspace="app", reuse=True,
                       inputs={"app": ["calc.py", "test_*.py", "pyproject.toml"]})),
                   verification=dict(mode="red-green", check="unit", test_paths=["test_mul_regression.py"],
                                     reason="Reproduce the wrong result before the production edit.")),
    "repair-result": dict(summary="Multiplication fixed.", evidence="Retained failing checkpoint and current passing unit log; prior regressions remain green."),
    "agent": dict(role="research", requirements=["R1"], question="Locate multiplication callers and their existing tests.",
                  paths=["/absolute/path/to/app"], done_when="Return bounded caller/test evidence with paths and lines.",
                  model="TERRA", reasoning="medium", model_reason="Bounded evidence extraction with simple acceptance."),
    "agent-result": dict(accepted=True, summary="Callers and tests identified.", evidence=["calc.py:12; test_calc.py:8"],
                         validation="Parent inspected the cited callers and reconciled all requested evidence."),
    "usage": dict(id="main-session", source="Host session cumulative counters, exact session id and timestamp.",
                  measurements=dict(input_tokens=1200, cached_input_tokens=600, output_tokens=100, tool_calls=12)),
    "operation-result": dict(status="completed", evidence="Read-back confirms exact commit id or published artifact contents; operation was not replayed."),
    "review": dict(method="self", verdict="pass", summary="Verified all criteria, error paths, and test assertions against the diff.", findings=[],
                   requirements=[dict(id="R1", evidence="Original request and D1 criteria match; test_calc.py covers zero and negatives.")]),
    "closeout": [dict(id=1, classification="observation", reason="Unrelated finding; no requested criterion depends on it.")],
}


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("-w", "--workflow")
    commands = result.add_subparsers(dest="command", required=True)
    item = commands.add_parser("init")
    item.add_argument("location")
    item.add_argument("--title", required=True)
    item.add_argument("--request-file", required=True)
    item = commands.add_parser("schema")
    item.add_argument("name", choices=SCHEMAS)
    for name in ("status", "next", "approve", "resume", "resolve", "final"):
        item = commands.add_parser(name)
        if name in ("approve", "resume", "resolve"):
            item.add_argument("--answer", required=True)
        if name == "resolve":
            item.add_argument("--by", choices=("operator", "manager"), default="operator")
            item.add_argument("--evidence")
        if name == "status":
            item.add_argument("--json", action="store_true")
    item = commands.add_parser("scope")
    item.add_argument("action", choices=("check", "confirm"))
    item.add_argument("--answer")
    item = commands.add_parser("plan")
    item.add_argument("action", choices=("check",))
    item = commands.add_parser("amend")
    item.add_argument("--scope-file")
    item.add_argument("--plan-file")
    item.add_argument("--answer", required=True)
    item = commands.add_parser("halt", aliases=["hault"])
    item.add_argument("--reason", default="Operator requested halt.")
    item = commands.add_parser("block")
    item.add_argument("--question", required=True)
    for name in ("start", "done", "test", "reopen"):
        item = commands.add_parser(name)
        item.add_argument("task")
        if name == "done":
            item.add_argument("--result-file", required=True)
        if name == "test":
            item.add_argument("--stage", required=True, choices=("red", "pin"))
            item.add_argument("--note", required=True)
        if name == "reopen":
            item.add_argument("--reason", required=True)
    item = commands.add_parser("check")
    item.add_argument("name")
    item.add_argument("--force", action="store_true", help="rerun even when a passing check matches current contents")
    item = commands.add_parser("widen")
    item.add_argument("task")
    item.add_argument("--path", action="append", required=True)
    item.add_argument("--deliverable", required=True)
    item.add_argument("--reason", required=True)
    for name in ("show", "refine", "test-update"):
        item = commands.add_parser(name)
        item.add_argument("task")
        if name != "show":
            item.add_argument("--file", required=True)
        if name == "refine":
            item.add_argument("--reason", required=True)
        if name == "test-update":
            item.add_argument("--repair")
    item = commands.add_parser("note")
    item.add_argument("text")
    for name in ("review", "closeout"):
        item = commands.add_parser(name)
        item.add_argument("--file", required=True)
        if name == "closeout":
            item.add_argument("--answer")
    import tracking
    tracking.add_parsers(commands)
    return result


def main(argv=None):
    invoked_at = time.monotonic()
    args = parser().parse_args(argv)
    try:
        if args.command == "schema":
            print(json.dumps(SCHEMAS[args.name], indent=2))
            return 0
        if args.command == "init":
            output = initialize(args)
            import tracking
            tracking.record_call(Workflow(args.created_workflow), "init", time.monotonic() - invoked_at, True)
            print(output)
            return 0
        need(args.workflow, "use -w with the workflow directory")
        for key in ("answer", "reason", "question", "note"):
            if hasattr(args, key) and getattr(args, key) is not None:
                need(text(getattr(args, key)), f"--{key} must not be blank")
        wf = Workflow(args.workflow)
        if args.command == "status":
            print(json.dumps(wf.state, indent=2) if args.json else status(wf))
            return 0
        if args.command == "show":
            print(execute(wf, args))
            return 0
        import tracking
        if args.command in tracking.READ_ONLY:
            print(tracking.execute(wf, args, sys.modules[__name__]))
            return 0
        # Serialize state transitions; check workers release this lock during execution.
        with (wf.meta / "lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            wf = Workflow(args.workflow)
            wf.lock = lock
            if args.command == "hault":
                args.command = "halt"
            try:
                output = execute(wf, args)
                wf.save()
            except BaseException:
                tracking.record_call(wf, args.command, time.monotonic() - invoked_at, False)
                raise
            tracking.record_call(wf, args.command, time.monotonic() - invoked_at, True)
            if args.command == "final":
                write(wf.root / "metrics.json", tracking.metrics(wf))
        print(output)
        return 0
    except (Gate, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
