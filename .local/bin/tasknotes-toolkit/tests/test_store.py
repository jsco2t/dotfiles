"""Public API lifecycle, data integrity and safe local file behavior."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tasknotes_toolkit.store import TaskStore
from tasknotes_toolkit.model import TaskError

DESCRIPTION = "Fix login timeouts so returning users can sign in reliably.\n\nThe current session expires during a retry. Preserve successful sign-ins.\n\n## Acceptance\n\n- A retry succeeds without a second password prompt.\n\n## Verification\n\nRun the session regression tests.\n"


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tasknotes-store-")
        self.root = Path(self.temp.name) / "tasks"
        self.store = TaskStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def create(self, title="Fix login", **fields):
        return self.store.create(title, DESCRIPTION, **fields)

    def test_create_read_edit_complete_reopen_archive_and_delete(self):
        task = self.create(projects=["[[Alpha]]"], priority="high")
        self.assertEqual(task.fields["status"], "open")
        self.assertEqual(task.description, DESCRIPTION)
        self.assertEqual(self.store.get(task.id).path, task.path)
        created = task.fields["dateCreated"]
        edited = self.store.edit(task.id, {"priority": "low", "due": "2026-12-01"}, expected_revision=task.revision)
        self.assertEqual(edited.fields["priority"], "low")
        done = self.store.complete(task.id, on="2026-11-21", note="Session regression tests pass.")
        self.assertEqual(done.fields["completedDate"], "2026-11-21")
        self.assertEqual(done.fields["status"], "done")
        self.assertIn("Session regression tests pass.", done.description)
        self.assertEqual(self.store.complete(task.id, on="2026-11-21").revision, done.revision)
        reopened = self.store.reopen(task.id)
        self.assertNotIn("completedDate", reopened.fields)
        self.assertEqual(reopened.fields["dateCreated"], created)
        self.store.archive(task.id)
        self.assertEqual(self.store.list(), [])
        self.assertEqual(len(self.store.list(include_archived=True)), 1)
        self.store.archive(task.id, archived=False)
        self.store.delete(task.id)
        self.assertFalse((self.root / task.path).exists())

    def test_project_filter_ready_limit_priorities_claims_and_future_schedule(self):
        low = self.create("Low", projects=["[[Alpha]]"], priority="low")
        high = self.create("High", projects=["[[Alpha]]"], priority="high")
        self.create("Other", projects=["[[Beta]]"], priority="high")
        self.create("Future", projects=["[[Alpha]]"], scheduled="2099-01-01")
        self.assertEqual([t.id for t in self.store.ready(project="Alpha", limit=2)], [high.id, low.id])
        started = self.store.start(high.id, expected_revision=high.revision)
        self.assertEqual(started.fields["status"], "in-progress")
        self.assertEqual([t.id for t in self.store.ready(project="[[Alpha]]", limit=1)], [low.id])
        self.assertEqual(len(self.store.list(project="Beta")), 1)
        with self.assertRaises(TaskError):
            self.store.ready(limit=0)

    def test_unresolved_dependencies_block_and_completion_unblocks(self):
        first = self.create("Prepare environment")
        second = self.create("Run migration", blockedBy=[dict(uid=first.id, reltype="FINISHTOSTART")])
        self.create("Missing dependency", blockedBy=[dict(uid="[[Unknown task]]", reltype="FINISHTOSTART")])
        self.assertEqual([t.id for t in self.store.ready(limit=10)], [first.id])
        self.store.complete(first.id)
        self.assertEqual([t.id for t in self.store.ready(limit=10)], [second.id])
        with self.assertRaises(TaskError):
            self.store.edit(second.id, {"blockedBy": [dict(uid=second.id, reltype="FINISHTOSTART")]})

    def test_revision_conflicts_do_not_overwrite_human_edits(self):
        task = self.create()
        path = self.root / task.path
        path.write_text(path.read_text() + "\nA human added useful context.\n")
        before = path.read_bytes()
        with self.assertRaises(TaskError) as caught:
            self.store.edit(task.id, {"priority": "high"}, expected_revision=task.revision)
        self.assertEqual(caught.exception.code, "conflict")
        self.assertEqual(path.read_bytes(), before)

    def test_preview_and_reads_never_create_directories_or_write_files(self):
        preview = self.create(dry_run=True)
        self.assertFalse(self.root.exists())
        self.assertEqual(preview.description, DESCRIPTION)
        task = self.create()
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.store.complete(task.id, dry_run=True)
        self.store.delete(task.id, dry_run=True)
        self.store.get(task.id)
        self.store.list()
        after = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_invalid_values_path_escape_symlinks_and_unsupported_yaml_never_write(self):
        task = self.create()
        before = (self.root / task.path).read_bytes()
        for fields in ({"due": "2026-02-30"}, {"projects": "Alpha"}, {"id": "changed"}):
            with self.subTest(fields=fields), self.assertRaises(TaskError):
                self.store.edit(task.id, fields)
        self.assertEqual((self.root / task.path).read_bytes(), before)
        outside = Path(self.temp.name) / "outside.md"
        outside.write_text("Keep outside.")
        (self.root / "escape.md").symlink_to(outside)
        for ref in ("../outside.md", str(outside), "escape.md"):
            with self.subTest(ref=ref), self.assertRaises(TaskError):
                self.store.delete(ref)
        self.assertEqual(outside.read_text(), "Keep outside.")
        path = self.root / task.path
        path.write_text(path.read_text().replace('status: "open"', 'status: *unknown'))
        invalid = path.read_bytes()
        with self.assertRaises(TaskError):
            self.store.complete(task.path)
        self.assertEqual(path.read_bytes(), invalid)

    def test_targeted_mutations_preserve_custom_fields_body_and_attachments(self):
        task = self.create()
        path = self.root / task.path
        text = path.read_text().replace('status: "open"', 'status: open # human status note')
        text = text.replace("---\n", "---\ncustom:\n  owner: 'Human'\n  anchored: &keep {a: 1}\n", 1)
        path.write_text(text)
        self.store.edit(task.path, {"priority": "high"})
        result = path.read_text()
        self.assertIn("custom:\n  owner: 'Human'\n  anchored: &keep {a: 1}\n", result)
        self.assertIn(DESCRIPTION, result)
        attachment = self.root / "proof.txt"
        attachment.write_text("Evidence.")
        self.store.edit(task.path, {"attachments": ["proof.txt"]})
        self.store.delete(task.path)
        self.assertEqual(attachment.read_text(), "Evidence.")

    def test_generic_status_edits_obey_completion_and_recurring_guards(self):
        task = self.create()
        done = self.store.edit(task.id, {"status": "done"})
        self.assertIn("completedDate", done.fields)
        opened = self.store.edit(task.id, {"status": "open"})
        self.assertNotIn("completedDate", opened.fields)
        recurring = self.create("Weekly review", recurrence="FREQ=WEEKLY;BYDAY=MO", scheduled="2026-11-23")
        before = (self.root / recurring.path).read_bytes()
        for action in (lambda: self.store.complete(recurring.id), lambda: self.store.edit(recurring.id, {"status": "done"})):
            with self.assertRaises(TaskError) as caught:
                action()
            self.assertEqual(caught.exception.code, "unsupported_recurrence")
        self.assertEqual((self.root / recurring.path).read_bytes(), before)

    def test_settings_are_optional_native_json_and_do_not_change_task_directory(self):
        self.root.mkdir()
        (self.root / ".tasknotes-toolkit.json").write_text(json.dumps(dict(
            fieldMapping={"status": "state", "completedDate": "finished"},
            customStatuses=[dict(value="todo"), dict(value="doing"), dict(value="shipped", isCompleted=True)],
            defaultTaskStatus="todo", activeStatus="doing", taskIdentificationMethod="property", taskPropertyName="type", taskPropertyValue="task")))
        store = TaskStore(self.root)
        task = store.create("Mapped task", DESCRIPTION)
        self.assertIn('state: "todo"', (self.root / task.path).read_text())
        completed = store.complete(task.id, on="2026-11-21")
        self.assertEqual(completed.fields["status"], "shipped")
        self.assertIn('finished: "2026-11-21"', (self.root / task.path).read_text())

    def test_duplicate_titles_are_safe_and_failed_replacement_is_atomic(self):
        first, second = self.create(), self.create()
        self.assertNotEqual(first.path, second.path)
        self.assertNotEqual(first.id, second.id)
        path = self.root / first.path
        old = path.read_bytes()
        with patch("tasknotes_toolkit.store.os.replace", side_effect=OSError("simulated disk error")):
            with self.assertRaises(TaskError):
                self.store.edit(first.id, {"priority": "high"})
        self.assertEqual(path.read_bytes(), old)
        self.assertEqual(len(list(self.root.glob("*.md"))), 2)

    def test_notes_are_appended_without_replacing_the_human_description(self):
        task = self.create()
        updated = self.store.add_note(task.id, "The retry test now reproduces the failure.", section="Progress")
        self.assertTrue(updated.description.startswith(DESCRIPTION))
        self.assertIn("## Progress", updated.description)
        self.assertIn("The retry test now reproduces the failure.", updated.description)

    def test_mapped_storage_keys_cannot_bypass_completion_validation(self):
        store = TaskStore(self.root, config={"fieldMapping": {"status": "state"}})
        task = store.create("Mapped task", DESCRIPTION)
        result = store.edit(task.id, {"state": "done"})
        self.assertEqual(result.fields["status"], "done")
        self.assertIn("completedDate", result.fields)
        self.assertEqual(store.validate(task.id)[0]["issues"], [])

    def test_indented_frontmatter_markers_remain_literal_content(self):
        task = self.create()
        path = self.root / task.path
        original = path.read_text().replace("---\n", "---\ncustom: |\n  Keep this block.\n  ---\n  Keep this too.\n  ...\n", 1)
        path.write_text(original)
        self.store.complete(task.id)
        result = path.read_text()
        self.assertIn("custom: |\n  Keep this block.\n  ---\n  Keep this too.\n  ...\n", result)
        self.assertIn(DESCRIPTION, result)
        self.assertEqual(self.store.get(task.id).fields["status"], "done")

    def test_convenience_mutations_preserve_an_external_edit_even_with_none_revision(self):
        task = self.create()
        path = self.root / task.path
        original_note = self.store._note

        def simultaneous_human_note(body, text, section):
            path.write_text(path.read_text() + "\nA human supplied additional acceptance context.\n")
            return original_note(body, text, section)

        with patch.object(self.store, "_note", side_effect=simultaneous_human_note):
            with self.assertRaises(TaskError) as caught:
                self.store.complete(task.id, note="Tests passed.", expected_revision=None)
        self.assertEqual(caught.exception.code, "conflict")
        self.assertIn("A human supplied additional acceptance context.", path.read_text())

    def test_mapped_create_values_receive_the_same_completion_rules_as_edit(self):
        store = TaskStore(self.root, config={"fieldMapping": {"status": "state"}})
        task = store.create("Mapped create", DESCRIPTION, state="done")
        self.assertEqual(task.fields["status"], "done")
        self.assertIn("completedDate", task.fields)
        self.assertEqual(store.validate(task.id)[0]["issues"], [])

    def test_repeated_completion_with_the_same_evidence_is_a_noop(self):
        task = self.create()
        first = self.store.complete(task.id, note="Regression and integration checks pass.")
        second = self.store.complete(task.id, note="Regression and integration checks pass.")
        self.assertEqual(first.revision, second.revision)
        self.assertEqual(second.description.count("Regression and integration checks pass."), 1)

    def test_complete_preserves_an_existing_configured_completed_status(self):
        store = TaskStore(self.root, config=dict(customStatuses=[dict(value="open"), dict(value="done", isCompleted=True), dict(value="shipped", isCompleted=True)]))
        task = store.create("Already shipped", DESCRIPTION, status="shipped")
        self.assertEqual(store.complete(task.id).fields["status"], "shipped")

    def test_ready_refuses_malformed_metadata_with_a_structured_error(self):
        task = self.create()
        path = self.root / task.path
        path.write_text(path.read_text().replace('priority: "normal"', 'priority: {invalid: object}'))
        before = path.read_bytes()
        with self.assertRaises(TaskError):
            self.store.ready(limit=1)
        self.assertEqual(path.read_bytes(), before)

    def test_validation_handles_invalid_nested_instance_values_without_crashing(self):
        task = self.create()
        path = self.root / task.path
        path.write_text(path.read_text().replace("---\n", '---\ncomplete_instances: [{bad: value}]\nskipped_instances: ["2026-11-21"]\n', 1))
        issues = self.store.validate(task.id)[0]["issues"]
        self.assertIn("complete_instances", [issue["field"] for issue in issues])

    def test_duplicate_caller_supplied_ids_are_refused_before_publishing(self):
        first = self.create("First", id="stable-imported-id")
        with self.assertRaises(TaskError):
            self.create("Second", id="stable-imported-id")
        self.assertEqual([task.id for task in self.store.list()], [first.id])


if __name__ == "__main__":
    unittest.main()
