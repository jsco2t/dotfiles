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
BUDGET_FLAG = "--max-agents=N"
BUDGET_SECTION = "**Sub-agent budget (`--max-agents=N`"
# A /skill reference in prose: a slash that does not continue a path, then a skill-like name.
SLASH_REF = re.compile(r"(?<![\w/.~-])/([a-z][a-z0-9-]*[a-z0-9])\b")
SKILL_LINE = re.compile(r"\bSkill:\s*([a-z][a-z0-9-]*[a-z0-9])\b")


def frontmatter(path):
    return path.read_text().split("---")[1]


def field(front: str, key: str) -> str:
    m = re.search(rf"^{key}:(.*)$", front, re.M)
    return m.group(1).strip().strip("\"'") if m else ""


class Skill:
    def __init__(self, path):
        self.dir = path.parent.name
        self.text = path.read_text()
        front = self.text.split("---")[1] if self.text.startswith("---") else ""
        self.name = field(front, "name") or self.dir
        self.hint = field(front, "argument-hint")
        self.body = self.text.split("---", 2)[2] if self.text.startswith("---") else self.text

    def declares_budget(self) -> bool:
        return BUDGET_FLAG in self.hint

    def mentions(self, other: "Skill") -> bool:
        return any(re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", self.body) for n in {other.name, other.dir})


def skills():
    """Every installed skill, keyed by its directory name: the name Claude Code lists and
    resolves it by. test_every_skill_is_named_after_its_directory keeps the frontmatter name
    equal to it, so a reference by either name finds the skill."""
    found = [Skill(p) for p in sorted((CLAUDE / "skills").glob("*/SKILL.md"))]
    return found, {s.dir: s for s in found}


def applied_skills(text: str, index):
    """The skills an agent definition applies: `Skill: x` lines and `/x` references to skills."""
    names = set(SKILL_LINE.findall(text)) | set(SLASH_REF.findall(text))
    return {index[n].dir: index[n] for n in names if n in index}.values()


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
        # An agent that applies a skill which takes a sub-agent budget (/reviewomatic,
        # /doc-reviewer, ...) keeps the Agent tool and passes the budget on; a /task-pipeline
        # brief sets it to 0. Every other agent cannot start sub-agents at all. Which agents
        # fan out is read from the definitions and the skills they apply, never listed here.
        _, index = skills()
        fanning = 0
        for path in sorted(AGENTS.glob("*.md")):
            tools = re.search(r"^tools:(.*)$", frontmatter(path), re.M)
            text = path.read_text()
            fans_out = [s.name for s in applied_skills(text, index) if s.declares_budget()]
            with self.subTest(agent=path.stem, fan_out_skills=fans_out):
                self.assertIsNotNone(tools)
                names = [t.strip() for t in tools.group(1).split(",")] if tools else []
                self.assertNotIn("*", names)
                if fans_out:
                    fanning += 1
                    self.assertIn("Agent", names)
                    self.assertIn("--max-agents", text)
                else:
                    self.assertNotIn("Agent", names)
        self.assertGreater(fanning, 0, "no agent applies a skill that takes a sub-agent budget; is discovery broken?")

    def test_every_skill_is_named_after_its_directory(self) -> None:
        # Claude Code lists and resolves a skill by its directory name. A frontmatter name that
        # differs from it is what other skills and agents then call it by, and that call fails.
        found, _ = skills()
        for s in found:
            with self.subTest(skill=s.dir):
                self.assertEqual(s.name, s.dir)

    def test_every_skill_an_agent_invokes_is_installed(self) -> None:
        _, index = skills()
        for path in sorted(AGENTS.glob("*.md")):
            for name in SKILL_LINE.findall(path.read_text()):
                with self.subTest(agent=path.stem, skill=name):
                    self.assertIn(name, index)

    def test_every_skill_that_takes_a_sub_agent_budget_documents_it(self) -> None:
        # A skill declares the budget in its argument-hint and says what `--max-agents=0` means.
        # It either caps its own sub-agents (the budget section) or, like a router, forwards
        # the flag to skills it names that take the budget themselves.
        found, _ = skills()
        budgeted = [s for s in found if s.declares_budget()]
        self.assertTrue(budgeted, "no installed skill declares a sub-agent budget; is discovery broken?")
        for s in budgeted:
            with self.subTest(skill=s.name):
                self.assertIn("`--max-agents=0`", s.body)
                if BUDGET_SECTION not in s.body:
                    downstream = [t.name for t in budgeted if t is not s and s.mentions(t)]
                    self.assertTrue(downstream, f"{s.name} has no budget section and forwards to no budgeted skill")
                    self.assertIn(BUDGET_FLAG, s.body)
        for s in found:
            if BUDGET_SECTION in s.body:
                with self.subTest(skill=s.name):
                    self.assertTrue(s.declares_budget(), f"{s.name} has a budget section but no {BUDGET_FLAG} hint")

    def test_every_agent_takes_its_contract_and_style_from_the_brief(self) -> None:
        for path in sorted(AGENTS.glob("*.md")):
            text = path.read_text()
            with self.subTest(agent=path.stem):
                self.assertIn("the contract your brief names", text)
                self.assertIn("the brief wins", text)
                self.assertIn("the style your brief names", text)


if __name__ == "__main__":
    unittest.main()
