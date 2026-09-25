"""Content snapshots of a workspace, without touching the user's index or refs.

A snapshot is a git tree id describing the exact working-tree content of a
workspace (tracked + untracked, honoring .gitignore):

* git workspaces   — `git add -A` into a *temporary copy* of the repository's
                     index, then `git write-tree`. HEAD, branches, and the real
                     index are never modified.
* other workspaces — the same, using a private shadow repository under
                     <workflow>/.orch/shadow/<name>.git.

Every verdict in the ledger cites the snapshot it evaluated; gates compare that
id against a fresh snapshot, so any change after a review makes the review
stale. The workflow directory itself is always excluded from the snapshot.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .common import OrchError, Workflow

DEFAULT_EXCLUDES = (
    ".DS_Store",
    "__pycache__/",
    "*.pyc",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".coverage",
    "htmlcov/",
    "coverage.out",
    "*.coverprofile",
    "node_modules/",
    ".venv/",
)

GIT_TIMEOUT = 600


@dataclass
class Snapshot:
    workspace: str
    id: str
    tree: str
    mode: str  # "git" | "shadow"
    toplevel: str
    prefix: str = ""
    gitdir: str = ""
    scope: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Snapshot":
        return cls(
            workspace=data["workspace"],
            id=data["id"],
            tree=data["tree"],
            mode=data["mode"],
            toplevel=data["toplevel"],
            prefix=data.get("prefix", ""),
            gitdir=data.get("gitdir", ""),
            scope=list(data.get("scope") or []),
        )


def _run_git(
    args: Sequence[str],
    cwd: Path,
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
) -> str:
    full_env = dict(os.environ)
    full_env.setdefault("GIT_OPTIONAL_LOCKS", "0")
    if env:
        full_env.update(env)
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=full_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=GIT_TIMEOUT,
    )
    if check and proc.returncode != 0:
        raise OrchError(
            f"git {' '.join(args[:3])} failed in {cwd}: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout


def detect(ws_path: Path) -> Dict[str, str]:
    ws_path = Path(ws_path).resolve()
    if not ws_path.is_dir():
        raise OrchError(f"workspace path {ws_path} is not a directory")
    proc = subprocess.run(
        ["git", "-C", str(ws_path), "rev-parse", "--show-toplevel"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        top = Path(proc.stdout.strip()).resolve()
        prefix = os.path.relpath(ws_path, top)
        return {"mode": "git", "toplevel": str(top), "prefix": "" if prefix == "." else prefix}
    return {"mode": "shadow", "toplevel": str(ws_path), "prefix": ""}


def _join(prefix: str, rel: str) -> str:
    rel = rel.strip("/")
    if not prefix:
        return rel or "."
    return f"{prefix}/{rel}" if rel and rel != "." else prefix


def _pathspecs(
    wf: Workflow,
    toplevel: Path,
    prefix: str,
    scope: Sequence[str],
    excludes: Sequence[str],
) -> List[str]:
    specs = [_join(prefix, s) for s in scope] if scope else [prefix or "."]
    glob_root = f"{prefix}/" if prefix else ""
    for pattern in list(DEFAULT_EXCLUDES) + list(excludes):
        pattern = pattern.strip()
        if not pattern:
            continue
        if pattern.endswith("/"):
            specs.append(f":(exclude,glob){glob_root}**/{pattern}**")
        else:
            specs.append(f":(exclude,glob){glob_root}**/{pattern}")
    try:
        rel_wf = wf.root.resolve().relative_to(toplevel.resolve())
        specs.append(f":(exclude){rel_wf.as_posix()}")
    except ValueError:
        pass
    return specs


def _scoped_id(prefix_char: str, listing: str) -> str:
    return f"{prefix_char}:" + hashlib.sha256(listing.encode("utf-8")).hexdigest()[:40]


def take(
    wf: Workflow,
    workspace: str,
    ws_path: Path,
    scope: Sequence[str] = (),
    excludes: Sequence[str] = (),
) -> Snapshot:
    info = detect(ws_path)
    toplevel = Path(info["toplevel"])
    prefix = info["prefix"]
    tmp_dir = wf.control / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    specs = _pathspecs(wf, toplevel, prefix, scope, excludes)
    if info["mode"] == "git":
        index = tmp_dir / f"index-{os.getpid()}-{time.time_ns()}"
        real = _run_git(["rev-parse", "--git-path", "index"], toplevel).strip()
        real_path = Path(real) if Path(real).is_absolute() else toplevel / real
        try:
            if real_path.is_file():
                shutil.copyfile(real_path, index)
            env = {"GIT_INDEX_FILE": str(index)}
            _run_git(["add", "-A", "--", *specs], toplevel, env=env)
            tree = _run_git(["write-tree"], toplevel, env=env).strip()
        finally:
            for leftover in (index, Path(str(index) + ".lock")):
                if leftover.exists():
                    leftover.unlink()
        if scope:
            listing = _run_git(
                ["ls-tree", "-r", "--full-tree", tree, "--", *[_join(prefix, s) for s in scope]],
                toplevel,
            )
            snap_id = _scoped_id("gs", listing)
        elif prefix:
            sub = _run_git(["rev-parse", f"{tree}:{prefix}"], toplevel, check=False).strip()
            snap_id = f"g:{sub or 'empty'}"
        else:
            snap_id = f"g:{tree}"
        return Snapshot(workspace, snap_id, tree, "git", str(toplevel), prefix, "", list(scope))

    gitdir = wf.control / "shadow" / f"{workspace}.git"
    if not (gitdir / "HEAD").exists():
        gitdir.parent.mkdir(parents=True, exist_ok=True)
        _run_git(["init", "--bare", "-q", str(gitdir)], wf.control)
    env = {
        "GIT_DIR": str(gitdir),
        "GIT_WORK_TREE": str(toplevel),
        "GIT_INDEX_FILE": str(gitdir / "orch-index"),
    }
    _run_git(["-c", "core.bare=false", "add", "-A", "--", *specs], toplevel, env=env)
    tree = _run_git(["-c", "core.bare=false", "write-tree"], toplevel, env=env).strip()
    if scope:
        listing = _run_git(
            ["ls-tree", "-r", "--full-tree", tree, "--", *[_join("", s) for s in scope]],
            toplevel,
            env={"GIT_DIR": str(gitdir)},
        )
        snap_id = _scoped_id("ss", listing)
    else:
        snap_id = f"s:{tree}"
    return Snapshot(workspace, snap_id, tree, "shadow", str(toplevel), "", str(gitdir), list(scope))


def _diff_base(a: Snapshot, b: Snapshot) -> Dict[str, Any]:
    if a.mode != b.mode or a.toplevel != b.toplevel or a.gitdir != b.gitdir:
        raise OrchError("cannot diff snapshots from different workspaces")
    paths = [_join(a.prefix, s) for s in a.scope] if a.scope else [a.prefix or "."]
    env = {"GIT_DIR": a.gitdir} if a.mode == "shadow" else None
    return {"cwd": Path(a.toplevel), "env": env, "paths": paths}


def diff(a: Snapshot, b: Snapshot, unified: int = 3) -> str:
    base = _diff_base(a, b)
    return _run_git(
        ["diff", "--no-color", "--no-ext-diff", "-M", f"-U{unified}", a.tree, b.tree, "--", *base["paths"]],
        base["cwd"],
        env=base["env"],
    )


def name_status(a: Snapshot, b: Snapshot) -> List[Dict[str, str]]:
    base = _diff_base(a, b)
    out = _run_git(
        ["diff", "--no-color", "--no-ext-diff", "-M", "--name-status", a.tree, b.tree, "--", *base["paths"]],
        base["cwd"],
        env=base["env"],
    )
    changes = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0][:1]
        path = parts[-1]
        entry = {"status": status, "path": _strip_prefix(path, a.prefix)}
        if status == "R" and len(parts) >= 3:
            entry["from"] = _strip_prefix(parts[1], a.prefix)
        changes.append(entry)
    return changes


def _strip_prefix(path: str, prefix: str) -> str:
    if prefix and path.startswith(prefix + "/"):
        return path[len(prefix) + 1:]
    return path


def file_at(snap: Snapshot, rel: str) -> Optional[str]:
    """Content of workspace-relative `rel` in `snap`, or None if absent."""
    env = {"GIT_DIR": snap.gitdir} if snap.mode == "shadow" else None
    proc = subprocess.run(
        ["git", "show", f"{snap.tree}:{_join(snap.prefix, rel)}"],
        cwd=snap.toplevel,
        env={**os.environ, **(env or {})},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return proc.stdout if proc.returncode == 0 else None


def composite_id(snaps: Sequence[Snapshot]) -> str:
    return ";".join(f"{s.workspace}={s.id}" for s in sorted(snaps, key=lambda s: s.workspace))
