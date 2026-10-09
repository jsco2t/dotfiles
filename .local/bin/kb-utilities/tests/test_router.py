#!/usr/bin/env python3
"""Tests for the kbutil entrypoint: subcommand routing, symlink, and check.

Run from the kb-utilities directory:

    python3 tests/test_router.py -v

or from the dotfiles repository root:

    python3 .local/bin/kb-utilities/tests/test_router.py -v

The contract pinned here (Python standard library only; argparse
subparsers with set_defaults(func=...) in the style of ghtk and
atlassian):

kbutil is the single entrypoint at kb-utilities/kbutil. Each subcommand
routes to the sibling module it names, located relative to kbutil's own
__file__:

    new         ->  new_doc.py         create a kb document from a title
    clean       ->  doc_fix.py         frontmatter cleanup
    names       ->  fix_kb_ids.py      fix document names and titles
    links       ->  fix_wiki_links.py  fix wiki-links after renames
    fix         ->  migrate_kb.py      migrate old-convention documents
    git-fields  ->  git_fields.py      derive the git provenance fields
    validate    ->  git_fields.py      refresh last_validated on a document
    check       ->  migrate_kb.py      report-only conformance scan

The git fields (source_commit, last_validated, git_repo) describe the
repository a document REFERENCES, so git-fields, new and validate take
that repository explicitly: a local repository path, or a remote URL
that is recorded for git_repo when no local clone exists. They never
fall back to the document's enclosing repository or the current working
directory; without an explicit repository they fail with a usage error.
A URL never carries its credentials into output or frontmatter.

kbutil check PATH reports non-conforming documents (reusing
migrate_kb's scanner) and writes nothing.

.local/bin/kbutil is a symlink to kb-utilities/kbutil; the entrypoint is
executable and running it through the symlink works from any directory.

Every expected value below is hand-computed from this contract, not
generated from an implementation. The git fixtures are throwaway
repositories created with ``git init`` in a temporary directory through
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

import kb_common


# ── Locations ───────────────────────────────────────────────────────────────

UTILITIES = Path(__file__).resolve().parents[1]      # kb-utilities/
KBUTIL = UTILITIES / "kbutil"                        # the entrypoint script
SYMLINK = UTILITIES.parent / "kbutil"                # .local/bin/kbutil

SUBCOMMANDS = (
    "new", "clean", "names", "links", "fix", "git-fields", "validate", "check",
)

# Which sibling module each routed subcommand targets.
SIBLING_OF = {
    "new": "new_doc.py",
    "clean": "doc_fix.py",
    "names": "fix_kb_ids.py",
    "links": "fix_wiki_links.py",
    "fix": "migrate_kb.py",
    "check": "migrate_kb.py",
}

# The read-only notebook workspace: the motivating case for "never fall
# back to the enclosing repository", because the kb corpus lives there.
NOTEBOOK = Path("/home/ruser/Developer/sources/personal/notebook")


# ── Shared fixture data ─────────────────────────────────────────────────────

TODAY = datetime.date.today().isoformat()

# A remote URL that carries credentials, and its clean form: credentials
# must never reach kbutil output or document frontmatter.
CRED_URL = "https://user:ghp_testtoken123@github.com/example/repo.git"
CLEAN_URL = "https://github.com/example/repo.git"
TOKEN = "ghp_testtoken123"

# A document in the current convention: kebab-case filename matching the
# title, normalized title, no stray fields.
CONFORMING_NAME = "docker-networking.md"
CONFORMING_DOC = (
    "---\n"
    "id: 1jsj3x7c\n"
    "createdate: 2026-10-09T10:00:00-07:00\n"
    "title: docker networking\n"
    "tags: []\n"
    "---\n"
    "\n"
    "Body text about docker networking.\n"
)

# An old-convention document: an 8-char ID filename prefix, a title that
# is not normalized, a filename that does not match the title, and a
# stray id field. migrate_kb's scanner must report it.
OLD_NAME = "a1b2c3d4_old_style_notes.md"
OLD_DOC = (
    "---\n"
    "createdate: 2026-10-09T10:00:00-07:00\n"
    "title: Old Style Notes\n"
    "id: a1b2c3d4\n"
    "tags: []\n"
    "---\n"
    "\n"
    "Body text.\n"
)

# A document awaiting re-validation: its last_validated is stale and it
# carries no git provenance yet.
STALE_DOC = (
    "---\n"
    "createdate: 2026-10-09T10:00:00-07:00\n"
    "title: existing notes\n"
    "last_validated: 2020-01-01\n"
    "tags:\n"
    "  - notes\n"
    "---\n"
    "\n"
    "Body line.\n"
)


# ── Helpers ─────────────────────────────────────────────────────────────────

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


# Isolated git configuration: the fixtures must not depend on, or write
# to, the user's global or system git configuration.
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
    root: Path,
    name: str = "repo",
    remotes: tuple[tuple[str, str], ...] = (("origin", CRED_URL),),
) -> tuple[Path, str]:
    """Create a throwaway repository at root/name and return (repo, head sha).

    Each (name, url) pair in remotes is registered with git remote add. The
    repository gets one empty commit so HEAD resolves.
    """
    repo = root / name
    run_git(None, "init", "-q", "-b", "main", str(repo))
    for remote_name, url in remotes:
        run_git(repo, "remote", "add", remote_name, url)
    run_git(
        repo,
        "-c", "user.name=kb-test",
        "-c", "user.email=kb-test@example.com",
        "-c", "commit.gpgsign=false",
        "commit", "--allow-empty", "-q", "-m", "init",
    )
    return repo, run_git(repo, "rev-parse", "HEAD")


def run_tool(tool: Path, args: list[str], cwd: Path | None = None):
    """Run a Python script with the isolated git environment."""
    return subprocess.run(
        [sys.executable, str(tool), *args],
        capture_output=True, text=True, env=GIT_ENV, cwd=cwd,
    )


class RouterTestCase(unittest.TestCase):
    """Shared fixtures: a throwaway workspace, a fixture repository, kbutil."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="kbutil-tests-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.repo, self.sha = make_repo(self.tmp, name="referenced-repo")
        self.docs = self.tmp / "docs"
        self.docs.mkdir()

    def kbutil(self, *args: str, cwd: Path | None = None):
        """Run the kbutil entrypoint, failing cleanly while it does not exist."""
        if not KBUTIL.exists():
            self.fail(f"kbutil entrypoint is missing: {KBUTIL}")
        return run_tool(KBUTIL, list(args), cwd=cwd)

    def sibling(self, module: str, *args: str, cwd: Path | None = None):
        """Run one sibling module directly with the same arguments."""
        return run_tool(UTILITIES / module, list(args), cwd=cwd)

    def write_doc(self, name: str, content: str) -> Path:
        """Write a document into the fixture docs directory."""
        path = self.docs / name
        path.write_text(content, encoding="utf-8")
        return path

    def snapshot(self, directory: Path) -> dict[str, bytes]:
        """Map every file under directory to its bytes, for write checks."""
        return {
            str(path.relative_to(directory)): path.read_bytes()
            for path in sorted(Path(directory).rglob("*"))
            if path.is_file()
        }


