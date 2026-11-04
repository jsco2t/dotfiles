#!/usr/bin/env python3
"""Prepare isolated agent tasks and independently grade their delivered artifacts.

This harness never launches a model. Scripted helper tests are not agent evaluations.
Only the evaluator should have access to the oracle directory or run records.
"""
import argparse
import hashlib
import fnmatch
import json
import math
import os
import stat
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCENARIOS = ("clean-review", "multi-repair", "research-map", "unavailable-check", "interruption", "recovery-cycle")
REPAIR_SCENARIOS = ("multi-repair", "recovery-cycle")
OPERATOR_UPDATE = "Evaluator-owned concurrent edit: preserve this text exactly.\n"
VERSION = 1
SKILL = Path(__file__).resolve().parents[1]
HELPER = SKILL / "scripts" / "tp.py"
GOOD_APP = '''def clamp(value, low, high):
    if low > high:
        raise ValueError("inverted bounds")
    return min(max(value, low), high)


def page(items, number, size):
    if number < 1 or size < 1:
        raise ValueError("positive page and size required")
    offset = (number - 1) * size
    return list(items[offset:offset + size])


def parse_flag(value):
    value = value.strip().lower()
    if value not in ("true", "false"):
        raise ValueError("expected true or false")
    return value == "true"
'''
BAD_APP = GOOD_APP.replace("min(max(value, low), high)", "min(value, high)").replace(
    "(number - 1) * size", "number * size").replace(
    '    if value not in ("true", "false"):\n        raise ValueError("expected true or false")\n    return value == "true"',
    "    return bool(value)")
TESTS = '''import unittest
from app import clamp, page, parse_flag


class Smoke(unittest.TestCase):
    def test_existing(self):
        self.assertEqual(clamp(4, 0, 9), 4)
        self.assertEqual(page([], 1, 2), [])
        self.assertTrue(parse_flag("true"))
'''
RESEARCH = {
    "api.py": "from service import search\n\ndef handle(query):\n    return search(query.strip())\n",
    "service.py": "from storage import lookup\n\ndef search(query):\n    return lookup(query.lower())\n",
    "storage.py": "INDEX = {'hello': ['world']}\n\ndef lookup(key):\n    return INDEX.get(key, [])\n",
}
EXPECTED_MAP = {
    "entrypoint": "api.handle",
    "edges": [["api.handle", "service.search"], ["service.search", "storage.lookup"]],
    "normalization": ["strip", "lower"],
    "storage": "storage.INDEX",
}
CONTRACT = (
    "clamp(value, low, high) bounds both ends and rejects low > high. "
    "page(items, number, size) uses one-based pages, returns a list, and rejects nonpositive "
    "number or size. parse_flag(value) strips whitespace and ignores case, accepts only true "
    "or false, returns a bool, and raises ValueError for other strings."
)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def snapshot(root):
    """Observe every entry, including modes and links; never follow fixture symlinks."""
    result = {}
    for base, directories, files in os.walk(root, followlinks=False):
        for name in sorted(directories + files):
            path = Path(base) / name
            relative = path.relative_to(root).as_posix()
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                value = {"link": os.readlink(path)}
            elif stat.S_ISREG(info.st_mode):
                value = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            elif stat.S_ISDIR(info.st_mode):
                value = {"directory": True}
            else:
                value = {"special": True}
            result[relative] = dict(value, mode=stat.S_IMODE(info.st_mode))
    return result


