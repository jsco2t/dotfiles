#!/usr/bin/env python3
"""Offline regression tests for Atlassian body writes and link management.

Run: python3 test_atlassian.py -v
Covers plain text and rich bodies, versioned Confluence updates, legacy content
preservation, issue links, remote links, and parent hierarchy. API and HTTP calls
are stubbed; no credentials, network access, or live writes are needed.
"""
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
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
        a = args(SimpleNamespace(**{"key": "KUB-1", "body": "hello", "adf": False, "id": None,
                                "json": False}))
        with mock.patch.object(at, "api_request", return_value={"id": "1"}) as req:
            at.cmd_issue_comment(a)
        sent = req.call_args.kwargs["body"]["body"]
        self.assertEqual(sent["type"], "doc")
        self.assertEqual(sent["content"][0]["content"][0]["text"], "hello")

    def test_adf_body_is_sent_verbatim(self):
        a = args(SimpleNamespace(**{"key": "KUB-1", "body": json.dumps(ADF_DOC), "adf": True,
                                "id": None, "json": False}))
        with mock.patch.object(at, "api_request", return_value={"id": "1"}) as req:
            at.cmd_issue_comment(a)
        sent = req.call_args.kwargs["body"]["body"]
        self.assertEqual(sent, ADF_DOC)
        heads = [n for n in sent["content"] if n["type"] == "heading"]
        self.assertEqual(len(heads), 1)

    def test_adf_body_invalid_json_exits_without_api_call(self):
        a = args(SimpleNamespace(**{"key": "KUB-1", "body": "{broken", "adf": True,
                                "id": None, "json": False}))
        with mock.patch.object(at, "api_request") as req:
            with self.assertRaises(SystemExit):
                at.cmd_issue_comment(a)
        req.assert_not_called()


class ConfluenceAdfTest(unittest.TestCase):
    def test_conf_comment_plain_vs_adf(self):
        a = args(SimpleNamespace(**{"page": 42, "body": "hello", "adf": False, "json": False}))
        with mock.patch.object(at, "api_request", return_value={"id": "9"}) as req:
            at.cmd_conf_comment(a)
        sent = json.loads(req.call_args.kwargs["body"]["body"]["value"])
        self.assertEqual(sent["content"][0]["content"][0]["text"], "hello")

        a = args(SimpleNamespace(**{"page": 42, "body": json.dumps(ADF_DOC), "adf": True,
                                "json": False}))
        with mock.patch.object(at, "api_request", return_value={"id": "9"}) as req:
            at.cmd_conf_comment(a)
        sent = json.loads(req.call_args.kwargs["body"]["body"]["value"])
        self.assertEqual(sent, ADF_DOC)

    def test_conf_update_body_adf(self):
        cur = {"version": {"number": 3}, "title": "T",
               "body": {"atlas_doc_format": {"value": json.dumps(ADF_DOC)}}}
        a = args(SimpleNamespace(**{"id": 42, "title": None, "body": json.dumps(ADF_DOC),
                                "adf": True, "json": False}))
        with mock.patch.object(at, "api_request", return_value=cur) as req:
            at.cmd_conf_update(a)
        payload = req.call_args.kwargs["body"]
        sent = json.loads(payload["body"]["value"])
        self.assertEqual(sent, ADF_DOC)
        self.assertEqual(payload["version"]["number"], 4)


