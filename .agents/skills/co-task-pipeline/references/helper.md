# Codex state helper

Use `python3 "<actual-skill-dir>/scripts/tp.py"` as `tp` below. Python 3.9+ on macOS/Linux,
standard library only. No global configuration, installations or network calls are needed.
Run regression tests with `python3 -B -m unittest discover -s <skill-dir>/tests -v`.

## New workflow: scope and independently reviewed plan

```text
tp init <location> --title <title> --request-file <verbatim-request> --author-agent-id <actual-main-id>
tp -w <workflow> scope settle
tp -w <workflow> plan check
tp -w <workflow> agent reserve --id A1 --capacity 1 --file -
tp -w <workflow> agent attach --id A1 --agent-id <actual-independent-reviewer>
tp -w <workflow> agent finish --id A1 --file -
tp -w <workflow> plan accept --agent A1
tp -w <workflow> start T01
```

Write `scope.json` and `plan.json` before their validation commands. `schema scope|plan|agent`
prints examples. The agent reservation must specify `role: review, purpose: plan`; include
request requirement IDs, source starting paths, question, stopping condition and model/rationale.
The packet binds the current request, scope, plan JSON and rendered `plan.md` revision.
Give that exact request/document to the actual reviewer. Attach its host identity, validate its
result, then record `accepted: true`, summary, evidence, validation and `unresolved: []` through
`agent finish`. `plan accept` requires the completed independent review and unchanged source;
open questions or stale revisions stop entry. Review records are agent-supplied provenance,
not cryptographic authentication of host identity. Never invent an independent reviewer.

`init` creates a dated slug, preserving the full request in `request.md`. `scope settle` records
a manager decision without a human answer. It enters internal `PLANNING`, which is still the
scoping phase. `plan check` renders readable Markdown headings, task descriptions, criteria,
files and commands; it does not wait for approval. `plan accept` enters implementation. The
human never needs to approve a new run’s scope or implementation plan.

Known material uncertainties must be resolved first. Use `block --question ...` and `resolve
--answer <actual-clarification>`. Use `resolve --by manager --answer ... --evidence ...` only
when saved decisions already answer it. Missing facts are not authorization. A newly discovered
product decision during implementation returns that part to scoping, preserving independent work.

## Contract fields

`schema scope|plan|refine|repair|result|review|closeout|test-correction` prints full examples.

- Scope: `title`, deliverables (`id: D1`, `kind`, `what`, `where`), `requirements` (`id: R1`,
  `text`, deliverable IDs), `constraints`, `non_goals`, `workspaces`, `review`, `max_agents`,
  optional `estimate_minutes`. Every requested outcome/constraint needs coverage. Kinds:
  code, tests, docs, kb, tutorial, education, research, pm, integration. Code/tests require
  final review. `review: independent` requires an agent allowance; `self` final review still
  permits bounded independent component/plan reviewers. Default allowance is three, bounded
  by host capacity and explicit user limits. New runs always need one independent plan review.
- Workspaces: unique lowercase `name`, absolute resolved `path`, `mode: read|write`, and
  `snapshot: git|walk` (legacy default walk). Name submodules separately. Git tracks tracked
  files plus nonignored untracked source; explicit task files and declared check inputs include
  meaningful ignored dependencies. Git failures are errors, not a fallback to a giant walk.
  Optional `monitor: ["file.md", "reference-directory"]` bounds captured paths and traversal.
  Use it for reference documents instead of watching archives. Files added/deleted under those
  directories are observed. Task files and check-input roots are always added to monitoring,
  including ignored glob matches. Undeclared paths outside this set are **not drift-detected**;
  keep whole monitoring where that guarantee matters. This is bookkeeping, not a sandbox.
- Plan: `summary`, `tasks`, named `checks`, `final_checks`. Each task: `id: T01`, `title`,
  `kind`, `serves`, `requirements`, `workspace`, concrete relative `paths`, `depends_on`,
  `acceptance`, `checks`, `verification`; optional `adaptive: true`. Dependencies must be
  acyclic and all requirements/deliverables covered. Adaptive review/repair or research and
  integration tasks can initially have empty paths. Paths cannot escape, name directories,
  include globs or traverse symlinks. Nested workspaces own their files.
