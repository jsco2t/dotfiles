"""Fixes from four live runs (KUB-1330, KUB-1331, KUB-1336, KUB-1346) that kept work from
finishing hands-off: three runs sat overnight on a question the pipeline could have settled or
asked earlier, and agents were sent back for edits that changed no behaviour.

- The test-weakening gate counted reworded comments and gofmt realignment as weakened tests.
- A result summary a few words over the limit cost a round trip to an agent with a 200k context.
- Jira refused a post: the converter put `code` and `em` marks on the same text.
- The survey never compared the Go toolchain the repo pins with the one on PATH, so a newer local
  Go failed `make test` at the end of three runs and the human had to diagnose it.
- `tp final` had no way to finish after the human chose to leave a pre-existing failure, and
  it sent the run's own breakage to the human instead of to a fix task.
- Pinning a check command to the repo's toolchain needed the human's approval.
- A Jira comment or Confluence page planned as a single deliverable needed a scope change, and so
  a question, once planning found that a draft and its post are two deliverables.
- Outside writes the human pre-approved at the start still waited on a question at the end.
- Time waiting on an asked question counted against the budget as work.
"""
from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

from harness import Harness, git
from scenarios import FakeCli, Mixed

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pipeline import adf, common, run, survey  # noqa: E402

DRAFT = "wf:drafts/kub-1-comment.md"


def _weakened(old: str, new: str, name: str = "x_test.go"):
    with tempfile.TemporaryDirectory() as d:
        a, b = Path(d) / "old" / name, Path(d) / "new" / name
        a.parent.mkdir()
        b.parent.mkdir()
        a.write_text(old)
        b.write_text(new)
        return run._tests_weakened(a, b)


class WeakeningGateTest(unittest.TestCase):
    """Comments and alignment are not assertions; dropped assertions still fail the gate."""

    GO = ('package x\n\n// TestRefusal checks that every refusal names the contract code,\n'
          '// and that nothing reaches the member.\n'
          'func TestRefusal(t *testing.T) {\n'
          '\tcases := []struct{ Code, Message string }{\n'
          '\t\t{Code:    "agentless-member", Message: "refused"},\n'
          '\t}\n'
          '\tif got := refuse(); got != "agentless-member" {\n'
          '\t\tt.Fatalf("got %q", got)\n\t}\n\t_ = cases\n}\n')

    def test_a_reworded_comment_is_not_weakening(self) -> None:
        new = self.GO.replace("// TestRefusal checks that every refusal names the contract code,\n"
                              "// and that nothing reaches the member.\n",
                              "// TestRefusal: each refusal carries the code; the member sees nothing.\n")
        self.assertIsNone(_weakened(self.GO, new))

    def test_gofmt_realignment_is_not_weakening(self) -> None:
        new = self.GO.replace('{Code:    "agentless-member", Message: "refused"}',
                              '{Code: "agentless-member", Message: "refused"}')
        self.assertIsNone(_weakened(self.GO, new))

    def test_a_dropped_assertion_is_still_weakening(self) -> None:
        new = self.GO.replace('\tif got := refuse(); got != "agentless-member" {\n\t\tt.Fatalf("got %q", got)\n\t}\n',
                              "")
        self.assertIn("agentless-member", _weakened(self.GO, new) or "")

    def test_an_example_tests_expected_output_is_an_assertion(self) -> None:
        old = "func ExampleMul() {\n\tfmt.Println(Mul(2, 3))\n\t// Output:\n\t// 6\n}\n"
        self.assertIn("6", _weakened(old, "func ExampleMul() {\n\tfmt.Println(Mul(2, 3))\n\t// Output:\n}\n") or "")
        self.assertIn("Output", _weakened(old, "func ExampleMul() {\n\tfmt.Println(Mul(2, 3))\n}\n") or "")

    def test_a_build_constraint_is_not_a_comment(self) -> None:
        old = "//go:build e2e\n\npackage x\n"
        self.assertIn("go:build", _weakened(old, "package x\n") or "")

    def test_a_dereference_is_code_not_a_block_comment(self) -> None:
        old = "func TestX(t *testing.T) {\n\t*p = want\n\tcheck(t, p)\n}\n"
        self.assertIn("*p = want", _weakened(old, "func TestX(t *testing.T) {\n\tcheck(t, p)\n}\n") or "")

    def test_a_rust_test_attribute_is_not_a_comment(self) -> None:
        old = "#[cfg(test)]\nmod tests {\n    #[test]\n    fn adds() { assert_eq!(add(1, 2), 3); }\n}\n"
        new = "#[cfg(test)]\nmod tests {\n    fn adds() { assert_eq!(add(1, 2), 3); }\n}\n"
        self.assertIn("#[test]", _weakened(old, new, "lib_test.rs") or "")

    def test_python_comments_are_not_assertions(self) -> None:
        old = "# The sum of two numbers.\ndef test_add():\n    assert add(1, 2) == 3\n"
        new = "# Adding two numbers.\ndef test_add():\n    assert add(1, 2) == 3\n"
        self.assertIsNone(_weakened(old, new, "test_x.py"))


