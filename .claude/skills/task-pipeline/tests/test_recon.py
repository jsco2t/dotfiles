"""Planning research ("recon" internally): small, narrowly scoped items inside a research
budget the human agreed to, each answered as a small structured file. Anything a researcher
thinks needs more investigation comes back as a followup the manager decides on."""
from __future__ import annotations

import json
import unittest

from harness import Harness

PARTICIPANTS = [
    {"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."},
    {"agent": "codebase-researcher", "role": "research", "why": "Maps dash/, which the survey cannot see."},
    {"agent": "atlassian-liaison", "role": "research", "why": "Reads the epic's child issues for D1."},
]
ANSWER = {"answers": [{"q": "Which areas?", "a": "Three: api, ui, store.", "evidence": ["dash/api/"]}],
          "followups": [], "unknowns": []}


class ResearchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.confirmed(participants=PARTICIPANTS, research={"budget_minutes": 45, "why": "The epic is thin."})

    def tearDown(self) -> None:
        self.h.close()

    def add(self, rid: str, questions, expect: int = 0, agent: str = "codebase-researcher",
            purpose: str = "map", *extra: str):
        qf = self.h.root / f"{rid}.q"
        qf.write_text("\n".join(questions))
        return self.h.tp("research", "add", rid, "--agent", agent, "--purpose", purpose, "--questions-file",
                         str(qf), "--done-when", "I can split the work into tasks.", *extra, expect=expect)

    def record(self, rid: str, data=None, expect: int = 0):
        (self.h.wf / "recon" / f"{rid}.json").write_text(json.dumps(data or ANSWER))
        return self.h.tp("record", rid, expect=expect)

    def test_content_grade_asks_are_refused(self) -> None:
        # Regression: planning briefs asked for "EVERY file" and "the complete CLI command
        # tree with every flag" — the KB's content, not planning research.
        text = self.add("R1", ["Account for EVERY file in the paths you own."], expect=2).text
        self.assertIn("EVERY file", text)
        text = self.add("R1", ["Give the complete CLI command tree with every flag."], expect=2).text
        self.assertIn("complete", text)

    def test_investigate_may_trace_one_named_flow_end_to_end(self) -> None:
        q = ["Trace how `stratum up` brings up the kubelet, end to end."]
        self.add("R1", q, 2, "codebase-researcher", "map")
        self.add("R1", q, 0, "codebase-researcher", "investigate")
        self.assertIn("exhaustive", self.add("R2", ["Exhaustively list the call sites."], 2,
                                             "codebase-researcher", "investigate").text.lower())

    def test_purpose_is_required_and_known(self) -> None:
        qf = self.h.root / "q"
        qf.write_text("Which areas?")
        self.h.tp("research", "add", "R1", "--agent", "codebase-researcher", "--questions-file", str(qf),
                  "--done-when", "x", expect=2)
        self.assertIn("purpose", self.add("R1", ["Which areas?"], 2, "codebase-researcher", "audit").text)

    def test_at_most_three_questions(self) -> None:
        self.assertIn("3", self.add("R1", ["Q one?", "Q two?", "Q three?", "Q four?"], expect=2).text)

    def test_research_agent_must_be_confirmed(self) -> None:
        self.assertIn("domain-researcher",
                      self.add("R1", ["Which k8s distros?"], expect=2, agent="domain-researcher").text)

    def test_items_draw_down_the_agreed_budget_and_only_the_human_extends_it(self) -> None:
        for rid in ("R1", "R2", "R3"):
            self.add(rid, [f"Which areas does {rid} cover?"])
        text = self.add("R4", ["Which areas does R4 cover?"], expect=2).text
        self.assertIn("45 of 45", text)
        self.assertIn("research extend", text)
        self.h.tp("research", "extend", "--minutes", "15", "--answer", "Yes, one more item.")
        self.add("R4", ["Which areas does R4 cover?"])
        self.assertIn("one more item", (self.h.wf / "decisions.md").read_text())
        self.assertIn("60 agent-min", self.h.tp("next").out)

    def test_a_time_box_is_at_most_15_minutes(self) -> None:
        self.assertIn("15", self.add("R1", ["Which areas?"], 2, "codebase-researcher", "map", "--minutes", "25").text)
        self.add("R1", ["Which areas?"], 0, "codebase-researcher", "map", "--minutes", "10")

    def test_brief_frames_the_purpose_and_hands_back_followups(self) -> None:
        self.add("R1", ["What do KUB-9's open children require?"], 0, "atlassian-liaison", "requirements",
                 "--minutes", "10")
        out = self.h.tp("dispatch", "R1").out
        self.assertIn("atlassian-liaison", out)
        brief = (self.h.wf / "recon" / "R1.brief.md").read_text()
        self.assertIn("10 min", brief)
        self.assertIn("acceptance criteria", brief)       # requirements framing
        self.assertIn("followups", brief)
        self.assertIn("do not investigate", brief)
        self.assertIn("8000", brief)
        self.assertIn("R1.json", brief)
        self.assertLess(len(brief.encode()), 4000)

    def test_output_is_capped_and_schema_checked(self) -> None:
        self.add("R1", ["Which top-level areas does dash/ split into?"])
        self.h.tp("dispatch", "R1")
        self.assertIn("8000", self.record("R1", {"answers": [{"q": "x", "a": "y" * 9000}]}, expect=2).text)
        self.assertIn("followups", self.record("R1", {"answers": [{"q": "x", "a": "y"}],
                                                      "followups": [{"why": "no question"}]}, expect=2).text)
        self.record("R1")
        self.assertEqual(self.h.state()["recon"]["R1"]["status"], "done")

    def test_followups_are_decided_by_the_manager_before_submit(self) -> None:
        self.add("R1", ["Which areas does dash/ split into?"])
        self.h.tp("dispatch", "R1")
        out = self.record("R1", dict(ANSWER, followups=[
            {"question": "How does dash/store persist sessions?", "why": "Two stores exist.", "agent": "codebase-researcher"},
            {"question": "Is dash/legacy still built?", "why": "No Makefile target names it."}])).out
        self.assertIn("R1.F1", out)
        self.assertIn("R1.F2", out)
        self.h.write_json("plan.json", self.h.plan())
        self.assertIn("R1.F1", self.h.tp("plan", "submit", expect=2).text)
        self.add("R2", ["How does dash/store persist sessions?"], 0, "codebase-researcher", "investigate",
                 "--from", "R1.F1")
        self.h.tp("research", "dismiss", "R1.F2", "--reason", "The plan does not touch dash/legacy.")
        self.assertIn("R2", self.h.tp("plan", "submit", expect=2).text)   # R2 is still pending
        self.h.tp("dispatch", "R2")
        self.record("R2")
        self.h.tp("plan", "submit")
        followups = self.h.state()["recon"]["R1"]["followups"]
        self.assertEqual([f["status"] for f in followups], ["pursued", "dismissed"])

    def test_show_prints_only_the_part_asked_for(self) -> None:
        self.add("R1", ["Which areas?"])
        self.h.tp("dispatch", "R1")
        self.record("R1", dict(ANSWER, followups=[{"question": "What about dash/legacy?", "why": "Unbuilt."}]))
        out = self.h.tp("show", "R1", "--part", "followups").out
        self.assertIn("dash/legacy", out)
        self.assertNotIn("Three: api, ui, store.", out)
        self.assertIn("Three: api, ui, store.", self.h.tp("show", "R1", "--part", "answers").out)

    def test_at_most_three_agents_in_flight(self) -> None:
        for rid in ("R1", "R2", "R3", "R4"):
            self.add(rid, [f"Which areas does {rid} cover?"], 0, "codebase-researcher", "map", "--minutes", "10")
        self.h.tp("dispatch", "R1", "R2", "R3")
        self.assertIn("3 agents", self.h.tp("dispatch", "R4", expect=2).text)

    def test_tasks_cite_research_results_as_sources(self) -> None:
        self.add("R1", ["Which areas?"])
        plan = self.h.plan([self.h.task("T01", "a.md", sources=["src:calc/**", "research:R1"])])
        self.h.write_json("plan.json", plan)
        self.assertIn("R1", self.h.tp("plan", "check", expect=2).text)       # not answered yet
        self.h.tp("dispatch", "R1")
        self.record("R1")
        self.h.tp("plan", "check")
        self.h.tp("plan", "submit")
        self.h.tp("approve", "--answer", "approve")
        self.h.tp("dispatch", "T01")
        brief = (self.h.run_dir("T01") / "brief-author-0.md").read_text()
        self.assertIn(str(self.h.wf / "recon" / "R1.json"), brief)

    def test_unrun_research_must_be_run_or_dropped_before_submit(self) -> None:
        self.add("R1", ["Which areas?"])
        self.h.write_json("plan.json", self.h.plan())
        self.assertIn("R1", self.h.tp("plan", "submit", expect=2).text)
        self.h.tp("research", "drop", "R1", "--reason", "The survey answered it.")
        self.add("R2", ["Which areas does R2 cover?"])      # the dropped item's minutes are released
        self.add("R3", ["Which areas does R3 cover?"])
        self.add("R4", ["Which areas does R4 cover?"])

    def test_research_is_planning_only(self) -> None:
        self.h.write_json("plan.json", self.h.plan())
        self.h.tp("plan", "submit")
        self.h.tp("approve", "--answer", "approve")
        self.add("R2", ["Which areas?"], expect=2)


class NoResearchTest(unittest.TestCase):
    def test_a_straightforward_ask_has_no_research_phase(self) -> None:
        h = Harness()
        try:
            h.confirmed()
            qf = h.root / "q"
            qf.write_text("Which areas?")
            res = h.tp("research", "add", "R1", "--agent", "codebase-researcher", "--purpose", "map",
                       "--questions-file", str(qf), "--done-when", "x", expect=2)
            self.assertIn("no research budget", res.text)
        finally:
            h.close()


if __name__ == "__main__":
    unittest.main()
