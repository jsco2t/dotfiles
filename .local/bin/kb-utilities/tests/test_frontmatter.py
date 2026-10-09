#!/usr/bin/env python3
"""Tests for kb_common frontmatter parsing and serialization.

Run from the kb-utilities directory:

    python3 tests/test_frontmatter.py -v

or from the dotfiles repository root:

    python3 .local/bin/kb-utilities/tests/test_frontmatter.py -v

The contract pinned here (ported from notebook .tools, best of both parsers:
doc_fix.py:121-194 contributes tolerant close handling, tag forms and quote
stripping; fix_kb_ids.py:138-168 contributes the simple key/value shape):

parse_frontmatter(content) -> (fields, tags, fm_raw, body)
    Returns a dict of simple key -> value string pairs (quote-stripped,
    excluding tags), the list of tag strings, the raw frontmatter text
    including its --- markers, and the body after the frontmatter. Documents
    may be id-free: a missing id is simply absent from fields. Tags are read
    from inline arrays (``tags: [a, b]``), YAML lists (``tags:`` followed by
    indented ``- item`` lines) and single-line values (``tags: a``); an
    explicit empty array yields []. The closing --- is tolerated with
    trailing spaces and at end of file without a trailing newline. The
    frontmatter block ends at the closing marker's line terminator; any blank
    line after it belongs to the body, so parse -> serialize preserves the
    body verbatim (the ported .tools regex ``\n---\s*\n`` would instead swallow
    that blank line). A value may itself contain colons (the key ends at the
    first colon). Content that does not start with --- parses as no
    frontmatter: empty fields, empty tags, empty fm_raw, and the whole
    content as body.

serialize_frontmatter(fields, tags, body="") -> str
    The canonical document: "---\\n", one ``key: value`` line per field in
    insertion order, a canonical tags block (``tags:`` with indented
    ``- item`` lines, or ``tags: []`` when tags is empty), "---\\n", then
    body verbatim. Field and tag values are written unquoted.

Document IDs (recovered from notebook .tools/fix_kb_ids.py):

generate_ulid_short() -> str
    An 8-character lowercase Crockford Base32 ID compatible with
    ulidshort.js: the first 6 characters are the millisecond Unix
    timestamp encoded to Crockford Base32, the last 2 are random, and no
    ID repeats within a session.

is_valid_ulid_short(s) -> bool
    True for exactly 8 lowercase Crockford characters.

ensure_id(fields) -> (fields, minted)
    A valid existing id is kept as-is; a missing or invalid id is minted
    and inserted as the first field.

Round-trip: parse(serialize(parse(doc))) == parse(doc) for field values,
tags and body.
"""

import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import kb_common


INLINE_DOC = (
    "---\n"
    "createdate: 2026-10-09T10:00:00-07:00\n"
    "title: Docker Networking Basics\n"
    "tags: [docker, networking]\n"
    "---\n"
    "\n"
    "Body text here.\n"
)

YAML_LIST_DOC = (
    "---\n"
    "createdate: 2026-10-09T10:00:00-07:00\n"
    'title: "Systemd: Service Start Failures"\n'
    "tags:\n"
    "  - systemd\n"
    "  - 'journalctl'\n"
    "---\n"
    "Body.\n"
)

