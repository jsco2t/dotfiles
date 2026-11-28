"""Validation runs once, and only what can change a verdict runs again.

A real run (KUB-1339) spent much of its time re-running suites that told it nothing new:
- one task's acceptance said "make test passes", so its agent ran the whole repository's suite;
- every task's test_cmd turned Go's test cache off (`-count=1`), so each record ran cold;
- a package suite that ran past the 540s foreground limit was filed as a failure three times, each
  opening a fix round the manager then overrode after timing the suite by hand;
- the final `make test` failed only because the sandbox refuses unix sockets, and nothing could
  say the failure pre-dated the run: it ran four times in 31 minutes on an unchanged tree;
- the manager re-read the diff of every code task before accepting it, though a review read it next.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import unittest

from harness import git
from scenarios import CALC_MUL_PY, TEST_PY, Mixed

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pipeline import run  # noqa: E402


def finish_reviews(h) -> None:
    """Every review session done: what the final step finds once the reviews have run."""
    state = h.state()
    for s in state.get("reviews", {}).values():
        s["status"] = "done"
    (h.wf / ".tp" / "state.json").write_text(json.dumps(state))


class EnvVar:
    def __init__(self, **values: str) -> None:
        self.values, self.saved = values, {}

    def __enter__(self) -> "EnvVar":
        for k, v in self.values.items():
            self.saved[k] = os.environ.get(k)
            os.environ[k] = v
        return self

    def __exit__(self, *exc: object) -> None:
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# --- the plan check ------------------------------------------------------------------------------

class WholeChangeGatesStayFinalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.m = Mixed()
        self.h = self.m.h
        self.h.confirmed(**self.m.scope(["code"], ["code", "correctness"]))

    def tearDown(self) -> None:
        self.m.close()

    def check(self, **over) -> str:
        plan = self.h.plan([self.m.code_task(**over)], checks={"make-test": {"cmd": "make -j4 test", "cwd": "app"},
                                                               "make-lint": {"cmd": "make lint", "cwd": "app"}},
                           final_checks=["make-test", "make-lint"])
        self.h.write_json("plan.json", plan)
        return self.h.tp("plan", "check", expect=None).text

    def test_a_criterion_that_runs_a_final_check_is_refused(self) -> None:
        out = self.check(acceptance=["mul(2, 3) == 6", "make test passes"])
        self.assertIn("acceptance criterion 2", out)
        self.assertIn("make-test", out)

    def test_prose_that_merely_says_make_is_not_a_final_check(self) -> None:
        out = self.check(acceptance=["make sure mul(2, 3) == 6 and lint findings stay at zero"])
        self.assertNotIn("final check", out)

    def test_a_test_cmd_that_turns_the_go_test_cache_off_is_refused(self) -> None:
        out = self.check(test_cmd="tools/with-toolchain go test -race -count=1 ./internal/store/...")
        self.assertIn("-count=1", out)
        self.assertIn("test cache", out)

    def test_a_cached_go_test_cmd_passes(self) -> None:
        out = self.check(test_cmd="go test -race ./internal/store/... -run Token")
        self.assertNotIn("test cache", out)


# --- a timed-out run is never a finding ----------------------------------------------------------

# The marker that makes the suite slow lives outside the workspace, so the write fence never sees it.
SLOW_TEST = ("import os, time\nif os.path.exists({mark!r}):\n    time.sleep(4)\n"
             "import unittest\nunittest.main(module='test_calc', argv=['x', '-q'])\n")


class TimeoutIsNotAFailureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = EnvVar(TP_CHECK_TIMEOUT="2", TP_FINAL_CHECK_TIMEOUT="60").__enter__()
        self.m = m = Mixed()
        self.h = m.h
        self.mark = m.h.root / "slow"
        (m.app / "slow_test.py").write_text(SLOW_TEST.format(mark=str(self.mark)))
        git(m.app, "add", "-A")
        git(m.app, "commit", "-q", "-m", "slow runner")
        scope = m.scope(["code"], ["code", "correctness"])
        scope["split_tests"] = False
        m.approve([m.code_task(test_cmd="python3 slow_test.py", checks=[])], scope)

    def tearDown(self) -> None:
        self.m.close()
        self.env.__exit__()

    def build(self, slow: bool = True, **result) -> None:
        m, h = self.m, self.h
        h.tp("dispatch", "T01")
        (m.app / "test_calc.py").write_text(TEST_PY)
        h.tp("red", "T01")
        (m.app / "calc.py").write_text(CALC_MUL_PY)
        if slow:
            self.mark.write_text("")
        h.result("T01", "build", changed=["calc.py", "test_calc.py"], **result)

    def test_a_suite_past_the_foreground_limit_opens_no_fix_round(self) -> None:
        self.build(noticed=["calc.py has no module docstring"])
        out = self.h.tp("record", "T01", "--agent-id", "ca-1").out
        self.assertIn("NOT recorded", out)
        self.assertIn("--long", out)
        ts = self.h.state()["tasks"]["T01"]
        self.assertEqual(ts["round"], 0)
        self.assertIn("T01", self.h.state()["in_flight"])
        self.assertFalse((self.h.run_dir("T01") / "findings-1.json").exists())

    def test_the_long_record_finishes_it_and_notices_once(self) -> None:
        self.build(noticed=["calc.py has no module docstring"])
        self.h.tp("record", "T01", "--agent-id", "ca-1")
        out = self.h.tp("record", "T01", "--agent-id", "ca-1", "--long").out
        self.assertIn("passed its checks", out)
        self.assertNotIn("T01", self.h.state()["in_flight"])
        self.assertEqual((self.h.wf / "noticed.md").read_text().count("no module docstring"), 1)

    def test_the_long_record_runs_its_suite_outside_the_workflow_lock(self) -> None:
        # Every tp command takes the lock: a 45-minute suite held under it stalls every other hand-back.
        self.build()
        self.h.tp("record", "T01", "--agent-id", "ca-1")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TP_GUARD_DIR=str(self.h.root / "guard"),
                   TP_FOLLOW_ON="0", TP_AUTO_ACCEPT="0")
        from harness import PY, TP
        bg = subprocess.Popen([PY, str(TP), "-w", str(self.h.wf), "record", "T01", "--agent-id", "ca-1", "--long"],
                              env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            time.sleep(1.5)  # the 4-second suite is running now
            t0 = time.monotonic()
            self.h.tp("next")
            self.assertLess(time.monotonic() - t0, 2.0)
        finally:
            out = bg.communicate(timeout=60)[0]
        self.assertIn("passed its checks", out)

    def test_a_real_finding_beside_a_timeout_still_gets_its_fix_round(self) -> None:
        self.build()
        (self.m.app / "stray.py").write_text("x = 1\n")
        out = self.h.tp("record", "T01", "--agent-id", "ca-1").out
        self.assertIn("outside this task's paths: stray.py", out)
        findings = self.h.state()["tasks"]["T01"]["findings"]
        self.assertFalse(any("timed out" in f for f in findings), findings)

    def test_a_red_run_that_times_out_records_nothing(self) -> None:
        m, h = self.m, self.h
        h.tp("dispatch", "T01")
        (m.app / "test_calc.py").write_text(TEST_PY)
        self.mark.write_text("")
        err = h.tp("red", "T01", expect=2).text
        self.assertIn("neither red nor green", err)
        self.assertNotIn("red", h.state()["tasks"]["T01"])


class SlowCheckTest(unittest.TestCase):
    def test_a_per_task_check_that_times_out_is_not_a_finding(self) -> None:
        with EnvVar(TP_CHECK_TIMEOUT="1"):
            m = Mixed()
            try:
                scope = m.scope(["code"], ["code", "correctness"])
                scope["split_tests"] = False
                m.approve([m.code_task(checks=["slowlint"])], scope, checks={"slowlint": {"cmd": "sleep 3"}})
                m.h.tp("dispatch", "T01")
                (m.app / "test_calc.py").write_text(TEST_PY)
                m.h.tp("red", "T01")
                (m.app / "calc.py").write_text(CALC_MUL_PY)
                m.h.result("T01", "build", changed=["calc.py", "test_calc.py"])
                out = m.h.tp("record", "T01", "--agent-id", "ca-1").out
                self.assertIn("NOT recorded", out)
                self.assertIn("slowlint", out)
                self.assertEqual(m.h.state()["tasks"]["T01"]["round"], 0)
            finally:
                m.close()


# --- a final-check failure the approval commit already had ----------------------------------------

SUITE_PY = ("import os, random, sys\n"
            "print('ok  \\texample.com/fine\\t(cached)')\n"
            "print(f'--- FAIL: TestListensOnASocket ({random.random():.2f}s)')\n"
            "print(f'FAIL\\texample.com/sock\\t{random.random():.3f}s')\n"
            "if os.path.exists('new_break'):\n"
            "    print('--- FAIL: TestTheRunBrokeThis (0.00s)')\n"
            "sys.exit(1)\n")


class PreexistingFinalFailureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.m = m = Mixed()
        self.h = m.h
        (m.app / "suite.py").write_text(SUITE_PY)
        git(m.app, "add", "-A")
        git(m.app, "commit", "-q", "-m", "suite")
        self.workspace()
        scope = m.scope(["code"], ["code", "correctness"])
        scope["split_tests"] = False
        self.h.approved(self.h.plan([m.code_task()], checks={"suite": {"cmd": "python3 suite.py", "cwd": "app"}},
                                    final_checks=["suite"]), **scope)
        h = self.h
        h.tp("dispatch", "T01")
        (m.app / "test_calc.py").write_text(TEST_PY)
        h.tp("red", "T01")
        (m.app / "calc.py").write_text(CALC_MUL_PY)
        h.result("T01", "build", changed=["calc.py", "test_calc.py"])
        h.tp("record", "T01", "--agent-id", "ca-1")
        if h.state()["tasks"]["T01"]["status"] == "needs_check":
            h.tp("accept", "T01", "--note", "red then green; read the diff")
        finish_reviews(h)

    def workspace(self) -> None:
        """The write workspace: the repository itself here; a linked worktree in the subclass."""

    def tearDown(self) -> None:
        self.m.close()

    def probes(self) -> int:
        return sum(1 for e in run.Workflow(self.h.wf).events() if e.get("kind") == "base_probe")

    def test_a_failure_the_approval_commit_has_too_lets_the_run_finish(self) -> None:
        out = self.h.tp("final").out
        self.assertIn("DONE", out)
        report = (self.h.wf / "report.md").read_text()
        self.assertIn("Left as pre-existing", report)
        self.assertIn("clean copy of the approval commit", report)
        self.assertEqual(self.probes(), 1)
        # The probe leaves no copy behind and never touched the workspace's repository.
        self.assertFalse((self.h.wf / ".tp" / "base-copy").exists())
        wt = subprocess.run(["git", "-C", str(self.m.app), "worktree", "list"], capture_output=True, text=True)
        self.assertEqual(len(wt.stdout.strip().splitlines()), 1)

    def test_a_failure_only_this_run_has_still_stops_it_and_says_which(self) -> None:
        (self.m.app / "new_break").write_text("")
        err = self.h.tp("final", expect=2).text
        self.assertIn("final check suite failed", err)
        self.assertIn("TestTheRunBrokeThis", err)
        self.assertNotEqual(self.h.state()["phase"], "DONE")

    def test_the_approval_commit_is_checked_once(self) -> None:
        (self.m.app / "new_break").write_text("")
        self.h.tp("final", expect=2)
        self.h.tp("final", expect=2)
        self.assertEqual(self.probes(), 1)
        (self.m.app / "new_break").unlink()
        self.assertIn("DONE", self.h.tp("final").out)
        self.assertEqual(self.probes(), 1)


class PreexistingFinalFailureInALinkedWorktreeTest(PreexistingFinalFailureTest):
    """KUB-1339's workspace was a linked worktree (its `.git` is a file): the probe must check the
    approval commit out without writing to the main repository's `.git/worktrees`."""

    def workspace(self) -> None:
        wt = self.m.h.root / "app-wt"
        git(self.m.app, "worktree", "add", "-q", "-b", "wt", str(wt))
        self.main = self.m.app
        self.m.app = wt

    def test_a_failure_the_approval_commit_has_too_lets_the_run_finish(self) -> None:
        self.assertIn("DONE", self.h.tp("final").out)
        wt = subprocess.run(["git", "-C", str(self.main), "worktree", "list"], capture_output=True, text=True)
        self.assertEqual(len(wt.stdout.strip().splitlines()), 2)  # the repository and its one worktree


