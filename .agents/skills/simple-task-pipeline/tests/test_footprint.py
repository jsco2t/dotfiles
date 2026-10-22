"""The copied pipeline works as a standalone skill without an OpenCode deployment."""
from __future__ import annotations

import unittest
from pathlib import Path

from harness import Harness


class StandaloneSkillTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def test_main_session_workflow_uses_bundled_resources_without_agent_ids(self) -> None:
        h = self.h
        participants = [
            {"agent": "kb-author", "role": "author", "why": "Writes the D1 article in the main session."},
            {"agent": "doc-reviewer", "role": "reviewer", "why": "Reviews D1 in the main session."},
        ]
        plan = h.plan([h.task("T01", "index.md")])
        h.approved(plan=plan, participants=participants, review="final")
        dispatch = h.tp("dispatch", "T01")
        brief_path = next(line.removeprefix("brief: ") for line in dispatch.out.splitlines()
                          if line.startswith("brief: "))
        brief = Path(brief_path).read_text()
        # Dispatch must load the bundled style even when no OpenCode directories exist.
        self.assertIn("Point first.", brief)
        h.good_article("index.md")
        h.result("T01", "author", changed=["index.md"])
        h.tp("record", "T01")
        h.tp("accept", "T01", "--note", "Verified the source citation in the main session.")
        h.tp("halt", "--reason", "Pause before final self-review.")
        self.assertTrue((h.wf / "halt.json").is_file())
        h.tp("status")
        h.tp("resume", "--answer", "Continue final self-review.")
        sid = "B1/doc-reviewer"
        h.tp("dispatch", sid)
        h.write_json("runs/B1/doc-reviewer-1.json", {"batch": "B1", "verdict": "pass", "findings": []})
        h.tp("record", sid)
        h.tp("final")
        state = h.state()
        self.assertEqual(state["phase"], "DONE")
        self.assertEqual(state["in_flight"], {})
        self.assertEqual(state["tasks"]["T01"]["agents"], {})
        self.assertIsNone(state["reviews"][sid]["agent_id"])
        self.assertTrue((h.wf / "report.md").is_file())


if __name__ == "__main__":
    unittest.main()