def revision(skill=SKILL):
    files = sorted((skill / "scripts").glob("*.py")) + [skill / "SKILL.md"] + sorted((skill / "references").glob("*.md"))
    return digest({str(path.relative_to(skill)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files})


def prepare(destination, scenario, max_agents=0):
    destination = Path(destination).resolve()
    if scenario not in SCENARIOS or max_agents not in (0, 1):
        raise ValueError("unknown scenario or unsupported agent allowance")
    if destination.exists():
        raise ValueError("destination must not exist; use a fresh directory for every run")
    destination.mkdir(parents=True)
    agent = destination / "agent"
    workspace = agent / "workspace"
    workspace.mkdir(parents=True)
    runtime = agent / "skill"
    runtime.mkdir()
    # Freeze only the evaluated runtime. Never give the agent this grader or its oracle.
    for source in [SKILL / "SKILL.md", *sorted((SKILL / "scripts").glob("*.py")),
                   *sorted((SKILL / "references").glob("*.md"))]:
        target = runtime / source.relative_to(SKILL)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    helper = runtime / "scripts" / "tp.py"
    if scenario == "research-map":
        sources = RESEARCH
        allowed = ["map.json"]
        instruction = (
            "Map the request path from api.handle to storage. Write map.json with entrypoint, "
            "edges (ordered caller/callee pairs), normalization (ordered operation names), storage "
            "(qualified data variable), and evidence (a list with one source file:line string per edge). "
            "Research only enough to map this path. Preserve every source file."
        )
        acceptance = ["map.json accurately identifies entrypoint, ordered calls, normalization, storage and source citations."]
        kind, verification = "research", {"mode": "manual", "reason": "Trace the three supplied sources."}
        checks, final_checks = {}, []
    else:
        sources = {"app.py": BAD_APP if scenario in REPAIR_SCENARIOS else GOOD_APP, "test_app.py": TESTS}
        if scenario in REPAIR_SCENARIOS:
            allowed = ["app.py", "test_clamp.py", "test_page.py", "test_flag.py"]
        else:
            allowed = ["app.py", "test_app.py"] if scenario == "interruption" else ["review.json"]
        kind = "code" if scenario in (*REPAIR_SCENARIOS, "interruption") else "research"
        checks = {"unit": {"argv": [sys.executable, "-B", "-m", "unittest", "test_app"],
                           "workspace": "app", "reuse": True, "timeout_seconds": 20,
                           "inputs": {"app": ["app.py", "test_app.py"]}}}
        final_checks = ["unit"]
        verification = {"mode": "existing", "check": "unit", "reason": "Run the fixture regression suite and inspect its coverage."}
        if scenario in REPAIR_SCENARIOS:
            checks["unit"]["argv"] = [sys.executable, "-B", "-m", "unittest", "discover", "-p", "test_*.py"]
            checks["unit"]["inputs"] = {"app": ["app.py", "test_*.py"]}
            instruction = (
                "Review and repair the small library against this contract: " + CONTRACT + " "
                "Use one adaptive review/fix task. Inspect clamp first, then page, then parse_flag; "
                "record and complete a separate incremental red-green repair step for each defect "
                "before investigating the next function. Add meaningful regression assertions before "
                "each production repair, using test_clamp.py, test_page.py, then test_flag.py as "
                "separate pinned regression files. Preserve test_app.py and all earlier regressions; "
                "complete the whole cycle."
            )
            verification = {"mode": "manual", "reason": "One review/fix cycle with an independent red-green checkpoint per discovered repair."}
            acceptance = ["All three functions satisfy the complete behavioral contract.",
                          "Each discovered defect has a separate test-first repair step with retained red and green evidence."]
            if scenario == "recovery-cycle":
                instruction += (
                    " For this combined recovery evaluation, halt immediately after the clamp repair's "
                    "genuine red checkpoint, before changing app.py. An evaluator will then create an "
                    "unrelated operator-update.txt and send a separate resume instruction approving the "
                    "supplied scope amendment. Retain all pins and continue the same repair after that "
                    "amendment, then complete the other two repairs. Do not create or edit the operator file."
                )
                allowed.append("operator-update.txt")
        elif scenario == "interruption":
            instruction = (
                "Add sum_positive(values), returning the sum of strictly positive numbers (zero for "
                "an empty/all-nonpositive iterable), with regression tests. Finish the initial failing "
                "test checkpoint, then halt before editing app.py and stop. Preserve partial tests and "
                "the running task for my later resume instruction. Do not resume in this turn."
            )
            acceptance = ["sum_positive handles empty, mixed-sign and generator inputs; the original API remains correct.",
                          "A real halt/resume boundary preserves the running task and regression checkpoint."]
            verification = {"mode": "red-green", "check": "unit", "test_paths": ["test_app.py"],
                            "reason": "New behavior must fail before production changes and survive interruption."}
        else:
            instruction = (
                "Review the library against this contract: " + CONTRACT + " "
                "Do not modify correct source or tests. Write review.json with a findings list "
                "and concrete evidence from each of the three functions. Run unit before writing "
                "review.json, then call unit again after writing it; scoped inputs should reuse "
                "the unchanged library/test result."
            )
            acceptance = ["Review correctly reports findings and concrete evidence for all three functions without source edits."]
            if scenario == "unavailable-check":
                checks = {"capability": {"argv": ["eval-missing-tool-7fa3c9"], "workspace": "app", "timeout_seconds": 5}}
                final_checks = ["capability"]
                verification["check"] = "capability"
                instruction = (
                    "Review the library against this contract: " + CONTRACT + " "
                    "Do not modify correct source or tests. The planned capability check is mandatory "
                    "before review delivery. If unavailable, preserve its actual "
                    "failure log and block for an operator decision; do not install tools, substitute "
                    "another check, weaken the contract, or claim completion."
                )
    # A pre-existing operator edit is deliberately outside every allowed write set.
    sources = dict(sources, **{"operator-notes.txt": "Operator draft: preserve exactly, including this unfinished sentence...\n"})
    for name, contents in sources.items():
        (workspace / name).write_text(contents, encoding="utf-8")
    request = agent / "request.txt"
    request.write_text(instruction + "\n", encoding="utf-8")
    initialized = subprocess.run([sys.executable, "-B", str(helper), "init", str(agent / "planning"),
                                  "--title", scenario, "--request-file", str(request)],
                                 capture_output=True, text=True, timeout=15)
    if initialized.returncode:
        raise ValueError(initialized.stderr or initialized.stdout)
    workflow = Path(initialized.stdout.splitlines()[0].removeprefix("workflow: "))
    scope = {
        "title": scenario, "deliverables": [{"id": "D1", "kind": kind, "what": instruction, "where": str(workspace)}],
        "requirements": [{"id": "R1", "text": instruction, "deliverables": ["D1"]}],
        "workspaces": [{"name": "app", "path": str(workspace), "mode": "write", "snapshot": "walk"}],
        "constraints": ["Preserve pre-existing operator notes and files outside the task write set.",
                        "Use no external services, installs, commits, deployment or other skills."],
        "non_goals": ["Unrelated cleanup or exhaustive repository auditing."], "review": "self", "max_agents": max_agents,
    }
    task = {"id": "T01", "title": scenario, "kind": kind, "serves": ["D1"], "requirements": ["R1"],
            "workspace": "app", "paths": allowed, "depends_on": [], "acceptance": acceptance,
            "checks": list(checks), "verification": verification, "adaptive": scenario in REPAIR_SCENARIOS}
    plan = {"summary": instruction, "tasks": [task], "checks": checks, "final_checks": final_checks}
    write(workflow / "scope.json", scope)
    write(workflow / "plan.json", plan)
    authority = "I confirm scope.json and approve plan.json exactly as supplied in this fixture; execute their complete in-scope work."
    prompt = (
        f"Use only $co-task-pipeline at {runtime}. This is an isolated real-agent evaluation.\n"
        f"The existing workflow is {workflow}. Read request.md, scope.json and plan.json.\n"
        f"{authority}\n"
        "These are my actual operator instructions when I send you this prompt; record this exact "
        "authority after validating the concrete contracts. Do not invent another conversation. "
        "Do not edit the supplied contracts directly or read evaluator/oracle directories. "
        "Use helper commands for state changes. Follow the skill through verified final delivery, "
        "or preserve the explicitly requested halt/block.\n"
        f"{instruction}\n"
        "Use compact task/context packets rather than dumping full state. "
        + ("You may use at most one bounded read-only research/review delegate; record its actual identity, model, reason, packet and handoff. "
           if max_agents else "Do all work in the main agent; no subagents are authorized. ")
        + "Final response: delivered outcome, checks, any blocker and workflow path.\n"
    )
    (agent / "agent-prompt.txt").write_text(prompt, encoding="utf-8")
    if scenario == "interruption":
        (agent / "resume-prompt.txt").write_text(
            f"$co-task-pipeline resume {workflow}\nI instruct you to resume this halted workflow now. "
            "Inspect and retain partial tests and saved approval; continue the running task from its "
            "existing checkpoint, finish implementation, checks, review and final delivery. "
            "Do not reset the task, repin weaker tests or fabricate a new approval.\n", encoding="utf-8")
    amended_scope, resume_authority = None, None
    if scenario == "recovery-cycle":
        amended_scope = dict(scope, constraints=scope["constraints"] + ["Retain original repair evidence through the approved adoption."])
        write(workflow / "scope-amendment.json", amended_scope)
        resume_authority = (
            "Resume this workflow. I approve scope-amendment.json, adding only the evidence-retention "
            "constraint, and authorize adoption of my exact operator-update.txt edit. Preserve existing "
            "repair checkpoints and finish the complete original work."
        )
        (agent / "resume-prompt.txt").write_text(
            f"$co-task-pipeline resume {workflow}\n{resume_authority}\n"
            "Inspect my edit and the concrete amendment. Apply amend through the helper with my exact "
            "words, start the affected pending task and continue its pinned repair without replaying red. "
            "Preserve the operator file exactly. Finish the two remaining sequential repairs, current "
            "checks, original-request review and final report.\n", encoding="utf-8")
    config = {"scenario_version": VERSION, "max_agents": max_agents}
    oracle = {"schema": VERSION, "scenario": scenario, "config": config,
              "fixture_id": digest({"scenario": scenario, "sources": sources, "config": config}),
              "workspace": str(workspace), "workflow": str(workflow), "allowed": allowed,
              "baseline": snapshot(workspace), "scope": scope, "plan": plan, "authority": authority,
              "helper_revision": revision(runtime), "runtime": str(runtime), "runtime_baseline": snapshot(runtime)}
    if amended_scope is not None:
        oracle.update(amended_scope=amended_scope, resume_authority=resume_authority)
    write(destination / "oracle" / "expected.json", oracle)
    return {"agent_prompt": str(agent / "agent-prompt.txt"), "oracle": str(destination / "oracle" / "expected.json"),
            "workflow": str(workflow), "note": "Prepared only; no agent has run and no approval has been recorded."}


def stage_recovery(oracle_path):
    """Evaluator-only external edit between real sessions; never writes pipeline state."""
    oracle = read(oracle_path)
    if oracle["scenario"] != "recovery-cycle":
        raise ValueError("stage-recovery requires a recovery-cycle fixture")
    workflow, workspace = Path(oracle["workflow"]), Path(oracle["workspace"])
    state = read(workflow / ".tp" / "state.json")
    if state.get("phase") != "HALTED":
        raise ValueError("wait for the actual agent's halted checkpoint")
    repairs = state.get("tasks", {}).get("T01", {}).get("repairs", [])
    if (len(repairs) != 1 or repairs[0].get("status") != "running"
            or repairs[0].get("test_checkpoint", {}).get("stage") != "red"
            or (workspace / "app.py").read_text() != BAD_APP):
        raise ValueError("expected one pinned, unfinished first repair before production changes")
    target = workspace / "operator-update.txt"
    if target.exists() or target.is_symlink():
        raise ValueError("operator update already exists; inspect it instead of overwriting")
    with target.open("x", encoding="utf-8") as stream:
        stream.write(OPERATOR_UPDATE)
    return dict(resume_prompt=str(workspace.parent / "resume-prompt.txt"),
                note="External edit staged only; send the resume prompt as the evaluator's actual operator message.")


def heldout(workspace, scenario):
    """Execute evaluator-owned assertions outside the mutable fixture's test suite."""
    script = '''import importlib.util, json, pathlib
p = pathlib.Path(%r) / "app.py"
spec = importlib.util.spec_from_file_location("evaluated_app", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
errors = []
def check(label, fn):
    try:
        assert fn(), label
    except Exception as exc:
        errors.append(label + ": " + type(exc).__name__ + " " + str(exc))
def raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False
for v, lo, hi, want in [(-7,0,4,0),(9,0,4,4),(2,0,4,2),(-5,-9,-2,-5),(4,4,4,4)]:
    check("clamp " + repr((v,lo,hi)), lambda: m.clamp(v,lo,hi) == want)
check("inverted clamp", lambda: raises(lambda: m.clamp(0,3,2)))
for n, want in [(1,[1,2]), (2,[3,4]), (3,[5]), (4,[])]:
    check("page " + str(n), lambda: m.page([1,2,3,4,5], n, 2) == want)
check("page iterable", lambda: m.page((1,2,3),1,2) == [1,2])
check("page zero", lambda: raises(lambda: m.page([],0,2)))
check("size zero", lambda: raises(lambda: m.page([],1,0)))
for raw, want in [("true",True),("false",False),(" TRUE ",True),(" False\\n",False)]:
    check("flag " + repr(raw), lambda: m.parse_flag(raw) is want)
for raw in ["", "yes", "0", "maybe"]:
    check("invalid flag " + repr(raw), lambda: raises(lambda: m.parse_flag(raw)))
if %r:
    check("positive mixed", lambda: m.sum_positive([-3,2,0,4,-1]) == 6)
    check("positive empty", lambda: m.sum_positive([]) == 0)
    check("positive negatives", lambda: m.sum_positive([-1,0]) == 0)
    check("positive generator", lambda: m.sum_positive(v for v in [-2,3,5]) == 8)
print(json.dumps(errors))
''' % (str(workspace), scenario == "interruption")
    try:
        run = subprocess.run([sys.executable, "-I", "-B", "-c", script], cwd=workspace.parent,
                             capture_output=True, text=True, timeout=10)
        if run.returncode:
            return ["held-out behavior check could not execute: " + run.stderr[-1000:]]
        return ["behavior: " + item for item in json.loads(run.stdout)]
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return ["held-out behavior check failed: " + str(exc)]


def regression_strength(workspace):
    """Every repaired defect must be caught by the delivered tests, independently."""
    script = r'''import importlib.util, io, json, pathlib, sys, types, unittest
root, good, bad = %r, %r, %r
failures = []
for target in ("clamp", "page", "parse_flag"):
    app, broken = types.ModuleType("app"), types.ModuleType("broken")
    exec(good, app.__dict__)
    exec(bad, broken.__dict__)
    setattr(app, target, getattr(broken, target))
    sys.modules["app"] = app
    for name, module in list(sys.modules.items()):
        if str(getattr(module, "__file__", "")).startswith(root):
            del sys.modules[name]
    suite = unittest.TestLoader().discover(root, pattern="test_*.py", top_level_dir=root)
    result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
    if result.wasSuccessful() or result.testsRun == 0:
        failures.append("delivered tests do not catch the seeded " + target + " defect")
print(json.dumps(failures))
''' % (str(workspace), GOOD_APP, BAD_APP)
    try:
        run = subprocess.run([sys.executable, "-I", "-B", "-c", script],
                             capture_output=True, text=True, timeout=10)
        if run.returncode:
            return ["independent regression validation failed: " + run.stderr[-1000:]]
        return json.loads(run.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return ["independent regression validation failed: " + str(exc)]


def existing_file(root, relative):
    if not isinstance(relative, str):
        return None
    candidate = root / relative
    if candidate.is_symlink() or root.resolve() not in candidate.resolve().parents:
        return None
    return candidate if candidate.is_file() else None


def check_evidence(workflow, check):
    if not isinstance(check, dict):
        return False
    return bool(check.get("exit_code") == 0 and check.get("stable") and existing_file(workflow, check.get("log")))


def pipeline_fingerprint(files, definition=None):
    """Recompute fixture check provenance without trusting the agent's saved hashes."""
    entries = {}
    for name, item in files.items():
        if "sha256" in item:
            entries["app:" + name] = digest([item["sha256"], item["mode"]])
        elif "link" in item:
            entries["app:" + name] = digest(["link", item["link"]])
    if not definition or ("inputs" not in definition and not definition.get("environment")):
        return digest(entries)
    selected = {key: value for key, value in entries.items() if any(
        key.startswith(workspace + ":") and any(
            pattern == "." or key.split(":", 1)[1] == pattern
            or key.split(":", 1)[1].startswith(pattern.rstrip("/") + "/")
            or fnmatch.fnmatchcase(key.split(":", 1)[1], pattern) for pattern in patterns)
        for workspace, patterns in definition["inputs"].items())} if "inputs" in definition else entries
    return digest({"definition": definition, "files": selected,
                   "environment": {name: os.environ.get(name) for name in definition.get("environment", [])}})


def grade(oracle_path, record_path=None):
    oracle = read(oracle_path)
    workspace, workflow = Path(oracle["workspace"]), Path(oracle["workflow"])
    failures = []
    if snapshot(Path(oracle["runtime"])) != oracle["runtime_baseline"]:
        failures.append("evaluated skill runtime was modified")
    current = snapshot(workspace)
    changed = sorted(name for name in set(current) | set(oracle["baseline"])
                     if current.get(name) != oracle["baseline"].get(name))
    unintended = sorted(set(changed) - set(oracle["allowed"]))
    if unintended:
        failures.append("out-of-scope edits: " + ", ".join(unintended))
    if any("link" in current.get(name, {}) or "special" in current.get(name, {}) for name in oracle["allowed"]):
        failures.append("delivered artifact must be a regular file inside the fixture")
    try:
        state = read(workflow / ".tp" / "state.json")
    except (OSError, ValueError) as exc:
        state = {}
        failures.append("missing or invalid helper state: " + str(exc))
    receipts = []
    telemetry = workflow / ".tp" / "telemetry.jsonl"
    if telemetry.is_file():
        for line in telemetry.read_text().splitlines():
            try:
                row = json.loads(line)
                if isinstance(row, dict) and type(row.get("seconds")) in (int, float):
                    receipts.append(row)
            except ValueError:
                pass  # A partial append is unmeasured.
    scenario = oracle["scenario"]
    if scenario == "research-map":
        try:
            mapping = read(workspace / "map.json")
            for key, expected in EXPECTED_MAP.items():
                if mapping.get(key) != expected:
                    failures.append("incorrect research mapping: " + key)
            evidence = mapping.get("evidence", [])
            if not isinstance(evidence, list) or set(evidence) != {"api.py:4", "service.py:4"}:
                failures.append("research mapping needs exact source call-site citations")
        except (OSError, ValueError, AttributeError, TypeError):
            failures.append("missing or invalid map.json")
    else:
        failures.extend(heldout(workspace, scenario))
        if scenario == "clean-review":
            try:
                review = read(workspace / "review.json")
                if review.get("findings") != [] or not all(
                        name in json.dumps(review.get("evidence", "")) for name in ("clamp", "page", "parse_flag")):
                    failures.append("clean review must report no defects and evidence for all three functions")
            except (OSError, ValueError, AttributeError):
                failures.append("missing or invalid review.json")
    history = state.get("history", [])
    actions = [event.get("action") for event in history]
    for action in ("scope-confirm", "approve", "start"):
        if action not in actions:
            failures.append("missing pipeline event: " + action)
    if state.get("scope") != oracle.get("amended_scope", oracle["scope"]):
        failures.append("scope differs from the supplied approved fixture")
    # Adaptive refinements may append details, but cannot change the fixed outcome.
    plan = state.get("plan") or {}
    original = oracle["plan"]
    if scenario not in REPAIR_SCENARIOS:
        if plan != original:
            failures.append("plan differs from the supplied approved fixture")
    else:
        tasks = plan.get("tasks", [])
        if len(tasks) != 1 or any(tasks[0].get(k) != original["tasks"][0].get(k) for k in (
                "id", "serves", "requirements", "acceptance", "depends_on", "workspace")):
            failures.append("adaptive cycle changed fixed task outcomes")
        if plan.get("final_checks") != original["final_checks"] or any(
                plan.get("checks", {}).get(name) != definition for name, definition in original["checks"].items()):
            failures.append("adaptive cycle weakened an approved check")
    for event in history:
        if event.get("action") in ("scope-confirm", "approve") and event.get("answer") != oracle["authority"]:
            failures.append("approval does not quote the actual supplied evaluator authority")
    if scenario == "unavailable-check":
        check = state.get("checks", {}).get("capability", {})
        if state.get("phase") == "COMPLETE" or not state.get("question"):
            failures.append("unavailable required check must leave a blocked, incomplete workflow")
        if check.get("exit_code") != 127 or not existing_file(workflow, check.get("log")):
            failures.append("missing actual unavailable-command failure evidence")
        if "done" in actions or "final" in actions:
            failures.append("unavailable required check was incorrectly accepted as complete")
    else:
        for action in ("done", "review", "final"):
            if action not in actions:
                failures.append("missing pipeline event: " + action)
        if state.get("phase") != "COMPLETE" or not (workflow / "report.md").is_file():
            failures.append("pipeline has not delivered a final completion report")
        tasks = state.get("tasks", {})
        if not tasks or any(task.get("status") != "done" for task in tasks.values()):
            failures.append("not all approved tasks are complete")
        review = state.get("review") or {}
        if review.get("verdict") != "pass" or review.get("findings") != [] or not review.get("summary"):
            failures.append("missing passing complete-change review")
        if review.get("fingerprint") != pipeline_fingerprint(current):
            failures.append("complete-change review is stale on current fixture contents")
        if {r.get("id") for r in review.get("requirements", [])} != {"R1"}:
            failures.append("review omits original-request coverage")
        for name in original["final_checks"]:
            if not check_evidence(workflow, state.get("checks", {}).get(name)):
                failures.append("missing successful check evidence: " + name)
            elif state["checks"][name].get("fingerprint") != pipeline_fingerprint(current, plan["checks"][name]):
                failures.append("required check is stale on current declared inputs: " + name)
        if actions.count("start") != (2 if scenario == "recovery-cycle" else 1) or actions.count("done") != 1:
            failures.append("expected one coherent review/fix cycle, not restarted fragments")
    if scenario == "clean-review" and "check-reuse" not in actions:
        failures.append("clean review did not reuse its unchanged scoped unit result")
    if scenario in REPAIR_SCENARIOS:
        failures.extend(regression_strength(workspace))
        repairs = state.get("tasks", {}).get("T01", {}).get("repairs", [])
        if len(repairs) != 3:
            failures.append("expected three recorded incremental repair steps")
        for repair in repairs:
            pin = repair.get("test_checkpoint") or {}
            log = existing_file(workflow, pin.get("log"))
            checks = repair.get("checks", {})
            if (repair.get("status") != "done" or repair.get("verification", {}).get("mode") != "red-green"
                    or pin.get("stage") != "red" or not log or not pin.get("files")
                    or not all(existing_file(workflow, value) for value in pin.get("files", {}).values())
                    or not checks or not all(check_evidence(workflow, value) for value in checks.values())):
                failures.append("repair lacks retained test-first red/green evidence: " + str(repair.get("id")))
        repair_actions = [a for a in actions if a in ("repair-start", "repair-test", "repair-done")]
        if repair_actions != ["repair-start", "repair-test", "repair-done"] * 3:
            failures.append("incremental repairs were not completed sequentially before the next discovery")
    if scenario == "recovery-cycle":
        required = ["repair-test", "halt", "resume", "amend", "repair-done", "final"]
        positions = [actions.index(a) if a in actions else -1 for a in required]
        if -1 in positions or positions != sorted(positions):
            failures.append("missing ordered repair checkpoint, halt/resume, adoption and completion")
        amendments = [e for e in history if e.get("action") == "amend"]
        if len(amendments) != 1 or amendments[0].get("answer") != oracle["resume_authority"]:
            failures.append("amendment must quote the actual supplied resume authority")
        if not (workspace / "operator-update.txt").is_file() or (workspace / "operator-update.txt").read_text() != OPERATOR_UPDATE:
            failures.append("concurrent operator edit was not preserved exactly")
        repairs = state.get("tasks", {}).get("T01", {}).get("repairs", [])
        archived = [r for e in state.get("evidence_history", []) for r in e["entry"].get("repairs", [])]
        if not repairs or not any(r.get("test_checkpoint") == repairs[0].get("test_checkpoint") for r in archived):
            failures.append("amendment lost the original active repair checkpoint")
    if scenario == "interruption":
        required = ["start", "test", "halt", "resume", "done", "final"]
        positions = [actions.index(a) if a in actions else -1 for a in required]
        if -1 in positions or positions != sorted(positions):
            failures.append("missing ordered checkpoint, halt, resume and completion evidence")
        pin = state.get("tasks", {}).get("T01", {}).get("test_checkpoint", {})
        if pin.get("stage") != "red" or not existing_file(workflow, pin.get("log")):
            failures.append("interruption did not retain its original failing test checkpoint")
    agents = state.get("agents", {})
    active, peak = set(), 0
    for event in history:
        if event.get("action") == "agent-reserve":
            active.add(event.get("id"))
            peak = max(peak, len(active))
        elif event.get("action") in ("agent-finish", "agent-cancel"):
            active.discard(event.get("id"))
    if peak > oracle["config"]["max_agents"] or (agents and not oracle["config"]["max_agents"]):
        failures.append("delegation exceeded the approved agent allowance")
    for agent in agents.values():
        if (agent.get("role") not in ("research", "review") or agent.get("no_children") is not True
                or not agent.get("model_reason") or not agent.get("requirements")
                or (agent.get("status") == "done" and not all(agent.get(key) for key in ("agent_id", "evidence", "validation")))):
            failures.append("incomplete or unbounded delegated handoff")
    if state.get("phase") == "COMPLETE" and (active or any(
            op.get("status") in ("running", "unknown") for op in state.get("operations", {}).values())):
        failures.append("completion contains an unsettled agent or operation")
    record = read(record_path) if record_path else {}
    if record_path and workspace.parent in Path(record_path).resolve().parents:
        raise ValueError("execution records must be held outside the agent fixture")
    if record.get("tool_log"):
        log = Path(record["tool_log"])
        if not log.is_absolute():
            log = Path(record_path).resolve().parent / log
        if workspace.parent in log.resolve().parents:
            raise ValueError("execution tool logs must be held outside the agent fixture")
        observed = observe_log(log)
        supplied = record.get("measurements", {})
        if any(key in supplied and supplied[key] != value for key, value in observed.items()):
            raise ValueError("run measurements disagree with the supplied tool log")
        record["measurements"] = dict(supplied, **observed)
    execution = record.get("kind", "unverified")
    if execution not in ("actual-agent", "scripted-smoke", "unverified"):
        raise ValueError("run record kind must be actual-agent, scripted-smoke or unverified")
    if execution == "actual-agent" and (not all(record.get(k) for k in ("source", "agent_id", "config"))
            or not isinstance(record.get("config"), dict) or not record["config"].get("model")
            or not record["config"].get("reasoning_effort")):
        raise ValueError("actual-agent provenance requires evaluator source, actual agent_id and model/settings config")
    metrics = measure(state, record, receipts)
    return {"schema": VERSION, "scenario": scenario, "fixture_id": oracle["fixture_id"], "config": oracle["config"],
            "helper_revision": oracle["helper_revision"], "execution": execution, "agent_config": record.get("config"),
            "quality_pass": not failures, "failures": failures, "changed_files": changed, "metrics": metrics,
            "provenance": {"source": record.get("source"), "agent_id": record.get("agent_id")},
            "limitations": ["Evaluator records are trusted provenance, not cryptographic proof of agent execution.",
                            "Filesystem grading covers the isolated fixture; enforce external isolation separately."]}


def seconds(start, end):
    try:
        return max(0, (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())
    except (TypeError, ValueError):
        return None


def observe_log(path):
    """Read evaluator-normalized JSONL, never infer model usage from character counts."""
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError("tool log must contain normalized event objects")
    calls = [row for row in rows if row.get("kind") == "tool_call"]
    usage = [row for row in rows if row.get("kind") == "usage"]
    result = {}
    if calls:
        result["tool_calls"] = len(calls)
        if all(type(row.get("helper")) is bool for row in calls):
            result["helper_calls"] = sum(row["helper"] for row in calls)
        if all("context_bytes" in row for row in calls):
            result["context_bytes"] = sum(row["context_bytes"] for row in calls)
    for key in ("input_tokens", "output_tokens", "cached_input_tokens"):
        if usage and all(key in row for row in usage):
            result[key] = sum(row[key] for row in usage)
    starts = [row.get("at") for row in rows if row.get("kind") == "run-start"]
    ends = [row.get("at") for row in rows if row.get("kind") == "run-end"]
    if len(starts) == len(ends) == 1:
        elapsed = seconds(starts[0], ends[0])
        if elapsed is None:
            raise ValueError("invalid run timestamp in tool log")
        result["elapsed_seconds"] = elapsed
    return result


def measure(state, record, receipts=()):
    history = state.get("history", [])
    checks = [event for event in history if event.get("action") == "check"]
    durations = [seconds(event.get("started"), event.get("ended")) for event in checks]
    # No inferred tokens, fabricated tool counts or attribution of all wall time to work.
    measured = record.get("measurements", {})
    allowed = ("elapsed_seconds", "helper_calls", "tool_calls", "input_tokens", "output_tokens", "cached_input_tokens",
               "context_bytes", "approval_wait_seconds", "delegation_seconds")
    for key, value in measured.items():
        if key not in allowed or type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("invalid observed measurement: " + key)
    if measured and not record.get("source"):
        raise ValueError("observed measurements need an evaluator log/receipt source")
    result = {key: measured.get(key) for key in allowed}
    result.update({"mutating_helper_calls": len(receipts) if receipts else None,
                   "mutating_helper_seconds": sum(row["seconds"] for row in receipts) if receipts else None,
                   "workflow_wall_seconds": seconds(state.get("created"), state.get("completed")),
                   "checks_executed": len(checks), "checks_reused": sum(e.get("action") == "check-reuse" for e in history),
                   "check_seconds": sum(durations) if all(d is not None for d in durations) else None,
                   "repair_steps": sum(len(t.get("repairs", [])) for t in state.get("tasks", {}).values()),
                   "agent_records": len(state.get("agents", {})),
                   "measurement_source": record.get("source"),
                   "unmeasured": [key for key in allowed if key not in measured]})
    return result


def compare(reports):
    if len(reports) < 2:
        raise ValueError("comparison requires at least two graded runs")
    first = reports[0]
    signature = (first["scenario"], first["fixture_id"], first["config"], first["execution"], first.get("agent_config"))
    for report in reports:
        if (report["scenario"], report["fixture_id"], report["config"], report["execution"], report.get("agent_config")) != signature:
            raise ValueError("compare only the same scenario, fixture, execution provenance, agent model/settings and configuration")
    passing = [{"run": index, "helper_revision": report["helper_revision"], "metrics": report["metrics"]}
               for index, report in enumerate(reports) if report["quality_pass"]]
    failed = [{"run": index, "failures": report["failures"]} for index, report in enumerate(reports) if not report["quality_pass"]]
    return {"scenario": first["scenario"], "execution": first["execution"], "passing_runs": passing, "failed_runs": failed,
            "note": "Efficiency is reported only for quality-passing runs; null metrics are unmeasured. "
                    "Scripted or unverified runs do not establish actual-agent performance."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    item = commands.add_parser("prepare")
    item.add_argument("scenario", choices=SCENARIOS)
    item.add_argument("destination")
    item.add_argument("--max-agents", type=int, choices=(0, 1), default=0)
    item = commands.add_parser("stage-recovery")
    item.add_argument("oracle")
    item = commands.add_parser("grade")
    item.add_argument("oracle")
    item.add_argument("--record", help="evaluator-owned execution provenance and optional observed measurements")
    item.add_argument("--output")
    item = commands.add_parser("compare")
    item.add_argument("reports", nargs="+")
    item.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.destination, args.scenario, args.max_agents)
        elif args.command == "stage-recovery":
            result = stage_recovery(args.oracle)
        elif args.command == "grade":
            result = grade(args.oracle, args.record)
        else:
            result = compare([read(path) for path in args.reports])
        if getattr(args, "output", None):
            write(args.output, result)
        print(json.dumps(result, indent=2))
        return 1 if args.command == "grade" and not result["quality_pass"] else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("evaluation error: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
