"""Fixes from two live runs (KUB-1333, KUB-1338) that finished with every task accepted but spent
time on gates that proved nothing:

- `{files}` is documented in the plan schema, but nothing substituted it: every gofmt and tracker
  check in one run (14 of them) ran against the literal `{files}`, passed, and checked nothing.
  Four reviewers noticed and re-ran the checks by hand.
- `make test` as a final check ran past the 540s limit in both runs (once in one, three times in
  the other). The limit exists for checks run inside a foreground `tp record`; the final checks
  run in the background, and the same suite finished in 11 and 17 minutes without it.
- `make -j4 test` → `make -j8 test` went to the human, though the timeout advice says the job
  count is the manager's to settle.
- A finding about a Go package doc (`doc.go`) opened a red-test round: no test can fail on a
  comment, so the gate failed and the manager had to override it.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from harness import Harness

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pipeline import run  # noqa: E402


class FilesPlaceholderTest(unittest.TestCase):
    """`{files}`: the task's own files; a Go tool gets only the Go ones."""

    def setUp(self) -> None:
        self.h = Harness()
        for rel, text in (("internal/hub/hub.go", "package hub\n"), ("deploy/crds/c.yaml", "kind: X\n")):
            (self.h.kb / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.h.kb / rel).write_text(text)
        self.task = {"id": "T01", "workspace": "kb",
                     "paths": ["internal/hub/hub.go", "deploy/crds/c.yaml", "wf:drafts/comment.md"]}

    def tearDown(self) -> None:
        self.h.close()

    def test_a_go_tool_gets_the_tasks_go_files(self) -> None:
        self.assertEqual(run._expand_cmd("gofmt -l {files}", self.task, self.h.scope()),
                         f"gofmt -l {self.h.kb / 'internal/hub/hub.go'}")

    def test_another_tool_gets_every_file_the_task_writes_in_the_workspace(self) -> None:
        # Not a workflow draft: a Jira comment draft names its ticket, which a tracker check forbids in the code.
        self.assertEqual(run._expand_cmd("! grep -n KUB- {files}", self.task, self.h.scope()),
                         f"! grep -n KUB- {self.h.kb / 'internal/hub/hub.go'} {self.h.kb / 'deploy/crds/c.yaml'}")

    def test_a_tracker_reference_in_the_tasks_file_fails_the_check(self) -> None:
        h = self.h
        h.approved(h.plan([h.task("T01", "architecture/overview.md", checks=["tracker"]),
                           h.task("T02", "build/guide.md"),
                           h.task("T03", "index.md", depends_on=["T01", "T02"], checks=[],
                                  brief="Write kb/index.md linking every article.",
                                  acceptance=["Every article is linked from index.md."])],
                          checks={"tracker": {"cmd": "! grep -nE 'KUB-[0-9]+' {files}"}}))
        h.tp("dispatch", "T01")
        h.good_article("architecture/overview.md")
        with (h.kb / "architecture/overview.md").open("a") as f:
            f.write("\nFixed for KUB-12.\n")
        h.result("T01", "author", changed=["architecture/overview.md"])
        out = h.tp("record", "T01", "--agent-id", "agent-T01").out
        self.assertIn("Check `tracker` failed", out)
        log = (h.run_dir("T01") / "check-tracker-author-0.log").read_text()
        self.assertNotIn("{files}", log)
        self.assertIn("KUB-12", log)

    def test_a_go_tool_with_no_go_file_to_check_is_skipped_not_run_on_stdin(self) -> None:
        h = self.h
        h.approved(h.plan([h.task("T01", "architecture/overview.md", checks=["gofmt"]),
                           h.task("T02", "build/guide.md"),
                           h.task("T03", "index.md", depends_on=["T01", "T02"], checks=[],
                                  brief="Write kb/index.md linking every article.",
                                  acceptance=["Every article is linked from index.md."])],
                          checks={"gofmt": {"cmd": "test -z \"$(gofmt -l {files})\""}}))
        out = h.author("T01", "architecture/overview.md").out
        self.assertNotIn("Check `gofmt` failed", out)
        self.assertIn("skipped", (h.run_dir("T01") / "check-gofmt-author-0.log").read_text())

    def test_a_final_check_cannot_name_a_tasks_files(self) -> None:
        h = self.h
        h.confirmed()
        h.write_json("plan.json", h.plan(checks={"fmt": {"cmd": "gofmt -l {files}"}}, final_checks=["fmt"]))
        out = h.tp("plan", "check", expect=2).text
        self.assertIn("fmt", out)
        self.assertIn("{files}", out)


