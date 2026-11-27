"""Dispatch liveness: an in-flight step is judged by its agent's session — does one exist,
and when did it last produce a turn — not by a clock alone. Grounded in the 2026-11-27
KUB-1335 run, where two dispatches sat 21 and 29 minutes with no agent session at all (their
task calls were never sent) while tp said "in flight" and the watchdog kept firing, and one
was diagnosed dead and lost when its call had simply never started. A task whose call never
started is re-sent (no loss, no fresh brief); a session silent past the threshold is stale;
a live session or a running test command is work, never a stall."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from harness import Harness, elapse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pipeline import liveness  # noqa: E402


class LivenessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = h = Harness()
        h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def test_a_dispatch_whose_call_never_started_is_a_resend_not_a_lost_round(self) -> None:
        """The 29-minute verify gap: tp counted it in flight, the watchdog woke twice, and
        the manager had nothing to act on. A dispatch with no agent session past a short
        grace is a first-class action — re-send the call; no `tp lost`, no fresh agent."""
        h = self.h
        h.tp("dispatch", "T01")
        elapse(h, 6)                                   # past the grace; no kb-author session exists
        acts = {a["action"]: a for a in h.next()["actions"]}
        self.assertIn("resend", acts)
        self.assertEqual(acts["resend"]["id"], "T01")
        self.assertNotIn("stale", acts)                # nothing died: the call never started
        out = h.tp("next").out
        self.assertIn("tp resend T01", out)
        self.assertIn("T01", h.state()["in_flight"])   # the slot and brief are unchanged

    def test_a_live_session_beats_the_clock(self) -> None:
        """A 40-minute-old dispatch whose agent produced a turn a minute ago is working —
        a long review, a big generation — not 40 minutes of silence. The clock alone called
        it stale; the session says otherwise, so tp waits."""
        h = self.h
        h.tp("dispatch", "T01")
        elapse(h, 40)
        h.opencode_session("kb-author", "T01 author", seconds_ago=60)
        for a in h.next()["actions"]:
            self.assertNotIn(a["action"], ("stale", "resend"))
            self.assertNotEqual((a["action"], a.get("id")), ("stale", "T01"))
        self.assertIn("T01", h.state()["in_flight"])     # unbroken: waiting, never lost
        out = h.tp("next").out
        self.assertNotIn("tp lost T01", out)             # never counseled a loss
        self.assertNotIn("silence threshold", out)       # nor called silent

    def test_a_session_silent_past_the_threshold_is_stale(self) -> None:
        """A session that exists but has produced nothing for longer than the harness's
        silence kill is a dead dispatch: stale, `tp lost`, fresh dispatch — as before, but
        now on evidence (no turns) instead of a bare clock."""
        h = self.h
        h.tp("dispatch", "T01")
        elapse(h, 40)
        h.opencode_session("kb-author", "T01 author", seconds_ago=39 * 60)
        acts = [a for a in h.next()["actions"] if a["action"] in ("stale", "wait", "resend")]
        self.assertEqual([a["action"] for a in acts], ["stale"])
        self.assertEqual(acts[0]["id"], "T01")
        out = h.tp("next").out
        self.assertIn("tp lost T01", out)

    def test_resend_prints_the_call_again(self) -> None:
        h = self.h
        h.tp("dispatch", "T01")
        out = h.tp("resend", "T01").out
        self.assertIn("task(subagent_type=", out)
        self.assertIn("brief-author-0.md", out)          # the standing brief, unchanged
        self.assertIn("RESULT", out)
        self.assertIn("T01", h.state()["in_flight"])     # resend prints; it never re-dispatches
        self.assertIn("not in flight", h.tp("resend", "T02", expect=2).text)

    def test_an_untrusted_session_store_falls_back_to_the_clock(self) -> None:
        """A store whose newest row is hours old is not this run's store (wrong path, stale
        copy): trusting it could 'prove' a running agent unstarted and double-dispatch it.
        Then the clock alone decides — the old behavior, never a resend."""
        h = self.h
        h.opencode_session("full-access", "manager", seconds_ago=7 * 3600)  # store goes stale
        h.tp("dispatch", "T01")
        elapse(h, 40)
        acts = [a["action"] for a in h.next()["actions"]]
        self.assertIn("stale", acts)                    # the clock fallback
        self.assertNotIn("resend", acts)

    def test_a_missing_session_store_falls_back_to_the_clock(self) -> None:
        h = self.h
        h.db.unlink()
        h.tp("dispatch", "T01")
        elapse(h, 40)
        acts = [a["action"] for a in h.next()["actions"]]
        self.assertIn("stale", acts)
        self.assertNotIn("resend", acts)


class ProbeTest(unittest.TestCase):
    """Unit tests against the fake store: label matching, freshness, the trust guard."""

    def setUp(self) -> None:
        self.h = Harness()
        # The probe reads the store this process points it at, not a subprocess's env.
        import os
        os.environ["TP_OPENCODE_DB"] = str(self.h.db)

    def tearDown(self) -> None:
        import os
        os.environ.pop("TP_OPENCODE_DB", None)
        self.h.close()

    def test_the_verify_label_matches_when_the_state_says_review(self) -> None:
        """The live run stored the B3 verify round's step as 'review' while its session is
        titled 'B3/test-reviewer verify': the probe tries the label variants."""
        self.h.opencode_session("test-reviewer", "B3/test-reviewer verify", seconds_ago=30)
        probe = liveness.session_activity("test-reviewer", "B3/test-reviewer", "review", 60)
        self.assertIsNotNone(probe)
        self.assertEqual(probe["state"], "live")
        self.assertLess(probe["idle_min"], 1)

    def test_no_session_for_the_agent_means_unstarted(self) -> None:
        probe = liveness.session_activity("kb-author", "T01", "author", 0)
        self.assertIsNotNone(probe)
        self.assertEqual(probe["state"], "unstarted")

    def test_a_concurrent_sibling_of_the_same_agent_is_not_mistaken_for_this_one(self) -> None:
        """Three code-authors run at once; the label (T01 build) picks the right session,
        not the newest same-agent session. T01 was dispatched 30 minutes ago and has been
        silent for 25; T02 started next to it a minute ago."""
        self.h.opencode_session("code-author", "T02 build", seconds_ago=30)
        self.h.opencode_session("code-author", "T01 build", seconds_ago=25 * 60)
        probe = liveness.session_activity("code-author", "T01", "build", 30 * 60)
        self.assertEqual(probe["state"], "live")        # T01's own session, not T02's
        self.assertGreater(probe["idle_min"], 20)


class ProcessMatchTest(unittest.TestCase):
    """The long-build signal: a silent session whose test command is running is working."""

    def test_a_direct_command_line_matches(self) -> None:
        ps = "python3 -m unittest -q test_calc"
        self.assertTrue(liveness.cmd_running(ps, "python3 -m unittest -q test_calc"))

    def test_a_wrapper_prefix_is_dropped_and_quotes_normalized(self) -> None:
        """The live run's commands went through `tools/with-toolchain go test ...`; the
        process table shows the underlying `go test` line, unquoted."""
        ps = "go test -race ./internal/join -run AdminCancel"
        self.assertTrue(liveness.cmd_running(ps, "tools/with-toolchain go test -race ./internal/join -run 'AdminCancel'"))

    def test_a_different_target_never_matches(self) -> None:
        ps = "python3 -m unittest test_liveness"        # the test runner itself
        self.assertFalse(liveness.cmd_running(ps, "python3 -m unittest -q test_calc"))


if __name__ == "__main__":
    unittest.main()