class HumanWaiverTest(unittest.TestCase):
    """A failure the probe cannot settle (here: a log that names no failure tp can read) goes to the
    human once; their OK must let `tp final` finish, without running that check again — in KUB-1339
    the human accepted an outside-sandbox run and `tp final` re-ran `make test` and failed, twice."""

    def setUp(self) -> None:
        self.m = m = Mixed()
        self.h = h = m.h
        self.flag, self.flag2, self.runs = h.root / "sandboxed", h.root / "broken2", h.root / "runs"
        scope = m.scope(["code"], ["code", "correctness"])
        scope["split_tests"] = False
        h.approved(h.plan([m.code_task()], checks={
            "suite": {"cmd": f"echo x >> {self.runs}; test ! -e {self.flag}", "cwd": "app"},
            "lint": {"cmd": f"test ! -e {self.flag2}", "cwd": "app"}}, final_checks=["suite", "lint"]), **scope)
        h.tp("dispatch", "T01")
        (m.app / "test_calc.py").write_text(TEST_PY)
        h.tp("red", "T01")
        (m.app / "calc.py").write_text(CALC_MUL_PY)
        h.result("T01", "build", changed=["calc.py", "test_calc.py"])
        h.tp("record", "T01", "--agent-id", "ca-1")
        if h.state()["tasks"]["T01"]["status"] == "needs_check":
            h.tp("accept", "T01", "--note", "red then green; read the diff")
        finish_reviews(h)
        self.flag.write_text("")

    def tearDown(self) -> None:
        self.m.close()

    def runs_of_suite(self) -> int:
        return len(self.runs.read_text().splitlines()) if self.runs.exists() else 0

    def test_the_humans_ok_lets_final_finish_without_running_the_check_again(self) -> None:
        err = self.h.tp("final", expect=2).text
        self.assertIn("final check suite failed", err)
        self.assertIn("--waive", err)
        self.assertEqual(self.runs_of_suite(), 1)
        self.h.tp("final", "--waive", "--answer", "Accept the outside-sandbox run")
        self.assertIn("DONE", self.h.tp("final").out)
        self.assertEqual(self.runs_of_suite(), 1)
        report = (self.h.wf / "report.md").read_text()
        self.assertIn("Accept the outside-sandbox run", report)
        self.assertIn("waived", report)
        self.assertIn("Accept the outside-sandbox run", (self.h.wf / "decisions.md").read_text())

    def test_the_waiver_lapses_once_the_workspace_changes(self) -> None:
        self.h.tp("final", expect=2)
        self.h.tp("final", "--waive", "--answer", "Accept the outside-sandbox run")
        (self.m.app / "calc.py").write_text(CALC_MUL_PY + "\n# touched after the waiver\n")
        err = self.h.tp("final", expect=2).text
        self.assertIn("final check suite failed", err)
        self.assertIn("lapsed", err)
        self.assertEqual(self.runs_of_suite(), 2)

    def test_a_new_failure_after_the_waiver_still_stops_the_run(self) -> None:
        self.h.tp("final", expect=2)
        self.h.tp("final", "--waive", "--answer", "Accept the outside-sandbox run")
        self.flag2.write_text("")
        err = self.h.tp("final", expect=2).text
        self.assertIn("final check lint failed", err)
        self.assertNotIn("final check suite failed", err)
        self.assertEqual(self.runs_of_suite(), 1)

    def test_there_is_nothing_to_waive_before_a_failure(self) -> None:
        self.assertIn("no final-check failure to waive",
                      self.h.tp("final", "--waive", "--answer", "Accept it", expect=2).text)


