"""A deterministic structure map of a repository — the part of planning research a script
does in seconds: git pin, size by directory and language, Go packages and their doc lines,
entry points, build targets, docs, and tests."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


# Where a repository pins its Go toolchain, most specific first. `go 1.x` in go.mod is a minimum
# (a newer local Go satisfies it), so it is no pin; `toolchain go1.x.y` is.
_GO_TOOLCHAIN = re.compile(r"^toolchain\s+go(\d+\.\d+(?:\.\d+)?)\s*$", re.M)
_GO_VERSION_FILE = re.compile(r"^\s*v?(\d+\.\d+(?:\.\d+)?)\s*$")
_TOOL_VERSIONS = re.compile(r"^\s*(?:golang|go)\s+(\d+\.\d+(?:\.\d+)?)\s*$", re.M)
_MAKE_PIN = re.compile(r"^\s*(?:export\s+|override\s+)*(?:go_version|GO_VERSION|GOLANG_VERSION)\s*[:?]?=\s*v?"
                       r"(\d+\.\d+(?:\.\d+)?)\s*(?:#.*)?$", re.M)
_SETUP_GO = re.compile(r"go-version:\s*[\"']?(\d+\.\d+(?:\.\d+)?)[\"']?\s*$", re.M)


def _read(p: Path) -> str:
    try:
        return p.read_text(errors="replace")[:MAX_BYTES]
    except OSError:
        return ""


def toolchain_pins(root: Path) -> List[Dict[str, str]]:
    """The Go versions the repository pins, with the file that pins each: go.mod's `toolchain`
    line, .go-version, .tool-versions, a make variable (go_version / GO_VERSION) in a Makefile or
    *.mk at the top or one directory down, and a literal setup-go version in CI workflows."""
    pins: List[Tuple[str, str]] = []
    pins += [(v, "go.mod") for v in _GO_TOOLCHAIN.findall(_read(root / "go.mod"))]
    m = _GO_VERSION_FILE.match(_read(root / ".go-version").strip() or "-")
    if m:
        pins.append((m.group(1), ".go-version"))
    pins += [(v, ".tool-versions") for v in _TOOL_VERSIONS.findall(_read(root / ".tool-versions"))]
    makefiles = sorted({*root.glob("Makefile"), *root.glob("GNUmakefile"), *root.glob("*.mk"), *root.glob("*/*.mk")})
    for mk in makefiles:
        pins += [(v, mk.relative_to(root).as_posix()) for v in _MAKE_PIN.findall(_read(mk))]
    for wf in sorted((root / ".github" / "workflows").glob("*.y*ml")):
        pins += [(v, wf.relative_to(root).as_posix()) for v in _SETUP_GO.findall(_read(wf))]
    seen, out = set(), []
    for version, source in pins:
        if (version, source) not in seen:
            seen.add((version, source))
            out.append({"tool": "go", "version": version, "source": source})
    return out


def _local_go() -> Optional[str]:
    """The Go on PATH itself (GOTOOLCHAIN=local, outside any module, so nothing switches it)."""
    try:
        out = subprocess.run(["go", "env", "GOVERSION"], capture_output=True, text=True, timeout=30,
                             cwd=tempfile.gettempdir(), env=dict(os.environ, GOTOOLCHAIN="local"))
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"go(\d+\.\d+(?:\.\d+)?)", out.stdout)
    return m.group(1) if out.returncode == 0 and m else None


def pin_prefix(version: str) -> str:
    """Run a command under the pinned Go: GOTOOLCHAIN switches `go`; the pinned GOROOT/bin first
    on PATH makes a bare `gofmt` (a make target's) the pinned one too."""
    return (f'export GOTOOLCHAIN=go{version} PATH="$(GOTOOLCHAIN=go{version} go env GOROOT)/bin:$PATH"; ')


def toolchain_notes(root: Path, pins: Optional[List[Dict[str, str]]] = None) -> List[str]:
    """Lines for the survey when the Go on PATH is not the one the repo pins: a newer local Go
    fails gates (gofmt, vet, goldens) on files no task touched, which real runs mistook for
    regressions at the very end."""
    pins = toolchain_pins(root) if pins is None else pins
    if not pins:
        return []
    local = _local_go()
    want = pins[0]["version"]
    if local is None or local == want or local.startswith(want + "."):
        return []
    where = ", ".join(sorted({p["source"] for p in pins if p["version"] == want}))
    others = sorted({f"{p['version']} ({p['source']})" for p in pins if p["version"] != want})
    self_pinned = any("GOTOOLCHAIN" in _read(mk) for mk in (root / "Makefile", root / "GNUmakefile"))
    return [f"TOOLCHAIN: the repo pins Go {want} ({where}); PATH has go {local}"
            + (f" (other pins: {', '.join(others)})" if others else "") + ".",
            ("  The Makefile sets GOTOOLCHAIN itself, so make targets run under the pin; prefix every other check "
             "and test_cmd that calls go or gofmt directly" if self_pinned else
             "  Run every check and every task's test_cmd under the pin, or gates fail on code no task touched. "
             "Prefix each") + f" with: {pin_prefix(want)}",
            "  — and say so in conventions.md for the authors."]


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
        "toolchains": toolchain_pins(root),
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
    out = [f"survey {data['root']} — {pin}; {data['files']} files, {data['lines']} lines ({langs})."]
    out += toolchain_notes(Path(data["root"]), data.get("toolchains") or [])
    out += [f"full map: {out_path}", "largest directories (files / lines):"]
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