- Verification: `mode: red-green|characterization|existing|manual`, `reason`; automated modes
  name `check`, test-first modes name nonempty `test_paths`. Use red-green for real behavior
  regressions, pin for characterization, existing coverage when adequate, and honest manual
  evidence when automation adds no value.
- Checks: literal `argv` list, execution `workspace`, optional positive `timeout_seconds`
  (default 300), `reuse` (default false), `inputs` workspace-to-pattern map, `environment`
  variable names. Reuse requires complete source/test/runner/config/dependency inputs and a
  stable environment. Missing inputs conservatively use all monitored workspaces. Include
  absent-file patterns so new files invalidate evidence. Environment values are hashed, not
  printed. Shell syntax is not expanded unless a shell is explicitly in argv; authorize its
  side effects independently. External/time-sensitive checks stay uncached.

The contract freezes on acceptance; direct file edits are drift, not amendments. `plan.md`
is regenerated on valid refinement/amendment. Consult it and `packet T01` during implementation.
Original planned file copies under `.tp/baseline/` distinguish pipeline edits from existing edits.

## Low-overhead payloads and execution

Every JSON-reading payload option accepts `-` for stdin. JSON files must not use `.md` or
`.markdown`; legacy mislabeled payloads should be resubmitted via stdin or `.json`, leaving the
historical evidence unchanged. Never manufacture a Markdown wrapper for machine state.

```sh
python3 "<skill>/scripts/tp.py" -w "<workflow>" done T01 --result-file - <<'JSON'
{"task":"T01","summary":"Delivered the requested behavior.","acceptance":[{"criterion":1,"evidence":"src/calc.py:12 and unit PASS log."}]}
JSON
```

For deterministic transitions, use a single batch. Each step has `argv` and optionally `input`
for stdin. Successful steps save independently; failure stops later steps and preserves prior
progress. Batches do not roll back, change workflows or execute in parallel. They return `next`
after success. Do not put a future test result or unknown agent identity into a precomputed batch.

```json
[
  {"argv":["check","unit"]},
  {"argv":["done","T01","--result-file","-"],"input":{"task":"T01","summary":"Delivered and checked.","acceptance":[{"criterion":1,"evidence":"Inspected diff and current unit log."}]}}
]
```

Only one task runs at a time. `start T01` checkpoints; implement its paths. `test T01 --stage
red|pin --note ...` runs the real contracted check and pins test copies/hashes. `done` requires
current passing task checks, retained pins and one evidence entry per numbered criterion.

`check <name>` uses a detached cancellable worker and durable receipts. Reusable stable passes
at identical declared inputs return their existing log; `--force` requests a rerun. Source
mutation, missing tools, cancellation, timeouts and stale checks never count as passes. After
two same-input failures in new runs, further retries require `--retry-reason <diagnosis/change>`.
Inspect fixtures/readiness first. A red checkpoint needs an intended behavior failure: the
helper cannot interpret every language’s compiler/setup output for you.

`next` and mutating boundaries recover finished worker receipts automatically. If one remains
running or unknown, inspect its operation/log, wait or `cancel-check --id ... --reason ...`;
then recover. No new human gate is needed. Unknown commits/publications require read-back,
not a blind retry. `operation begin/finish` records already-authorized external effects; it
does not execute them or grant permission. Read-only `status`, `packet` and `metrics` do not recover.

## Refinement and self-healing

`refine T01 --file - --reason ...` adds paths/checks and establishes test-first verification
on adaptive tasks without changing outcomes or pinned strategy. `widen T01 --path ...
--deliverable D1 --reason ...` adds files inside an existing workspace. Do this before editing
new files. Neither operation adopts unexpected edits. `repair start/test/done` gives successive
findings independent retained checkpoints inside one adaptive task. Prefer a coherent finding
batch; do not create a new human decision per defect.