LINKS = {"fields": {"issuelinks": [
    {"id": "100", "type": {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
     "outwardIssue": {"key": "KUB-242"}},
    {"id": "101", "type": {"name": "Relates", "inward": "relates to", "outward": "relates to"},
     "inwardIssue": {"key": "KUB-242"}},
    {"id": "102", "type": {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
     "inwardIssue": {"key": "KUB-248"}},
]}}


class CmdIssueLinkDeleteTest(unittest.TestCase):
    def run_cmd(self, other, type_=None, dry_run=False):
        a = SimpleNamespace(key="KUB-252", other=other, type=type_, dry_run=dry_run)
        out = io.StringIO()
        with mock.patch.object(at, "api_request", return_value=LINKS) as req, \
                mock.patch("sys.stdout", out):
            at.cmd_issue_link_delete(a)
        return req, out.getvalue()

    def assert_exits_without_delete(self, other, type_=None):
        a = SimpleNamespace(key="KUB-252", other=other, type=type_, dry_run=False)
        with mock.patch.object(at, "api_request", return_value=LINKS) as req, \
                mock.patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit):
                at.cmd_issue_link_delete(a)
        self.assertEqual([c.args[0] for c in req.call_args_list], ["GET"])

    def test_deletes_the_typed_link_by_id(self):
        req, out = self.run_cmd("KUB-242", "blocks")
        self.assertEqual(req.call_args.args, ("DELETE", "/rest/api/3/issueLink/100"))
        self.assertIn("KUB-252 blocks KUB-242", out)

    def test_inward_link_reads_from_key_side(self):
        req, out = self.run_cmd("kub-248")
        self.assertEqual(req.call_args.args, ("DELETE", "/rest/api/3/issueLink/102"))
        self.assertIn("KUB-252 is blocked by kub-248", out)

    def test_several_links_without_type_exits_without_delete(self):
        self.assert_exits_without_delete("KUB-242")

    def test_no_match_exits_without_delete(self):
        self.assert_exits_without_delete("KUB-1")
        self.assert_exits_without_delete("KUB-248", "Relates")

    def test_dry_run_sends_no_delete(self):
        req, out = self.run_cmd("KUB-242", "Relates", dry_run=True)
        self.assertEqual([c.args[0] for c in req.call_args_list], ["GET"])
        self.assertIn("would delete link 101: KUB-252 relates to KUB-242", out)

    def test_parser_wiring(self):
        a = at.build_parser().parse_args(["jira", "issue", "link-delete", "KUB-1", "KUB-2", "--type", "Blocks",
                                          "--dry-run"])
        self.assertEqual((a.key, a.other, a.type, a.dry_run), ("KUB-1", "KUB-2", "Blocks", True))
        self.assertIs(a.func, at.cmd_issue_link_delete)


class CommandTest(unittest.TestCase):
    def run_command(self, argv, responses):
        a = at.build_parser().parse_args(argv)
        with mock.patch.object(at, "api_request", side_effect=responses) as req, \
                mock.patch("sys.stdout", io.StringIO()) as out:
            a.func(a)
        return req.call_args_list, out.getvalue()

    def assert_read_only_failure(self, argv, responses):
        a = at.build_parser().parse_args(argv)
        with mock.patch.object(at, "api_request", side_effect=responses) as req, \
                mock.patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit):
                a.func(a)
        self.assertTrue(all(c.args[0] == "GET" for c in req.call_args_list))


