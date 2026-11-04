# Codex state helper

Use `python3 "<actual-skill-dir>/scripts/tp.py"` for `tp` below. Do not assume a deployed home
path when working on a repository copy. Python 3.9+ and a macOS/Linux filesystem are sufficient;
there are no third-party Python packages, custom agent registrations, or network dependencies.
Run its regression suite with `python3 -B -m unittest discover -s <skill-dir>/tests -v`.
For incremental repair, measurement, scoped input reuse, operation recovery and compact
context commands, read [execution.md](execution.md) before using that mechanism. Complete-run
agent evaluations and independent grading are documented in [../evals/README.md](../evals/README.md).

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

Print `schema scope|plan|refine|test-update|result|review|closeout` for complete examples. Essential fields:

- Scope: `title`, `deliverables` (`id`, `kind`, `what`, `where`), `workspaces` (`name`, absolute
  resolved `path`, `mode: read|write`), `constraints`, `non_goals`, `review: self|independent|none`,
  `max_agents: 0|1|2|3`, optional `estimate_minutes`. New scopes use the standing allowance
  of three unless the operator sets a lower limit. A future write directory may not exist yet.
  Deliverable kinds are code, tests, docs, kb, tutorial, education, research, pm, integration.
  Code/tests always require review. Independent review requires a nonzero agent allowance.
  `max_agents` counts children; runtime capacity may include the parent and reduce available
  child slots. Final `review: self` does not prohibit delegated task/component reviews.
  Each workspace optionally selects `snapshot: git|walk` (legacy default `walk`). Select
  `git` for a Git worktree; it checkpoints tracked files (including tracked ignored outputs)
  and nonignored untracked files, without walking ignored caches. Explicit task files are
  included even when ignored. Deleted tracked files disappear from the snapshot and are
  detected as changes. Use separate workspaces for submodules; Git failure is an error, never
  a silent fallback. Choose `walk` for non-Git workspaces. Ignored undeclared source is outside
  a Git checkpoint; inspect meaningful ignored source and declare intended edits explicitly.
- New scopes include `requirements`: a nonempty list of `id` (`R1`, `R2`, ...), `text`, and
  `deliverables` (existing deliverable IDs). Account for every distinct requested outcome and
  explicit constraint; every deliverable must map back to the request. Existing approved
  workflows without this field remain compatible. The helper validates links, not whether
  the ledger faithfully captures the full request; compare it with `request.md` yourself.
- Plan: `summary`, `tasks`, `checks`, `final_checks`. A task has `id`, `title`, `kind`, `serves`
  (deliverable ids), `workspace`, `paths`, `depends_on`, `acceptance`, `checks`, `verification`.
  When scope has a requirement ledger, each task also has `requirements` (request requirement
  IDs); all requirements must have explicit task coverage, even when they share a deliverable.
  A task may name only requirements mapped to at least one deliverable that task serves.
  Name individual relative files, including expected new files; no directory or glob write sets.
  Research/integration tasks and explicitly adaptive tasks may have empty paths. Read-only workspaces cannot receive
  deliverables or check output. A file inside a nested workspace belongs to the nested workspace.
  Optional `adaptive: true` grants the manager permission, through plan approval, to add
  concrete paths/checks and establish test-first verification when findings become known.
  It also allows documented mechanical test corrections. Default false preserves legacy gates;
  it never grants new outcomes, roots, weaker tests or permission to adopt concurrent edits.
- Verification: `mode: red-green|characterization|existing|manual` and a specific `reason`.
  All automated modes require `check` naming one of the task's checks. The first two also require
  `test_paths` within task paths. Manual mode requires evidence in the result rather than a
  fabricated test command. Existing mode uses regression coverage without a new test phase.