# ── Help ────────────────────────────────────────────────────────────────────

class HelpTest(RouterTestCase):
    """kbutil --help lists every subcommand; bare kbutil shows usage."""

    def test_help_exits_zero_and_lists_every_subcommand(self):
        proc = self.kbutil("--help")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for name in SUBCOMMANDS:
            # Anchored at the help line's indented command name, so a
            # mention inside another description does not count.
            self.assertRegex(proc.stdout, rf"(?m)^\s+{re.escape(name)}\b")

    def test_bare_invocation_is_a_usage_error(self):
        proc = self.kbutil()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("usage", proc.stderr.lower())


# ── Symlink ─────────────────────────────────────────────────────────────────

class SymlinkTest(unittest.TestCase):
    """.local/bin/kbutil is an executable symlink to kb-utilities/kbutil."""

    def test_symlink_exists_and_resolves_to_the_entrypoint(self):
        self.assertTrue(KBUTIL.exists(), f"the entrypoint is missing: {KBUTIL}")
        self.assertTrue(SYMLINK.is_symlink(), f"{SYMLINK} is not a symlink")
        self.assertEqual(SYMLINK.resolve(), KBUTIL.resolve())

    def test_entrypoint_and_symlink_are_executable(self):
        for path in (KBUTIL, SYMLINK):
            self.assertTrue(
                os.access(path, os.X_OK), f"{path} is not executable"
            )

    def test_running_via_the_symlink_finds_the_siblings_from_any_cwd(self):
        if not KBUTIL.exists():
            self.fail(f"kbutil entrypoint is missing: {KBUTIL}")
        # A cwd far away from the entrypoint: the siblings must be located
        # relative to kbutil's own __file__, never relative to the caller.
        proc = subprocess.run(
            [str(SYMLINK), "--help"],
            capture_output=True, text=True, cwd=tempfile.gettempdir(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for name in SUBCOMMANDS:
            self.assertRegex(proc.stdout, rf"(?m)^\s+{re.escape(name)}\b")


# ── new ─────────────────────────────────────────────────────────────────────

class NewCommandTest(RouterTestCase):
    """kbutil new creates a document from a title; --repo is required."""

    def test_new_creates_a_document_with_git_provenance(self):
        proc = self.kbutil(
            "new", "Docker Networking",
            "--dir", str(self.docs), "--repo", str(self.repo),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        path = self.docs / CONFORMING_NAME
        self.assertTrue(
            path.exists(), f"no document created; stdout: {proc.stdout}"
        )
        fields, _, _, _ = kb_common.parse_frontmatter(
            path.read_text(encoding="utf-8")
        )
        self.assertEqual(fields["title"], "docker networking")
        self.assertTrue(kb_common.is_valid_ulid_short(fields["id"]),
                        "the created document must carry a valid id")
        self.assertEqual(fields["source_commit"], self.sha)
        self.assertEqual(fields["last_validated"], TODAY)
        self.assertEqual(fields["git_repo"], CLEAN_URL)
        self.assertIn(CONFORMING_NAME, proc.stdout)

    def test_new_records_a_url_when_no_local_clone_exists(self):
        proc = self.kbutil(
            "new", "Referenced Repo",
            "--dir", str(self.docs), "--repo", CLEAN_URL,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        created = list(self.docs.glob("*.md"))
        self.assertEqual(len(created), 1, proc.stdout)
        fields, _, _, _ = kb_common.parse_frontmatter(
            created[0].read_text(encoding="utf-8")
        )
        self.assertEqual(fields["git_repo"], CLEAN_URL)
        self.assertEqual(fields["last_validated"], TODAY)
        # No local clone: there is no commit to record.
        self.assertNotIn("source_commit", fields)

    def test_new_without_repo_is_a_usage_error(self):
        proc = self.kbutil("new", "Docker Networking", "--dir", str(self.docs))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("usage", proc.stderr.lower())
        self.assertEqual(
            [p.name for p in self.docs.iterdir()], [],
            "a document was created despite the missing repository",
        )

    def test_new_does_not_fall_back_to_the_enclosing_repository(self):
        enclosing, _ = make_repo(self.tmp, name="enclosing-repo")
        proc = self.kbutil(
            "new", "Enclosing Doc", "--dir", str(self.docs), cwd=enclosing
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("usage", proc.stderr.lower())
        self.assertEqual(
            [p.name for p in self.docs.iterdir()], [],
            "the enclosing repository's provenance leaked into a document",
        )

    @unittest.skipUnless(
        NOTEBOOK.is_dir() and (NOTEBOOK / ".git").exists(),
        "the read-only notebook workspace is not available",
    )
    def test_new_inside_the_notebook_never_uses_notebook_provenance(self):
        proc = self.kbutil(
            "new", "Notebook Doc", "--dir", str(self.docs), cwd=NOTEBOOK
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("usage", proc.stderr.lower())
        self.assertEqual(
            [p.name for p in self.docs.iterdir()], [],
            "notebook provenance leaked into a document",
        )
        self.assertNotIn("notebook", (proc.stdout + proc.stderr).lower())


# ── git-fields ──────────────────────────────────────────────────────────────

class GitFieldsCommandTest(RouterTestCase):
    """kbutil git-fields REPO prints the derived git provenance fields."""

    def test_git_fields_prints_the_derived_fields(self):
        proc = self.kbutil("git-fields", str(self.repo))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(f"source_commit: {self.sha}", proc.stdout)
        self.assertIn(f"last_validated: {TODAY}", proc.stdout)
        self.assertIn(f"git_repo: {CLEAN_URL}", proc.stdout)

    def test_git_fields_honors_last_validated(self):
        proc = self.kbutil(
            "git-fields", str(self.repo), "--last-validated", "2026-01-31"
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("last_validated: 2026-01-31", proc.stdout)

    def test_git_fields_records_a_url_when_no_local_clone_exists(self):
        proc = self.kbutil("git-fields", CLEAN_URL)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(f"git_repo: {CLEAN_URL}", proc.stdout)

    def test_git_fields_strips_credentials_from_a_url(self):
        proc = self.kbutil("git-fields", CRED_URL)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(f"git_repo: {CLEAN_URL}", proc.stdout)
        self.assertNotIn(TOKEN, proc.stdout + proc.stderr)

    def test_git_fields_without_a_repository_is_a_usage_error(self):
        proc = self.kbutil("git-fields")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("usage", proc.stderr.lower())

    def test_git_fields_fails_on_a_non_repository(self):
        proc = self.kbutil("git-fields", str(self.docs))
        self.assertNotEqual(proc.returncode, 0)
        self.assertTrue(proc.stderr.strip(), "the error was silent")


# ── validate ────────────────────────────────────────────────────────────────

class ValidateCommandTest(RouterTestCase):
    """kbutil validate refreshes a document against its referenced repo."""

    def setUp(self):
        super().setUp()
        self.doc = self.write_doc("existing-notes.md", STALE_DOC)

    def test_validate_refreshes_last_validated_and_source_commit(self):
        proc = self.kbutil(
            "validate", str(self.doc),
            "--repo", str(self.repo), "--last-validated", "2026-02-14",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        fields, tags, _, body = kb_common.parse_frontmatter(
            self.doc.read_text(encoding="utf-8")
        )
        self.assertEqual(fields["last_validated"], "2026-02-14")
        self.assertEqual(fields["source_commit"], self.sha)
        # Everything not refreshed is preserved verbatim.
        self.assertEqual(fields["title"], "existing notes")
        self.assertEqual(fields["createdate"], "2026-10-09T10:00:00-07:00")
        self.assertEqual(tags, ["notes"])
        self.assertEqual(body, "\nBody line.\n")

    def test_validate_defaults_last_validated_to_today(self):
        proc = self.kbutil("validate", str(self.doc), "--repo", str(self.repo))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        fields, _, _, _ = kb_common.parse_frontmatter(
            self.doc.read_text(encoding="utf-8")
        )
        self.assertEqual(fields["last_validated"], TODAY)
        self.assertEqual(fields["source_commit"], self.sha)

    def test_validate_accepts_a_url_repo(self):
        proc = self.kbutil("validate", str(self.doc), "--repo", CRED_URL)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = self.doc.read_text(encoding="utf-8")
        fields, _, _, _ = kb_common.parse_frontmatter(text)
        self.assertEqual(fields["git_repo"], CLEAN_URL)
        self.assertEqual(fields["last_validated"], TODAY)
        self.assertNotIn(TOKEN, text)

    def test_validate_without_repo_is_a_usage_error(self):
        before = self.doc.read_bytes()
        proc = self.kbutil("validate", str(self.doc))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("usage", proc.stderr.lower())
        self.assertEqual(self.doc.read_bytes(), before, "the doc was modified")


# ── check ───────────────────────────────────────────────────────────────────

class CheckCommandTest(RouterTestCase):
    """kbutil check reports non-conforming documents and writes nothing."""

    def test_check_reports_non_conforming_files_without_writing(self):
        self.write_doc(CONFORMING_NAME, CONFORMING_DOC)
        self.write_doc(OLD_NAME, OLD_DOC)
        before = self.snapshot(self.docs)
        proc = self.kbutil("check", str(self.docs))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(OLD_NAME, proc.stdout)
        self.assertEqual(
            self.snapshot(self.docs), before,
            "kbutil check modified the scanned directory",
        )

    def test_check_reports_conforming_files_as_conforming(self):
        self.write_doc(CONFORMING_NAME, CONFORMING_DOC)
        proc = self.kbutil("check", str(self.docs))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(CONFORMING_NAME, proc.stdout)
        self.assertEqual(
            self.snapshot(self.docs), {CONFORMING_NAME: CONFORMING_DOC.encode()},
            "kbutil check modified the scanned directory",
        )

    def test_check_missing_directory_fails(self):
        proc = self.kbutil("check", str(self.docs / "absent"))
        self.assertNotEqual(proc.returncode, 0)


# ── Routing to the sibling modules ──────────────────────────────────────────

class SiblingDispatchTest(RouterTestCase):
    """Each routed subcommand behaves like the sibling module it names.

    The routed run and the direct sibling run receive the same arguments
    AFTER the subcommand word: kbutil hands the caller's arguments after
    `kbutil fix DIR` -> `migrate_kb.py DIR`. The routed run must also
    succeed, so a broken route fails here instead of matching a sibling
    invoked with the same broken argv.
    """

    def assert_matches_sibling(self, module: str, *args: str, cwd=None):
        routed = self.kbutil(*args, cwd=cwd)
        direct = self.sibling(module, *args[1:], cwd=cwd)
        self.assertEqual(
            routed.returncode, 0,
            f"the routed invocation failed; stderr: {routed.stderr}"
        )
        self.assertEqual(
            routed.returncode, direct.returncode,
            f"exit codes differ: kbutil={routed.returncode}, "
            f"{module}={direct.returncode}; kbutil stderr: {routed.stderr}",
        )
        self.assertEqual(
            routed.stdout, direct.stdout,
            f"stdout differs from running {module} directly",
        )

    def test_clean_routes_to_doc_fix(self):
        self.write_doc("no-frontmatter.md", "Just a body.\n")
        self.write_doc(CONFORMING_NAME, CONFORMING_DOC)
        self.assert_matches_sibling(
            "doc_fix.py", "clean", ".", "--dry-run", cwd=self.docs
        )

    def test_names_routes_to_fix_kb_ids(self):
        self.write_doc(OLD_NAME, OLD_DOC)
        self.write_doc(CONFORMING_NAME, CONFORMING_DOC)
        self.assert_matches_sibling("fix_kb_ids.py", "names", str(self.docs),
                                    "--dry-run")

    def test_links_routes_to_fix_wiki_links(self):
        linked = CONFORMING_DOC.replace(
            "Body text about docker networking.", "See [[old-note]] too."
        )
        self.write_doc(CONFORMING_NAME, linked)
        mapping = self.tmp / "renames.json"
        mapping.write_text(
            '[{"old": "old-note.md", "new": "new-note.md"}]', encoding="utf-8"
        )
        self.assert_matches_sibling(
            "fix_wiki_links.py", "links", "--mapping-file", str(mapping),
            "--dry-run", cwd=self.docs,
        )

    def test_fix_routes_to_migrate_kb(self):
        self.write_doc(OLD_NAME, OLD_DOC)
        self.write_doc(CONFORMING_NAME, CONFORMING_DOC)
        self.assert_matches_sibling("migrate_kb.py", "fix", str(self.docs))


# ── Standard library only ───────────────────────────────────────────────────

class StdlibOnlyTest(unittest.TestCase):
    def test_kbutil_and_this_test_import_stdlib_only(self):
        if not KBUTIL.exists():
            self.fail(f"kbutil entrypoint is missing: {KBUTIL}")
        allowed = set(sys.stdlib_module_names)
        local = {
            "kb_common", "doc_fix", "fix_kb_ids", "fix_wiki_links",
            "migrate_kb", "git_fields", "new_doc",
        }
        sources = [Path(__file__), KBUTIL]
        for source in sources:
            modules = collect_top_level_imports(source) - local
            self.assertEqual(
                modules - allowed, set(),
                f"{source.name} imports non-stdlib modules: "
                f"{sorted(modules - allowed)}",
            )


if __name__ == "__main__":
    unittest.main()
