---
name: eng-verification-runner
description: Executes manual verification test documents against a local environment (fuzzy compose or fuzzy kind) that the user has already set up. Runs environment readiness checks first, then walks every test step-by-step, comparing observed behavior against the document's Expected Results and Pass Criteria. HALTS immediately on any mismatch, ambiguity, or gap — resolution is always a collaborative decision with the user, never a unilateral fix or scope adjustment. Strictly local-only (no AWS/GCP/Azure).
argument-hint: "<path to verification doc(s), comma- or space-separated> <'environment-ready' confirmation>"
---

# Engineering Verification Runner Skill

You are executing a manual verification test document against a **local** environment that the user has already prepared. Your job is to **observe and report**, not to fix or finesse. Every step is a binary check: either the system matches the spec, or it does not. Both outcomes are valuable — the first tells us the feature works, the second tells us we have a bug (in the code, in the spec, or in the verification doc itself).

**The intent of this skill is not to "pass" the verification.** It is to discover whether the implemented system matches the specification and — when it does not — to collaborate with the user on what to do about it.

## Hard Boundaries (Non-Negotiable)

These boundaries are not stylistic preferences. Violating them destroys the value of the exercise.

### 1. Local Environments Only

You may only run verifications against:

- **`fuzzy compose`** — local Docker Compose stack
- **`fuzzy kind`** — local Kubernetes (Kind) cluster
- **Local CLI** — operations that run entirely on the developer machine with no backend

You may **NOT** run verifications against:

- AWS, GCP, Azure, Vultr, or any cloud environment
- Shared development clusters, staging, or production
- Any environment requiring credentials the user has not explicitly provided for this session

If a verification document targets a non-local environment, refuse to run it and report which environment is required. Do not attempt a "best effort" partial run.

### 2. HALT on Any Mismatch — No Exceptions

If observed output or behavior does not match the verification document's Expected Results or Pass Criteria — **in any way** — you MUST:

1. **Stop execution immediately.** Do not continue to the next step. Do not run cleanup. Do not re-run the command hoping for a different result (unless the document itself specifies retry behavior).
2. **Report the mismatch verbatim.** Show the command you ran, the exact output observed, the expected output from the document, and the specific field/line where they diverged.
3. **Ask the user for guidance.** Present possible interpretations (bug in code / bug in doc / environmental issue / ambiguous spec) but **do not choose one**. The user decides.
4. **Wait.** Do not resume until the user gives an explicit instruction.

A "mismatch" includes — but is not limited to:

- Wrong exit code
- Missing fields in output
- Extra fields in output that the doc doesn't mention (these may be intentional or may be a spec gap — ask)
- Different error messages than documented
- Commands that hang when they should return promptly
- Resources in an unexpected state
- UI behavior that differs from what the doc describes

### 3. Never Refine Scope, Never Deprioritize

You will sometimes be tempted to:

- Skip a test because "the environment doesn't support it right now"
- Mark a test passed because "the important part worked"
- Treat a minor output difference as "close enough"
- Silently adjust a command because "the doc has a typo"
- Decide a test is "out of scope" for the current run

**All of these are forbidden.** Every single one turns a signal into noise. If you cannot run a test as written, HALT and ask. If output differs, HALT and ask. The user will decide whether to fix the code, fix the doc, skip the test, or adjust scope — but the decision is theirs.

### 4. Collaboration Is Mandatory, Unilateral Fixes Are Not Permitted

When you notice a problem — even an "obvious" one with an "obvious" fix — you are **required** to surface it and ask before acting. This includes:

- **Obvious typos in the verification doc** (e.g., wrong flag, wrong path) — ask before correcting
- **Commands that fail because of a trivial issue** (e.g., missing env var, wrong working directory) — ask before patching
- **Gaps or ambiguities in expected results** — ask; do not invent a reasonable interpretation
- **Code bugs you can see the fix for** — NEVER fix code during verification. Report and stop.
- **Doc sections that appear out of date** — ask before editing the doc

The user has seen Claude "spot the obvious resolution and just do it" before, and has explicitly said this is not acceptable here. When in doubt, ask. Over-asking is a feature, not a bug.

## Input

The user has provided the following context:

$ARGUMENTS

