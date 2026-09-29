"""What changed in a workspace directory between two moments. Scoped to the workspace
directory itself (never the whole enclosing repository), so parallel sessions that share
a repository do not see each other's work."""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tp", ".mypy_cache", ".pytest_cache",
             ".idea", ".vscode", "target", "dist", ".next", ".cache"}
SKIP_FILES = {".DS_Store"}
HASH_LIMIT = 2 * 1024 * 1024

Snapshot = Dict[str, str]


def _fingerprint(path: Path) -> str:
    st = path.stat()
    if st.st_size <= HASH_LIMIT:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    return f"{st.st_size}:{st.st_mtime_ns}"


def take(root: Path, exclude: Iterable[Path] = ()) -> Snapshot:
    root = root.resolve()
    skip = {p.resolve() for p in exclude}
    snap: Snapshot = {}
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and (here / d).resolve() not in skip]
        for name in filenames:
            if name in SKIP_FILES:
                continue
            p = here / name
            try:
                snap[p.relative_to(root).as_posix()] = _fingerprint(p)
            except OSError:
                continue
    return snap


def diff(before: Snapshot, after: Snapshot) -> List[str]:
    keys = set(before) | set(after)
    return sorted(k for k in keys if before.get(k) != after.get(k))


def save(path: Path, snap: Snapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap))


def load(path: Path) -> Snapshot:
    return json.loads(path.read_text()) if path.exists() else {}


def matches(rel: str, patterns: Iterable[str]) -> bool:
    for pat in patterns:
        pat = pat.rstrip("/")
        if rel == pat or fnmatch.fnmatchcase(rel, pat) or rel.startswith(pat + "/"):
            return True
        if pat.endswith("/**") and (rel == pat[:-3] or rel.startswith(pat[:-2])):
            return True
    return False


def git_porcelain(root: Path) -> Optional[str]:
    """`git status --porcelain` limited to `root`, or None when root is not in a git work tree."""
    try:
        inside = subprocess.run(["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
                                capture_output=True, text=True, timeout=30)
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return None
        out = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "-uall", "--", "."],
                             capture_output=True, text=True, timeout=120)
        return out.stdout if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def hash_files(root: Path, rels: Iterable[str]) -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {}
    for rel in rels:
        p = root / rel
        out[rel] = hashlib.sha1(p.read_bytes()).hexdigest() if p.is_file() else None
    return out
