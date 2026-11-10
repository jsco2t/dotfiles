"""What changed in a workspace directory between two moments. Scoped to the workspace
directory itself (never the whole enclosing repository), so parallel sessions that share
a repository do not see each other's work."""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import stat
import subprocess
import time
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tp", ".mypy_cache", ".pytest_cache",
             ".idea", ".vscode", "target", "dist", ".next", ".cache"}
SKIP_FILES = {".DS_Store"}
HASH_LIMIT = 2 * 1024 * 1024
# A file modified this close to when it was hashed may change again without its mtime moving
# (coarse filesystem clocks): such a hash is never reused. Git's "racily clean" rule.
RACY_NS = 2_000_000_000

Snapshot = Dict[str, str]
# Empty dot-files a task may legitimately create; every other empty dot-path is suspect (below).
REAL_EMPTY_DOTFILES = {".gitkeep", ".keep", ".gitignore", ".nojekyll"}


def sandbox_placeholder(root: Path, rel: str) -> bool:
    """A sandbox's per-command deny mount: Claude Code's sandbox masks dotfiles and dot-folders
    (.bashrc, .zshrc, .mcp.json, .claude/agents, .idea, ...) by mounting /dev/null over them, which
    leaves an empty file or a character device behind on the host. They come and go between
    commands, so no task wrote them — in real runs they were flagged as off-path edits on every
    record (dozens of no-op fix rounds and several questions to the human)."""
    parts = PurePosixPath(rel).parts
    if not parts or not any(p.startswith(".") for p in parts) or parts[-1] in REAL_EMPTY_DOTFILES:
        return False
    try:
        st = os.lstat(Path(root) / rel)
    except OSError:
        return False  # gone: no evidence it was a placeholder, so it stays a change
    return stat.S_ISCHR(st.st_mode) or (stat.S_ISREG(st.st_mode) and st.st_size == 0)


def _fingerprint(path: Path, st: os.stat_result) -> str:
    if st.st_size <= HASH_LIMIT:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    return f"{st.st_size}:{st.st_mtime_ns}"


def _load_cache(cache: Optional[Path]) -> Dict[str, list]:
    if cache is None or not cache.exists():
        return {}
    try:
        data = json.loads(cache.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_cache(cache: Path, entries: Dict[str, list]) -> None:
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries))
    os.replace(tmp, cache)


def take(root: Path, exclude: Iterable[Path] = (), cache: Optional[Path] = None,
         only: Optional[Iterable[str]] = None, ignore: Iterable[str] = ()) -> Snapshot:
    """{workspace-relative path: content fingerprint}. cache: a stat cache file — a file whose size
    and mtime match its cached entry keeps its cached hash instead of being read again (the same
    trade git's index makes; contents swapped under an unchanged size and mtime go unseen). only:
    patterns, as `matches` reads them, limiting which files are fingerprinted. ignore: patterns
    left out entirely. Only regular files count: a sandbox's per-command mount points (character
    devices over dotfiles) come and go with each command, and reading a FIFO would block."""
    root = root.resolve()
    skip = {p.resolve() for p in exclude}
    patterns = list(only) if only is not None else None
    ignored = list(ignore)
    known = _load_cache(cache)
    fresh: Dict[str, list] = {}
    started = time.time_ns()
    snap: Snapshot = {}
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and (here / d).resolve() not in skip]
        for name in filenames:
            if name in SKIP_FILES:
                continue
            p = here / name
            rel = p.relative_to(root).as_posix()
            if patterns is not None and not matches(rel, patterns):
                continue
            if ignored and matches(rel, ignored):
                continue
            try:
                st = p.stat()
                if not stat.S_ISREG(st.st_mode):
                    continue
                if st.st_size == 0 and sandbox_placeholder(root, rel):
                    continue
                prev = known.get(rel)
                if prev and len(prev) == 4 and prev[3] and prev[0] == st.st_size and prev[1] == st.st_mtime_ns:
                    fp, trusted = prev[2], True
                else:
                    fp, trusted = _fingerprint(p, st), st.st_mtime_ns < started - RACY_NS
            except OSError:
                continue
            snap[rel] = fp
            fresh[rel] = [st.st_size, st.st_mtime_ns, fp, trusted]
    if cache is not None:
        _save_cache(cache, fresh if patterns is None else {**known, **fresh})
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
        if out.returncode != 0:
            return None
        top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=30).stdout.strip() or str(root)
        # Untracked sandbox placeholders are noise. -z gives the real (unquoted) path of each entry,
        # relative to the repository top; only entries proven to be placeholders are dropped.
        raw = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "-z", "-uall", "--", "."],
                             capture_output=True, text=True, timeout=120, errors="surrogateescape")
        noise = set()
        if raw.returncode == 0:
            noise = {e[3:] for e in raw.stdout.split("\0") if e.startswith("?? ")
                     and sandbox_placeholder(Path(top), e[3:])}
        keep = [ln for ln in out.stdout.splitlines()
                if not (ln.startswith("?? ") and _unquote(ln[3:]) in noise)]
        return "".join(ln + "\n" for ln in keep)
    except (OSError, subprocess.SubprocessError):
        return None


def _unquote(path: str) -> str:
    """A porcelain path as git prints it without -z: C-quoted when unusual; plain otherwise."""
    if len(path) >= 2 and path[0] == path[-1] == '"':
        try:
            return path[1:-1].encode("latin-1", "backslashreplace").decode("unicode_escape").encode(
                "latin-1").decode("utf-8", "surrogateescape")
        except (UnicodeError, ValueError):
            return path
    return path


def hash_files(root: Path, rels: Iterable[str]) -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {}
    for rel in rels:
        p = root / rel
        out[rel] = hashlib.sha1(p.read_bytes()).hexdigest() if p.is_file() else None
    return out
