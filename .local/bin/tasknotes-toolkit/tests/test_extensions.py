"""Optional coding-work metadata and cooperative ownership, exercised test-first."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

import test_store as storage
import test_cli as commands
from tasknotes_toolkit import Config, TaskError, TaskStore
from tasknotes_toolkit.model import validate_task


class OptionalMetadataTests(unittest.TestCase):
    setUp = storage.StoreTests.setUp
    tearDown = storage.StoreTests.tearDown
    create = storage.StoreTests.create

    def metadata(self):
        return dict(repository="https://github.com/example/portal", workingDirectory="services/auth",
                    workType="bug", sourceRefs=["https://github.com/example/portal/issues/42", "[[Login requirements]]"])

    def test_optional_metadata_is_typed_round_trips_and_keeps_the_description(self):
        task = self.create(**self.metadata())
        for name, value in self.metadata().items():
            self.assertEqual(task.fields.get(name), value)
            self.assertNotIn(name, task.custom_fields)
        updated = self.store.edit(task.id, {"workingDirectory": ".", "workType": "maintenance"})
        self.assertEqual(updated.fields["workingDirectory"], ".")
        self.assertEqual(updated.description, storage.DESCRIPTION)
        done = self.store.complete(task.id)
        self.assertEqual(done.fields["repository"], self.metadata()["repository"])

    def test_absent_extensions_are_never_added_to_ordinary_tasks(self):
        task = self.create()
        for name in (*self.metadata(), "claimedBy", "claimedAt"):
            self.assertNotIn(name, task.fields)
            self.assertNotIn(name + ":", (self.root / task.path).read_text())
        self.assertEqual(self.store.start(task.id).fields["status"], "in-progress")

    def test_invalid_optional_values_are_no_write_failures(self):
        task = self.create()
        path = self.root / task.path
        before = path.read_bytes()
        invalid = [dict(repository=123), dict(repository=" "), dict(workType="unknown-kind"),
                   dict(sourceRefs="https://example.com/issue"), dict(sourceRefs=[""]),
                   dict(claimedBy=42), dict(claimedBy=""), dict(claimedAt="2026-11-21T10:00:00"),
                   dict(claimedAt="2026-11-21T10:00:00Z")]
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(TaskError):
                self.store.edit(task.id, values)
            self.assertEqual(path.read_bytes(), before)

    def test_working_directory_is_portable_relative_and_cannot_escape(self):
        task = self.create()
        for value in ("../other", "services/../../other", "/tmp/other", "C:/other", "C:\\other", "\\\\host\\share", "~/other", "", "https://host/repo"):
            with self.subTest(value=value), self.assertRaises(TaskError):
                self.store.edit(task.id, {"workingDirectory": value})
        result = self.store.edit(task.id, {"workingDirectory": "./services/auth"})
        self.assertEqual(result.fields["workingDirectory"], "services/auth")

    def test_native_mapping_applies_to_extensions_and_claim_lifecycle(self):
        store = TaskStore(self.root, config={"fieldMapping": {"repository": "repo", "claimedBy": "owner", "claimedAt": "owned_since"}})
        task = store.create("Mapped task", storage.DESCRIPTION, repository="git@example.com:team/repo.git")
        claimed = store.start(task.id, claimed_by="run-a")
        self.assertEqual(claimed.fields["repository"], "git@example.com:team/repo.git")
        self.assertIn('owner: "run-a"', (self.root / task.path).read_text())
        result = store.complete(task.id, claimed_by="run-a")
        self.assertNotIn("claimedBy", result.fields)
        self.assertNotIn("owned_since:", (self.root / task.path).read_text())

    def test_validation_reports_bad_imported_metadata_and_claim_timestamps(self):
        task = self.create()
        values = dict(task.fields, workType="unknown", workingDirectory="../outside", sourceRefs=[False], claimedBy="run-a", claimedAt="not-a-timestamp")
        issues = validate_task(values, Config())
        self.assertTrue({"workType", "workingDirectory", "sourceRefs", "claimedAt"} <= {item["field"] for item in issues})

    def test_list_and_ready_filter_by_repository_work_type_and_owner(self):
        first = self.create("Bug", **self.metadata())
        self.create("Docs", repository=self.metadata()["repository"], workType="docs")
        other = self.create("Other", repository="git@example.com:other/repo.git", workType="bug")
        self.assertEqual([t.id for t in self.store.ready(repository=self.metadata()["repository"], work_type="bug", limit=3)], [first.id])
        self.store.start(first.id, claimed_by="run-a")
        self.assertEqual([t.id for t in self.store.list(claimed_by="run-a")], [first.id])
        self.assertEqual([t.id for t in self.store.ready(work_type="bug", limit=3)], [other.id])


class ClaimTests(unittest.TestCase):
    setUp = storage.StoreTests.setUp
    tearDown = storage.StoreTests.tearDown
    create = storage.StoreTests.create

    def test_start_records_owner_and_normalized_timestamp_and_is_idempotent(self):
        task = self.create()
        started = self.store.start(task.id, claimed_by="codex-session-123", expected_revision=task.revision)
        self.assertEqual(started.fields["claimedBy"], "codex-session-123")
        self.assertRegex(started.fields["claimedAt"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual(started.fields["status"], "in-progress")
        repeated = self.store.start(task.id, claimed_by="codex-session-123")
        self.assertEqual(started.revision, repeated.revision)
        self.assertEqual(repeated.fields["claimedAt"], started.fields["claimedAt"])

    def test_claim_blocks_other_owners_and_unidentified_mutators_without_writes(self):
        task = self.store.start(self.create().id, claimed_by="run-a")
        path = self.root / task.path
        before = path.read_bytes()
        operations = [lambda: self.store.start(task.id, claimed_by="run-b", expected_revision=task.revision),
                      lambda: self.store.complete(task.id, claimed_by="run-b"),
                      lambda: self.store.edit(task.id, {"priority": "high"}),
                      lambda: self.store.reopen(task.id, claimed_by="run-b"),
                      lambda: self.store.archive(task.id, claimed_by="run-b"),
                      lambda: self.store.add_note(task.id, "An unrelated agent's update.", claimed_by="run-b"),
                      lambda: self.store.delete(task.id, claimed_by="run-b")]
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaises(TaskError) as caught:
                operation()
            self.assertEqual(caught.exception.code, "claim_conflict")
            self.assertEqual(path.read_bytes(), before)

    def test_owner_can_record_results_and_completion_clears_only_active_claim(self):
        task = self.store.start(self.create(repository="https://github.com/example/portal").id, claimed_by="run-a")
        task = self.store.add_note(task.id, "The regression reproduces the reported failure.", claimed_by="run-a")
        completed = self.store.complete(task.id, note="All requested checks pass.", claimed_by="run-a", expected_revision=task.revision)
        self.assertEqual(completed.fields["status"], "done")
        self.assertNotIn("claimedBy", completed.fields)
        self.assertNotIn("claimedAt", completed.fields)
        self.assertEqual(completed.fields["repository"], "https://github.com/example/portal")
        self.assertIn("All requested checks pass.", completed.description)
        self.assertIn("regression reproduces", completed.description)

    def test_reopen_and_release_clear_claims_and_restore_backlog_readiness(self):
        task = self.store.start(self.create().id, claimed_by="run-a")
        opened = self.store.reopen(task.id, claimed_by="run-a")
        self.assertNotIn("claimedBy", opened.fields)
        task = self.store.start(task.id, claimed_by="run-a")
        released = self.store.release(task.id, claimed_by="run-a", expected_revision=task.revision)
        self.assertEqual(released.fields["status"], "open")
        self.assertNotIn("claimedAt", released.fields)
        self.assertEqual(self.store.ready()[0].id, released.id)
        self.assertEqual(self.store.release(task.id).revision, released.revision)

    def test_claims_have_no_automatic_expiry_even_when_backlog_status_is_open(self):
        task = self.create(claimedBy="old-session", claimedAt="2020-01-01T00:00:00Z")
        self.assertEqual(self.store.ready(limit=10), [])
        self.assertEqual(self.store.get(task.id).fields["claimedBy"], "old-session")

    def test_force_release_requires_an_exact_revision_and_still_rejects_stale_reads(self):
        task = self.store.start(self.create().id, claimed_by="lost-session")
        before = (self.root / task.path).read_bytes()
        for revision in (None, "stale-revision"):
            with self.subTest(revision=revision), self.assertRaises(TaskError):
                self.store.release(task.id, force=True, expected_revision=revision)
            self.assertEqual((self.root / task.path).read_bytes(), before)
        result = self.store.release(task.id, force=True, expected_revision=task.revision)
        self.assertNotIn("claimedBy", result.fields)
        self.assertEqual(result.fields["status"], "open")

    def test_claim_preview_does_not_modify_files(self):
        task = self.create()
        before = (self.root / task.path).read_bytes()
        preview = self.store.start(task.id, claimed_by="run-a", dry_run=True)
        self.assertEqual(preview.fields["claimedBy"], "run-a")
        self.assertEqual((self.root / task.path).read_bytes(), before)

    def test_releasing_an_unclaimed_completed_task_does_not_reopen_it(self):
        task = self.store.complete(self.create().id)
        result = self.store.release(task.id)
        self.assertEqual(result.fields["status"], "done")
        self.assertEqual(result.revision, task.revision)

    def test_generic_status_edits_clear_claims_and_force_delete_does_not_bypass_ownership(self):
        task = self.store.start(self.create().id, claimed_by="run-a")
        with self.assertRaises(TaskError) as caught:
            self.store.delete(task.id, force=True, claimed_by="run-b")
        self.assertEqual(caught.exception.code, "claim_conflict")
        result = self.store.edit(task.id, {"status": "done"}, claimed_by="run-a")
        self.assertNotIn("claimedBy", result.fields)
        self.assertNotIn("claimedAt", result.fields)
        self.assertIn("completedDate", result.fields)


class ExtensionCliTests(unittest.TestCase):
    setUp = commands.CliTests.setUp
    tearDown = commands.CliTests.tearDown
    run_cli = commands.CliTests.run_cli
    create = commands.CliTests.create

    def test_cli_metadata_flags_and_human_json_inspection(self):
        task = self.run_cli("create", "Fix login", "--description", "The retry must preserve the user's valid session.",
            "--repository", "https://github.com/example/portal", "--working-directory", "services/auth", "--work-type", "bug",
            "--source-ref", "https://github.com/example/portal/issues/42", "--source-ref", "[[Login requirements]]")["data"]
        self.assertEqual(task["fields"]["sourceRefs"], ["https://github.com/example/portal/issues/42", "[[Login requirements]]"])
        shown = self.run_cli("show", task["id"], human=True)
        self.assertIn("https://github.com/example/portal", shown)
        self.assertIn("services/auth", shown)
        updated = self.run_cli("edit", task["id"], "--work-type", "docs", "--working-directory", ".")["data"]
        self.assertEqual(updated["fields"]["workType"], "docs")
        self.assertEqual(len(self.run_cli("list", "--repository", "https://github.com/example/portal", "--work-type", "docs")["data"]), 1)

    def test_cli_claim_ownership_completion_and_owner_filter(self):
        task = self.create()
        claimed = self.run_cli("start", task["id"], "--claimed-by", "run-a", "--if-match", task["revision"])["data"]
        self.assertIn("claimedAt", claimed["fields"])
        self.assertEqual(len(self.run_cli("list", "--claimed-by", "run-a")["data"]), 1)
        denied = self.run_cli("complete", task["id"], "--claimed-by", "run-b", ok=False)
        self.assertEqual(denied["error"]["code"], "claim_conflict")
        completed = self.run_cli("complete", task["id"], "--claimed-by", "run-a", "--message", "The regression passes.")["data"]
        self.assertNotIn("claimedBy", completed["fields"])

    def test_cli_force_release_is_explicit_and_revision_protected(self):
        task = self.create()
        claimed = self.run_cli("start", task["id"], "--claimed-by", "lost-run")["data"]
        self.run_cli("release", task["id"], "--force", ok=False)
        result = self.run_cli("release", task["id"], "--force", "--if-match", claimed["revision"])["data"]
        self.assertEqual(result["fields"]["status"], "open")
        self.assertNotIn("claimedBy", result["fields"])

    def test_competing_processes_cannot_both_claim_one_task(self):
        task = self.create()
        processes = [subprocess.Popen([sys.executable, "-B", str(commands.SCRIPT), str(self.root), "--format", "json", "start",
                     task["id"], "--claimed-by", owner, "--if-match", task["revision"]], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for owner in ("run-a", "run-b")]
        results = [json.loads(process.communicate(timeout=10)[0]) for process in processes]
        self.assertEqual(sum(result["ok"] for result in results), 1)
        self.assertIn(self.run_cli("show", task["id"])["data"]["fields"]["claimedBy"], ("run-a", "run-b"))


if __name__ == "__main__":
    unittest.main()
