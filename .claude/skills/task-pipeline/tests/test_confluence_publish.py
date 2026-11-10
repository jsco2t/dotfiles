"""Confluence writes are `tp publish` steps run by the manager's own session, like Jira's. In real
runs a liaison sub-agent's footer comment was refused by the permission check although the human
had approved it, and a page edit stalled because the agent could read the page only as flat text
(its tables and code block would have been lost). Both runs ended stuck in EXECUTING."""
from __future__ import annotations

import json
import os
import stat
import unittest
from pathlib import Path

from harness import git
from scenarios import Mixed

FAKE = r'''#!/usr/bin/env python3
import json, sys
from pathlib import Path
state_path = Path(__file__).with_suffix(".state.json")
log_path = Path(__file__).with_suffix(".log")
state = json.loads(state_path.read_text())
args = sys.argv[1:]
body = sys.stdin.read() if "-" in args else None
with open(log_path, "a") as fh:
    fh.write(json.dumps({"args": args, "stdin": body}) + "\n")
def save():
    state_path.write_text(json.dumps(state))
if args[0] == "page":
    print(json.dumps({"id": args[1], "title": state["title"], "version": {"number": state["version"]},
                      "body": {"storage": {"value": state["storage"]}}}))
elif args[0] == "update":
    want = int(args[args.index("--version") + 1])
    if want != state["version"]:
        print(f"page version changed (expected {want}, found {state['version']})", file=sys.stderr)
        sys.exit(4)
    state["storage"] = Path(args[args.index("--body-file") + 1]).read_text()
    state["version"] += 1
    save()
    print(json.dumps({"id": args[1], "version": {"number": state["version"]}}))
elif args[0] == "comment":
    cid = str(state.get("next", 500)); state["next"] = int(cid) + 1
    state.setdefault("comments", []).append({"id": cid, "body": json.loads(body)})
    save()
    print(json.dumps({"id": cid, "body": {"atlas_doc_format": {"value": body}}}))
else:
    print("unsupported", args, file=sys.stderr); sys.exit(3)
'''

PAGE = ("<h2>Contract</h2><table><tr><th>Field</th><th>Meaning</th></tr><tr><td>rev</td><td>old</td></tr></table>"
        '<ac:structured-macro ac:name="code"><ac:plain-text-body><![CDATA[x := 1]]></ac:plain-text-body>'
        "</ac:structured-macro>")


class FakeConfluence:
    def __init__(self, root: Path) -> None:
        self.path = root / "bin" / "confluence"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(FAKE)
        self.path.chmod(self.path.stat().st_mode | stat.S_IEXEC)
        self.state_path = self.path.with_suffix(".state.json")
        self.state_path.write_text(json.dumps({"title": "Contract", "version": 7, "storage": PAGE}))
        self.saved = os.environ.get("TP_CONFLUENCE_BIN")
        os.environ["TP_CONFLUENCE_BIN"] = str(self.path)

    def restore(self) -> None:
        if self.saved is None:
            os.environ.pop("TP_CONFLUENCE_BIN", None)
        else:
            os.environ["TP_CONFLUENCE_BIN"] = self.saved

    def state(self) -> dict:
        return json.loads(self.state_path.read_text())

    def bump(self) -> None:  # someone else edits the page
        st = self.state()
        st["version"] += 1
        self.state_path.write_text(json.dumps(st))

    def writes(self) -> list:
        log = self.path.with_suffix(".log")
        calls = [json.loads(ln) for ln in log.read_text().splitlines()] if log.exists() else []
        return [c for c in calls if c["args"][0] in ("update", "comment")]


