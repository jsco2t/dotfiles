#!/usr/bin/env python3
"""
Fix wiki-links after file renames.

Reads a JSON rename mapping and updates all wiki-links across the vault
that reference renamed files. The scan root is the current working
directory, so run this from the vault root.

Usage:
    # From a mapping file:
    python3 fix_wiki_links.py --mapping-file renames.json

    # From stdin (e.g. piped from a rename-producing script):
    ... | python3 fix_wiki_links.py

    # Dry run:
    python3 fix_wiki_links.py --mapping-file renames.json --dry-run

Mapping format (JSON array of basename pairs; the .md suffix is optional):
    [{"old": "old-note.md", "new": "new-note.md"}, ...]

Every wikilink form is rewritten by basename stem: [[stem]],
[[stem|alias]], [[stem#heading]], [[stem#heading|alias]], ![[stem]]
embeds, and path-based links whose basename matches.
"""

import argparse
import json
import os
import re
import sys

import kb_common


# ── Wiki-link regex ─────────────────────────────────────────────────────────

# Matches [[target]], [[target|alias]], [[target#heading]], [[target#heading|alias]]
# Also matches ![[embed]] variants (image/file embeds)
WIKI_LINK_RE = re.compile(
    r'(?P<embed>!)?\[\['
    r'(?P<target>[^\]|#]+?)'
    r'(?P<heading>#[^\]|]+?)?'
    r'(?:\|(?P<alias>[^\]]+))?'
    r'\]\]'
)


# ── Rename mapping ──────────────────────────────────────────────────────────

