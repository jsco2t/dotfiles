"""Agent-owned test corrections with real baseline execution and bound review evidence."""
from pathlib import Path
import os

import checks
from snapshot import digest, take


def target(wf, task_id, repair_id=None):
    task = next(t for t in wf.state["plan"]["tasks"] if t["id"] == task_id)
    entry = wf.tasks()[task_id]
    item = next((r for r in entry.get("repairs", []) if r["id"] == repair_id), {}) if repair_id else entry
    return task, entry, item


def revision(wf, task_id, repair_id=None, proof_id=None):
    task, _, item = target(wf, task_id, repair_id)
    pin = item.get("test_checkpoint", {})
    scope, plan = wf.contract()
    snapshot = wf.snapshot(scope, plan)
    # Mandatory test hashes/contract bind even when a reviewer narrows optional inputs.
    return digest([task, item.get("verification"), pin,
                   {p: snapshot.get(p) for p in pin.get("hashes", {})},
                   wf.state.get("proofs", {}).get(proof_id) if proof_id else None])


def baseline_snapshot(proof):
    root = Path(proof["baseline"])
    return take([dict(name="baseline", path=str(root), mode="read", snapshot=proof["snapshot_mode"])],
                root / ".tp-proof-exclude", [dict(workspace="baseline", paths=proof["test_paths"])], {})


def execute(wf, args, api):
    wf.runnable()
    task, entry, item = target(wf, args.task, args.repair)
    api.need(entry["status"] == "running" and item.get("test_checkpoint"), "correction proof needs a running task with an existing pin")
    api.need(wf.state.get("governance") == "autonomous", "legacy runs use their original correction contract")
    scope, plan = wf.contract()
    snapshot, _ = wf.edits(scope, plan, task, entry["before"])
    api.verification_evidence.preserve(wf, snapshot, api.need, exclude=(args.task, args.repair))
    baseline = Path(args.baseline).expanduser().resolve()
    api.need(baseline.is_dir(), "baseline must be a prepared isolated directory")
    for workspace in scope["workspaces"]:
        live = Path(workspace["path"])
        api.need(baseline != live and live not in baseline.parents and baseline not in live.parents,
                 "baseline must be isolated outside all live workspace roots")
    verification = item["verification"] if args.repair else task["verification"]
    command = wf.state["plan"]["checks"][verification["check"]]["argv"]
    for workspace in scope["workspaces"]:
        live = str(Path(workspace["path"]))
        api.need(not any(live in arg for arg in command),
                 "baseline command references a live workspace; use a relative isolated runner")
        api.need(not any(live in os.environ.get(name, "") for name in ("PYTHONPATH", "NODE_PATH", "DART_PACKAGE_CONFIG")),
                 "baseline language search path references a live workspace; use an isolated environment")
    for directory, dirs, files in os.walk(baseline, followlinks=False):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in dirs + files:
            path = Path(directory) / name
            if path.is_symlink():
                resolved = path.resolve()
                api.need(resolved == baseline or baseline in resolved.parents,
                         "baseline symlinks must not escape into live code or unrecorded inputs")
    proof = dict(task=args.task, repair=args.repair, baseline=str(baseline), identity=args.identity,
                 snapshot_mode=args.snapshot, test_paths=verification["test_paths"],
                 tests={p: snapshot.get(p) for p in item["test_checkpoint"]["hashes"]},
                 check_definition=plan["checks"][verification["check"]])
    before = baseline_snapshot(proof)
    for relative in verification["test_paths"]:
        api.need(before.get("baseline:" + relative) == snapshot.get(task["workspace"] + ":" + relative)
                 and before.get("baseline:" + relative), "baseline must contain the exact corrected test files")
    proof["baseline_fingerprint"] = digest(before)
    result = checks.run(wf, verification["check"], scope, plan, proof=proof)
    expected = result["exit_code"] > 0 and result["exit_code"] not in (124, 127, 130) if item["test_checkpoint"]["stage"] == "red" else result["exit_code"] == 0
    api.need(expected and result["stable"], "baseline did not produce a stable expected failure/pass; inspect the actual proof log")
    return f"Baseline proof recorded: {result['operation']}; inspect {result['log']} for a behavior failure, never an import/build/setup error."
