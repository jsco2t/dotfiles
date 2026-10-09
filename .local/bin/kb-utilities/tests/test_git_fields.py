#!/usr/bin/env python3
"""Tests for git_fields: git provenance frontmatter derived from a repository
and written into a document.

Run from the kb-utilities directory:

    python3 tests/test_git_fields.py -v

or from the dotfiles repository root:

    python3 .local/bin/kb-utilities/tests/test_git_fields.py -v

The contract pinned here (stdlib only; git is consulted through subprocess):

normalize_remote_url(url) -> str | None
    Maps a git remote URL to the HTTPS URL recorded in git_repo. An
    http(s) URL keeps its scheme, host and path but loses any userinfo
    (``user:token@`` or ``token@``), so credentials never survive. An
    scp-like ``git@host:path`` URL or an ``ssh://git@host/path`` URL
    becomes ``https://host/path.git`` (``.git`` appended when the path
    lacks it). A URL that cannot become an HTTPS URL (a local path,
    ``file://``) returns None.

derive_git_fields(repo_path, commit=None, last_validated=None) -> dict
    Returns a subset of the three git frontmatter fields (source_commit,
    last_validated, git_repo) for the repository at repo_path.
    source_commit is the full 40-hex sha of HEAD, or of the explicit
    commit when one is given; a short sha resolves to its full sha and an
    unresolvable commit raises ValueError; a repository without commits
    omits the field. last_validated is the explicit date used as-is, or
    today's local date; a value that is not a YYYY-MM-DD date raises
    ValueError. git_repo is the first remote in git's listing order whose
    URL normalizes via normalize_remote_url; a repository without a
    qualifying remote omits the field.

update_git_fields(path, fields) -> str
    Updates exactly the given git frontmatter fields in the markdown
    document at path: an existing field is rewritten in place, new fields
    are appended after the existing ones (before the tags block), and a
    document without frontmatter gains a frontmatter block. Every other
    field, the tags block and the body are preserved verbatim. A key
    outside the three git fields raises ValueError. Returns the rewritten
    document text.

Every expected value below is hand-computed from this contract, not
generated from an implementation. The git fixtures are throwaway
repositories created with ``git init`` in a temporary directory through
subprocess, isolated from the user's git configuration.
"""

import ast
import datetime
import os
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import git_fields
import kb_common

SOURCE_COMMIT_RE = r"^[0-9a-f]{40}$"
LAST_VALIDATED_RE = r"^\d{4}-\d{2}-\d{2}$"

CRED_URL = "https://user:ghp_testtoken123@github.com/example/repo.git"
CRED_URL_CLEAN = "https://github.com/example/repo.git"
TOKEN = "ghp_testtoken123"

# A frontmatter document in the current convention, used by the update tests.
DOC = (
    "---\n"
    "createdate: 2026-10-09T10:00:00-07:00\n"
    "title: Docker Networking Basics\n"
    "tags:\n"
    "  - docker\n"
    "---\n"
    "\n"
    "Body line.\n"
    "\n"
    "More body.\n"
)

# A document that already carries git provenance, used by the subset test.
PROVENANCED_DOC = (
    "---\n"
    "title: Existing Notes\n"
    f"source_commit: {'1' * 40}\n"
    "last_validated: 2020-01-01\n"
    "---\n"
    "Body.\n"
)


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


# Isolated git configuration: the fixtures must not depend on, or write to,
# the user's global or system git configuration.
GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")


def run_git(repo: Path | None, *args: str) -> str:
    """Run one git command against repo (or without -C) and return stdout."""
    cmd = ["git"]
    if repo is not None:
        cmd += ["-C", str(repo)]
    cmd += list(args)
    proc = subprocess.run(cmd, capture_output=True, text=True, env=GIT_ENV)
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def make_repo(
    root: Path, remotes: Sequence[tuple[str, str]] = (), with_commit: bool = True
) -> tuple[Path, str | None]:
    """Create a throwaway repository at root/repo and return (repo, head sha).

    Each (name, url) pair in remotes is registered with git remote add. With
    with_commit the repository gets one empty commit so HEAD resolves.
    """
    repo = root / "repo"
    run_git(None, "init", "-q", "-b", "main", str(repo))
    for name, url in remotes:
        run_git(repo, "remote", "add", name, url)
    sha = None
    if with_commit:
        run_git(
            repo,
            "-c", "user.name=kb-test",
            "-c", "user.email=kb-test@example.com",
            "-c", "commit.gpgsign=false",
            "commit", "--allow-empty", "-q", "-m", "init",
        )
        sha = run_git(repo, "rev-parse", "HEAD")
    return repo, sha


