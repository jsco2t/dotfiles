#!/usr/bin/env python3
"""Tests for migrate_kb.py, the old-convention migration fixer.

Run from the kb-utilities directory:

    python3 tests/test_migrate.py -v

or from the dotfiles repository root:

    python3 .local/bin/kb-utilities/tests/test_migrate.py -v

The contract pinned here:

migrate_kb.py PATH [--apply] [--mapping-out FILE]
    Fixes old-convention documents in place. An old-convention document
    (scope: "a Markdown KB file whose filename carries an ID prefix or
    whose title/filename pair does not match the new naming rules") is
    detected by any of: an 8-char lowercase ID filename prefix
    (^[0-9a-z]{8}_), a filename stem that is not
    kb_common.normalize_filename of the frontmatter title, a title that
    is not kb_common.normalize_title of itself, or a stray ``id``
    frontmatter field.

- The positional PATH is a directory; it is scanned recursively,
  skipping the directories named in kb_common.EXCLUDED_DIRS.
- The rename target for each document is kb_common.normalize_filename of
  its frontmatter title. The plan is printed as a table showing each old
  and new name. Documents that already conform are reported as skipped,
  not rewritten.
- The default run is a dry run: it reports the plan and writes nothing,
  including no --mapping-out file. Renames happen only with --apply.
- On --apply the file is renamed, the obsolete ``id`` frontmatter field
  is removed, the title is rewritten to kb_common.normalize_title of
  itself, and every other field and the body are preserved verbatim
  (wikilinks in the body are NOT rewritten here; that is fix_wiki_links'
  job, driven by the mapping). A document whose filename already
  conforms is fixed in place without a rename. A document with no
  usable title (no frontmatter) is left unchanged.
- Collisions get numeric suffixes (-2 style, via
  kb_common.normalize_filename with a suffix) both between two planned
  renames and against a file that already exists; the pre-existing file
  is never overwritten.
- Running --apply twice is idempotent: the second run renames nothing
  and changes no file.
- --mapping-out FILE writes a JSON array of {"old", "new"} basename
  pairs (the shape fix_wiki_links.load_rename_mapping consumes), but
  only when --apply is given.
- Exit codes: 1 when the path does not exist or is not a valid
  directory, 0 otherwise (including when nothing needs fixing).
- Standard library only; it reuses kb_common.

The fixtures below are a small corpus of old-convention documents:
ID-prefixed snake_case filenames, human Title Case titles (some quoted),
stray id frontmatter fields, and wikilinks between the documents.
"""

import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fix_wiki_links  # noqa: E402
import kb_common  # noqa: E402
import migrate_kb  # noqa: E402  (red until the migration script exists)

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = Path(__file__).resolve().parents[1] / "migrate_kb.py"


def write_doc(path: Path, title: str, body: str = "# Body\n",
              doc_id: str | None = "3f2a9c01") -> None:
    """Write an old-convention document.

    ID-prefixed filenames are passed by the caller; the frontmatter
    carries a Title Case title, a stray id field (unless doc_id is
    None), and a createdate field that must survive migration.
    """
    fields: dict[str, str] = {
        "createdate": "2026-01-02T03:04:05-07:00",
        "title": title,
    }
    if doc_id is not None:
        fields["id"] = doc_id
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        kb_common.serialize_frontmatter(fields, ["docker"], body),
        encoding="utf-8",
    )


def snapshot(root: Path) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


class MigrationTestCase(unittest.TestCase):
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


class TestDetection(MigrationTestCase):
    """Old-convention documents are detected; conforming ones are not."""

    def test_id_prefix_alone_marks_a_document_old_convention(self):
        # Filename stem matches the title's slug form, but the 8-char ID
        # prefix and the id field are old convention.
        write_doc(self.dir / "3f2a9c01_kubernetes_basics.md",
                  "kubernetes basics")
        proc = self.run_cli(str(self.dir))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("kubernetes-basics.md", proc.stdout)

    def test_snake_case_name_without_id_prefix_is_detected(self):
        # No ID prefix, but the stem is not normalize_filename of the title.
        write_doc(self.dir / "k8s_rolling_restarts.md",
                  "Kubernetes Rolling Restarts", doc_id=None)
        proc = self.run_cli(str(self.dir))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("kubernetes-rolling-restarts.md", proc.stdout)

    def test_conforming_file_is_reported_as_skipped(self):
        write_doc(self.dir / "my-great-doc.md", "my great doc", doc_id=None)
        proc = self.run_cli(str(self.dir))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("my-great-doc.md", proc.stdout)
        self.assertIn("skip", proc.stdout.lower())

    def test_file_without_frontmatter_is_left_alone(self):
        # No title to derive a plan from; renaming it would be destructive.
        orphan = self.dir / "3f2a9c01_orphan.md"
        orphan.write_text("just some notes\n", encoding="utf-8")
        proc = self.run_cli(str(self.dir), "--apply")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(orphan.read_text(encoding="utf-8"), "just some notes\n")


