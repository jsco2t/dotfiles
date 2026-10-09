#!/usr/bin/env python3
"""Tests for the fix_kb_ids.py naming fixer.

Run from the kb-utilities directory:

    python3 tests/test_names.py -v

or from the dotfiles repository root:

    python3 .local/bin/kb-utilities/tests/test_names.py -v

The contract pinned here:

fix_kb_ids.py is the naming fixer. It keeps its CLI shape (a positional
path, --dry-run, --no-rename, --json) but gains new semantics:

- No ID minting. No filename or frontmatter carries a generated ID, and
  the generated IDs of the old convention (generate_ulid_short) are gone.
- The filename stem is kb_common.normalize_filename of the frontmatter
  title (kebab-case, at most 42 characters); the frontmatter title is
  kb_common.normalize_title of the title.
- When a file is renamed, the obsolete ``id`` frontmatter field is
  dropped.
- --json prints a JSON array of {"old", "new"} basename pairs, the shape
  fix_wiki_links.py consumes.
- Collision targets get numeric suffixes (-2 style) so two files mapping
  to the same target get distinct names.
- --dry-run changes nothing and still prints the planned renames.
- --no-rename fixes the frontmatter title in place without renaming.
- Exit codes: 1 when the path is not a markdown file or not a valid
  file/directory, 0 otherwise (including when nothing needs fixing).
- Standard library only; it reuses kb_common.

The fixtures below are old-convention documents: 8-char-ID-prefixed
snake_case filenames whose frontmatter titles are human Title Case.
"""

import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fix_kb_ids  # noqa: E402  (red until the naming fixer exists)
import kb_common  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = Path(__file__).resolve().parents[1] / "fix_kb_ids.py"


def write_doc(path: Path, title: str) -> None:
    """Write an old-convention document: ID-prefixed filename, Title Case
    title, an id field, and a createdate field that must survive."""
    fields = {
        "id": "3f2a9c01",
        "createdate": "2026-01-02T03:04:05-07:00",
        "title": title,
    }
    path.write_text(kb_common.serialize_frontmatter(fields, ["docker"], "# Body\n"), encoding="utf-8")


