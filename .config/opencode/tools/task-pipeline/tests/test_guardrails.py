"""Guardrails from the pipeline review: the manager never shrinks or grows agreed work alone,
time is an estimate and never a stop, agents and the manager ask instead of guessing, every
acceptance criterion comes back with evidence, code is always reviewed, and workspace
snapshots stay fast on large repositories."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from harness import SKILL, Harness

sys.path.insert(0, str(SKILL / "scripts"))

CODE = dict(
    deliverables=[{"id": "D1", "kind": "code", "what": "calc gains mul()", "where": "app"}],
    participants=[{"agent": "test-author", "role": "tests", "why": "Writes mul's tests first."},
                  {"agent": "code-author", "role": "author", "why": "Implements mul to pass them."},
                  {"agent": "correctness-reviewer", "role": "reviewer", "why": "Reviews the D1 change."}],
    review="final",
)
FINAL_REVIEW = dict(review="final", participants=[
    {"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."},
    {"agent": "doc-reviewer", "role": "reviewer", "why": "Reviews the finished KB for accuracy."}])
S1 = "B1/doc-reviewer"


def brief(h: Harness, tid: str, name: str) -> str:
    return (h.run_dir(tid) / name).read_text()


class ScopeNeedsTheHumanTest(unittest.TestCase):
    """Skipping a task and shipping work with open blocking findings shrink what was agreed: only
    the human may do either."""

    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def block_t01(self) -> None:
        self.h.approved()
        self.h.tp("dispatch", "T01")
        self.h.tp("exception", "--task", "T01", "--summary", "The source repo is unreachable.")

    def test_only_the_human_can_skip_a_task(self) -> None:
        self.block_t01()
        res = self.h.tp("resolve", "--task", "T01", "--action", "skip", "--answer", "not needed", "--by", "manager",
                        expect=2)
        self.assertIn("human", res.text)
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "blocked")
        self.h.tp("resolve", "--task", "T01", "--action", "skip", "--answer", "Drop it; the repo is gone.",
                  "--by", "human")
        self.assertEqual(self.h.state()["tasks"]["T01"]["status"], "skipped")

    def test_every_resolve_names_who_decided(self) -> None:
        self.block_t01()
        res = self.h.tp("resolve", "--task", "T01", "--action", "answer", "--answer", "retry later", expect=2)
        self.assertIn("--by", res.text)

    def test_only_the_human_can_ship_a_batch_with_open_findings(self) -> None:
        h = self.h
        h.approved(h.plan([h.task("T01", "a.md")], final_checks=[]), **FINAL_REVIEW)
        h.author("T01", "a.md")
        h.tp("accept", "T01", "--note", "ok")
        state_path = h.wf / ".tp" / "state.json"
        state = json.loads(state_path.read_text())
        state["reviews"][S1].update(status="blocked", block="rounds", findings=[
            {"id": "F1", "state": "wrong", "blocking": True, "where": "a.md:1", "issue": "x", "task": "T01"}])
        state_path.write_text(json.dumps(state))
        res = h.tp("resolve", "--review", S1, "--action", "accept", "--answer", "ship it", "--by", "manager", expect=2)
        self.assertIn("human", res.text)
        h.tp("resolve", "--review", S1, "--action", "accept", "--answer", "Ship it; I'll fix F1.", "--by", "human")
        self.assertEqual(h.state()["reviews"][S1]["status"], "done")

    def test_a_large_plan_is_never_told_to_cut_work(self) -> None:
        h = self.h
        h.confirmed()
        h.write_json("plan.json", h.plan([h.task(f"T{i:02d}", f"area{i}/a.md") for i in range(1, 44)]))
        text = h.tp("plan", "check", expect=2).text
        self.assertNotIn("cut", text)
        self.assertIn("phase", text)

    def test_printed_resolve_hints_name_who_decides(self) -> None:
        # `--by` is required: every `tp resolve` line the tool prints must carry it, or the manager
        # copies a command that fails.
        missing = []
        for path in sorted((SKILL / "scripts").rglob("*.py")):
            lines = path.read_text().splitlines()
            for i, ln in enumerate(lines):
                if "`tp resolve" in ln and not ln.lstrip().startswith(('"""', "#")):
                    window = " ".join(lines[i:i + 3])
                    if "--by" not in window:
                        missing.append(f"{path.name}:{i + 1}")
        self.assertEqual(missing, [])


class ManagerAnswersClarifyTest(unittest.TestCase):
    """The manager may answer an agent's question when the plan already settles it, but only a
    human answer can change what a task must deliver."""

    def test_brief_says_only_human_answers_override_it(self) -> None:
        h = Harness()
        try:
            h.approved()
            h.tp("dispatch", "T01")
            h.result("T01", "author", status="needs_input", questions=["Which heading style?"])
            out = h.tp("record", "T01", "--agent-id", "a-1").out
            self.assertIn("--by", out)
            self.assertIn("never drop or loosen", out)
            h.tp("resolve", "--task", "T01", "--action", "answer", "--answer", "Sentence case.", "--by", "manager")
            h.good_article("architecture/overview.md")
            h.result("T01", "author", changed=["architecture/overview.md"])
            h.tp("record", "T01")
            h.tp("reject", "T01", "--reason", "Cite the line.")
            h.tp("dispatch", "T01")
            fix = brief(h, "T01", "brief-fix-1.md")
            self.assertIn("(manager)", fix)
            self.assertIn("Answers marked (human) win", fix)
            self.assertIn("never removes or loosens", fix)
        finally:
            h.close()


