"""The deterministic tools that replace planning research and much of document review:
the repository survey and the docs checker."""
from __future__ import annotations

import json
import os
import sys
import unittest

from harness import SKILL, Harness, git


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


FAKE_JIRA = r'''
import json, sys
a = sys.argv[1:]
thin = {"KUB-11": "Fix it.", "KUB-12": "x" * 900, "KUB-13": ""}
if a[:2] == ["issue", "get"]:
    key = a[2]
    if key == "KUB-9":
        print(json.dumps({"key": "KUB-9", "type": "Epic", "summary": "Papercuts", "status": "In Progress",
                          "statusCategory": "In Progress", "labels": ["v1"], "description": "d" * 1200,
                          "comments": [{"author": "a", "created": "2026-09-01", "text": "see page"}]}))
    else:
        print(json.dumps({"key": key, "type": "Bug", "summary": key, "status": "To Do", "statusCategory": "To Do",
                          "description": thin[key], "labels": []}))
elif a[:1] == ["search"]:
    if "parent = KUB-9" not in a[1]:
        print(json.dumps({"schema": 1, "issues": []}))
    else:
        issues = [{"key": k, "type": "Bug", "summary": k, "status": s, "statusCategory": s, "comments": c}
                  for k, s, c in (("KUB-11", "To Do", []), ("KUB-12", "To Do", [{"text": "hi"}]),
                                  ("KUB-13", "In Progress", []), ("KUB-14", "Done", []))]
        print(json.dumps({"schema": 1, "issues": issues}))
elif a[:2] == ["issue", "links"]:
    print(json.dumps([{"title": "Design", "url": "https://x.atlassian.net/wiki/spaces/E/pages/123/Design"}]))
else:
    sys.exit(f"unexpected: {a}")
'''

FAKE_GHTK = r'''
import json, sys
a = sys.argv[1:]
assert a[:3] == ["issue", "get", "12"], a
print(json.dumps({"number": 12, "title": "Add retries", "state": "open", "author": "x", "labels": ["bug"],
                  "isPullRequest": False, "body": "Needs #34 and KUB-9. See https://github.com/o/r/pull/56",
                  "comments": [{"author": "y", "body": "+1"}]}))
'''


class IssueSurveyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.init()
        for name, body in (("jira", FAKE_JIRA), ("ghtk", FAKE_GHTK)):
            (self.h.root / f"fake_{name}.py").write_text(body)
        os.environ["TP_JIRA"] = f"{sys.executable} {self.h.root / 'fake_jira.py'}"
        os.environ["TP_GHTK"] = f"{sys.executable} {self.h.root / 'fake_ghtk.py'}"

    def tearDown(self) -> None:
        os.environ.pop("TP_JIRA", None)
        os.environ.pop("TP_GHTK", None)
        self.h.close()

    def test_a_jira_epic_is_sized_without_an_agent(self) -> None:
        out = self.h.tp("survey-issue", "jira:KUB-9").out
        self.assertLess(len(out.splitlines()), 30)
        data = json.loads((self.h.wf / "survey" / "issue-KUB-9.json").read_text())
        self.assertEqual(data["key"], "KUB-9")
        self.assertEqual(len(data["children"]), 4)
        self.assertEqual(data["counts"]["open"], 3)
        self.assertEqual(sorted(data["thin"]), ["KUB-11", "KUB-13"])    # too little written to research
        self.assertEqual(data["links"][0]["title"], "Design")
        self.assertIn("thin", out)
        self.assertIn("KUB-11", out)
        self.assertIn("starting point", out)

    def test_a_github_issue_lists_what_it_references(self) -> None:
        self.h.tp("survey-issue", "gh:o/r#12")
        data = json.loads((self.h.wf / "survey" / "issue-o-r-12.json").read_text())
        self.assertEqual(data["title"], "Add retries")
        self.assertEqual(sorted(data["references"]), ["#34", "KUB-9", "https://github.com/o/r/pull/56"])

    def test_an_unknown_source_is_refused(self) -> None:
        self.assertIn("jira:", self.h.tp("survey-issue", "linear:ABC-1", expect=2).text)


