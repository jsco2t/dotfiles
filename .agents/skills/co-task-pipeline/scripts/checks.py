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
    if not any(op["kind"] == "check" and op["status"] in ("running", "unknown")
               for op in wf.state.get("operations", {}).values()):
        return []
    scope, plan = wf.contract()
    recovered = []
    for op in wf.state.get("operations", {}).values():
        if op["kind"] != "check" or op["status"] not in ("running", "unknown"):
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
        result = dict(check=name, argv=op["argv"], workspace=op["workspace"],
                      started=op["started"], ended=receipt["ended"],
                      exit_code=receipt["exit_code"], log=op["log"],
                      fingerprint=op.get("input_fingerprint"),
                      stable=stable, operation=op["id"])
        wf.state["checks"][name] = result
        op.update(status=receipt["status"], ended=receipt["ended"], exit_code=receipt["exit_code"])
        wf.event("check", **result)
        import tracking
        if wf.state.get("active_activity", {}).get("operation") == op["id"]:
            tracking.pause(wf, "worker receipt", ended=receipt["ended"])
            previous = op.get("resume_activity")
            if previous and wf.state["phase"] == "EXECUTING" and not wf.state.get("question"):
                tracking.switch(wf, previous["category"], previous["label"], previous.get("task"))
        recovered.append(op["id"])
    return recovered


def run(wf, name, scope, plan):
    if name not in plan["checks"]:
        raise ValueError(f"unknown check {name}")
    if any(op["status"] in ("running", "unknown") for op in wf.state.get("operations", {}).values()):
        raise ValueError("an operation is unresolved; recover and inspect it before another check")
    definition = plan["checks"][name]
    workspace = next(w for w in scope["workspaces"] if w["name"] == definition["workspace"])
    operation = "check-" + uuid.uuid4().hex[:16]
    directory = wf.meta / "operations" / operation
    directory.mkdir(parents=True)
    log = wf.root / "checks" / (operation + ".log")
    log.parent.mkdir(exist_ok=True)
    before = wf.snapshot(scope, plan)
    op = dict(id=operation, kind="check", status="running", check=name,
              argv=definition["argv"], workspace=definition["workspace"], started=wf.timestamp(),
              before=digest(before), input_fingerprint=fingerprint(before, definition), contract=digest([scope, plan]),
              log=str(log.relative_to(wf.root)), receipt=str((directory / "receipt.json").relative_to(wf.root)))
    import tracking
    op["resume_activity"] = wf.state.get("active_activity")
    tracking.switch(wf, "verification", "Check " + name, operation=operation)
    wf.state.setdefault("operations", {})[operation] = op
    wf.write_json(directory / "spec.json", dict(argv=definition["argv"], cwd=workspace["path"],
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
        wf.state = wf.read_json(wf.state_path)
    recover(wf)
    wf.save()
    result = wf.state["checks"].get(name)
    if not result or result.get("operation") != operation:
        raise ValueError(f"check outcome unknown ({operation}); inspect receipt/log and use recover; do not replay")
    return result


def cancel(wf):
    for op in wf.state.get("operations", {}).values():
        if op["status"] != "running":
            continue
        if op["kind"] == "check":
            (wf.root / op["receipt"]).with_name("cancel").touch()
        else:
            op["status"] = "unknown"  # An external effect cannot be assumed cancelled.
