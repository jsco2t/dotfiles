# Task-pipeline tests

The tests import `harness` as a sibling module, so run them from this directory:

    cd tests
    python3 -m unittest discover -s .

or scoped:

    cd tests
    python3 -m unittest test_plan          # planning: scope, budget, checks, amend, coverage
    python3 -m unittest test_execute        # dispatch/record/accept gates, auto-accept (~90 s)
    python3 -m unittest test_code_flow      # split red/green gates + the fused build round
    python3 -m unittest test_docscheck      # docscheck unit tests (fast)
    python3 -m unittest test_progress       # closeout, lost dispatches, ship

Timings: the full suite is ~430 tests / ~5.5 min (integration tests shell out to real
`tp.py` subprocesses; nothing hangs — `test_execute` alone needs ~90 s, so a 120 s
timeout on the whole suite is too tight). `python3 -m unittest discover -s tests` from
the repo root also works; plain `python3 -m unittest tests.test_plan` does NOT (tests/
is not a package by design).

Lineage note: this suite merges the OpenCode and Claude Code variants' tests (the
2026-11 single-sourcing round). `tests/test_docscheck.py` carries the OpenCode-only
de-noising cases (node_modules exclusion, fragment matching, README-vs-index reachability);
the rest of the Claude suite covers the shared machinery — advance, publish, lean review,
plan amend/scope amend — that this copy now also implements. Run the whole suite after
any change that touches `pipeline/` modules both variants share.
