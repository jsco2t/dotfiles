#!/usr/bin/env python3
"""
Document front matter cleanup: tag normalization, tag suggestion, and frontmatter addition.

Usage:
    python3 .tools/doc_fix.py [OPTIONS] [PATH...]

    PATH         File or directory path(s). Omit to process all content dirs.

Options:
    --dry-run    Preview changes without writing
    --json       Output JSON (for skill to parse)
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta


# ── Exclusions ──────────────────────────────────────────────────────────────

EXCLUDED_DIRS = {
    "templates", "TaskNotes", "boards", ".obsidian", ".git",
    "scratch", "xchive", "resources",
}

CONTENT_DIRS = ["kb", "journal", "projects", "logs", "learning"]


# ── Tag normalization map ───────────────────────────────────────────────────

TAG_NORMALIZATION: dict[str, str] = {
    "golang": "go", "go-lang": "go",
    "kubernetes": "k8s", "kube": "k8s",
    "javascript": "js", "typescript": "ts",
    "python": "py", "ruby": "rb",
    "bash": "sh", "shell-script": "sh",
    "mac": "macos", "osx": "macos", "macosx": "macos",
    "gnu-linux": "linux", "rocky-linux": "rocky",
    "deb": "debian", "ubuntu-linux": "ubuntu",
    "nvim": "neovim",
    "artificial-intelligence": "ai", "large-language-model": "llm",
    "machine-learning": "ml", "secure-shell": "ssh",
    "network-file-system": "nfs", "command-line": "cli",
    "terminal": "cli", "rest-api": "api", "database": "db",
}

# ── Tag blocklist (never suggest or keep these tags) ──────────────────────

TAG_BLOCKLIST: set[str] = {
    "sh",     # too generic — nearly every doc has shell code blocks
    "yaml",   # too generic — nearly every doc has YAML frontmatter/config
    "json",   # too generic — data format, not a meaningful topic tag
    "toml",   # too generic — config format, not a meaningful topic tag
}

# ── Code block language → tag mapping ───────────────────────────────────────

CODE_LANG_TAGS: dict[str, str] = {
    "go": "go", "golang": "go",
    "python": "py", "py": "py",
    "javascript": "js", "js": "js",
    "typescript": "ts", "ts": "ts",
    "bash": "sh", "sh": "sh", "shell": "sh", "zsh": "sh",
    "yaml": "yaml", "yml": "yaml",
    "json": "json",
    "dockerfile": "docker",
    "sql": "sql",
    "rust": "rust",
    "ruby": "rb", "rb": "rb",
    "lua": "lua",
    "hcl": "terraform",
    "toml": "toml",
    "css": "css",
    "html": "html",
}

# ── Keyword patterns → tag suggestions ──────────────────────────────────────
# Each entry: (compiled regex, suggested tag)
# Built once at import time for performance.

_KEYWORD_RULES: list[tuple[str, str]] = [
    (r"\bkubernetes\b|\bk8s\b|\bkubectl\b|\bhelm\b", "k8s"),
    (r"\bdocker\b|\bdockerfile\b|\bdocker-compose\b", "docker"),
    (r"\bpodman\b", "podman"),
    (r"\bgit\b|\bgithub\b|\bgitlab\b", "git"),
    (r"\bssh\b|\bopenssh\b|\bsshd\b", "ssh"),
    (r"\blinux\b|\bunix\b", "linux"),
    (r"\bsecurity\b|\bauthentication\b|\bauthorization\b|\btls\b|\bssl\b", "security"),
    (r"\bnetwork(?:ing)?\b|\bsubnet\b|\bfirewall\b|\bdns\b", "networking"),
    (r"\bstorage\b|\bfilesystem\b|\bdisk\b|\bnfs\b|\bceph\b", "storage"),
    (r"\bhomelab\b|\bself-host\b|\bself-hosted\b", "homelab"),
    (r"\balgorithm\b", "algorithm"),
    (r"\bdata[- ]structure", "data-structures"),
    (r"\bchatgpt\b|\bclaude\b|\bopenai\b|\bllm\b", "llm"),
    (r"\bproxmox\b", "proxmox"),
    (r"\blxc\b|\blxd\b", "lxc"),
    (r"\bcaddy\b|\bcaddyfile\b", "caddy"),
    (r"\bnginx\b", "nginx"),
    (r"\bpostgres(?:ql)?\b", "postgresql"),
    (r"\bredis\b", "redis"),
    (r"\bneovim\b|\bnvim\b", "neovim"),
    (r"\bansible\b", "ansible"),
    (r"\bterraform\b", "terraform"),
    (r"\bwarewulf\b", "warewulf"),
    (r"\bslurm\b", "slurm"),
    (r"\bsystemd\b|\bjournalctl\b", "systemd"),
]

KEYWORD_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pattern, re.IGNORECASE), tag)
    for pattern, tag in _KEYWORD_RULES
]


# ── Frontmatter parsing ────────────────────────────────────────────────────

def parse_frontmatter(content: str) -> tuple[dict[str, str], list[str], str, str]:
    """
    Parse YAML frontmatter from markdown content.

    Returns:
        (fields_dict, tags_list, frontmatter_raw, body)

    fields_dict: simple key→value (excluding tags)
    tags_list: list of tag strings
    frontmatter_raw: raw text between --- markers (including the markers)
    body: everything after frontmatter
    """
    if not content.startswith("---"):
        return ({}, [], "", content)

    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        # Try end-of-file frontmatter (no trailing newline after ---)
        end_match = re.search(r"\n---\s*$", content[3:])
        if not end_match:
            return ({}, [], "", content)

    # content[3:] skips opening "---"; end_match is relative to that slice
    body_start = 3 + end_match.end()       # first char after closing ---\n
    fm_inner_end = 3 + end_match.start()   # position of \n before closing ---
    fm_inner = content[4:fm_inner_end]     # between opening ---\n and \n---
    body = content[body_start:]
    fm_raw = content[:body_start]

    # Parse fields
    fields: dict[str, str] = {}
    tags: list[str] = []

    lines = fm_inner.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        # Tag handling — inline array: tags: [foo, bar] or tags: []
        tag_inline = re.match(r'^tags:\s*\[([^\]]*)\]\s*$', line)
        if tag_inline:
            raw_tags = tag_inline.group(1).strip()
            if raw_tags:
                tags = [t.strip().strip("'\"") for t in raw_tags.split(",") if t.strip()]
            i += 1
            continue

        # Tag handling — YAML list: tags:\n  - foo\n  - bar
        if re.match(r'^tags:\s*$', line):
            i += 1
            while i < len(lines) and re.match(r'^\s+-\s+', lines[i]):
                tag_val = re.match(r'^\s+-\s+(.+)$', lines[i])
                if tag_val:
                    tags.append(tag_val.group(1).strip().strip("'\""))
                i += 1
            continue

        # Tag handling — tags on same line as key but not array
        tag_single = re.match(r'^tags:\s+(\S.*)$', line)
        if tag_single:
            val = tag_single.group(1).strip().strip("'\"")
            if val:
                tags = [val]
            i += 1
            continue

        # Regular field
        if ":" in line and not line.startswith(" ") and not line.startswith("\t"):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip().strip("'\"")

        i += 1

    return (fields, tags, fm_raw, body)


def rebuild_tags_block(tags: list[str]) -> str:
    """Build a YAML tags block in list format."""
    if not tags:
        return "tags: []"
    lines = ["tags:"]
    for t in tags:
        lines.append(f"  - {t}")
    return "\n".join(lines)


def replace_tags_in_frontmatter(fm_raw: str, new_tags: list[str]) -> str:
    """
    Replace the tags section within raw frontmatter text.
    Preserves everything else character-for-character.
    """
    new_block = rebuild_tags_block(new_tags)

    # Pattern: tags line followed by optional list items (YAML list format)
    pattern_list = re.compile(
        r'^tags:\s*\n(?:\s+-\s+.+\n?)*',
        re.MULTILINE,
    )
    if pattern_list.search(fm_raw):
        return pattern_list.sub(new_block + "\n", fm_raw, count=1)

    # Pattern: inline array format tags: [...]
    pattern_inline = re.compile(r'^tags:\s*\[.*?\]\s*$', re.MULTILINE)
    if pattern_inline.search(fm_raw):
        return pattern_inline.sub(new_block, fm_raw, count=1)

    # Pattern: tags with single value on same line
    pattern_single = re.compile(r'^tags:\s+\S.*$', re.MULTILINE)
    if pattern_single.search(fm_raw):
        return pattern_single.sub(new_block, fm_raw, count=1)

    # No tags field found — add before closing ---
    return fm_raw.rstrip().rstrip("-").rstrip() + "\n" + new_block + "\n---\n"


def build_frontmatter(title: str, tags: list[str]) -> str:
    """Build new frontmatter for a file that has none."""
    now = datetime.now(timezone(timedelta(hours=-7)))
    createdate = now.strftime("%Y-%m-%dT%H:%M:%S-07:00")
    tag_lines = "\n".join(f"  - {t}" for t in tags) if tags else "[]"
    tag_section = f"tags:\n{tag_lines}" if tags else "tags: []"
    return f"---\nid: placeholder\ncreatedate: {createdate}\ntitle: {title}\n{tag_section}\n---\n"


# ── Title derivation ───────────────────────────────────────────────────────

def title_from_filename(filepath: str) -> str:
    """
    Derive a human-readable title from a filename.
    Strips numbered prefixes (01-, 02-), ID prefixes, and extensions.
    Converts separators to spaces, title-cases.
    """
    name = os.path.basename(filepath)
    name = re.sub(r'\.md$', '', name, flags=re.IGNORECASE)

    # Strip 8-char ULID prefix + underscore
    name = re.sub(r'^[0-9a-z]{8}_', '', name)

    # Strip numbered prefix like 01- or 01_
    name = re.sub(r'^\d{1,3}[-_]', '', name)

    # Convert separators to spaces
    name = name.replace("_", " ").replace("-", " ")

    # Title case
    return name.strip().title()


# ── Tag suggestion engine ──────────────────────────────────────────────────

def suggest_tags(content: str, existing_tags: list[str]) -> list[str]:
    """
    Suggest tags based on content analysis.
    Returns tags not already present (after normalization).
    """
    existing_normalized = {normalize_tag(t) for t in existing_tags}
    suggestions: dict[str, bool] = {}  # tag -> True (preserves insertion order)

    # 1. Code block languages
    for lang_match in re.finditer(r'```(\w+)', content):
        lang = lang_match.group(1).lower()
        tag = CODE_LANG_TAGS.get(lang)
        if tag and tag not in TAG_BLOCKLIST and tag not in existing_normalized and tag not in suggestions:
            suggestions[tag] = True

    # 2. Keyword patterns (search full content)
    for pattern, tag in KEYWORD_PATTERNS:
        if tag not in TAG_BLOCKLIST and tag not in existing_normalized and tag not in suggestions:
            if pattern.search(content):
                suggestions[tag] = True

    return list(suggestions.keys())


def normalize_tag(tag: str) -> str:
    """Normalize a single tag through the normalization map."""
    t = tag.lower().strip()
    return TAG_NORMALIZATION.get(t, t)


def normalize_tags(tags: list[str]) -> tuple[list[str], dict[str, str]]:
    """
    Normalize a list of tags. Returns (new_tags, changes_map).
    changes_map: old_tag -> new_tag (only for tags that changed).
    Deduplicates after normalization, preserving first occurrence order.
    """
    changes: dict[str, str] = {}
    seen: set[str] = set()
    result: list[str] = []

    for tag in tags:
        normalized = normalize_tag(tag)
        if normalized != tag:
            changes[tag] = normalized
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    return result, changes


# ── TOC fixing ────────────────────────────────────────────────────────────


def strip_markdown_inline(text: str) -> str:
    """Strip inline markdown formatting (bold, italic, code, links)."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    return text


