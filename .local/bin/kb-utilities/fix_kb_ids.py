#!/usr/bin/env python3
"""
Fix KB document names and titles.

This is the naming fixer of the kb-utilities toolkit. It finds markdown
documents whose filename or frontmatter title does not follow the naming
convention and fixes both:

- The filename stem becomes kb_common.normalize_filename of the
  frontmatter title: lowercase kebab-case, at most 42 characters. No ID
  prefix is required and none is minted.
- The frontmatter title becomes kb_common.normalize_title of the title.
- The document carries a valid ``id`` frontmatter field: an existing
  8-character Crockford Base32 id is kept as-is; a missing or invalid id
  is minted through kb_common.ensure_id and written as the first
  frontmatter field. Every other field, the tags, and the body are
  preserved verbatim.

Two documents that map to the same target get distinct names: the second
and later ones receive a numeric suffix (``-2``, ``-3``, ...) sized so the
stem stays within the 42-character cap. A target occupied by any existing
entry of the directory, or reserved by an earlier document of the same
run, is avoided the same way; a rename never overwrites a file.

Accepts a single .md file or a directory of markdown files, walked
recursively while skipping kb_common.EXCLUDED_DIRS and hidden directories.

Usage:
    python fix_kb_ids.py <file_or_directory>
    python fix_kb_ids.py <file_or_directory> --dry-run
    python fix_kb_ids.py <file_or_directory> --no-rename
    python fix_kb_ids.py --json <file_or_directory> | python fix_wiki_links.py

With --no-rename only the frontmatter title is fixed in place and no file
is renamed. With --json the script prints a JSON array of {"old", "new"}
basename pairs, the mapping fix_wiki_links.py consumes. Documents without
a usable title are skipped with a warning on stderr. Exit status is 1
when the path is not a markdown file or not a valid file or directory,
else 0 (including when nothing needs fixing).
"""

import argparse
import json
import os
import sys
from typing import NamedTuple

import kb_common


# ── Discovery ───────────────────────────────────────────────────────────────

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


# ── Planning ────────────────────────────────────────────────────────────────

class Fix(NamedTuple):
    """A document that needs fixing, with its fix fully decided."""

    path: str                   # current file path
    filename: str               # current basename
    old_title: str              # frontmatter title as found
    new_basename: str | None    # target basename; None when the name stays
    fields: dict[str, str]      # frontmatter fields with the fix applied
    tags: list[str]
    body: str
    minted_id: bool             # whether a new id field was minted
    reason: str                 # one-line description of what is wrong


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
    filepath: str, no_rename: bool, taken: dict[str, set[str]]
) -> tuple[Fix | None, str]:
    """Decide what to do with one document without touching it.

    Returns (fix, "") when the document needs fixing, (None, "") when it
    already conforms, and (None, reason) when it cannot be fixed. taken
    maps each directory to its occupied basenames: the current directory
    contents plus the targets planned earlier in the same run.
    """
    filename = os.path.basename(filepath)
    directory = os.path.dirname(filepath)
    if directory not in taken:
        taken[directory] = set(os.listdir(directory))

    try:
        content = read_file(filepath)
    except (OSError, UnicodeDecodeError) as error:
        return (None, f"unreadable ({type(error).__name__})")
    fields, tags, _, body = kb_common.parse_frontmatter(content)
    title = fields.get("title", "")
    if not title.strip():
        return (None, "no title in the frontmatter")
    normalized = kb_common.normalize_title(title)
    if not normalized:
        return (None, "title normalizes to an empty name")

    reasons = []
    if title != normalized:
        reasons.append("title is not normalized")
    stem = filename[:-3] if filename.endswith(".md") else filename
    # A collision-suffixed stem (same-topic-2 for "Same Topic") is the
    # stable outcome of an earlier run: it conforms and never renames,
    # otherwise the -2 and -3 forms of one title would swap every run.
    rename = (not no_rename and stem != kb_common.normalize_filename(title)
              and not kb_common.is_collision_stem(stem, title))
    if rename:
        reasons.append("filename does not match the title")
    new_fields, minted = kb_common.ensure_id(fields)
    if minted:
        reasons.append("frontmatter id is missing or invalid")
    if not reasons:
        return (None, "")

    new_fields["title"] = normalized
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
    md_files: list[str], no_rename: bool
) -> tuple[list[Fix], list[tuple[str, str]]]:
    """Plan every document of a run.

    Returns (fixes, skipped): the documents to fix, in discovery order,
    and (filename, reason) pairs for the documents that cannot be fixed.
    """
    fixes: list[Fix] = []
    skipped: list[tuple[str, str]] = []
    taken: dict[str, set[str]] = {}
    for filepath in md_files:
        fix, skip_reason = plan_file(filepath, no_rename, taken)
        if fix is not None:
            fixes.append(fix)
        elif skip_reason:
            skipped.append((os.path.basename(filepath), skip_reason))
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


