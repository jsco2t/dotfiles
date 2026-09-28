"""Shared primitives: time, JSON I/O, locking, the session registry, workflow layout.

Everything durable about a workflow lives in its workflow directory (chosen by
the user). The only state outside it is the registry under TASK_ORCH_HOME:
`sessions/` maps a Claude Code session id to the workflow directory that session
drives, and `workflows/` catalogs every workflow created or bound on this
machine so `orch list` can offer them for resuming. The registry defaults to
~/.cache/task-orchestrator because that is writable from inside the Claude Code
Bash sandbox; losing it only loses bindings and the catalog, which
`orch bind <workflow-dir>` restores.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

SCHEMA = 1
SKILL_NAME = "task-orchestrator"
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
SKILL_DIR = SCRIPTS_DIR.parent
ORCH_CLI = SCRIPTS_DIR / "orch.py"

QUALITY_MANDATE = (
    "QUALITY MANDATE: This process does not look for ways to make the work "
    "cheaper, faster, or smaller. It produces very high quality results that "
    "match exactly what the user asked for. DO NOT SKIP STEPS. DO NOT DEFER "
    "WORK. DO NOT weaken a goal, a test, or a criterion to get past a gate. "
    "Equally, DO NOT DO MORE than was asked: no unrequested audits, fixes, "
    "rewrites, or analysis. If you believe the plan missed something the human "
    "needs, raise a scope proposal — never do it yourself. If you are not sure "
    "how to proceed, stop and ask a human."
)

# Workflow phases. STOP_PHASES are the phases in which the main session may end
# its turn without the Stop hook forcing a continuation.
PHASES = (
    "PLANNING",
    "AWAITING_APPROVAL",
    "EXECUTING",
    "FINAL",
    "DONE",
    "CLOSED",
    "NEEDS_HUMAN",
    "PLAN_CHANGE_REQUIRED",
    "HALTED",
)
STOP_PHASES = frozenset(
    {
        "PLANNING",
        "AWAITING_APPROVAL",
        "DONE",
        "CLOSED",
        "NEEDS_HUMAN",
        "PLAN_CHANGE_REQUIRED",
        "HALTED",
    }
)
ACTIVE_PHASES = frozenset({"EXECUTING", "FINAL"})

TASK_STATUSES = ("PENDING", "IN_PROGRESS", "ACCEPTED", "BLOCKED")


class OrchError(Exception):
    """A user-facing refusal or failure. The CLI prints it and exits 2."""


# ---------------------------------------------------------------- time


def utcnow() -> str:
    """UTC timestamp, millisecond precision, ISO 8601 with a Z suffix."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def parse_ts(value: Any) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp (Z or offset). Python 3.9 safe."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        # 3.9's fromisoformat rejects some fractional-second widths.
        match = re.match(
            r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?([+-]\d{2}:\d{2})?$",
            text,
        )
        if not match:
            return None
        base, frac, offset = match.groups()
        frac = (frac or "0")[:6].ljust(6, "0")
        try:
            parsed = datetime.fromisoformat(f"{base}.{frac}{offset or '+00:00'}")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- files


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_text_atomic(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def write_json_atomic(path: Path, data: Any) -> None:
    write_text_atomic(path, json.dumps(data, indent=2, sort_keys=False) + "\n")


@contextlib.contextmanager
def file_lock(path: Path) -> Generator[None, None, None]:
    """Exclusive advisory lock held for the duration of the block."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(data: Any) -> str:
    return sha256_text(json.dumps(data, sort_keys=True, separators=(",", ":")))


def is_within(path: Path, root: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def slugify(text: str, limit: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug[:limit].rstrip("-")) or "work"


# ---------------------------------------------------------------- registry


def orch_home() -> Path:
    override = os.environ.get("TASK_ORCH_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cache" / SKILL_NAME


def current_session_id() -> Optional[str]:
    return os.environ.get("CLAUDE_CODE_SESSION_ID") or None


def _binding_path(session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id)
    return orch_home() / "sessions" / f"{safe}.json"


def get_binding(session_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not session_id:
        return None
    data = read_json(_binding_path(session_id))
    if not isinstance(data, dict) or not data.get("workflow_dir"):
        return None
    return data


def set_binding(session_id: str, workflow_dir: Path, workflow_id: str) -> None:
    write_json_atomic(
        _binding_path(session_id),
        {
            "session_id": session_id,
            "workflow_dir": str(Path(workflow_dir).resolve()),
            "workflow_id": workflow_id,
            "bound_at": utcnow(),
        },
    )


def clear_binding(session_id: str) -> None:
    with contextlib.suppress(FileNotFoundError):
        _binding_path(session_id).unlink()


def list_bindings() -> List[Dict[str, Any]]:
    folder = orch_home() / "sessions"
    if not folder.is_dir():
        return []
    out = []
    for entry in sorted(folder.glob("*.json")):
        data = read_json(entry)
        if isinstance(data, dict):
            out.append(data)
    return out


def _catalog_path(workflow_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", workflow_id)
    return orch_home() / "workflows" / f"{safe}.json"


def register_workflow(workflow_dir: Path, workflow_id: str, title: str) -> None:
    """Record a workflow in the catalog (idempotent; keeps the first registration time)."""
    path = _catalog_path(workflow_id)
    existing = read_json(path) if path.exists() else None
    write_json_atomic(path, {
        "workflow_id": workflow_id,
        "workflow_dir": str(Path(workflow_dir).resolve()),
        "title": title,
        "registered_at": (existing or {}).get("registered_at") or utcnow(),
    })


def catalog_entries() -> List[Dict[str, Any]]:
    """Every known workflow: the catalog plus any bound workflow the catalog lacks."""
    found: Dict[str, Dict[str, Any]] = {}
    folder = orch_home() / "workflows"
    if folder.is_dir():
        for entry in sorted(folder.glob("*.json")):
            data = read_json(entry)
            if isinstance(data, dict) and data.get("workflow_dir"):
                found[str(Path(data["workflow_dir"]).resolve())] = data
    for binding in list_bindings():
        root = str(Path(binding["workflow_dir"]).resolve())
        found.setdefault(root, {"workflow_id": binding.get("workflow_id"), "workflow_dir": root})
    return list(found.values())


def find_workflow(target: str) -> Optional[Path]:
    """A workflow directory from a path or a catalogued workflow id; None if neither."""
    path = Path(target).expanduser()
    if (path / ".orch" / "state.json").is_file():
        return path.resolve()
    for entry in catalog_entries():
        if entry.get("workflow_id") == target:
            root = Path(entry["workflow_dir"])
            if (root / ".orch" / "state.json").is_file():
                return root
    return None


# ---------------------------------------------------------------- layout


FROZEN_TOP_FILES = ("request.md", "scope.md", "plan.md", "architecture.md", "gate.json")
GENERATED_FILES = ("index.md", "status.md", "tasks/index.md", "research/index.md")
REPORT_DIRS = ("runs", "research", "reviews", "loops", "final")
TASK_FILE_RE = re.compile(r"^(T\d{3,})-[a-z0-9][a-z0-9-]*\.md$")
INTERIM_DIR = "interim"


def interim_path(report: Path) -> Path:
    """Where an agent stopped by the budget hook writes its interim report: an
    `interim/` folder beside its report, same file name. Interim reports never
    satisfy a gate and are not linked from the research index."""
    report = Path(report)
    return report.parent / INTERIM_DIR / report.name


def report_for_interim(interim: Path) -> Path:
    interim = Path(interim)
    return interim.parent.parent / interim.name


ROOT_PATTERNS = frozenset({"", ".", "./", "/", "*", "**", "**/*", "*/**"})


def path_matches(path: str, pattern: str) -> bool:
    """A workspace-relative path against an `expected_paths` / `out_of_plan` entry: a plain
    entry is a file or directory prefix; an entry with * ? [ is a glob (`**/` may match nothing)."""
    import fnmatch

    path = path.strip().strip("/")
    raw = pattern.strip()
    if raw in ROOT_PATTERNS:
        return True
    pat = (raw[2:] if raw.startswith("./") else raw).strip("/")
    if any(ch in pat for ch in "*?["):
        candidates = {pat, pat.replace("**/", ""), pat.replace("/**", "")}
        return any(fnmatch.fnmatchcase(path, c) or fnmatch.fnmatchcase(path, c.rstrip("/") + "/*")
                   for c in candidates if c)
    return path == pat or path.startswith(pat + "/")


class Workflow:
    """Paths inside one workflow directory."""

    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve()

    # control
    @property
    def control(self) -> Path:
        return self.root / ".orch"

    @property
    def state_path(self) -> Path:
        return self.control / "state.json"

    @property
    def ledger_path(self) -> Path:
        return self.control / "ledger.jsonl"

    @property
    def lock_path(self) -> Path:
        return self.control / "lock"

    @property
    def halt_path(self) -> Path:
        return self.root / "HALT"

    @property
    def agents_dir(self) -> Path:
        """Per-agent activity records, written by the hooks (see activity.py)."""
        return self.control / "agents"

    # plan package
    @property
    def request(self) -> Path:
        return self.root / "request.md"

    @property
    def scope(self) -> Path:
        """The scope the human confirmed before research: deliverables, significant terms, non-goals."""
        return self.root / "scope.md"

    @property
    def plan(self) -> Path:
        return self.root / "plan.md"

    @property
    def architecture(self) -> Path:
        return self.root / "architecture.md"

    @property
    def gate(self) -> Path:
        return self.root / "gate.json"

    @property
    def decisions(self) -> Path:
        return self.root / "decisions.md"

    @property
    def tasks_dir(self) -> Path:
        return self.root / "tasks"

    @property
    def research_dir(self) -> Path:
        return self.root / "research"

    @property
    def reviews_dir(self) -> Path:
        return self.root / "reviews"

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    @property
    def loops_dir(self) -> Path:
        return self.root / "loops"

    @property
    def final_dir(self) -> Path:
        return self.root / "final"

    def run_dir(self, task_id: str, attempt: int) -> Path:
        return self.runs_dir / task_id / f"a{attempt}"

    def loop_dir(self, loop: int) -> Path:
        return self.loops_dir / f"L{int(loop):02d}"

    def task_files(self) -> List[Path]:
        if not self.tasks_dir.is_dir():
            return []
        return sorted(
            p for p in self.tasks_dir.iterdir() if p.is_file() and TASK_FILE_RE.match(p.name)
        )

    def frozen_files(self) -> List[Path]:
        files = [self.root / name for name in FROZEN_TOP_FILES if (self.root / name).exists()]
        files.extend(self.task_files())
        return files

    def is_frozen_path(self, path: Path) -> bool:
        path = Path(path).resolve()
        if path.parent == self.root and path.name in FROZEN_TOP_FILES:
            return True
        return path.parent == self.tasks_dir and bool(TASK_FILE_RE.match(path.name))

    def is_generated_path(self, path: Path) -> bool:
        path = Path(path).resolve()
        if any(path == self.root / rel for rel in GENERATED_FILES):
            return True
        # runs/<task>/index.md
        return (
            path.name == "index.md"
            and path.parent.parent == self.runs_dir
        )

    def rel(self, path: Path) -> str:
        try:
            return str(Path(path).resolve().relative_to(self.root))
        except ValueError:
            return str(path)

    # state
    def exists(self) -> bool:
        return self.state_path.is_file()

    def load_state(self) -> Dict[str, Any]:
        state = read_json(self.state_path)
        if not isinstance(state, dict):
            raise OrchError(f"No workflow state at {self.state_path}")
        return state

    def save_state(self, state: Dict[str, Any]) -> None:
        state["updated_at"] = utcnow()
        write_json_atomic(self.state_path, state)


def resolve_workflow(explicit: Optional[str] = None) -> Workflow:
    """The workflow for this invocation: --wf, else this session's binding."""
    if explicit:
        wf = Workflow(Path(explicit))
        if not wf.exists():
            raise OrchError(f"{wf.root} is not a task-orchestrator workflow directory")
        return wf
    session_id = current_session_id()
    binding = get_binding(session_id)
    if not binding:
        raise OrchError(
            "This session is not bound to a workflow. Start one with "
            "`orch init`, or bind an existing one with `orch bind <workflow-dir>`."
        )
    wf = Workflow(Path(binding["workflow_dir"]))
    if not wf.exists():
        raise OrchError(
            f"The bound workflow directory {wf.root} has no state. "
            "Re-bind with `orch bind <workflow-dir>`."
        )
    return wf
