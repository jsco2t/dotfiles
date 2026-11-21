"""Field/date rules taken from the canonical TaskNotes contract, using stdlib only."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tasknotes_toolkit.model import Config, TaskError, canonical_datetime, normalize_fields, read_fields, task_detected, validate_task


class ModelTests(unittest.TestCase):
    def valid(self, **changes):
        values = dict(title="Fix login", status="open", priority="normal", tags=["task"],
                      dateCreated="2026-11-20T10:00:00Z", dateModified="2026-11-21T10:00:00Z")
        values.update(changes)
        return values

    def test_native_plugin_mapping_statuses_and_task_identification(self):
        config = Config.from_dict(dict(fieldMapping={"title": "Task title", "status": "state", "completedDate": "finished"},
            customStatuses=[dict(value="todo", isCompleted=False), dict(value="doing", isCompleted=False), dict(value="shipped", isCompleted=True)],
            defaultTaskStatus="todo", taskIdentificationMethod="property", taskPropertyName="type", taskPropertyValue="task"))
        self.assertEqual(config.mapping["completedDate"], "finished")
        self.assertEqual(config.completed_statuses, ("shipped",))
        self.assertTrue(task_detected({"type": "task"}, config))
        self.assertFalse(task_detected({"tags": ["task"]}, config))
        self.assertEqual(read_fields({"Task title": "The title", "state": "todo"}, config, "legacy.md")["title"], "The title")

    def test_detection_does_not_treat_every_markdown_note_as_a_task(self):
        config = Config()
        self.assertTrue(task_detected({"tags": ["task/bug", "work"]}, config))
        self.assertFalse(task_detected({"title": "Project overview", "tags": ["taskforce"]}, config))
        self.assertEqual(read_fields({"tags": ["task"]}, config, "A readable filename.md")["title"], "A readable filename")

    def test_canonical_date_times_preserve_instants_and_truncate_fractional_seconds(self):
        self.assertEqual(canonical_datetime("2026-11-21T09:30:00.999+02:00"), "2026-11-21T07:30:00Z")
        fields = normalize_fields({"due": "2026-11-21", "scheduled": "2026-11-21T09:30:00-05:00"}, Config())
        self.assertEqual(fields["due"], "2026-11-21")
        self.assertEqual(fields["scheduled"], "2026-11-21T14:30:00Z")
        for value in ("2026-02-30", "20261121", "2026-11-21T09:30:00", "2026-11-21 09:30:00"):
            with self.subTest(value=value), self.assertRaises(TaskError):
                normalize_fields({"due": value}, Config())

    def test_validation_explains_required_types_dates_and_completion_invariants(self):
        self.assertEqual(validate_task(self.valid(), Config()), [])
        missing = validate_task({"title": "Task", "status": "done"}, Config())
        self.assertTrue({"dateCreated", "dateModified", "completedDate"} <= {issue["field"] for issue in missing})
        invalid = validate_task(self.valid(timeEstimate=-1, projects="Alpha", due="2026-02-30"), Config())
        self.assertTrue({"timeEstimate", "projects", "due"} <= {issue["field"] for issue in invalid})
        self.assertTrue(all({"code", "severity", "message", "field"} <= issue.keys() for issue in invalid))
        self.assertTrue(validate_task(self.valid(dateModified="2026-11-19T00:00:00Z"), Config()))

    def test_mapping_collisions_and_invalid_default_status_are_configuration_errors(self):
        for settings in (dict(fieldMapping={"title": "same", "status": "same"}),
                         dict(customStatuses=[dict(value="done", isCompleted=True)], defaultTaskStatus="missing")):
            with self.subTest(settings=settings), self.assertRaises(TaskError):
                Config.from_dict(settings)

    def test_canonical_mapping_wins_over_legacy_alias_without_losing_unknowns(self):
        values = read_fields({"dateCreated": "2026-11-21T10:00:00Z", "date_created": "2020-01-01T00:00:00Z",
                              "title": "Keep canonical", "custom": {"owner": "Human"}}, Config(), "task.md")
        self.assertEqual(values["dateCreated"], "2026-11-21T10:00:00Z")


if __name__ == "__main__":
    unittest.main()