def apply_fix(fix: Fix) -> tuple[str, tuple[str, str] | None]:
    """Write the fixed document, renaming it when planned.

    Returns ("renamed", (old_basename, new_basename)) after a rename,
    ("updated", None) after an in-place fix, and ("blocked",
    (old_basename, new_basename)) when the planned target exists on disk;
    a rename never overwrites a file.
    """
    new_content = kb_common.serialize_frontmatter(fix.fields, fix.tags, fix.body)
    if fix.new_basename is None:
        write_file(fix.path, new_content)
        return ("updated", None)
    new_path = os.path.join(os.path.dirname(fix.path), fix.new_basename)
    if os.path.exists(new_path):
        return ("blocked", (fix.filename, fix.new_basename))
    write_file(new_path, new_content)
    os.remove(fix.path)
    return ("renamed", (fix.filename, fix.new_basename))


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fix KB document names and titles"
    )
    parser.add_argument(
        "path",
        help="Path to a single .md file or a directory containing KB documents"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without making changes"
    )
    parser.add_argument(
        "--no-rename",
        action="store_true",
        help="Only fix the frontmatter title in place, without renaming files"
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Output the rename mapping as JSON (for piping to fix_wiki_links.py)"
    )

    args = parser.parse_args()
    quiet = args.json_output

    target_path = os.path.abspath(args.path)
    if os.path.isfile(target_path):
        if not target_path.endswith(".md"):
            print(f"Error: '{args.path}' is not a markdown file", file=sys.stderr)
            return 1
        md_files = [target_path]
        if not quiet:
            print(f"Processing: {target_path}")
    elif os.path.isdir(target_path):
        md_files = find_markdown_files(target_path)
        if not quiet:
            print(f"Scanning: {target_path}")
    else:
        print(f"Error: '{args.path}' is not a valid file or directory", file=sys.stderr)
        return 1

    if not quiet:
        if args.dry_run:
            print("(DRY RUN - no changes will be made)\n")
        else:
            print()
        print(f"Found {len(md_files)} markdown files\n")

    fixes, skipped = plan_documents(md_files, args.no_rename)
    for filename, reason in skipped:
        print(f"fix_kb_ids: skipped {filename}: {reason}", file=sys.stderr)

    if not fixes:
        if quiet:
            print("[]")
        else:
            print("All documents already follow the naming convention. Nothing to fix.")
        return 0

    if not quiet:
        print(f"Found {len(fixes)} to fix:\n")

    renames: list[dict[str, str]] = []
    fixed = 0
    blocked = 0
    for index, fix in enumerate(fixes, 1):
        if not quiet:
            print(f"[{index}/{len(fixes)}] {fix.filename}")
            print(f"  Reason: {fix.reason}")

        if args.dry_run:
            if fix.new_basename is not None:
                renames.append({"old": fix.filename, "new": fix.new_basename})
                if not quiet:
                    print(f"  Would rename: {fix.filename} -> {fix.new_basename}")
            if not quiet:
                print(f"  Would set the title to: {fix.fields['title']}")
            fixed += 1
        else:
            status, pair = apply_fix(fix)
            if status == "blocked":
                blocked += 1
                if quiet:
                    print(
                        f"fix_kb_ids: skipped {fix.filename}: "
                        f"target {pair[1]} already exists",
                        file=sys.stderr,
                    )
                else:
                    print(f"  ERROR: Target file {pair[1]} already exists. Skipping.")
            else:
                fixed += 1
                if status == "renamed":
                    renames.append({"old": pair[0], "new": pair[1]})
                if not quiet:
                    if status == "renamed":
                        print(f"  Renamed: {pair[0]} -> {pair[1]}")
                    print(f"  Set the title to: {fix.fields['title']}")
                    if fix.minted_id:
                        print(f"  Minted the id field: {fix.fields['id']}")
        if not quiet:
            print()

    noun = "file" if fixed == 1 else "files"
    skipped_note = f" Skipped {len(skipped)} that cannot be fixed." if skipped else ""
    if quiet:
        print(json.dumps(renames))
    elif args.dry_run:
        print(f"Would fix {fixed} {noun}.{skipped_note}")
    else:
        print(f"Fixed {fixed} {noun}.{skipped_note}")
    if blocked and not quiet:
        print(f"{blocked} renames were skipped because their target already exists.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