def _tool_use(name, **inp):
    return {"type": "tool_use", "id": "t", "name": name, "input": inp}


class FanoutCheckTest(unittest.TestCase):
    """fanout_check.py reads an agent or session transcript and says how many sub-agents it
    started, whether the loaded skill text carried the budget paragraph, and whether a budget held."""

    def setUp(self) -> None:
        self.h = Harness()
        self.script = SKILL / "scripts" / "fanout_check.py"

    def tearDown(self) -> None:
        self.h.close()

    def transcript(self, messages, extra_lines=()):
        p = self.h.root / "t.jsonl"
        lines = [json.dumps({"message": {"role": "assistant", "content": m}}) for m in messages]
        p.write_text("\n".join(list(extra_lines) + lines) + "\n")
        return p

    def run_check(self, path, *args, expect=0):
        import subprocess
        res = subprocess.run([sys.executable, str(self.script), str(path), *args], capture_output=True, text=True)
        self.assertEqual(res.returncode, expect, res.stdout + res.stderr)
        return res.stdout

    def test_counts_agent_calls_and_the_largest_parallel_batch(self) -> None:
        p = self.transcript([[_tool_use("Skill", skill="doc-reviewer", args="x --max-agents=2")],
                             [_tool_use("Agent", subagent_type="general-purpose"), _tool_use("Agent", subagent_type="Explore")],
                             [_tool_use("Bash", command="ls")]],
                            extra_lines=['{"note": "**Sub-agent budget (`--max-agents=N`, default 6)."}'])
        out = self.run_check(p, "--max", "2")
        self.assertIn("Agent calls: 2", out)
        self.assertIn("largest parallel batch: 2", out)
        self.assertIn("doc-reviewer", out)
        self.assertIn("budget paragraph loaded: yes", out)
        self.assertIn("within budget", out)

    def test_a_budget_breach_fails(self) -> None:
        p = self.transcript([[_tool_use("Agent"), _tool_use("Agent"), _tool_use("Agent")]])
        self.assertIn("OVER BUDGET", self.run_check(p, "--max", "2", expect=1))

    def test_since_counts_only_after_a_marker(self) -> None:
        p = self.h.root / "s.jsonl"
        early = json.dumps({"message": {"role": "assistant", "content": [_tool_use("Agent")]}})
        marker = json.dumps({"message": {"role": "user", "content": "<command-name>/reviewomatic</command-name>"}})
        late = json.dumps({"message": {"role": "assistant", "content": [_tool_use("Agent")]}})
        p.write_text("\n".join([early, marker, late]) + "\n")
        self.assertIn("Agent calls: 1", self.run_check(p, "--since", "/reviewomatic"))


class SchemaTest(unittest.TestCase):
    def test_every_schema_prints_as_valid_json(self) -> None:
        h = Harness()
        try:
            for name in ("scope", "plan", "research", "result", "review"):
                data = json.loads(h.tp("schema", name, wf=False).out)
                self.assertIsInstance(data, dict, name)
            self.assertIn("review_batches", h.tp("schema", "plan", wf=False).out)
            self.assertIn("followups", h.tp("schema", "research", wf=False).out)
        finally:
            h.close()


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

    def test_naming_the_cited_file_itself_is_not_a_claim_to_check(self) -> None:
        # Seen live: `go.mod:30` was doubted because the sentence names `go.mod`, the heuristic
        # took `mod` from it, and nothing near line 30 says "mod".
        lines = ["module example.com/calc", ""] + ["// pinned"] * 27 + ["toolchain go1.22.0"]
        (self.h.src / "go.mod").write_text("\n".join(lines) + "\n")
        self.run_check("`go.mod` pins the toolchain (`go.mod:30`).\n", "--strict")
        self.run_check("The pin lives in `go.mod` (`src:go.mod:30`).\n", "--strict")
        res = self.run_check("`Multiply` is pinned in `go.mod` (`go.mod:30`).\n")
        self.assertIn("multiply", res.text.lower())        # a real name the line lacks is still doubted

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


