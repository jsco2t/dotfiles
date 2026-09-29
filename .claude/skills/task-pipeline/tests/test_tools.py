"""The deterministic tools that replace planning research and much of document review:
the repository survey and the docs checker."""
from __future__ import annotations

import json
import unittest

from harness import Harness, git


class SurveyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = h = Harness()
        src = h.src
        (src / "cmd" / "calc").mkdir(parents=True)
        (src / "cmd" / "calc" / "main.go").write_text("package main\n\nfunc main() {}\n")
        (src / "calc" / "calc_test.go").write_text("package calc\n\nimport \"testing\"\n\nfunc TestAdd(t *testing.T) {}\n")
        (src / "docs").mkdir()
        (src / "docs" / "design.md").write_text("# Design\n")
        (src / "Makefile").write_text("build:\n\tgo build ./...\n\ntest: build\n\tgo test ./...\n")
        (src / "go.mod").write_text("module example.com/calc\n\ngo 1.22\n")
        (src / "calc" / "aa_helpers.go").write_text("// aa_helpers.go — small helpers.\npackage calc\n")
        (src / "empty.mk").write_text("# no targets\n")
        git(src, "add", "-A")
        git(src, "commit", "-q", "-m", "more")
        h.init()

    def tearDown(self) -> None:
        self.h.close()

    def test_survey_maps_structure_without_an_agent(self) -> None:
        out = self.h.tp("survey", str(self.h.src), "--name", "src").out
        self.assertLess(len(out.splitlines()), 80)
        data = json.loads((self.h.wf / "survey" / "src.json").read_text())
        self.assertEqual(data["git"]["branch"], "main")
        self.assertEqual(len(data["git"]["commit"]), 40)
        pkgs = {p["dir"]: p for p in data["go_packages"]}
        self.assertEqual(pkgs["calc"]["doc"], "Package calc does arithmetic.")
        self.assertEqual(pkgs["cmd/calc"]["name"], "main")
        self.assertIn("cmd/calc", data["entry_points"])
        self.assertEqual(set(data["build_targets"]["Makefile"]), {"build", "test"})
        self.assertNotIn("empty.mk", data["build_targets"])
        self.assertIn("docs/design.md", data["docs"])
        self.assertEqual(data["tests"]["files"], 1)
        dirs = {d["path"]: d for d in data["dirs"]}
        self.assertGreater(dirs["calc"]["lines"], 0)
        self.assertIn("calc", out)

    def test_survey_works_outside_git(self) -> None:
        self.h.tp("survey", str(self.h.kb), "--name", "kb")
        data = json.loads((self.h.wf / "survey" / "kb.json").read_text())
        self.assertIsNone(data["git"])


class DocsCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()

    def tearDown(self) -> None:
        self.h.close()

    def run_check(self, text: str, *extra: str, expect: int = 0):
        p = self.h.kb / "a.md"
        p.write_text(text)
        return self.h.tp("check-docs", str(p), "--repo", f"src={self.h.src}", *extra, expect=expect, wf=False)

    def test_supported_citation_passes(self) -> None:
        self.run_check("`Add` sums two ints (`calc/calc.go:5`). See [web](https://example.com).\n")

    def test_broken_relative_link(self) -> None:
        self.assertIn("nope.md", self.run_check("See [x](nope.md#part).\n", expect=2).text)

    def test_anchor_only_and_existing_links_pass(self) -> None:
        (self.h.kb / "b.md").write_text("# B\n")
        self.run_check("See [b](b.md#top) and [here](#intro).\n")

    def test_citation_to_a_missing_file(self) -> None:
        self.assertIn("calc/nope.go", self.run_check("`Add` is in `calc/nope.go:5`.\n", expect=2).text)

    def test_citation_past_the_end_of_the_file(self) -> None:
        self.assertIn("calc/calc.go:500", self.run_check("`Add` is at `calc/calc.go:500`.\n", expect=2).text)

    def test_citation_that_does_not_support_its_claim_is_a_warning(self) -> None:
        # The sentence names `Multiply`; nothing near calc.go:5 does. A heuristic, so it is a
        # warning for the manager's fact check — an error only with --strict.
        res = self.run_check("`Multiply` multiplies two ints (`calc/calc.go:5`).\n")
        self.assertIn("may not support", res.text)
        self.assertIn("multiply", res.text.lower())
        self.run_check("`Multiply` multiplies two ints (`calc/calc.go:5`).\n", "--strict", expect=2)

    def test_line_ranges_and_qualified_names(self) -> None:
        res = self.run_check("`calc.Add` is defined at `calc/calc.go:4-6`; see `example.com/calc.Add` "
                             "and `:5`. `Add` also appears at `calc/calc.go:2,4-6`.\n", "--strict")
        self.assertNotIn("WARN", res.text)
        self.assertIn("4 citations", res.text)  # 4-6, :5, and the list 2,4-6 (two)
        self.assertIn("calc/calc.go:99", self.run_check("`Add` is at `calc/calc.go:5,99`.\n", expect=2).text)

    def test_a_sentence_with_several_citations_is_judged_as_a_whole(self) -> None:
        # Seen live: the name sits at one citation; the other citation backs the rest of the claim.
        lines = ["package calc", "", "func Add(a, b int) int {", "\treturn a + b", "}"]
        lines += ["// filler"] * 14 + ["func Other() {"] + ["\t_ = 0"] * 40 + ["}"]
        (self.h.src / "calc" / "big.go").write_text("\n".join(lines) + "\n")
        self.run_check("`Add` is defined early and `Other` runs long (`calc/big.go:3`, `calc/big.go:55`).\n",
                       "--strict")
        self.run_check("`Add` sits at the top and the file runs long (`calc/big.go:3`, `calc/big.go:55`).\n",
                       "--strict")
        res = self.run_check("`Multiply` is here (`calc/big.go:3`, `calc/big.go:55`).\n")
        self.assertIn("may not support", res.text)

    def test_a_citation_inside_the_named_function_supports_it(self) -> None:
        body = "".join(f"\tx{i} := {i}\n" for i in range(20))
        (self.h.src / "calc" / "long.go").write_text(f"package calc\n\nfunc Long() int {{\n{body}\treturn 0\n}}\n")
        self.run_check("`Long` returns zero (`calc/long.go:22`).\n", "--strict")

    def test_bare_file_names_resolve_only_when_unique(self) -> None:
        self.run_check("`Add` is in `calc.go:5`.\n", "--strict")
        (self.h.src / "other").mkdir()
        (self.h.src / "other" / "calc.go").write_text("package other\n")
        res =self.run_check("`Add` is in `calc.go:5`.\n", expect=2)
        self.assertIn("2 files", res.text)

    def test_unreachable_article(self) -> None:
        (self.h.kb / "index.md").write_text("# KB\n\n- [A](a.md)\n")
        (self.h.kb / "a.md").write_text("# A\n")
        (self.h.kb / "orphan.md").write_text("# Orphan\n")
        res = self.h.tp("check-docs", str(self.h.kb), "--root", str(self.h.kb / "index.md"),
                        expect=2, wf=False)
        self.assertIn("orphan.md", res.text)
        self.assertNotIn("a.md is not reachable", res.text)

    def test_code_blocks_are_ignored(self) -> None:
        self.run_check("```\n[x](nope.md) `calc/nope.go:1`\n```\n")


if __name__ == "__main__":
    unittest.main()