class AdfMarksTest(unittest.TestCase):
    """ADF allows the code mark only beside a link: Jira answers 400 INVALID_INPUT otherwise."""

    def marks(self, md: str):
        para = adf.to_adf(md)["content"][0]
        return {n["text"]: sorted(m["type"] for m in n.get("marks", [])) for n in para["content"]}

    def test_code_inside_italic_drops_the_italic(self) -> None:
        marks = self.marks("*Rule: `ReasonAgentless` holds*")
        self.assertEqual(marks["ReasonAgentless"], ["code"])
        self.assertEqual(marks["Rule: "], ["em"])

    def test_code_inside_bold_drops_the_bold(self) -> None:
        self.assertEqual(self.marks("**`make test` passes**")["make test"], ["code"])

    def test_code_inside_a_link_keeps_the_link(self) -> None:
        self.assertEqual(self.marks("[`calc.go`](https://x.test/c)")["calc.go"], ["code", "link"])


class LongSummaryTest(unittest.TestCase):
    """A summary over 80 words is trimmed where it is shown, not sent back to its agent."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def test_a_slightly_long_summary_is_recorded(self) -> None:
        h = self.h
        h.tp("dispatch", "T01")
        h.good_article("architecture/overview.md")
        h.result("T01", "author", summary="word " * 94, changed=["architecture/overview.md"])
        h.tp("record", "T01")
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "needs_check")

    def test_a_runaway_summary_is_still_refused(self) -> None:
        h = self.h
        h.tp("dispatch", "T01")
        h.result("T01", "author", summary="word " * 500)
        self.assertIn("summary", h.tp("record", "T01", expect=2).text)


def _fake_go(bin_dir: Path, version: str) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    go = bin_dir / "go"
    go.write_text("#!/bin/sh\n"
                  f'if [ "$1" = env ] && [ "$2" = GOVERSION ]; then echo go{version}; exit 0; fi\n'
                  f'if [ "$1" = version ]; then echo "go version go{version} linux/amd64"; exit 0; fi\n'
                  "exit 1\n")
    go.chmod(go.stat().st_mode | stat.S_IEXEC)


class ToolchainPinTest(unittest.TestCase):
    """The survey names the Go the repo pins when PATH has another: three runs failed their final
    `make test` on a newer local Go and asked the human about failures the run never caused."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="tp-pin-"))
        self.repo = self.tmp / "repo"
        (self.repo / "build").mkdir(parents=True)
        (self.repo / "go.mod").write_text("module example.com/x\n\ngo 1.26.0\n")
        (self.repo / "build" / "versions.mk").write_text("# pins\ngo_version         = 1.26.2\nnode_version = 22\n")
        (self.repo / "Makefile").write_text("include build/versions.mk\ntest:\n\tgo test ./...\n")
        self.old_path = os.environ["PATH"]

    def tearDown(self) -> None:
        os.environ["PATH"] = self.old_path
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def use_go(self, version: str) -> None:
        _fake_go(self.tmp / "bin", version)
        os.environ["PATH"] = f"{self.tmp / 'bin'}{os.pathsep}{self.old_path}"

    def test_a_versions_mk_pin_is_found(self) -> None:
        pins = survey.toolchain_pins(self.repo)
        self.assertIn(("go", "1.26.2", "build/versions.mk"), [(p["tool"], p["version"], p["source"]) for p in pins])

    def test_go_mod_toolchain_and_dot_go_version_are_pins_but_the_go_line_is_not(self) -> None:
        (self.repo / "build" / "versions.mk").unlink()
        self.assertEqual(survey.toolchain_pins(self.repo), [])           # `go 1.26.0` is a minimum, not a pin
        (self.repo / "go.mod").write_text("module example.com/x\n\ngo 1.26.0\n\ntoolchain go1.26.3\n")
        self.assertEqual([p["version"] for p in survey.toolchain_pins(self.repo)], ["1.26.3"])
        (self.repo / ".go-version").write_text("1.26.3\n")
        self.assertEqual({p["source"] for p in survey.toolchain_pins(self.repo)}, {"go.mod", ".go-version"})

    def test_a_mismatch_prints_the_prefix_for_checks_and_tests(self) -> None:
        self.use_go("1.27.1")
        notes = survey.toolchain_notes(self.repo)
        text = "\n".join(notes)
        self.assertIn("1.26.2", text)
        self.assertIn("1.27.1", text)
        self.assertIn("GOTOOLCHAIN=go1.26.2", text)
        self.assertIn("go env GOROOT", text)                              # gofmt comes from the pinned bin too
        self.assertIn("test_cmd", text)

    def test_a_matching_toolchain_says_nothing(self) -> None:
        self.use_go("1.26.2")
        self.assertEqual(survey.toolchain_notes(self.repo), [])

    def test_the_survey_command_shows_the_mismatch_near_the_top(self) -> None:
        self.use_go("1.27.1")
        h = Harness()
        try:
            h.init()
            git(self.repo, "init", "-q", "-b", "main")
            out = h.tp("survey", str(self.repo), "--name", "repo").out
            self.assertIn("GOTOOLCHAIN=go1.26.2", "\n".join(out.splitlines()[:6]))
            data = json.loads((h.wf / "survey" / "repo.json").read_text())
            self.assertEqual(data["toolchains"][0]["version"], "1.26.2")
        finally:
            h.close()


