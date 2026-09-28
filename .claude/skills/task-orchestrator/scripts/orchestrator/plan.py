"""Parse and validate the plan package: request.md, plan.md, gate.json, tasks/*.md.

The task documents are the single source of truth for task metadata and
acceptance criteria — nothing is copied into state.json by hand. Each task
document carries a fenced ```json task``` metadata block and an
"## Acceptance criteria" checklist whose items look like:

    - [ ] AC1: <objective, checkable criterion> — Verified by: <test | command | inspection>
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .common import TASK_FILE_RE, Workflow, read_json
from .roster import CODE_LIKE_TYPES, PROSE_TYPES, REVIEWERS, TASK_TYPES, TEST_FORWARD_MODES

MAX_TASK_DAYS = 1.5

TASK_META_RE = re.compile(r"```json[ \t]+task[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.S)
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.M)
AC_RE = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(AC\d+)\s*[:.)\-–—]\s*(.*?)\s*$")
VERIFIED_SPLIT_RE = re.compile(r"\s*(?:—|–|--|-|\|)?\s*verified by\s*:\s*", re.I)
VERIFIED_LINE_RE = re.compile(r"^\s*(?:[-*]\s+)?verified by\s*:\s*(.+?)\s*$", re.I)
REQ_RE = re.compile(r"^\s*[-*]\s+(?:\*\*)?(R\d+)(?:\*\*)?\s*[:.)\-–—]\s*(.+?)\s*$")
FAC_RE = re.compile(r"^\s*[-*]\s+(?:\[( |x|X)\]\s+)?(?:\*\*)?(FAC\d+)(?:\*\*)?\s*[:.)\-–—]\s*(.+?)\s*$")
Q_RE = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(?:\*\*)?(Q\d+)(?:\*\*)?\s*[:.)\-–—]\s*(.+?)\s*$")
NUMBERING_RE = re.compile(r"^\s*(?:§\s*)?\d+(?:\.\d+)*[.)]?\s+")

PLAN_SECTIONS = (
    "objective",
    "requirements",
    "current state",
    "approach",
    "architectural decisions",
    "architectural review",
    "loop plan",
    "quality gate",
    "risks",
    "out of scope",
    "final acceptance criteria",
    "open questions",
)
PLAN_SECTIONS_CODE = ("test strategy", "test plan")
TASK_SECTIONS = (
    "goal",
    "context",
    "scope",
    "acceptance criteria",
    "validation",
    "dependencies",
    "risks",
)
TASK_SECTIONS_CODE = ("test plan",)

META_TYPES: Dict[str, Any] = {
    "id": str,
    "title": str,
    "type": str,
    "loop": int,
    "depends_on": list,
    "requirements": list,
    "workspace": str,
    "authors": list,
    "reviewers": list,
    "test_forward": str,
    "estimated_days": (int, float),
    "expected_paths": list,
    "validation": dict,
}


# ---------------------------------------------------------------- markdown


def norm_heading(text: str) -> str:
    text = NUMBERING_RE.sub("", text.strip())
    text = re.sub(r"[*_`]", "", text)
    return text.strip().rstrip(":").strip().lower()


def split_sections(text: str, level: int = 2) -> Dict[str, str]:
    """Map normalized level-N heading -> body text, ignoring fenced code."""
    marker = "#" * level + " "
    sections: Dict[str, str] = {}
    current: Optional[str] = None
    buf: List[str] = []
    fence: Optional[str] = None
    for line in text.splitlines():
        stripped = line.lstrip()
        if fence:
            if stripped.startswith(fence):
                fence = None
            if current is not None:
                buf.append(line)
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = stripped[:3]
            if current is not None:
                buf.append(line)
            continue
        if line.startswith(marker) and not line.startswith(marker + "#"):
            if current is not None:
                sections.setdefault(current, "\n".join(buf))
            current = norm_heading(line[len(marker):])
            buf = []
            continue
        if current is not None:
            buf.append(line)
    if current is not None:
        sections.setdefault(current, "\n".join(buf))
    return sections


def find_section(sections: Dict[str, str], key: str) -> Optional[str]:
    for name, body in sections.items():
        if name.startswith(key):
            return body
    return None


# ---------------------------------------------------------------- tasks


@dataclass
class Criterion:
    id: str
    text: str
    verified_by: str


@dataclass
class TaskSpec:
    path: Path
    id: str
    meta: Dict[str, Any]
    heading: str
    criteria: List[Criterion]
    sections: Dict[str, str]
    errors: List[str] = field(default_factory=list)
    sha256: str = ""

    # convenience accessors (safe on malformed meta)
    @property
    def title(self) -> str:
        return str(self.meta.get("title") or self.heading or self.id)

    @property
    def type(self) -> str:
        return str(self.meta.get("type") or "")

    @property
    def loop(self) -> int:
        value = self.meta.get("loop")
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    @property
    def workspace(self) -> str:
        return str(self.meta.get("workspace") or "")

    @property
    def authors(self) -> List[str]:
        return [a for a in self.meta.get("authors") or [] if isinstance(a, str)]

    @property
    def reviewers(self) -> List[str]:
        return [r for r in self.meta.get("reviewers") or [] if isinstance(r, str)]

    @property
    def depends_on(self) -> List[str]:
        return [d for d in self.meta.get("depends_on") or [] if isinstance(d, str)]

    @property
    def test_forward(self) -> str:
        return str(self.meta.get("test_forward") or "")

    @property
    def expected_paths(self) -> List[str]:
        return [p for p in self.meta.get("expected_paths") or [] if isinstance(p, str)]

    @property
    def parallel_safe(self) -> bool:
        return bool(self.meta.get("parallel_safe"))

    @property
    def external_writes(self) -> bool:
        return bool(self.meta.get("external_writes"))

    def validation(self, key: str) -> List[str]:
        block = self.meta.get("validation") or {}
        items = block.get(key) if isinstance(block, dict) else None
        return [c for c in items or [] if isinstance(c, str) and c.strip()]

    def required_reviewers(self) -> List[str]:
        spec = TASK_TYPES.get(self.type, {})
        out: List[str] = list(spec.get("min_reviewers", ()))
        for name in self.reviewers:
            if name not in out:
                out.append(name)
        return out


def parse_criteria(body: str) -> Tuple[List[Criterion], List[str]]:
    criteria: List[Criterion] = []
    errors: List[str] = []
    pending: Optional[List[str]] = None  # [id, text, verified]
    for line in body.splitlines():
        match = AC_RE.match(line)
        if match:
            if pending:
                criteria.append(Criterion(*pending))
            _, cid, rest = match.groups()
            parts = VERIFIED_SPLIT_RE.split(rest, maxsplit=1)
            text = parts[0].strip()
            verified = parts[1].strip() if len(parts) > 1 else ""
            pending = [cid, text, verified]
            continue
        if pending and not pending[2]:
            vmatch = VERIFIED_LINE_RE.match(line)
            if vmatch:
                pending[2] = vmatch.group(1).strip()
    if pending:
        criteria.append(Criterion(*pending))
    seen = set()
    for crit in criteria:
        if crit.id in seen:
            errors.append(f"duplicate acceptance criterion id {crit.id}")
        seen.add(crit.id)
        if not crit.text:
            errors.append(f"{crit.id} has no criterion text")
        if not crit.verified_by:
            errors.append(f"{crit.id} has no 'Verified by:' clause")
    return criteria, errors


def parse_task(path: Path) -> TaskSpec:
    text = path.read_text(encoding="utf-8")
    name_match = TASK_FILE_RE.match(path.name)
    file_id = name_match.group(1) if name_match else path.stem
    errors: List[str] = []
    meta: Dict[str, Any] = {}
    blocks = TASK_META_RE.findall(text)
    if not blocks:
        errors.append("missing ```json task``` metadata block")
    elif len(blocks) > 1:
        errors.append("more than one ```json task``` metadata block")
    else:
        try:
            parsed = json.loads(blocks[0])
            if isinstance(parsed, dict):
                meta = parsed
            else:
                errors.append("task metadata must be a JSON object")
        except json.JSONDecodeError as exc:
            errors.append(f"task metadata is not valid JSON ({exc})")
    h1 = H1_RE.search(text)
    sections = split_sections(text)
    body = find_section(sections, "acceptance criteria") or ""
    criteria, crit_errors = parse_criteria(body)
    errors.extend(crit_errors)
    spec = TaskSpec(
        path=path,
        id=str(meta.get("id") or file_id),
        meta=meta,
        heading=h1.group(1).strip() if h1 else "",
        criteria=criteria,
        sections=sections,
        errors=errors,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
    if meta.get("id") and meta.get("id") != file_id:
        spec.errors.append(f"metadata id {meta.get('id')!r} does not match file name id {file_id!r}")
    return spec


# ---------------------------------------------------------------- plan + gate


@dataclass
class PlanDoc:
    sections: Dict[str, str]
    requirements: Dict[str, str]
    final_criteria: Dict[str, str]
    questions: List[Dict[str, Any]]


def parse_plan(path: Path) -> PlanDoc:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    sections = split_sections(text)
    requirements: Dict[str, str] = {}
    for line in (find_section(sections, "requirements") or "").splitlines():
        match = REQ_RE.match(line)
        if match:
            requirements.setdefault(match.group(1), match.group(2))
    final_criteria: Dict[str, str] = {}
    for line in (find_section(sections, "final acceptance criteria") or "").splitlines():
        match = FAC_RE.match(line)
        if match:
            final_criteria.setdefault(match.group(2), match.group(3))
    questions: List[Dict[str, Any]] = []
    for line in (find_section(sections, "open questions") or "").splitlines():
        match = Q_RE.match(line)
        if match:
            box, qid, rest = match.groups()
            questions.append(
                {"id": qid, "resolved": box.lower() == "x", "text": rest,
                 "has_resolution": bool(re.search(r"resolution\s*:", rest, re.I))}
            )
    return PlanDoc(sections, requirements, final_criteria, questions)


def load_gate(wf: Workflow) -> Dict[str, Any]:
    data = read_json(wf.gate, default=None)
    return data if isinstance(data, dict) else {}


def gate_workspaces(gate: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    spaces = gate.get("workspaces")
    return spaces if isinstance(spaces, dict) else {}


def workspace_path(gate: Dict[str, Any], name: str) -> Optional[Path]:
    entry = gate_workspaces(gate).get(name)
    if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
        return None
    return Path(entry["path"]).expanduser().resolve()


def gate_commands(gate: Dict[str, Any], name: str, level: str) -> List[str]:
    entry = gate_workspaces(gate).get(name) or {}
    items = entry.get(level) if isinstance(entry, dict) else None
    return [c for c in items or [] if isinstance(c, str) and c.strip()]


def snapshot_excludes(gate: Dict[str, Any], name: str) -> List[str]:
    entry = gate_workspaces(gate).get(name) or {}
    items = entry.get("snapshot_exclude") if isinstance(entry, dict) else None
    return [c for c in items or [] if isinstance(c, str) and c.strip()]


# ---------------------------------------------------------------- package


@dataclass
class Package:
    wf: Workflow
    plan: PlanDoc
    gate: Dict[str, Any]
    tasks: Dict[str, TaskSpec]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def loops(self) -> List[int]:
        return sorted({t.loop for t in self.tasks.values() if t.loop > 0})

    def tasks_in_loop(self, loop: int) -> List[TaskSpec]:
        return [t for t in self.ordered_tasks() if t.loop == loop]

    def ordered_tasks(self) -> List[TaskSpec]:
        return [self.tasks[k] for k in sorted(self.tasks)]


def load_package(wf: Workflow) -> Package:
    tasks: Dict[str, TaskSpec] = {}
    errors: List[str] = []
    for path in wf.task_files():
        spec = parse_task(path)
        if spec.id in tasks:
            errors.append(f"duplicate task id {spec.id} ({path.name})")
            continue
        tasks[spec.id] = spec
    stray = []
    if wf.tasks_dir.is_dir():
        for path in wf.tasks_dir.iterdir():
            if path.suffix == ".md" and path.name != "index.md" and not TASK_FILE_RE.match(path.name):
                stray.append(path.name)
    for name in sorted(stray):
        errors.append(f"tasks/{name} does not match the T###-slug.md naming rule")
    return Package(wf, parse_plan(wf.plan), load_gate(wf), tasks, errors, [])


def _check_meta_types(spec: TaskSpec) -> List[str]:
    out = []
    for key, typ in META_TYPES.items():
        if key not in spec.meta:
            out.append(f"metadata is missing `{key}`")
            continue
        value = spec.meta[key]
        if isinstance(value, bool) and typ in (int, (int, float)):
            out.append(f"`{key}` must be a number")
        elif not isinstance(value, typ):
            out.append(f"`{key}` has the wrong type")
    return out


def _find_cycle(tasks: Dict[str, TaskSpec]) -> Optional[List[str]]:
    color: Dict[str, int] = {}
    stack: List[str] = []

    def visit(node: str) -> Optional[List[str]]:
        color[node] = 1
        stack.append(node)
        for dep in tasks[node].depends_on:
            if dep not in tasks:
                continue
            if color.get(dep) == 1:
                return stack[stack.index(dep):] + [dep]
            if color.get(dep) is None:
                found = visit(dep)
                if found:
                    return found
        stack.pop()
        color[node] = 2
        return None

    for node in sorted(tasks):
        if color.get(node) is None:
            found = visit(node)
            if found:
                return found
    return None


def validate(
    wf: Workflow,
    state: Optional[Dict[str, Any]] = None,
    for_approval: bool = False,
) -> Package:
    """Validate the whole plan package. Errors block submit/approve."""
    pkg = load_package(wf)
    err, warn = pkg.errors, pkg.warnings

    if not wf.request.is_file() or not wf.request.read_text(encoding="utf-8").strip():
        err.append("request.md is missing or empty")
    if not wf.plan.is_file():
        err.append("plan.md is missing")
    types_present = {t.type for t in pkg.tasks.values()}
    has_code = bool(types_present & CODE_LIKE_TYPES)

    # plan.md sections
    required = list(PLAN_SECTIONS) + (list(PLAN_SECTIONS_CODE) if has_code else [])
    for key in required:
        body = find_section(pkg.plan.sections, key)
        if body is None:
            err.append(f"plan.md is missing a `## {key.title()}` section")
        elif not body.strip():
            err.append(f"plan.md section `{key.title()}` is empty")
    if not pkg.plan.requirements:
        err.append("plan.md `## Requirements` lists no `- R1: ...` requirements")
    if not pkg.plan.final_criteria:
        err.append("plan.md `## Final acceptance criteria` lists no `- [ ] FAC1: ...` criteria")
    for q in pkg.plan.questions:
        if q["resolved"] and not q["has_resolution"]:
            err.append(f"open question {q['id']} is checked but has no `Resolution:` text")
        if for_approval and not q["resolved"]:
            err.append(f"open question {q['id']} is unresolved: {q['text']}")

    # gate.json
    spaces = gate_workspaces(pkg.gate)
    if not wf.gate.is_file():
        err.append("gate.json is missing")
    elif not spaces:
        err.append("gate.json has no `workspaces`")
    for name, entry in spaces.items():
        if not isinstance(entry, dict):
            err.append(f"gate.json workspace `{name}` must be an object")
            continue
        path = workspace_path(pkg.gate, name)
        if path is None:
            err.append(f"gate.json workspace `{name}` has no `path`")
        elif not path.is_dir():
            err.append(f"gate.json workspace `{name}` path {path} is not a directory")
        for level in ("standard", "final"):
            items = entry.get(level)
            if items is not None and not (
                isinstance(items, list) and all(isinstance(c, str) for c in items)
            ):
                err.append(f"gate.json `{name}.{level}` must be a list of command strings")
        users = [t for t in pkg.tasks.values() if t.workspace == name]
        if any(t.type in CODE_LIKE_TYPES for t in users) and not gate_commands(pkg.gate, name, "standard"):
            err.append(f"workspace `{name}` has code/test tasks but no standard gate commands")
        elif users and not gate_commands(pkg.gate, name, "standard"):
            warn.append(
                f"workspace `{name}` has no standard gate commands; plan.md must explain why"
            )

    # tasks
    if not pkg.tasks:
        err.append("tasks/ contains no task documents")
    ids = set(pkg.tasks)
    for tid, spec in sorted(pkg.tasks.items()):
        p = f"{tid}:"
        for e in spec.errors:
            err.append(f"{p} {e}")
        for e in _check_meta_types(spec):
            err.append(f"{p} {e}")
        ttype = spec.type
        tspec = TASK_TYPES.get(ttype)
        if tspec is None:
            err.append(f"{p} unknown type `{ttype}` (allowed: {', '.join(sorted(TASK_TYPES))})")
            continue
        if spec.loop < 1:
            err.append(f"{p} `loop` must be an integer >= 1")
        for dep in spec.depends_on:
            if dep == tid:
                err.append(f"{p} depends on itself")
            elif dep not in ids:
                err.append(f"{p} depends on unknown task {dep}")
            elif pkg.tasks[dep].loop > spec.loop:
                err.append(f"{p} depends on {dep}, which runs in a later loop")
        if not spec.meta.get("requirements"):
            err.append(f"{p} traces to no requirement (`requirements` is empty)")
        for req in spec.meta.get("requirements") or []:
            if req not in pkg.plan.requirements:
                err.append(f"{p} references unknown requirement {req}")
        if spec.workspace not in spaces:
            err.append(f"{p} workspace `{spec.workspace}` is not declared in gate.json")
        tf = spec.test_forward
        if tf not in TEST_FORWARD_MODES:
            err.append(f"{p} `test_forward` must be one of {', '.join(TEST_FORWARD_MODES)}")
        elif tf not in tspec["test_forward"]:
            err.append(f"{p} test_forward `{tf}` is not allowed for `{ttype}` tasks")
        justification = str(spec.meta.get("test_forward_justification") or "").strip()
        if ttype in CODE_LIKE_TYPES and tf == "not-applicable" and len(justification) < 40:
            err.append(f"{p} code task with test_forward not-applicable needs a real `test_forward_justification`")
        allowed_authors = [list(seq) for seq in tspec["authors"]]
        if ttype == "code" and tf == "not-applicable":
            allowed_authors.append(["code-author"])
        if spec.authors not in allowed_authors:
            err.append(
                f"{p} authors {spec.authors} are not an allowed sequence for `{ttype}` "
                f"(allowed: {allowed_authors})"
            )
        for reviewer in spec.reviewers:
            if reviewer not in REVIEWERS:
                err.append(f"{p} unknown reviewer `{reviewer}`")
        missing = [r for r in tspec["min_reviewers"] if r not in spec.reviewers]
        if missing:
            err.append(f"{p} reviewers must include {missing} for `{ttype}` tasks")
        if tf in ("red-green", "characterization") and not spec.validation("red_green"):
            err.append(f"{p} test_forward `{tf}` needs `validation.red_green` test commands")
        if ttype in CODE_LIKE_TYPES and not spec.validation("task"):
            err.append(f"{p} code/test tasks need `validation.task` commands")
        days = spec.meta.get("estimated_days")
        if isinstance(days, (int, float)) and not isinstance(days, bool):
            if days <= 0 or days > MAX_TASK_DAYS:
                err.append(f"{p} estimated_days {days} is outside (0, {MAX_TASK_DAYS}]; split the task")
        for rel in spec.expected_paths:
            if rel.startswith("/") or ".." in Path(rel).parts:
                err.append(f"{p} expected_paths entry {rel!r} must be relative to the workspace")
        if spec.parallel_safe:
            if ttype not in PROSE_TYPES:
                err.append(f"{p} parallel_safe is only allowed for document-type tasks")
            if not spec.expected_paths:
                err.append(f"{p} parallel_safe tasks must declare expected_paths")
        if spec.external_writes and ttype != "integration":
            err.append(f"{p} external_writes is only allowed on `integration` tasks")
        if not spec.criteria:
            err.append(f"{p} has no acceptance criteria (`- [ ] AC1: ... — Verified by: ...`)")
        for key in list(TASK_SECTIONS) + (list(TASK_SECTIONS_CODE) if ttype in CODE_LIKE_TYPES else []):
            if find_section(spec.sections, key) is None:
                err.append(f"{p} is missing a `## {key.title()}` section")
        if not spec.heading.startswith(tid):
            warn.append(f"{p} first heading should start with `# {tid} — ...`")

    cycle = _find_cycle(pkg.tasks)
    if cycle:
        err.append("dependency cycle: " + " -> ".join(cycle))
    loops = pkg.loops()
    if loops and loops != list(range(1, len(loops) + 1)):
        err.append(f"loops must be numbered contiguously from 1 (found {loops})")

    # scope trace: once scope.md exists, every requirement serves something the human confirmed,
    # every deliverable is served, and every task that writes declares its footprint.
    if wf.scope.is_file():
        from . import ledger
        from . import scope as scopemod
        from .common import ROOT_PATTERNS
        from .roster import AUTHORS

        citable = scopemod.citable(wf, ledger.read(wf))
        served: Set[str] = set()
        for req, text in sorted(pkg.plan.requirements.items()):
            ids = scopemod.parse_serves(text)
            if not ids:
                err.append(f"requirement {req} has no `Serves: D#` — every requirement serves a deliverable "
                           "(or significant term / accepted proposal) of the confirmed scope")
            for unknown in scopemod.unknown_ids(ids, set(citable)):
                err.append(f"requirement {req} serves {unknown}, which the confirmed scope does not have")
            served.update(ids)
        scope_doc = scopemod.parse(wf) or {"deliverables": {}}
        for deliverable in sorted(scope_doc["deliverables"]):
            if deliverable not in served:
                err.append(f"deliverable {deliverable} is served by no requirement")
        for tid, spec in sorted(pkg.tasks.items()):
            writes = bool(set(spec.authors) & (AUTHORS | {"planning-author"}))
            if writes and not spec.expected_paths:
                err.append(f"{tid}: declare `expected_paths` — the files, directories, or globs this task will "
                           "change (include index files, lockfiles, generated files)")
            for rel in spec.expected_paths:
                if rel.strip() in ROOT_PATTERNS:
                    err.append(f"{tid}: expected_paths entry {rel!r} is the whole workspace; name what changes")

    # requirement coverage: covered by a task or explicitly listed out of scope
    covered = {r for t in pkg.tasks.values() for r in t.meta.get("requirements") or []}
    out_of_scope = find_section(pkg.plan.sections, "out of scope") or ""
    for req in sorted(pkg.plan.requirements):
        if req not in covered and not re.search(rf"\b{re.escape(req)}\b", out_of_scope):
            err.append(f"requirement {req} is covered by no task and not listed under Out of scope")

    # revisions must not rewrite accepted history
    if state:
        prior = state.get("tasks") or {}
        accepted_max = 0
        for tid, info in prior.items():
            if info.get("status") == "ACCEPTED":
                accepted_max = max(accepted_max, int(re.sub(r"\D", "", tid) or 0))
                spec = pkg.tasks.get(tid)
                if spec is None:
                    err.append(f"accepted task {tid} was removed from tasks/")
                elif info.get("doc_sha256") and spec.sha256 != info.get("doc_sha256"):
                    err.append(f"accepted task {tid} document changed after acceptance")
        for tid in pkg.tasks:
            if tid not in prior and accepted_max and int(re.sub(r"\D", "", tid) or 0) <= accepted_max:
                err.append(f"new task {tid} must be numbered after the last accepted task")
    return pkg


def plan_hash(wf: Workflow) -> str:
    """Hash the frozen planning artifacts (request, plan, architecture, gate, tasks)."""
    digest = hashlib.sha256()
    for path in wf.frozen_files():
        digest.update(wf.rel(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def frozen_mtime(wf: Workflow) -> float:
    stamps = [p.stat().st_mtime for p in wf.frozen_files()]
    return max(stamps) if stamps else 0.0