class ConfluenceUpdateTest(CommandTest):
    def page(self, fmt="atlas_doc_format", value=None, version=7):
        if value is None:
            value = json.dumps(ADF_DOC) if fmt == "atlas_doc_format" else '<p>Keep &amp; preserve</p>'
        return {"id": "42", "title": "Original", "version": {"number": version},
                "body": {fmt: {"value": value}}}

    def test_url_and_storage_file_replace_body_and_increment_version(self):
        storage = '<h2>Design</h2><ac:structured-macro ac:name="toc"/>'
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "page.xml"
            f.write_text(storage, encoding="utf-8")
            calls, _ = self.run_command([
                "confluence", "update", "https://ciqinc.atlassian.net/wiki/spaces/ENG/pages/42/Design",
                "--body-file", str(f), "--storage", "--version", "7"], [self.page("storage"), {}])
        self.assertEqual(calls[-1].args, ("PUT", "/wiki/api/v2/pages/42"))
        self.assertEqual(calls[-1].kwargs["body"], {
            "id": "42", "title": "Original", "status": "current", "version": {"number": 8},
            "body": {"representation": "storage", "value": storage}})
        self.assertFalse(calls[-1].kwargs["idempotent"])

    def test_plain_body_stdin(self):
        with mock.patch("sys.stdin", io.StringIO("new\n\ntext")):
            calls, _ = self.run_command(["confluence", "update", "42", "--body", "-"], [self.page(), {}])
        body = calls[-1].kwargs["body"]["body"]
        self.assertEqual(json.loads(body["value"]), at.text_to_adf("new\n\ntext"))

    def test_title_only_preserves_adf_exactly(self):
        cur = self.page()
        calls, _ = self.run_command(["confluence", "update", "42", "--title", "New"], [cur, {}])
        self.assertEqual(calls[-1].kwargs["body"]["body"]["value"], cur["body"]["atlas_doc_format"]["value"])

    def test_title_only_falls_back_to_storage_without_losing_macros(self):
        cur = self.page()
        cur["body"] = {}
        storage = '<ac:structured-macro ac:name="children"/>'
        calls, _ = self.run_command(["confluence", "update", "42", "--title", "New"],
                                    [cur, self.page("storage", storage), {}])
        self.assertEqual(calls[1].kwargs["params"], {"body-format": "storage"})
        self.assertEqual(calls[-1].kwargs["body"]["body"], {"representation": "storage", "value": storage})

    def test_empty_adf_on_legacy_page_uses_storage_instead(self):
        calls, _ = self.run_command(["confluence", "update", "42", "--title", "New"],
                                    [self.page(value=""), self.page("storage"), {}])
        self.assertEqual(calls[-1].kwargs["body"]["body"]["representation"], "storage")

    def test_missing_body_or_version_refuses_write(self):
        cur = self.page()
        cur["body"] = {}
        self.assert_read_only_failure(["confluence", "update", "42", "--title", "New"], [cur, cur])
        cur = self.page()
        del cur["version"]
        self.assert_read_only_failure(["confluence", "update", "42", "--body", "new"], [cur])

    def test_stale_authored_version_refuses_write(self):
        self.assert_read_only_failure(["confluence", "update", "42", "--body", "new", "--version", "6"],
                                      [self.page()])

    def test_page_changes_during_fallback_refuses_write(self):
        cur = self.page()
        cur["body"] = {}
        self.assert_read_only_failure(["confluence", "update", "42", "--title", "New"],
                                      [cur, self.page("storage", version=8)])

    def test_empty_stored_body_is_preserved(self):
        calls, _ = self.run_command(["confluence", "update", "42", "--title", "New", "--storage"],
                                    [self.page("storage", ""), {}])
        self.assertEqual(calls[-1].kwargs["body"]["body"]["value"], "")

    def test_raw_page_returns_editable_content_and_version(self):
        cur = self.page("storage")
        calls, out = self.run_command(["confluence", "page", "42", "--body-format", "storage", "--raw"], [cur])
        self.assertEqual(json.loads(out), cur)
        self.assertEqual(len(calls), 1)

    def test_storage_create(self):
        calls, _ = self.run_command(["confluence", "create", "--space", "12", "--title", "New",
                                     "--body", "<h1>Rich</h1>", "--storage"], [{"id": "42"}])
        self.assertEqual(calls[0].kwargs["body"]["body"], {"representation": "storage", "value": "<h1>Rich</h1>"})

    def test_invalid_input_never_calls_api(self):
        for options in (["--body", "broken", "--adf"], ["--body-file", "/no/such/body-file"], []):
            self.assert_read_only_failure(["confluence", "update", "42", *options], [])

    def test_conflicting_format_and_source_flags_rejected(self):
        for options in (["--adf", "--storage"], ["--body", "x", "--body-file", "x"]):
            with mock.patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit):
                at.build_parser().parse_args(["confluence", "update", "42", *options])