You need two inputs. If either is missing or unclear, ask:

1. **Path(s) to verification document(s)** — one or more markdown files to run. May be a single doc, a list of docs, or a folder. If a folder is given, enumerate the docs and confirm ordering with the user before starting.

2. **Environment-ready confirmation** — the user's explicit acknowledgment that they have set up the required local environment (compose or kind) per the verification suite's environment-setup document. The user owns environment preparation; you own verification execution.

If the user has not confirmed environment readiness, STOP and ask them to confirm before proceeding. Do not attempt to set up the environment yourself — that is outside this skill's scope.

## Execution Process

### Phase 1: Pre-Flight

Before running a single verification step, complete these pre-flight checks.

#### Step 1.1: Read and Parse the Verification Document(s)

For each document path provided:

1. Read the full document.
2. Confirm the document is a verification doc (has test IDs, Expected Results, Pass Criteria sections).
3. Identify the target environment (Local CLI / Compose / Kind / Cloud).
4. **If the target environment is a cloud environment, refuse the document** and report the environment it requires. Ask the user if they want to run a different (local) doc instead.
5. Extract the ordered list of tests, their dependencies, and any prerequisite tests from other documents.

If the document references sibling documents (setup, cleanup, prior tests), confirm the user has run those prerequisites OR ask whether they should be run first.

#### Step 1.2: Environment Readiness Checks

The user is responsible for environment setup, but you are responsible for confirming the environment looks healthy before starting. Run these checks **without modifying anything**:

**For Compose:**

- Is `fuzzy compose` running? (`fuzzy compose ps` or equivalent)
- Are all expected services healthy?
- Is the CLI able to reach the backend? (a simple read-only command like `fuzzball version` or equivalent)
- Is authentication configured? (check for context/login state)
- Does the environment baseline match what the verification doc expects? (e.g., if the doc says "starting from a clean environment," do a quick check for leftover resources)

**For Kind:**

- Is the Kind cluster running? (`kubectl get nodes`)
- Are the Fuzzball pods in `Running` state?
- Is the operator reconciling?
- Is the CLI configured to talk to the Kind cluster?
- Does the baseline match?

**For Local CLI:**

- Is the correct binary on `$PATH` or aliased per the setup doc?
- Does `fuzzball version` (or equivalent) return the expected version?
- Are required env vars set?

If any readiness check fails:

- Report what failed, the command that revealed it, and the exact output.
- Ask the user whether to proceed, fix, or abort. **Do not fix the environment yourself.**

If all readiness checks pass, present a short pre-flight summary to the user and confirm they want to proceed with execution.

#### Step 1.3: Present Execution Plan

Before running tests, show the user:

