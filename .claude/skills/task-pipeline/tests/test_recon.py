"""Planning recon: at most a few narrow questions, answered as a small map — never the
deliverable's content."""
from __future__ import annotations

import json
import unittest

from harness import Harness

RECON = {"agent": "codebase-researcher", "role": "recon",
         "why": "Maps the dashboard's structure, which the survey cannot see."}


class ReconTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.confirmed(participants=[
            {"agent": "kb-author", "role": "author", "why": "Writes every KB article for D1."}, RECON])

    def tearDown(self) -> None:
        self.h.close()

    def add(self, rid: str, questions, expect: int = 0, agent: str = "codebase-researcher"):
        qf = self.h.root / f"{rid}.q"
        qf.write_text("\n".join(questions))
        return self.h.tp("recon", "add", rid, "--agent", agent, "--questions-file", str(qf),
                         "--done-when", "I can split the KB into article tasks.", expect=expect)

    def test_content_grade_asks_are_refused(self) -> None:
        # Regression: planning briefs asked for "EVERY file" and "the complete CLI command
        # tree with every flag" — the KB's content, not a planning map.
        text = self.add("R1", ["Account for EVERY file in the paths you own."], expect=2).text
        self.assertIn("EVERY file", text)
        text = self.add("R1", ["Give the complete CLI command tree with every flag."], expect=2).text
        self.assertIn("complete", text)

    def test_at_most_three_questions(self) -> None:
        self.assertIn("3", self.add("R1", ["Q one?", "Q two?", "Q three?", "Q four?"], expect=2).text)

    def test_recon_agent_must_be_confirmed_for_recon(self) -> None:
        self.assertIn("domain-researcher",
                      self.add("R1", ["Which k8s distros?"], agent="domain-researcher", expect=2).text)

    def test_recon_brief_carries_the_time_box_and_output_cap(self) -> None:
        self.add("R1", ["Which top-level areas does dash/ split into?"])
        out = self.h.tp("dispatch", "R1").out
        self.assertIn("codebase-researcher", out)
        brief = (self.h.wf / "recon" / "R1.brief.md").read_text()
        self.assertIn("15 min", brief)
        self.assertIn("8000", brief)
        self.assertIn("R1.json", brief)
        self.assertLess(len(brief.encode()), 4000)

    def test_recon_output_is_capped_and_schema_checked(self) -> None:
        self.add("R1", ["Which top-level areas does dash/ split into?"])
        self.h.tp("dispatch", "R1")
        out = self.h.wf / "recon" / "R1.json"
        out.write_text(json.dumps({"answers": [{"q": "x", "a": "y" * 9000, "evidence": []}]}))
        self.assertIn("8000", self.h.tp("record", "R1", expect=2).text)
        out.write_text(json.dumps({"answers": [{"q": "Which areas?", "a": "Three: api, ui, store.",
                                                "evidence": ["dash/api/"]}],
                                   "areas": [], "unknowns": []}))
        self.h.tp("record", "R1")
        self.assertEqual(self.h.state()["recon"]["R1"]["status"], "done")

    def test_at_most_two_agents_in_flight(self) -> None:
        for rid in ("R1", "R2", "R3"):
            self.add(rid, [f"Which areas does {rid} cover?"])
        self.h.tp("dispatch", "R1")
        self.h.tp("dispatch", "R2")
        self.assertIn("2 agents", self.h.tp("dispatch", "R3", expect=2).text)

    def test_recon_is_planning_only(self) -> None:
        self.add("R1", ["Which areas?"])
        self.h.write_json("plan.json", self.h.plan())
        self.h.tp("plan", "submit")
        self.h.tp("approve", "--answer", "approve")
        self.add("R2", ["Which areas?"], expect=2)


if __name__ == "__main__":
    unittest.main()