PROVENANCE_DOC = (
    "---\n"
    "createdate: 2026-10-09T10:00:00-07:00\n"
    "title: Containerd Registry Mirrors\n"
    "tags: [containers]\n"
    "source_commit: 1a2b3c4\n"
    "last_validated: 2026-10-01\n"
    "git_repo: https://github.com/example/example\n"
    "---\n"
    "Body about a repository.\n"
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


class TestParseFrontmatter(unittest.TestCase):
    def test_document_without_frontmatter(self):
        content = "Just a body.\n"
        self.assertEqual(
            kb_common.parse_frontmatter(content),
            ({}, [], "", content),
        )

    def test_id_free_document_with_inline_tags_and_unquoted_title(self):
        fields, tags, fm_raw, body = kb_common.parse_frontmatter(INLINE_DOC)
        self.assertEqual(
            fields,
            {
                "createdate": "2026-10-09T10:00:00-07:00",
                "title": "Docker Networking Basics",
            },
        )
        # Tags live outside fields, and an id-free document has no id key.
        self.assertNotIn("tags", fields)
        self.assertNotIn("id", fields)
        self.assertEqual(tags, ["docker", "networking"])
        # The blank line after the closing --- belongs to the body, so a
        # parse -> serialize rewrite preserves it.
        self.assertEqual(body, "\nBody text here.\n")
        # Raw frontmatter keeps both --- markers and every original line.
        self.assertTrue(fm_raw.startswith("---"))
        self.assertTrue(fm_raw.rstrip().endswith("---"))
        self.assertIn("title: Docker Networking Basics", fm_raw)

    def test_quoted_title_and_yaml_list_tags(self):
        fields, tags, fm_raw, body = kb_common.parse_frontmatter(YAML_LIST_DOC)
        self.assertEqual(
            fields,
            {
                "createdate": "2026-10-09T10:00:00-07:00",
                "title": "Systemd: Service Start Failures",
            },
        )
        self.assertEqual(tags, ["systemd", "journalctl"])
        self.assertEqual(body, "Body.\n")

    def test_inline_tags_with_quotes_and_spaces(self):
        doc = "---\ntitle: T\ntags: [ 'docker', \"networking\" ]\n---\nB\n"
        _, tags, _, _ = kb_common.parse_frontmatter(doc)
        self.assertEqual(tags, ["docker", "networking"])

    def test_explicit_empty_inline_tags(self):
        doc = "---\ntitle: T\ntags: []\n---\nB\n"
        _, tags, _, _ = kb_common.parse_frontmatter(doc)
        self.assertEqual(tags, [])

    def test_single_line_tags_value(self):
        doc = "---\ntitle: T\ntags: docker\n---\nB\n"
        _, tags, _, _ = kb_common.parse_frontmatter(doc)
        self.assertEqual(tags, ["docker"])

    def test_tolerant_close_with_trailing_spaces(self):
        doc = "---\ntitle: X\ntags: []\n--- \nBody\n"
        fields, tags, _, body = kb_common.parse_frontmatter(doc)
        self.assertEqual(fields, {"title": "X"})
        self.assertEqual(tags, [])
        self.assertEqual(body, "Body\n")

    def test_tolerant_close_at_end_of_file(self):
        doc = "---\ntitle: X\ntags: [a]\n---"
        fields, tags, _, body = kb_common.parse_frontmatter(doc)
        self.assertEqual(fields, {"title": "X"})
        self.assertEqual(tags, ["a"])
        self.assertEqual(body, "")

    def test_value_containing_colons_survives(self):
        doc = "---\ntitle: CI: What Breaks\ntags: []\n---\nB\n"
        fields, _, _, _ = kb_common.parse_frontmatter(doc)
        self.assertEqual(fields["title"], "CI: What Breaks")


class TestSerializeFrontmatter(unittest.TestCase):
    def test_canonical_yaml_list_output(self):
        self.assertEqual(
            kb_common.serialize_frontmatter(
                {
                    "createdate": "2026-10-09T10:00:00-07:00",
                    "title": "Docker Networking Basics",
                },
                ["docker", "networking"],
                "Body.\n",
            ),
            "---\n"
            "createdate: 2026-10-09T10:00:00-07:00\n"
            "title: Docker Networking Basics\n"
            "tags:\n"
            "  - docker\n"
            "  - networking\n"
            "---\n"
            "Body.\n",
        )

    def test_empty_tags_render_as_inline_empty_array(self):
        self.assertEqual(
            kb_common.serialize_frontmatter({"title": "Solo"}, [], "Body"),
            "---\ntitle: Solo\ntags: []\n---\nBody",
        )

    def test_empty_body_ends_after_closing_marker(self):
        self.assertEqual(
            kb_common.serialize_frontmatter({"title": "Solo"}, [], ""),
            "---\ntitle: Solo\ntags: []\n---\n",
        )


class TestFrontmatterRoundTrip(unittest.TestCase):
    def assert_round_trip(self, doc: str) -> None:
        fields, tags, _, body = kb_common.parse_frontmatter(doc)
        rebuilt = kb_common.serialize_frontmatter(fields, tags, body)
        fields2, tags2, _, body2 = kb_common.parse_frontmatter(rebuilt)
        self.assertEqual(fields2, fields)
        self.assertEqual(tags2, tags)
        self.assertEqual(body2, body)
        self.assertNotIn("id", fields2)

    def test_round_trip_inline_array_document(self):
        self.assert_round_trip(INLINE_DOC)

    def test_round_trip_yaml_list_document(self):
        self.assert_round_trip(YAML_LIST_DOC)

    def test_round_trip_document_with_git_provenance_fields(self):
        self.assert_round_trip(PROVENANCE_DOC)

    def test_round_trip_document_without_frontmatter(self):
        # A body-only document gains an (empty) frontmatter block on the way
        # through and keeps its body verbatim.
        self.assert_round_trip("Just a body.\n")


class TestDocumentIds(unittest.TestCase):
    """The recovered notebook ID generator, now living in kb_common."""

    def test_generate_ulid_short_is_8_crockford_chars(self):
        for _ in range(200):
            self.assertTrue(kb_common.is_valid_ulid_short(
                kb_common.generate_ulid_short()))

    def test_ids_are_unique_within_a_session(self):
        ids = {kb_common.generate_ulid_short() for _ in range(500)}
        self.assertEqual(len(ids), 500)

    def test_generator_matches_the_recovered_original(self):
        # The first 6 characters still come from the millisecond timestamp
        # encoded to Crockford Base32; only the last 2 are random. The
        # clock may tick between sampling and generating, so the stem must
        # match one of the brackets.
        before = kb_common.encode_crockford_base32(
            int(__import__("time").time() * 1000)).lower()[:6]
        ulid = kb_common.generate_ulid_short()
        after = kb_common.encode_crockford_base32(
            int(__import__("time").time() * 1000)).lower()[:6]
        self.assertEqual(len(before), 6)
        self.assertIn(ulid[:6], {before, after},
                      "the timestamp stem must match the clock")

    def test_is_valid_ulid_short_rejects_bad_shapes(self):
        for bad in ("", "1jsj3x7", "1jsj3x7cc", "1JSJ3X7C", "1jsj3il7",
                    "1jsj3x7c ".strip() + "!"):
            self.assertFalse(kb_common.is_valid_ulid_short(bad),
                             f"{bad!r} must not validate")

    def test_ensure_id_keeps_a_valid_id_in_place(self):
        fields = {"id": "1jsj3x7c", "title": "t", "createdate": "d"}
        kept, minted = kb_common.ensure_id(fields)
        self.assertIs(minted, False)
        self.assertEqual(kept, fields)

    def test_ensure_id_mints_and_puts_the_id_first(self):
        fields = {"title": "t", "createdate": "d"}
        new_fields, minted = kb_common.ensure_id(fields)
        self.assertIs(minted, True)
        self.assertEqual(list(new_fields)[0], "id")
        self.assertTrue(kb_common.is_valid_ulid_short(new_fields["id"]))
        self.assertEqual(new_fields["title"], "t")

    def test_ensure_id_replaces_an_invalid_id(self):
        fields = {"id": "notvalid1", "title": "t"}
        new_fields, minted = kb_common.ensure_id(fields)
        self.assertIs(minted, True)
        self.assertNotEqual(new_fields["id"], "notvalid1")
        self.assertTrue(kb_common.is_valid_ulid_short(new_fields["id"]))


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
