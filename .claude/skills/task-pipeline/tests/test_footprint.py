"""The pipeline's own footprint stays small, and every agent definition is standalone:
brief-driven, free of the retired task-orchestrator machinery, and unable to start
sub-agents of its own (the pipeline's three-agent cap is mechanical)."""
from __future__ import annotations

import json
import re
import unittest

from harness import SKILL

CLAUDE = SKILL.parents[1]
AGENTS = CLAUDE / "agents"
CATALOG = json.loads((SKILL / "references" / "catalog.json").read_text())
# Agents whose skills fan out (code-sleuth and tutorial-builder do not, so their agents stay without it).
FANOUT_AGENTS = {"architecture-reviewer", "code-reviewer", "doc-reviewer", "kb-author", "test-reviewer", "ux-reviewer"}
FANOUT_SKILLS = ["comp-reviewomatic", "comp-goreviewomatic", "doc-reviewomatic", "test-reviewer", "doc-reviewer",
                 "eng-ux-reviewer", "arch-reviewer", "arch-plan-reviewer", "kb-updater", "knowledge-discovery"]


def frontmatter(path):
    return path.read_text().split("---")[1]


class FootprintTest(unittest.TestCase):
    def test_skill_md_is_small(self) -> None:
        # Anything that can be printed on demand (`tp next`, `tp schema`) stays out of SKILL.md.
        self.assertLess(len((SKILL / "SKILL.md").read_bytes()), 10_000)

    def test_core_style_is_small(self) -> None:
        self.assertLess(len((CLAUDE / "output-styles" / "answer-first-core.md").read_bytes()), 1_500)

    def test_every_catalog_agent_has_a_definition(self) -> None:
        for name in CATALOG["agents"]:
            self.assertTrue((AGENTS / f"{name}.md").exists(), name)


class AgentDefinitionTest(unittest.TestCase):
    def test_frontmatter_is_complete(self) -> None:
        # Broken frontmatter makes an agent silently disappear from the Agent tool.
        for path in sorted(AGENTS.glob("*.md")):
            front = frontmatter(path)
            with self.subTest(agent=path.stem):
                for key in ("name", "description", "tools", "model"):
                    self.assertRegex(front, re.compile(rf"^{key}:", re.M))
                self.assertIn(f"name: {path.stem}\n", front)

    def test_no_agent_depends_on_the_retired_orchestrator(self) -> None:
        # A hook pointing at a deleted script exits 2, which blocks every tool call.
        for path in sorted(AGENTS.glob("*.md")):
            text = path.read_text()
            with self.subTest(agent=path.stem):
                for gone in ("task-orchestrator", "hook.py", "orch-result", "orch brief", "scope_proposals",
                             "project-manager", "plan_hash"):
                    self.assertNotIn(gone, text)
                self.assertNotRegex(frontmatter(path), re.compile(r"^hooks:", re.M))

    def test_only_agents_whose_skills_fan_out_can_start_sub_agents(self) -> None:
        # Standalone, these agents run skills that fan out (/reviewomatic, /doc-reviewer, ...),
        # so they keep the Agent tool and pass a sub-agent budget on; a /task-pipeline brief
        # sets it to 0. Every other agent cannot start sub-agents at all.
        for path in sorted(AGENTS.glob("*.md")):
            tools = re.search(r"^tools:(.*)$", frontmatter(path), re.M)
            with self.subTest(agent=path.stem):
                self.assertIsNotNone(tools)
                names = [t.strip() for t in tools.group(1).split(",")] if tools else []
                self.assertNotIn("*", names)
                if path.stem in FANOUT_AGENTS:
                    self.assertIn("Agent", names)
                    self.assertIn("--max-agents", path.read_text())
                else:
                    self.assertNotIn("Agent", names)

    def test_every_fan_out_skill_takes_a_sub_agent_budget(self) -> None:
        for name in FANOUT_SKILLS:
            text = (CLAUDE / "skills" / name / "SKILL.md").read_text()
            with self.subTest(skill=name):
                hint = re.search(r"^argument-hint:(.*)$", text, re.M)
                self.assertIsNotNone(hint)
                self.assertIn("--max-agents=N", hint.group(1) if hint else "")
                self.assertIn("**Sub-agent budget (`--max-agents=N`", text)
                self.assertIn("`--max-agents=0`", text)
        router = (CLAUDE / "skills" / "reviewomatic" / "SKILL.md").read_text()
        self.assertIn("--max-agents=N", router)

    def test_every_agent_takes_its_contract_and_style_from_the_brief(self) -> None:
        for path in sorted(AGENTS.glob("*.md")):
            text = path.read_text()
            with self.subTest(agent=path.stem):
                self.assertIn("the contract your brief names", text)
                self.assertIn("the brief wins", text)
                self.assertIn("the style your brief names", text)


if __name__ == "__main__":
    unittest.main()
