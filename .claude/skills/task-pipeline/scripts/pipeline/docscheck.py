"""Mechanical document checks: relative links resolve, `path:line` citations point at real
lines, each citation's sentence names something that appears near the cited line, and every
article is reachable from the index."""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

LINK_RE = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
SPAN_RE = re.compile(r"`([^`\n]+)`")
CITE_RE = re.compile(r"^(?:[a-z0-9_-]+:)?((?:[\w.@+-]+/)*[\w.@+-]+):(\d+(?:-\d+)?(?:,\s*\d+(?:-\d+)?)*)$")
SOURCE_EXT = {"go", "py", "rs", "ts", "tsx", "js", "jsx", "mjs", "java", "kt", "c", "h", "cc", "cpp", "hpp", "cs",
              "rb", "php", "swift", "lua", "pl", "sh", "bash", "zsh", "yaml", "yml", "json", "toml", "ini", "cfg",
              "conf", "md", "mod", "sum", "proto", "sql", "tf", "hcl", "mk", "service", "txt", "html", "css",
              "scss", "vue", "svelte", "xml", "gradle", "lock", "tpl", "tmpl", "j2", "cue", "rego", "nix", "bzl"}
SOURCE_NAMES = {"Makefile", "Dockerfile", "Containerfile", "Justfile", "Taskfile", "Vagrantfile", "Jenkinsfile",
                "Gemfile", "Rakefile", "BUILD", "WORKSPACE", "magefile"}


def parse_cites(span: str) -> List[Tuple[str, int, int]]:
    """[(path, start, end)] when an inline-code span is a `path:line[-end][,line[-end]...]` citation."""
    m = CITE_RE.match(span.strip())
    if not m:
        return []
    path = m.group(1)
    name = path.rsplit("/", 1)[-1]
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    if "/" not in path and ext not in SOURCE_EXT and name not in SOURCE_NAMES:
        return []
    if "/" in path and not ext and name not in SOURCE_NAMES and not name[:1].isupper():
        return []
    out = []
    for part in m.group(2).split(","):
        lo, _, hi = part.strip().partition("-")
        out.append((path, int(lo), int(hi or lo)))
    return out


