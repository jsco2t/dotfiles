#!/usr/bin/env python3
# Inspired by "ship-the-result" by ChufanS008
# (https://github.com/ChufanS008/ship-the-result, reviewed at commit b40a8de).
# Independent, hardened reimplementation: Python standard library only. File
# reads triggered by -F/--body-file/--notes-file go through the safe_read_text
# guard in residue_check.py, so this hook never reads home-directory dotfiles,
# sensitive directories (~/.ssh, ~/.aws, ...) or secret-looking files.
# Not affiliated with or endorsed by the original project.
"""Claude Code PreToolUse hook for the Bash tool.

Intercepts commands that write outward-facing text into project history
(git commit, gh/ghtk pr create/edit, gh release create/edit) and scans the message,
title, body and notes for conversation residue. Also scans staged changes for
residue in comments, test names and new filenames.

Blocking behaviour: exit 2 with the findings on stderr. Claude Code feeds
stderr back to the model, which then rewrites. If the exact same command is
issued again unchanged, it passes: that is the model (or the human) confirming
the flagged phrase is a genuine requirement, not residue. The hook is a
backstop and a nudge, not an enforcement gate -- a re-issued identical command
always proceeds.

Hook input arrives as JSON on stdin: {"tool_name": "Bash", "tool_input": {"command": "..."}}
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from residue_check import scan_text, format_findings, safe_read_text  # noqa: E402

CONFIRM_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "ship-the-result"
TRIGGERS = re.compile(r"\b(git\s+commit|gh\s+pr\s+(create|edit)|gh\s+release\s+(create|edit)|ghtk\s+pr\s+(create|edit))\b")

# Flags whose values are outward-facing prose.
TEXT_FLAGS = ("-m", "--message", "-t", "--title", "-b", "--body", "-n", "--notes", "-F", "--body-file", "--notes-file")
FILE_FLAGS = ("-F", "--body-file", "--notes-file")

COMMENT_LINE = re.compile(r"^\+\s*(#|//|/\*|\*|<!--|--|;|\"\"\"|''')")
TEST_DEF = re.compile(r"^\+\s*(def test_\w+|(it|test|describe)\s*\(\s*['\"`]|func Test\w+|fn test_\w+|@Test)")


def _unescape(value: str) -> str:
    """Turn common backslash escapes (\\n, \\t, \\r) into real characters.

    A targeted replacement rather than codecs' 'unicode_escape', which mangles
    UTF-8 and can raise on some byte sequences.
    """
    if "\\" not in value:
        return value
    for esc, real in (("\\n", "\n"), ("\\t", "\t"), ("\\r", "\r")):
        value = value.replace(esc, real)
    return value


def extract_text_args(command: str) -> tuple[list[str], list[str]]:
    """Pull quoted values following message/title/body flags, plus heredoc bodies.

    Returns (texts, skips): texts to scan, and human-readable notes for any
    referenced file that the safety guard refused to read (so an unscannable
    file is reported rather than silently passing unchecked).

    Only the part of the command from the first trigger (git commit / gh pr ...)
    onward is inspected, so a heredoc feeding an earlier `python3 -` in the same
    command line is not mistaken for the commit message.
    """
    texts: list[str] = []
    skips: list[str] = []
    trig = TRIGGERS.search(command)
    command = command[trig.start():] if trig else command
    # heredoc attached to this statement: $(cat <<'EOF' ... EOF). The opener must
    # sit on the same line as the trigger, otherwise it belongs to a later command.
    for m in re.finditer(r"<<-?\s*['\"]?(\w+)['\"]?\n(.*?)\n\s*\1\b", command, re.DOTALL):
        if "\n" in command[: m.start()]:
            continue
        texts.append(m.group(2))
    # flag "value" / flag 'value' / flag=value
    flag_alt = "|".join(re.escape(f) for f in TEXT_FLAGS)
    for m in re.finditer(rf"(?:{flag_alt})(?:\s+|=)(\"((?:[^\"\\]|\\.)*)\"|'([^']*)'|(\S+))", command):
        val = m.group(2) if m.group(2) is not None else (m.group(3) if m.group(3) is not None else m.group(4))
        if val and not val.startswith("-") and "$(" not in val:  # heredoc bodies were captured above
            flag = m.group(0).split()[0].split("=")[0]
            if flag in FILE_FLAGS:
                text, err = safe_read_text(val)
                if err:
                    skips.append(err)
                elif text is not None:
                    texts.append(text)
            else:
                texts.append(_unescape(val))
    return texts, skips


def staged_residue() -> list[str]:
    """Scan staged diff for residue in comments, test names and added filenames."""
    reports: list[str] = []
    try:
        diff = subprocess.run(
            ["git", "diff", "--cached", "-U0", "--no-color"], capture_output=True, text=True, timeout=10
        ).stdout
        added = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=A"], capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:
        return reports

    comment_lines, name_lines = [], []
    for line in diff.splitlines():
        if COMMENT_LINE.match(line):
            comment_lines.append(line[1:].strip())
        elif TEST_DEF.match(line):
            name_lines.append(line[1:].strip())

    if comment_lines:
        f = scan_text("\n".join(comment_lines), "comment")
        if f:
            reports.append(format_findings(f, "staged comments"))
    if name_lines:
        f = scan_text("\n".join(name_lines), "name")
        if f:
            reports.append(format_findings(f, "staged test names"))
    if added.strip():
        f = scan_text("\n".join(Path(p).name for p in added.splitlines()), "name")
        if f:
            reports.append(format_findings(f, "new filenames"))
    return reports


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    command = (payload.get("tool_input") or {}).get("command", "")
    if not command or not TRIGGERS.search(command):
        return 0

    digest = hashlib.sha256(command.encode()).hexdigest()[:16]
    CONFIRM_DIR.mkdir(parents=True, exist_ok=True)
    marker = CONFIRM_DIR / digest
    if marker.exists():
        marker.unlink(missing_ok=True)  # confirmed once, let it through
        return 0

    reports: list[str] = []
    texts, skips = extract_text_args(command)
    for text in texts:
        found = scan_text(text, "message")
        if found:
            reports.append(format_findings(found, "commit/PR text"))
    if "git commit" in command:
        reports.extend(staged_residue())
    for note in skips:
        reports.append(
            "a referenced file could not be scanned, so it was NOT checked:\n"
            f"  {note}\n"
            "  Provide the text inline, or use a file inside the repository, then re-run."
        )

    if not reports:
        return 0

    marker.touch()
    sys.stderr.write("[ship-the-result] blocked: outward-facing text carries conversation residue.\n\n")
    sys.stderr.write("\n\n".join(reports))
    sys.stderr.write("\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