class NamingFixerTestCase(unittest.TestCase):
    """Base fixture: a temp directory of old-convention documents."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )


class TestSingleFileRename(NamingFixerTestCase):
    """Done-when 1: the canonical old-convention document."""

    def test_id_prefixed_file_renamed_to_normalized_title(self):
        write_doc(self.dir / "3f2a9c01_my_great_doc.md", "My Great Doc!")

        proc = self.run_cli(str(self.dir / "3f2a9c01_my_great_doc.md"))

        self.assertEqual(proc.returncode, 0, proc.stderr)
        new_path = self.dir / "my-great-doc.md"
        self.assertTrue(new_path.exists(), "file was not renamed to my-great-doc.md")
        self.assertFalse((self.dir / "3f2a9c01_my_great_doc.md").exists())
        fields, _, _, _ = kb_common.parse_frontmatter(new_path.read_text(encoding="utf-8"))
        self.assertEqual(fields["title"], "my great doc")
        self.assertNotIn("id", fields, "the obsolete id field must be dropped")
        self.assertEqual(fields["createdate"], "2026-01-02T03:04:05-07:00")

    def test_already_conforming_file_is_left_alone(self):
        write_doc(self.dir / "my-great-doc.md", "my great doc")
        proc = self.run_cli(str(self.dir))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((self.dir / "my-great-doc.md").exists())


class TestDirectoryRun(NamingFixerTestCase):
    def test_directory_run_renames_and_reports_pairs(self):
        write_doc(self.dir / "3f2a9c01_my_great_doc.md", "My Great Doc!")
        proc = self.run_cli(str(self.dir))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((self.dir / "my-great-doc.md").exists())
        self.assertIn("my-great-doc.md", proc.stdout)


class TestDryRun(NamingFixerTestCase):
    """Done-when 2: --dry-run changes nothing and still prints the plan."""

    def test_dry_run_prints_plan_and_changes_nothing(self):
        write_doc(self.dir / "3f2a9c01_my_great_doc.md", "My Great Doc!")
        proc = self.run_cli(str(self.dir), "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((self.dir / "3f2a9c01_my_great_doc.md").exists())
        self.assertFalse((self.dir / "my-great-doc.md").exists())
        self.assertIn("my-great-doc.md", proc.stdout)


class TestJsonOutput(NamingFixerTestCase):
    """Done-when 2: --json output is a JSON array of {old,new} objects."""

    def test_json_prints_basename_pairs_compatible_with_fix_wiki_links(self):
        write_doc(self.dir / "3f2a9c01_my_great_doc.md", "My Great Doc!")
        proc = self.run_cli(str(self.dir), "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        pairs = json.loads(proc.stdout)
        self.assertEqual(pairs, [{"old": "3f2a9c01_my_great_doc.md", "new": "my-great-doc.md"}])

    def test_json_prints_empty_array_when_nothing_to_fix(self):
        write_doc(self.dir / "my-great-doc.md", "my great doc")
        proc = self.run_cli(str(self.dir), "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), [])

    def test_json_dry_run_reports_the_plan_without_applying_it(self):
        write_doc(self.dir / "3f2a9c01_my_great_doc.md", "My Great Doc!")
        proc = self.run_cli(str(self.dir), "--json", "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            json.loads(proc.stdout),
            [{"old": "3f2a9c01_my_great_doc.md", "new": "my-great-doc.md"}],
        )
        self.assertTrue((self.dir / "3f2a9c01_my_great_doc.md").exists())


class TestCollisions(NamingFixerTestCase):
    """Done-when 3: collision targets get distinct -2 style suffixes."""

    def test_two_files_with_the_same_title_get_distinct_names(self):
        write_doc(self.dir / "1aaaaaaa_same_topic.md", "Same Topic")
        write_doc(self.dir / "2bbbbbbb_same_topic.md", "Same Topic")
        proc = self.run_cli(str(self.dir))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((self.dir / "same-topic.md").exists())
        self.assertTrue((self.dir / "same-topic-2.md").exists())
        names = sorted(p.name for p in self.dir.glob("*.md"))
        self.assertEqual(names, ["same-topic-2.md", "same-topic.md"])

    def test_collision_with_an_existing_unrelated_file_gets_suffix(self):
        write_doc(self.dir / "my-great-doc.md", "my great doc")  # target already taken
        write_doc(self.dir / "3f2a9c01_my_great_doc.md", "My Great Doc!")
        proc = self.run_cli(str(self.dir))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((self.dir / "my-great-doc.md").exists())
        self.assertTrue((self.dir / "my-great-doc-2.md").exists())
        fields, _, _, _ = kb_common.parse_frontmatter(
            (self.dir / "my-great-doc-2.md").read_text(encoding="utf-8")
        )
        self.assertEqual(fields["title"], "my great doc")
        self.assertNotIn("id", fields)


class TestNoRename(NamingFixerTestCase):
    def test_no_rename_fixes_frontmatter_in_place(self):
        write_doc(self.dir / "3f2a9c01_my_great_doc.md", "My Great Doc!")
        proc = self.run_cli(str(self.dir), "--no-rename")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((self.dir / "3f2a9c01_my_great_doc.md").exists())
        self.assertFalse((self.dir / "my-great-doc.md").exists())
        fields, _, _, _ = kb_common.parse_frontmatter(
            (self.dir / "3f2a9c01_my_great_doc.md").read_text(encoding="utf-8")
        )
        self.assertEqual(fields["title"], "my great doc")
        self.assertNotIn("id", fields)


class TestExitCodes(NamingFixerTestCase):
    """Exit codes per R1: 1 on an invalid path, 0 otherwise."""

    def test_non_markdown_file_exits_1(self):
        not_md = self.dir / "notes.txt"
        not_md.write_text("hello", encoding="utf-8")
        proc = self.run_cli(str(not_md))
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(proc.stderr)

    def test_nonexistent_path_exits_1(self):
        proc = self.run_cli(str(self.dir / "missing.md"))
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(proc.stderr)

    def test_valid_target_exits_0_even_when_nothing_needs_fixing(self):
        write_doc(self.dir / "my-great-doc.md", "my great doc")
        proc = self.run_cli(str(self.dir))
        self.assertEqual(proc.returncode, 0, proc.stderr)


class TestNoIdGenerationRemains(NamingFixerTestCase):
    """Done-when 4: no ID generation remains; standard library only."""

    def test_no_id_minting_symbols(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("generate_ulid_short", source)
        self.assertNotIn("CROCKFORD", source)
        self.assertNotIn("_generated_ids", source)

    def test_stdlib_only_and_reuses_kb_common(self):
        allowed = set(sys.stdlib_module_names) | {"kb_common"}
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.add(node.module.split(".")[0])
        self.assertEqual(modules - allowed, set(), f"non-stdlib imports: {sorted(modules - allowed)}")
        self.assertIn("kb_common", modules, "the fixer must reuse kb_common")


class TestLongTitleCap(NamingFixerTestCase):
    def test_renamed_stem_is_normalize_filename_of_the_title(self):
        long_title = "Understanding systemd services start failures cgroups limits"
        write_doc(self.dir / "1aaaaaaa_systemd.md", long_title)
        proc = self.run_cli(str(self.dir))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        expected = kb_common.normalize_filename(long_title)
        self.assertTrue((self.dir / f"{expected}.md").exists())
        self.assertLessEqual(len(expected), kb_common.MAX_FILENAME_LEN)


if __name__ == "__main__":
    unittest.main()
