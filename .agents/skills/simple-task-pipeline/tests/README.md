# Simple-task-pipeline tests

The tests import `harness` as a sibling module, so run them from this directory:

    cd tests
    python3 -m unittest discover -s .

or scoped:

    cd tests
    python3 -m unittest test_plan          # planning: scope, estimates, checks, amend
    python3 -m unittest test_execute       # dispatch/record/accept gates (~85 s)
    python3 -m unittest test_docscheck     # docscheck unit tests (fast)

The integration tests shell out to the bundled `tp.py` in fresh processes and temporary
workspaces; allow a few minutes for the complete suite. `python3 -m unittest discover -s tests` from
the repo root also works; plain `python3 -m unittest tests.test_plan` does NOT (tests/
is not a package by design).

The copied suite runs against this skill’s own `scripts/tp.py`. The packaging test
checks a complete local workflow, bundled style loading, and halt/resume without
agent ids; it does not require OpenCode agent definitions or output styles.


`test_recovery_estimates` covers advisory stage/total estimates, long research/tasks/reviews,
read-only status, halt with partial work, recovery without a halt marker, legacy version-1
checkpoints, saved drafts, approvals and drift, code test/implementation/fix/review recovery,
all CLI command entry points, and a relocated skill running from another working directory.
Run it with:

    python3 -m unittest discover -s tests -p test_recovery_estimates.py

No agent-host SDK or API is required. Issue-survey tests use local fake CLIs; they do not
write to GitHub or Jira. `fanout_check.py` tests exercise the optional OpenCode log audit;
the pipeline itself does not depend on that audit or OpenCode's session store.