class FinalCheckTest(unittest.TestCase):
    """A run's own breakage is a fix task; a pre-existing failure is asked about once, early, and
    the answer lets the run finish."""

    def setUp(self) -> None:
        self.h = Harness()
        self.flag = self.h.root / "broken"
        self.other = self.h.root / "broken-too"

    def tearDown(self) -> None:
        self.h.close()

    def approve(self, **scope) -> None:
        self.h.approved(self.h.plan(checks={"lint": {"cmd": f"test ! -e {self.flag}"},
                                            "unit": {"cmd": f"test ! -e {self.other}"}},
                                    final_checks=["docs-all", "lint", "unit"]), **scope)

    def finish(self) -> None:
        h = self.h
        for tid, rel in (("T01", "architecture/overview.md"), ("T02", "build/guide.md")):
            h.author(tid, rel, agent_id=f"a-{tid}")
            h.tp("accept", tid, "--note", "ok")
        h.tp("dispatch", "T03")
        (h.kb / "index.md").write_text("# KB\n\n- [O](architecture/overview.md)\n- [B](build/guide.md)\n")
        h.result("T03", "author", changed=["index.md"])
        h.tp("record", "T03", "--agent-id", "a-3")
        h.tp("accept", "T03", "--note", "ok")

    def test_the_runs_own_failure_goes_to_a_fix_task_not_the_human(self) -> None:
        self.approve()
        self.finish()
        self.flag.write_text("x")
        err = self.h.tp("final", expect=2).text
        self.assertIn("plan amend --delegated", err)
        self.assertNotIn("`tp exception --summary ...` and ask the human", err)

    def test_baseline_failures_are_asked_about_at_the_start(self) -> None:
        self.flag.write_text("x")
        self.approve()
        out = self.h.tp("baseline").out
        self.assertIn("baseline --leave --answer", out)
        self.assertIn("now", out)

    def test_leaving_a_pre_existing_failure_lets_final_finish(self) -> None:
        self.flag.write_text("x")
        self.approve()
        self.h.tp("baseline")
        self.h.tp("baseline", "--leave", "--answer", "Leave it, it is not ours")
        self.finish()
        self.h.tp("final")
        self.assertEqual(self.h.state()["phase"], "DONE")
        report = (self.h.wf / "report.md").read_text()
        self.assertIn("pre-existing", report)
        self.assertIn("Leave it, it is not ours", report)

    def test_leaving_a_failure_masks_no_new_one(self) -> None:
        self.flag.write_text("x")
        self.approve()
        self.h.tp("baseline")
        self.h.tp("baseline", "--leave", "--answer", "Leave it")
        self.finish()
        self.other.write_text("x")
        err = self.h.tp("final", expect=2).text
        self.assertIn("final check unit failed", err)
        self.assertNotEqual(self.h.state()["phase"], "DONE")

    def test_leave_needs_a_recorded_failure_and_the_humans_words(self) -> None:
        self.approve()
        self.h.tp("baseline")
        self.assertIn("nothing", self.h.tp("baseline", "--leave", "--answer", "Leave it", expect=2).text)

    def test_a_baseline_after_work_has_landed_is_refused(self) -> None:
        self.approve()
        self.h.author("T01", "architecture/overview.md", agent_id="a-T01")
        self.flag.write_text("x")                        # the run's own breakage must not become "pre-existing"
        err = self.h.tp("baseline", expect=2).text
        self.assertIn("before the first dispatch", err)
        self.assertNotIn("final_baseline", self.h.state())

    def test_a_timeout_is_advised_as_a_slow_check_not_a_fix_task(self) -> None:
        advice = run.final_failure_advice(["check:unit:timeout"], set())
        self.assertIn(str(run.CHECK_TIMEOUT), advice)
        self.assertNotIn("fix task", advice)
        self.assertIn("fix task", run.final_failure_advice(["check:unit"], set()))

    def test_a_timeout_is_never_a_known_failure(self) -> None:
        self.assertNotEqual(run.check_key("unit", "timed out after 540s"), run.check_key("unit", "exit 2"))


