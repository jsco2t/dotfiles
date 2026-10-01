#!/usr/bin/env python3
"""Tests for the atlassian toolkit, focused on the --adf raw-ADF body input.

Run: python3 test_atlassian.py -v
Covers the plain-text wrapping contract (text_to_adf), the additive --adf pass-through
(body_adf), argument wiring for every command that gained --adf, and one end-to-end
command execution with a stubbed api_request for issue comments and Confluence writes.
"""
import importlib.util
import io
import json
import unittest
from types import SimpleNamespace
from unittest import mock

SCRIPT = __file__.rsplit("/", 1)[0] + "/atlassian"

spec = importlib.util.spec_from_loader(
    "atlassian_toolkit",
    importlib.machinery.SourceFileLoader("atlassian_toolkit", SCRIPT),
)
at = importlib.util.module_from_spec(spec)
spec.loader.exec_module(at)


ADF_DOC = {
    "type": "doc", "version": 1,
    "content": [
        {"type": "heading", "attrs": {"level": 2},
         "content": [{"type": "text", "text": "Overview"}]},
        {"type": "paragraph", "content": [
            {"type": "text", "text": "uses "},
            {"type": "text", "text": "actions/checkout@v7",
             "marks": [{"type": "code"}]}]},
        {"type": "bulletList", "content": [
            {"type": "listItem", "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": "a/b.yaml:41", "marks": [{"type": "code"}]}]}]}]},
    ],
}


def args(ns, **kw):
    """An argparse-style namespace with defaults from `ns` overridden by kw."""
    merged = dict(vars(ns))
    merged.update(kw)
    return SimpleNamespace(**merged)


class TextToAdfTest(unittest.TestCase):
    """The existing plain-text contract must be unchanged."""

    def test_paragraph_split_on_blank_lines(self):
        doc = at.text_to_adf("one\n\ntwo")
        self.assertEqual([n["type"] for n in doc["content"]], ["paragraph", "paragraph"])
        self.assertEqual(doc["content"][0]["content"][0]["text"], "one")

    def test_single_newline_is_hard_break(self):
        doc = at.text_to_adf("a\nb")
        para = doc["content"][0]["content"]
        self.assertIn("hardBreak", [n["type"] for n in para])

    def test_markup_is_stored_literally(self):
        doc = at.text_to_adf("h2. Overview\n\n{{code}}")
        texts = [n.get("text", "") for n in doc["content"][0]["content"]]
        self.assertIn("h2. Overview", texts)
        texts2 = [n.get("text", "") for n in doc["content"][1]["content"]]
        self.assertIn("{{code}}", texts2)

    def test_no_markdown_or_wiki_parsing(self):
        doc = at.text_to_adf("plain text")
        self.assertNotIn("marks", doc["content"][0]["content"][0])


class BodyAdfTest(unittest.TestCase):
    def test_plain_text_path_matches_text_to_adf(self):
        self.assertEqual(at.body_adf("hello", False), at.text_to_adf("hello"))
        self.assertEqual(at.body_adf("hello", False), at.text_to_adf("hello"))

    def test_adf_document_passes_through_verbatim(self):
        self.assertEqual(at.body_adf(json.dumps(ADF_DOC), True), ADF_DOC)

    def test_adf_invalid_json_exits(self):
        with self.assertRaises(SystemExit):
            at.body_adf("{not json", True)

    def test_adf_non_document_exits(self):
        with self.assertRaises(SystemExit):
            at.body_adf('{"type": "paragraph"}', True)
        with self.assertRaises(SystemExit):
            at.body_adf('["not", "a", "doc"]', True)

    def test_adf_document_without_content_exits(self):
        with self.assertRaises(SystemExit):
            at.body_adf('{"type": "doc", "version": 1}', True)


