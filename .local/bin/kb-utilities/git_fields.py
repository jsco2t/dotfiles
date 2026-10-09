#!/usr/bin/env python3
"""Git provenance frontmatter for kb documents: derive, normalize, update.

Remote URLs
-----------

``normalize_remote_url`` maps a git remote URL to the HTTPS URL recorded in
the ``git_repo`` frontmatter field. An http(s) URL keeps its scheme, host
and path but loses any userinfo (``user:token@`` or ``token@``), so
credentials never survive into a document. An scp-like ``git@host:path``
URL or an ``ssh://git@host/path`` URL becomes ``https://host/path.git``
(``.git`` appended when the path lacks it). A URL that cannot become an
HTTPS URL (a local path, ``file://``) returns None.

Derivation
----------

``derive_git_fields`` returns a subset of the three git frontmatter fields
for a repository. ``source_commit`` is the full 40-hex sha of HEAD, or of
an explicit commit (a short sha resolves to its full sha; an unresolvable
commit raises ValueError); a repository without commits omits the field.
``last_validated`` is an explicit YYYY-MM-DD date used as-is, or today's
local date. ``git_repo`` is the first remote in git's listing order whose
URL normalizes via ``normalize_remote_url``; a repository without a
qualifying remote omits the field.

Updating documents
------------------

``update_git_fields`` rewrites exactly the given git frontmatter fields in
a markdown document: an existing field is rewritten in place, new fields
are appended after the existing ones (before the tags block), and a
document without frontmatter gains a frontmatter block. Every other field,
the tags block and the body are preserved verbatim. A key outside the
three git fields raises ValueError. The rewritten text is written back to
the file and returned.

Git is consulted through ``git`` subprocess calls; only the Python
standard library is used.
"""

import datetime
import re
import subprocess
import urllib.parse
from pathlib import Path

import kb_common


# ── Git frontmatter fields ─────────────────────────────────────────────────

# The only frontmatter keys update_git_fields may touch.
GIT_FIELD_KEYS = ("source_commit", "last_validated", "git_repo")

# last_validated is a bare calendar date.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# scp-like remote: [user@]host:path with a slashful path, as in
# git@github.com:example/repo.git (git's scp syntax never uses //).
_SCP_LIKE_RE = re.compile(r"^[^/@]+@([^/:]+):(.+)$")

# A tags block start inside frontmatter: "tags:", "tags: [..]", "tags: value".
_TAGS_LINE_RE = re.compile(r"^tags:(?:\s|\[|$)")


# ── Remote URL normalization ────────────────────────────────────────────────

def normalize_remote_url(url: str) -> str | None:
    """Map a git remote URL to the HTTPS URL for the git_repo field.

    Userinfo is always stripped, so credentials never survive. http(s)
    URLs keep scheme, host and path; scp-like and ssh:// URLs become
    https://host/path.git. Returns None for URLs that cannot become an
    HTTPS URL (a local path, file://, unknown schemes).
    """
    url = url.strip()
    if not url:
        return None

    if "://" in url:
        parts = urllib.parse.urlsplit(url)
        # rpartition keeps the host[:port] after the last "@", dropping any
        # user:token@ or token@ userinfo.
        host = parts.netloc.rpartition("@")[2]
        if not host:
            return None
        scheme = parts.scheme.lower()
        if scheme in ("http", "https"):
            return f"{scheme}://{host}{parts.path}"
        if scheme == "ssh":
            path = parts.path
            if path and not path.endswith(".git"):
                path += ".git"
            return f"https://{host}{path}"
        return None

    scp = _SCP_LIKE_RE.match(url)
    if scp:
        host, path = scp.group(1), scp.group(2)
        if not path.endswith(".git"):
            path += ".git"
        return f"https://{host}/{path}"
    return None


# ── Git consultation ────────────────────────────────────────────────────────