class PinnedCheckAmendTest(unittest.TestCase):
    """Running a check under the repo's pinned toolchain changes no work: the manager settles it."""

    def test_an_env_prefix_on_a_check_is_the_managers_to_settle(self) -> None:
        h = Harness()
        try:
            (h.src / ".go-version").write_text("1.26.2\n")
            h.approved(h.plan(checks={"unit": {"cmd": "true"}}, final_checks=["docs-all", "unit"]))
            h.tp("plan", "amend")
            draft = h.read_json("plan-amend.json")
            draft["checks"]["unit"]["cmd"] = 'GOTOOLCHAIN=go1.26.2 PATH="$(GOTOOLCHAIN=go1.26.2 go env GOROOT)/bin:$PATH" true'
            (h.wf / "plan-amend.json").write_text(json.dumps(draft))
            out = h.tp("plan", "amend").out
            self.assertIn("--delegated", out)
            self.assertNotIn("Ask the human", out)
            h.tp("plan", "amend", "--delegated", "--note", "Run unit under the Go the repo pins.")
            self.assertIn("GOTOOLCHAIN", h.read_json("plan.json")["checks"]["unit"]["cmd"])
        finally:
            h.close()

    def test_a_prefix_that_could_change_what_runs_goes_to_the_human(self) -> None:
        for cmd in ('PATH=/tmp/fakebin:$PATH true',                                   # a fake tool shadows the real one
                    'export GOTOOLCHAIN=go1.26.2 PATH="$(touch /tmp/x; echo /bin):$PATH"; true',
                    'GOTOOLCHAIN=go1.26.2 GOROOT=/tmp/fake true',
                    'GOTOOLCHAIN="$(id)" true'):
            with self.subTest(cmd=cmd):
                h = Harness()
                try:
                    h.approved(h.plan(checks={"unit": {"cmd": "true"}}, final_checks=["docs-all", "unit"]))
                    h.tp("plan", "amend")
                    draft = h.read_json("plan-amend.json")
                    draft["checks"]["unit"]["cmd"] = cmd
                    (h.wf / "plan-amend.json").write_text(json.dumps(draft))
                    self.assertIn("Ask the human", h.tp("plan", "amend").out)
                finally:
                    h.close()

    def test_the_survey_prefix_itself_is_the_managers_to_settle(self) -> None:
        h = Harness()
        try:
            (h.src / ".go-version").write_text("1.26.2\n")
            h.approved(h.plan(checks={"unit": {"cmd": "true"}}, final_checks=["docs-all", "unit"]))
            h.tp("plan", "amend")
            draft = h.read_json("plan-amend.json")
            draft["checks"]["unit"]["cmd"] = survey.pin_prefix("1.26.2") + "true"
            (h.wf / "plan-amend.json").write_text(json.dumps(draft))
            self.assertNotIn("Ask the human", h.tp("plan", "amend").out)
        finally:
            h.close()

    def test_a_version_no_workspace_pins_goes_to_the_human(self) -> None:
        for pinned in (None, "1.26.2"):
            with self.subTest(pinned=pinned):
                h = Harness()
                try:
                    if pinned:
                        (h.src / ".go-version").write_text(pinned + "\n")
                    h.approved(h.plan(checks={"unit": {"cmd": "true"}}, final_checks=["docs-all", "unit"]))
                    h.tp("plan", "amend")
                    draft = h.read_json("plan-amend.json")
                    draft["checks"]["unit"]["cmd"] = survey.pin_prefix("1.20.0") + "true"
                    (h.wf / "plan-amend.json").write_text(json.dumps(draft))
                    self.assertIn("Ask the human", h.tp("plan", "amend").out)
                finally:
                    h.close()

    def test_any_other_rewrite_still_goes_to_the_human(self) -> None:
        h = Harness()
        try:
            h.approved(h.plan(checks={"unit": {"cmd": "make test"}}, final_checks=["docs-all", "unit"]))
            h.tp("plan", "amend")
            draft = h.read_json("plan-amend.json")
            draft["checks"]["unit"]["cmd"] = "go test ./internal/x"
            (h.wf / "plan-amend.json").write_text(json.dumps(draft))
            self.assertIn("Ask the human", h.tp("plan", "amend").out)
        finally:
            h.close()


