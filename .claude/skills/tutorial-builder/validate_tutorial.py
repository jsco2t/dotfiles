#!/usr/bin/env python3
"""Validate tutorial files against quality and structure requirements.

Checks that tutorials follow the established patterns:
- Proper frontmatter with 'tutorial' tag
- Prerequisites/setup section
- Interactive "Try it" or "Explore" sections
- Code blocks with language tags
- Progressive structure
- No presumed knowledge (checks for setup steps)

Zero external dependencies. Works with Python 3.8+ on macOS and Linux.

Usage:
    python3 validate_tutorial.py <file_or_directory>
    python3 validate_tutorial.py learning/my-topic/
    python3 validate_tutorial.py learning/my-topic/01_basics.md
"""

import json
import os
import re
import sys
from pathlib import Path


def parse_frontmatter(text):
    """Extract YAML frontmatter fields."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm_text = text[4:end]
    result = {}
    current_key = None
    current_list = None
    for line in fm_text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and current_key:
            if current_list is None:
                current_list = []
            current_list.append(stripped[2:].strip().strip('"').strip("'"))
            continue
        if current_list is not None and current_key:
            result[current_key] = current_list
            current_list = None
        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            current_key = key
            if val:
                result[key] = val
    if current_list is not None and current_key:
        result[current_key] = current_list
    return result


def validate_file(filepath):
    """Validate a single tutorial file. Returns a list of issues."""
    issues = []
    warnings = []
    path = Path(filepath)

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return [f"Cannot read file: {e}"], []

    lines = text.split("\n")
    total_lines = len(lines)

    # --- Frontmatter checks ---
    fm = parse_frontmatter(text)
    if not fm:
        issues.append("Missing YAML frontmatter")
    else:
        if "title" not in fm:
            issues.append("Missing 'title' in frontmatter")
        if "id" not in fm:
            issues.append("Missing 'id' in frontmatter")
        if "createdate" not in fm:
            issues.append("Missing 'createdate' in frontmatter")
        tags = fm.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        if "tutorial" not in tags:
            issues.append("Missing 'tutorial' tag in frontmatter")

    # --- Structure checks ---
    headings = []
    code_blocks = []
    in_code_block = False
    code_lang = None
    interactive_sections = 0
    has_setup = False
    has_prereqs = False
    untagged_code_blocks = 0

    for i, line in enumerate(lines, 1):
        # Track code blocks
        if line.strip().startswith("```"):
            if not in_code_block:
                in_code_block = True
                lang = line.strip()[3:].strip()
                code_lang = lang if lang else None
                if not lang:
                    untagged_code_blocks += 1
                code_blocks.append({"line": i, "lang": lang})
            else:
                in_code_block = False
                code_lang = None
            continue

        if in_code_block:
            continue

        # Track headings
        heading_match = re.match(r"^(#{1,6})\s+(.*)", line)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            headings.append({"level": level, "title": title, "line": i})

            title_lower = title.lower()

            # Check for setup/prerequisites
            if any(kw in title_lower for kw in [
                "setup", "prerequisite", "requirements", "what you need",
                "before you begin", "getting started", "installation",
                "project setup", "environment",
            ]):
                has_setup = True
                has_prereqs = True

            # Check for interactive sections
            if any(kw in title_lower for kw in [
                "try it", "explore", "exercise", "challenge",
                "your turn", "experiment", "hands-on", "practice",
                "try this", "do it yourself",
            ]):
                interactive_sections += 1

    # --- Quality checks ---
    if not has_prereqs:
        warnings.append(
            "No prerequisites/setup section found. Consider adding one "
            "with heading like 'Prerequisites', 'Setup', or 'What You Need'"
        )

    if interactive_sections == 0:
        issues.append(
            "No interactive sections found. Tutorials must include at "
            "least one 'Try it', 'Explore', 'Exercise', or 'Challenge' "
            "section to reinforce learning"
        )

    if len(code_blocks) == 0:
        warnings.append("No code blocks found — unusual for a tutorial")

    if untagged_code_blocks > 0:
        warnings.append(
            f"{untagged_code_blocks} code block(s) without language tags. "
            f"Add language identifiers (```go, ```bash, etc.)"
        )

    if len(headings) < 3:
        warnings.append(
            f"Only {len(headings)} headings found. Tutorials should be "
            f"broken into multiple sections for progressive learning"
        )

    # Check for word count (too short = not enough depth)
    # Strip frontmatter and code blocks for word count
    body = text
    if body.startswith("---"):
        end = body.find("\n---", 3)
        if end != -1:
            body = body[end + 4:]
    body = re.sub(r"```[\s\S]*?```", "", body)
    word_count = len(body.split())

    if word_count < 300:
        warnings.append(
            f"Only {word_count} words of prose. Tutorials should have "
            f"enough explanation to teach without presuming knowledge"
        )

    return issues, warnings


def validate_directory(dirpath):
    """Validate all tutorial files in a directory."""
    results = {}
    path = Path(dirpath)

    for md_file in sorted(path.rglob("*.md")):
        if md_file.name == "00_index.md":
            continue
        rel = str(md_file.relative_to(path.parent))
        issues, warnings = validate_file(md_file)
        results[rel] = {"issues": issues, "warnings": warnings}

    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 validate_tutorial.py <file_or_directory>",
              file=sys.stderr)
        sys.exit(1)

    target = sys.argv[1]

    if os.path.isfile(target):
        issues, warnings = validate_file(target)
        report = {
            "file": target,
            "issues": issues,
            "warnings": warnings,
            "pass": len(issues) == 0,
        }
        print(json.dumps(report, indent=2))
        sys.exit(0 if report["pass"] else 1)

    elif os.path.isdir(target):
        results = validate_directory(target)
        all_pass = True
        summary = {"files": 0, "passed": 0, "failed": 0, "details": {}}

        for filepath, result in results.items():
            summary["files"] += 1
            passed = len(result["issues"]) == 0
            if passed:
                summary["passed"] += 1
            else:
                summary["failed"] += 1
                all_pass = False
            summary["details"][filepath] = {
                "pass": passed,
                "issues": result["issues"],
                "warnings": result["warnings"],
            }

        print(json.dumps(summary, indent=2))
        sys.exit(0 if all_pass else 1)

    else:
        print(f"Error: '{target}' is not a file or directory",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
