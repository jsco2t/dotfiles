#!/usr/bin/env python3
"""
Fix KB document IDs and filenames.

This script finds markdown files that don't have properly formatted filenames
(must start with an 8-character Crockford Base32 ID followed by underscore)
or have mismatched frontmatter IDs, then fixes them.

Accepts a single .md file or a directory of markdown files.

Usage:
    python fix_kb_ids.py <file_or_directory>
    python fix_kb_ids.py <file_or_directory> --dry-run
    python fix_kb_ids.py <file_or_directory> --no-rename
    python fix_kb_ids.py --json <file_or_directory> | python fix_wiki_links.py
"""

import argparse
import json
import os
import random
import re
import sys
import time


# Crockford's Base32 alphabet (same as ulidshort.js)
CROCKFORD_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"

# Track generated IDs to ensure uniqueness within a session
_generated_ids: set[str] = set()


def generate_ulid_short() -> str:
    """
    Generate an 8-character ID compatible with ulidshort.js.

    Uses Date.now() equivalent (milliseconds since Unix epoch),
    encodes to Crockford's Base32, lowercases, and takes first 8 chars.

    The last 2 characters are randomized to ensure uniqueness when
    generating multiple IDs in batch (since timestamp-only IDs change slowly).
    """
    timestamp_ms = int(time.time() * 1000)

    # Encode timestamp to Crockford's Base32 (same as JS)
    encoded = encode_crockford_base32(timestamp_ms)
    base_id = encoded.lower()[:6]  # First 6 chars from timestamp

    # Keep trying with random suffixes until we get a unique ID
    max_attempts = 1000
    for _ in range(max_attempts):
        # Generate 2 random characters from Crockford alphabet
        suffix = "".join(random.choices(CROCKFORD_ALPHABET, k=2))
        ulid = base_id + suffix

        if ulid not in _generated_ids:
            _generated_ids.add(ulid)
            return ulid

    # This should never happen with 32^2 = 1024 possible suffixes
    raise RuntimeError("Failed to generate unique ID after max attempts")


def encode_crockford_base32(num: int) -> str:
    """Encode a number to Crockford's Base32."""
    if num == 0:
        return "0"

    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    output = ""

    while num > 0:
        output = alphabet[num & 31] + output
        num >>= 5

    return output


def is_valid_ulid_short(id_str: str) -> bool:
    """
    Check if a string is a valid 8-character Crockford Base32 ID.
    Must be exactly 8 characters, all from the Crockford alphabet (lowercase).
    """
    if len(id_str) != 8:
        return False

    return all(c in CROCKFORD_ALPHABET for c in id_str)


def parse_filename(filename: str) -> tuple[str | None, str]:
    """
    Parse a filename to extract ID prefix (if valid) and the semantic name.

    Returns:
        (id_or_none, semantic_name)

    Examples:
        "1jgmfyfk_linux_symbolic_link.md" -> ("1jgmfyfk", "linux_symbolic_link")
        "01hjcz2_dijkstra_algorithm.md" -> (None, "dijkstra_algorithm")  # ID too short
        "kerberos_protocol.md" -> (None, "kerberos_protocol")  # No ID prefix
    """
    # Remove .md extension
    name = filename[:-3] if filename.endswith(".md") else filename

    # Check if starts with valid 8-char ID + underscore
    if len(name) > 9 and name[8] == "_":
        potential_id = name[:8]
        rest = name[9:]
        if is_valid_ulid_short(potential_id):
            return (potential_id, rest)

    # No valid ID prefix - try to strip any partial ID-like prefix
    # Pattern: starts with digit (IDs always start with digits since they encode timestamps),
    # followed by crockford chars, then underscore
    match = re.match(r"^([0-9][0-9a-z]*)_(.+)$", name)
    if match:
        prefix, rest = match.groups()
        # If prefix looks like a partial/invalid ID (all crockford chars but wrong length)
        if all(c in CROCKFORD_ALPHABET for c in prefix) and len(prefix) != 8:
            return (None, rest)

    return (None, name)


