"""Operations shared by the CLI and the brief generator: recorded snapshots,
task diffs, integrity scans, evidence and gate runs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import ledger
from . import plan as planmod
from . import runner
from . import scan as scanmod
from . import snapshot as snapmod
from .common import OrchError, write_text_atomic
from .gates import Context


def record_snapshot(
    ctx: Context, snap: snapmod.Snapshot, label: str, **fields: Any
) -> Dict[str, Any]:
    entry = {
        "kind": "snapshot",
        "label": label,
        "workspace": snap.workspace,
        "scope_key": "scoped" if snap.scope else "full",
        "snapshot": snap.to_dict(),
    }
    entry.update({k: v for k, v in fields.items() if v is not None})
    recorded = ledger.append(ctx.wf, entry)
    ctx.entries.append(recorded)
    return recorded


def task_state(ctx: Context, task_id: str) -> Dict[str, Any]:
    info = (ctx.state.get("tasks") or {}).get(task_id)
    if info is None:
        raise OrchError(f"task {task_id} is not in workflow state")
    return info


def current_task_snapshot(ctx: Context, task_id: str, label: str) -> snapmod.Snapshot:
    spec = ctx.spec(task_id)
    info = task_state(ctx, task_id)
    snap = ctx.take(spec.workspace, ctx.scope(spec))
    record_snapshot(ctx, snap, label, task=task_id, attempt=info.get("attempt"))
    return snap


def start_snapshot(ctx: Context, task_id: str) -> snapmod.Snapshot:
    info = task_state(ctx, task_id)
    data = info.get("start_snapshot")
    if not isinstance(data, dict):
        raise OrchError(f"task {task_id} has no start snapshot (was it started?)")
    return snapmod.Snapshot.from_dict(data)


def checkpoint_snapshot(ctx: Context, task_id: str) -> Optional[snapmod.Snapshot]:
    info = task_state(ctx, task_id)
    for phase in ("red", "baseline"):
        found = ctx.latest_kind("evidence", task=task_id, attempt=info.get("attempt"), phase=phase)
        if found and isinstance(found.get("snapshot"), dict):
            return snapmod.Snapshot.from_dict(found["snapshot"])
    return None


def write_task_diff(ctx: Context, task_id: str, since: Optional[str] = None) -> Dict[str, Any]:
    """Write the task diff (start -> now), or checkpoint -> now with since='checkpoint'."""
    info = task_state(ctx, task_id)
    run_dir = ctx.wf.run_dir(task_id, int(info.get("attempt") or 0))
    run_dir.mkdir(parents=True, exist_ok=True)
    if since:
        base = checkpoint_snapshot(ctx, task_id)
        if base is None:
            raise OrchError(f"{task_id} has no red/baseline checkpoint in this attempt")
        stem = "changes-since-checkpoint"
    else:
        base = start_snapshot(ctx, task_id)
        stem = "changes"
    now = current_task_snapshot(ctx, task_id, "diff")
    patch = snapmod.diff(base, now)
    changes = snapmod.name_status(base, now)
    files_name = "changed-files.txt" if not since else f"{stem}.txt"
    write_text_atomic(run_dir / f"{stem}.patch", patch)
    write_text_atomic(
        run_dir / files_name,
        "".join(f"{c['status']}\t{c['path']}\n" for c in changes) or "(no changes)\n",
    )
    return {
        "snapshot": now.id,
        "patch": str(run_dir / f"{stem}.patch"),
        "files": str(run_dir / files_name),
        "changes": changes,
    }


def run_task_scan(ctx: Context, task_id: str) -> Dict[str, Any]:
    info = task_state(ctx, task_id)
    spec = ctx.spec(task_id)
    attempt = int(info.get("attempt") or 0)
    run_dir = ctx.wf.run_dir(task_id, attempt)
    start = start_snapshot(ctx, task_id)
    now = current_task_snapshot(ctx, task_id, "scan")
    diff_text = snapmod.diff(start, now, unified=0)
    after_checkpoint: List[str] = []
    checkpoint = checkpoint_snapshot(ctx, task_id)
    if checkpoint is not None and checkpoint.tree != now.tree:
        after_checkpoint = [
            c["path"] for c in snapmod.name_status(checkpoint, now) if scanmod.is_test_path(c["path"])
        ]
    result = scanmod.scan(
        diff_text,
        expected_paths=spec.expected_paths,
        prefix=start.prefix,
        tests_changed_after_checkpoint=after_checkpoint,
    )
    write_text_atomic(run_dir / "scan.json", json.dumps(result, indent=2) + "\n")
    write_text_atomic(run_dir / "scan.md", scanmod.render_markdown(result, f"{task_id} attempt {attempt}"))
    entry = ledger.append(
        ctx.wf,
        {
            "kind": "scan",
            "task": task_id,
            "attempt": attempt,
            "snapshot": now.to_dict(),
            "digest": result["digest"],
            "hit_count": len(result["hits"]),
            "by_category": result["by_category"],
            "report": str(run_dir / "scan.md"),
        },
    )
    ctx.entries.append(entry)
    return entry


def _summary(results: Sequence[Dict[str, Any]]) -> str:
    return "; ".join(f"`{r['command']}` exit {r['exit']} ({Path(r['log']).name})" for r in results)


def run_evidence(ctx: Context, task_id: str, phase: str, timeout: int) -> Dict[str, Any]:
    info = task_state(ctx, task_id)
    if info.get("status") != "IN_PROGRESS":
        raise OrchError(f"task {task_id} is not in progress")
    spec = ctx.spec(task_id)
    tf = spec.test_forward
    allowed = {"red-green": ("red", "green"), "characterization": ("baseline", "green")}.get(tf, ())
    if spec.type == "test":
        allowed = ("green",)
    if phase not in allowed:
        raise OrchError(
            f"{task_id} is `{spec.type}` with test_forward `{tf}`; evidence phases allowed: "
            f"{', '.join(allowed) or 'none'}"
        )
    commands = spec.validation("red_green")
    if not commands:
        raise OrchError(f"{task_id} declares no validation.red_green commands")
    attempt = int(info.get("attempt") or 0)
    run_dir = ctx.wf.run_dir(task_id, attempt) / "evidence"
    before = ctx.take(spec.workspace, ctx.scope(spec))
    ws = ctx.ws_path(spec.workspace)
    nth = len(ledger.select(ctx.entries, "evidence", task=task_id, attempt=attempt)) + 1
    results = runner.run_commands(commands, ws, run_dir, f"{nth:02d}-{phase}", timeout)
    after = snapmod.take(ctx.wf, spec.workspace, ws, scope=ctx.scope(spec),
                         excludes=planmod.snapshot_excludes(ctx.pkg.gate, spec.workspace))
    drift = before.id != after.id
    if phase == "red":
        passed = all(r["exit"] != 0 and not r["timed_out"] for r in results)
    else:
        passed = all(r["exit"] == 0 for r in results)
    passed = passed and not drift
    changed_since_start: List[Dict[str, str]] = []
    if phase in ("red", "baseline"):
        start = start_snapshot(ctx, task_id)
        for change in snapmod.name_status(start, before):
            change["test_file"] = "yes" if scanmod.is_test_path(change["path"]) else "no"
            changed_since_start.append(change)
    entry = ledger.append(
        ctx.wf,
        {
            "kind": "evidence",
            "task": task_id,
            "attempt": attempt,
            "phase": phase,
            "passed": passed,
            "drift": drift,
            "commands": results,
            "summary": _summary(results) + (" — WORKSPACE CHANGED DURING THE RUN" if drift else ""),
            "snapshot": before.to_dict(),
            "changed_since_start": changed_since_start,
        },
    )
    ctx.entries.append(entry)
    record_snapshot(ctx, before, f"evidence-{phase}", task=task_id, attempt=attempt)
    return entry


def run_gate(
    ctx: Context,
    level: str,
    scope: str,
    workspace: str,
    task_id: Optional[str] = None,
    loop: Optional[int] = None,
    label: Optional[str] = None,
    timeout: int = runner.DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    gate = ctx.pkg.gate
    commands = planmod.gate_commands(gate, workspace, level)
    if level == "final" and not commands:
        commands = planmod.gate_commands(gate, workspace, "standard")
    if not commands:
        raise OrchError(f"workspace `{workspace}` has no `{level}` gate commands")
    ws = ctx.ws_path(workspace)
    attempt = None
    snap_scope: List[str] = []
    if scope == "task":
        info = task_state(ctx, task_id or "")
        spec = ctx.spec(task_id or "")
        attempt = int(info.get("attempt") or 0)
        snap_scope = ctx.scope(spec)
        log_dir = ctx.wf.run_dir(task_id or "", attempt) / "gate"
    elif scope == "loop":
        log_dir = ctx.wf.loop_dir(int(loop or 0)) / "gate"
    else:
        log_dir = ctx.wf.final_dir / "gate"
    before = ctx.take(workspace, snap_scope)
    nth = len(list(log_dir.glob("*.log"))) + 1 if log_dir.is_dir() else 1
    results = runner.run_commands(commands, ws, log_dir, f"{nth:02d}-{workspace}-{level}", timeout)
    after = snapmod.take(ctx.wf, workspace, ws, scope=snap_scope,
                         excludes=planmod.snapshot_excludes(gate, workspace))
    drift = before.id != after.id
    passed = all(r["exit"] == 0 for r in results) and not drift
    entry = ledger.append(
        ctx.wf,
        {
            "kind": "gate",
            "scope": scope,
            "level": level,
            "workspace": workspace,
            "task": task_id,
            "attempt": attempt,
            "loop": loop,
            "label": label,
            "passed": passed,
            "drift": drift,
            "commands": results,
            "summary": _summary(results) + (" — WORKSPACE CHANGED DURING THE RUN" if drift else ""),
            "snapshot": before.to_dict(),
        },
    )
    ctx.entries.append(entry)
    record_snapshot(ctx, before, f"gate-{scope}", task=task_id, attempt=attempt, loop=loop)
    return entry


def composite_now(ctx: Context, workspaces: Sequence[str], label: str, **fields: Any) -> Tuple[str, List[snapmod.Snapshot]]:
    comp, snaps = ctx.composite(workspaces)
    for snap in snaps:
        record_snapshot(ctx, snap, label, **fields)
    return comp, snaps


def write_range_diffs(
    ctx: Context, target_dir: Path, starts: Dict[str, Dict[str, Any]], workspaces: Sequence[str], label: str
) -> Dict[str, Any]:
    """Diff each workspace from a recorded start snapshot to now; write patch + file lists."""
    target_dir.mkdir(parents=True, exist_ok=True)
    out: Dict[str, Any] = {"patches": {}, "doc_files_changed": False}
    comp, snaps = composite_now(ctx, workspaces, label)
    for snap in snaps:
        start = starts.get(snap.workspace)
        if not isinstance(start, dict):
            continue
        base = snapmod.Snapshot.from_dict(start)
        patch = snapmod.diff(base, snap)
        changes = snapmod.name_status(base, snap)
        write_text_atomic(target_dir / f"changes-{snap.workspace}.patch", patch)
        write_text_atomic(
            target_dir / f"changed-files-{snap.workspace}.txt",
            "".join(f"{c['status']}\t{c['path']}\n" for c in changes) or "(no changes)\n",
        )
        out["patches"][snap.workspace] = str(target_dir / f"changes-{snap.workspace}.patch")
        if any(c["path"].endswith((".md", ".mdx", ".rst", ".adoc", ".txt")) for c in changes):
            out["doc_files_changed"] = True
    out["composite"] = comp
    return out