def heading_to_anchor(text: str) -> str:
    """Convert heading text to GitHub-flavored markdown anchor."""
    text = strip_markdown_inline(text)
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'\s+', '-', text.strip())
    return text


def extract_headings(body: str) -> list[tuple[str, str]]:
    """
    Extract ## headings from markdown body, skipping code blocks and the TOC heading.
    Returns list of (display_text, anchor).
    """
    headings = []
    in_code_block = False
    for line in body.split('\n'):
        if line.startswith('```'):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        m = re.match(r'^## (.+)$', line)
        if m:
            raw_text = m.group(1).strip()
            if raw_text.lower() == 'table of contents':
                continue
            display = strip_markdown_inline(raw_text)
            display = re.sub(r'^\d+\.\s+', '', display)
            anchor = heading_to_anchor(raw_text)
            headings.append((display, anchor))
    return headings


def build_toc(headings: list[tuple[str, str]]) -> str:
    """Build a numbered TOC from headings list."""
    lines = []
    for i, (display, anchor) in enumerate(headings, 1):
        lines.append(f"{i}. [{display}](#{anchor})")
    return '\n'.join(lines)


def fix_toc(body: str) -> tuple[str, bool, int]:
    """
    Fix the Table of Contents in the document body.
    Returns (new_body, changed, entry_count).
    """
    toc_match = re.search(r'^## Table of Contents[ \t]*\n', body, re.MULTILINE)
    if not toc_match:
        return body, False, 0

    toc_heading_end = toc_match.end()

    # Find next ## heading after the TOC heading
    next_heading = re.search(r'^## ', body[toc_heading_end:], re.MULTILINE)
    if next_heading:
        toc_section_end = toc_heading_end + next_heading.start()
    else:
        toc_section_end = len(body)

    # Check for --- separator in the TOC section
    between = body[toc_heading_end:toc_section_end]
    has_separator = bool(re.search(r'^---[ \t]*$', between, re.MULTILINE))

    # Extract headings from entire body
    headings = extract_headings(body)
    if not headings:
        return body, False, 0

    # Build new TOC section
    toc_content = build_toc(headings)
    separator = "\n---\n" if has_separator else ""
    new_toc_section = f"## Table of Contents\n\n{toc_content}\n{separator}\n"

    new_body = body[:toc_match.start()] + new_toc_section + body[toc_section_end:]

    changed = new_body != body
    return new_body, changed, len(headings)