def parse_cite(span: str) -> Optional[Tuple[str, int, int]]:
    cites = parse_cites(span)
    return cites[0] if cites else None
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z`*\[(])")
WINDOW = 10  # lines either side of a citation in which a name its sentence mentions may appear


@dataclass
class Citation:
    doc: Path
    line: int
    path: str
    start: int
    end: int
    sentence: str
    source: Optional[Path] = None


def md_files(paths: Iterable[Path]) -> List[Path]:
    out: List[Path] = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            out += sorted(x for x in p.rglob("*.md") if not any(part.startswith(".") for part in x.parts))
        elif p.suffix == ".md" and p.exists():
            out.append(p)
    return sorted({x.resolve() for x in out})


def prose_lines(text: str) -> List[str]:
    """The document's lines with fenced code blocks blanked (line numbers preserved)."""
    out, fenced = [], False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            fenced = not fenced
            out.append("")
            continue
        out.append("" if fenced else line)
    return out


def _paragraph_sentences(lines: List[str]) -> List[Tuple[int, str]]:
    """(first line number, sentence) for every sentence, joining wrapped paragraph lines."""
    out: List[Tuple[int, str]] = []
    buf: List[Tuple[int, str]] = []

    def flush() -> None:
        if not buf:
            return
        text = " ".join(t.strip() for _, t in buf)
        offsets = []
        pos = 0
        for n, t in buf:
            offsets.append((pos, n))
            pos += len(t.strip()) + 1
        start = 0
        for sent in SENTENCE_SPLIT.split(text):
            idx = text.find(sent, start)
            line_no = max((n for off, n in offsets if off <= idx), default=buf[0][0])
            out.append((line_no, sent))
            start = idx + len(sent)
        buf.clear()

    for i, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith(("#", "|", "- ", "* ", "> ")) or re.match(r"\s*\d+\.\s", line):
            flush()
            if line.strip():
                buf.append((i, re.sub(r"^\s*(#+|[-*>]|\d+\.)\s*", "", line)))
                flush()
            continue
        buf.append((i, line))
    flush()
    return out


CONTINUATION_RE = re.compile(r"^:(\d+)(?:-(\d+))?$")


def citations(doc: Path, lines: List[str]) -> List[Citation]:
    """Every `path:line[-end]` citation, plus `:line` shorthand continuing the sentence's last path."""
    out = []
    for line_no, sentence in _paragraph_sentences(lines):
        last: Optional[str] = None
        for span in SPAN_RE.findall(sentence):
            cites = parse_cites(span)
            if cites:
                last = cites[0][0]
                out += [Citation(doc, line_no, p, s, e, sentence) for p, s, e in cites]
                continue
            cont = CONTINUATION_RE.match(span.strip())
            if cont and last:
                start = int(cont.group(1))
                out.append(Citation(doc, line_no, last, start, int(cont.group(2) or start), sentence))
    return out


def _identifiers(sentence: str) -> Set[str]:
    """Single code tokens the sentence names (lower-cased): what a supporting line should mention.
    Multi-word spans (commands, prose) and paths are skipped — too loose to match reliably."""
    names: Set[str] = set()
    for span in SPAN_RE.findall(sentence):
        span = span.strip().strip("'\"")
        if " " in span or parse_cite(span) or CONTINUATION_RE.match(span):
            continue
        if "/" in span:  # a qualified name such as internal/version.StratumVersion; a bare path names nothing
            span = span.rstrip("/").rsplit("/", 1)[-1]
            if "." not in span or span.rsplit(".", 1)[-1].lower() in SOURCE_EXT:
                continue
        token = span.lstrip("-").rstrip("()")
        for sep in ("::", "->", "."):
            if sep in token:
                token = token.split(sep)[-1]
        token = token.split("=")[0].rstrip("()[]{}:,")
        if len(token) > 2 and not token.isdigit():
            names.add(token.lower())
    return names


_basenames: Dict[Path, Dict[str, List[Path]]] = {}


def resolve(path: str, repos: Dict[str, Path]) -> Tuple[Optional[Path], int]:
    """(the cited file, how many files matched): repo-relative, or a bare file name unique in a repo."""
    for root in repos.values():
        candidate = (root / path)
        if candidate.is_file():
            return candidate, 1
    if "/" in path:
        return None, 0
    most = 0
    for root in repos.values():
        if root not in _basenames:
            index: Dict[str, List[Path]] = {}
            for p in root.rglob("*"):
                if p.is_file() and ".git" not in p.parts and "node_modules" not in p.parts:
                    index.setdefault(p.name, []).append(p)
            _basenames[root] = index
        hits = _basenames[root].get(path, [])
        if len(hits) == 1:
            return hits[0], 1
        most = max(most, len(hits))
    return None, most


DEF_RE = re.compile(r"^\s*(func|def|fn|pub fn|function|class|type|struct|impl|interface|const|var)\b|^\s*[\w.-]+:\s*$")


def supported(c: Citation, src_lines: List[str]) -> Tuple[bool, Set[str]]:
    """Whether a name the sentence mentions appears near the cited lines, or on the definition
    that encloses them (a citation into a function's body supports a sentence about the function)."""
    names = _identifiers(c.sentence)
    if not names:
        return True, names
    lo = max(0, c.start - 1 - WINDOW)
    window = src_lines[lo:c.end + WINDOW]
    for i in range(c.start - 1, max(-1, c.start - 400), -1):
        if DEF_RE.match(src_lines[i]):
            window = window + [src_lines[i]]
            break
    text = "\n".join(window).lower()
    return any(name in text for name in names), names


def doubtful(cites: List[Tuple[Citation, List[str]]]) -> List[Tuple[Citation, Set[str]]]:
    """Citations the support heuristic doubts. A sentence with several citations is judged as a
    whole: the names it mentions may sit at any one of them."""
    by_sentence: Dict[Tuple[Path, int, str], List[Tuple[Citation, bool, Set[str]]]] = {}
    for c, src_lines in cites:
        ok, names = supported(c, src_lines)
        by_sentence.setdefault((c.doc, c.line, c.sentence), []).append((c, ok, names))
    out = []
    for group in by_sentence.values():
        if not any(ok for _, ok, _ in group):
            out += [(c, names) for c, ok, names in group]
    return out


def check(paths: Sequence[Path], repos: Dict[str, Path], root: Optional[Path] = None
          ) -> Tuple[List[str], List[str], Dict[str, int]]:
    """(errors, warnings, stats). Errors are certain (broken link, missing file, line past the end,
    ambiguous file name, unreachable article); warnings are the support heuristic."""
    errors: List[str] = []
    warnings: List[str] = []
    stats = {"files": 0, "links": 0, "citations": 0}
    docs = md_files(paths)
    graph: Dict[Path, Set[Path]] = {}
    for doc in docs:
        stats["files"] += 1
        lines = prose_lines(doc.read_text(errors="replace"))
        graph[doc] = set()
        for n, line in enumerate(lines, 1):
            for target in LINK_RE.findall(line):
                if SCHEME_RE.match(target) or target.startswith("#") or target.startswith("/"):
                    continue
                stats["links"] += 1
                rel = target.split("#", 1)[0].split("?", 1)[0]
                dest = (doc.parent / rel).resolve()
                if not dest.exists():
                    errors.append(f"{doc}:{n}: broken link {target}")
                elif dest.suffix == ".md":
                    graph[doc].add(dest)
        if not repos:
            continue
        valid: List[Tuple[Citation, List[str]]] = []
        for c in citations(doc, lines):
            stats["citations"] += 1
            src, hits = resolve(c.path, repos)
            where = f"{doc}:{c.line}"
            if src is None:
                errors.append(f"{where}: cites {c.path}, which matches {hits} files — cite the repo-relative path"
                              if hits > 1 else f"{where}: cites {c.path}, which is in no source repo ({', '.join(repos)})")
                continue
            src_lines = src.read_text(errors="replace").splitlines()
            if c.start < 1 or c.end > len(src_lines) or c.end < c.start:
                errors.append(f"{where}: `{c.path}:{c.start}` is past the end of {c.path} ({len(src_lines)} lines)")
                continue
            valid.append((c, src_lines))
        for c, names in doubtful(valid):
            listed = ", ".join(f"`{x}`" for x in sorted(names))
            warnings.append(f"{doc}:{c.line}: `{c.path}:{c.start}` may not support its sentence: none of {listed} "
                            f"appears near it or on its enclosing definition")
    if root is not None:
        root = root.resolve()
        seen, todo = {root}, [root]
        while todo:
            for nxt in graph.get(todo.pop(), set()):
                if nxt not in seen:
                    seen.add(nxt)
                    todo.append(nxt)
        for doc in docs:
            if doc not in seen:
                errors.append(f"{doc} is not reachable from {root.name} by links")
    return errors, warnings, stats


def sample(docs: Sequence[Path], repos: Dict[str, Path], n: int = 3, seed: str = "") -> List[str]:
    """Up to n citations with the source lines they cite, for the manager's fact check —
    citations the support heuristic doubts first, then a random draw."""
    valid: List[Tuple[Citation, List[str]]] = []
    for doc in md_files(docs):
        for c in citations(doc, prose_lines(doc.read_text(errors="replace"))):
            c.source, _ = resolve(c.path, repos)
            if c.source is None:
                continue
            src = c.source.read_text(errors="replace").splitlines()
            if 1 <= c.start <= c.end <= len(src):
                valid.append((c, src))
    flagged = [c for c, _ in doubtful(valid)]
    rest = [c for c, _ in valid if c not in flagged]
    random.Random(seed).shuffle(rest)
    out = []
    for c in (flagged + rest)[:max(n, min(len(flagged), 6))]:
        assert c.source is not None
        src = c.source.read_text(errors="replace").splitlines()
        lo, hi = max(1, c.start - 2), min(len(src), c.end + 2)
        flag = "  [may not support its sentence — check it]" if c in flagged else ""
        out.append(f"{c.doc.name}:{c.line} — {c.sentence.strip()[:300]}{flag}")
        out += [f"    {c.path}:{i}: {src[i - 1]}" for i in range(lo, hi + 1)]
    return out
