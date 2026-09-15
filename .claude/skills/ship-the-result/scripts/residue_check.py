#!/usr/bin/env python3
# Inspired by "ship-the-result" by ChufanS008
# (https://github.com/ChufanS008/ship-the-result, reviewed at commit b40a8de).
# Independent, hardened reimplementation: Python standard library only, with a
# path-safety guard (never reads files directly in $HOME, sensitive directories
# such as ~/.ssh or ~/.aws, or secret-looking filenames) and a faster scanner.
# Not affiliated with or endorsed by the original project.
"""Scan outward-facing text for conversation residue.

"Residue" is any phrase that describes the process of arriving at the
deliverable (a rejected draft, a correction, a reviewer's feedback) rather
than the deliverable itself. Commit messages, PR titles, code comments, test
names and filenames should read as if the conversation never happened.

Usage:
    residue_check.py [--kind KIND] [--json] [FILE ...]
    echo "Add retry logic (without exponential backoff)" | residue_check.py

KIND narrows which pattern families apply:
    message   commit message / PR title / PR body / release notes (default)
    comment   code comment lines
    name      identifiers: test names, function names, filenames, titles

Exit code 0 = clean, 1 = residue found. Findings go to stdout.

Safety: file arguments are read through safe_read_text(), which refuses paths
that sit directly in the home directory, inside a sensitive directory, under a
protected system location, or whose name looks like a secret. stdin is never
restricted (the caller chose to feed it in).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat as statmod
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

# --------------------------------------------------------------------------- #
# Residue patterns
# --------------------------------------------------------------------------- #
# Each family: (family_id, why it is residue, [regexes]).
# Patterns are deliberately conservative. A false positive costs one re-read;
# a false negative costs a permanent line in git history.
FAMILIES = [
    (
        "negated-draft",
        "names something that was never a requirement, only a rejected draft",
        [
            r"\(\s*(no|without|sans|minus|non-)\s*[\w\- ]+\)",        # (no ketchup) (without lodash)
            r"\b(no|without|non)[\s\-]\w+\s+(version|variant|edition|approach|impl(ementation)?)\b",
            r"\bwithout (the|using|relying on|any)\b",
            r"\binstead of (the|using|a|an)\b",
            r"\brather than (the|using|a|an)\b",
            r"\bnot (using|use|relying on|via|with)\b",
            r"\b(dropped|removed|ditched|took out|got rid of) the (\w+ )?(approach|version|draft|attempt|idea|suggestion)\b",
            r"\bno longer (uses|using|relies|relying|calls|depends)\b",
        ],
    ),
    (
        "chat-reference",
        "points at a conversation the reader was not part of",
        [
            r"\bas (we )?discussed\b",
            r"\bas (you )?(requested|asked|suggested|mentioned|wanted|noted|pointed out)\b",
            r"\bper (your|the|our) (feedback|request|review|discussion|conversation|comment|suggestion)\b",
            r"\b(based on|after|following|addressing|incorporating|address|addresses) (your|the|reviewer'?s?|review) (feedback|review|comments?|suggestions?)\b",
            r"\byou (asked|said|mentioned|wanted|suggested|pointed out|requested)\b",
            r"\bthis time\b",
            r"\bnow (correctly|properly|actually|really|finally)\b",
            r"\bshould (now )?(work|be fixed|be correct) now\b",
        ],
    ),
    (
        "revision-marker",
        "labels the artifact as a redo of something the reader never saw",
        [
            r"\b(updated|fixed|corrected|revised|new|final|clean|proper|improved|better) (version|attempt|take|draft|pass)\b",
            r"\(\s*(fixed|updated|corrected|revised|final|v\d+|take ?\d+|attempt ?\d+)\s*\)",
            r"\b(second|third|another|new) (attempt|try|pass|go)\b",
            r"\btake ?\d\b",
            r"\bv\d+ of the\b",
            r"\bre-?(did|done|doing|written|wrote|worked) (the|this|it)\b",
        ],
    ),
    (
        "apology-or-history",
        "narrates earlier mistakes instead of describing what ships",
        [
            r"\b(sorry|oops|apologies|my (mistake|bad|error))\b",
            r"\b(previously|earlier|initially|originally|at first|before),? (i|we|it|this|the code)\b",
            r"\b(the )?(first|previous|earlier|original|initial|last) (draft|attempt|version|implementation|approach|pass)\b",
            r"\bi (had|have) (previously|earlier|initially|mistakenly|wrongly|accidentally)\b",
            r"\b(mistakenly|wrongly|accidentally|erroneously) (added|used|included|wrote|put)\b",
            r"\b(turns out|it turned out)\b",
        ],
    ),
    (
        "self-reference",
        "narrates the rule it is following; the reader does not care which skill wrote this",
        [
            r"\bship-the-result\b",
            r"\b(follow(ing|s|ed)?|per|apply(ing)?|according to|as per|under) (the|this|my|our)? ?(\w+[\-\w]* )?(rule|skill|guideline|policy|convention|instruction)s?\b",
            r"\b(i|we) (will|'ll|am going to|'m going to) (only|just)? ?(write|include|keep|describe|mention)\b",
            r"\b(only|just) (the )?(final(ly)?|adopted|accepted|chosen) (result|version|approach|solution|design)\b",
            r"\b(not|without) (leav|keep|includ|mention|carry)\w* (the )?(rejected|discarded|abandoned|dropped|earlier|previous) \w+",
        ],
    ),
    (
        "identifier-residue",
        "bakes a draft's history into a name that will outlive it",
        [
            r"(?i)(^|[_\-\s.])(v\d+|fixed|final|new|old|updated|corrected|revised|clean|real|actual|good|working)(?=[_\-\s.]|$)",
            r"(?i)(^|[_\-\s.])(no|without|sans)[_\-]\w+",
            r"(?i)(^|[_\-\s.])(with)?out[_\-]\w+",
            r"(?i)_?(instead|not)_of_\w+",
        ],
    ),
]

KIND_FAMILIES = {
    "message": {"negated-draft", "chat-reference", "revision-marker", "apology-or-history", "self-reference"},
    "comment": {"negated-draft", "chat-reference", "revision-marker", "apology-or-history", "self-reference"},
    "name": {"identifier-residue", "negated-draft"},
}


def _strip_leading_iflag(pat: str) -> str:
    """Remove a leading inline global flag so patterns can be joined.

    Python 3.11+ raises re.error for a global inline flag (e.g. ``(?i)``) that is
    not at the very start of the expression, which happens once alternatives are
    joined with ``|``. Case-insensitivity is reapplied via re.IGNORECASE on the
    combined pattern, so stripping the leading flag is safe. A slice is used (not
    str.replace) so an occurrence elsewhere in the pattern is left untouched.
    """
    return pat[4:] if pat.startswith("(?i)") else pat


# One compiled regex per family: alternatives are joined so each family costs a
# single search() per line instead of one per raw pattern.
_COMPILED = [
    (fid, why, re.compile("|".join("(?:%s)" % _strip_leading_iflag(p) for p in pats), re.IGNORECASE))
    for fid, why, pats in FAMILIES
]

# Lines longer than this are scanned only up to the cap. Outward-facing prose is
# short; the cap bounds worst-case regex cost on a pathological single line.
_MAX_LINE = 8192


# --------------------------------------------------------------------------- #
# Path-safety guard (shared with the PreToolUse hook)
# --------------------------------------------------------------------------- #
_HOME = os.path.realpath(os.path.expanduser("~"))

# Directory names that make any file beneath them off-limits, at any depth.
# Kept to well-known secret stores; ~/.config is deliberately NOT blocked
# wholesale (it holds gh, git, nvim config), the secret-name rule covers the
# secrets that actually live there.
_SENSITIVE_DIR_NAMES = frozenset({
    ".ssh", ".aws", ".kube", ".gnupg", ".dotfiles", ".docker",
    ".claude", ".gcloud", ".azure", ".oci", ".password-store",
})

# Absolute locations that are never legitimate to scan.
_SENSITIVE_ABS_PREFIXES = ("/etc", "/private/etc", "/root", "/var/root", "/var/db")

# Filenames that look like secrets, wherever they sit.
_SENSITIVE_NAME_RE = re.compile(
    r"^(?:"
    r"\.env(?:\..+)?"
    r"|\.netrc|\.pgpass|\.htpasswd|\.npmrc|\.pypirc"
    r"|credentials(?:\..+)?"
    r"|id_(?:rsa|dsa|ecdsa|ed25519)(?:\.pub)?"
    r"|.+\.(?:pem|key|p12|pfx|asc|gpg|keychain|keychain-db)"
    r")$",
    re.IGNORECASE,
)

# Never slurp more than this from a referenced file.
_MAX_READ_BYTES = 512 * 1024


def _candidates(raw: str) -> tuple[str, ...]:
    """Expand ~ and $VARS, absolutize, and resolve symlinks.

    Returns the plain absolute path and (when different) the symlink-resolved
    real path, so a symlink pointing into a sensitive location is still caught.
    realpath may raise under a sandbox for a denied component; that is tolerated
    and the string form is used, which the name/location rules still catch.
    """
    expanded = os.path.expandvars(os.path.expanduser(str(raw)))
    abs_expanded = os.path.abspath(expanded)
    try:
        real = os.path.realpath(abs_expanded)
    except OSError:
        real = abs_expanded
    return (abs_expanded,) if abs_expanded == real else (abs_expanded, real)


def _blocked_reason(raw: str) -> str | None:
    """Return why a path is off-limits, or None if it may be read.

    Pure string logic only: no filesystem access, so a sensitive path is
    rejected without ever being opened or stat-ed.
    """
    home = Path(_HOME)
    for cand in _candidates(raw):
        p = Path(cand)
        if p.parent == home:
            return "sits directly in the home directory"
        for comp in p.parts:
            if comp in _SENSITIVE_DIR_NAMES:
                return f"inside a sensitive directory ({comp})"
        for pref in _SENSITIVE_ABS_PREFIXES:
            if cand == pref or cand.startswith(pref + os.sep):
                return f"under a protected system location ({pref})"
        if _SENSITIVE_NAME_RE.match(p.name):
            return f"filename looks sensitive ({p.name})"
    return None


def safe_read_text(raw: str, max_bytes: int = _MAX_READ_BYTES) -> tuple[str | None, str | None]:
    """Read a file only if it clears the guard. Returns (text, error).

    On success -> (contents, None). On refusal or failure -> (None, reason).
    The name/location checks run before any filesystem call, so sensitive paths
    are never touched.
    """
    reason = _blocked_reason(raw)
    if reason:
        return None, f"refused to read {raw!r}: {reason}"
    target = _candidates(raw)[-1]  # symlink-resolved form when available
    try:
        st = os.stat(target)
    except OSError as exc:
        return None, f"cannot read {raw!r}: {type(exc).__name__}"
    if not statmod.S_ISREG(st.st_mode):
        return None, f"refused to read {raw!r}: not a regular file"
    if st.st_size > max_bytes:
        return None, f"refused to read {raw!r}: too large ({st.st_size} bytes > {max_bytes})"
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(max_bytes), None
    except OSError as exc:
        return None, f"cannot read {raw!r}: {type(exc).__name__}"


# --------------------------------------------------------------------------- #
# Scanning
# --------------------------------------------------------------------------- #
@dataclass
class Finding:
    line_no: int
    line: str
    match: str
    family: str
    why: str


def scan_text(text: str, kind: str = "message") -> list[Finding]:
    allowed = KIND_FAMILIES.get(kind, KIND_FAMILIES["message"])
    findings: list[Finding] = []
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) > _MAX_LINE:
            stripped = stripped[:_MAX_LINE]
        for fid, why, rx in _COMPILED:
            if fid not in allowed:
                continue
            m = rx.search(stripped)  # one hit per family per line is enough
            if m:
                findings.append(Finding(i, stripped, m.group(0).strip(" _-."), fid, why))
    return findings


def format_findings(findings: list[Finding], source: str = "") -> str:
    head = f"residue found in {source}:" if source else "residue found:"
    out = [head]
    for f in findings:
        out.append(f"  L{f.line_no}: {f.line}")
        out.append(f"      -> \"{f.match}\" [{f.family}] {f.why}")
    out.append("")
    out.append(
        "Rewrite from the final result and the original requirement only. "
        "Describe what the artifact is, not how the conversation got here. "
        "If a flagged phrase is a genuine requirement (e.g. the feature really is "
        "'login without password'), keep it and re-run the same command unchanged to confirm."
    )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="files to scan; reads stdin when omitted")
    ap.add_argument("--kind", choices=sorted(KIND_FAMILIES), default="message")
    ap.add_argument("--json", action="store_true", help="emit findings as JSON")
    args = ap.parse_args(argv)

    sources: list[tuple[str, str]] = []
    if args.files:
        for path in args.files:
            text, err = safe_read_text(path)
            if err:
                print(err, file=sys.stderr)
                continue
            sources.append((path, text if text is not None else ""))
    else:
        sources.append(("stdin", sys.stdin.read()))

    all_findings: dict[str, list[Finding]] = {}
    for name, text in sources:
        found = scan_text(text, args.kind)
        if found:
            all_findings[name] = found

    if args.json:
        print(json.dumps({k: [asdict(f) for f in v] for k, v in all_findings.items()}, indent=2))
    else:
        for name, found in all_findings.items():
            print(format_findings(found, name))
    return 1 if all_findings else 0


if __name__ == "__main__":
    sys.exit(main())