# ── File processing ─────────────────────────────────────────────────────────

TAG_MAX = 10


def infer_path_tags(filepath: str, base_dir: str) -> list[str]:
    """
    Infer tags from a file's location in the directory tree.
    Files under projects/<name>/ get the project name as a tag.
    """
    rel = os.path.relpath(filepath, base_dir)
    parts = rel.split(os.sep)
    if len(parts) >= 2 and parts[0] == "projects":
        project_name = parts[1].lower()
        return [project_name]
    return []


def process_file(filepath: str, dry_run: bool, base_dir: str = "") -> dict | None:
    """
    Process a single markdown file.

    Returns a result dict with keys:
        file, action, tags_before, tags_after,
        normalized, suggested, added_frontmatter, skipped, reason
    Or None if file should be skipped entirely.
    """
    result: dict = {
        "file": filepath,
        "action": "none",
        "tags_before": [],
        "tags_after": [],
        "normalized": {},
        "suggested": [],
        "added_frontmatter": False,
        "skipped": False,
        "reason": "",
        "toc_fixed": False,
        "toc_entries": 0,
    }

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError) as e:
        result["skipped"] = True
        result["reason"] = str(e)
        return result

    # Skip empty files
    if not content.strip():
        result["skipped"] = True
        result["reason"] = "empty file"
        return result

    _, tags, fm_raw, body = parse_frontmatter(content)

    # Infer tags from file path (e.g. project name)
    path_tags = infer_path_tags(filepath, base_dir) if base_dir else []

    if not fm_raw:
        # ── No frontmatter → add it ────────────────────────────────────
        fixed_content, toc_changed, toc_count = fix_toc(content)
        result["toc_fixed"] = toc_changed
        result["toc_entries"] = toc_count

        title = title_from_filename(filepath)
        suggested = suggest_tags(fixed_content, path_tags)
        new_tags = [t for t in (path_tags + suggested) if t not in TAG_BLOCKLIST][:TAG_MAX]

        new_fm = build_frontmatter(title, new_tags)
        new_content = new_fm + "\n" + fixed_content

        result["action"] = "add_frontmatter"
        result["added_frontmatter"] = True
        result["tags_after"] = new_tags
        result["suggested"] = new_tags

        if not dry_run:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)

        return result

    # ── Has frontmatter → normalize + suggest ───────────────────────────

    result["tags_before"] = list(tags)

    # Fix TOC
    new_body, toc_changed, toc_count = fix_toc(body)
    result["toc_fixed"] = toc_changed
    result["toc_entries"] = toc_count

    # Normalize existing tags
    normalized_tags, norm_changes = normalize_tags(tags)
    result["normalized"] = norm_changes

    # Strip blocklisted tags from existing tags
    normalized_tags = [t for t in normalized_tags if t not in TAG_BLOCKLIST]

    # Reserve slots for path-inferred tags (e.g. project name), then add them
    existing_set = {t.lower() for t in normalized_tags}
    path_tags_to_add = [pt for pt in path_tags if pt not in existing_set]
    reserved_slots = len(path_tags_to_add)

    # Cap existing tags to make room for path tags
    base_tags = normalized_tags[:TAG_MAX - reserved_slots] + path_tags_to_add

    # Suggest new tags from content analysis
    full_content = (fm_raw + "\n" + new_body) if new_body else fm_raw
    suggested = suggest_tags(full_content, base_tags)

    # Fill remaining slots with suggestions
    slots_available = TAG_MAX - len(base_tags)
    tags_to_add = suggested[:max(0, slots_available)]
    result["suggested"] = tags_to_add

    final_tags = base_tags + tags_to_add
    result["tags_after"] = final_tags

    # Determine if anything changed
    tags_changed = final_tags != tags
    if not tags_changed and not toc_changed:
        result["action"] = "none"
        return result

    if tags_changed:
        result["action"] = "update_tags"
    else:
        result["action"] = "fix_toc"

    if not dry_run:
        new_fm = replace_tags_in_frontmatter(fm_raw, final_tags) if tags_changed else fm_raw
        new_content = new_fm + new_body
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

    return result