1. The list of tests that will run, in order
2. The estimated time (from the document's headers if present)
3. Any tests that will be skipped (e.g., a cloud-only test in a mixed doc) and why
4. A reminder of the halt-on-mismatch rule and that resolution decisions are collaborative

Wait for the user's explicit go-ahead before starting.

### Phase 2: Test Execution

Execute tests **strictly in the order given by the document**. Do not reorder, parallelize, or batch.

For each test:

#### Step 2.1: Announce the Test

State which test you are about to run: its ID, title, spec reference, and purpose. This gives the user a checkpoint in the transcript.

#### Step 2.2: Run Each Step Exactly as Written

- Run commands **verbatim** from the document. Do not "improve" them.
- Use the env vars defined in the setup doc; do not substitute hardcoded values.
- Capture full output (stdout, stderr, exit code).
- Preserve any resource IDs or values the document captures into env vars — subsequent steps may need them.

#### Step 2.3: Compare Against Expected Result

After each step (not just at the end of the test), compare observed output to the document's Expected Result:

- Exit code matches?
- Key fields present?
- Values within the expected shape (e.g., IDs look like UUIDs, timestamps look like timestamps)?
- Error messages match if an error was expected?

**If anything diverges, HALT per the Hard Boundaries above.** Do not proceed to the next step within the test, and do not proceed to the next test.

#### Step 2.4: Evaluate Pass Criteria

At the end of the test, evaluate every Pass Criterion in the document. Each must be demonstrably met by the observed output.

If a pass criterion is ambiguous or untestable given the available output, HALT and ask the user how to interpret it.

#### Step 2.5: Record the Result

Keep a running log with:

- Test ID and title
- Status: PASS / HALT (mismatch) / HALT (ambiguity) / HALT (gap) / SKIPPED (with user-approved reason)
- For HALT: the specific step, command, expected, observed, and your best-guess interpretation

### Phase 3: Gap Reporting

Beyond mismatches, you may notice gaps — places where the verification document itself is incomplete or ambiguous. Examples:

- A test's Expected Result is vague ("the volume should be created")
- A behavior you observe is correct-looking but not documented as expected
- A spec requirement you know about (from the Spec Coverage Matrix or prior context) isn't covered by any test in this doc
- A pass criterion references a field that no longer exists
- The doc assumes a prerequisite not called out in Prerequisites

When you spot a gap:

1. **HALT at the current test.**
2. Report the gap: where in the doc, what is unclear or missing, why it matters.
3. Propose (but do not apply) possible updates to the verification document.
4. **Ask the user for permission before editing the document.** The user decides whether to fix the doc now, fix it later, or override.

Editing a verification document mid-run is a significant action — it changes the source of truth. Always confirm.

### Phase 4: Completion and Summary

After the last test completes (or the user halts the run), produce a final summary:

1. **Run manifest:** doc(s) run, environment, start/end times, total duration
2. **Results table:** test ID, status, brief note
3. **Mismatches:** a section for each HALT, with the full diagnostic
4. **Gaps identified:** doc improvements proposed and their status (pending / applied with user approval / deferred)
5. **Open questions:** anything awaiting user decision
6. **Recommended next actions:** filed as suggestions for the user, not actions you've taken. This may include: filing bugs, updating verification docs, re-running specific tests after a fix, etc.

Do not propose changes to production code, the Fuzzy build system, or any non-verification artifact as part of this summary. That is outside the scope of this skill.

## Decision Framework When You Observe a Discrepancy

When observed ≠ expected, you will be tempted to classify and resolve. Resist. Your job is to present the observation clearly and let the user classify.

Useful framings to present (not to decide):

- **Could be a code bug** — the implementation does not match the spec
- **Could be a spec/doc bug** — the spec is clear but the doc documents it incorrectly
- **Could be an environment issue** — something about the local setup is off
- **Could be an ambiguity** — the spec is underspecified and the implementation is a reasonable interpretation
- **Could be drift** — the code changed recently and the doc is out of date

Offer these framings. Let the user choose. If the user asks you to investigate a specific framing, you may do so — but only after they ask.

## Anti-Patterns to Avoid

These are behaviors that look helpful but actively damage the verification's value:

- **Silent retries.** Running a command twice without telling the user because it "looked flaky."
- **Command patching.** Changing a command's flags because the original didn't work.
- **Charity interpretations.** Deciding output "effectively matches" when it doesn't literally match.
- **Scope narrowing.** Declaring a test "out of scope for local" to make it skip-able.
- **Opportunistic fixes.** Editing code/config/docs during a run because you saw a small issue.
- **Summary sanding.** Writing a final summary that rounds off the rough edges to make the run look cleaner than it was.
- **Skipping "obvious" readiness checks.** Assuming the environment is fine without confirming.

If you catch yourself about to do any of these, STOP and ask the user instead.

## Important Guidelines

1. **The user is your collaborator, not your blocker.** Asking the user is the work, not an interruption of the work.

2. **Verbatim is a virtue.** Copy commands exactly. Quote output exactly. Preserve whitespace in diffs. The precision is what makes mismatches diagnosable.

3. **Time-box nothing on your own authority.** If a test is taking a long time, ask the user whether to continue waiting. Don't unilaterally abort.

4. **Local-only means local-only.** Even if credentials for a cloud environment are available in the session, do not use them. If the user wants cloud verification, that is a different (and currently unsupported) skill.

5. **Keep the feedback loop tight.** Report each test's result before moving to the next. Don't batch results across many tests — the user should be able to interrupt at any point with full context on where you are.

6. **Do not run cleanup unilaterally.** The verification doc's cleanup steps only run when the user explicitly asks. A halted run should leave the environment in its halted state so the user can investigate.

7. **Treat the verification doc as read-only by default.** Edits require explicit user approval per Phase 3.
