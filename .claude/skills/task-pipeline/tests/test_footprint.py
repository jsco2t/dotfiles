"""The pipeline's own footprint stays small, and the shared agent definitions defer to
the dispatching brief's contract without losing what task-orchestrator relies on."""
from __future__ import annotations

import json
import re
import unittest

from harness import SKILL

CLAUDE = SKILL.parents[1]
AGENTS = CLAUDE / "agents"
CATALOG = json.loads((SKILL / "references" / "catalog.json").read_text())


class FootprintTest(unittest.TestCase):
    def test_skill_md_is_small(self) -> None:
        # The orchestrator's SKILL.md was 32 KB and loaded on every invocation.
        self.assertLess(len((SKILL / "SKILL.md").read_bytes()), 10_000)

    def test_core_style_is_small(self) -> None:
        self.assertLess(len((CLAUDE / "output-styles" / "answer-first-core.md").read_bytes()), 1_500)

    def test_every_catalog_agent_has_a_definition(self) -> None:
        for name in CATALOG["agents"]:
            self.assertTrue((AGENTS / f"{name}.md").exists(), name)


class AgentDefinitionTest(unittest.TestCase):
    def test_contract_comes_from_the_brief(self) -> None:
        for path in sorted(AGENTS.glob("*.md")):
            text = path.read_text()
            with self.subTest(agent=path.stem):
                self.assertIn("the contract your brief names", text)
                self.assertIn("task-orchestrator/references/agent-contract.md", text)
                self.assertIn("the brief wins", text)

    def test_output_style_comes_from_the_brief(self) -> None:
        for path in sorted(AGENTS.glob("*.md")):
            with self.subTest(agent=path.stem):
                self.assertIn("the style your brief names", path.read_text())

    def test_frontmatter_keeps_the_orchestrator_budget_hook(self) -> None:
        for path in sorted(AGENTS.glob("*.md")):
            front = path.read_text().split("---")[1]
            with self.subTest(agent=path.stem):
                self.assertRegex(front, re.compile(r"hook\.py\" budget"))


if __name__ == "__main__":
    unittest.main()
