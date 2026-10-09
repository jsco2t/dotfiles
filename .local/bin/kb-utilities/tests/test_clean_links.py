#!/usr/bin/env python3
"""Tests for the ported doc_fix.py and fix_wiki_links.py in kb-utilities.

Run from the kb-utilities directory:

    python3 tests/test_clean_links.py -v

or from the dotfiles repository root:

    python3 .local/bin/kb-utilities/tests/test_clean_links.py -v

The contract pinned here (ported from notebook .tools with new-convention
changes; every expected value is hand-computed and was cross-checked against
the original scripts on throwaway fixtures in /tmp):

doc_fix.py --json PATH...
    Emits exactly the keys {total, changed, skipped, toc_fixed,
    frontmatter_added_dirs, results} and parses as one JSON document.
    total counts every scanned markdown file; changed counts non-skipped
    files whose action is not "none"; skipped counts files it could not
    process (empty files); results holds only the changed entries with the
    per-file keys file, action, tags_before, tags_after, normalized,
    suggested, added_frontmatter, skipped, reason, toc_fixed, toc_entries.
    Tag normalization maps synonyms (golang→go, kubernetes→k8s,
    JavaScript→js, ...), dedupes after normalization, drops blocklisted
    tags (sh, yaml, json, toml) and caps the list at ten tags. A stale
    "## Table of Contents" section is rebuilt from the ## headings outside
    code fences, numbered, with GitHub-style anchors. A file without
    frontmatter gains one whose title is kb_common.title_from_filename of
    the filename stem (no ID-prefix stripping) and whose createdate is
    ISO 8601 with a -07:00 offset; it carries no id field. --dry-run
    reports the same changes but writes nothing. Directories named in
    kb_common.EXCLUDED_DIRS and hidden directories are never scanned.

fix_wiki_links.py --mapping-file FILE|--json|--dry-run
    The mapping is a JSON array of {"old", "new"} basename pairs; .md
    suffixes are optional; when --mapping-file is omitted the mapping is
    read from stdin. The scan root is the current working directory (the
    notebook version derived the vault from the script location, which
    does not translate to the dotfiles install, so run it from the vault
    root). Every wikilink form is rewritten by stem: [[stem]],
    [[stem|alias]], [[stem#heading]], [[stem#heading|alias]] and ![[stem]]
    embeds, including path-based links whose basename matches. Links to
    other targets, heading-only links and links inside code fences are
    left untouched. --json emits exactly {files_scanned, files_updated,
    links_fixed, updates} with update entries {file, line, old_link,
    new_link} and 1-based line numbers. An empty mapping exits 0 with
    zero counts and scans nothing; an unloadable mapping exits 1 with a
    message on stderr.

Both scripts import standard-library modules plus the shared kb_common,
and contain no ID-prefix or ID-generation logic.
"""

import ast
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import kb_common

UTILS_DIR = Path(__file__).resolve().parents[1]
DOC_FIX = UTILS_DIR / "doc_fix.py"
FIX_LINKS = UTILS_DIR / "fix_wiki_links.py"

# ── Shared helpers ──────────────────────────────────────────────────────────


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