def load_rename_mapping(source: str | None) -> list[dict[str, str]]:
    """Load a rename mapping from a JSON file or stdin."""
    if source:
        with open(source, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        raw = sys.stdin.read().strip()
        if not raw:
            return []
        data = json.loads(raw)

    if not isinstance(data, list) or not all(
        isinstance(entry, dict)
        and isinstance(entry.get("old"), str)
        and isinstance(entry.get("new"), str)
        for entry in data
    ):
        raise ValueError(
            'mapping must be a JSON array of {"old", "new"} string pairs')
    return data


def build_lookup(mapping: list[dict[str, str]]) -> dict[str, str]:
    """
    Build a lookup table: old_name_no_ext -> new_name_no_ext.

    Handles both bare filenames and path-based names.
    """
    lookup: dict[str, str] = {}
    for entry in mapping:
        old = entry["old"]
        new = entry["new"]
        # Strip .md extension if present
        old_stem = old[:-3] if old.endswith(".md") else old
        new_stem = new[:-3] if new.endswith(".md") else new
        lookup[old_stem] = new_stem
    return lookup


# ── File discovery ──────────────────────────────────────────────────────────

def find_markdown_files(root: str) -> list[str]:
    """Find all .md files under root, respecting exclusions."""
    results: list[str] = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [
            d for d in dirs
            if d not in kb_common.EXCLUDED_DIRS and not d.startswith(".")
        ]
        for fname in sorted(files):
            if fname.endswith(".md"):
                results.append(os.path.join(dirpath, fname))
    return sorted(results)


# ── Link processing ─────────────────────────────────────────────────────────

def process_file(
    filepath: str,
    lookup: dict[str, str],
    dry_run: bool,
) -> list[dict]:
    """
    Process a single file: find wiki-links and update those referencing
    renamed files.

    Returns list of update dicts with: file, line, old_link, new_link
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return []

    updates: list[dict] = []
    new_lines: list[str] = []
    changed = False
    in_code_block = False

    for line_num, line in enumerate(content.split("\n"), start=1):
        if line.strip().startswith("```"):
            in_code_block = not in_code_block

        if in_code_block:
            new_lines.append(line)
            continue

        new_line = WIKI_LINK_RE.sub(
            lambda m: _replace_link(m, lookup, updates, filepath, line_num),
            line,
        )
        if new_line != line:
            changed = True
        new_lines.append(new_line)

    if changed and not dry_run:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines))

    return updates


def _replace_link(
    match: re.Match,
    lookup: dict[str, str],
    updates: list[dict],
    filepath: str,
    line_num: int,
) -> str:
    """Regex sub callback: replace a wiki-link if its target was renamed."""
    embed = match.group("embed") or ""
    target = match.group("target")
    heading = match.group("heading") or ""
    alias = match.group("alias")

    # Skip heading-only links like [[#SomeHeading]]
    if not target.strip():
        return match.group(0)

    # Extract the basename for lookup (handle path-based links)
    if "/" in target:
        path_prefix, basename = target.rsplit("/", 1)
        if not basename:
            # Directory link with trailing slash (e.g., [[architecture/]]) — skip
            return match.group(0)
        new_basename = lookup.get(basename)
        if new_basename:
            new_target = f"{path_prefix}/{new_basename}"
        else:
            return match.group(0)
    else:
        new_target = lookup.get(target)
        if not new_target:
            return match.group(0)

    # Build the updated link
    alias_part = f"|{alias}" if alias else ""
    new_link = f"{embed}[[{new_target}{heading}{alias_part}]]"

    updates.append({
        "file": filepath,
        "line": line_num,
        "old_link": match.group(0),
        "new_link": new_link,
    })

    return new_link


# ── Output formatting ───────────────────────────────────────────────────────

def format_human(all_updates: list[dict], files_scanned: int, dry_run: bool) -> str:
    """Format results for human-readable output."""
    if not all_updates:
        prefix = "DRY RUN — " if dry_run else ""
        return f"{prefix}No wiki-links needed updating.\nFiles scanned: {files_scanned}"

    lines: list[str] = []
    prefix = "DRY RUN — " if dry_run else ""

    # Group by file
    by_file: dict[str, list[dict]] = {}
    for u in all_updates:
        by_file.setdefault(u["file"], []).append(u)

    for filepath, updates in sorted(by_file.items()):
        lines.append(f"  {filepath}")
        for u in updates:
            lines.append(f"    L{u['line']}: {u['old_link']} → {u['new_link']}")
        lines.append("")

    summary = [
        f"{prefix}Files scanned:  {files_scanned}",
        f"Files updated:  {len(by_file)}",
        f"Links fixed:    {len(all_updates)}",
    ]

    return "\n".join(lines) + "\n".join(summary)


def format_json(all_updates: list[dict], files_scanned: int) -> str:
    """Format results as JSON with the documented output keys."""
    by_file: dict[str, list[dict]] = {}
    for u in all_updates:
        by_file.setdefault(u["file"], []).append(u)

    output = {
        "files_scanned": files_scanned,
        "files_updated": len(by_file),
        "links_fixed": len(all_updates),
        "updates": all_updates,
    }
    return json.dumps(output, indent=2)


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fix wiki-links after file renames."
    )
    parser.add_argument(
        "--mapping-file",
        help="Path to JSON rename mapping file. If omitted, reads from stdin.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview changes without writing.",
    )
    parser.add_argument(
        "--json", dest="json_output", action="store_true",
        help="Output JSON.",
    )

    args = parser.parse_args()

    # The scan root is the current working directory; run from the vault root.
    scan_root = os.getcwd()

    # Load rename mapping
    try:
        mapping = load_rename_mapping(args.mapping_file)
    except (json.JSONDecodeError, OSError, ValueError) as e:
        print(f"Error loading rename mapping: {e}", file=sys.stderr)
        return 1

    if not mapping:
        if args.json_output:
            print(json.dumps({"files_scanned": 0, "files_updated": 0,
                              "links_fixed": 0, "updates": []}))
        else:
            print("No renames to process.")
        return 0

    lookup = build_lookup(mapping)

    # Scan the vault
    all_files = find_markdown_files(scan_root)

    if not args.json_output:
        action = "Scanning" if args.dry_run else "Fixing wiki-links in"
        print(f"{action} {len(all_files)} files...\n")

    # Process files
    all_updates: list[dict] = []
    for filepath in all_files:
        rel_path = os.path.relpath(filepath, scan_root)
        updates = process_file(filepath, lookup, dry_run=args.dry_run)
        # Store relative paths for display
        for u in updates:
            u["file"] = rel_path
        all_updates.extend(updates)

    # Output
    if args.json_output:
        print(format_json(all_updates, len(all_files)))
    else:
        print(format_human(all_updates, len(all_files), dry_run=args.dry_run))

    return 0


if __name__ == "__main__":
    sys.exit(main())
