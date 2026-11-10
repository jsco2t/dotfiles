"""Input provenance and durable, cancellable check execution. No agent/service APIs."""
import fcntl
import fnmatch
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from snapshot import digest


def matches(path, pattern):
    if pattern == "." or path == pattern or path.startswith(pattern.rstrip("/") + "/"):
        return True
    variants = {pattern}
    pending = [pattern]
    while pending:
        item = pending.pop()
        for index in range(len(item)):
            if item[index:index + 3] == "**/":
                variant = item[:index] + item[index + 3:]
                if variant not in variants:
                    variants.add(variant)
                    pending.append(variant)
    return any(fnmatch.fnmatchcase(path, item) for item in variants)


def fingerprint(snapshot, definition):
    if "inputs" not in definition and not definition.get("environment"):
        return digest(snapshot)  # Preserve existing approved workflows.
    selected = {key: value for key, value in snapshot.items() if any(
        key.startswith(workspace + ":") and any(matches(key.split(":", 1)[1], p) for p in patterns)
        for workspace, patterns in definition["inputs"].items())} if "inputs" in definition else snapshot
    # The definition includes unmatched patterns: creating a previously absent input
    # changes selected. Hash selected environment values without exposing them in logs.
    environment = {name: os.environ.get(name) for name in definition.get("environment", [])}
    return digest(dict(definition=definition, files=selected, environment=environment))


def read_receipt(path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None


def recover(wf):
    """Merge detached worker receipts idempotently, including after parent loss."""
    if not any(op["kind"] in ("check", "proof") and op["status"] in ("running", "unknown")
               for op in wf.state.get("operations", {}).values()):
        return []
    scope, plan = wf.contract()
    recovered = []
    for op in wf.state.get("operations", {}).values():
        if op["kind"] not in ("check", "proof") or op["status"] not in ("running", "unknown"):
            continue
        receipt = read_receipt(wf.root / op["receipt"])
        if receipt is None:
            pid = op.get("worker_pid")
            try:
                os.kill(pid, 0) if pid else (_ for _ in ()).throw(ProcessLookupError())
            except ProcessLookupError:
                op["status"] = "unknown"
            continue
        name = op["check"]
        definition = plan["checks"].get(name)
        after = wf.snapshot(scope, plan)
        same_contract = op["contract"] == digest([scope, plan])
        stable = op["before"] == digest(after) and same_contract
        if op["kind"] == "proof":
            from corrections import baseline_snapshot
            stable = stable and op["proof"]["baseline_fingerprint"] == digest(baseline_snapshot(op["proof"]))
        result = dict(check=name, argv=op["argv"], workspace=op["workspace"],
                      started=op["started"], ended=receipt["ended"],
                      exit_code=receipt["exit_code"], log=op["log"],
                      fingerprint=op.get("input_fingerprint"),
                      stable=stable, operation=op["id"])
        if op["kind"] == "proof":
            result.update(proof=op["proof"])
            wf.state.setdefault("proofs", {})[op["id"]] = result
        else:
            wf.state["checks"][name] = result
        op.update(status=receipt["status"], ended=receipt["ended"], exit_code=receipt["exit_code"])
        wf.event("correction-proof" if op["kind"] == "proof" else "check", **result)
        import tracking
        if wf.state.get("active_activity", {}).get("operation") == op["id"]:
            tracking.pause(wf, "worker receipt", ended=receipt["ended"])
            previous = op.get("resume_activity")
            if previous and wf.state["phase"] == "EXECUTING" and not wf.state.get("question"):
                tracking.switch(wf, previous["category"], previous["label"], previous.get("task"))
        recovered.append(op["id"])
    return recovered


def run(wf, name, scope, plan, proof=None):
    if name not in plan["checks"]:
        raise ValueError(f"unknown check {name}")
    if any(op["status"] in ("running", "unknown") for op in wf.state.get("operations", {}).values()):
        raise ValueError("an operation is unresolved; recover and inspect it before another check")
    definition = plan["checks"][name]
    workspace = next(w for w in scope["workspaces"] if w["name"] == definition["workspace"])
    operation = ("proof-" if proof else "check-") + uuid.uuid4().hex[:16]
    directory = wf.meta / "operations" / operation
    directory.mkdir(parents=True)
    log = wf.root / "checks" / (operation + ".log")
    log.parent.mkdir(exist_ok=True)
    before = wf.snapshot(scope, plan)
    op = dict(id=operation, kind="proof" if proof else "check", status="running", check=name,
              argv=definition["argv"], workspace=definition["workspace"], started=wf.timestamp(),
              before=digest(before), input_fingerprint=fingerprint(before, definition), contract=digest([scope, plan]),
              log=str(log.relative_to(wf.root)), receipt=str((directory / "receipt.json").relative_to(wf.root)))
    if proof:
        op["proof"] = proof
    import tracking
    op["resume_activity"] = wf.state.get("active_activity")
    tracking.switch(wf, "verification", "Check " + name, operation=operation)
    wf.state.setdefault("operations", {})[operation] = op
    wf.write_json(directory / "spec.json", dict(argv=definition["argv"], cwd=proof["baseline"] if proof else workspace["path"],
                  timeout_seconds=definition.get("timeout_seconds", 300), log=str(log)))
    wf.event("operation-start", operation=operation, kind="check", check=name)
    wf.save()  # Durable intent precedes execution; unknown launch outcomes are never replayed.
    try:
        worker = subprocess.Popen([sys.executable, "-B", str(Path(__file__).with_name("check_worker.py")),
                                   str(directory)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as exc:
        op.update(status="failed", ended=wf.timestamp(), exit_code=127)
        wf.save()
        raise ValueError(f"cannot launch check worker: {exc}") from exc
    op["worker_pid"] = worker.pid
    wf.save()
    # Release bookkeeping lock during work. halt can now persist and request cancellation.
    fcntl.flock(wf.lock, fcntl.LOCK_UN)
    try:
        while read_receipt(directory / "receipt.json") is None:
            if worker.poll() is not None:
                break
            time.sleep(0.05)
    finally:
        fcntl.flock(wf.lock, fcntl.LOCK_EX)
        wf.reload()
    recover(wf)
    wf.save()
    result = wf.state.get("proofs", {}).get(operation) if proof else wf.state["checks"].get(name)
    if not result or result.get("operation") != operation:
        raise ValueError(f"check outcome unknown ({operation}); inspect receipt/log and use recover; do not replay")
    return result


def cancel(wf):
    for op in wf.state.get("operations", {}).values():
        if op["status"] != "running":
            continue
        if op["kind"] in ("check", "proof"):
            (wf.root / op["receipt"]).with_name("cancel").touch()
        else:
            op["status"] = "unknown"  # An external effect cannot be assumed cancelled.


def cancel_one(wf, operation, reason):
    """Request cancellation through the owning worker, never an arbitrary PID."""
    op = wf.state.get("operations", {}).get(operation)
    if not op or op["kind"] not in ("check", "proof"):
        raise ValueError("cancel-check requires a known check operation id")
    recover(wf)
    if op["status"] in ("running", "unknown"):
        (wf.root / op["receipt"]).with_name("cancel").touch()
        op["cancellation_reason"] = reason
        wf.event("check-cancel-request", operation=operation, reason=reason)
        return "Cancellation requested; inspect the worker receipt with recover. Task and approval are preserved."
    return "Check already settled; no process was signalled. Task and approval are preserved."
