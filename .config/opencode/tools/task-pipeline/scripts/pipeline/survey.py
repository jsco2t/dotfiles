"""A deterministic structure map of a repository — the part of planning research a script
does in seconds: git pin, size by directory and language, Go packages and their doc lines,
entry points, build targets, docs, and tests."""
from __future__ import annotations

import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .snapshot import SKIP_DIRS

LANG = {".go": "Go", ".py": "Python", ".rs": "Rust", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
        ".jsx": "JavaScript", ".mjs": "JavaScript", ".vue": "Vue", ".svelte": "Svelte", ".java": "Java", ".kt": "Kotlin",
        ".c": "C", ".h": "C", ".cc": "C++", ".cpp": "C++", ".hpp": "C++", ".cs": "C#", ".rb": "Ruby", ".php": "PHP",
        ".swift": "Swift", ".sh": "Shell", ".bash": "Shell", ".md": "Markdown", ".yaml": "YAML", ".yml": "YAML",
        ".json": "JSON", ".toml": "TOML", ".proto": "Protobuf", ".sql": "SQL", ".tf": "Terraform", ".css": "CSS",
        ".scss": "CSS", ".html": "HTML", ".lua": "Lua"}
TEST_RE = re.compile(r"(_test\.go|^test_.*\.py|_test\.py|\.(test|spec)\.[jt]sx?|_spec\.rb)$")
MAKE_TARGET = re.compile(r"^([A-Za-z0-9][\w.-]*)\s*:(?!=)")
MAX_BYTES = 2 * 1024 * 1024


def _git(root: Path, *args: str) -> Optional[str]:
    try:
        out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _files(root: Path, in_git: bool) -> List[str]:
    if in_git:
        listed = _git(root, "ls-files", "-co", "--exclude-standard", "--", ".")
        if listed is not None:
            return [ln for ln in listed.splitlines() if ln and (root / ln).is_file()]
    out = []
    for p in root.rglob("*"):
        if p.is_file() and not any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            out.append(p.relative_to(root).as_posix())
    return sorted(out)


def _lines(path: Path) -> int:
    try:
        data = path.read_bytes()[:MAX_BYTES]
    except OSError:
        return 0
    if b"\0" in data[:8192]:
        return 0
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


def _go_doc(text: str) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("package "):
            doc: List[str] = []
            j = i - 1
            while j >= 0 and lines[j].startswith("//"):
                doc.insert(0, lines[j][2:].strip())
                j -= 1
            para = " ".join(d for d in doc if not d.startswith(("go:", "+build")))
            first = re.split(r"(?<=\.)\s", para, maxsplit=1)[0]
            return first[:160]
    return ""