# ── Directory walking ───────────────────────────────────────────────────────

def is_excluded(path: str) -> bool:
    """Check if a path component is in the exclusion list."""
    parts = path.split(os.sep)
    for part in parts:
        if part in EXCLUDED_DIRS or (part.startswith(".") and part not in (".", "..")):
            return True
    return False


def find_markdown_files(path: str) -> list[str]:
    """
    Find all .md files under path, respecting exclusions.
    If path is a file, return it as a single-element list.
    """
    if os.path.isfile(path):
        return [path] if path.endswith(".md") else []

    results: list[str] = []
    for root, dirs, files in os.walk(path):
        # Filter excluded directories in-place to prevent descent
        dirs[:] = [
            d for d in dirs
            if d not in EXCLUDED_DIRS and not d.startswith(".")
        ]

        for fname in sorted(files):
            if fname.endswith(".md"):
                results.append(os.path.join(root, fname))

    return sorted(results)


# ── Output formatting ──────────────────────────────────────────────────────

def format_human(results: list[dict]) -> str:
    """Format results for human-readable output."""
    lines: list[str] = []
    changed = 0
    added_fm = 0
    normalized_count = 0
    suggested_count = 0
    toc_fixed_count = 0
    skipped = 0

    for r in results:
        if r["skipped"]:
            skipped += 1
            continue

        if r["action"] == "none":
            continue

        rel = r["file"]
        lines.append(f"  {rel}")

        if r["added_frontmatter"]:
            added_fm += 1
            title_tag = ", ".join(r["tags_after"][:5])
            suffix = "..." if len(r["tags_after"]) > 5 else ""
            lines.append(f"    + frontmatter added (tags: {title_tag}{suffix})")

        if r["normalized"]:
            normalized_count += 1
            for old, new in r["normalized"].items():
                lines.append(f"    {old} → {new}")

        if r["suggested"]:
            suggested_count += 1
            lines.append(f"    + suggested: {', '.join(r['suggested'])}")

        if r.get("toc_fixed"):
            toc_fixed_count += 1
            lines.append(f"    + TOC fixed ({r.get('toc_entries', 0)} entries)")

        changed += 1
        lines.append("")

    summary = [
        f"Files scanned:    {len(results)}",
        f"Files changed:    {changed}",
        f"  Tags normalized:  {normalized_count}",
        f"  Tags suggested:   {suggested_count}",
        f"  Frontmatter added:{added_fm}",
        f"  TOC fixed:        {toc_fixed_count}",
        f"Files skipped:    {skipped}",
    ]

    if lines:
        return "\n".join(lines) + "\n" + "\n".join(summary)
    return "\n".join(summary)


