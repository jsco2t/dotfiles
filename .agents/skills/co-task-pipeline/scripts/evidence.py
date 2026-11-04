"""Retain verification provenance when completion is invalidated."""
import copy

from snapshot import digest


def archive(wf, tid, reason):
    entry = copy.deepcopy(wf.tasks()[tid])
    if not any(key in entry for key in ("result", "test_checkpoint", "repairs", "test_updates")):
        return
    # Large workspace snapshots are checkpoints, not regression evidence. Keep their identity.
    for item in [entry] + entry.get("repairs", []):
        if "before" in item:
            item["before_fingerprint"] = digest(item.pop("before"))
    task = next(t for t in wf.state["plan"]["tasks"] if t["id"] == tid)
    wf.state.setdefault("evidence_history", []).append(
        dict(task=tid, at=wf.timestamp(), reason=reason, contract=copy.deepcopy(task), entry=entry))


def reset(wf, tid, reason):
    archive(wf, tid, reason)
    entry = copy.deepcopy(wf.tasks()[tid])
    for key in ("before", "result", "checks", "ended"):
        entry.pop(key, None)
    entry["status"] = "pending"
    return entry


def preserve(wf, snapshot, need, exclude=None):
    """A later task cannot silently weaken an earlier accepted regression."""
    for tid, entry in wf.tasks().items():
        for rid, item in [(None, entry)] + [(r["id"], r) for r in entry.get("repairs", [])]:
            if (tid, rid) == exclude or item.get("status") == "superseded":
                continue
            pin = item.get("test_checkpoint")
            if pin:
                need(all(snapshot.get(path) == value for path, value in pin["hashes"].items()),
                     f"pinned tests changed in {tid}" + (f"/{rid}" if rid else "") +
                     "; use a mechanical correction or an explicitly approved test amendment")
