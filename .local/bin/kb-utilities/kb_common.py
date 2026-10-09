#!/usr/bin/env python3
"""Shared core for the kb-utilities toolkit: naming rules and frontmatter.

Naming rules
------------

A knowledge-base document is named after its title. ``normalize_title``
lowercases the title, drops apostrophes entirely, turns every other
non-alphanumeric character into a space, and collapses and trims whitespace.
``normalize_filename`` turns the normalized title into a kebab-case filename
stem, truncated to at most MAX_FILENAME_LEN characters at a dash boundary,
with an optional collision suffix. ``title_from_filename`` maps a stem back
to its title form, so a stem and its title differ only by spaces versus
dashes and by the length cap.

Frontmatter
-----------

``parse_frontmatter`` and ``serialize_frontmatter`` are ported from the
notebook ``.tools`` scripts and keep the best of both parsers found there
(doc_fix.py:121-194 and fix_kb_ids.py:138-168): tags are read from inline
arrays, YAML lists and single-line values; the closing ``---`` is tolerated
with trailing spaces and at end of file; and a value may itself contain
colons, since the key ends at the first colon. Unlike the ported regex, the
frontmatter block ends at the closing marker's line terminator, so any blank
line after it belongs to the body and parse -> serialize preserves the body
verbatim. Documents may be id-free: a missing id is simply absent from the
parsed fields.

Only the Python standard library is used.
"""

import re


# ── Naming rules ────────────────────────────────────────────────────────────

# A filename stem never exceeds this many characters.
MAX_FILENAME_LEN = 42

# Apostrophes are dropped from titles rather than replaced by a space; the
# second form is the typographic right single quotation mark.
_APOSTROPHES = "'’"


def normalize_title(title: str) -> str:
    """Normalize a document title for naming.

    Lowercase; apostrophes dropped entirely (no space inserted); every other
    non-alphanumeric character becomes a space; whitespace collapsed and
    trimmed. A title without alphanumerics normalizes to the empty string.
    """
    for apostrophe in _APOSTROPHES:
        title = title.replace(apostrophe, "")
    replaced = "".join(ch if ch.isalnum() else " " for ch in title.lower())
    return " ".join(replaced.split())


def _truncate_at_dash(text: str, limit: int) -> str:
    """Truncate text to at most limit characters, cutting at a dash boundary.

    The cut falls at the last dash within the allowed length; a form with no
    dash there is cut hard at the limit.
    """
    if len(text) <= limit:
        return text
    cut = text[:limit]
    dash = cut.rfind("-")
    if dash < 0:
        return cut
    return cut[:dash]


def normalize_filename(title: str, suffix: str | None = None) -> str:
    """Derive a kebab-case filename stem from a document title.

    The stem is the normalized title with spaces replaced by dashes,
    truncated to at most MAX_FILENAME_LEN characters at a dash boundary and
    never ending with a dash. When suffix is given (a collision suffix such
    as "2") it is appended as -<suffix>, and the stem part is truncated to
    leave room for it so the whole stem stays within MAX_FILENAME_LEN.
    """
    dashed = normalize_title(title).replace(" ", "-")
    if suffix is None:
        return _truncate_at_dash(dashed, MAX_FILENAME_LEN)
    room = MAX_FILENAME_LEN - len(suffix) - 1
    if room < 1:
        room = 1
    return f"{_truncate_at_dash(dashed, room)}-{suffix}"


def title_from_filename(stem: str) -> str:
    """Map a filename stem back to its title form: dashes become spaces."""
    return stem.replace("-", " ")


# ── Frontmatter ─────────────────────────────────────────────────────────────

# Tag forms, ported from notebook .tools/doc_fix.py:160-185: inline array,
# YAML list key, and single-line value.
_TAG_INLINE_RE = re.compile(r"^tags:\s*\[([^\]]*)\]\s*$")
_TAG_LIST_KEY_RE = re.compile(r"^tags:\s*$")
_TAG_LIST_ITEM_RE = re.compile(r"^\s+-\s+(.+)$")
_TAG_SINGLE_RE = re.compile(r"^tags:\s+(\S.*)$")

