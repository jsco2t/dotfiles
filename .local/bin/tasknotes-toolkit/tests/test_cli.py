"""Execute the real CLI against temporary collections, including its JSON protocol."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "tntk"


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tasknotes-cli-")
        self.root = Path(self.temp.name) / "tasks"

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args, text=None, ok=True, human=False):
        cmd = [sys.executable, "-B", str(SCRIPT), str(self.root)]
        if not human:
            cmd += ["--format", "json"]
        run = subprocess.run(cmd + list(args), input=text, capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode == 0, ok, run.stdout + run.stderr)
        if human:
            return run.stdout + run.stderr
        result = json.loads(run.stdout)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["ok"], ok)
        return result

    def create(self, title="Fix retry", project="[[Alpha]]"):
        return self.run_cli("create", title, "--project", project, "--description-file", "-",
            text="Fix the retry so a user can finish signing in.\n\n## Acceptance\n\n- The regression test passes.\n")["data"]

    def test_json_human_help_and_full_descriptions(self):
        task = self.create()
        shown = self.run_cli("show", task["id"])["data"]
        self.assertIn("regression test passes", shown["description"])
        human = self.run_cli("show", task["id"], human=True)
        self.assertIn("Fix the retry so a user can finish signing in.", human)
        self.assertIn("Acceptance", human)
        self.assertIn("create", self.run_cli("--help", human=True))

    def test_multi_project_next_claim_complete_and_dry_run(self):
        first = self.create()
        self.create("Beta work", "[[Beta]]")
        ready = self.run_cli("next", "--project", "Alpha", "--limit", "1")["data"]
        self.assertEqual([task["id"] for task in ready], [first["id"]])
        self.run_cli("start", first["id"], "--if-match", first["revision"])
        self.assertEqual(self.run_cli("next", "--project", "Alpha")["data"], [])
        self.run_cli("--dry-run", "complete", first["id"])
        self.assertEqual(self.run_cli("show", first["id"])["data"]["fields"]["status"], "in-progress")
        self.run_cli("complete", first["id"], "--message", "The regression and full suite pass.")
        self.assertEqual(self.run_cli("show", first["id"])["data"]["fields"]["status"], "done")

    def test_structured_errors_and_explicit_delete(self):
        task = self.create()
        bad = self.run_cli("edit", task["id"], "--set", 'due="2026-02-30"', ok=False)
        self.assertIn("code", bad["error"])
        self.run_cli("delete", task["id"], ok=False)
        self.assertEqual(self.run_cli("show", task["id"])["data"]["id"], task["id"])
        self.run_cli("delete", task["id"], "--yes")
        self.run_cli("show", task["id"], ok=False)

    def test_create_requires_a_real_description_without_an_arbitrary_length_gate(self):
        self.run_cli("create", "Task without a description", ok=False)
        task = self.run_cli("create", "Repair link", "--description", "Repair the broken documentation link.")["data"]
        self.assertEqual(task["description"], "Repair the broken documentation link.")

    def test_edit_reads_a_stdin_description_exactly_once(self):
        task = self.create()
        body = "Preserve the user's session during retry.\n\nVerify both retry and expiry behavior.\n"
        updated = self.run_cli("edit", task["id"], "--description-file", "-", text=body)["data"]
        self.assertEqual(updated["description"], body)

    def test_reserved_create_fields_produce_structured_errors_without_tracebacks(self):
        for field in ("title=Other", "description=Other", "dry_run=true"):
            with self.subTest(field=field):
                response = self.run_cli("create", "Original", "--description", "Keep the original task clear.", "--set", field, ok=False)
                self.assertEqual(response["error"]["code"], "usage")


if __name__ == "__main__":
    unittest.main()