class ConfluencePublishTest(unittest.TestCase):
    def setUp(self) -> None:
        self.m = m = Mixed()
        self.conf = FakeConfluence(m.h.root)
        self.scope = m.scope(["docs", "integration"], ["docs", "doc-review"])
        self.scope["deliverables"][1] = {"id": "D3", "kind": "integration", "what": "The contract page, updated",
                                         "where": "confluence:2812936200"}

    def tearDown(self) -> None:
        self.conf.restore()
        self.m.close()

    def run_to_publish(self, to: str, draft: str, text: str, **extra) -> None:
        m, h = self.m, self.m.h
        doc = m.doc_task("T01", path=draft, brief="Write the page text from the current body.", checks=[])
        pub = {"id": "T02", "title": "Post it", "serves": ["D3"], "workspace": "app",
               "publish": dict({"to": to, "target": "2812936200", "body": draft}, **extra),
               "acceptance": ["Posted once and read back."], "estimate_min": 5, "depends_on": ["T01"]}
        h.init()
        (h.wf / "sources").mkdir()
        (h.wf / "sources" / "page.json").write_text(json.dumps(
            {"title": "Contract", "version": {"number": 7}, "body": {"storage": {"value": PAGE}}}))
        h.write_json("scope.json", h.scope(**self.scope))
        h.tp("scope", "check")
        h.tp("scope", "confirm", "--answer", "yes")
        h.write_json("plan.json", h.plan([doc, pub], final_checks=[]))
        h.tp("plan", "check")
        h.tp("plan", "submit")
        h.plan_review_pass()
        h.tp("approve")
        h.tp("dispatch", "T01")
        path = h.wf / draft[3:]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        h.result("T01", "author", changed=[str(path)])
        h.tp("record", "T01", "--agent-id", "da-1")
        h.tp("accept", "T01", "--note", "the text matches the code")
        for _ in range(4):  # the final review, then the publish is ready
            ready = [a["id"] for a in h.next()["actions"] if a["action"] == "review"]
            for sid in ready:
                h.tp("dispatch", sid)
                m.review_file(sid, 1, "pass")
                h.tp("record", sid, "--agent-id", f"rev-{sid}")
        self.assertEqual(h.next()["actions"][0]["action"], "publish")

    def test_a_page_edit_keeps_its_tables_and_macros_and_posts_from_this_session(self) -> None:
        h = self.m.h
        new = PAGE.replace("<td>old</td>", "<td>the precondition revision</td>")
        self.run_to_publish("confluence-page", "wf:drafts/contract.xml", new, base="wf:sources/page.json")
        out = h.tp("publish", "T02").out
        self.assertIn("tables 1 → 1, macros 1 → 1", out)
        self.assertNotIn("WARN", out)
        self.assertEqual(self.conf.writes(), [])                         # the dry run writes nothing
        out = h.tp("publish", "T02", "--answer", "Post it.").out
        self.assertIn("published T02", out)
        self.assertEqual(self.conf.state()["storage"], new)
        self.assertEqual(self.conf.state()["version"], 8)
        self.assertEqual(h.state()["tasks"]["T02"]["status"], "accepted")

    def test_a_flattened_draft_is_flagged_before_anything_is_written(self) -> None:
        h = self.m.h
        self.run_to_publish("confluence-page", "wf:drafts/contract.xml", "<p>Contract: rev means old.</p>",
                            base="wf:sources/page.json")
        out = h.tp("publish", "T02").out
        self.assertIn("WARN: the new body has fewer tables (1 → 0)", out)
        self.assertIn("fewer macros", out)

    def test_a_concurrent_page_edit_is_never_overwritten(self) -> None:
        h = self.m.h
        self.run_to_publish("confluence-page", "wf:drafts/contract.xml", PAGE.replace("old", "new"),
                            base="wf:sources/page.json")
        self.conf.bump()                                                  # edited after the draft's read
        self.assertIn("never overwrite", h.tp("publish", "T02", expect=2).text)
        self.assertEqual(self.conf.writes(), [])

    def test_an_edit_between_dry_run_and_post_is_refused(self) -> None:
        h = self.m.h
        self.run_to_publish("confluence-page", "wf:drafts/contract.xml", PAGE.replace("old", "new"),
                            base="wf:sources/page.json")
        h.tp("publish", "T02")
        self.conf.bump()
        self.assertIn("changed since the dry run", h.tp("publish", "T02", "--answer", "Post it.", expect=2).text)
        self.assertEqual(self.conf.writes(), [])

    def test_a_footer_comment_posts_once_and_reads_back(self) -> None:
        h = self.m.h
        self.run_to_publish("confluence-comment", "wf:drafts/note.md",
                            "## Updated\n\nThe engine now publishes the precondition revision.\n")
        self.assertIn("footer comment", h.tp("publish", "T02").out)
        out = h.tp("publish", "T02", "--answer", "Post both.").out
        self.assertIn("matches what was sent", out)
        self.assertEqual(len(self.conf.state()["comments"]), 1)
        self.assertIn("already accepted", h.tp("publish", "T02", "--answer", "again", expect=2).text)

    def test_plan_check_refuses_a_page_edit_from_markdown_or_without_a_base(self) -> None:
        m, h = self.m, self.m.h
        h.confirmed(**self.scope)
        doc = m.doc_task("T01", path="wf:drafts/contract.md", checks=[])
        pub = {"id": "T02", "title": "Post it", "serves": ["D3"], "workspace": "app",
               "publish": {"to": "confluence-page", "target": "2812936200", "body": "wf:drafts/contract.md"},
               "acceptance": ["Posted once."], "estimate_min": 5, "depends_on": ["T01"]}
        h.write_json("plan.json", h.plan([doc, pub], final_checks=[]))
        text = h.tp("plan", "check", expect=2).text
        self.assertIn("storage XHTML", text)
        self.assertIn("names `base`", text)


if __name__ == "__main__":
    unittest.main()
