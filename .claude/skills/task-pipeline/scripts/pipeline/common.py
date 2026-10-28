"""Shared plumbing: the workflow directory, its state, the event and decision logs."""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

SKILL = Path(__file__).resolve().parents[2]
CATALOG_PATH = SKILL / "references" / "catalog.json"
STYLE_PATH = SKILL.parents[1] / "output-styles" / "answer-first-core.md"
TP_SCRIPT = SKILL / "scripts" / "tp.py"

PHASES = ("SCOPING", "PLANNING", "AWAITING_APPROVAL", "EXECUTING", "DONE")
# A noticed.md item: `- (<source>[, ×<repeats>]) <text>`.
_NOTICED_LINE = re.compile(r"- \((.*?)(?:, ×(\d+))?\) (.*)$")
_LINE_REF = re.compile(r":\d+(?:-\d+)?")


def noticed_key(text: str) -> str:
    """What makes two noticed items the same: their words, with line numbers left out. Later fix
    rounds re-notice a gap after the lines moved (`LICENSING.md:329` becomes `:340`)."""
    return " ".join(_LINE_REF.sub(":N", str(text)).lower().split())


def agent_context_tokens(agent_id: Optional[str]) -> Optional[int]:
    """The context an agent carried on its last turn (input plus cached tokens), read from its
    transcript; None when the transcript cannot be found. Every resumed turn re-reads all of it."""
    if not agent_id or not re.fullmatch(r"[\w-]+", agent_id):
        return None
    root = Path(os.environ.get("TP_TRANSCRIPTS") or "~/.claude/projects").expanduser()
    for path in root.glob(f"*/*/subagents/agent-{agent_id}.jsonl"):
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - 512_000))
            tail = handle.read().decode(errors="replace").splitlines()
        for line in reversed(tail):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            usage = entry.get("message", {}).get("usage") if entry.get("type") == "assistant" else None
            if usage:
                return sum(int(usage.get(k) or 0) for k in
                           ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    return None


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
                # A task waiting on its siblings' red tests waits on the manager's work, not the human.
                or any(t.get("status") == "blocked" and (t.get("blocked") or {}).get("kind") != "sibling"
                       for t in state.get("tasks", {}).values())
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


_limit_overrides: Dict[str, int] = {}


def set_limit_overrides(overrides: Any) -> None:
    """scope.json `limits`: the human's per-workflow values, which win over the catalog's."""
    _limit_overrides.clear()
    if isinstance(overrides, dict):
        for name, value in overrides.items():
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                _limit_overrides[str(name)] = value


def limit(name: str) -> int:
    if name in _limit_overrides:
        return _limit_overrides[name]
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
    @property
    def guard_path(self) -> Path:
        """Where the last write's sequence number is kept, outside the workflow folder: a copy of
        the folder restored over itself rolls back state.json and events.jsonl together, so only a
        record kept elsewhere can tell."""
        base = os.environ.get("TP_GUARD_DIR") or str(
            Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "task-pipeline" / "guard")
        return Path(base) / (hashlib.sha1(str(self.root).encode()).hexdigest()[:16] + ".json")

    def load(self) -> Dict[str, Any]:
        if not self.exists():
            raise TPError(f"No /task-pipeline workflow at {self.root} (run `tp.py -w <dir> init`).")
        state = json.loads(self.state_path.read_text())
        try:
            guard = json.loads(self.guard_path.read_text())
        except (OSError, ValueError):
            guard = None
        if isinstance(guard, dict) and int(guard.get("seq", 0)) > int(state.get("seq", 0)):
            raise TPError(f"{self.state_path} was rolled back: it holds write {state.get('seq', 0)}, but this "
                          f"workflow last wrote {guard['seq']} (at {guard.get('ts', '?')}). Something replaced the "
                          "workflow folder with an older copy — work recorded since then is missing from it. "
                          "Restore the newer state, or, to continue from this one knowingly, delete "
                          f"{self.guard_path} and re-record what was lost.")
        return state

    def save(self, state: Dict[str, Any]) -> None:
        _tick_idle(state)  # every state change opens or closes a span of waiting on the human
        state["seq"] = int(state.get("seq", 0)) + 1
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1, sort_keys=True))
        os.replace(tmp, self.state_path)
        try:
            self.guard_path.parent.mkdir(parents=True, exist_ok=True)
            self.guard_path.write_text(json.dumps({"root": str(self.root), "seq": state["seq"], "ts": now_iso()}))
        except OSError:
            pass  # a guard that cannot be written only loses the rollback check

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
        clean = " ".join(str(text).split())
        lines = path.read_text().splitlines()
        for i, ln in enumerate(lines):
            m = _NOTICED_LINE.match(ln)
            # Merge repeats: later fix rounds and reviews re-notice the same gap, and a pile of
            # duplicates buries the decisions the closeout must put to the human.
            if m and noticed_key(m.group(3)) == noticed_key(clean):
                count = int(m.group(2) or 1) + 1
                lines[i] = f"- ({m.group(1)}, ×{count}) {m.group(3)}"
                path.write_text("\n".join(lines) + "\n")
                return
        with open(path, "a") as handle:
            handle.write(f"- ({source}) {clean}\n")

    def noticed_items(self) -> List[str]:
        path = self.root / "noticed.md"
        if not path.exists():
            return []
        return [ln[2:] for ln in path.read_text().splitlines() if ln.startswith("- ")]