class VersionedPutTransportTest(unittest.TestCase):
    def test_versioned_put_serializes_storage_and_does_not_retry_lost_response(self):
        a = at.build_parser().parse_args(["confluence", "update", "42", "--body", "<p>New</p>", "--storage"])
        page_response = mock.MagicMock()
        page_response.__enter__.return_value.read.return_value = json.dumps({
            "title": "Original", "version": {"number": 7}}).encode()
        with mock.patch.object(at, "load_auth", return_value=("https://example.atlassian.net", "test", "fake")), \
                mock.patch.object(at, "build_ssl_context"), \
                mock.patch.object(at.urllib.request, "urlopen", side_effect=[page_response, TimeoutError("lost reply")]) as send, \
                mock.patch.object(at.time, "sleep") as sleep, mock.patch("sys.stderr", io.StringIO()) as err:
            with self.assertRaises(SystemExit) as exc:
                a.func(a)
        self.assertEqual(exc.exception.code, at.EX_NET)
        self.assertIn("may already have been applied", err.getvalue())
        self.assertEqual(send.call_count, 2)  # GET, PUT; no replay of the uncertain PUT
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.atlassian.net/wiki/api/v2/pages/42")
        self.assertEqual(request.method, "PUT")
        payload = json.loads(request.data)
        self.assertEqual(payload["body"], {"representation": "storage", "value": "<p>New</p>"})
        self.assertEqual(payload["version"]["number"], 8)
        sleep.assert_not_called()


