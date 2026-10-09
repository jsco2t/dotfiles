#!/usr/bin/env python3
"""Create a kb document from a title.

Creation
--------

``create_document(title, tags=None, directory=None, repo=None, commit=None,
last_validated=None)`` creates ``<directory>/<normalize_filename(title)>.md``
(directory defaults to the current directory) and returns the created
``Path``. The frontmatter carries the kb_common fields: ``createdate`` as
a local ISO-8601 timestamp with second precision and a numeric UTC offset,
``title`` equal to ``normalize_title(title)``, and a canonical tags block
(``tags: []`` when no tags are given). When repo is given, the git fields
derived by ``git_fields.derive_git_fields(repo, commit, last_validated)``
are added, so credentials stored in a remote URL never reach the document.
An existing target file is never overwritten: the colliding document gets
a numeric collision suffix (``-2``, then ``-3``, ...) appended through
``kb_common.normalize_filename``.

Command line
------------

python3 new_doc.py TITLE [--tags A,B] [--dir DIR] [--repo PATH]
    [--commit SHA] [--last-validated YYYY-MM-DD]

creates the document, prints its path, and exits 0; a bad title, an
unusable repository, or an unwritable directory prints the error to
stderr and exits 1. Only the Python standard library is used.
"""

import argparse
import datetime
import sys
from pathlib import Path

import git_fields
import kb_common


# ── Creation ────────────────────────────────────────────────────────────────

def _createdate() -> str:
    """Local ISO-8601 timestamp with second precision and a UTC offset."""
    return (
        datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()
    )


def _target_path(title: str, directory: Path) -> Path:
    """Return the first free path for title's normalized filename.

    A path that already exists is never reused: the collision gets a
    numeric suffix -2, -3, ... appended through kb_common.normalize_filename,
    which keeps the whole stem within MAX_FILENAME_LEN.
    """
    stem = kb_common.normalize_filename(title)
    if not stem:
        raise ValueError(f"title has no nameable characters: {title!r}")
    path = directory / f"{stem}.md"
    collision = 1
    while path.exists():
        collision += 1
        path = directory / f"{kb_common.normalize_filename(title, str(collision))}.md"
    return path


def create_document(
    title: str,
    tags: list[str] | None = None,
    directory: str | Path | None = None,
    repo: str | Path | None = None,
    commit: str | None = None,
    last_validated: str | None = None,
) -> Path:
    """Create a kb document from a title and return its Path.

    The frontmatter carries createdate, title and a canonical tags block;
    when repo is given the git provenance fields from
    git_fields.derive_git_fields are added. Raises ValueError for a title
    with no nameable characters or for unusable git inputs (see
    git_fields.derive_git_fields).
    """
    directory = Path(directory) if directory is not None else Path.cwd()
    fields = {
        "createdate": _createdate(),
        "title": kb_common.normalize_title(title),
    }
    if repo is not None:
        fields.update(
            git_fields.derive_git_fields(
                repo, commit=commit, last_validated=last_validated
            )
        )

    path = _target_path(title, directory)
    path.write_text(
        kb_common.serialize_frontmatter(fields, list(tags) if tags else [], ""),
        encoding="utf-8",
    )
    return path


# ── Command line ────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """Create one document from the command line arguments."""
    parser = argparse.ArgumentParser(
        description="Create a kb document from a title."
    )
    parser.add_argument("title", help="document title; the filename derives from it")
    parser.add_argument(
        "--tags", default="", help="comma-separated tags for the document"
    )
    parser.add_argument(
        "--dir", type=Path, default=None,
        help="directory to create the document in (default: current directory)",
    )
    parser.add_argument(
        "--repo", type=Path, default=None,
        help="git repository to derive source_commit, last_validated and "
             "git_repo from",
    )
    parser.add_argument("--commit", default=None, help="commit sha for source_commit")
    parser.add_argument(
        "--last-validated", dest="last_validated", default=None,
        help="validation date as YYYY-MM-DD (default: today)",
    )
    args = parser.parse_args(argv)

    tags = [tag.strip() for tag in args.tags.split(",") if tag.strip()]
    try:
        path = create_document(
            args.title,
            tags=tags,
            directory=args.dir,
            repo=args.repo,
            commit=args.commit,
            last_validated=args.last_validated,
        )
    except (ValueError, OSError) as err:
        parser.exit(1, f"new_doc: {err}\n")
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