class DraftAndPostTest(unittest.TestCase):
    """A comment or page the run posts is two deliverables — the reviewed draft and the post — and
    the scope check says so before the human confirms, so planning never has to ask again."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.init()

    def tearDown(self) -> None:
        self.h.close()

    def check(self, deliverables, participants=None) -> str:
        scope = self.h.scope(deliverables=deliverables, participants=participants or [
            {"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."},
            {"agent": "doc-author", "role": "author", "why": "Drafts the KUB-1 comment text (D2)."}])
        self.h.write_json("scope.json", scope)
        return self.h.tp("scope", "check", expect=None).text

    KB = {"id": "D1", "kind": "kb", "what": "A KB covering calc's code and build", "where": "kb"}

    def test_a_draft_with_no_post_is_refused_with_the_pair_spelled_out(self) -> None:
        out = self.check([self.KB, {"id": "D2", "kind": "docs", "what": "The KUB-1 comment text",
                                    "where": "wf:drafts/kub-1-comment.md"}])
        self.assertIn("integration", out)
        self.assertIn("jira:", out)
        self.assertNotIn("scope ok", out)

    def test_a_jira_kind_names_the_pair(self) -> None:
        out = self.check([self.KB, {"id": "D2", "kind": "jira", "what": "A comment on KUB-1", "where": "KUB-1"}])
        self.assertIn("wf:drafts/", out)
        self.assertIn("integration", out)

    def test_a_post_with_no_draft_is_warned_about(self) -> None:
        out = self.check([self.KB, {"id": "D2", "kind": "integration", "what": "A comment on KUB-1",
                                    "where": "jira:KUB-1"}],
                         [{"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."}])
        self.assertIn("scope ok", out)
        self.assertIn("WARN", out)
        self.assertIn("wf:drafts/", out)

    def test_the_pair_passes(self) -> None:
        out = self.check([self.KB, {"id": "D2", "kind": "docs", "what": "The KUB-1 comment text",
                                    "where": "wf:drafts/kub-1-comment.md"},
                          {"id": "D3", "kind": "integration", "what": "The D2 comment posted on KUB-1",
                           "where": "jira:KUB-1"}])
        self.assertIn("scope ok", out)
        self.assertNotIn("wf:drafts/", out.split("scope ok")[0])


class PreapprovedPostTest(unittest.TestCase):
    """The human can approve outside writes at the start; the post then goes out after its dry run
    without a question at the end of the run (one run waited ten hours on that question)."""

    def setUp(self) -> None:
        self.m = m = Mixed()
        self.jira = FakeCli(m.h.root)
        self.scope = m.scope(["code", "docs", "integration"],
                             ["tests", "code", "docs", "correctness", "doc-review"])
        self.draft_task = m.doc_task("T02", path=DRAFT, depends_on=["T01"],
                                     brief="Write the KUB-1 comment text about mul, citing calc.py.")
        self.publish = {"id": "T03", "title": "Post the KUB-1 comment", "serves": ["D3"], "workspace": "app",
                        "publish": {"to": "jira-comment", "target": "KUB-1", "body": DRAFT},
                        "acceptance": ["The comment is posted once and reads back as sent."],
                        "estimate_min": 5, "depends_on": ["T02"]}

    def tearDown(self) -> None:
        self.jira.restore()
        self.m.close()

    def ready_to_post(self, outside_writes=None, text: str = "## Fixed\n\n- `mul` multiplies (`calc.py:5-6`).\n") -> None:
        m = self.m
        scope = dict(self.scope, **({"outside_writes": outside_writes} if outside_writes else {}))
        m.approve([m.code_task("T01"), self.draft_task, self.publish], scope)
        m.code_done("T01")
        m.h.tp("dispatch", "T02")
        draft = m.h.wf / "drafts" / "kub-1-comment.md"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text(text)
        m.h.result("T02", "author", changed=[str(draft)])
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

    def test_a_preapproved_post_needs_no_question(self) -> None:
        self.ready_to_post({"approval": "pre-approved", "answer": "Post them, no need to ask"})
        out = self.m.h.tp("publish", "T03").out
        self.assertIn("--preapproved", out)
        self.assertNotIn("ask once", out.lower())
        self.m.h.tp("publish", "T03", "--preapproved")
        self.assertEqual(len(self.jira.writes()), 1)
        self.assertEqual(self.m.status("T03"), "accepted")
        self.assertIn("Post them, no need to ask", (self.m.h.wf / "decisions.md").read_text())

    def test_without_preapproval_the_flag_is_refused(self) -> None:
        self.ready_to_post()
        self.m.h.tp("publish", "T03")
        self.assertIn("pre-approved", self.m.h.tp("publish", "T03", "--preapproved", expect=2).text)
        self.assertEqual(self.jira.writes(), [])

    def test_a_dry_run_warning_goes_to_the_human_despite_preapproval(self) -> None:
        self.ready_to_post({"approval": "pre-approved", "answer": "Post them"},
                           text="## Fixed\n\n- `mul` multiplies; a ** b stays literal.\n")
        out = self.m.h.tp("publish", "T03").out
        self.assertIn("WARN", out)
        self.assertNotIn("--preapproved", out)
        self.assertIn("WARN", self.m.h.tp("publish", "T03", "--preapproved", expect=2).text)
        self.assertEqual(self.jira.writes(), [])

    def test_a_preapproval_written_into_scope_after_confirmation_counts_for_nothing(self) -> None:
        self.ready_to_post()
        scope = json.loads((self.m.h.wf / "scope.json").read_text())
        scope["outside_writes"] = {"approval": "pre-approved", "answer": "Post them"}
        (self.m.h.wf / "scope.json").write_text(json.dumps(scope))
        self.assertNotIn("--preapproved", self.m.h.tp("publish", "T03", expect=None).text)
        self.assertIn("confirmed", self.m.h.tp("publish", "T03", "--preapproved", expect=2).text)
        self.assertEqual(self.jira.writes(), [])

    def test_preapproval_still_needs_the_dry_run(self) -> None:
        self.ready_to_post({"approval": "pre-approved", "answer": "Post them"})
        self.assertIn("dry run", self.m.h.tp("publish", "T03", "--preapproved", expect=2).text)
        self.assertEqual(self.jira.writes(), [])


class WaitingOnTheHumanTest(unittest.TestCase):
    """An open question, an asked gate, or a dry run shown to the human, with nothing in flight,
    is time waiting on the human — not time the budget charges to the work."""

    def state(self, **over):
        base = {"phase": "EXECUTING", "in_flight": {}, "tasks": {"T01": {"status": "pending"}}, "reviews": {}}
        base.update(over)
        return base

    def test_an_open_question_is_waiting(self) -> None:
        self.assertTrue(common._waiting_on_human(self.state(questions={"Q1": {"text": "?", "asked": "x"}})))

    def test_an_answered_question_is_not(self) -> None:
        self.assertFalse(common._waiting_on_human(self.state(
            questions={"Q1": {"text": "?", "asked": "x", "answered": "y"}})))

    def test_a_shown_dry_run_is_waiting(self) -> None:
        self.assertTrue(common._waiting_on_human(self.state(
            tasks={"T03": {"status": "pending", "publish": {"sha": "s", "ts": "x"}}})))

    def test_work_in_flight_is_never_waiting(self) -> None:
        self.assertFalse(common._waiting_on_human(self.state(
            in_flight={"T02": {}}, questions={"Q1": {"text": "?", "asked": "x"}})))


if __name__ == "__main__":
    unittest.main()