class JiraLinkManagementTest(CommandTest):
    TYPES = {"issueLinkTypes": [{"id": "10", "name": "Blocks", "inward": "is blocked by", "outward": "blocks"}]}

    def test_create_both_directions_with_name_or_id(self):
        for direction, type_, key_side, other_side, label in [
            ("outward", "blocks", "inwardIssue", "outwardIssue", "blocks"),
            ("inward", "10", "outwardIssue", "inwardIssue", "is blocked by"),
        ]:
            with self.subTest(direction=direction):
                calls, out = self.run_command(["jira", "issue", "link", "KUB-1", "KUB-2", "--type", type_,
                                               "--direction", direction], [self.TYPES, b""])
                self.assertEqual(calls[-1].args, ("POST", "/rest/api/3/issueLink"))
                self.assertEqual(calls[-1].kwargs["body"], {"type": {"id": "10"},
                                  key_side: {"key": "KUB-1"}, other_side: {"key": "KUB-2"}})
                self.assertIn(f"KUB-1 {label} KUB-2", out)

    def test_create_dry_run_and_unknown_type_never_write(self):
        calls, out = self.run_command(["jira", "issue", "link", "KUB-1", "KUB-2", "--type", "Blocks", "--dry-run"],
                                      [self.TYPES])
        self.assertEqual(len(calls), 1)
        self.assertIn("would create", out)
        self.assert_read_only_failure(["jira", "issue", "link", "KUB-1", "KUB-2", "--type", "Missing"], [self.TYPES])

    def test_issue_links_show_ids_direction_and_json(self):
        calls, out = self.run_command(["jira", "issue", "issue-links", "KUB-252"], [LINKS])
        self.assertEqual(calls[0].kwargs["params"], {"fields": "issuelinks"})
        self.assertIn("KUB-252 blocks KUB-242", out)
        self.assertIn("KUB-252 is blocked by KUB-248", out)
        self.assertIn("id 102", out)
        _, out = self.run_command(["jira", "issue", "issue-links", "KUB-252", "--json"], [LINKS])
        self.assertEqual(json.loads(out), LINKS["fields"]["issuelinks"])

    def test_opposite_links_of_same_type_can_be_deleted_by_id(self):
        links = {"fields": {"issuelinks": [
            {"id": "1", "type": self.TYPES["issueLinkTypes"][0], "outwardIssue": {"key": "KUB-2"}},
            {"id": "2", "type": self.TYPES["issueLinkTypes"][0], "inwardIssue": {"key": "KUB-2"}}]}}
        argv = ["jira", "issue", "link-delete", "KUB-1", "KUB-2", "--type", "Blocks"]
        self.assert_read_only_failure(argv, [links])
        calls, _ = self.run_command([*argv, "--id", "2"], [links, b""])
        self.assertEqual(calls[-1].args, ("DELETE", "/rest/api/3/issueLink/2"))
        self.assert_read_only_failure([*argv, "--id", "999"], [links])

    def test_remote_links_still_use_existing_list_schema(self):
        links = [{"id": 5, "object": {"title": "Design", "url": "https://example.com/design"}}]
        calls, out = self.run_command(["jira", "issue", "links", "KUB-1", "--json"], [links])
        self.assertEqual(calls[0].args, ("GET", "/rest/api/3/issue/KUB-1/remotelink"))
        self.assertEqual(json.loads(out), links)
        _, out = self.run_command(["jira", "issue", "links", "KUB-1"], [links])
        self.assertIn("id 5", out)

    def test_remote_link_create_and_edit_preserve_metadata(self):
        argv = ["jira", "issue", "remote-link", "KUB-1", "https://example.com/new", "--title", "New"]
        calls, _ = self.run_command([*argv, "--global-id", "doc=42"], [{"id": 5}])
        self.assertEqual(calls[-1].kwargs["body"], {"globalId": "doc=42",
                          "object": {"url": "https://example.com/new", "title": "New"}})
        cur = {"id": 5, "self": "ignored", "globalId": "doc=42", "application": {"type": "com.atlassian.confluence"},
               "relationship": "mentioned in", "object": {"url": "old", "title": "Old", "summary": "Keep me"}}
        calls, _ = self.run_command([*argv, "--id", "5"], [cur, {}])
        self.assertEqual(calls[-1].args, ("PUT", "/rest/api/3/issue/KUB-1/remotelink/5"))
        payload = calls[-1].kwargs["body"]
        self.assertEqual(payload["object"]["summary"], "Keep me")
        self.assertEqual(payload["globalId"], "doc=42")
        self.assertEqual(payload["application"], cur["application"])
        self.assertEqual(payload["relationship"], "mentioned in")
        self.assertNotIn("self", payload)

    def test_remote_dry_runs_do_not_write(self):
        calls, out = self.run_command(["jira", "issue", "remote-link", "KUB-1", "https://example.com",
                                      "--title", "Doc", "--dry-run"], [])
        self.assertEqual(calls, [])
        self.assertEqual(json.loads(out)["method"], "POST")
        calls, _ = self.run_command(["jira", "issue", "remote-link-delete", "KUB-1", "5", "--dry-run"], [{"id": 5}])
        self.assertEqual([c.args[0] for c in calls], ["GET"])

    def test_remote_delete_uses_remote_endpoint(self):
        calls, _ = self.run_command(["jira", "issue", "remote-link-delete", "KUB-1", "5"], [b""])
        self.assertEqual(calls[-1].args, ("DELETE", "/rest/api/3/issue/KUB-1/remotelink/5"))

    def test_parent_edit_and_clear_are_hierarchy_fields(self):
        for option, expected in [(["--parent", "KUB-10"], {"key": "KUB-10"}), (["--clear-parent"], None)]:
            calls, _ = self.run_command(["jira", "issue", "edit", "KUB-1", *option], [b""])
            self.assertEqual(calls[-1].kwargs["body"], {"fields": {"parent": expected}})

    def test_parent_can_be_read_back_in_issue_json(self):
        issue = {"key": "KUB-1", "fields": {"parent": {"key": "KUB-10", "fields": {
            "issuetype": {"name": "Epic"}, "status": {"name": "Open"}}}}}
        calls, out = self.run_command(["jira", "issue", "get", "KUB-1", "--json"], [issue])
        self.assertIn("parent", calls[0].kwargs["params"]["fields"].split(","))
        self.assertEqual(json.loads(out)["parent"]["key"], "KUB-10")


