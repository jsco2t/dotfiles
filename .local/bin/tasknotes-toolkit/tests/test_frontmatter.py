"""TaskNotes-shaped, source-preserving Markdown behavior; no external YAML library."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tasknotes_toolkit.frontmatter import Document, FrontmatterError, RawYaml


class FrontmatterTests(unittest.TestCase):
    def test_reads_upstream_style_note_and_keeps_full_markdown_body(self):
        body = "\nReview the quarterly report so finance can approve the budget.\n\n## Acceptance\n\n- Revenue matches the ledger.\n"
        note = "---\ntags:\n  - task\ntitle: Review quarterly report\nstatus: in-progress\npriority: high\nprojects:\n  - \"[[Q1 Planning]]\"\n---\n" + body
        doc = Document.parse(note)
        self.assertEqual(doc.data["tags"], ["task"])
        self.assertEqual(doc.data["projects"], ["[[Q1 Planning]]"])
        self.assertEqual(doc.body, body)
        self.assertEqual(doc.render({}), note)

    def test_targeted_edit_preserves_unknown_yaml_comments_order_and_crlf_body(self):
        note = "\ufeff---\r\n# Human annotation\r\nstatus: open # keep this comment\r\ncustom:\r\n  deep: [one, two]\r\n  reminder: {type: relative, offset: -PT5M}\r\n---\r\n\r\nDo the useful work.\r\n\r\n- [ ] Keep this checkbox.\r\n"
        result = Document.parse(note).render({"status": "done", "completedDate": "2026-11-21"})
        self.assertIn("# Human annotation\r\n", result)
        self.assertIn("# keep this comment\r\n", result)
        self.assertIn("custom:\r\n  deep: [one, two]\r\n  reminder: {type: relative, offset: -PT5M}\r\n", result)
        self.assertEqual(Document.parse(result).body, Document.parse(note).body)
        self.assertEqual(Document.parse(result).data["status"], "done")
        self.assertTrue(result.startswith("\ufeff---\r\n"))

    def test_supports_flow_values_nested_tasknotes_objects_and_quoted_keys(self):
        note = "---\n'Task title': 'Fix the user''s login'\ntags: [task, work]\nprojects: [\"[[Project: Alpha]]\", 'Project B']\nblockedBy:\n  - uid: \"[[Prepare environment]]\"\n    reltype: FINISHTOSTART\n    gap: PT1H\nreminders:\n  - id: reminder-1\n    type: absolute\n    absoluteTime: 2026-11-21T09:00:00Z\n---\n\nFix login.\n"
        doc = Document.parse(note)
        self.assertEqual(doc.data["Task title"], "Fix the user's login")
        self.assertEqual(doc.data["projects"], ["[[Project: Alpha]]", "Project B"])
        self.assertEqual(doc.data["blockedBy"][0], dict(uid="[[Prepare environment]]", reltype="FINISHTOSTART", gap="PT1H"))
        self.assertEqual(doc.data["reminders"][0]["absoluteTime"], "2026-11-21T09:00:00Z")

    def test_scalar_quoting_round_trips_multiline_unicode_and_yaml_looking_strings(self):
        fields = {"title": "Fix: café #42", "status": "open", "tags": ["task", "yes"],
                  "notes": "First paragraph.\n\nSecond paragraph.", "custom": {"on": "false", "count": 0, "enabled": True},
                  "projects": ["[[Alpha|Alias]]"], "empty": []}
        rendered = Document.parse("").render(fields, body="\nMake the expected behavior clear.\n")
        self.assertEqual(Document.parse(rendered).data, fields)
        self.assertEqual(Document.parse(rendered).body, "\nMake the expected behavior clear.\n")

    def test_literal_and_folded_strings_and_unindented_sequences(self):
        doc = Document.parse("---\ntitle: >-\n  Fix login\n  for returning users\ntags:\n- task\n- work\nexplanation: |\n  Keep # literal text.\n  Keep the next line.\n---\nDescription.\n")
        self.assertEqual(doc.data["title"], "Fix login for returning users")
        self.assertEqual(doc.data["tags"], ["task", "work"])
        self.assertEqual(doc.data["explanation"], "Keep # literal text.\nKeep the next line.\n")

    def test_duplicate_keys_and_unterminated_frontmatter_are_refused(self):
        for note in ("---\nstatus: open\nstatus: done\n---\nBody.", "---\nstatus: open\nBody."):
            with self.subTest(note=note), self.assertRaises(FrontmatterError):
                Document.parse(note)

    def test_unknown_anchored_values_remain_raw_and_cannot_be_rewritten(self):
        note = "---\ntags: [task]\nstatus: open\ncustom: &anchor {keep: true}\ncopy: *anchor\n---\nReadable body.\n"
        doc = Document.parse(note)
        self.assertIsInstance(doc.data["custom"], RawYaml)
        self.assertIn("custom: &anchor {keep: true}\ncopy: *anchor\n", doc.render({"status": "done"}))
        with self.assertRaises(FrontmatterError):
            doc.render({"custom": "overwrite an anchor"})

    def test_body_replacement_is_explicit_and_field_removal_does_not_rebuild_others(self):
        note = "---\ntags: [task]\ndue: 2026-11-22\n# Useful context\ncustom: 'unchanged'\n---\nOld description.\n"
        result = Document.parse(note).render({"due": None}, body="Deliver a clear result.\n\nExplain how to verify it.\n")
        self.assertNotIn("due:", result)
        self.assertIn("# Useful context\ncustom: 'unchanged'\n", result)
        self.assertEqual(Document.parse(result).body, "Deliver a clear result.\n\nExplain how to verify it.\n")

    def test_nested_tasknotes_object_lists_round_trip_through_canonical_writer(self):
        fields = {"tags": ["task"], "blockedBy": [{"uid": "[[Prepare]]", "reltype": "FINISHTOSTART"}],
                  "reminders": [{"id": "notify", "type": "relative", "relatedTo": "due", "offset": "-PT5M"}]}
        self.assertEqual(Document.parse(Document.parse("").render(fields)).data, fields)

    def test_literal_block_preserves_blank_lines_and_hash_lines_as_content(self):
        doc = Document.parse("---\nnotes: |\n  First paragraph.\n\n  # This is literal content.\n  Next paragraph.\n---\nBody.\n")
        self.assertEqual(doc.data["notes"], "First paragraph.\n\n# This is literal content.\nNext paragraph.\n")


if __name__ == "__main__":
    unittest.main()