class FinalCheckTimeoutTest(unittest.TestCase):
    """The final checks run in the background, so they get the time a whole suite needs."""

    def test_a_final_check_may_outlast_the_per_task_limit(self) -> None:
        self.assertGreaterEqual(run.FINAL_CHECK_TIMEOUT, 30 * 60)
        self.assertGreater(run.FINAL_CHECK_TIMEOUT, run.CHECK_TIMEOUT)

    def test_the_final_checks_run_under_the_final_limit(self) -> None:
        h = Harness()
        try:
            h.approved(h.plan(checks={"slow": {"cmd": "sleep 2"}}, final_checks=["slow"]))
            wf = run.Workflow(h.wf)
            state = wf.load()
            plan, scope, _ = run._loaded(wf, state)
            saved = run.CHECK_TIMEOUT, run.FINAL_CHECK_TIMEOUT
            run.CHECK_TIMEOUT, run.FINAL_CHECK_TIMEOUT = 1, 30
            try:
                failures, results = run._run_final_checks(wf, state, plan, scope)
            finally:
                run.CHECK_TIMEOUT, run.FINAL_CHECK_TIMEOUT = saved
            self.assertEqual(failures, [])
            self.assertIn("slow: ok", results)
        finally:
            h.close()

    def test_the_timeout_advice_names_the_final_limit_and_the_background(self) -> None:
        advice = run.final_failure_advice(["check:unit:timeout"], set())
        self.assertIn(f"{run.FINAL_CHECK_TIMEOUT // 60}-minute", advice)
        self.assertIn("background", advice)

    def test_tp_final_says_to_run_it_in_the_background(self) -> None:
        self.assertIn("background", run.GUIDE["final"])


class JobCountTest(unittest.TestCase):
    """A check already run in parallel may run with more jobs: the same targets."""

    def amend(self, old: str, new: str) -> str:
        h = Harness()
        try:
            h.approved(h.plan(checks={"unit": {"cmd": old}}, final_checks=["docs-all", "unit"]))
            h.tp("plan", "amend")
            draft = h.read_json("plan-amend.json")
            draft["checks"]["unit"]["cmd"] = new
            (h.wf / "plan-amend.json").write_text(json.dumps(draft))
            return h.tp("plan", "amend").out
        finally:
            h.close()

    def test_more_jobs_is_the_managers_to_settle(self) -> None:
        self.assertNotIn("Ask the human", self.amend("make -j4 test", "make -j8 test"))

    def test_other_targets_still_go_to_the_human(self) -> None:
        for new in ("make -j8 lint", "make -j8 test TESTS=x", "make -j999 test"):
            with self.subTest(new=new):
                self.assertIn("Ask the human", self.amend("make -j4 test", new))


class PackageDocRouteTest(unittest.TestCase):
    """A finding about a package doc is wording: the code author fixes it, with no red-test round."""

    TASK = {"workspace": "app", "serves": ["D1"], "tests_paths": ["internal/x/x_test.go"],
            "paths": ["internal/x/doc.go", "internal/x/x.go", "internal/x/x_test.go"]}
    SCOPE = {"deliverables": [{"id": "D1", "kind": "code"}],
             "workspaces": [{"name": "app", "path": "/x", "mode": "write"}]}

    def test_the_live_finding_goes_to_the_code_author(self) -> None:
        f = {"state": "wrong", "where": "internal/x/doc.go:22",
             "issue": "Wrong: the package doc tells a reader that the reconciler only finalizes successful joins."}
        self.assertEqual(run.fix_route(self.TASK, self.SCOPE, f), "impl")

    def test_a_package_doc_finding_cited_elsewhere_is_still_wording(self) -> None:
        f = {"state": "gap", "where": "internal/x/x.go:1", "issue": "The package doc omits restart recovery."}
        self.assertEqual(run.fix_route(self.TASK, self.SCOPE, f), "impl")

    def test_a_behaviour_bug_still_gets_its_failing_test(self) -> None:
        f = {"state": "wrong", "where": "internal/x/x.go:40", "issue": "Finish logs a retry that never comes."}
        self.assertEqual(run.fix_route(self.TASK, self.SCOPE, f), "tests-red")


if __name__ == "__main__":
    unittest.main()