class AttachmentTest(CommandTest):
    """`issue attach` is the one multipart write; it must encode a real file part, never JSON."""

    def setUp(self):
        import tempfile as _tf
        self.tmp = _tf.NamedTemporaryFile(suffix=".md", delete=False)
        self.tmp.write(b"# proposal\n")
        self.tmp.close()
        self.addCleanup(os.unlink, self.tmp.name)

    def test_multipart_body_has_file_part_and_matching_boundary(self):
        body, ctype = at.multipart_file_body("report.pdf", b"%PDF-1.7", "application/pdf")
        self.assertTrue(ctype.startswith("multipart/form-data; boundary="))
        boundary = ctype.split("boundary=", 1)[1].encode()
        self.assertIn(b'Content-Disposition: form-data; name="file"; filename="report.pdf"', body)
        self.assertIn(b"Content-Type: application/pdf\r\n\r\n%PDF-1.7\r\n", body)
        self.assertTrue(body.endswith(b"--" + boundary + b"--\r\n"))
        self.assertIn(b"--" + boundary + b"\r\n", body)

    def test_attach_posts_multipart_with_xsrf_header(self):
        calls, out = self.run_command(["jira", "issue", "attach", "KUB-1", self.tmp.name],
                                      [[{"id": "9", "filename": "x.md"}]])
        call = calls[-1]
        self.assertEqual(call.args, ("POST", "/rest/api/3/issue/KUB-1/attachments"))
        self.assertIsNone(call.kwargs.get("body"))  # no JSON body on a multipart write
        raw = call.kwargs["raw"]
        self.assertIn(b'name="file"; filename=', raw)
        self.assertIn(self.tmp.name.rsplit("/", 1)[-1].encode(), raw)
        self.assertTrue(call.kwargs["extra_headers"]["Content-Type"].startswith("multipart/form-data;"))
        self.assertEqual(call.kwargs["extra_headers"]["X-Atlassian-Token"], "no-check")
        self.assertIn("id 9", out)

    def test_attach_dry_run_makes_no_api_call(self):
        calls, out = self.run_command(["jira", "issue", "attach", "KUB-1", self.tmp.name, "--dry-run"], [])
        self.assertEqual(calls, [])
        plan = json.loads(out)
        self.assertEqual(plan["method"], "POST")
        self.assertEqual(plan["size"], len(b"# proposal\n"))

    def test_attach_rejects_quoted_and_path_filenames(self):
        for bad in ('say "hi".md', "two\rlines.md", ""):
            with self.assertRaises(SystemExit):
                at.safe_attachment_filename(bad)
        self.assertEqual(at.safe_attachment_filename("dir/sub/report.md"), "report.md")
        self.assertEqual(at.safe_attachment_filename("..\\..\\win.md"), "win.md")
        # a bad explicit --filename exits before any API call
        a = at.build_parser().parse_args(["jira", "issue", "attach", "KUB-1", self.tmp.name,
                                          "--filename", 'say "hi".md'])
        with mock.patch.object(at, "api_request") as req:
            with self.assertRaises(SystemExit):
                at.cmd_issue_attach(a)
        req.assert_not_called()

    def test_attach_missing_file_exits_without_api_call(self):
        a = at.build_parser().parse_args(["jira", "issue", "attach", "KUB-1", "/nonexistent.md"])
        with mock.patch.object(at, "api_request") as req:
            with self.assertRaises(SystemExit):
                at.cmd_issue_attach(a)
        req.assert_not_called()

    def test_attachments_list_reads_the_attachment_field(self):
        issue = {"fields": {"attachment": [{"id": "5", "filename": "report.pdf", "size": 9,
                    "author": {"displayName": "Jason"}, "created": "2026-11-10T01:02:03Z"}]}}
        calls, out = self.run_command(["jira", "issue", "attachments", "KUB-1"], [issue])
        self.assertEqual(calls[0].args, ("GET", "/rest/api/3/issue/KUB-1"))
        self.assertEqual(calls[0].kwargs["params"]["fields"], "attachment")
        self.assertIn("report.pdf", out)
        empty = self.run_command(["jira", "issue", "attachments", "KUB-1"], [{"fields": {}}])[1]
        self.assertIn("(no attachments)", empty)

    def test_attach_delete_uses_attachment_endpoint(self):
        calls, _ = self.run_command(["jira", "issue", "attach-delete", "KUB-1", "5"], [b""])
        self.assertEqual(calls[-1].args, ("DELETE", "/rest/api/3/attachment/5"))
        calls, out = self.run_command(["jira", "issue", "attach-delete", "KUB-1", "5", "--dry-run"],
                                      [{"id": "5", "filename": "report.pdf"}])
        self.assertEqual([c.args[0] for c in calls], ["GET"])
        self.assertEqual(json.loads(out)["id"], "5")


if __name__ == "__main__":
    unittest.main(verbosity=2)
