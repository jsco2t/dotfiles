#!/usr/bin/env python3
"""
Migrate old-convention KB documents to the new naming convention.

This is the one-shot migration fixer of the kb-utilities toolkit. An
old-convention document is a Markdown file that carries any of the old
``<8-char ID>_<snake_case>.md`` habits:

- an 8-char lowercase ID filename prefix (``^[0-9a-z]{8}_``),
- a filename stem that is not ``kb_common.normalize_filename`` of its
  frontmatter title,
- a title that is not ``kb_common.normalize_title`` of itself, or
- a missing or invalid ``id`` frontmatter field.

The fix renames the file to ``kb_common.normalize_filename`` of its
title, rewrites the title to ``kb_common.normalize_title`` of itself,
and mints a new ``id`` (kb_common.generate_ulid_short, the recovered
notebook generator) when the field is missing or invalid; an existing
valid id is kept as-is. Every other field, the tags, and
the body are preserved verbatim: body wikilinks are NOT rewritten here,
that is fix_wiki_links.py's job, driven by the {old,new} mapping this
script optionally writes with --mapping-out.

The default run is a dry run: it prints the plan as a table and writes
nothing, including no --mapping-out file. Renames happen only with
--apply. Documents that already conform are reported as skipped and
never rewritten; a document without a usable title (no frontmatter) is
left unchanged. Collision targets get numeric suffixes (``-2``, ...)
through kb_common.normalize_filename, both between two planned renames
and against a file that already exists; a rename never overwrites. A
file already sitting at a collision-suffixed name (same-topic-2.md for
"Same Topic") conforms and is left in place, so repeated --apply runs
are idempotent.

Usage:
    python migrate_kb.py <directory>                # dry run (default)
    python migrate_kb.py <directory> --apply
    python migrate_kb.py <directory> --apply --mapping-out renames.json

The positional PATH must be a directory; it is scanned recursively while
skipping kb_common.EXCLUDED_DIRS and hidden directories. Exit status is
1 when the path does not exist or is not a valid directory, else 0
(including when nothing needs fixing).

Standard library only; it reuses kb_common.
"""

import argparse
import json
import os
import re
import sys
from typing import NamedTuple

import kb_common


# ── Detection ───────────────────────────────────────────────────────────────

# The old-convention ID filename prefix: 8 lowercase alphanumeric chars
# followed by an underscore.
_ID_PREFIX_RE = re.compile(r"^[0-9a-z]{8}_")


class Fix(NamedTuple):
    """An old-convention document, with its fix fully decided."""

    path: str                   # current file path
    filename: str               # current basename
    old_title: str              # frontmatter title as found
    new_basename: str | None    # target basename; None when the name stays
    fields: dict[str, str]      # frontmatter fields with the fix applied
    tags: list[str]
    body: str
    minted_id: bool             # whether a new id field was minted
    reason: str                 # one-line description of what is wrong


def find_markdown_files(directory: str) -> list[str]:
    """Find all .md files under directory, recursively.

    Directories named in kb_common.EXCLUDED_DIRS and hidden directories
    are never entered.
    """
    files = []
    for root, dirs, names in os.walk(directory):
        dirs[:] = sorted(
            d for d in dirs
            if d not in kb_common.EXCLUDED_DIRS and not d.startswith(".")
        )
        for name in sorted(names):
            if name.endswith(".md"):
                files.append(os.path.join(root, name))
    return files


def take_target(title: str, used: set[str]) -> str:
    """Reserve and return an unoccupied .md basename for a title.

    The plain normalized name is preferred; when it is taken, numeric
    suffixes (-2, -3, ...) are tried through kb_common.normalize_filename,
    which keeps each suffixed stem within MAX_FILENAME_LEN. The reserved
    name is added to used so later documents of the same run avoid it.
    """
    candidate = kb_common.normalize_filename(title)
    if f"{candidate}.md" not in used:
        used.add(f"{candidate}.md")
        return f"{candidate}.md"
    n = 2
    while True:
        candidate = kb_common.normalize_filename(title, suffix=str(n))
        if f"{candidate}.md" not in used:
            used.add(f"{candidate}.md")
            return f"{candidate}.md"
        n += 1


def plan_file(
    filepath: str, taken: dict[str, set[str]]
) -> tuple[Fix | None, str]:
    """Decide what to do with one document without touching it.

    Returns (fix, "") when the document is old-convention, and
    (None, note) when nothing is planned: "already conforms" for a
    conforming document, or the reason it cannot be fixed. taken maps
    each directory to its occupied basenames: the current directory
    contents plus the targets planned earlier in the same run.
    """
    filename = os.path.basename(filepath)
    directory = os.path.dirname(filepath)
    if directory not in taken:
        taken[directory] = set(os.listdir(directory))

    fields, tags, _, body = kb_common.parse_frontmatter(read_file(filepath))
    title = fields.get("title", "")
    if not title.strip():
        return (None, "no title in the frontmatter")
    normalized = kb_common.normalize_title(title)
    if not normalized:
        return (None, "title normalizes to an empty name")

    reasons = []
    stem = filename[:-3] if filename.endswith(".md") else filename
    plain_stem = kb_common.normalize_filename(title)
    rename_needed = (stem != plain_stem
                     and not kb_common.is_collision_stem(stem, title))
    if _ID_PREFIX_RE.match(stem):
        reasons.append("filename carries an ID prefix")
    elif rename_needed:
        reasons.append("filename does not match the title")
    if title != normalized:
        reasons.append("title is not normalized")
    new_fields, minted = kb_common.ensure_id(fields)
    if minted:
        reasons.append("frontmatter id is missing or invalid")
    if not reasons:
        return (None, "already conforms")

    new_fields["title"] = normalized
    rename = rename_needed
    new_basename = take_target(title, taken[directory]) if rename else None

    fix = Fix(
        path=filepath,
        filename=filename,
        old_title=title,
        new_basename=new_basename,
        fields=new_fields,
        tags=tags,
        body=body,
        minted_id=minted,
        reason=" and ".join(reasons),
    )
    return (fix, "")