def write_doc(root: Path, rel: str, content: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def read_doc(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def run_script(
    script: Path,
    args: list[str],
    cwd: Path,
    stdin_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        input=stdin_text,
        timeout=120,
    )


def snapshot(root: Path) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


# ── doc_fix fixtures ────────────────────────────────────────────────────────

NAMING_DOC = (
    "---\n"
    "createdate: 2026-10-09T10:00:00-07:00\n"
    "title: Test Doc\n"
    "tags: [golang, go, Kubernetes, yaml, sh, JavaScript]\n"
    "---\n"
    "\n"
    "Some notes live here.\n"
)

# Twelve tags; none is blocklisted and none duplicates another after
# normalization, so the ten-tag cap alone decides the outcome.
CAP_TAGS = [
    "kubernetes", "golang", "python", "javascript", "ruby", "mac",
    "nvim", "database", "terminal", "rest-api", "rocky-linux",
    "machine-learning",
]
CAP_TAGS_AFTER = [
    "k8s", "go", "py", "js", "rb", "macos", "neovim", "db", "cli", "api",
]
CAP_DOC = (
    "---\n"
    "title: Doc\n"
    "tags: [%s]\n"
    "---\n"
    "\n"
    "Notes.\n" % ", ".join(CAP_TAGS)
)

TOC_DOC = (
    "---\n"
    "createdate: 2026-10-09T10:00:00-07:00\n"
    "title: TOC Notes\n"
    "tags: [golang]\n"
    "---\n"
    "\n"
    "## Table of Contents\n"
    "\n"
    "1. [Stale Entry](#stale-entry)\n"
    "\n"
    "## Install Steps\n"
    "\n"
    "Install things.\n"
    "\n"
    "## Use It\n"
    "\n"
    "```text\n"
    "## Fake Heading In Fence\n"
    "```\n"
    "\n"
    "## Final Notes\n"
    "\n"
    "Done.\n"
)

BARE_DOC = "Plain notes only.\n"

LEGACY_NAME = "1ab2c3d4_old_style_note.md"
LEGACY_DOC = "Old style note.\n"

EXCLUDED_DOC = (
    "---\n"
    "tags: [golang]\n"
    "---\n"
    "\n"
    "## Table of Contents\n"
    "\n"
    "1. [Stale](#stale)\n"
)


def make_doc_fixtures(root: Path) -> None:
    write_doc(root, "normalize/kb-naming.md", NAMING_DOC)
    write_doc(root, "normalize/tags-cap.md", CAP_DOC)
    write_doc(root, "notes/toc.md", TOC_DOC)
    write_doc(root, "plain/docker-networking-basics.md", BARE_DOC)
    write_doc(root, "plain/" + LEGACY_NAME, LEGACY_DOC)
    write_doc(root, "plain/empty.md", "")
    write_doc(root, "templates/excluded.md", EXCLUDED_DOC)
    write_doc(root, ".obsidian/hidden.md", "untouched\n")


def run_doc_fix(root: Path, *extra: str) -> dict:
    proc = run_script(DOC_FIX, ["--json", str(root), *extra], cwd=root)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def result_for(out: dict, name: str) -> dict:
    """Return the changed-file result whose reported path ends with name."""
    matches = [r for r in out["results"] if r["file"].endswith(name)]
    assert len(matches) == 1, f"expected exactly one result for {name}: {matches}"
    return matches[0]


# ── fix_wiki_links fixtures ─────────────────────────────────────────────────

OLD_STEM = "docker-networking-basics"
NEW_STEM = "docker-networking"
MAPPING = [{"old": f"{OLD_STEM}.md", "new": f"{NEW_STEM}.md"}]
BARE_MAPPING = [{"old": OLD_STEM, "new": NEW_STEM}]

NOTES_BEFORE = (
    "See [[docker-networking-basics]] and [[docker-networking-basics|Docker Net]].\n"
    "Also [[docker-networking-basics#Install Steps]] and "
    "[[docker-networking-basics#Install Steps|setup]].\n"
    "Embed: ![[docker-networking-basics]]\n"
    "Path form: [[kb/docker-networking-basics]]\n"
    "Untouched: [[docker-networking]] [[#install-steps]] [[unrelated-note]].\n"
)
NOTES_AFTER = (
    "See [[docker-networking]] and [[docker-networking|Docker Net]].\n"
    "Also [[docker-networking#Install Steps]] and "
    "[[docker-networking#Install Steps|setup]].\n"
    "Embed: ![[docker-networking]]\n"
    "Path form: [[kb/docker-networking]]\n"
    "Untouched: [[docker-networking]] [[#install-steps]] [[unrelated-note]].\n"
)
FENCED_BEFORE = (
    "Real: [[docker-networking-basics]]\n"
    "\n"
    "```text\n"
    "[[docker-networking-basics]]\n"
    "```\n"
)
FENCED_AFTER = (
    "Real: [[docker-networking]]\n"
    "\n"
    "```text\n"
    "[[docker-networking-basics]]\n"
    "```\n"
)
INDEX_BEFORE = "| Doc | [[docker-networking-basics]] |\n"
INDEX_AFTER = "| Doc | [[docker-networking]] |\n"


def make_link_fixtures(root: Path) -> None:
    # Scanned: kb/docker-networking.md, kb/notes.md, kb/fenced.md,
    # learning/index.md (templates/ is excluded, so its link survives).
    write_doc(root, "kb/docker-networking.md", "The renamed document.\n")
    write_doc(root, "kb/notes.md", NOTES_BEFORE)
    write_doc(root, "kb/fenced.md", FENCED_BEFORE)
    write_doc(root, "learning/index.md", INDEX_BEFORE)
    write_doc(root, "templates/link.md", "[[docker-networking-basics]]\n")


def run_link_fix(
    root: Path,
    *extra: str,
    stdin_text: str | None = None,
    mapping_file: Path | None = None,
) -> dict:
    args = ["--json", *extra]
    if mapping_file is not None:
        args += ["--mapping-file", str(mapping_file)]
    proc = run_script(FIX_LINKS, args, cwd=root, stdin_text=stdin_text)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# ── doc_fix: tags ───────────────────────────────────────────────────────────


class TestDocFixTagNormalization(unittest.TestCase):
    def setUp(self):
        if not DOC_FIX.exists():
            self.fail(f"doc_fix.py not found at {DOC_FIX}; these tests are "
                      "written first and stay red until the port lands")
        self.root = Path(tempfile.mkdtemp(prefix="docfix-", dir="/tmp/opencode"))
        make_doc_fixtures(self.root)

    def test_normalizes_and_dedupes_tags(self):
        out = run_doc_fix(self.root)
        res = result_for(out, "kb-naming.md")
        self.assertEqual(res["tags_before"],
                         ["golang", "go", "Kubernetes", "yaml", "sh", "JavaScript"])
        # Synonyms map, duplicates collapse, blocklisted sh/yaml are dropped.
        self.assertEqual(res["tags_after"], ["go", "k8s", "js"])
        self.assertEqual(res["normalized"],
                         {"golang": "go", "Kubernetes": "k8s", "JavaScript": "js"})
        _, tags, _, _ = kb_common.parse_frontmatter(
            read_doc(self.root, "normalize/kb-naming.md"))
        self.assertEqual(tags, ["go", "k8s", "js"])

    def test_caps_tags_at_ten(self):
        out = run_doc_fix(self.root)
        res = result_for(out, "tags-cap.md")
        self.assertEqual(res["tags_after"], CAP_TAGS_AFTER)
        _, tags, _, _ = kb_common.parse_frontmatter(
            read_doc(self.root, "normalize/tags-cap.md"))
        self.assertEqual(tags, CAP_TAGS_AFTER)


# ── doc_fix: TOC ────────────────────────────────────────────────────────────


class TestDocFixToc(unittest.TestCase):
    def setUp(self):
        if not DOC_FIX.exists():
            self.fail(f"doc_fix.py not found at {DOC_FIX}; these tests are "
                      "written first and stay red until the port lands")
        self.root = Path(tempfile.mkdtemp(prefix="docfix-", dir="/tmp/opencode"))
        make_doc_fixtures(self.root)

    def test_rebuilds_stale_toc_from_headings(self):
        out = run_doc_fix(self.root)
        res = result_for(out, "toc.md")
        self.assertTrue(res["toc_fixed"])
        self.assertEqual(res["toc_entries"], 3)
        content = read_doc(self.root, "notes/toc.md")
        self.assertIn("1. [Install Steps](#install-steps)", content)
        self.assertIn("2. [Use It](#use-it)", content)
        self.assertIn("3. [Final Notes](#final-notes)", content)
        self.assertNotIn("[Stale Entry]", content)
        # The fenced line is body text, not a heading: it stays in the
        # fence and never enters the TOC.
        self.assertIn("```text\n## Fake Heading In Fence\n```", content)


# ── doc_fix: added frontmatter ──────────────────────────────────────────────


class TestDocFixFrontmatter(unittest.TestCase):
    def setUp(self):
        if not DOC_FIX.exists():
            self.fail(f"doc_fix.py not found at {DOC_FIX}; these tests are "
                      "written first and stay red until the port lands")
        self.root = Path(tempfile.mkdtemp(prefix="docfix-", dir="/tmp/opencode"))
        make_doc_fixtures(self.root)

    def test_adds_frontmatter_with_kb_common_title(self):
        out = run_doc_fix(self.root)
        res = result_for(out, "docker-networking-basics.md")
        self.assertEqual(res["action"], "add_frontmatter")
        self.assertTrue(res["added_frontmatter"])
        fields, tags, _, _ = kb_common.parse_frontmatter(
            read_doc(self.root, "plain/docker-networking-basics.md"))
        # The title follows the shared naming rule: dashes become spaces,
        # lowercase, no ID-prefix handling.
        self.assertEqual(fields["title"], "docker networking basics")
        self.assertEqual(fields["title"],
                         kb_common.title_from_filename("docker-networking-basics"))
        self.assertNotIn("id", fields)
        self.assertRegex(fields["createdate"],
                         r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}-07:00$")
        # The body carries no taggable keywords, so the tags stay empty.
        self.assertEqual(tags, [])

    def test_keeps_id_prefix_in_derived_title(self):
        # An old-convention ID-prefixed filename is doc_fix's input, not its
        # concern: the stem maps to the title verbatim via kb_common rules.
        out = run_doc_fix(self.root)
        result_for(out, LEGACY_NAME)
        fields, _, _, _ = kb_common.parse_frontmatter(read_doc(self.root, "plain/" + LEGACY_NAME))
        self.assertEqual(fields["title"], "1ab2c3d4_old_style_note")
        self.assertTrue(fields["title"].startswith("1ab2c3d4"))


# ── doc_fix: dry run and JSON shape ─────────────────────────────────────────


class TestDocFixDryRunAndJson(unittest.TestCase):
    def setUp(self):
        if not DOC_FIX.exists():
            self.fail(f"doc_fix.py not found at {DOC_FIX}; these tests are "
                      "written first and stay red until the port lands")
        self.root = Path(tempfile.mkdtemp(prefix="docfix-", dir="/tmp/opencode"))
        make_doc_fixtures(self.root)

    def test_dry_run_reports_changes_but_writes_nothing(self):
        before = snapshot(self.root)
        out = run_doc_fix(self.root, "--dry-run")
        self.assertEqual(snapshot(self.root), before)
        # Six scanned files, five changed, the empty file skipped, one TOC.
        self.assertEqual(out["total"], 6)
        self.assertEqual(out["changed"], 5)
        self.assertEqual(out["skipped"], 1)
        self.assertEqual(out["toc_fixed"], 1)

    def test_json_emits_documented_keys_and_counts(self):
        out = run_doc_fix(self.root)
        self.assertEqual(
            set(out),
            {"total", "changed", "skipped", "toc_fixed",
             "frontmatter_added_dirs", "results"},
        )
        self.assertEqual(out["total"], 6)
        self.assertEqual(out["changed"], 5)
        self.assertEqual(out["skipped"], 1)
        self.assertEqual(out["toc_fixed"], 1)
        self.assertEqual(len(out["results"]), 5)
        documented_result_keys = {
            "file", "action", "tags_before", "tags_after", "normalized",
            "suggested", "added_frontmatter", "skipped", "reason",
            "toc_fixed", "toc_entries",
        }
        for res in out["results"]:
            self.assertFalse(res["skipped"])
            self.assertTrue(documented_result_keys.issubset(res),
                            f"missing {documented_result_keys - set(res)}")
        # Both frontmatter-less fixtures live in plain/, so exactly one
        # directory is reported, by its plain name.
        self.assertEqual([Path(d).name for d in out["frontmatter_added_dirs"]],
                         ["plain"])

    def test_excluded_dirs_are_never_scanned_or_written(self):
        run_doc_fix(self.root)
        self.assertEqual(read_doc(self.root, "templates/excluded.md"),
                         EXCLUDED_DOC)
        self.assertEqual(read_doc(self.root, ".obsidian/hidden.md"), "untouched\n")
        self.assertEqual(read_doc(self.root, "plain/empty.md"), "")


# ── fix_wiki_links ──────────────────────────────────────────────────────────


class TestFixWikiLinks(unittest.TestCase):
    def setUp(self):
        if not FIX_LINKS.exists():
            self.fail(f"fix_wiki_links.py not found at {FIX_LINKS}; these "
                      "tests are written first and stay red until the port "
                      "lands")
        self.root = Path(tempfile.mkdtemp(prefix="wikilink-", dir="/tmp/opencode"))
        make_link_fixtures(self.root)

    def apply_mapping_and_assert_rewrites(self) -> dict:
        mapping = write_doc(self.root.parent, self.root.name + "-mapping.json",
                            json.dumps(MAPPING))
        out = run_link_fix(self.root, mapping_file=mapping)
        self.assertEqual(read_doc(self.root, "kb/notes.md"), NOTES_AFTER)
        self.assertEqual(read_doc(self.root, "kb/fenced.md"), FENCED_AFTER)
        self.assertEqual(read_doc(self.root, "learning/index.md"), INDEX_AFTER)
        self.assertEqual(read_doc(self.root, "kb/docker-networking.md"),
                         "The renamed document.\n")
        # templates/ is excluded, so its link to the old stem survives.
        self.assertEqual(read_doc(self.root, "templates/link.md"),
                         "[[docker-networking-basics]]\n")
        return out

    def test_rewrites_all_link_forms_via_mapping_file(self):
        self.apply_mapping_and_assert_rewrites()

    def test_json_counts_and_update_entries(self):
        out = self.apply_mapping_and_assert_rewrites()
        self.assertEqual(set(out),
                         {"files_scanned", "files_updated", "links_fixed",
                          "updates"})
        self.assertEqual(out["files_scanned"], 4)
        self.assertEqual(out["files_updated"], 3)
        self.assertEqual(out["links_fixed"], 8)
        self.assertEqual(len(out["updates"]), 8)
        for update in out["updates"]:
            self.assertEqual(set(update), {"file", "line", "old_link",
                                           "new_link"})
            self.assertIn(OLD_STEM, update["old_link"])
            self.assertIn(NEW_STEM, update["new_link"])

    def test_stdin_mapping_with_bare_stems(self):
        out = run_link_fix(self.root, stdin_text=json.dumps(BARE_MAPPING))
        self.assertEqual(read_doc(self.root, "kb/notes.md"), NOTES_AFTER)
        self.assertEqual(out["links_fixed"], 8)

    def test_dry_run_reports_updates_but_writes_nothing(self):
        mapping = write_doc(self.root.parent, self.root.name + "-mapping.json",
                            json.dumps(MAPPING))
        before = snapshot(self.root)
        out = run_link_fix(self.root, "--dry-run", mapping_file=mapping)
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(out["files_scanned"], 4)
        self.assertEqual(out["files_updated"], 3)
        self.assertEqual(out["links_fixed"], 8)

    def test_empty_mapping_is_a_noop(self):
        before = snapshot(self.root)
        proc = run_script(FIX_LINKS, ["--json"], cwd=self.root, stdin_text="")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(set(out),
                         {"files_scanned", "files_updated", "links_fixed",
                          "updates"})
        self.assertEqual(out["files_scanned"], 0)
        self.assertEqual(out["files_updated"], 0)
        self.assertEqual(out["links_fixed"], 0)
        self.assertEqual(out["updates"], [])
        self.assertEqual(snapshot(self.root), before)

    def test_invalid_mapping_file_exits_1(self):
        mapping = write_doc(self.root.parent, self.root.name + "-bad.json",
                            "{not json")
        proc = run_script(FIX_LINKS, ["--mapping-file", str(mapping)],
                          cwd=self.root)
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(proc.stderr.strip())


# ── ported-script conventions ───────────────────────────────────────────────


class TestPortedScriptConventions(unittest.TestCase):
    def setUp(self):
        missing = [p for p in (DOC_FIX, FIX_LINKS) if not p.exists()]
        if missing:
            self.fail(f"not ported yet: {', '.join(p.name for p in missing)}; "
                      "these tests are written first and stay red until the "
                      "port lands")

    def test_scripts_import_stdlib_only(self):
        allowed = set(sys.stdlib_module_names) | {"kb_common"}
        for source in (DOC_FIX, FIX_LINKS):
            with self.subTest(source=source.name):
                modules = collect_top_level_imports(source)
                self.assertEqual(
                    modules - allowed,
                    set(),
                    f"{source.name} imports non-stdlib modules: "
                    f"{sorted(modules - allowed)}",
                )

    def test_no_id_prefix_or_id_generation_logic(self):
        for source in (DOC_FIX, FIX_LINKS):
            with self.subTest(source=source.name):
                src = source.read_text(encoding="utf-8").lower()
                for marker in ("ulid", "crockford", "generate_"):
                    self.assertNotIn(marker, src,
                                     f"{source.name} carries ID-generation "
                                     f"logic ({marker})")
                self.assertIsNone(
                    re.search(r"\[0-9a-z\]\{8\}", src),
                    f"{source.name} still strips the 8-char ID filename "
                    "prefix",
                )


if __name__ == "__main__":
    unittest.main()