- A named check has `argv` (a nonempty list of literal arguments), `workspace` for its working
  directory, optional positive `timeout_seconds` (default 300), and optional `reuse` (default
  false). Opt in only for checks whose inputs are declared workspace files in a stable
  environment; leave checks involving external services, time, or untracked inputs uncached.
  The helper does not parse shell syntax, expand `$HOME`, or run shell strings. If a repository
  genuinely requires a shell, explicitly plan `['bash', '-lc', '...']`. Check authorization includes any side effects of
  that approved command; do not use external writes or installation as incidental checks.
  Optional `inputs` maps workspace names to file/directory/glob patterns; optional `environment`
  names variables whose values affect the command. Definitions and these inputs determine
  freshness; omitted inputs conservatively fingerprint all monitored workspaces. See execution.md.

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
reason; never repeatedly repin weaker tests to make implementation pass. For an adaptive
review/fix task, successive `repair` steps have independent pins against each step's starting
contents; the entire task need not restart. New pins retain
the check log and original test copies in `.tp/test-baseline/` so mechanical corrections
can be inspected without restoring production code.

`show T01` reads one task's contract, status and recorded result/checks without writing state
or printing workspace fingerprint maps. Prefer it to `status --json` and full plan dumps.

`check` runs the approved command through a detached cancellable worker, records its exit status and source fingerprint, and saves
output under `checks/`. With `reuse: true`, an unchanged prior stable pass is returned without
execution; `check <name> --force` reruns it. A failed, missing, or stale result is never reused.
Red/pin checkpoints always execute their check. This saves repeated runs at the same contents;
it cannot observe changes outside declared workspaces or changes to environment state.
The helper does not infer a pre-existing failure or waive one. Missing programs,
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
The generated-tree exclusions above apply to `walk`; `git` uses Git's tracked/ignore rules
instead. Neither mode requires relocating caches, modifying ignore files, or changing product
layout to satisfy bookkeeping. Snapshot mode is part of scope; changing a legacy contract's
mode needs an approved amendment rather than an automatic migration.

## Adaptive detail and mechanical test corrections

```text
tp schema refine
tp -w <workflow-dir> refine T01 --file <refinement.json> --reason <finding-and-need>
tp schema test-update
tp -w <workflow-dir> test-update T01 --file <correction.json>
```

`refine` requires `adaptive: true` in the approved task. Its JSON contains only optional
`paths` (a list of concrete relative files), `checks` (name → definition), and `verification`.
Paths/checks append; existing checks must match exactly. New checks run in the task's existing
writable workspace and must be authorized, focused verification of its existing outcomes,
not installation or unrelated external mutations. Task IDs, dependencies, acceptance criteria,
deliverable/requirement mappings, final checks and scope stay unchanged. Verification may
move from `manual`/`existing` to `red-green`/`characterization` before a pin; it cannot replace
an approved test-first strategy. Use one coherent regression batch per adaptive review/fix unit.

Refine a pending/running task before editing the added files. The helper rejects unexpected
edits and newly exposed ignored contents, captures original file baselines, preserves the
running checkpoint/partial work, retains checks whose definitions and inputs remain current,
and invalidates final review. It records manager
provenance without an invented operator answer. If only paths are needed, `widen` remains
available on nonadaptive tasks too. Helper validation cannot decide whether prose justification
is truthful; the manager must keep every refinement within the approved outcomes.

`test-update` requires a running adaptive task, an existing pin with saved original copies,
and a fresh passing verification check on the corrected current contents. JSON needs
`kind: mechanical`, `reason`, and concrete `evidence` explaining why values, cases and assertions
are unchanged. Inspect the original saved tests and current diff. Use this only for equivalent
formatting/lint corrections (for example `0` → `0o0`), never assertion removal, new expectations,
test skipping or strategy changes. Those need operator-approved amendment. New behavior still
needs genuine pre-fix regression evidence; this command cannot create it retroactively.

The helper retains the previous checkpoint, original test copies and original red/pin log,
stores corrected copies/hashes, and records the correction in history/report. It does not
replay production or prove semantic equivalence automatically. It never accepts an ordinary
`test` call as permission to repin. Old pins without saved copies require an amendment.
This prevents a routine equivalent lint fix from forcing a rollback and a fresh approval.

## Questions, amendments, and repairs