Honest pinned test corrections use the detailed procedure in [execution.md](execution.md).
New runs require a focused independent reviewer for pin changes, preserving old evidence and
current genuine proof. Before pinning, correct mistakes directly. No human approval is needed
for same-contract test fixes. Do not label assertion weakening a mechanical correction.

`amend --by manager --reason ... --plan-file <draft.json>` can adjust same-scope scheduling,
concrete files and verification runners while preserving task IDs, titles, deliverables,
requirements, workspace roots, criteria, verification modes, existing paths/check obligations,
final gates and pins. Replacing an existing check definition requires an accepted independent
`purpose: amendment` assignment with `plan_file` naming that exact draft inside the workflow;
pass `--agent <id>`. Reviewer must verify the command still executes all required cases,
assertions and checks. It is not permission to replace tests with a no-op. Concurrent edits
cannot be auto-adopted. `refine` is simpler when only adding finding-driven detail.

Accepted tasks keep their delivery evidence when manager changes invalidate checks; the
helper marks affected completed tasks and transitive dependents `verification_dirty`. Repair
pending/running work first. `next` then requests stale affected checks and refreshes saved check
evidence without forcing repeated `done` records or creating dependency deadlocks. Final
review still covers integration and original requirement coverage. `reopen T01 --reason ...`
reopens an actual defective owner and marks completed dependents for verification in new runs.

New outcomes, changed scope or adoption of another actor’s edits need a real human decision:
`amend --answer <actual-response> --scope-file ... --plan-file ...`. Show the concrete change
when asking. Keep unrelated work as an observation instead of expanding the contract.

## Closeout and persistence

New-run `note <worthwhile-unrelated-finding>` records an optional observation immediately,
without assigning the human a follow-up obligation. Use it once per substantive finding, not
for progress chatter. Required work must finish; it cannot be parked as an observation.
Legacy `closeout --file ...` keeps its original deferral/follow-up approval contract.

`review --file -` records final method, verdict, summary, findings and evidence for every
request requirement. Independent methods identify the actual reviewer. Valid findings reopen
owners; retain prior coverage and rerun affected checks. `final` refuses missing tasks, dirty
verification, stale final checks, missing review, unsettled agents/effects or unclassified notes.
It writes the final human report and metrics. It does not run checks implicitly.

New-run JSON state holds references to immutable compressed checkpoint maps in one
`.tp/snapshots.sqlite3` file. Keep that database with state; missing/corrupt objects fail closed.
Legacy JSON checkpoints remain readable and retain their existing semantics. Fingerprint
caching uses stat signatures; content, symlink targets and permissions are checked. Durable
pins, original files, logs and effect receipts are evidence, not disposable junk.

Root artifacts are request, scope, readable plan, optional compact research notes, final report
and metrics. Use `.tp/drafts/`, `.tp/evidence/`, `.tp/scratch/` for their respective purposes.
Payloads and packets normally flow through stdin/tool output and need no files. Remove only
owned disposable scratch, retaining any content cited as evidence. Never clean historical runs
or other actors’ files opportunistically.

## Legacy compatibility and measurements

Existing states without `governance: autonomous` keep their actual scope-confirm/approve and
amendment contracts. Resume using saved authority; never fabricate an old user answer. Explicit
`init --legacy-approvals` exists only for historical evaluations/compatibility fixtures, not
new user work. It does not migrate live workflows. Status remains read-only.

`metrics` measures helper-boundary wall spans, recorded checks/reuse/agents and imported actual
host usage. `activity` can refine phase attribution; do not create a bookkeeping call for every
minor activity. Spans overlap; waiting labels are not proof of idle CPU/model time. Tokens are
unmeasured unless supplied from actual host receipts. See [../evals/README.md](../evals/README.md)
and [../evals/hidlins-execution-audit.md](../evals/hidlins-execution-audit.md) for evidence and limits.
