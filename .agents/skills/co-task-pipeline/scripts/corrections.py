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


def writer(wf, task, entry, need):
    """A later delivery unit may own an honest edit to an earlier unit's tests."""
    if entry["status"] == "running":
        return task, entry
    active = next((t for t in wf.state["plan"]["tasks"] if wf.tasks()[t["id"]]["status"] == "running"), None)
    need(wf.state.get("governance") == "autonomous" and entry["status"] == "done" and active is not None,
         "test correction needs a running writer; start the owner or a later task that owns the changed tests")
    return active, wf.tasks()[active["id"]]


def affected(wf, task_id, repair_id, snapshot):
    """Group shared-file pin changes so one review preserves all original regressions."""
    _, _, primary = target(wf, task_id, repair_id)
    paths = set(primary.get("test_checkpoint", {}).get("hashes", {}))
    result = []
    for task in wf.state["plan"]["tasks"]:
        entry = wf.tasks()[task["id"]]
        for rid, item in [(None, entry)] + [(r["id"], r) for r in entry.get("repairs", [])]:
            pin = item.get("test_checkpoint")
            if not pin or item.get("status") == "superseded":
                continue
            delta = {p for p, value in pin["hashes"].items() if snapshot.get(p) != value}
            if delta and delta <= paths:
                result.append((task, rid, item))
    return result


def revision(wf, task_id, repair_id=None, proof_id=None, proof_ids=()):
    task, _, item = target(wf, task_id, repair_id)
    pin = item.get("test_checkpoint", {})
    scope, plan = wf.contract()
    snapshot = wf.snapshot(scope, plan)
    # Mandatory test hashes/contract bind even when a reviewer narrows optional inputs.
    active = [t for t in plan["tasks"] if wf.tasks()[t["id"]]["status"] == "running"]
    related = [[owner, rid, entry["test_checkpoint"]] for owner, rid, entry in affected(wf, task_id, repair_id, snapshot)]
    return digest([task, active, related, item.get("verification"), pin,
                   {p: snapshot.get(p) for p in pin.get("hashes", {})},
                   [[pid, wf.state.get("proofs", {}).get(pid)] for pid in ([proof_id] if proof_id else []) + list(proof_ids)]])


def verify_regression(wf, task, rid, item, proof, hashes, agent, api):
    """Validate each old pin's own proof; grouped updates do not erase obligations."""
    api.need(isinstance(proof, dict) and proof.get("basis") in ("retained", "reproduced") and api.text(proof.get("evidence")),
             "correction needs independently verified regression evidence for every affected pin")
    if proof["basis"] == "retained":
        api.need(proof.get("assertions_unchanged") is True and proof.get("original_checkpoint_valid") is True,
                 "retained proof requires unchanged cases/assertions and a genuine original behavior failure; otherwise reproduce")
        return None
    receipt = wf.state.get("proofs", {}).get(proof.get("operation"), {})
    details = receipt.get("proof", {})
    verification = item["verification"] if rid else task["verification"]
    api.need(receipt and receipt.get("stable") and details.get("task") == task["id"]
             and details.get("repair") == rid and details.get("tests") == hashes
             and details.get("check_definition") == wf.state["plan"]["checks"][verification["check"]]
             and proof.get("operation") in ([agent.get("proof")] + agent.get("proofs", [])),
             "reproduced correction needs the actual stable correction-proof receipt for these exact tests and reviewer")
    stage = details.get("stage", item["test_checkpoint"]["stage"])
    api.need(stage == "red" or stage == item["test_checkpoint"]["stage"], "cannot weaken behavioral red to a passing pin")
    code = receipt["exit_code"]
    api.need((code > 0 and code not in (124, 127, 130)) if stage == "red" else code == 0,
             "baseline must demonstrate the intended failure/pass, not a launch error or timeout")
    return receipt


def baseline_snapshot(proof):
    root = Path(proof["baseline"])
    return take([dict(name="baseline", path=str(root), mode="read", snapshot=proof["snapshot_mode"])],
                root / ".tp-proof-exclude", [dict(workspace="baseline", paths=proof["test_paths"])], {})


def execute(wf, args, api):
    wf.runnable()
    task, entry, item = target(wf, args.task, args.repair)
    api.need(item.get("test_checkpoint"), "correction proof needs an existing pin")
    active_task, active_entry = writer(wf, task, entry, api.need)
    api.need(wf.state.get("governance") == "autonomous", "legacy runs use their original correction contract")
    scope, plan = wf.contract()
    snapshot, _ = wf.edits(scope, plan, active_task, active_entry["before"])
    related = affected(wf, args.task, args.repair, snapshot)
    api.verification_evidence.preserve(wf, snapshot, api.need, exclude={(t["id"], rid) for t, rid, _ in related})
    baseline = Path(args.baseline).expanduser().resolve()
    api.need(baseline.is_dir(), "baseline must be a prepared isolated directory")
    for workspace in scope["workspaces"]:
        live = Path(workspace["path"])
        api.need(baseline != live and live not in baseline.parents and baseline not in live.parents,
                 "baseline must be isolated outside all live workspace roots")
    verification = item["verification"] if args.repair else task["verification"]
    stage = args.stage or item["test_checkpoint"]["stage"]
    api.need(stage == "red" or stage == item["test_checkpoint"]["stage"], "cannot weaken behavioral red to a passing pin")
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
    proof = dict(task=args.task, repair=args.repair, stage=stage, baseline=str(baseline), identity=args.identity,
                 snapshot_mode=args.snapshot, test_paths=verification["test_paths"],
                 tests={p: snapshot.get(p) for p in item["test_checkpoint"]["hashes"]},
                 check_definition=plan["checks"][verification["check"]])
    before = baseline_snapshot(proof)
    for relative in verification["test_paths"]:
        api.need(before.get("baseline:" + relative) == snapshot.get(task["workspace"] + ":" + relative)
                 and before.get("baseline:" + relative), "baseline must contain the exact corrected test files")
    proof["baseline_fingerprint"] = digest(before)
    result = checks.run(wf, verification["check"], scope, plan, proof=proof)
    expected = result["exit_code"] > 0 and result["exit_code"] not in (124, 127, 130) if stage == "red" else result["exit_code"] == 0
    api.need(expected and result["stable"], "baseline did not produce a stable expected failure/pass; inspect the actual proof log")
    return f"Baseline proof recorded: {result['operation']}; inspect {result['log']} for a behavior failure, never an import/build/setup error."
