# Simple-task-pipeline tests

The tests import `harness` as a sibling module, so run them from this directory:

    cd tests
    python3 -m unittest discover -s .

or scoped:

    cd tests
    python3 -m unittest test_plan          # planning: scope, budget, checks, amend
    python3 -m unittest test_execute       # dispatch/record/accept gates (~85 s)
    python3 -m unittest test_docscheck     # docscheck unit tests (fast)

Timings: the full suite is ~280 tests / ~2 min (integration tests shell out to real
`tp.py` subprocesses; nothing hangs). `python3 -m unittest discover -s tests` from
the repo root also works; plain `python3 -m unittest tests.test_plan` does NOT (tests/
is not a package by design).

The copied suite runs against this skill’s own `scripts/tp.py`. The packaging test
checks a complete local workflow, bundled style loading, and halt/resume without
agent ids; it does not require OpenCode agent definitions or output styles.
