"""Unit tests for the docscheck support heuristic's de-noising rules: wildcard/placeholder
tokens, mangled call spans, distant enclosing definitions, string-literal matches, and
camelCase/snake_case equivalence — with guards that genuine drift still warns."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pipeline.docscheck import Citation, _enclosing, _identifiers, check, supported

REPO = "repo"


def cite(sentence: str, start: int = 1, end: int = 1) -> Citation:
    return Citation(Path("doc.md"), 3, "src.py", start, end, sentence)


class IdentifiersTests(unittest.TestCase):
    def test_single_token_still_extracted(self):
        self.assertEqual(_identifiers("The reconciler sets `status` on each pod."), {"status"})

    def test_multi_word_spans_and_paths_are_skipped(self):
        # Commands and bare paths name nothing a supporting line must mention.
        self.assertEqual(_identifiers("Run `etcdctl snapshot save` from `/var/lib`."), set())


class WildcardTokenTests(unittest.TestCase):
    def test_placeholder_token_matches_its_literal_fragment(self):
        c = cite("The backup job writes `bak-<ts>` under the staging dir.")
        self.assertTrue(supported(c, ['\tp := filepath.Join(dir, "bak-"+stamp)'])[0])

    def test_placeholder_token_matches_alpha_prefix_in_go_name(self):
        c = cite("Each pod is named `node-<hex>` in the StatefulSet.")
        self.assertTrue(supported(c, ['\tpodName := fmt.Sprintf("node-%s", hex[:8])'])[0])

    def test_wildcard_command_token_matches_its_command_fragment(self):
        c = cite("Take a snapshot with `etcdctl_snapshot_save` before upgrading.")
        self.assertTrue(supported(c, ["\t# runs: etcdctl snapshot save /var/lib/etcd"])[0])

    def test_version_placeholder_matches_literal_fragments(self):
        c = cite("The image tag is `v<version>-<suffix>` in the release manifest.")
        self.assertTrue(supported(c, ['\ttag := fmt.Sprintf("v%s-%s", version, suffix)'])[0])

    def test_placeholder_with_no_matching_fragment_still_unsupported(self):
        c = cite("The backup job writes `bak-<ts>` under the staging dir.")
        self.assertFalse(supported(c, ["\tprintln(\"nothing relevant here\")"])[0])


class MangledSpanTests(unittest.TestCase):
    def test_mangled_call_span_matches_usable_name_fragments(self):
        c = cite("The server decodes `base64url(hmac-sha256(payload` before verifying it.")
        self.assertTrue(supported(c, ["\tn, err := base64url.Decode(body)"])[0])
        self.assertTrue(supported(c, ["\tsum := hmac_sha256(key, body)"])[0])

    def test_mangled_call_span_with_no_matching_fragment_still_unsupported(self):
        c = cite("The server decodes `base64url(hmac-sha256(payload` before verifying it.")
        self.assertFalse(supported(c, ["\tprintln(\"unrelated\")"])[0])


class DistantDefinitionTests(unittest.TestCase):
    def test_name_on_enclosing_definition_beyond_400_lines_supports(self):
        lines = ["func reconcileCluster(c *Cluster) error {"] + ["\tx := 1"] * 500 + ["\treturn nil", "}"]
        c = cite("The reconciler updates `cluster` status before returning.", start=480, end=482)
        self.assertTrue(supported(c, lines)[0])

    def test_name_absent_from_window_and_distant_definitions_still_unsupported(self):
        lines = ["func reconcileCluster(c *Cluster) error {"] + ["\tx := 1"] * 500 + ["\treturn nil", "}"]
        c = cite("The reconciler prunes `orphaned` leases before returning.", start=480, end=482)
        self.assertFalse(supported(c, lines)[0])


class StringLiteralTests(unittest.TestCase):
    def test_token_inside_quoted_string_literal_in_sentence(self):
        c = cite('The realm must be set to `"stratum.local"` on every node.')
        self.assertTrue(supported(c, ['\trealm := "stratum.local"'])[0])

    def test_token_matching_only_a_string_literal_value_supports(self):
        c = cite("The driver falls back to the `nats-jetstream` backend when no store is configured.")
        self.assertTrue(supported(c, ['\tdriver := os.Getenv("NATS_JETSTREAM")'])[0])


class CaseEquivalenceTests(unittest.TestCase):
    def test_camel_case_sentence_matches_snake_case_source(self):
        c = cite("The autoscaler stops at `maxReplicas` pods.")
        self.assertTrue(supported(c, ["\tif got := len(set); got > max_replicas {"])[0])

    def test_snake_case_sentence_matches_camel_case_source(self):
        c = cite("The autoscaler reads `max_replicas` from the config.")
        self.assertTrue(supported(c, ["\tif got := len(set); got > cfg.MaxReplicas {"])[0])

    def test_equivalence_does_not_match_a_different_name(self):
        c = cite("The autoscaler stops at `minReplicas` pods.")
        self.assertFalse(supported(c, ["\tif got := len(set); got > max_replicas {"])[0])

    def test_plain_single_token_matching_is_unchanged(self):
        c = cite("The reconciler sets `status` on each pod.")
        self.assertTrue(supported(c, ["\tstatus = Ready"])[0])


class DocFixtureTests(unittest.TestCase):
    def test_check_flags_only_the_genuinely_unsupported_citation(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / REPO
            repo.mkdir()
            (repo / "src.py").write_text(
                "package main\n"
                "\n"
                "def run():\n"
                "    p = os.path.join(dir, 'bak-' + stamp)\n"
                "    use(p)\n"
                "\n"
                "\n"
                + "    filler()\n" * 12
                + "\n"
                "def other():\n"
                "    print('unrelated')\n"
                "    return None\n"
            )
            doc = root / "doc.md"
            doc.write_text(
                "Backups land in `bak-<ts>` under the staging dir `src.py:4`.\n"
                "\n"
                "The backup job writes `bak-<ts>` on every run `src.py:22`.\n"
            )
            errors, warnings, stats = check([doc], {REPO: repo})
            self.assertEqual(errors, [])
            self.assertEqual(stats["citations"], 2)
            self.assertEqual(len(warnings), 1, warnings)
            self.assertIn("src.py:22", warnings[0])
            self.assertIn("bak-<ts", warnings[0])


if __name__ == "__main__":
    unittest.main()


class BoundsTest(unittest.TestCase):
    """supported() and _enclosing() take direct callers' values without raising:
    check() guards the inputs today, but the helpers must stand alone."""

    SRC = ["func f() {", "    token", "}"]

    def _cite(self, start: int, end: int) -> Citation:
        return Citation(doc=Path("x.md"), line=1, path="f", start=start, end=end,
                        sentence="it uses `token`")

    def test_start_zero(self) -> None:
        ok, _ = supported(self._cite(0, 1), self.SRC)
        self.assertTrue(ok)

    def test_start_far_past_eof(self) -> None:
        ok, _ = supported(self._cite(10_000, 10_002), self.SRC)
        self.assertFalse(ok)

    def test_end_past_eof(self) -> None:
        ok, _ = supported(self._cite(1, 99), self.SRC)
        self.assertTrue(ok)

    def test_empty_source(self) -> None:
        ok, names = supported(self._cite(1, 1), [])
        self.assertFalse(ok)
        self.assertEqual(names, {"token"})

    def test_enclosing_edge_cases(self) -> None:
        self.assertIsNone(_enclosing(self.SRC, 0))
        self.assertIsNone(_enclosing([], 5))
        self.assertIsNone(_enclosing(self.SRC, 10 ** 9))