class WidenGuardrailTest(unittest.TestCase):
    """`tp widen` adds single files the same deliverable needs, at most two per task on the
    manager's say-so; more takes the human's answer."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def test_two_files_then_the_human(self) -> None:
        h = self.h
        h.tp("widen", "T01", "--path", "architecture/a.md", "--reason", "F1 needs it")
        h.tp("widen", "T01", "--path", "architecture/b.md", "--reason", "F2 needs it")
        res = h.tp("widen", "T01", "--path", "architecture/c.md", "--reason", "F3 needs it", expect=2)
        self.assertIn("human", res.text)
        self.assertIn("--answer", res.text)
        h.tp("widen", "T01", "--path", "architecture/c.md", "--reason", "F3 needs it",
             "--answer", "Yes, add the glossary too.")
        self.assertIn("architecture/c.md", h.read_json("plan.json")["tasks"][0]["paths"])
        self.assertRegex((h.wf / "decisions.md").read_text(), r"widen T01 paths · human: .*glossary")

    def test_widen_takes_files_not_folders_or_globs(self) -> None:
        h = self.h
        (h.kb / "architecture").mkdir()
        for bad in ("architecture", "architecture/", "architecture/*.md"):
            with self.subTest(path=bad):
                self.assertIn("one file", h.tp("widen", "T01", "--path", bad, "--reason", "x", expect=2).text)


class EstimatesNotDeadlinesTest(unittest.TestCase):
    """Minutes in a brief are estimates: no agent is told to stop because time ran out, and
    planning is never told to submit early. A task that turns out bigger than its brief stops
    for the manager, and is never cut down to fit."""

    def test_author_and_fix_briefs(self) -> None:
        h = Harness()
        try:
            h.approved()
            h.tp("dispatch", "T01")
            author = brief(h, "T01", "brief-author-0.md")
            self.assertNotIn("Time box", author)
            self.assertNotIn("cannot fit", author)
            self.assertIn("not a deadline", author)
            self.assertIn("bigger than its brief", author)
            self.assertIn("never cut it down", author)
            h.result("T01", "author", changed=[])
            h.tp("record", "T01", "--agent-id", "a-1")
            h.tp("lost", "T01", "--summary", "x", expect=2)      # not in flight: it failed its round
            h.tp("dispatch", "T01")
            self.assertNotIn("Time box", brief(h, "T01", "brief-fix-1.md"))
        finally:
            h.close()

    def test_review_and_verify_briefs(self) -> None:
        h = Harness()
        try:
            h.approved(h.plan([h.task("T01", "a.md")], final_checks=[]), **FINAL_REVIEW)
            h.author("T01", "a.md")
            h.tp("accept", "T01", "--note", "ok")
            h.tp("dispatch", S1)
            text = (h.wf / "runs" / "B1" / "brief-doc-reviewer-1.md").read_text()
            self.assertNotIn("Time box", text)
            self.assertIn("not a deadline", text)
        finally:
            h.close()

    def test_research_brief(self) -> None:
        h = Harness()
        try:
            h.confirmed(participants=[
                {"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."},
                {"agent": "codebase-researcher", "role": "research", "why": "Maps calc's areas for D1."}])
            qf = h.root / "q"
            qf.write_text("Which areas does calc split into?")
            h.tp("research", "add", "R1", "--agent", "codebase-researcher", "--purpose", "map",
                 "--questions-file", str(qf), "--done-when", "I can split it.")
            h.tp("dispatch", "R1")
            body = (h.wf / "recon" / "R1.brief.md").read_text()
            self.assertNotIn("hard", body)
            self.assertIn("not a deadline", body)
        finally:
            h.close()

    def test_planning_is_never_told_to_submit_early(self) -> None:
        h = Harness()
        try:
            h.confirmed()
            state_path = h.wf / ".tp" / "state.json"
            state = json.loads(state_path.read_text())
            state["created"] = "2020-01-01T00:00:00Z"
            state_path.write_text(json.dumps(state))
            self.assertFalse(any("submit what you have" in w for w in h.next()["warnings"]))
        finally:
            h.close()


class AgentsAskTest(unittest.TestCase):
    def test_the_brief_says_when_to_ask(self) -> None:
        h = Harness()
        try:
            h.approved()
            h.tp("dispatch", "T01")
            self.assertIn("hand back `needs_input` with the question instead of guessing",
                          brief(h, "T01", "brief-author-0.md"))
        finally:
            h.close()


class AcceptanceEvidenceTest(unittest.TestCase):
    """A `done` hand-back gives every Done-when item its evidence, and the manager's fact-check
    sample shows it."""

    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()
        self.h.tp("dispatch", "T01")
        self.h.good_article("architecture/overview.md")

    def tearDown(self) -> None:
        self.h.close()

    def test_the_brief_numbers_the_criteria_and_asks_for_evidence(self) -> None:
        text = brief(self.h, "T01", "brief-author-0.md")
        self.assertIn("1. Explains what Add does", text)
        self.assertIn('"acceptance"', text)

    def test_a_handback_without_evidence_is_refused(self) -> None:
        self.h.result("T01", "author", changed=["architecture/overview.md"], acceptance=None)
        res = self.h.tp("record", "T01", "--agent-id", "a-1", expect=2)
        self.assertIn("acceptance", res.text)
        self.assertIn("T01", self.h.state()["in_flight"])         # nothing recorded: fix the file, record again

    def test_every_criterion_needs_its_own_evidence(self) -> None:
        self.h.result("T01", "author", changed=["architecture/overview.md"],
                      acceptance=[{"criterion": 1, "evidence": ""}])
        self.assertIn("criterion 1", self.h.tp("record", "T01", "--agent-id", "a-1", expect=2).text)

    def test_the_sample_shows_the_evidence(self) -> None:
        self.h.result("T01", "author", changed=["architecture/overview.md"],
                      acceptance=[{"criterion": 1, "evidence": "architecture/overview.md:3 cites calc/calc.go:5"}])
        out = self.h.tp("record", "T01", "--agent-id", "a-1").out
        self.assertIn("Explains what Add does", out)
        self.assertIn("architecture/overview.md:3 cites calc/calc.go:5", out)

    def test_an_agent_briefed_before_evidence_existed_is_not_refused(self) -> None:
        state_path = self.h.wf / ".tp" / "state.json"
        state = json.loads(state_path.read_text())
        state["in_flight"]["T01"].pop("evidence", None)            # dispatched by the previous version
        state_path.write_text(json.dumps(state))
        self.h.result("T01", "author", changed=["architecture/overview.md"], acceptance=None)
        self.h.tp("record", "T01", "--agent-id", "a-1")


class CodeIsAlwaysReviewedTest(unittest.TestCase):
    def test_code_deliverables_need_a_review(self) -> None:
        h = Harness()
        try:
            h.init()
            scope = h.scope(**dict(CODE, review="none", participants=CODE["participants"][:2]))
            h.write_json("scope.json", scope)
            self.assertIn("code", h.tp("scope", "check", expect=2).text)
            h.write_json("scope.json", h.scope(**CODE))
            h.tp("scope", "check")
        finally:
            h.close()


class SnapshotCacheTest(unittest.TestCase):
    """Snapshots reuse a file's hash while its size and mtime are unchanged (as git's index does),
    re-hashing anything touched near the moment the cache was written."""

    def setUp(self) -> None:
        from pipeline import snapshot
        self.snapshot = snapshot
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.root = Path(self.tmp.name) / "ws"
        self.root.mkdir()
        self.cache = Path(self.tmp.name) / "cache.json"
        self.old = time.time() - 3600

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, rel: str, text: str, mtime=None) -> Path:
        p = self.root / rel
        p.write_text(text)
        if mtime is not None:
            os.utime(p, (mtime, mtime))
        return p

    def test_an_edit_is_seen(self) -> None:
        self.write("a.md", "one\n", self.old)
        before = self.snapshot.take(self.root, cache=self.cache)
        self.write("a.md", "two\n")
        self.assertEqual(self.snapshot.diff(before, self.snapshot.take(self.root, cache=self.cache)), ["a.md"])

    def test_a_same_size_edit_right_after_caching_is_seen(self) -> None:
        first = os.stat(self.write("a.md", "one\n")).st_mtime_ns
        before = self.snapshot.take(self.root, cache=self.cache)   # hashed within the racy window
        p = self.write("a.md", "two\n")
        os.utime(p, ns=(first, first))                         # same size, same mtime: only the racy rule sees it
        self.assertEqual(self.snapshot.diff(before, self.snapshot.take(self.root, cache=self.cache)), ["a.md"])

    def test_the_cache_is_used_for_untouched_files(self) -> None:
        # Documents the accepted blind spot (the same one git's stat cache has): content swapped
        # under an unchanged size and mtime goes unnoticed — proof the cached hash was reused.
        self.write("a.md", "one\n", self.old)
        before = self.snapshot.take(self.root, cache=self.cache)
        self.write("a.md", "two\n", self.old)
        self.assertEqual(self.snapshot.take(self.root, cache=self.cache), before)
        self.assertNotEqual(self.snapshot.take(self.root), before)   # without the cache it is seen

    def test_only_limits_the_walk_to_matching_paths(self) -> None:
        self.write("a.md", "a\n")
        (self.root / "sub").mkdir()
        self.write("sub/b.md", "b\n")
        self.assertEqual(sorted(self.snapshot.take(self.root, only=["sub/**"])), ["sub/b.md"])


if __name__ == "__main__":
    unittest.main()
