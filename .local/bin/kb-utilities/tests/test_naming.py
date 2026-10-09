#!/usr/bin/env python3
"""Tests for kb_common naming rules: normalize_title, normalize_filename,
title_from_filename, and the shared EXCLUDED_DIRS.

Run from the kb-utilities directory:

    python3 tests/test_naming.py -v

or from the dotfiles repository root:

    python3 .local/bin/kb-utilities/tests/test_naming.py -v

The contract pinned here (kb_common is stdlib-only):

normalize_title(title)
    Lowercase; apostrophes dropped entirely (no space inserted); every other
    non-alphanumeric character becomes a space; whitespace collapsed; trimmed.

normalize_filename(title, suffix=None)
    normalize_title with spaces replaced by dashes, truncated to at most 42
    characters at a dash boundary, with no trailing dash. Truncation cuts at
    the last dash within the allowed length; a form with no dash there is cut
    hard at 42. When ``suffix`` is given (a collision suffix such as "2") it
    is appended as ``-<suffix>`` and the stem is truncated to leave room for
    it, so the full stem never exceeds 42 characters.

title_from_filename(stem)
    The reverse mapping: dashes become spaces. A filename stem and its title
    differ only by spaces vs dashes and by the 42-character cap.

EXCLUDED_DIRS
    The directory-name exclusion set shared by the walk-based tools, ported
    verbatim from notebook .tools (doc_fix.py:25-28, fix_wiki_links.py:29-34).

Every expected value below is hand-computed from this contract, not generated
from an implementation.
"""

import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import kb_common


LONG_TITLE = "Understanding systemd services start failures cgroups limits"


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


class TestNormalizeTitle(unittest.TestCase):
    def test_dropped_apostrophes_and_punctuation(self):
        self.assertEqual(
            kb_common.normalize_title("Don't Stop -- Pre-commit!"),
            "dont stop pre commit",
        )

    def test_lowercased(self):
        self.assertEqual(
            kb_common.normalize_title("Kubernetes Rolling Restarts"),
            "kubernetes rolling restarts",
        )

    def test_apostrophe_dropped_without_inserting_space(self):
        # The apostrophe vanishes; it must not split the word.
        self.assertEqual(kb_common.normalize_title("don't"), "dont")

    def test_underscores_become_spaces(self):
        # Old-convention snake_case slugs normalize like any other punctuation.
        self.assertEqual(kb_common.normalize_title("snake_case_name"), "snake case name")

    def test_digits_are_kept(self):
        self.assertEqual(kb_common.normalize_title("IPv6 in 2026"), "ipv6 in 2026")

    def test_every_other_non_alnum_becomes_one_space(self):
        # '+', '&', '/' and surrounding spaces all collapse to single spaces.
        self.assertEqual(kb_common.normalize_title("C++ & Rust/C"), "c rust c")

    def test_whitespace_collapsed_and_trimmed(self):
        self.assertEqual(kb_common.normalize_title("  A   B  "), "a b")

    def test_title_without_alphanumerics_is_empty(self):
        self.assertEqual(kb_common.normalize_title("!!!"), "")
        self.assertEqual(kb_common.normalize_title(""), "")


