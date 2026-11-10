"""Markdown → Atlassian Document Format, so a reviewed Markdown draft posts as rich Jira text
without any agent hand-building ADF."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pipeline import adf  # noqa: E402


def kinds(nodes):
    return [n["type"] for n in nodes]


class ToAdfTest(unittest.TestCase):
    def test_document_shape(self) -> None:
        doc = adf.to_adf("Hello.")
        self.assertEqual((doc["type"], doc["version"]), ("doc", 1))
        self.assertEqual(kinds(doc["content"]), ["paragraph"])

    def test_headings_paragraphs_and_rules(self) -> None:
        doc = adf.to_adf("## Fixed\n\nThe collector works.\nIt refuses bypasses.\n\n---\n\n### Next\n")
        self.assertEqual(kinds(doc["content"]), ["heading", "paragraph", "rule", "heading"])
        self.assertEqual(doc["content"][0]["attrs"], {"level": 2})
        self.assertEqual(adf.text_of(doc["content"][1]), "The collector works. It refuses bypasses.")

    def test_inline_marks(self) -> None:
        para = adf.to_adf("Run `make test`, see **bold**, *italic*, and [the PR](https://x.test/1).")["content"][0]
        marks = {n["text"]: [m["type"] for m in n.get("marks", [])] for n in para["content"]}
        self.assertEqual(marks["make test"], ["code"])
        self.assertEqual(marks["bold"], ["strong"])
        self.assertEqual(marks["italic"], ["em"])
        self.assertEqual(marks["the PR"], ["link"])
        link = next(n for n in para["content"] if n["text"] == "the PR")
        self.assertEqual(link["marks"][0]["attrs"], {"href": "https://x.test/1"})

    def test_lists_nest(self) -> None:
        doc = adf.to_adf("- one\n- two\n  - two a\n  - two b\n- three\n\n1. first\n2. second\n")
        bullets, ordered = doc["content"]
        self.assertEqual((bullets["type"], ordered["type"]), ("bulletList", "orderedList"))
        self.assertEqual(len(bullets["content"]), 3)
        second = bullets["content"][1]
        self.assertEqual(kinds(second["content"]), ["paragraph", "bulletList"])
        self.assertEqual(len(second["content"][1]["content"]), 2)
        self.assertEqual(adf.text_of(ordered), "first second")

    def test_fenced_code_keeps_its_text_and_language(self) -> None:
        doc = adf.to_adf("```bash\nmake test\n  go vet ./...\n```\n")
        block = doc["content"][0]
        self.assertEqual(block["type"], "codeBlock")
        self.assertEqual(block["attrs"], {"language": "bash"})
        self.assertEqual(block["content"][0]["text"], "make test\n  go vet ./...")

    def test_no_markdown_markup_survives_as_text(self) -> None:
        doc = adf.to_adf("## Title\n\n- **bold** and `code`\n\n1. [x](https://x.test)\n")
        self.assertEqual(adf.literal_markup(doc), [])
        self.assertEqual(adf.literal_markup({"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "## not a heading **bold**"}]}]}),
            ["## not a heading **bold**"])


if __name__ == "__main__":
    unittest.main()