def format_json(results: list[dict]) -> str:
    """Format results as JSON."""
    changed = [r for r in results if r["action"] != "none" and not r["skipped"]]
    skipped = [r for r in results if r["skipped"]]
    fm_added_dirs = list({
        os.path.dirname(r["file"])
        for r in results
        if r["added_frontmatter"]
    })
    toc_fixed = sum(1 for r in changed if r.get("toc_fixed"))
    output = {
        "total": len(results),
        "changed": len(changed),
        "skipped": len(skipped),
        "toc_fixed": toc_fixed,
        "frontmatter_added_dirs": sorted(fm_added_dirs),
        "results": changed,
    }
    return json.dumps(output, indent=2)


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Document front matter cleanup: tag normalization, suggestions, and frontmatter addition."
    )
    parser.add_argument(
        "paths", nargs="*",
        help="File or directory path(s). Omit to process all content dirs.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Output JSON")

    args = parser.parse_args()

    # Resolve base directory (script lives in .tools/)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Determine targets
    if args.paths:
        targets: list[str] = []
        for p in args.paths:
            full = os.path.join(base_dir, p) if not os.path.isabs(p) else p
            targets.append(full)
    else:
        targets = [os.path.join(base_dir, d) for d in CONTENT_DIRS if os.path.exists(os.path.join(base_dir, d))]

    if not targets:
        print("No targets found.", file=sys.stderr)
        return 1

    # Collect all files
    all_files: list[str] = []
    for t in targets:
        if is_excluded(os.path.relpath(t, base_dir)):
            continue
        all_files.extend(find_markdown_files(t))

    if not all_files:
        if args.json_output:
            print(json.dumps({"total": 0, "changed": 0, "skipped": 0, "results": []}))
        else:
            print("No markdown files found.")
        return 0

    if not args.json_output and not args.dry_run:
        print(f"Processing {len(all_files)} files...\n")
    elif not args.json_output and args.dry_run:
        print(f"DRY RUN — scanning {len(all_files)} files...\n")

    # Process
    results: list[dict] = []
    for filepath in all_files:
        # Make paths relative for display
        rel_path = os.path.relpath(filepath, base_dir)
        r = process_file(filepath, dry_run=args.dry_run, base_dir=base_dir)
        if r:
            r["file"] = rel_path
            results.append(r)

    # Output
    if args.json_output:
        print(format_json(results))
    else:
        print(format_human(results))

    return 0


if __name__ == "__main__":
    sys.exit(main())