def _run_git(repo_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run one git command against repo_path and return the raw result."""
    return subprocess.run(
        ["git", "-C", str(repo_path), *args], capture_output=True, text=True
    )


def _require_repository(repo_path: Path) -> None:
    """Raise ValueError when repo_path is not a git repository."""
    proc = _run_git(repo_path, "rev-parse", "--git-dir")
    if proc.returncode != 0:
        raise ValueError(f"not a git repository: {repo_path}")


def _resolve_commit(repo_path: Path, commit: str | None) -> str | None:
    """Return the full 40-hex sha of commit (or HEAD when commit is None).

    An explicit commit that does not resolve raises ValueError; a HEAD
    that does not resolve (a repository without commits) returns None.
    """
    rev = commit if commit is not None else "HEAD"
    # "^{commit}" peels any object kind down to a commit and rejects
    # non-commit objects; --quiet only silences the error message.
    proc = _run_git(repo_path, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    sha = proc.stdout.strip()
    if proc.returncode != 0 or not sha:
        if commit is not None:
            raise ValueError(f"commit does not resolve in {repo_path}: {commit}")
        return None
    return sha


def _validated_last_validated(last_validated: str | None) -> str:
    """Return last_validated as-is, or today's local date when None.

    A value that is not a YYYY-MM-DD date raises ValueError.
    """
    if last_validated is None:
        return datetime.date.today().isoformat()
    value = last_validated.strip()
    if not _DATE_RE.match(value):
        raise ValueError(f"last_validated must be YYYY-MM-DD: {last_validated!r}")
    # Rejects impossible dates such as 2026-02-30 with a ValueError.
    datetime.date.fromisoformat(value)
    return value


def _first_remote_url(repo_path: Path) -> str | None:
    """Return the first remote URL (git's listing order) that normalizes."""
    proc = _run_git(repo_path, "remote")
    for name in proc.stdout.split():
        url_proc = _run_git(repo_path, "remote", "get-url", name)
        normalized = normalize_remote_url(url_proc.stdout)
        if normalized:
            return normalized
    return None


def derive_git_fields(
    repo_path: str | Path,
    commit: str | None = None,
    last_validated: str | None = None,
) -> dict[str, str]:
    """Derive the git provenance frontmatter fields for a repository.

    Returns a subset of source_commit, last_validated and git_repo (see
    the module docstring). Raises ValueError when repo_path is not a git
    repository, when an explicit commit does not resolve, or when
    last_validated is not a YYYY-MM-DD date.
    """
    repo_path = Path(repo_path)
    _require_repository(repo_path)

    fields: dict[str, str] = {}
    sha = _resolve_commit(repo_path, commit)
    if sha:
        fields["source_commit"] = sha
    fields["last_validated"] = _validated_last_validated(last_validated)
    git_repo = _first_remote_url(repo_path)
    if git_repo:
        fields["git_repo"] = git_repo
    return fields


# ── Document updates ────────────────────────────────────────────────────────

def _render_with_git_fields(content: str, fields: dict[str, str]) -> str:
    """Return content with exactly the given git fields rendered in.

    Existing git fields are rewritten in place; new ones are inserted
    after the existing fields and before the tags block; content without
    frontmatter gains a block built by kb_common.serialize_frontmatter.
    """
    lines = content.split("\n")
    close_idx = None
    if lines and lines[0].strip() == "---":
        close_idx = next(
            (i for i in range(1, len(lines)) if lines[i].strip() == "---"), None
        )
    if close_idx is None:
        return kb_common.serialize_frontmatter(dict(fields), [], content)

    inner = lines[1:close_idx]
    body = "\n".join(lines[close_idx + 1 :])

    appended: list[str] = []
    for key, value in fields.items():
        # A field line is unindented and starts with "key:"; values may
        # contain colons, so the key match must anchor at the line start.
        key_re = re.compile(r"^" + re.escape(key) + r":")
        at = next((i for i, line in enumerate(inner) if key_re.match(line)), None)
        if at is None:
            appended.append(f"{key}: {value}")
        else:
            inner[at] = f"{key}: {value}"

    if appended:
        at = next(
            (i for i, line in enumerate(inner) if _TAGS_LINE_RE.match(line)),
            len(inner),
        )
        inner[at:at] = appended

    return "\n".join(["---", *inner, "---"]) + "\n" + body


def update_git_fields(path: str | Path, fields: dict[str, str]) -> str:
    """Update exactly the given git frontmatter fields in the document.

    Every key in fields must be one of GIT_FIELD_KEYS; anything else
    raises ValueError before the file is touched. The rewritten text is
    written back to path and returned.
    """
    unknown = sorted(key for key in fields if key not in GIT_FIELD_KEYS)
    if unknown:
        raise ValueError(f"not git frontmatter fields: {', '.join(unknown)}")

    path = Path(path)
    text = _render_with_git_fields(path.read_text(encoding="utf-8"), fields)
    path.write_text(text, encoding="utf-8")
    return text