class TestNormalizeRemoteUrl(unittest.TestCase):
    def test_https_userinfo_user_token_is_stripped(self):
        self.assertEqual(git_fields.normalize_remote_url(CRED_URL), CRED_URL_CLEAN)

    def test_https_token_only_userinfo_is_stripped(self):
        url = "https://ghp_testtoken123@github.com/example/repo.git"
        self.assertEqual(git_fields.normalize_remote_url(url), CRED_URL_CLEAN)

    def test_https_without_userinfo_is_unchanged(self):
        self.assertEqual(
            git_fields.normalize_remote_url(CRED_URL_CLEAN), CRED_URL_CLEAN
        )

    def test_scp_like_remote_with_git_suffix_converts(self):
        self.assertEqual(
            git_fields.normalize_remote_url("git@github.com:example/repo.git"),
            "https://github.com/example/repo.git",
        )

    def test_scp_like_remote_without_git_suffix_gets_git_appended(self):
        self.assertEqual(
            git_fields.normalize_remote_url("git@github.com:example/repo"),
            "https://github.com/example/repo.git",
        )

    def test_ssh_url_converts(self):
        self.assertEqual(
            git_fields.normalize_remote_url("ssh://git@github.com/example/repo.git"),
            "https://github.com/example/repo.git",
        )

    def test_local_path_is_not_convertible(self):
        self.assertIsNone(git_fields.normalize_remote_url("/srv/git/repo"))

    def test_file_url_is_not_convertible(self):
        self.assertIsNone(git_fields.normalize_remote_url("file:///srv/git/repo"))


