"""Content checkpoints, excluding generated trees and the pipeline's own files."""
import hashlib
import json
import os
import stat
from pathlib import Path


SKIP = {".git", ".tp", "node_modules", "__pycache__", ".venv", "venv", ".cache",
        ".pytest_cache", ".mypy_cache", "target", "dist", ".next"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def fingerprint(path, cache):
    info = path.lstat()
    signature = [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
                 info.st_ctime_ns, info.st_mode]
    key = str(path)
    previous = cache.get(key)
    if previous and previous[0] == signature:
        return previous[1]
    if path.is_symlink():
        value = digest(["link", os.readlink(path)])
    elif stat.S_ISREG(info.st_mode):
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        value = digest([hasher.hexdigest(), stat.S_IMODE(info.st_mode)])
    else:
        raise ValueError(f"Cannot checkpoint special file: {path}")
    cache[key] = [signature, value]
    return value


def take(workspaces, workflow, tasks, cache):
    result = {}
    roots = {w["name"]: Path(w["path"]) for w in workspaces}
    for name, root in roots.items():
        excluded = [workflow] + [p for p in roots.values() if p != root and root in p.parents]
        paths = set()
        for directory, dirs, files in os.walk(root, followlinks=False):
            here = Path(directory)
            # Directory symlinks are artifacts too, but never followed.
            files += [d for d in dirs if (here / d).is_symlink()]
            dirs[:] = [d for d in dirs if d not in SKIP and not (here / d).is_symlink()
                       and not any(here / d == p for p in excluded)]
            for filename in files:
                path = here / filename
                if path == workflow or workflow in path.parents:
                    continue
                paths.add(path)
        # Explicit task files count even inside an ordinarily ignored generated tree.
        for task in tasks:
            if task["workspace"] == name:
                for relative in task["paths"]:
                    path = root / relative
                    if path.exists() or path.is_symlink():
                        paths.add(path)
        for path in sorted(paths):
            result[f"{name}:{path.relative_to(root).as_posix()}"] = fingerprint(path, cache)
    return result


def changed(before, after):
    return sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
