# Codex state helper

Use `python3 "<actual-skill-dir>/scripts/tp.py"` for `tp` below. Do not assume a deployed home
path when working on a repository copy. Python 3.9+ and a macOS/Linux filesystem are sufficient;
there are no third-party Python packages, custom agent registrations, or network dependencies.
Run its regression suite with `python3 -B -m unittest discover -s <skill-dir>/tests -v`.

## Starting and approving

```text
tp init <planning-location> --title <title> --request-file <verbatim-request-file>
tp schema scope
tp -w <workflow-dir> scope check
tp -w <workflow-dir> scope confirm --answer <actual-operator-response>
tp schema plan
tp -w <workflow-dir> plan check
tp -w <workflow-dir> approve --answer <actual-operator-response>
tp -w <workflow-dir> next
```

`init` creates `<location>/<UTC-date>-<slug>/`, adding a suffix for collisions. It preserves the
request in `request.md`. The caller writes `scope.json` and `plan.json` from the schema examples;
replace every example value with the actual work. `scope.md` and `plan.md` are rendered complete
contracts for operator review, not extra sources of state. `-w` precedes the command.
Approval also preserves original planned file contents under `.tp/baseline/`; the state's
`baseline_files` maps `workspace:path` to its saved file, or null for an initially missing file.
Use these copies to review the pipeline's actual edits separately from pre-existing user edits,
including in non-Git workspaces. Amendments add copies for newly planned files without replacing
the original copies of existing files.

`scope confirm` and `approve` are two separate gates. They record exact operator words supplied
by the calling agent. They cannot prove who spoke them: never fabricate a response, treat an
unanswered question as consent, or use this helper as a sandbox/authorization bypass.

## Contract format

Print `schema scope|plan|result|review|closeout` for complete examples. Essential fields:

- Scope: `title`, `deliverables` (`id`, `kind`, `what`, `where`), `workspaces` (`name`, absolute
  resolved `path`, `mode: read|write`), `constraints`, `non_goals`, `review: self|independent|none`,
  `max_agents: 0|1|2`, optional `estimate_minutes`. A future write directory may not exist yet.
  Deliverable kinds are code, tests, docs, kb, tutorial, education, research, pm, integration.
  Code/tests always require review. Independent review requires a nonzero agent allowance.
- Plan: `summary`, `tasks`, `checks`, `final_checks`. A task has `id`, `title`, `kind`, `serves`
  (deliverable ids), `workspace`, `paths`, `depends_on`, `acceptance`, `checks`, `verification`.
  Name individual relative files, including expected new files; no directory or glob write sets.
  Only research/integration tasks may have empty paths. Read-only workspaces cannot receive
  deliverables or check output. A file inside a nested workspace belongs to the nested workspace.
- Verification: `mode: red-green|characterization|existing|manual` and a specific `reason`.
  All automated modes require `check` naming one of the task's checks. The first two also require
  `test_paths` within task paths. Manual mode requires evidence in the result rather than a
  fabricated test command. Existing mode uses regression coverage without a new test phase.
- A named check has `argv` (a nonempty list of literal arguments), `workspace` for its working
  directory, and optional positive `timeout_seconds` (default 300). The helper does not parse
  shell syntax, expand `$HOME`, or run shell strings. If a repository genuinely requires a shell,
  explicitly plan `['bash', '-lc', '...']`. Check authorization includes any side effects of
  that approved command; do not use external writes or installation as incidental checks.

The helper validates dependency cycles, missing deliverables, evidence coverage, and concrete
write paths. It freezes scope/plan values on approval; direct edits are rejected. It does not
assess whether prose criteria are sufficient or evidence actually proves them. Codex must do so.

## Working loop

```text
tp -w <workflow-dir> start T01
tp -w <workflow-dir> test T01 --stage red --note <why-the-test-failure-proves-missing-behavior>
tp -w <workflow-dir> check unit
tp -w <workflow-dir> done T01 --result-file <result.json>
tp -w <workflow-dir> next
```

Only one task may be running. `start` checkpoints all workspaces. Test-first `red` requires a
failing check; characterization uses `--stage pin` and a passing check. Before that checkpoint,
only planned test files may have changed. The checkpoint pins test contents through completion.
To correct a defective test strategy, ask the operator and amend/restart with a documented
reason; never repeatedly repin weaker tests to make implementation pass.

