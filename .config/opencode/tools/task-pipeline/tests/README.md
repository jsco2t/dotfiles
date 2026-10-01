# Task-pipeline tests

The tests import `harness` as a sibling module, so run them from this directory:

    cd tests
    python3 -m unittest discover -s .

or scoped:

    cd tests
    python3 -m unittest test_plan          # planning: scope, budget, checks, amend
    python3 -m unittest test_execute       # dispatch/record/accept gates (~85 s)
    python3 -m unittest test_docscheck     # docscheck unit tests (fast)

Timings: the full suite is ~190 tests / ~3.5 min (integration tests shell out to real
`tp.py` subprocesses; nothing hangs — `test_execute` alone needs ~90 s, so a 120 s
timeout on the whole suite is too tight). `python3 -m unittest discover -s tests` from
the repo root also works; plain `python3 -m unittest tests.test_plan` does NOT (tests/
is not a package by design).