class TestDeriveGitFields(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def test_https_remote_yields_git_repo_with_credentials_removed(self):
        repo, _ = make_repo(self.tmp, [("origin", CRED_URL)])
        fields = git_fields.derive_git_fields(repo)
        self.assertEqual(fields["git_repo"], CRED_URL_CLEAN)
        # The token never appears anywhere in the derived fields.
        self.assertNotIn(TOKEN, repr(fields))

    def test_ssh_remote_converts_to_https(self):
        repo, _ = make_repo(self.tmp, [("origin", "git@github.com:example/repo.git")])
        fields = git_fields.derive_git_fields(repo)
        self.assertEqual(fields["git_repo"], "https://github.com/example/repo.git")

    def test_first_normalizable_remote_wins(self):
        # "aaa" points at a local path (not convertible), "zzz" at HTTPS with
        # credentials; the HTTPS remote is the source of git_repo, stripped.
        repo, _ = make_repo(
            self.tmp,
            [
                ("aaa", str(self.tmp / "somewhere-local")),
                ("zzz", "https://user:ghp_pickme@github.com/example/picked.git"),
            ],
        )
        fields = git_fields.derive_git_fields(repo)
        self.assertEqual(fields["git_repo"], "https://github.com/example/picked.git")
        self.assertNotIn("ghp_pickme", repr(fields))

    def test_source_commit_defaults_to_head_full_sha(self):
        repo, sha = make_repo(self.tmp)
        fields = git_fields.derive_git_fields(repo)
        self.assertEqual(fields["source_commit"], sha)
        self.assertRegex(fields["source_commit"], SOURCE_COMMIT_RE)

    def test_explicit_full_commit_is_used(self):
        repo, sha = make_repo(self.tmp)
        fields = git_fields.derive_git_fields(repo, commit=sha)
        self.assertEqual(fields["source_commit"], sha)

    def test_explicit_short_commit_resolves_to_full_sha(self):
        repo, sha = make_repo(self.tmp)
        fields = git_fields.derive_git_fields(repo, commit=sha[:8])
        self.assertEqual(fields["source_commit"], sha)

    def test_unresolvable_commit_raises_value_error(self):
        repo, _ = make_repo(self.tmp)
        with self.assertRaises(ValueError):
            git_fields.derive_git_fields(repo, commit="not-a-sha")

    def test_last_validated_defaults_to_today(self):
        repo, _ = make_repo(self.tmp)
        fields = git_fields.derive_git_fields(repo)
        self.assertEqual(fields["last_validated"], datetime.date.today().isoformat())
        self.assertRegex(fields["last_validated"], LAST_VALIDATED_RE)

    def test_explicit_last_validated_is_used_as_is(self):
        repo, _ = make_repo(self.tmp)
        fields = git_fields.derive_git_fields(repo, last_validated="2026-01-15")
        self.assertEqual(fields["last_validated"], "2026-01-15")

    def test_invalid_last_validated_raises_value_error(self):
        repo, _ = make_repo(self.tmp)
        with self.assertRaises(ValueError):
            git_fields.derive_git_fields(repo, last_validated="not-a-date")

    def test_repo_without_remote_omits_git_repo(self):
        repo, sha = make_repo(self.tmp)
        fields = git_fields.derive_git_fields(repo)
        self.assertNotIn("git_repo", fields)
        self.assertEqual(fields["source_commit"], sha)

    def test_repo_without_commits_omits_source_commit(self):
        repo, _ = make_repo(self.tmp, [("origin", CRED_URL)], with_commit=False)
        fields = git_fields.derive_git_fields(repo)
        self.assertNotIn("source_commit", fields)
        self.assertEqual(fields["git_repo"], CRED_URL_CLEAN)
        self.assertRegex(fields["last_validated"], LAST_VALIDATED_RE)


class TestUpdateGitFields(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.doc = self.tmp / "docker-networking-basics.md"
        self.doc.write_text(DOC, encoding="utf-8")
        self.fields = {
            "source_commit": "a" * 40,
            "last_validated": "2026-10-09",
            "git_repo": "https://github.com/example/repo.git",
        }

    def test_updates_and_appends_exactly_the_given_git_fields(self):
        text = git_fields.update_git_fields(self.doc, self.fields)
        fields, tags, _, body = kb_common.parse_frontmatter(text)
        self.assertEqual(fields["source_commit"], "a" * 40)
        self.assertEqual(fields["last_validated"], "2026-10-09")
        self.assertEqual(fields["git_repo"], "https://github.com/example/repo.git")
        # New git fields sit after the existing fields, before the tags block.
        self.assertEqual(
            list(fields),
            ["createdate", "title", "source_commit", "last_validated", "git_repo"],
        )
        # Everything not asked for is preserved verbatim.
        self.assertEqual(tags, ["docker"])
        self.assertEqual(body, "\nBody line.\n\nMore body.\n")
        # The document on disk is the rewritten text.
        self.assertEqual(text, self.doc.read_text(encoding="utf-8"))

    def test_subset_update_touches_only_its_keys(self):
        doc = self.tmp / "already-provenanced.md"
        doc.write_text(PROVENANCED_DOC, encoding="utf-8")
        text = git_fields.update_git_fields(doc, {"source_commit": "a" * 40})
        fields, _, _, _ = kb_common.parse_frontmatter(text)
        self.assertEqual(fields["source_commit"], "a" * 40)
        # last_validated keeps its old value; git_repo is not added.
        self.assertEqual(fields["last_validated"], "2020-01-01")
        self.assertNotIn("git_repo", fields)

    def test_document_without_frontmatter_gains_a_block(self):
        doc = self.tmp / "plain.md"
        doc.write_text("Just a body.\n", encoding="utf-8")
        text = git_fields.update_git_fields(doc, self.fields)
        self.assertEqual(
            text,
            "---\n"
            f"source_commit: {'a' * 40}\n"
            "last_validated: 2026-10-09\n"
            "git_repo: https://github.com/example/repo.git\n"
            "tags: []\n"
            "---\n"
            "Just a body.\n",
        )

    def test_key_outside_the_git_fields_is_rejected(self):
        with self.assertRaises(ValueError):
            git_fields.update_git_fields(self.doc, {"title": "x"})


class TestStdlibOnly(unittest.TestCase):
    def test_git_fields_and_this_test_import_stdlib_only(self):
        allowed = set(sys.stdlib_module_names)
        local = {"kb_common", "git_fields", "new_doc"}
        sources = [
            Path(__file__),
            Path(__file__).resolve().parents[1] / "git_fields.py",
            Path(__file__).resolve().parents[1] / "new_doc.py",
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