class FailureSignatureTest(unittest.TestCase):
    def test_makes_timing_dependent_lines_do_not_count(self) -> None:
        mine = run.failure_signature("FAIL\tp\t1s\nmake: *** Waiting for unfinished jobs....\n"
                                     "make[2]: *** [Makefile:9: test] Error 1\n", [])
        base = run.failure_signature("FAIL\tp\t1s\nmake: *** [Makefile:9: test] Error 1\n", [])
        self.assertEqual(mine, base)

    def test_durations_and_directories_do_not_make_two_runs_differ(self) -> None:
        a = run.failure_signature("--- FAIL: TestX (0.01s)\nFAIL\texample.com/p\t1.234s\n"
                                  "make: *** [Makefile:9: test] Error 1\nnot ok 3 - parses /w/a/x\n", ["/w/a"])
        b = run.failure_signature("--- FAIL: TestX (2.50s)\nFAIL\texample.com/p\t9.9s\n"
                                  "make: *** [Makefile:9: test] Error 1\nnot ok 7 - parses /tmp/c/x\n", ["/tmp/c"])
        self.assertEqual(a, b)
        self.assertIn("--- FAIL: TestX", a)

    def test_a_new_failing_test_in_an_already_failing_package_differs(self) -> None:
        base = run.failure_signature("--- FAIL: TestOld (0.1s)\nFAIL\tp\t1s\n", [])
        mine = run.failure_signature("--- FAIL: TestOld (0.2s)\n--- FAIL: TestNew (0.0s)\nFAIL\tp\t2s\n", [])
        self.assertEqual(mine - base, {"--- FAIL: TestNew"})

    def test_subtests_and_passing_lines_are_not_failures(self) -> None:
        sig = run.failure_signature("ok  \texample.com/p\t0.1s\n    --- FAIL: TestX/sub (0.00s)\n--- PASS: TestY\n", [])
        self.assertEqual(sig, set())