def read_file(filepath: str) -> str:
    """Read file contents."""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def write_file(filepath: str, content: str) -> None:
    """Write content to file."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def parse_frontmatter(content: str) -> tuple[dict[str, str], str, str]:
    """
    Parse YAML frontmatter from markdown content.

    Returns:
        (frontmatter_dict, frontmatter_raw, body)

    The frontmatter_dict contains simple key-value pairs (only handles simple values).
    frontmatter_raw is the raw frontmatter text between --- markers.
    body is everything after the frontmatter.
    """
    if not content.startswith("---"):
        return ({}, "", content)

    # Find the closing ---
    end_match = re.search(r"\n---\n", content[3:])
    if not end_match:
        return ({}, "", content)

    end_pos = end_match.start() + 3  # Position in original content
    frontmatter_raw = content[4:end_pos]  # Skip opening ---\n
    body = content[end_pos + 5:]  # Skip closing \n---\n

    # Parse simple key-value pairs (handles strings and simple values)
    frontmatter = {}
    for line in frontmatter_raw.split("\n"):
        if ":" in line and not line.startswith(" ") and not line.startswith("\t"):
            key, _, value = line.partition(":")
            frontmatter[key.strip()] = value.strip()

    return (frontmatter, frontmatter_raw, body)


def update_frontmatter_id(content: str, new_id: str) -> str:
    """
    Update the 'id' field in the frontmatter to the new value.
    Preserves all other frontmatter content exactly as-is.
    """
    if not content.startswith("---"):
        # No frontmatter - add it
        return f"---\nid: {new_id}\n---\n{content}"

    # Find the closing ---
    end_match = re.search(r"\n---\n", content[3:])
    if not end_match:
        return content

    end_pos = end_match.start() + 3
    frontmatter_raw = content[4:end_pos]
    body = content[end_pos + 5:]

    # Update or add the id field
    lines = frontmatter_raw.split("\n")
    new_lines = []
    id_found = False

    for line in lines:
        if line.startswith("id:"):
            new_lines.append(f"id: {new_id}")
            id_found = True
        else:
            new_lines.append(line)

    if not id_found:
        # Add id as first field
        new_lines.insert(0, f"id: {new_id}")

    new_frontmatter = "\n".join(new_lines)
    return f"---\n{new_frontmatter}\n---\n{body}"


def find_markdown_files(directory: str) -> list[str]:
    """Find all .md files in the given directory (non-recursive)."""
    files = []
    for entry in os.listdir(directory):
        if entry.endswith(".md"):
            files.append(os.path.join(directory, entry))
    return sorted(files)


def needs_fixing(filepath: str, no_rename: bool = False) -> tuple[bool, str]:
    """
    Check if a file needs its ID fixed.

    Returns:
        (needs_fix, reason)
    """
    content = read_file(filepath)
    frontmatter, _, _ = parse_frontmatter(content)
    frontmatter_id = frontmatter.get("id", "")

    if no_rename:
        # Only check frontmatter — filename prefix doesn't matter
        if not frontmatter_id or not is_valid_ulid_short(frontmatter_id):
            return (True, f"frontmatter id missing or invalid ('{frontmatter_id}')")
        return (False, "")

    filename = os.path.basename(filepath)
    file_id, _ = parse_filename(filename)

    if file_id is None:
        return (True, "filename missing valid 8-char ID prefix")

    if frontmatter_id != file_id:
        return (True, f"frontmatter id '{frontmatter_id}' doesn't match filename id '{file_id}'")

    return (False, "")


def fix_file(
    filepath: str,
    dry_run: bool = False,
    no_rename: bool = False,
    quiet: bool = False,
) -> tuple[str, str] | None:
    """
    Fix a file's ID in both filename and frontmatter.

    When no_rename=True, only updates the frontmatter ID without renaming.
    When quiet=True, suppresses human-readable output (for --json mode).

    Returns:
        (old_path, new_path) if changes were made, None if skipped
    """
    filename = os.path.basename(filepath)
    directory = os.path.dirname(filepath)

    # Generate new ID
    new_id = generate_ulid_short()

    if no_rename:
        new_filepath = filepath
    else:
        _, semantic_name = parse_filename(filename)
        new_filename = f"{new_id}_{semantic_name}.md"
        new_filepath = os.path.join(directory, new_filename)

    if dry_run:
        if no_rename:
            if not quiet:
                print(f"  Would update frontmatter id to: {new_id} (no rename)")
        else:
            if not quiet:
                print(f"  Would rename: {filename} -> {os.path.basename(new_filepath)}")
                print(f"  Would update frontmatter id to: {new_id}")
        return (filepath, new_filepath)

    if not no_rename:
        # Check for collision - don't overwrite existing files
        if os.path.exists(new_filepath) and new_filepath != filepath:
            if not quiet:
                print(f"  ERROR: Target file {os.path.basename(new_filepath)} already exists. Skipping.")
            return None

    # Read and update content
    content = read_file(filepath)
    new_content = update_frontmatter_id(content, new_id)

    # Write updated content
    write_file(new_filepath, new_content)

    # Remove old file (if renamed to a different path)
    if not no_rename and filepath != new_filepath:
        os.remove(filepath)

    if not quiet:
        if no_rename:
            print(f"  Updated frontmatter id to: {new_id} (no rename)")
        else:
            print(f"  Renamed: {filename} -> {os.path.basename(new_filepath)}")
            print(f"  Updated frontmatter id to: {new_id}")

    return (filepath, new_filepath)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fix KB document IDs and filenames"
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
        help="Only update frontmatter ID, don't rename files (for projects/)"
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Output rename mapping as JSON (for piping to fix_wiki_links.py)"
    )

    args = parser.parse_args()
    quiet = args.json_output

    # Resolve path
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

    # Check each file
    files_to_fix = []
    for filepath in md_files:
        needs_fix, reason = needs_fixing(filepath, no_rename=args.no_rename)
        if needs_fix:
            files_to_fix.append((filepath, reason))

    if not files_to_fix:
        if quiet:
            print("[]")
        else:
            print("All files have valid IDs. Nothing to fix.")
        return 0

    if not quiet:
        print(f"Found {len(files_to_fix)} files that need fixing:\n")

    # Fix each file
    fixed_count = 0
    renames: list[dict[str, str]] = []
    for filepath, reason in files_to_fix:
        filename = os.path.basename(filepath)
        if not quiet:
            print(f"[{fixed_count + 1}/{len(files_to_fix)}] {filename}")
            print(f"  Reason: {reason}")

        result = fix_file(
            filepath,
            dry_run=args.dry_run,
            no_rename=args.no_rename,
            quiet=quiet,
        )
        if result:
            fixed_count += 1
            old_path, new_path = result
            old_name = os.path.basename(old_path)
            new_name = os.path.basename(new_path)
            if old_name != new_name:
                renames.append({"old": old_name, "new": new_name})
        if not quiet:
            print()

    if quiet:
        print(json.dumps(renames))
    elif args.dry_run:
        print(f"Would fix {fixed_count} files.")
    else:
        print(f"Fixed {fixed_count} files.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
