"""Fixes from a live run (KUB-1332) that finished with every task accepted but still cost time:

- The Jira post's dry run came before the closeout and the final checks. The run then sat nine
  hours on the human's answer with that work undone, the manager ran every repo gate by hand so
  the question could say they passed, a comment-only fix task after the post had to keep the
  posted comment's line citations valid, and drafts got fix rounds after their text was posted.
  The post now waits for the closeout and the final checks, and `tp final` after the post
  reuses those check results when nothing changed.
- `go vet {dirs}` was handed directories with no Go files (`tools/` with shell scripts, a
  JavaScript mock folder): two fix rounds and two gates accepted over their findings.
- `final_failure_advice` offered `make -j4` for a slow check as the manager's call, but the
  amendment classifier sent it to the human.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from harness import Harness
from scenarios import FakeCli, Mixed

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pipeline import run, survey  # noqa: E402

DRAFT = "wf:drafts/kub-1-comment.md"


class GoDirsTest(unittest.TestCase):
    """`{dirs}` in a Go command names only directories that hold Go files."""

    def setUp(self) -> None:
        self.h = Harness()
        for rel, text in (("internal/hub/hub.go", "package hub\n"), ("tools/gen-deps.sh", "#!/bin/sh\n"),
                          ("tools/daemon-deps.txt", "x\n"), ("dash/mock/fleet-mock.mjs", "export {}\n")):
            (self.h.kb / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.h.kb / rel).write_text(text)
        self.task = {"id": "T01", "workspace": "kb",
                     "paths": ["internal/hub/hub.go", "tools/daemon-deps.txt", "dash/mock/fleet-mock.mjs"]}

    def tearDown(self) -> None:
        self.h.close()

    def test_go_vet_skips_directories_without_go_files(self) -> None:
        self.assertEqual(run._expand_cmd("go vet {dirs}", self.task, self.h.scope()), "go vet ./internal/hub")

    def test_a_wrapped_go_command_is_still_go(self) -> None:
        self.assertEqual(run._expand_cmd("tools/with-toolchain go vet {dirs}", self.task, self.h.scope()),
                         "tools/with-toolchain go vet ./internal/hub")

    def test_another_tool_keeps_every_code_directory(self) -> None:
        self.assertEqual(run._expand_cmd("lint {dirs}", self.task, self.h.scope()),
                         "lint ./dash/mock ./internal/hub ./tools")

    def test_a_check_with_no_directory_to_check_is_skipped_not_run_bare(self) -> None:
        h = Harness()
        try:
            tasks = [h.task("T01", "architecture/overview.md", checks=["pkg"]), h.task("T02", "build/guide.md"),
                     h.task("T03", "index.md", depends_on=["T01", "T02"], checks=[],
                            brief="Write kb/index.md linking every article.",
                            acceptance=["Every article is linked from index.md."])]
            h.approved(h.plan(tasks, checks={"pkg": {"cmd": "false {dirs}"}}))
            out = h.author("T01", "architecture/overview.md").out
            self.assertNotIn("Check `pkg` failed", out)
            self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_check")
            self.assertIn("skipped", (h.run_dir("T01") / "check-pkg-author-0.log").read_text())
        finally:
            h.close()


class ParallelMakeAmendTest(unittest.TestCase):
    """`make -jN <targets>` runs the same targets as `make <targets>`: the manager settles it."""

    def amend(self, old: str, new: str, go_version: str = "") -> str:
        h = Harness()
        try:
            if go_version:
                (h.src / ".go-version").write_text(go_version + "\n")
            h.approved(h.plan(checks={"unit": {"cmd": old}}, final_checks=["docs-all", "unit"]))
            h.tp("plan", "amend")
            draft = h.read_json("plan-amend.json")
            draft["checks"]["unit"]["cmd"] = new
            (h.wf / "plan-amend.json").write_text(json.dumps(draft))
            out = h.tp("plan", "amend").out
            if "Ask the human" not in out:
                h.tp("plan", "amend", "--delegated", "--note", "make test runs past the limit; run it in parallel.")
                self.assertEqual(h.read_json("plan.json")["checks"]["unit"]["cmd"], new)
            return out
        finally:
            h.close()

    def test_parallel_make_is_the_managers_to_settle(self) -> None:
        self.assertNotIn("Ask the human", self.amend("make test", "make -j4 test"))

    def test_parallel_make_under_the_repo_pin_is_the_managers_to_settle(self) -> None:
        self.assertNotIn("Ask the human", self.amend("make test", survey.pin_prefix("1.26.2") + "make -j4 test",
                                                     go_version="1.26.2"))

    def test_anything_more_than_the_job_count_goes_to_the_human(self) -> None:
        for new in ("make -j4 lint", "make -j4 -k test", "make -j test", "make -j999 test", "make -j4 test TESTS=x",
                    "make -j4 test; true", "go test ./..."):
            with self.subTest(new=new):
                self.assertIn("Ask the human", self.amend("make test", new))

    def test_the_timeout_advice_names_the_delegated_route(self) -> None:
        advice = run.final_failure_advice(["check:unit:timeout"], set())
        self.assertIn("make -j", advice)
        self.assertIn("--delegated", advice)


class PostLastTest(unittest.TestCase):
    """The post is the last write: after the closeout and the final checks, so the human's answer
    ends the run and nothing changes what the post cites."""

    def setUp(self) -> None:
        self.m = m = Mixed()
        self.jira = FakeCli(m.h.root)
        self.runs = m.h.root / "final-runs"
        scope = m.scope(["code", "docs", "integration"], ["tests", "code", "docs", "correctness", "doc-review"])
        tasks = [m.code_task("T01"),
                 m.doc_task("T02", path=DRAFT, depends_on=["T01"],
                            brief="Write the KUB-1 comment text about mul, citing calc.py."),
                 {"id": "T03", "title": "Post the KUB-1 comment", "serves": ["D3"], "workspace": "app",
                  "publish": {"to": "jira-comment", "target": "KUB-1", "body": DRAFT},
                  "acceptance": ["The comment is posted once and reads back as sent."],
                  "estimate_min": 5, "depends_on": ["T02"]}]
        # Like a real build, the check writes into the workspace (a coverage file that differs per run).
        m.h.approved(plan=m.h.plan(tasks, checks={"unit": {"cmd": f"echo run >> {self.runs} && "
                                                          f"date +%s%N > {m.app}/coverage.out"}},
                                   final_checks=["unit"]), **scope)
        m.code_done("T01")
        m.h.tp("dispatch", "T02")
        draft = m.h.wf / "drafts" / "kub-1-comment.md"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text("## Fixed\n\n- `mul` multiplies (`calc.py:5-6`).\n")
        m.h.result("T02", "author", changed=[str(draft)], noticed=["calc.py has no docstring for add."])
        m.h.tp("record", "T02", "--agent-id", "da-1")
        m.h.tp("accept", "T02", "--note", "citation holds")
        for _ in range(6):
            ready = [a["id"] for a in m.actions() if a["action"] == "review"]
            if not ready:
                break
            for sid in ready:
                m.h.tp("dispatch", sid)
                m.review_file(sid, 1, "pass")
                m.h.tp("record", sid)

    def tearDown(self) -> None:
        self.jira.restore()
        self.m.close()

    def kinds(self):
        return [a["action"] for a in self.m.actions()]

    def check_runs(self) -> int:
        return len(self.runs.read_text().splitlines()) if self.runs.exists() else 0

    def classify(self) -> None:
        self.m.h.tp("closeout", "--items", "1", "--class", "observation", "--note", "add lacks a docstring; harmless")
        self.m.h.whole_pass()  # /reviewomatic over the whole change, after the closeout

    def test_the_closeout_comes_before_the_post(self) -> None:
        self.assertIn("closeout", self.kinds())
        self.assertNotIn("publish", self.kinds())
        self.assertIn("closeout is open", self.m.h.tp("publish", "T03", expect=2).text)
        self.assertEqual(self.check_runs(), 0)

    def test_the_final_checks_run_before_the_post_and_are_reused_after_it(self) -> None:
        h = self.m.h
        self.classify()
        self.assertEqual(self.kinds(), ["publish"])
        self.assertEqual(self.check_runs(), 0)
        h.tp("publish", "T03")  # the dry run runs the final checks first
        self.assertEqual(h.state()["phase"], "EXECUTING")
        self.assertEqual(self.check_runs(), 1)
        h.tp("publish", "T03", "--answer", "Post it")
        self.assertEqual(len(self.jira.writes()), 1)
        self.assertIn("DONE", h.tp("final").out)
        self.assertEqual(self.check_runs(), 1)
        self.assertIn("unit: ok", (h.wf / "report.md").read_text())

    def test_a_change_after_the_checks_runs_them_again(self) -> None:
        h = self.m.h
        self.classify()
        h.tp("publish", "T03")
        (self.m.app / "calc.py").write_text((self.m.app / "calc.py").read_text() + "\n# touched\n")
        h.tp("publish", "T03", "--answer", "Post it")
        h.tp("final")
        self.assertEqual(self.check_runs(), 2)

    def test_a_failing_final_check_holds_the_post(self) -> None:
        h = self.m.h
        self.classify()
        plan = h.read_json("plan.json")
        self.runs.mkdir()  # `echo >> dir` fails: the check fails
        self.assertIn("final check unit failed", h.tp("publish", "T03", expect=2).text)
        self.assertEqual(self.jira.writes(), [])
        self.assertNotIn("publish", h.state()["tasks"]["T03"])
        self.assertEqual(plan["final_checks"], ["unit"])

    def test_a_dry_run_shown_before_this_rule_still_posts(self) -> None:
        # A workflow upgraded mid-question: the human already has the dry run in front of them.
        h = self.m.h
        state = h.state()
        del state["reviews"]["W/code-reviewer"]  # a run approved before the whole-change review
        state["tasks"]["T03"]["publish"] = {"sha": "x", "head": None, "seen": None, "ts": state["approved"],
                                            "warnings": []}
        (h.wf / ".tp" / "state.json").write_text(json.dumps(state))
        self.assertIn("publish", self.kinds())


class CompactReportTest(unittest.TestCase):
    """A real report ran to 85KB, 39KB of it observations nobody acts on; one note was printed
    once per task it covered, and one amendment's reason once per task it added."""

    def test_observations_go_to_their_own_file_and_notes_print_once(self) -> None:
        from harness import Harness as H
        h = H()
        try:
            h.approved()
            h.author("T01", "architecture/overview.md")
            h.author("T02", "build/guide.md")
            h.tp("accept", "T01", "T02", "--note", "Read both articles; every citation holds.")
            h.tp("dispatch", "T03")
            (h.kb / "index.md").write_text("# KB\n\n- [O](architecture/overview.md)\n- [B](build/guide.md)\n")
            h.result("T03", "author", changed=["index.md"],
                     noticed=[f"Observation {i}: calc/calc.go:{i} has a long line." for i in range(1, 6)])
            h.tp("record", "T03", "--agent-id", "a-3")
            h.tp("accept", "T03", "--note", "ok")
            h.tp("closeout", "--items", "1-5", "--class", "observation", "--note", "style only")
            h.tp("final")
            report = (h.wf / "report.md").read_text()
            self.assertIn("5 observations", report)
            self.assertNotIn("Observation 3", report)
            self.assertIn("Observation 3", (h.wf / "observations.md").read_text())
            self.assertEqual(report.count("every citation holds"), 1)
            self.assertIn("T01, T02: Read both articles", report)
        finally:
            h.close()


if __name__ == "__main__":
    unittest.main()