class ParserWiringTest(unittest.TestCase):
    """Every command that writes a body accepts --adf; commands without one do not."""

    def test_issue_comment_accepts_adf(self):
        p = at.build_parser()
        a = p.parse_args(["jira", "issue", "comment", "KUB-1", "body text", "--adf"])
        self.assertTrue(a.adf)
        self.assertEqual(a.body, "body text")

    def test_issue_comment_without_adf(self):
        p = at.build_parser()
        a = p.parse_args(["jira", "issue", "comment", "KUB-1", "body text"])
        self.assertFalse(a.adf)

    def test_issue_worklog_accepts_adf(self):
        p = at.build_parser()
        a = p.parse_args(["jira", "issue", "worklog", "KUB-1", "2h", "--comment", "done", "--adf"])
        self.assertTrue(a.adf)

    def test_confluence_create_update_comment_accept_adf(self):
        p = at.build_parser()
        a = p.parse_args(["confluence", "create", "--space", "ENG", "--title", "T",
                          "--body", "-", "--adf"])
        self.assertTrue(a.adf)
        a = p.parse_args(["confluence", "update", "123", "--body", "-", "--adf"])
        self.assertTrue(a.adf)
        a = p.parse_args(["confluence", "comment", "123", "-", "--adf"])
        self.assertTrue(a.adf)

    def test_issue_create_has_no_adf_flag(self):
        # issue create/edit take rich input through --field description=...; no --adf there.
        p = at.build_parser()
        with self.assertRaises(SystemExit):
            p.parse_args(["jira", "issue", "create", "--project", "KUB", "--type", "Bug",
                          "--summary", "s", "--description", "-", "--adf"])

    def test_worklog_without_adf(self):
        p = at.build_parser()
        a = p.parse_args(["jira", "issue", "worklog", "KUB-1", "2h", "--comment", "done"])
        self.assertFalse(a.adf)


class CmdIssueCommentAdfTest(unittest.TestCase):
    def test_plain_body_is_wrapped(self):
        a = args(SimpleNamespace({"key": "KUB-1", "body": "hello", "adf": False, "id": None,
                                "json": False}))
        with mock.patch.object(at, "api_request", return_value={"id": "1"}) as req:
            at.cmd_issue_comment(a)
        sent = req.call_args.kwargs["body"]["body"]
        self.assertEqual(sent["type"], "doc")
        self.assertEqual(sent["content"][0]["content"][0]["text"], "hello")

    def test_adf_body_is_sent_verbatim(self):
        a = args(SimpleNamespace({"key": "KUB-1", "body": json.dumps(ADF_DOC), "adf": True,
                                "id": None, "json": False}))
        with mock.patch.object(at, "api_request", return_value={"id": "1"}) as req:
            at.cmd_issue_comment(a)
        sent = req.call_args.kwargs["body"]["body"]
        self.assertEqual(sent, ADF_DOC)
        heads = [n for n in sent["content"] if n["type"] == "heading"]
        self.assertEqual(len(heads), 1)

    def test_adf_body_invalid_json_exits_without_api_call(self):
        a = args(SimpleNamespace({"key": "KUB-1", "body": "{broken", "adf": True,
                                "id": None, "json": False}))
        with mock.patch.object(at, "api_request") as req:
            with self.assertRaises(SystemExit):
                at.cmd_issue_comment(a)
        req.assert_not_called()


class ConfluenceAdfTest(unittest.TestCase):
    def test_conf_comment_plain_vs_adf(self):
        a = args(SimpleNamespace({"page": 42, "body": "hello", "adf": False, "json": False}))
        with mock.patch.object(at, "api_request", return_value={"id": "9"}) as req:
            at.cmd_conf_comment(a)
        sent = json.loads(req.call_args.kwargs["body"]["body"]["value"])
        self.assertEqual(sent["content"][0]["content"][0]["text"], "hello")

        a = args(SimpleNamespace({"page": 42, "body": json.dumps(ADF_DOC), "adf": True,
                                "json": False}))
        with mock.patch.object(at, "api_request", return_value={"id": "9"}) as req:
            at.cmd_conf_comment(a)
        sent = json.loads(req.call_args.kwargs["body"]["body"]["value"])
        self.assertEqual(sent, ADF_DOC)

    def test_conf_update_body_adf(self):
        cur = {"version": {"number": 3}, "title": "T",
               "body": {"atlas_doc_format": {"value": json.dumps(ADF_DOC)}}}
        a = args(SimpleNamespace({"id": 42, "title": None, "body": json.dumps(ADF_DOC),
                                "adf": True, "json": False}))
        with mock.patch.object(at, "api_request", return_value=cur) as req:
            at.cmd_conf_update(a)
        payload = req.call_args.kwargs["body"]
        sent = json.loads(payload["body"]["value"])
        self.assertEqual(sent, ADF_DOC)
        self.assertEqual(payload["version"]["number"], 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