def plan_documents(
    md_files: list[str],
) -> tuple[list[Fix], list[tuple[str, str]]]:
    """Plan every document of a run.

    Returns (fixes, skipped): the old-convention documents to fix, in
    discovery order, and (filename, note) pairs for every other
    document — conforming ones ("already conforms") and ones that
    cannot be fixed.
    """
    fixes: list[Fix] = []
    skipped: list[tuple[str, str]] = []
    taken: dict[str, set[str]] = {}
    for filepath in md_files:
        fix, note = plan_file(filepath, taken)
        if fix is not None:
            fixes.append(fix)
        else:
            skipped.append((os.path.basename(filepath), note))
    return (fixes, skipped)


# ── Applying ────────────────────────────────────────────────────────────────

def read_file(filepath: str) -> str:
    """Read file contents."""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def write_file(filepath: str, content: str) -> None:
    """Write content to file."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def apply_fix(fix: Fix) -> str:
    """Write the fixed document, renaming it when planned.

    Returns "renamed" after a rename, "updated" after an in-place fix,
    and "blocked" when the planned target exists on disk; a rename never
    overwrites a file.
    """
    new_content = kb_common.serialize_frontmatter(fix.fields, fix.tags, fix.body)
    if fix.new_basename is None:
        write_file(fix.path, new_content)
        return "updated"
    new_path = os.path.join(os.path.dirname(fix.path), fix.new_basename)
    if os.path.exists(new_path):
        return "blocked"
    write_file(new_path, new_content)
    os.remove(fix.path)
    return "renamed"


# ── Output ──────────────────────────────────────────────────────────────────

def print_plan(fixes: list[Fix], skipped: list[tuple[str, str]]) -> None:
    """Print the plan as a table: each planned fix and each skipped file."""
    width = max(
        [len(f.filename) for f in fixes]
        + [len(name) for name, _ in skipped]
        + [len("old")],
    )
    print(f"{'old':<{width}}  →  new")
    for fix in fixes:
        target = fix.new_basename or "(same, fixed in place)"
        print(f"{fix.filename:<{width}}  →  {target}")
    for name, note in skipped:
        print(f"{name:<{width}}  →  skip ({note})")


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate old-convention KB documents to the new naming"
    )
    parser.add_argument(
        "path",
        help="Path to a directory containing KB documents",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Apply the plan; the default run is a dry run",
    )
    parser.add_argument(
        "--mapping-out", dest="mapping_out",
        help="Write the {old,new} rename mapping as JSON to this file "
             "(only with --apply; consumed by fix_wiki_links.py)",
    )

    args = parser.parse_args()

    target_path = os.path.abspath(args.path)
    if not os.path.isdir(target_path):
        print(f"Error: '{args.path}' is not a valid directory", file=sys.stderr)
        return 1

    md_files = find_markdown_files(target_path)
    print(f"Scanning: {target_path}")
    if not args.apply:
        print("(DRY RUN - no changes will be made)")
    print(f"Found {len(md_files)} markdown files\n")

    fixes, skipped = plan_documents(md_files)
    for name, note in skipped:
        if note != "already conforms":
            print(f"migrate_kb: skipped {name}: {note}", file=sys.stderr)

    print_plan(fixes, skipped)
    if not fixes:
        print("\nAll documents already follow the convention. Nothing to fix.")
        return 0

    renames: list[dict[str, str]] = []
    if not args.apply:
        if args.mapping_out:
            print("\n--mapping-out needs --apply; no mapping file written.")
        print(f"\nWould fix {len(fixes)} "
              f"{'file' if len(fixes) == 1 else 'files'}.")
        return 0

    print()
    blocked = 0
    for fix in fixes:
        status = apply_fix(fix)
        if status == "blocked":
            blocked += 1
            print(f"  ERROR: target {fix.new_basename} already exists; "
                  f"skipped {fix.filename}")
            continue
        if status == "renamed":
            renames.append({"old": fix.filename, "new": fix.new_basename})
            print(f"  Renamed: {fix.filename} -> {fix.new_basename}")
        else:
            print(f"  Fixed in place: {fix.filename}")
        if fix.old_title != fix.fields["title"]:
            print(f"  Set the title to: {fix.fields['title']}")
        if fix.minted_id:
            print(f"  Minted the id field: {fix.fields['id']}")

    if args.mapping_out:
        with open(args.mapping_out, "w", encoding="utf-8") as f:
            json.dump(renames, f, indent=2)
            f.write("\n")
        print(f"\nWrote the rename mapping to {args.mapping_out}")

    noun = "file" if len(fixes) - blocked == 1 else "files"
    print(f"Fixed {len(fixes) - blocked} {noun}.")
    if blocked:
        print(f"{blocked} renames were skipped because their target "
              f"already exists.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
