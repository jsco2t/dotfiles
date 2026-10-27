"""The manager's loop costs one large-context turn per call, so tp does more per call: `advance`
records and dispatches what follows, `record` prints one fact-check sample with its source lines
quoted, closeout sorts noticed items itself, and a fix round goes to a fresh agent once the old
one's context is too large to be worth resuming."""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

from harness import Harness
from scenarios import Mixed

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


class AdvanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.m = m = Mixed()
        m.approve([m.code_task("T01")], m.scope(["code"], ["tests", "code", "correctness"]))

    def tearDown(self) -> None:
        self.m.close()

    def test_advance_records_and_dispatches_what_follows_in_one_call(self) -> None:
        m = self.m
        m.h.tp("dispatch", "T01")
        from scenarios import TEST_PY
        (m.app / "test_calc.py").write_text(TEST_PY)
        m.h.result("T01", "tests", changed=["test_calc.py"])
        out = m.h.tp("advance", "T01", "--agent-id", "ta-1").out
        self.assertIn("red", out)
        self.assertIn("DISPATCH T01 · impl · code-author", out)
        self.assertIn('Agent(subagent_type="code-author"', out)
        self.assertEqual(m.h.state()["in_flight"]["T01"]["step"], "impl")

    def test_advance_stops_at_the_fact_check(self) -> None:
        m = self.m
        m.red("T01")
        m.h.tp("dispatch", "T01")
        from scenarios import CALC_MUL_PY
        (m.app / "calc.py").write_text(CALC_MUL_PY)
        m.h.result("T01", "impl", changed=["calc.py"])
        out = m.h.tp("advance", "T01", "--agent-id", "ca-1").out
        self.assertIn("green", out)
        self.assertIn("tp accept T01", out)
        self.assertNotIn("DISPATCH", out)


class LeanRecordTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = h = Harness()
        task = h.task("T01", "architecture/overview.md",
                      acceptance=["Explains Add.", "Cites calc.go.", "Links nothing broken."])
        h.approved(plan=h.plan([task], final_checks=[]))

    def tearDown(self) -> None:
        self.h.close()

    def test_record_prints_one_sampled_criterion_with_its_cited_lines(self) -> None:
        h = self.h
        h.tp("dispatch", "T01")
        h.good_article("architecture/overview.md")
        h.result("T01", "author", changed=["architecture/overview.md"],
                 acceptance=[{"criterion": i, "evidence": f"overview.md:3 cites calc/calc.go:5 (item {i})"}
                             for i in (1, 2, 3)])
        out = h.tp("record", "T01").out
        self.assertEqual(len([ln for ln in out.splitlines() if "(item " in ln]), 1)
        self.assertIn("calc/calc.go:5:", out)
        self.assertIn("return a + b", out)
        self.assertIn("--part acceptance", out)
        full = h.tp("show", "T01", "--part", "acceptance").out
        self.assertEqual(full.count("(item "), 3)


class CloseoutSortingTest(unittest.TestCase):
    def test_near_duplicates_that_differ_only_in_line_numbers_merge(self) -> None:
        from pipeline.common import Workflow
        with tempfile.TemporaryDirectory() as tmp:
            wf = Workflow(Path(tmp))
            wf.noticed("T06", "LICENSING.md:329-332 has no conflict status.")
            wf.noticed("T06", "LICENSING.md:340-343 has no conflict status.")
            self.assertEqual(len(wf.noticed_items()), 1)
            self.assertIn("×2", wf.noticed_items()[0])

    def run_to_closeout(self, noticed) -> Harness:
        h = Harness()
        self.addCleanup(h.close)
        h.approved(plan=h.plan([h.task("T01", "architecture/overview.md")], final_checks=[]))
        h.tp("dispatch", "T01")
        h.good_article("architecture/overview.md")
        h.result("T01", "author", changed=["architecture/overview.md"], noticed=noticed)
        h.tp("record", "T01")
        h.tp("accept", "T01", "--note", "ok")
        return h

    def test_plain_chatter_is_classified_without_the_manager(self) -> None:
        h = self.run_to_closeout(["Implementation note: the list is sorted before writing.",
                                  "An untracked file from a sibling task was left untouched.",
                                  "webhookauth.go still writes the pair non-atomically."])
        out = h.tp("closeout").out
        self.assertIn("2 classified automatically", out)
        self.assertIn("webhookauth.go", out)
        self.assertNotIn("Implementation note", out)
        num = re.search(r"(\d+)\. \[UNCLASSIFIED\][^\n]*webhookauth", out).group(1)
        h.tp("closeout", "--item", num, "--class", "observation")
        self.assertEqual(h.next()["actions"][0]["action"], "final")

    def test_several_items_classify_in_one_call(self) -> None:
        h = self.run_to_closeout(["first gap in the parser.", "second gap in the parser.",
                                  "third gap in the parser."])
        h.tp("closeout", "--items", "1,3", "--class", "followup", "--note", "the parser needs its own task")
        h.tp("closeout", "--items", "2", "--class", "observation")
        self.assertEqual(h.next()["actions"][0]["why"], "deferred or follow-up work awaits the human's decision")

    def test_the_question_offers_fixing_or_filing_never_a_local_file(self) -> None:
        h = self.run_to_closeout(["webhookauth.go still writes the pair non-atomically."])
        h.tp("closeout", "--item", "1", "--class", "followup", "--note", "a crash can tear the config file")
        out = h.tp("closeout", "--ask").out
        self.assertIn("fix them now", out)
        self.assertIn("file them as tickets", out)
        self.assertIn("Never offer to park them in a local file", out)

    def test_the_noticed_field_asks_only_for_what_someone_must_act_on(self) -> None:
        h = Harness()
        self.addCleanup(h.close)
        h.approved()
        h.tp("dispatch", "T01")
        brief = (h.run_dir("T01") / "brief-author-0.md").read_text()
        self.assertIn("someone must act on", brief)


