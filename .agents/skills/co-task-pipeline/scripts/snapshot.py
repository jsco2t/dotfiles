"""Content checkpoints, excluding generated trees and the pipeline's own files."""
import hashlib
import json
import os
import stat
import subprocess
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


def take(workspaces, workflow, tasks, cache, input_roots=()):
    result = {}
    roots = {w["name"]: Path(w["path"]) for w in workspaces}
    modes = {w["name"]: w.get("snapshot", "walk") for w in workspaces}
    for name, root in roots.items():
        excluded = [workflow] + [p for p in roots.values() if p != root and root in p.parents]
        paths = set()
        workspace = next(w for w in workspaces if w["name"] == name)
        monitoring = workspace.get("monitor")
        monitored = [root / p for p in monitoring] if monitoring is not None else [root]
        monitored += [root / p for task in list(tasks) + list(input_roots) if task["workspace"] == name for p in task["paths"]]

        def selected(path):
            return any(path == p or p in path.parents for p in monitored)

        def traverse(path):
            return selected(path) or any(path in p.parents for p in monitored)

        if modes[name] == "git":
            # Git performs ignore pruning without opening SDKs, caches or build outputs.
            # Keep tracked ignored files and ordinary untracked source in the checkpoint.
            process = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached",
                                      "--others", "--exclude-standard", "--", "."],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if process.returncode:
                raise ValueError(f"Git snapshot failed for {root}: {os.fsdecode(process.stderr).strip()}")
            for raw in process.stdout.split(b"\0"):
                if raw:
                    path = root / os.fsdecode(raw)
                    if any(path == p or p in path.parents for p in excluded):
                        continue
                    if path.is_dir() and not path.is_symlink():
                        raise ValueError(f"Git snapshot needs a separate workspace for submodule {path}")
                    if selected(path) and (path.exists() or path.is_symlink()):
                        paths.add(path)
        if modes[name] == "git":
            patterns = [p for item in input_roots if item["workspace"] == name for p in item.get("patterns", [])]
            if patterns:
                # Declared check inputs include ignored dependencies, including new glob matches.
                prefixes = [p for item in input_roots if item["workspace"] == name for p in item["paths"]]
                process = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--others", "--ignored",
                                          "--exclude-standard", "--", *prefixes],
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if process.returncode:
                    raise ValueError("Git input enumeration failed: " + os.fsdecode(process.stderr))
                for raw in process.stdout.split(b"\0"):
                    if raw:
                        path = root / os.fsdecode(raw)
                        from checks import matches
                        if any(matches(path.relative_to(root).as_posix(), pattern) for pattern in patterns) and not any(path == p or p in path.parents for p in excluded):
                            paths.add(path)
        for directory, dirs, files in os.walk(root, followlinks=False) if modes[name] == "walk" else ():
            here = Path(directory)
            # Directory symlinks are artifacts too, but never followed.
            files += [d for d in dirs if (here / d).is_symlink()]
            dirs[:] = [d for d in dirs if d != ".git" and
                       (d not in SKIP or any(here / d == p or here / d in p.parents for p in monitored if p != root))
                       and not (here / d).is_symlink() and traverse(here / d)
                       and not any(here / d == p for p in excluded)]
            for filename in files:
                path = here / filename
                if path == workflow or workflow in path.parents:
                    continue
                if selected(path):
                    paths.add(path)
        # Explicit task files count even inside an ordinarily ignored generated tree.
        for task in tasks:
            if task["workspace"] == name:
                for relative in task["paths"]:
                    path = root / relative
                    if path.exists() or path.is_symlink():
                        paths.add(path)
        for path in sorted(paths):
            if any(path == p or p in path.parents for p in excluded):
                continue
            result[f"{name}:{path.relative_to(root).as_posix()}"] = fingerprint(path, cache)
    return result


def changed(before, after):
    return sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