# --- a code task a review will read needs no fact check -------------------------------------------

class AutoAcceptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = EnvVar(TP_TEST_AUTO_ACCEPT="1").__enter__()
        self.m = Mixed()
        self.h = self.m.h

    def tearDown(self) -> None:
        self.m.close()
        self.env.__exit__()

    def approve(self, participants, tasks=None, deliverables=("code", "docs")) -> None:
        m = self.m
        scope = m.scope(list(deliverables), participants)
        scope["split_tests"] = False
        m.approve(tasks or [m.code_task()], scope)

    def build(self) -> str:
        m, h = self.m, self.h
        h.tp("dispatch", "T01")
        (m.app / "test_calc.py").write_text(TEST_PY)
        h.tp("red", "T01")
        (m.app / "calc.py").write_text(CALC_MUL_PY)
        h.result("T01", "build", changed=["calc.py", "test_calc.py"])
        return h.tp("record", "T01", "--agent-id", "ca-1").out

    def test_a_code_task_a_batch_review_will_read_is_accepted_without_a_fact_check(self) -> None:
        self.approve(["code", "docs", "correctness"], [self.m.code_task(), self.m.doc_task(depends_on=["T01"])])
        out = self.build()
        self.assertIn("no fact check needed", out)
        self.assertNotIn("citation sample", out)
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "accepted")
        accepts = [e for e in run.Workflow(self.h.wf).events() if e.get("kind") == "accept"]
        self.assertTrue(accepts and accepts[-1].get("auto"))

    def test_with_no_review_to_come_the_manager_still_checks_it(self) -> None:
        self.approve(["code", "docs", "correctness"], [self.m.code_task(), self.m.doc_task(depends_on=["T01"])])
        finish_reviews(self.h)
        self.build()
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "needs_check")

    def test_a_document_is_never_auto_accepted(self) -> None:
        m, h = self.m, self.h
        self.approve(["docs", "doc-review"], [m.doc_task("T02")], deliverables=("docs",))
        h.tp("dispatch", "T02")
        m.note(cite="calc.py:1-2")
        h.result("T02", "author", changed=["docs/calc.md"])
        h.tp("record", "T02", "--agent-id", "da-1")
        self.assertEqual(h.state()["tasks"]["T02"]["status"], "needs_check")


if __name__ == "__main__":
    unittest.main()