`check` runs the approved command, records its exit status and source fingerprint, and saves
output under `checks/`. It does not infer a pre-existing failure or waive one. Missing programs,
timeouts, unexpected failures, and commands that change source artifacts cannot count as passes.
Use short focused commands and the runtime's interrupt controls if a check must stop on halt.

`done` requires a result like:

```json
{
  "task": "T01",
  "summary": "The requested behavior is implemented and verified.",
  "acceptance": [
    {"criterion": 1, "evidence": "src/calc.py:12 and test_calc.py:8; unit check PASS."}
  ]
}
```

Supply every criterion exactly once, numbered from 1. The helper compares workspace changes to
the task's file list, verifies pinned tests, and requires successful checks on the current
content. It also rejects unexplained changes between tasks. Inspect unexpected edits; never
auto-revert another actor's work. Ask before adopting those edits through an amendment.

Checkpoints compare file contents, symlink targets, and permissions. They skip `.git`, `.tp`,
the workflow directory, and common generated trees (`node_modules`, Python caches/venvs,
`target`, `dist`, `.next`, `.cache`). Explicit task files inside skipped trees are included.
Stat caching avoids rehashing unchanged files. This is drift detection within declared
workspaces, not a sandbox: it cannot monitor undeclared paths, transient writes restored before
sampling, or prove a command had no external side effects. Observe the contract independently.

## Questions, amendments, and repairs

```text
tp -w <workflow-dir> block --question <specific-unknown-and-its-consequence>
tp -w <workflow-dir> resolve --answer <operator-clarification>
tp -w <workflow-dir> amend --scope-file <draft-scope.json> --plan-file <draft-plan.json> --answer <approval>
tp -w <workflow-dir> reopen T01 --reason <confirmed-defect-and-evidence>
tp -w <workflow-dir> note <unrelated-discovery>
```

`block` preserves partial work and prevents further execution until a decision. `resolve` records
a clarification and does not change scope. For a changed contract, prepare new draft files,
validate their implications, show the exact changes, and ask before `amend`. Either draft flag
may be omitted to retain its approved value; during planning there may be no plan yet.
Amendment decisions and old/new contracts remain in history. Changed tasks and their dependents
reopen; changed scope reopens all tasks. Partial edits remain for inspection. Final check/review
records invalidate. An amendment may explicitly adopt concurrent edits; never use a made-up
answer to reset a failing checkpoint. Adopted edits are named in the decision history, and
completed tasks owning those files reopen for verification.
When moving a workspace to a different root, give it a new workspace name and update task/check
references in the draft; names retain their root identity so original file evidence stays clear.

`reopen` repairs in-scope work and reopens completed dependents without changing the contract.
On a test-first repair, add the regression test before changing production code, then checkpoint
it with the same planned test strategy. If existing partial production changes make that
impossible, inspect them and ask about a corrected plan rather than bypassing the gate.

## Review and completion

After every task is done, `next` requests final checks, final review, closeout as needed, then
`final`. Print `schema review` for the review format. `method` must match approved scope; an
independent result also names the actual `agent_id`. A passing review has an empty `findings`
list. A `changes` verdict has findings with `task`, `issue`, and `evidence`; these reopen owning
tasks and completed dependents. Validate findings before recording them. After fixes, run
required checks and review current artifacts again.

Closeout takes a JSON list with `id`, `classification: observation|deferred|followup`, and
`reason` describing the issue and consequence:

```text
tp -w <workflow-dir> closeout --file <decisions.json> [--answer <operator-decision>]
tp -w <workflow-dir> final
```

Deferrals and follow-up obligations require an operator answer; observations do not. Closeout
cannot skip a task. Defer required work only by an explicit scope/plan amendment. `final` checks
the gates and writes `report.md` with acceptance evidence, checks, actual review method,
amendments, and noticed items. It never commits, pushes, deploys, or files a ticket.

## Recovery and status

`halt --reason ...` (alias `hault`) preserves the current phase, running task checkpoint, and
approval. `resume --answer ...` restores that phase. Inspect interrupted edits, then follow
`next`; a running task continues from its checkpoint rather than being blindly restarted.
`status` is read-only; `status --json` exposes the complete persistent state and decision history.
An explicit status-only invocation stops after reporting; a status question during execution
does not end the active work. Mutating helper commands lock and atomically replace state.

State is identified as `codex-task-pipeline-v1`; existing Claude/OpenCode state is rejected
without modification. The operator's start/resume/halt/status interaction stays familiar;
internal helper commands and file schemas deliberately differ.
