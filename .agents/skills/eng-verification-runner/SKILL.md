---
name: eng-verification-runner
description: Execute approved manual verification documents exactly as written against a user-prepared local CLI, fuzzy compose, or fuzzy kind environment. Use for strict step-by-step verification with readiness checks, literal expected-result comparison, immediate halt on mismatches or gaps, and structured evidence reporting. Never runs cloud verification or fixes code, environment, or documents. Supports direct requests and delegated/chained workflows.
---

# Engineering Verification Runner

Observe whether a prepared local system matches its verification document. Passing is not the objective; trustworthy evidence is. Run every in-scope test exactly as written and stop at the first discrepancy.

## Inputs

Require:

1. One or more verification document paths, or a folder containing them.
2. Explicit confirmation that the required local environment is prepared.

Also accept:

- Approved document order.
- Confirmation that prerequisites or sibling setup documents have run.
- Explicit authorization to begin after pre-flight (`start-approved`).
- Caller-provided environment details, working directory, variables, and prior decisions.

When a folder is supplied, enumerate eligible documents in filename order. Ask the direct user to confirm the order unless the caller already supplied or approved it. In delegated use, honor caller-provided readiness, order, and start approval; do not repeat answered questions. Return every pause or blocker to the caller in the structured format below.

## Requirements and Skill Boundaries

### Local environments only

Run only against:

- Local CLI with no remote backend.
- `fuzzy compose` on the developer machine.
- `fuzzy kind` on a local Kind cluster.

Never run against AWS, Azure, GCP, Vultr, shared development clusters, staging, production, or any other remote environment. If any selected document requires cloud or shared infrastructure, refuse that document and report its requirement. Do not substitute a partial local test.

### Execute, observe, and report only

- Do not set up an environment the user owns.
- Do not fix code, configuration, tests, documentation, or infrastructure.
- Do not change commands, flags, paths, assertions, scope, or expected results.
- Do not silently retry. Retry only when the document specifies it or the user/caller explicitly authorizes it.
- Do not mark output “close enough.” Extra fields, changed text, unexpected timing, or undocumented state are discrepancies.
- Do not skip, reorder, parallelize, batch, or combine tests unless the user/caller explicitly changes the approved run.
- Do not impose a timeout that the document does not specify. If a command runs unusually long, ask whether to continue waiting.

### Halt on any mismatch, ambiguity, or gap

Immediately stop before the next command when:

- Exit code, output, field, error text, timing, resource state, or UI behavior differs from Expected Result or Pass Criteria.
- A command is invalid or cannot run as written.
- Expected behavior is ambiguous or unobservable.
- A prerequisite, field, or required verification step is missing.
- The environment baseline differs from the document.

On halt:

1. Preserve the environment state. Do not run cleanup.
2. Record the exact command, exit code, stdout/stderr, expected result, pass criterion, and precise difference.
3. Offer possible classifications—implementation defect, verification-document defect, environment issue, specification ambiguity, or drift—without choosing one.
4. Request an explicit decision and wait.

Edits to a verification document require explicit approval because they change the source of truth. Investigation or fixes outside this skill require a separate user/caller instruction.

### Repository and delegation rules

- Follow `AGENTS.md`; use `CLAUDE.md` only as legacy repository guidance when relevant.
- Treat secrets in commands and output carefully; redact credentials while retaining diagnostic value.
- A delegated invocation must return `complete`, `halted`, `approval-needed`, or `blocked` with evidence and the exact resume point.

## Core Skill Process

### 1. Parse the verification set

Read every selected document fully. Confirm it contains test IDs, Steps, Expected Result, Pass Criteria, and Teardown. Extract:

- Environment type and required tools.
- Ordered tests and commands.
- Declared prerequisites and cross-document dependencies.
- Expected results and pass criteria.
- Estimated duration and cleanup instructions.

Reject cloud documents. If sibling setup or prerequisite documents are referenced, confirm their completion or include them in the proposed run when permitted.

### 2. Run read-only pre-flight checks

Do not mutate the environment during pre-flight.

For Compose, check stack status, service health, backend reachability, authentication state, and expected baseline with documented or equivalent read-only commands.

For Kind, check nodes, Fuzzball pods, operator health, CLI connectivity, authentication state, and expected baseline.

