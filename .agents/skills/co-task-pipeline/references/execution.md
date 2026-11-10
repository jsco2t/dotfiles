# Execution and honest test corrections

Use the normal start → implementation → affected checks → done loop in [helper.md](helper.md).
Retain previous evidence rather than starting a new research/approval cycle per finding.

## Prevent premature pins

Before a red checkpoint, compile/load fixtures and check that tests execute the intended
behavior. An import error, build failure, unavailable device or broken setup is not a useful
behavioral failure. Correct these mistakes and rerun before pinning. Keep fixture checks
focused. Once checks pass and no new concern appears, proceed; do not repeat broad verification.

## Correcting pinned tests without human approval

The agent owns honest test repairs. A pin is evidence to preserve and, when mistaken, correct;
it is not a reason to wait overnight for permission to fix an import or expectation.

1. Inspect the original saved tests and red/pin log, task criteria and current diff. Identify
   the actual mistake and how the corrected test proves the unchanged requested behavior.
   Preserve every unaffected regression. Correct the tests in the running task’s declared
   paths; keep other actors’ edits separate. Do not restore the live production tree.
2. Choose the evidence basis. If values/cases/assertions and the genuine original behavioral
   proof are unchanged, use `basis: retained` with `assertions_unchanged: true`,
   `original_checkpoint_valid: true` and specific evidence. An original compiler/setup failure
   cannot be retained as behavioral red. A semantic correction needs a fresh reproduction.
3. For reproduction, prepare an isolated trustworthy pre-fix checkout/fixture outside all
   live workspace roots. Include the exact corrected test files, necessary source,
   dependencies/configuration and explicit baseline identity. Inspect the baseline diff;
   `.tp/baseline` copies alone may not reconstruct a multi-step repair’s original state.
   Baseline source symlinks cannot escape the directory, and the runner/language search path
   must not point into live workspaces. This is evidence bookkeeping, not an OS sandbox: the
   reviewer must inspect source/runner behavior and dependencies as well as the directory name.
   Execute the contracted verification command there:

   ```text
   tp correction-proof T01 --repair F1 --baseline <isolated-dir> --identity <exact-pre-fix-provenance> --snapshot git
   ```

   Omit `--repair` for a task-level pin; use `--snapshot walk` for a small non-Git fixture.
   This uses the same detached cancellable worker as normal checks. It records exact argv,
   baseline fingerprint, corrected test hashes, observed exit status, stability and log under
   a `proof-...` operation ID. It does not overwrite current green evidence. Inspect its log:
   intended assertion/behavior failure for red, original passing behavior for characterization.
   The helper cannot recognize every compiler/setup error; the reviewer must reject those.
   Do not invent the exit status or supply an arbitrary log in place of execution.
4. Run the current live verification check green. Get one focused independent reviewer with
   `role: review, purpose: test-correction, task: T01`, optional `repair: F1`, and `proof:
   <proof-operation>` when reproduced. Give the reviewer original/corrected tests, original
   criteria/pin, current diff/green log and baseline identity/actual proof log. They verify
   cases/assertions, meaningful regression detection and absence of weakened obligations.
   The helper binds mandatory corrected-test hashes and task/pin/proof revision even if
   optional review inputs are narrow. Attach the real host identity and validate the response.
5. Record `test-update T01 --repair F1 --file -`. JSON has `kind: correction`, concrete
   `reason`, `evidence`, `agent: <completed-assignment-id>` and `regression`. For reproduced
   evidence use `{"basis":"reproduced","operation":"proof-actual-id","evidence":"specific intended failure"}`.
   For retained evidence use the fields in step 2. A stale review, mismatched test/proof,
   missing real receipt or absent current green stops replacement. Original pin/copies/logs
   remain archived; the corrected pin carries the current proof. Continue without human approval.

Legacy workflows retain their previous formatting-only `kind: mechanical` procedure or actual
operator-authorized supersession. Do not silently migrate legacy authority. New workflows
require focused review of every pin correction; merely labeling a semantic change mechanical
does not bypass review. Before a pin, routine test fixes need no correction ceremony.

If a trustworthy pre-fix baseline cannot be reconstructed, investigate an alternate genuine
reproduction and record the limitation honestly. Do not manufacture red evidence, weaken tests
or ask the human to approve success without proof. Ask only for missing facts or material
requirements they actually need to decide.

## Evidence reuse and recovery

Current checks are available from `packet T01 --section checks`; a final reviewer without a
task can use `packet --section checks`. These are saved logs/definitions, not a fresh audit;
helper execution boundaries validate freshness. Include full source/config/runner/dependency
and environment inputs when caching. Ignore unrelated bookkeeping changes, never dependencies.

`next` and advancing commands merge finished check/proof receipts. Running/unknown operations
are not replayed. `cancel-check --id <id> --reason ...` requests cancellation through the
recorded worker; inspect/recover after it settles. Missing receipts require diagnosis, not
repeated respawn. External effect receipts must be reconciled by actual read-back before retry.

`metrics` exposes recorded counts and overlapping wall spans; use it at unit boundaries to
spot repeated work. After two unchanged check failures, diagnose infrastructure/readiness and
record `--retry-reason` before another attempt. An environment fix belongs in scope only when
a demonstrated blocker requires it. Required unavailable checks remain unfinished, never pass.