```text
tp -w <workflow-dir> block --question <specific-unknown-and-its-consequence>
tp -w <workflow-dir> resolve --answer <operator-clarification>
tp -w <workflow-dir> resolve --by manager --answer <already-settled-answer> --evidence <saved-decision>
tp -w <workflow-dir> widen T01 --path <file> --deliverable D1 --reason <existing-criterion-and-why-it-needs-this-file>
tp -w <workflow-dir> amend --scope-file <draft-scope.json> --plan-file <draft-plan.json> --answer <approval>
tp -w <workflow-dir> reopen T01 --reason <confirmed-defect-and-evidence>
tp -w <workflow-dir> note <unrelated-discovery>
```

`block` preserves partial work and prevents further execution until a decision. `resolve` records
a clarification and does not change scope. Default `--by operator` records actual operator
words. `--by manager` requires `--evidence` pointing to the scope, plan, or saved decision
that already answers the question; it grants no new approval and keeps that provenance in
history/report. Consult those sources before blocking or asking a settled question again.

`widen` adds individual files to a pending/running task in its existing writable workspace
without another operator answer. Name one of its existing `serves` deliverables and explain
why unchanged criteria need the files. It cannot change scope, acceptance criteria, check
commands, test strategy, workspace roots, or adopt unexpected edits. Honor constraints and
non-goals independently. Widen before editing the extra files; existing drift and previously
untracked contents in ignored trees require inspection and an approved amendment. Reopen
completed work first, and finish any other running task. The helper preserves original
baselines, captures newly planned originals, keeps test pins/partial work, retains check records
whose command and inputs remain current, invalidates final review, and records a manager
decision. No heuristic proves the reason true.

For a changed contract, prepare new draft files, validate their implications, show the exact
changes, and ask before `amend`. Either draft flag
may be omitted to retain its approved value; during planning there may be no plan yet.
Amendment decisions and old/new contracts remain in history. Changed tasks and their dependents
reopen; changed scope reopens all tasks conservatively. Partial edits remain for inspection.
Unchanged current check results survive; changed commands/inputs and final review invalidate.
Task/repair checkpoints, correction history and completed repair results remain attached across
reopening. Prior attempts and removed tasks are archived separately in `.tp/state.json` under
`evidence_history`, including original contracts and red/pin copies/log links. Restart an affected
pending task with `start`; a pinned running repair resumes from the adopted checkpoint without
manufacturing another red. Earlier pins are checked across task boundaries and at final review.
An amendment may explicitly adopt concurrent edits; never use a made-up
answer to reset a failing checkpoint. Adopted edits are named in the decision history, and
completed tasks owning those files reopen for verification.
When moving a workspace to a different root, give it a new workspace name and update task/check
references in the draft; names retain their root identity so original file evidence stays clear.

`reopen` repairs in-scope work and reopens completed dependents without changing the contract.
On a test-first repair, add the regression test before changing production code, then checkpoint
it with the planned strategy. On an adaptive reopened task, use a new repair ID and regression
file while retaining prior repairs. If partial production changes make that impossible,
inspect them and ask about a corrected plan rather than bypassing the gate.

Replacing a pin requires concrete approval of the corrected test strategy and
`amend --supersede-tests T01` (task pin) or `--supersede-tests T01:F1` (repair pin); repeat the
flag for multiple pins. Original evidence is archived with the exact operator answer.
A superseded repair remains visible but no longer supplies valid verification; register its
approved replacement with `replaces: ["F1"]` and complete it before claiming the task's criteria.
An unrelated scope amendment cannot silently adopt changed pinned tests.
Mechanical equivalent corrections still use `test-update`
without another approval. Archive records are provenance, not a fresh pass.

## Review and completion

After every task is done, `next` requests final checks, final review, closeout as needed, then
`final`. Print `schema review` for the review format. `method` must match approved scope; an
independent result also names the actual `agent_id`. A passing review has an empty `findings`
list. If scope has a requirement ledger, review JSON also needs `requirements` with exactly
one `id` and concrete `evidence` per requirement, checked against the original request and
delivered artifacts. The report preserves these links and evidence. Legacy scopes without
the ledger keep their existing review format. A `changes` verdict has findings with `task`,
`issue`, and `evidence`; these reopen owning tasks and completed dependents. Validate findings
before recording them. After fixes, run required checks and review current artifacts again.

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