# Directory names excluded from every walk-based tool. Ported verbatim from
# notebook .tools/doc_fix.py:25-28 and .tools/fix_wiki_links.py:31-34.
EXCLUDED_DIRS = {
    "templates", "TaskNotes", "boards", ".obsidian", ".git",
    "scratch", "xchive", "resources",
}


def _clean_value(raw: str) -> str:
    """Strip surrounding whitespace and one layer of quotes from a value."""
    return raw.strip().strip("'\"")


def parse_frontmatter(content: str) -> tuple[dict[str, str], list[str], str, str]:
    """Parse YAML frontmatter from markdown content.

    Returns (fields, tags, fm_raw, body): a dict of simple key -> value
    strings (quote-stripped, excluding tags), the list of tag strings, the
    raw frontmatter text including its --- markers, and the body after the
    frontmatter. Content that does not open with a --- marker parses as no
    frontmatter: empty fields, empty tags, empty fm_raw, and the whole
    content as body.
    """
    if not content.startswith("---"):
        return ({}, [], "", content)

    lines = content.split("\n")
    if lines[0].strip() != "---":
        return ({}, [], "", content)

    # Closing marker: a --- line, tolerated with trailing spaces and at end
    # of file without a trailing newline.
    close_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close_idx = i
            break
    if close_idx is None:
        return ({}, [], "", content)

    # The block ends at the closing marker's line terminator; everything
    # after it, including any blank line, is body.
    fm_raw = "\n".join(lines[: close_idx + 1]) + "\n"
    body = "\n".join(lines[close_idx + 1 :])

    fields: dict[str, str] = {}
    tags: list[str] = []

    inner = lines[1:close_idx]
    i = 0
    while i < len(inner):
        line = inner[i]

        # Inline array: tags: [foo, bar] or tags: []
        tag_inline = _TAG_INLINE_RE.match(line)
        if tag_inline:
            raw_tags = tag_inline.group(1).strip()
            if raw_tags:
                tags = [t.strip().strip("'\"") for t in raw_tags.split(",") if t.strip()]
            i += 1
            continue

        # YAML list: tags: followed by indented "- item" lines
        if _TAG_LIST_KEY_RE.match(line):
            i += 1
            while i < len(inner):
                item = _TAG_LIST_ITEM_RE.match(inner[i])
                if not item:
                    break
                tags.append(_clean_value(item.group(1)))
                i += 1
            continue

        # Single-line value: tags: foo
        tag_single = _TAG_SINGLE_RE.match(line)
        if tag_single:
            value = _clean_value(tag_single.group(1))
            if value:
                tags = [value]
            i += 1
            continue

        # Regular field: the key ends at the first colon; indented lines are
        # not fields.
        if ":" in line and not line.startswith((" ", "\t")):
            key, _, value = line.partition(":")
            fields[key.strip()] = _clean_value(value)

        i += 1

    return (fields, tags, fm_raw, body)


def serialize_frontmatter(
    fields: dict[str, str], tags: list[str], body: str = ""
) -> str:
    """Serialize a canonical document: frontmatter block, tags block, body.

    One ``key: value`` line per field in insertion order, a canonical tags
    block (``tags:`` with indented ``- item`` lines, or ``tags: []`` when
    tags is empty), the closing marker, then the body verbatim. Field and
    tag values are written unquoted.
    """
    lines = ["---"]
    for key, value in fields.items():
        lines.append(f"{key}: {value}")
    if tags:
        lines.append("tags:")
        lines.extend(f"  - {tag}" for tag in tags)
    else:
        lines.append("tags: []")
    lines.append("---")
    return "\n".join(lines) + "\n" + body
