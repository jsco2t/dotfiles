"""The guidance printed for a blocked task names a `tp resolve` that resolve accepts.

In a real run (KUB-1339) a code author handed back `blocked` for two files outside its write
list. The guide's list of routine mechanics offered "a retry (`--action retry --by manager`)":
the manager widened the task and ran it, and tp refused twice — `--answer` is required, and
retry does not apply to a blocked hand-back (an input block takes answer or skip)."""
from __future__ import annotations

import re
import shlex
import unittest

from harness import Harness


class BlockedGuidanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = Harness()
        self.h.approved()

    def tearDown(self) -> None:
        self.h.close()

    def blocked(self) -> str:
        h = self.h
        h.tp("dispatch", "T01")
        h.result("T01", "author", status="blocked", summary="Needs build/guide.md widened.",
                 questions=["Widen T01 with build/guide.md?"])
        return h.tp("record", "T01").out + "\n" + h.tp("next").out

    def test_every_retry_it_offers_carries_the_required_answer(self) -> None:
        out = self.blocked()
        for snippet in re.findall(r"`([^`]*--action retry[^`]*)`", out):
            self.assertIn("--answer", snippet, out)

    def test_the_answer_it_offers_for_a_blocked_handback_runs(self) -> None:
        h = self.h
        out = self.blocked()
        guide = next(line for line in out.splitlines() if line.startswith("→ human T01"))
        cmds = [c for c in re.findall(r"`(tp resolve [^`]*)`", guide) if "--action answer" in c]
        self.assertTrue(cmds, guide)
        args = shlex.split(cmds[0].replace('"..."', '"Widened; finish the task."'))[1:]
        args[args.index("--by") + 1] = "manager"                          # the guide offers manager|human
        self.assertIn("back in flight", h.tp(*args).out)
        self.assertEqual(h.state()["tasks"]["T01"]["status"], "in_flight")


if __name__ == "__main__":
    unittest.main()
