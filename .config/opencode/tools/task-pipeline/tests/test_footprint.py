"""The pipeline's OpenCode footprint stays small, and every agent definition is standalone:
brief-driven, free of the retired task-orchestrator machinery, and (except the fan-out
reviewers) unable to start sub-agents of its own — the pipeline's three-agent cap is mechanical."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from harness import SKILL

OPENCODE = SKILL.parents[1]                 # ~/.config/opencode
AGENTS = OPENCODE / "agent"                 # the deployed OpenCode agent definitions
COMMAND = OPENCODE / "command" / "oc-task-pipeline.md"
STYLES = OPENCODE / "output-styles"
CATALOG = json.loads((SKILL / "references" / "catalog.json").read_text())
# Agents whose skills fan out (code-sleuth and tutorial-builder do not, so their agents stay without it).
FANOUT_AGENTS = {"architecture-reviewer", "code-reviewer", "doc-reviewer", "kb-author", "test-reviewer", "ux-reviewer"}


def frontmatter(path: Path) -> str:
    return path.read_text().split("---")[1]


def permission(front: str, name: str):
    block = re.search(r"^permission:\n((?:  .*\n)+)", front, re.M)
    if not block:
        return None
    hit = re.search(rf"^\s+{name}:\s*(\S+)\s*$", block.group(1), re.M)
    return hit.group(1) if hit else None


class FootprintTest(unittest.TestCase):
    def test_the_command_file_is_small(self) -> None:
        # Anything `tp.py` prints on demand (`tp next`, `tp schema`) stays out of the command.
        self.assertLess(len(COMMAND.read_bytes()), 12_000)

    def test_core_style_is_small(self) -> None:
        self.assertLess(len((STYLES / "answer-first-core.md").read_bytes()), 1_500)

    def test_the_full_style_is_deployed(self) -> None:
        # Agent definitions point standalone agents at it.
        self.assertTrue((STYLES / "answer-first.md").exists())

    def test_every_catalog_agent_has_a_definition(self) -> None:
        for name in CATALOG["agents"]:
            self.assertTrue((AGENTS / f"{name}.md").exists(), name)


class AgentDefinitionTest(unittest.TestCase):
    def test_frontmatter_is_complete(self) -> None:
        # Broken frontmatter makes an agent silently disappear from the task tool.
        for path in sorted(AGENTS.glob("*.md")):
            front = frontmatter(path)
            with self.subTest(agent=path.stem):
                self.assertRegex(front, re.compile(r"^description:", re.M))
                self.assertRegex(front, re.compile(r"^mode:\s*subagent\s*$", re.M))

    def test_no_agent_depends_on_the_retired_orchestrator(self) -> None:
        for path in sorted(AGENTS.glob("*.md")):
            text = path.read_text()
            with self.subTest(agent=path.stem):
                for gone in ("task-orchestrator", "hook.py", "orch-result", "orch brief", "scope_proposals",
                             "project-manager", "plan_hash"):
                    self.assertNotIn(gone, text)

    def test_only_agents_whose_skills_fan_out_may_start_sub_agents(self) -> None:
        # Standalone, these agents run skills that fan out (/reviewomatic, /doc-reviewer, ...),
        # so they keep the `task` tool and pass a sub-agent budget on; a /task-pipeline brief
        # sets it to 0. Every other agent denies the task tool outright.
        for path in sorted(AGENTS.glob("*.md")):
            front = frontmatter(path)
            with self.subTest(agent=path.stem):
                if path.stem in FANOUT_AGENTS:
                    self.assertNotEqual(permission(front, "task"), "deny", path.stem)
                    self.assertIn("--max-agents", path.read_text())
                else:
                    self.assertEqual(permission(front, "task"), "deny", path.stem)

    def test_every_agent_takes_its_contract_and_style_from_the_brief(self) -> None:
        for path in sorted(AGENTS.glob("*.md")):
            text = path.read_text()
            with self.subTest(agent=path.stem):
                self.assertIn("the contract your brief names", text)
                self.assertIn("the brief wins", text)
                self.assertIn("the style your brief names", text)

    def test_every_agent_reads_the_deployed_style(self) -> None:
        # The style path must be this deployment's, not Claude Code's. (A cross-skill path such
        # as the tutorial-builder validator is a real dependency and may stay.)
        for path in sorted(AGENTS.glob("*.md")):
            text = path.read_text()
            with self.subTest(agent=path.stem):
                self.assertNotIn(".claude/output-styles", text)

    def test_no_agent_depends_on_claude_code_owned_files(self) -> None:
        # Every tool an OpenCode agent names must live in this deployment. The tutorial-builder
        # validator, for example, has its own OpenCode copy under tools/.
        for path in sorted(AGENTS.glob("*.md")):
            text = path.read_text()
            with self.subTest(agent=path.stem):
                self.assertNotIn("~/.claude", text)
                self.assertNotIn(".claude/", text)


class TutorialValidatorTest(unittest.TestCase):
    """The deployed validator copy works: a conforming tutorial passes, a hollow one fails."""

    def setUp(self) -> None:
        self.validator = OPENCODE / "tools" / "tutorial-builder" / "validate_tutorial.py"
        self.dir = Path(__import__("tempfile").mkdtemp(prefix="tp-tutorial-"))

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, name: str, text: str) -> None:
        (self.dir / name).write_text(text)

    def run_validator(self, expect: int) -> str:
        import subprocess
        res = subprocess.run(["python3", str(self.validator), str(self.dir)], capture_output=True, text=True)
        self.assertEqual(res.returncode, expect, res.stdout + res.stderr)
        return res.stdout

    GOOD = ('---\ntitle: Basics\nid: basics\ncreatedate: 2026-09-30\ntags:\n  - tutorial\n---\n\n# Basics\n\n'
            '## What You Need\n\nPython 3.8 or newer.\n\n' + ("Prose explaining the concept, carefully. " * 80) +
            '\n## Try it\n\n```bash\necho hello\n```\n\nExpected output: hello\n')

    def test_a_conforming_tutorial_passes(self) -> None:
        self.write("good.md", self.GOOD)
        out = self.run_validator(0)
        self.assertIn('"passed": 1', out)

    def test_a_hollow_tutorial_fails_with_its_reasons(self) -> None:
        self.write("bad.md", "# Bad\n\nToo short to teach anything.\n")
        out = self.run_validator(1)
        self.assertIn("interactive sections", out)
        self.assertIn("frontmatter", out)


if __name__ == "__main__":
    unittest.main()