class TestDryRunDefault(MigrationTestCase):
    """Done-when 1: the default run is a dry run that writes nothing."""

    def test_default_run_prints_plan_and_writes_nothing(self):
        write_doc(self.dir / "3f2a9c01_my_great_doc.md", "My Great Doc!")
        before = snapshot(self.dir)

        proc = self.run_cli(str(self.dir))

        self.assertEqual(proc.returncode, 0, proc.stderr)
        # The plan table names both sides of every planned rename.
        self.assertIn("3f2a9c01_my_great_doc.md", proc.stdout)
        self.assertIn("my-great-doc.md", proc.stdout)
        self.assertEqual(snapshot(self.dir), before, "dry run wrote a file")

    def test_dry_run_writes_no_mapping_file(self):
        write_doc(self.dir / "3f2a9c01_my_great_doc.md", "My Great Doc!")
        mapping = self.dir / "renames.json"
        proc = self.run_cli(str(self.dir), "--mapping-out", str(mapping))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(mapping.exists(),
                         "dry run must not write the mapping file")


class TestApply(MigrationTestCase):
    """Done-when 2: --apply renames, strips id, and is idempotent."""

    def test_apply_renames_and_removes_id_field(self):
        write_doc(self.dir / "3f2a9c01_my_great_doc.md", "My Great Doc!")

        proc = self.run_cli(str(self.dir), "--apply")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        new_path = self.dir / "my-great-doc.md"
        self.assertTrue(new_path.exists(), "file was not renamed")
        self.assertFalse((self.dir / "3f2a9c01_my_great_doc.md").exists())
        fields, tags, _, body = kb_common.parse_frontmatter(
            new_path.read_text(encoding="utf-8"))
        self.assertNotIn("id", fields, "the obsolete id field must be dropped")
        self.assertEqual(fields["title"], "my great doc")
        self.assertEqual(fields["createdate"], "2026-01-02T03:04:05-07:00")
        self.assertEqual(tags, ["docker"])
        self.assertEqual(body, "# Body\n")

    def test_apply_normalizes_a_nonconforming_title_in_place(self):
        # Filename already conforms; only the Title Case title is wrong.
        write_doc(self.dir / "my-great-doc.md", "My Great Doc!", doc_id=None)
        proc = self.run_cli(str(self.dir), "--apply")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((self.dir / "my-great-doc.md").exists())
        fields, _, _, _ = kb_common.parse_frontmatter(
            (self.dir / "my-great-doc.md").read_text(encoding="utf-8"))
        self.assertEqual(fields["title"], "my great doc")

    def test_apply_removes_a_stray_id_without_renaming(self):
        # Conforming filename and title, but a stray id field remains.
        write_doc(self.dir / "my-great-doc.md", "my great doc",
                  doc_id="3f2a9c01")
        proc = self.run_cli(str(self.dir), "--apply")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((self.dir / "my-great-doc.md").exists())
        self.assertFalse((self.dir / "my-great-doc-2.md").exists())
        fields, _, _, _ = kb_common.parse_frontmatter(
            (self.dir / "my-great-doc.md").read_text(encoding="utf-8"))
        self.assertNotIn("id", fields)

    def test_apply_is_idempotent_on_a_second_run(self):
        write_doc(self.dir / "3f2a9c01_my_great_doc.md", "My Great Doc!")
        first = self.run_cli(str(self.dir), "--apply")
        self.assertEqual(first.returncode, 0, first.stderr)
        after_first = snapshot(self.dir)

        second = self.run_cli(str(self.dir), "--apply")

        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(snapshot(self.dir), after_first,
                         "the second apply run changed a file")

    def test_apply_preserves_body_wikilinks_untouched(self):
        # Link rewriting belongs to fix_wiki_links, driven by the mapping;
        # migrate_kb must leave body content verbatim.
        write_doc(self.dir / "3f2a9c01_alpha_doc.md",
                  "Alpha Document", body="see [[3f2a9c01_beta_doc]] here\n")
        write_doc(self.dir / "3f2a9c01_beta_doc.md", "Beta Document")
        proc = self.run_cli(str(self.dir), "--apply")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        alpha = (self.dir / "alpha-document.md").read_text(encoding="utf-8")
        self.assertIn("[[3f2a9c01_beta_doc]]", alpha)
        self.assertTrue((self.dir / "beta-document.md").exists())