class FreshAgentTest(unittest.TestCase):
    """Resuming an agent re-reads its whole context every turn; past a threshold a fresh agent
    with a full fix brief is cheaper."""

    def setUp(self) -> None:
        self.m = m = Mixed()
        self.transcripts = m.h.root / "projects"
        self.saved = os.environ.get("TP_TRANSCRIPTS")
        os.environ["TP_TRANSCRIPTS"] = str(self.transcripts)
        m.approve([m.doc_task("T01")], m.scope(["docs"], ["docs", "doc-review"]))
        m.doc_done("T01", cite="calc.py:1-2", agent_id="a5c0ffee")
        m.h.tp("resolve", "--task", "T01", "--action", "reopen", "--answer", "tighten the note", "--by", "manager")

    def tearDown(self) -> None:
        if self.saved is None:
            os.environ.pop("TP_TRANSCRIPTS", None)
        else:
            os.environ["TP_TRANSCRIPTS"] = self.saved
        self.m.close()

    def transcript(self, context: int) -> None:
        d = self.transcripts / "-proj" / "session-1" / "subagents"
        d.mkdir(parents=True, exist_ok=True)
        usage = {"input_tokens": 2, "cache_read_input_tokens": context - 1002, "cache_creation_input_tokens": 1000}
        lines = [{"type": "user", "message": {"content": "brief"}},
                 {"type": "assistant", "message": {"id": "m1", "usage": usage, "content": []}}]
        (d / "agent-a5c0ffee.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")

    def test_a_large_context_gets_a_fresh_agent_and_a_full_brief(self) -> None:
        self.transcript(220_000)
        out = self.m.h.tp("dispatch", "T01").out
        self.assertIn('Agent(subagent_type="doc-author"', out)
        self.assertNotIn("SendMessage", out)
        self.assertIn("220k", out)
        brief = (self.m.h.run_dir("T01") / "brief-fix-1.md").read_text()
        self.assertIn("## Task", brief)

    def test_a_small_context_is_resumed(self) -> None:
        self.transcript(40_000)
        self.assertIn('SendMessage(to="a5c0ffee"', self.m.h.tp("dispatch", "T01").out)

    def test_no_transcript_found_resumes_as_before(self) -> None:
        self.assertIn("SendMessage", self.m.h.tp("dispatch", "T01").out)


class PlanShapeWarningsTest(unittest.TestCase):
    def test_a_serial_chain_on_one_file_is_flagged_as_a_merge_candidate(self) -> None:
        m = Mixed()
        try:
            m.h.confirmed(**m.scope(["code"], ["tests", "code", "correctness"]))
            tasks = [m.code_task("T01"), m.code_task("T02", depends_on=["T01"]),
                     m.code_task("T03", depends_on=["T02"])]
            m.h.write_json("plan.json", m.plan(tasks))
            out = m.h.tp("plan", "check").out
            self.assertIn("WARN", out)
            self.assertIn("T01 → T02 → T03", out)
            self.assertIn("calc.py", out)
            self.assertIn("critical path", out)
        finally:
            m.close()


class ResearchModelTest(unittest.TestCase):
    def test_a_research_item_can_run_on_a_named_model(self) -> None:
        h = Harness()
        try:
            h.confirmed(participants=[
                {"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."},
                {"agent": "codebase-researcher", "role": "research", "why": "Maps calc for the plan split."}],
                research={"budget_minutes": 30, "why": "calc's layout is unknown to the manager"})
            q = h.root / "q.txt"
            q.write_text("Which packages does calc have?\n")
            h.tp("research", "add", "R1", "--agent", "codebase-researcher", "--purpose", "map",
                 "--questions-file", str(q), "--done-when", "each package is named", "--model", "sonnet")
            self.assertIn('model="sonnet"', h.tp("dispatch", "R1").out)
        finally:
            h.close()


if __name__ == "__main__":
    unittest.main()