For Local CLI, check the binary path/version, required environment variables, and any local-only prerequisites.

If a check fails or the baseline differs, halt and report the command and exact output. Do not repair it.

### 3. Present the execution plan

Report:

- Documents and tests in execution order.
- Environment and estimated time.
- Verified prerequisites.
- Any rejected documents.
- The halt-on-first-discrepancy rule.

Obtain explicit start approval unless `start-approved` was already supplied by the delegating caller. A caller may authorize the run in advance; record that authorization in the manifest.

### 4. Execute each test sequentially

For each test:

1. Announce ID, title, spec reference, and purpose.
2. Run each command exactly as written, in order.
3. Capture command, exit code, stdout, and stderr.
4. Preserve exported IDs and context changes for subsequent steps.
5. Compare after every step, not only at test end.
6. Evaluate every pass criterion using observed evidence.
7. Record and report PASS before starting the next test.

Recognize these document patterns mechanically:

- **Workflow execute and verify:** capture `WF_ID`, follow events, confirm `Finished`, then inspect the specified job log.
- **Persistent service:** follow the scoped terminating stage or documented polling loop, run checks, then execute the documented workflow stop.
- **Expected error:** capture stdout and stderr; a non-zero exit is expected only when the test says so, and error text must match.
- **CRUD lifecycle:** execute add/create, list/info, state transition, and remove/delete in the documented order.
- **Context switch:** track the active context/user until the document switches back.
- **Idempotent command:** tolerate failure only when the command explicitly uses an approved pattern such as `2>/dev/null || true`.

Pattern recognition never relaxes evaluation. If the document omits a needed command or expected value, halt as a documentation gap.

### 5. Handle a discrepancy

Do not continue, clean up, edit, diagnose beyond the evidence, or attempt a fix. Return the halted report and wait. Resume only from the exact halted step after an explicit user/caller decision. Record any approved override, document edit, retry, or skip in the run log; never rewrite history.

### 6. Complete the run

After the final test, run teardown only when the document and user/caller authorization permit it. If teardown itself differs from the document, halt and report it like any other step.

Produce the run summary below. Do not suggest or apply production-code, build-system, or non-verification changes. Suggested next actions may include filing a defect, updating a verification document with approval, or rerunning a specific test after another workflow fixes the issue.

## Output Formatting

Maintain this result record during execution:

```markdown
| Test ID | Title | Status | Evidence / Resume Point |
| --- | --- | --- | --- |
| [ID] | [Title] | PASS / HALTED / SKIPPED | [Brief evidence or exact step] |
```

For every halt, report:

````markdown
### Verification Halt

**Status:** halted
**Document:** [path]
**Test:** [ID and title]
**Step:** [number and description]
**Command:**

```bash
[exact command]
```

**Exit Code:** [code or still running]

**Observed stdout:**

```text
[exact output, with secrets redacted]
```

**Observed stderr:**

```text
[exact output, with secrets redacted]
```

**Expected Result:** [verbatim or precise reference]

**Failed/Ambiguous Criterion:** [criterion]

**Difference:** [specific field, line, state, or missing evidence]

**Possible Classifications:** implementation defect / document defect / environment issue / specification ambiguity / drift

**Environment State:** preserved; cleanup not run

**Resume Point:** [exact command or decision after which execution may resume]

**Decision Needed:** [minimum explicit user/caller choice]
````

At completion or user-directed stop, report:

- `Status`: `complete`, `halted`, `approval-needed`, or `blocked`.
- `Run manifest`: documents, environment, revision if known, start/end times, duration, and source of start authorization.
- `Results`: full test table.
- `Mismatches`: detailed halt reports, or `None`.
- `Gaps`: ambiguous or incomplete document content and approval state.
- `Overrides`: explicit retries, skips, or interpretation decisions and who authorized them.
- `Teardown`: `completed`, `not run due to halt`, `not authorized`, or detailed failure.
- `Open decisions`: exact input needed to resume.
- `Recommended next actions`: suggestions only, within verification scope.

If input documents are invalid, the environment is not confirmed, or pre-flight cannot establish a safe baseline, report `blocked` or `approval-needed` with completed checks and the minimum input needed. Never manufacture a pass or broaden the environment scope to make progress.