sys.path.insert(0, str(SKILL / "scripts"))
from pipeline import docscheck, run  # noqa: E402


class ReportOnlyTest(unittest.TestCase):
    """docscheck.check(report_only=...): only the given documents are judged and counted, every
    document still feeds the link graph, and a link to a removed document is reported wherever
    it is."""

    def setUp(self) -> None:
        self.h = Harness()
        self.kb = self.h.kb

    def tearDown(self) -> None:
        self.h.close()

    def write(self, rel: str, text: str) -> None:
        p = self.kb / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def test_only_the_given_docs_are_judged_and_counted(self) -> None:
        self.write("index.md", "# KB\n\n- [A](a.md)\n")
        self.write("a.md", "# A\n\nSee [nope](nope.md).\n")
        self.write("b.md", "# B\n\nSee [gone](gone.md).\n")      # unjudged, unreachable, broken
        a = (self.kb / "a.md").resolve()
        errors, warnings, stats = docscheck.check([self.kb], {}, self.kb / "index.md", report_only={a})
        self.assertEqual([e for e in errors if "nope.md" in e], errors, errors)   # nothing about b.md
        self.assertEqual(len(errors), 1)          # a.md is reached through the unjudged index
        self.assertEqual(stats["files"], 1)
        self.assertEqual(stats["links"], 1)

    def test_a_link_to_a_removed_doc_is_reported_from_an_untouched_doc(self) -> None:
        self.write("guide.md", "# Guide\n\nSee [old](old.md).\n")
        removed = {(self.kb / "old.md").resolve()}
        errors, _, _ = docscheck.check([self.kb], {}, None, report_only=set(), removed=removed)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("guide.md:3: broken link old.md", errors[0])


class ChangedMarkdownTest(unittest.TestCase):
    """run._changed_md: what a git workspace gained, changed and removed since a baseline."""

    def setUp(self) -> None:
        self.h = Harness()
        self.repo = self.h.kb

    def tearDown(self) -> None:
        self.h.close()

    def write(self, rel: str, text: str = "# Doc\n") -> None:
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def commit(self) -> str:
        if not (self.repo / ".git").exists():
            git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "c")
        return git(self.repo, "rev-parse", "HEAD").strip()

    def rel(self, paths, root=None) -> set:
        return {str(p.relative_to((root or self.repo).resolve())) for p in paths}

    def test_names_git_would_quote_are_read_exactly(self) -> None:
        self.write("spaced name.md")
        base = self.commit()
        self.write("spaced name.md", "# Changed\n")
        self.write("docs/café.md")                       # untracked, non-ASCII
        changed, removed = run._changed_md(self.repo, base)
        self.assertEqual(self.rel(changed), {"spaced name.md", "docs/café.md"})
        self.assertEqual(removed, set())

    def test_a_workspace_in_a_subdirectory_reads_its_own_paths(self) -> None:
        self.write("site/old.md")
        self.write("other.md")
        base = self.commit()
        self.write("site/old.md", "# Changed\n")
        self.write("other.md", "# Changed\n")            # outside the workspace
        site = self.repo / "site"
        changed, _ = run._changed_md(site, base)
        self.assertEqual(self.rel(changed, site), {"old.md"})

    def test_deletions_and_rename_sources_are_removed(self) -> None:
        self.write("a.md")
        self.write("b.md")
        base = self.commit()
        (self.repo / "a.md").unlink()
        git(self.repo, "mv", "b.md", "c.md")
        changed, removed = run._changed_md(self.repo, base)
        self.assertEqual(self.rel(changed), {"c.md"})
        self.assertEqual(self.rel(removed), {"a.md", "b.md"})

    def test_no_answer_from_git_means_judge_every_file(self) -> None:
        self.write("a.md")
        self.commit()
        self.assertEqual(run._changed_md(self.repo, "0" * 40), (None, set()))
        self.assertEqual(run._changed_md(self.repo, None), (None, set()))


if __name__ == "__main__":
    unittest.main()
