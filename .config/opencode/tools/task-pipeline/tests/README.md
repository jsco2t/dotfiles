# Task-pipeline tests

The tests import `harness` as a sibling module, so run them from this directory:

    python3 run_parallel.py                 # everything, one worker per CPU — the usual way
    python3 run_parallel.py -j 4 test_plan  # a module, a class, or a test id

Scoped and serial (the runner runs whole classes; a single test inside one is fastest alone):

    python3 -m unittest test_plan.PlanTest.test_amend_needs_tasks   # one test
    python3 -m unittest test_plan          # one module, serially

The suite is ~460 tests. Nearly all of its time is spent waiting on `tp` subprocesses, so
the runner gives each test class its own interpreter and runs several classes at a time
(about 8 min serially; about 1 min with one worker per core on a 10-core host — and the
per-class processes keep tests that change os.environ, such as a fake session store, from
leaking into one another). The slowest classes start first, by the timings of the last run
(kept in `__pycache__`, which git ignores). `test_parallel_runner.py` tests the runner.

Timings: the full suite is ~460 tests / ~1 min via the runner (integration tests shell out
to real `tp.py` subprocesses; nothing hangs — `test_execute` alone needs ~90 s serially, so
a 120 s timeout on the whole suite is too tight). `python3 -m unittest discover -s tests`
from the repo root also works; plain `python3 -m unittest tests.test_plan` does NOT (tests/
is not a package by design).

Lineage note: this suite merges the OpenCode and Claude Code variants' tests (the
2026-11 single-sourcing round). `tests/test_docscheck.py` carries the OpenCode-only
de-noising cases (node_modules exclusion, fragment matching, README-vs-index reachability);
the rest of the Claude suite covers the shared machinery — advance, publish, lean review,
plan amend/scope amend — that this copy now also implements. Run the whole suite after
any change that touches `pipeline/` modules both variants share.
