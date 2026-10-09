#!/usr/bin/env python3
"""Tests for new_doc: create a kb document from a title.

Run from the kb-utilities directory:

    python3 tests/test_new_doc.py -v

or from the dotfiles repository root:

    python3 .local/bin/kb-utilities/tests/test_new_doc.py -v

The contract pinned here (naming via kb_common, git fields via git_fields,
stdlib only):

create_document(title, tags=None, directory=None, repo=None, commit=None,
last_validated=None) -> Path
    Creates <directory>/<normalize_filename(title)>.md (directory defaults
    to the current directory) and returns the created Path. The frontmatter
    carries the T01 fields: createdate as a local ISO-8601 timestamp with
    second precision and a numeric UTC offset, title equal to
    normalize_title(title), and a canonical tags block (``tags: []`` when
    no tags are given). When repo is given, the git fields derived by
    git_fields.derive_git_fields(repo, commit, last_validated) are added,
    so credentials stored in a remote URL never reach the document. An
    existing target file is never overwritten: the colliding document gets
    a numeric collision suffix (``-2``, then ``-3``, ...) appended through
    kb_common.normalize_filename.

Command line
    python3 new_doc.py TITLE [--tags A,B] [--dir DIR] [--repo PATH]
        [--commit SHA] [--last-validated YYYY-MM-DD]
    creates the document and exits 0.

Every expected value below is hand-computed from this contract, not
generated from an implementation. The git fixture is a throwaway
repository created with ``git init`` in a temporary directory through
subprocess, isolated from the user's git configuration.
"""

import ast
import datetime
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import git_fields
import kb_common
import new_doc

CREATEDATE_RE = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$"
SOURCE_COMMIT_RE = r"^[0-9a-f]{40}$"

CRED_URL = "https://user:ghp_newdoctoken@github.com/example/repo.git"
CRED_URL_CLEAN = "https://github.com/example/repo.git"
TOKEN = "ghp_newdoctoken"

TITLE = "Don't Stop -- Pre-commit!"
STEM = "dont-stop-pre-commit"
NORMALIZED_TITLE = "dont stop pre commit"


def collect_top_level_imports(path: Path) -> set[str]:
    """Return the top-level module names imported by a Python source file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])
    return modules


# Isolated git configuration: the fixture must not depend on, or write to,
# the user's global or system git configuration.
GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")


def make_repo(root: Path) -> tuple[Path, str]:
    """Create a throwaway repository at root/repo with one HTTPS remote."""
    repo = root / "repo"
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repo)],
        capture_output=True, text=True, env=GIT_ENV, check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", CRED_URL],
        capture_output=True, text=True, env=GIT_ENV, check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo),
         "-c", "user.name=kb-test", "-c", "user.email=kb-test@example.com",
         "-c", "commit.gpgsign=false",
         "commit", "--allow-empty", "-q", "-m", "init"],
        capture_output=True, text=True, env=GIT_ENV, check=True,
    )
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, env=GIT_ENV, check=True,
    ).stdout.strip()
    return repo, sha


class TestCreateDocument(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def test_filename_is_normalized_title_with_md_suffix(self):
        path = new_doc.create_document(TITLE, directory=self.tmp)
        self.assertEqual(path, self.tmp / f"{STEM}.md")
        self.assertTrue(path.is_file())

    def test_title_field_equals_normalize_title(self):
        path = new_doc.create_document(TITLE, directory=self.tmp)
        fields, _, _, _ = kb_common.parse_frontmatter(
            path.read_text(encoding="utf-8")
        )
        self.assertEqual(fields["title"], NORMALIZED_TITLE)
        self.assertEqual(fields["title"], kb_common.normalize_title(TITLE))

    def test_createdate_is_local_iso_timestamp_with_offset(self):
        path = new_doc.create_document(TITLE, directory=self.tmp)
        fields, _, _, _ = kb_common.parse_frontmatter(
            path.read_text(encoding="utf-8")
        )
        self.assertRegex(fields["createdate"], CREATEDATE_RE)

    def test_tags_round_trip(self):
        path = new_doc.create_document(
            "Docker Networking Basics",
            tags=["docker", "networking"],
            directory=self.tmp,
        )
        _, tags, _, _ = kb_common.parse_frontmatter(
            path.read_text(encoding="utf-8")
        )
        self.assertEqual(tags, ["docker", "networking"])

    def test_without_tags_the_tags_block_is_empty(self):
        path = new_doc.create_document(TITLE, directory=self.tmp)
        _, tags, _, _ = kb_common.parse_frontmatter(
            path.read_text(encoding="utf-8")
        )
        self.assertEqual(tags, [])

    def test_collision_gets_numeric_suffix_and_keeps_the_first_file(self):
        first = new_doc.create_document(TITLE, directory=self.tmp)
        first_text = first.read_text(encoding="utf-8")
        second = new_doc.create_document(TITLE, directory=self.tmp)
        self.assertEqual(second, self.tmp / f"{STEM}-2.md")
        self.assertTrue(second.is_file())
        self.assertEqual(first.read_text(encoding="utf-8"), first_text)

    def test_repo_adds_git_fields_and_strips_credentials(self):
        repo, sha = make_repo(self.tmp)
        path = new_doc.create_document(
            "Docker Networking Basics", repo=repo, directory=self.tmp
        )
        fields, _, _, _ = kb_common.parse_frontmatter(
            path.read_text(encoding="utf-8")
        )
        self.assertEqual(fields["git_repo"], CRED_URL_CLEAN)
        self.assertEqual(fields["source_commit"], sha)
        self.assertRegex(fields["source_commit"], SOURCE_COMMIT_RE)
        self.assertEqual(fields["last_validated"], datetime.date.today().isoformat())
        # The token never reaches the document.
        self.assertNotIn(TOKEN, path.read_text(encoding="utf-8"))

    def test_returns_a_path(self):
        path = new_doc.create_document(TITLE, directory=self.tmp)
        self.assertIsInstance(path, Path)


class TestNewDocCli(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.script = Path(__file__).resolve().parents[1] / "new_doc.py"

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.script), *args],
            capture_output=True, text=True,
        )

    def test_cli_creates_the_document(self):
        proc = self.run_cli("Kubernetes Rolling Restarts", "--dir", str(self.tmp))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((self.tmp / "kubernetes-rolling-restarts.md").is_file())

    def test_cli_tags_flag_is_comma_separated(self):
        proc = self.run_cli(
            "Kubernetes Rolling Restarts",
            "--tags", "kubernetes,rollouts",
            "--dir", str(self.tmp),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        _, tags, _, _ = kb_common.parse_frontmatter(
            (self.tmp / "kubernetes-rolling-restarts.md").read_text(encoding="utf-8")
        )
        self.assertEqual(tags, ["kubernetes", "rollouts"])


class TestStdlibOnly(unittest.TestCase):
    def test_new_doc_and_this_test_import_stdlib_only(self):
        allowed = set(sys.stdlib_module_names)
        local = {"kb_common", "git_fields", "new_doc"}
        sources = [
            Path(__file__),
            Path(__file__).resolve().parents[1] / "new_doc.py",
            Path(__file__).resolve().parents[1] / "git_fields.py",
        ]
        for source in sources:
            with self.subTest(source=source.name):
                modules = collect_top_level_imports(source) - local
                self.assertEqual(
                    modules - allowed,
                    set(),
                    f"{source.name} imports non-stdlib modules: "
                    f"{sorted(modules - allowed)}",
                )


if __name__ == "__main__":
    unittest.main()
