"""Markdown → Atlassian Document Format (ADF), deterministic and stdlib-only, so a reviewed
Markdown draft posts to Jira as rich text. The subset is what tickets need: headings,
paragraphs, bullet and ordered lists (nested by indentation), fenced code, rules, and inline
code, bold, italic, and links. Anything else stays as its plain text."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

Node = Dict[str, Any]

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)\s*([\w+-]*)\s*$")
_RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_ITEM = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
# Inline tokens, tried left to right: code first, so markup inside backticks stays literal.
_INLINE = re.compile(r"`([^`]+)`|\*\*(.+?)\*\*|__(.+?)__|\[([^\]]+)\]\(([^)\s]+)\)|(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])"
                     r"|(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])")
# Markdown that should never reach Jira as literal text once rendered.
_MARKUP = re.compile(r"^#{1,6}\s|\*\*|__|`|\[[^\]]+\]\([^)]+\)")


def _text(text: str, marks: Optional[List[Node]] = None) -> Node:
    node: Node = {"type": "text", "text": text}
    if marks:
        node["marks"] = marks
    return node


def inline(text: str, marks: Optional[List[Node]] = None) -> List[Node]:
    out: List[Node] = []
    pos = 0
    base = list(marks or [])
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            out.append(_text(text[pos:m.start()], base))
        code, strong, strong2, label, href, em, em2 = m.groups()
        if code is not None:
            out.append(_text(code, base + [{"type": "code"}]))
        elif strong is not None or strong2 is not None:
            out += inline(strong if strong is not None else strong2, base + [{"type": "strong"}])
        elif label is not None:
            out += inline(label, base + [{"type": "link", "attrs": {"href": href}}])
        else:
            out += inline(em if em is not None else em2, base + [{"type": "em"}])
        pos = m.end()
    if pos < len(text):
        out.append(_text(text[pos:], base))
    return [n for n in out if n["text"]]


def _paragraph(lines: List[str]) -> Node:
    return {"type": "paragraph", "content": inline(" ".join(ln.strip() for ln in lines))}


def _list(lines: List[str], start: int) -> Tuple[Node, int]:
    """Parse a list whose first item is lines[start]; return (node, index after it). Items
    indented deeper than the list's own items nest under the item before them."""
    first = _ITEM.match(lines[start])
    assert first is not None
    indent = len(first.group(1))
    ordered = first.group(2)[0].isdigit()
    node: Node = {"type": "orderedList" if ordered else "bulletList", "content": []}
    i = start
    while i < len(lines):
        m = _ITEM.match(lines[i])
        if not m or len(m.group(1)) != indent or m.group(2)[0].isdigit() != ordered:
            if m and len(m.group(1)) > indent and node["content"]:
                child, i = _list(lines, i)
                node["content"][-1]["content"].append(child)
                continue
            if lines[i].strip() and not m and lines[i].startswith(" " * (indent + 2)) and node["content"]:
                para = node["content"][-1]["content"][0]  # a wrapped continuation line
                para["content"] += [_text(" ")] + inline(lines[i].strip())
                i += 1
                continue
            break
        node["content"].append({"type": "listItem", "content": [_paragraph([m.group(3)])]})
        i += 1
    return node, i


def to_adf(markdown: str) -> Node:
    lines = markdown.replace("\r\n", "\n").split("\n")
    content: List[Node] = []
    para: List[str] = []

    def flush() -> None:
        if para:
            content.append(_paragraph(para))
            para.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        fence = _FENCE.match(line)
        if fence:
            flush()
            body: List[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(fence.group(1)):
                body.append(lines[i])
                i += 1
            block: Node = {"type": "codeBlock", "content": [_text("\n".join(body))] if body else []}
            if fence.group(2):
                block["attrs"] = {"language": fence.group(2)}
            content.append(block)
            i += 1
            continue
        if not line.strip():
            flush()
            i += 1
            continue
        heading = _HEADING.match(line)
        if heading:
            flush()
            content.append({"type": "heading", "attrs": {"level": len(heading.group(1))},
                            "content": inline(heading.group(2))})
            i += 1
            continue
        if _RULE.match(line) and not para:
            content.append({"type": "rule"})
            i += 1
            continue
        if _ITEM.match(line):
            flush()
            node, i = _list(lines, i)
            content.append(node)
            continue
        para.append(line)
        i += 1
    flush()
    return {"type": "doc", "version": 1, "content": content}


def _texts(node: Any) -> List[str]:
    if isinstance(node, dict):
        if node.get("type") == "text":
            return [str(node.get("text", ""))]
        return [t for child in node.get("content", []) for t in _texts(child)]
    if isinstance(node, list):
        return [t for child in node for t in _texts(child)]
    return []


def text_of(node: Any) -> str:
    """The document's words, whitespace-normalized: what a reader sees, for comparing a stored
    document with the one sent (Jira adds attributes, never words)."""
    return " ".join(" ".join(_texts(node)).split())


def literal_markup(node: Any) -> List[str]:
    """Text nodes that still carry Markdown markup: a sign the body was posted as plain text."""
    out = []
    for n in _walk(node):
        if n.get("type") == "text" and not any(m.get("type") == "code" for m in n.get("marks", [])) \
                and _MARKUP.search(str(n.get("text", ""))):
            out.append(str(n["text"]))
    return out


def _walk(node: Any):
    if isinstance(node, dict):
        yield node
        for child in node.get("content", []):
            yield from _walk(child)
    elif isinstance(node, list):
        for child in node:
            yield from _walk(child)
