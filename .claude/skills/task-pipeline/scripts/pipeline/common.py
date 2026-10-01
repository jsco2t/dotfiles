"""Shared plumbing: the workflow directory, its state, the event and decision logs."""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

SKILL = Path(__file__).resolve().parents[2]
CATALOG_PATH = SKILL / "references" / "catalog.json"
STYLE_PATH = SKILL.parents[1] / "output-styles" / "answer-first-core.md"
TP_SCRIPT = SKILL / "scripts" / "tp.py"

PHASES = ("SCOPING", "PLANNING", "AWAITING_APPROVAL", "EXECUTING", "DONE")


class TPError(Exception):
    """A refusal. Each line of the message is printed as `ERROR: <line>`; exit code 2."""

    def __init__(self, *lines: str) -> None:
        super().__init__("\n".join(lines))
        self.lines = [ln for ln in lines if ln]
        self.done = ""  # output of the steps that succeeded before the refusal, printed first


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def minutes_since(ts: Optional[str], until: Optional[str] = None) -> float:
    if not ts:
        return 0.0
    end = parse_iso(until) if until else datetime.now(timezone.utc)
    return max(0.0, (end - parse_iso(ts)).total_seconds() / 60.0)


def gap_minutes(start: Optional[str], end: Optional[str], gaps: List[List[Optional[str]]]) -> float:
    """Minutes of [start, end] (end None: now) inside the union of `gaps` — [from, to] pairs, to None
    for a gap still open. Overlapping gaps count once."""
    if not start:
        return 0.0
    now = datetime.now(timezone.utc)
    lo, hi = parse_iso(start), parse_iso(end) if end else now
    spans = []
    for a, b in gaps:
        if a:
            a_, b_ = max(parse_iso(a), lo), min(parse_iso(b) if b else now, hi)
            if b_ > a_:
                spans.append((a_, b_))
    total, cur = 0.0, None
    for a, b in sorted(spans):
        if cur and a <= cur[1]:
            cur = (cur[0], max(cur[1], b))
            continue
        if cur:
            total += (cur[1] - cur[0]).total_seconds()
        cur = (a, b)
    if cur:
        total += (cur[1] - cur[0]).total_seconds()
    return total / 60.0


def waiting_gaps(state: Dict[str, Any]) -> List[List[Optional[str]]]:
    """Spans in which nothing ran and the work waited on the human: halts and blocks (kept by
    Workflow.save), plus each halt's own record for workflows older than that."""
    gaps = [list(g) for g in state.get("idle", [])]
    if state.get("idle_since"):
        gaps.append([state["idle_since"], None])
    for h in state.get("halts", []) + ([state["halt"]] if state.get("halt") else []):
        if h.get("halted"):
            gaps.append([h["halted"], h.get("resumed")])
    return gaps


def _waiting_on_human(state: Dict[str, Any]) -> bool:
    if state.get("phase") != "EXECUTING" or state.get("in_flight"):
        return False
    return bool(state.get("halt") or state.get("blocked")
                or any(t.get("status") == "blocked" for t in state.get("tasks", {}).values())
                or any(s.get("status") == "blocked" for s in state.get("reviews", {}).values()))


def _tick_idle(state: Dict[str, Any]) -> None:
    waiting, since = _waiting_on_human(state), state.get("idle_since")
    if waiting and not since:
        state["idle_since"] = now_iso()
    elif since and not waiting:
        state.setdefault("idle", []).append([since, now_iso()])
        del state["idle_since"]


def sha_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path, what: str) -> Any:
    if not path.exists():
        raise TPError(f"{path} does not exist ({what}).")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise TPError(f"{path} is not valid JSON ({what}): line {exc.lineno} col {exc.colno}: {exc.msg}.")


_catalog: Dict[str, Any] = {}


def catalog() -> Dict[str, Any]:
    if not _catalog:
        _catalog.update(json.loads(CATALOG_PATH.read_text()))
    return _catalog


def limit(name: str) -> int:
    return int(catalog()["limits"][name])


def style_core() -> str:
    """The answer-first core style, without its frontmatter, for inlining into briefs."""
    if not STYLE_PATH.exists():
        raise TPError(f"{STYLE_PATH} is missing: install output-styles/answer-first-core.md with the skill.")
    text = STYLE_PATH.read_text()
    if text.startswith("---"):
        text = text.split("---", 2)[2]
    lines = [ln for ln in text.strip().splitlines() if not ln.startswith("# ")]
    return "\n".join(lines).strip()


def words(text: str) -> int:
    return len(str(text).split())


class Workflow:
    """A workflow directory. Only tp.py writes `.tp/`, `decisions.md`, and `noticed.md`."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.meta = self.root / ".tp"
        self.state_path = self.meta / "state.json"

    # --- paths ---------------------------------------------------------------
    @property
    def scope_json(self) -> Path:
        return self.root / "scope.json"

    @property
    def plan_json(self) -> Path:
        return self.root / "plan.json"

    def run_dir(self, tid: str) -> Path:
        return self.root / "runs" / tid

    def exists(self) -> bool:
        return self.state_path.exists()

    # --- state -----------------------------------------------------------------
    def load(self) -> Dict[str, Any]:
        if not self.exists():
            raise TPError(f"No /task-pipeline workflow at {self.root} (run `tp.py -w <dir> init`).")
        return json.loads(self.state_path.read_text())

    def save(self, state: Dict[str, Any]) -> None:
        _tick_idle(state)  # every state change opens or closes a span of waiting on the human
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1, sort_keys=True))
        os.replace(tmp, self.state_path)

    @contextlib.contextmanager
    def locked(self) -> Iterator[None]:
        self.meta.mkdir(parents=True, exist_ok=True)
        with open(self.meta / "lock", "w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    # --- logs --------------------------------------------------------------------
    def event(self, kind: str, **fields: Any) -> None:
        entry = {"ts": now_iso(), "t_ns": time.time_ns(), "kind": kind, **fields}
        with open(self.meta / "events.jsonl", "a") as handle:
            handle.write(json.dumps(entry) + "\n")

    def events(self) -> List[Dict[str, Any]]:
        path = self.meta / "events.jsonl"
        if not path.exists():
            return []
        return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]

    def decision(self, what: str, text: str, who: Optional[str] = "human") -> None:
        """who=None records the decision without attributing it (`tp resolve` without --by)."""
        path = self.root / "decisions.md"
        if not path.exists():
            path.write_text("# Decisions\n\nEvery human answer and every manager ruling, verbatim, in order.\n\n")
        with open(path, "a") as handle:
            handle.write(f"- {now_iso()} · {what}{f' · {who}' if who else ''}: {text.strip()}\n")

    def noticed(self, source: str, text: str) -> None:
        path = self.root / "noticed.md"
        if not path.exists():
            path.write_text("# Noticed, not in plan\n\nObservations outside the plan. Never actioned "
                            "without the human.\n\n")
        with open(path, "a") as handle:
            handle.write(f"- ({source}) {text.strip()}\n")

    def noticed_items(self) -> List[str]:
        path = self.root / "noticed.md"
        if not path.exists():
            return []
        return [ln[2:] for ln in path.read_text().splitlines() if ln.startswith("- ")]