class TestMappingOut(MigrationTestCase):
    """Done-when 3: --mapping-out writes the {old,new} JSON mapping."""

    def test_mapping_out_writes_pairs_consumable_by_fix_wiki_links(self):
        write_doc(self.dir / "3f2a9c01_alpha_doc.md", "Alpha Document")
        write_doc(self.dir / "3f2a9c01_beta_doc.md", "Beta Document")
        mapping = self.dir / "renames.json"

        proc = self.run_cli(str(self.dir), "--apply",
                            "--mapping-out", str(mapping))

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(mapping.exists())
        pairs = fix_wiki_links.load_rename_mapping(str(mapping))
        self.assertEqual(
            sorted(pairs, key=lambda p: p["old"]),
            [
                {"old": "3f2a9c01_alpha_doc.md", "new": "alpha-document.md"},
                {"old": "3f2a9c01_beta_doc.md", "new": "beta-document.md"},
            ],
        )

    def test_mapping_out_covers_only_renamed_files(self):
        write_doc(self.dir / "3f2a9c01_my_great_doc.md", "My Great Doc!")
        write_doc(self.dir / "already-fine.md", "already fine", doc_id=None)
        mapping = self.dir / "renames.json"
        proc = self.run_cli(str(self.dir), "--apply",
                            "--mapping-out", str(mapping))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        pairs = fix_wiki_links.load_rename_mapping(str(mapping))
        self.assertEqual(
            pairs, [{"old": "3f2a9c01_my_great_doc.md", "new": "my-great-doc.md"}])


class TestCollisions(MigrationTestCase):
    """Collision targets get -2 style suffixes; nothing is overwritten."""

    def test_two_documents_with_the_same_title_get_distinct_names(self):
        write_doc(self.dir / "1aaaaaaa_same_topic.md", "Same Topic")
        write_doc(self.dir / "2bbbbbbb_same_topic.md", "Same Topic")
        proc = self.run_cli(str(self.dir), "--apply")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        names = sorted(p.name for p in self.dir.glob("*.md"))
        self.assertEqual(names, ["same-topic-2.md", "same-topic.md"])
        for name in names:
            fields, _, _, _ = kb_common.parse_frontmatter(
                (self.dir / name).read_text(encoding="utf-8"))
            self.assertNotIn("id", fields)
            self.assertEqual(fields["title"], "same topic")

    def test_collision_with_an_existing_file_gets_a_suffix(self):
        write_doc(self.dir / "my-great-doc.md", "my great doc", doc_id=None)
        existing = (self.dir / "my-great-doc.md").read_bytes()
        write_doc(self.dir / "3f2a9c01_my_great_doc.md", "My Great Doc!")

        proc = self.run_cli(str(self.dir), "--apply")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual((self.dir / "my-great-doc.md").read_bytes(), existing,
                         "the pre-existing file was overwritten")
        self.assertTrue((self.dir / "my-great-doc-2.md").exists())


class TestRecursiveScan(MigrationTestCase):
    """Directory scans are recursive and honor EXCLUDED_DIRS."""

    def test_subdirectory_documents_are_migrated(self):
        write_doc(self.dir / "kb" / "sub" / "3f2a9c01_nested_doc.md",
                  "Nested Doc!")
        proc = self.run_cli(str(self.dir), "--apply")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((self.dir / "kb" / "sub" / "nested-doc.md").exists())

    def test_excluded_dirs_are_never_scanned(self):
        for excluded in ("resources", "scratch", ".git"):
            write_doc(self.dir / excluded / "3f2a9c01_skip_doc.md",
                      "Skip Doc!")
        before = snapshot(self.dir)
        proc = self.run_cli(str(self.dir), "--apply")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(snapshot(self.dir), before,
                         "a file inside an excluded directory was changed")


class TestExitCodes(MigrationTestCase):
    """Exit codes per fix_kb_ids: 1 on an invalid path, 0 otherwise."""

    def test_nonexistent_path_exits_1(self):
        proc = self.run_cli(str(self.dir / "missing.md"))
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(proc.stderr)

    def test_non_markdown_file_exits_1(self):
        not_md = self.dir / "notes.txt"
        not_md.write_text("hello", encoding="utf-8")
        proc = self.run_cli(str(not_md))
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(proc.stderr)

    def test_nothing_to_fix_exits_0(self):
        write_doc(self.dir / "my-great-doc.md", "my great doc", doc_id=None)
        proc = self.run_cli(str(self.dir))
        self.assertEqual(proc.returncode, 0, proc.stderr)


class TestStdlibOnly(MigrationTestCase):
    """Standard library only; the fixer reuses kb_common."""

    def test_stdlib_only_and_reuses_kb_common(self):
        allowed = set(sys.stdlib_module_names) | {"kb_common"}
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.add(node.module.split(".")[0])
        self.assertEqual(modules - allowed, set(),
                         f"non-stdlib imports: {sorted(modules - allowed)}")
        self.assertIn("kb_common", modules, "the fixer must reuse kb_common")


if __name__ == "__main__":
    unittest.main()