def survey(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    commit = _git(root, "rev-parse", "HEAD")
    git = None
    if commit:
        git = {"commit": commit, "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"),
               "remote": _git(root, "config", "--get", "remote.origin.url"),
               "dirty": bool(_git(root, "status", "--porcelain", "--", "."))}
    files = _files(root, git is not None)

    langs: Dict[str, int] = defaultdict(int)
    dirs: Dict[str, Dict[str, Any]] = {}
    go_pkgs: Dict[str, Dict[str, Any]] = {}
    tests = 0
    test_dirs: Dict[str, int] = defaultdict(int)
    docs: List[str] = []
    entry: List[str] = []
    for rel in files:
        p = root / rel
        parts = rel.split("/")
        n = _lines(p)
        lang = LANG.get(p.suffix.lower(), "other")
        langs[lang] += n
        for depth in (1, 2):
            if len(parts) > depth:
                key = "/".join(parts[:depth])
                d = dirs.setdefault(key, {"path": key, "files": 0, "lines": 0, "languages": defaultdict(int)})
                d["files"] += 1
                d["lines"] += n
                d["languages"][lang] += n
        if TEST_RE.search(parts[-1]):
            tests += 1
            test_dirs[parts[0] if len(parts) > 1 else "."] += 1
        if p.suffix == ".md":
            docs.append(rel)
        if p.suffix == ".go":
            pkg_dir = "/".join(parts[:-1]) or "."
            info = go_pkgs.setdefault(pkg_dir, {"dir": pkg_dir, "name": "", "doc": "", "files": 0, "tests": 0,
                                                "lines": 0})
            info["lines"] += n
            if rel.endswith("_test.go"):
                info["tests"] += 1
                continue
            info["files"] += 1
            try:
                text = p.read_text(errors="replace")
            except OSError:
                continue
            m = re.search(r"^package (\w+)", text, re.M)
            if m and not info["name"]:
                info["name"] = m.group(1)
            doc = _go_doc(text)
            # The Go convention ("Package x ..." / "Command x ...") beats a file-header comment; doc.go beats both.
            rank = (2 if parts[-1] == "doc.go" else 0) + (1 if doc.startswith(("Package ", "Command ")) else 0)
            if doc and rank > info.get("_rank", -1):
                info["doc"], info["_rank"] = doc, rank
        if parts[-1] in ("main.rs",) and "src" in parts:
            entry.append(rel)
    for pkg in go_pkgs.values():
        pkg.pop("_rank", None)
        if pkg["name"] == "main":
            entry.append(pkg["dir"])

    targets: Dict[str, List[str]] = {}
    for rel in files:
        name = rel.rsplit("/", 1)[-1]
        if rel.count("/") > 1:
            continue
        p = root / rel
        if name in ("Makefile", "GNUmakefile") or name.endswith(".mk"):
            found = [m.group(1) for ln in p.read_text(errors="replace").splitlines()
                     if (m := MAKE_TARGET.match(ln)) and not m.group(1).startswith(".")]
            if found:
                targets[rel] = sorted(set(found))
        elif name == "package.json":
            try:
                data = json.loads(p.read_text())
            except (ValueError, OSError):
                continue
            if data.get("scripts"):
                targets[rel] = sorted(data["scripts"])
            bins = data.get("bin")
            if bins:
                entry += [f"{rel}:bin:{b}" for b in (bins if isinstance(bins, dict) else {data.get('name'): bins})]
        elif name == "pyproject.toml":
            text = p.read_text(errors="replace")
            block = re.search(r"^\[project\.scripts\]\n((?:[^\[].*\n?)*)", text, re.M)
            if block:
                entry += [f"{rel}:script:{ln.split('=')[0].strip()}" for ln in block.group(1).splitlines() if "=" in ln]
        elif name in ("magefile.go",) or (rel.startswith("magefiles/") and name.endswith(".go")):
            text = p.read_text(errors="replace")
            targets.setdefault("mage", [])
            targets["mage"] += re.findall(r"^func ([A-Z]\w*)\(", text, re.M)

    top = sorted(dirs.values(), key=lambda d: -d["lines"])
    for d in top:
        d["languages"] = dict(sorted(d["languages"].items(), key=lambda kv: -kv[1])[:4])
    return {
        "root": str(root), "git": git, "files": len(files), "lines": sum(langs.values()),
        "languages": dict(sorted(langs.items(), key=lambda kv: -kv[1])),
        "dirs": top[:80], "go_packages": sorted(go_pkgs.values(), key=lambda g: g["dir"]),
        "entry_points": sorted(set(entry)), "build_targets": targets,
        "docs": sorted(docs)[:200], "docs_count": len(docs),
        "tests": {"files": tests, "by_top_dir": dict(sorted(test_dirs.items(), key=lambda kv: -kv[1])[:10])},
    }


def summary(data: Dict[str, Any], out_path: Path) -> str:
    g = data["git"]
    pin = f"{g['commit'][:10]} on {g['branch']}{' (dirty)' if g['dirty'] else ''}" if g else "not a git repo"
    langs = ", ".join(f"{k} {v}" for k, v in list(data["languages"].items())[:6])
    out = [f"survey {data['root']} — {pin}; {data['files']} files, {data['lines']} lines ({langs}).",
           f"full map: {out_path}", "largest directories (files / lines):"]
    out += [f"  {d['path']:<40} {d['files']:>5} {d['lines']:>8}" for d in data["dirs"][:30]]
    pkgs = data["go_packages"]
    if pkgs:
        out.append(f"go packages: {len(pkgs)} (showing 20 largest)")
        for p in sorted(pkgs, key=lambda x: -x["lines"])[:20]:
            out.append(f"  {p['dir']:<40} {p['lines']:>7}  {p['doc'][:70]}")
    if data["entry_points"]:
        out.append("entry points: " + ", ".join(data["entry_points"][:15]))
    for src, names in data["build_targets"].items():
        out.append(f"build targets ({src}): " + ", ".join(names[:25]))
    out.append(f"docs: {data['docs_count']} Markdown files" + (": " + ", ".join(data["docs"][:8]) if data["docs"] else ""))
    out.append(f"tests: {data['tests']['files']} files " + json.dumps(data["tests"]["by_top_dir"]))
    return "\n".join(out[:79])