class TestNormalizeFilename(unittest.TestCase):
    def test_spaces_become_dashes(self):
        self.assertEqual(
            kb_common.normalize_filename("Don't Stop -- Pre-commit!"),
            "dont-stop-pre-commit",
        )

    def test_stable_for_already_kebab_input(self):
        # An existing conforming filename stem passes through unchanged.
        self.assertEqual(
            kb_common.normalize_filename("dont-stop-pre-commit"),
            "dont-stop-pre-commit",
        )

    def test_long_title_is_60_chars(self):
        # Pins the "a 60-char title" premise of the cap tests below.
        self.assertEqual(len(LONG_TITLE), 60)

    def test_cap_cuts_at_dash_boundary(self):
        # Dashed form is 60 chars; the last dash within 42 chars is at index 36.
        stem = kb_common.normalize_filename(LONG_TITLE)
        self.assertEqual(stem, "understanding-systemd-services-start")
        self.assertLessEqual(len(stem), 42)
        self.assertFalse(stem.endswith("-"))

    def test_cap_drops_a_dash_that_lands_on_the_boundary(self):
        # Dashed form is 47 chars and its 42nd character is a dash; the dash
        # itself is dropped so the stem ends at a word boundary.
        stem = kb_common.normalize_filename(
            "postgresql backup restore with pgdump and roles"
        )
        self.assertEqual(stem, "postgresql-backup-restore-with-pgdump-and")
        self.assertLessEqual(len(stem), 42)
        self.assertFalse(stem.endswith("-"))

    def test_cap_hard_cuts_when_no_dash_exists_in_range(self):
        # A single long word has no dash boundary to cut at.
        self.assertEqual(kb_common.normalize_filename("a" * 50), "a" * 42)
        self.assertEqual(kb_common.normalize_filename("a" * 43), "a" * 42)

    def test_form_of_exactly_42_chars_is_unchanged(self):
        self.assertEqual(kb_common.normalize_filename("a" * 42), "a" * 42)

    def test_filename_invariants(self):
        titles = [
            "Don't Stop -- Pre-commit!",
            LONG_TITLE,
            "snake_case_name",
            "IPv6 in 2026",
            "C++ & Rust/C",
            "a" * 50,
        ]
        for title in titles:
            with self.subTest(title=title):
                stem = kb_common.normalize_filename(title)
                self.assertTrue(stem)
                self.assertEqual(stem, stem.lower())
                self.assertNotIn(" ", stem)
                self.assertFalse(stem.startswith("-"))
                self.assertFalse(stem.endswith("-"))
                self.assertLessEqual(len(stem), 42)

    def test_collision_suffix_is_appended(self):
        self.assertEqual(
            kb_common.normalize_filename("Don't Stop -- Pre-commit!", suffix="2"),
            "dont-stop-pre-commit-2",
        )

    def test_collision_suffix_respects_the_cap(self):
        # The stem leaves room for the suffix so the whole stem stays <= 42.
        with_suffix = kb_common.normalize_filename(LONG_TITLE, suffix="2")
        self.assertEqual(with_suffix, "understanding-systemd-services-start-2")
        self.assertLessEqual(len(with_suffix), 42)
        wider_suffix = kb_common.normalize_filename(LONG_TITLE, suffix="10")
        self.assertLessEqual(len(wider_suffix), 42)
        self.assertTrue(wider_suffix.endswith("-10"))


class TestTitleFilenameRoundTrip(unittest.TestCase):
    def test_title_from_filename_replaces_dashes_with_spaces(self):
        self.assertEqual(
            kb_common.title_from_filename("dont-stop-pre-commit"),
            "dont stop pre commit",
        )

    def test_round_trip_differs_only_by_spaces_and_cap(self):
        titles = [
            "Don't Stop -- Pre-commit!",
            LONG_TITLE,
            "Kubernetes Rolling Restarts",
            "postgresql backup restore with pgdump and roles",
            "C++ & Rust/C",
        ]
        for title in titles:
            with self.subTest(title=title):
                stem = kb_common.normalize_filename(title)
                paired_title = kb_common.title_from_filename(stem)
                # The paired title is the stem with dashes swapped for spaces.
                self.assertEqual(paired_title, stem.replace("-", " "))
                # Its words are the leading words of the normalized title.
                words = kb_common.normalize_title(title).split()
                self.assertEqual(paired_title.split(), words[: len(paired_title.split())])
                # Re-deriving the filename from the paired title is stable.
                self.assertEqual(kb_common.normalize_filename(paired_title), stem)

    def test_short_titles_round_trip_exactly(self):
        # Below the cap there is no truncation: title and stem differ only by
        # spaces vs dashes.
        for title in ("Don't Stop -- Pre-commit!", "Kubernetes Rolling Restarts"):
            with self.subTest(title=title):
                self.assertEqual(
                    kb_common.title_from_filename(kb_common.normalize_filename(title)),
                    kb_common.normalize_title(title),
                )

    def test_60_char_title_truncates_to_the_same_words(self):
        stem = kb_common.normalize_filename(LONG_TITLE)
        self.assertEqual(
            kb_common.title_from_filename(stem),
            "understanding systemd services start",
        )
        # Exactly the leading words of the full normalized title.
        self.assertEqual(
            kb_common.title_from_filename(stem).split(),
            kb_common.normalize_title(LONG_TITLE).split()[:4],
        )


class TestExcludedDirs(unittest.TestCase):
    def test_shared_exclusion_set_ported_verbatim(self):
        # Literal set shared by notebook .tools/doc_fix.py:25-28 and
        # .tools/fix_wiki_links.py:29-34.
        self.assertEqual(
            kb_common.EXCLUDED_DIRS,
            {
                "templates",
                "TaskNotes",
                "boards",
                ".obsidian",
                ".git",
                "scratch",
                "xchive",
                "resources",
            },
        )


class TestStdlibOnly(unittest.TestCase):
    def test_kb_common_and_this_test_import_stdlib_only(self):
        allowed = set(sys.stdlib_module_names)
        sources = [
            Path(__file__),
            Path(__file__).resolve().parents[1] / "kb_common.py",
        ]
        for source in sources:
            with self.subTest(source=source.name):
                modules = collect_top_level_imports(source) - {"kb_common"}
                self.assertEqual(
                    modules - allowed,
                    set(),
                    f"{source.name} imports non-stdlib modules: "
                    f"{sorted(modules - allowed)}",
                )


if __name__ == "__main__":
    unittest.main()
