---
name: eng-verification-creator
description: Creates manual verification test documents from an engineering implementation plan and design document. Fetches spec requirements from Jira/Confluence as the source of truth, maps every requirement to concrete verification steps, organizes tests by deployment environment (cheapest-first), and produces copy-paste-ready documents with spec coverage matrix.
argument-hint: "<path to eng-implementation-plan.md> <path to engineering-design.md> <output directory>"
---

# Engineering Verification Creator Skill

You are creating a comprehensive set of manual verification test documents for a feature. Your goal is to produce documents that a developer or QA engineer can follow step-by-step to verify every aspect of a feature works correctly end-to-end.

**The specifications in Jira and Confluence are the authoritative source of truth.** Every requirement, acceptance criterion, and behavioral specification called out in those documents MUST have corresponding verification tests. Additional verifications beyond the spec are expected — but spec compliance coverage is mandatory and must be demonstrably complete.

## Input

The user has provided the following context:

$ARGUMENTS

You need three inputs. If any are missing, ask the user:

1. **Engineering implementation plan** (eng-implementation-plan.md) — the "what and why"
2. **Engineering design document** (engineering-design.md) — the "how"
3. **Output directory** — where to write the verification documents

## Guiding Principles

These principles are non-negotiable. Every verification document must satisfy them:

1. **Spec compliance is mandatory, not optional.** Every requirement in Jira/Confluence MUST have at least one verification test in at least one environment. The Spec Coverage Matrix in the README is the accountability layer that proves this. If a spec requirement cannot be verified, document why explicitly.

2. **Cheapest feedback first.** Organize verification environments from simplest to most complex. A CLI-only test that catches a bug in 2 minutes is better than a Kind test that catches the same bug in 30 minutes. Always verify in the easiest environment first, then expand to more complex environments for behaviors that require infrastructure.

3. **Copy-paste or it didn't happen.** Every command must be directly copy-pasteable into a terminal. Use environment variables (set once, referenced everywhere), heredocs for multi-line content, and shell aliases for long binary paths. A tester should never have to edit a command before running it.

4. **Manual fallbacks for everything.** Automated checks fail. Services don't start. Bootstrap races. Every verification must include what to do when the happy path doesn't work — manual creation steps, diagnostic commands, known issues with workarounds.

5. **Small documents, clear progression.** Break each environment's verifications into numbered documents that build on each other. Each document should be completable in 5-30 minutes. The first document is always environment setup; the last is always cleanup. Group related verifications together in the same document.

6. **Explain the "why", not just the "what".** When a test uses a specific provisioner, explain why. When a command needs a flag, explain what happens without it. When a known issue exists, explain the root cause. The tester should understand the feature, not just follow steps.

7. **Documents are self contained** EVERY verification document must understand how to configure the environment for testing AND clean everything up for testing. **DO NOT** create verification documents which are just "setup" or "cleanup". Leave the system under test in the same state as when you found it.

8. **Verification Document Conventions**:
   - Every document can setup and cleanup after itself.
   - Verification documents do not rely on the order in which the documents are ran.
   - Do NOT use the temp directory for test fixtures — check them into the repository.
   - If the output of one command needs to be used as the input to another command then capture that as a variable.

9. **Test fixtures live beside the verification docs, not in temp.** Create a `fixtures/` directory beside (or within) the verification environment folders. Organize by type: `fixtures/provisioners/`, `fixtures/workflows/`, `fixtures/segments/`, etc. Reference via a `$FIXTURES` environment variable set to the fully qualified path. NEVER write fixtures to `/tmp`, `$TMPDIR`, or any temporary directory. NEVER create ad-hoc YAML fixtures inline via heredocs written to temp files — if a test needs a YAML fixture, it must be a checked-in file in the `fixtures/` directory.

10. **Consistent CLI patterns.** Before writing any verification document, verify the actual CLI conventions against the source code. Lock these into a conventions table and apply uniformly across ALL documents:
    - Binary alias (e.g., `$fb` for `fuzzball`)
    - Workflow termination command (`stop` vs `cancel` — check which exists)
    - Event following flag (`--follow` vs `--watch` — check which is canonical)
    - JSON output field casing (e.g., `.ID` vs `.id` — check the proto/CLI source)
    - Idempotent resource creation pattern (e.g., `2>/dev/null || true`)
    Do NOT copy conventions from existing docs — they may be stale. Check the source.

11. **Service workflow events safety.** When a workflow contains a `persist: true` service (or any non-terminating workload), `events --follow` on the workflow will hang forever. For these workflows:
    - If the workflow has a `depends-on` verify job, follow that specific stage: `$fb workflow events $WF_ID verify-internal --follow`
    - If no verify job exists, poll workflow status instead of following events
    - ALWAYS include an explicit `$fb workflow stop` after verifying a service workflow
    Never write a step that says "press Ctrl-C" or requires manual interruption.

12. **Verify feature availability per level.** Before placing a test at a given environment level, confirm the feature is actually available there. Check compose configs for service availability (e.g., object cache, service proxy). Check Kind configs for environment types (e.g., segmented). Do not write tests for features that aren't present at that level.

13. **Human and AI executable.** Every document must be runnable by a human or by the `/eng-verification-runner` skill. Include an AI guidance header at the top of every verification document:
    ```
    > **AI Verification Runner Guidance**
    > This document is designed to be executed by a human or by the `/eng-verification-runner` skill.
    > - Execute steps sequentially within each test. HALT on any mismatch.
    > - Capture all command outputs and compare against Expected Results exactly.
    > - On MacOS, you may need to leave the sandbox to interact with the system under test.
    > - Use `$fb workflow events $WF_ID --follow` to monitor workflow execution (not --watch or describe --watch).
    ```
    For cloud-level docs, add a note that cloud tests require credentials and the runner skill cannot execute them directly.

14. **Simple, single-minded tests.** Each test should verify ONE thing clearly. Don't combine multiple unrelated verifications into a single test. Optimize for the number of tests that accurately verify product functionality — do NOT optimize for the fewest possible tests.

15. **Cloud environment exception.** The ONLY exception to the self-sufficiency rule (Principle 7) is cloud environments. Cloud environments MAY use a single setup document (`00-*-environment-setup.md`) and teardown document (`99-*-environment-teardown.md`) because deploying cloud infrastructure is expensive and slow. All other docs within that cloud environment assume the cluster is deployed but must be self-sufficient for everything else (provisioners, volumes, users, groups).

16. **Multi-account cloud configuration.** Cloud verification docs must provide environment variables for ALL required cloud accounts. For AWS, this typically means both a nonprod/test account AND a marketplace/container account. Include both in the env var block of every cloud doc.

## Document Schema (Mandatory Structure)

Every verification document MUST follow this exact structure. Deviations create inconsistency between documents and increase variance during test execution. The runner skill depends on this structure for mechanical execution.

### Document-Level Structure

Every document follows this section order. All sections are required unless marked optional.

```
# NN - Document Title (Environment Name)

**Suite:** <folder-name>
**Purpose:** <what this document verifies>
**Estimated Time:** <minutes>

> **AI Verification Runner Guidance**
> [Standard header — see AI Guidance Header below]

---

## Environment Variables              ← required, exports only

---

## Prerequisites                     ← required (local envs) or ## Environment Setup (cloud envs)

---

[Test cases — see Test Case Structure]

---

## Teardown                           ← required, always named "Teardown"

---

## Summary                            ← required, table of all tests
```

**Section naming rules (no alternatives):**
- `## Environment Variables` — never "Environment Setup" for the export block
- `## Prerequisites` — for compose/kind docs (build, start, authenticate, doc-specific setup)
- `## Environment Setup` — for cloud docs only (auth, discovery, resource creation beyond cluster deploy)
- `## Teardown` — never "Cleanup" or "Document Cleanup"
- `## Summary` — always a table

### Test Case Structure

Every test case MUST have these sections in this exact order. All are required unless marked optional.

```
## TEST-ID: Test Title

**Spec Reference:** FUZZ-NNNN (requirement summary)
**Prerequisite:** <previous test IDs, or "Prerequisites above">
**Purpose:** <what specifically this test verifies and why>

### Background                        ← optional, only when the test needs conceptual explanation

### Setup                             ← optional, only when the test needs per-test resource creation

### Steps

1. Step description:
   ```bash
   command
   ```

### Expected Result

- <specific, observable outcomes>

### Pass Criteria

- [ ] <precise, unambiguous checkboxes>

### Cleanup                           ← optional, only when per-test cleanup is needed beyond doc Teardown
```

**Required fields — no test may omit these:**
- `**Spec Reference:**` — Jira key or `N/A` for non-spec tests
- `**Prerequisite:**` — dependency chain or "Prerequisites above"
- `**Purpose:**` — one sentence explaining what and why
- `### Steps` — at least one numbered step with a bash code block
- `### Expected Result` — narrative description of what should happen
- `### Pass Criteria` — `- [ ]` checkboxes for binary pass/fail evaluation

**Expected Result vs. Pass Criteria — the distinction matters:**
- **Expected Result** describes *what should happen* in narrative form (e.g., "Workflow reaches Finished. Log contains `hello from compose`.")
- **Pass Criteria** are *binary checkboxes* that the runner evaluates mechanically (e.g., `- [ ] Workflow status is Finished`, `- [ ] Log contains 'hello from compose'`)
- When writing Expected Result for a test that previously lacked one, derive it from the Pass Criteria — restate the checkboxes as the observable outcome. Do not invent new expectations.

### Test ID Conventions

Test IDs follow a consistent scheme per environment:

- **Compose:** `MVT-CC-AREA-NN` (e.g., `MVT-CC-PROV-01`, `MVT-CC-VOL-01`)
- **Kind:** `MVT-KD-AREA-NN` (e.g., `MVT-KD-STG-01`, `MVT-KD-SEG-01`)
- **AWS:** `AWS-AREA-NN` (e.g., `AWS-PROV-01`, `AWS-VOL-01`)
- **Azure:** `AZ-AREA-NN` (e.g., `AZ-OWN-01`)
- **GCP:** `GCP-AREA-NN`

Within each environment, AREA codes are short functional domains: PROV (provisioner), VOL (volume), WF (workflow), AC (access control), OWN (ownership), NFS, SEG (segmentation), CLI, DT (data transfer), EP (endpoints), etc.

### Test Grouping (Optional)

When a document contains logically distinct groups of tests (e.g., "Core CRUD" vs. "Validation"), use a non-heading visual separator:

```markdown
---

**Part A: Group Title**

---
```

Do NOT use `##` headings for Part groupings — `##` is reserved for test case headings and document-level sections. Part separators are organizational aids, not structural elements.

### AI Guidance Header

Every document includes this blockquote immediately after the metadata block. Use this exact text for local environment docs:

```markdown
> **AI Verification Runner Guidance**
> This document is designed to be executed by a human or by the `/eng-verification-runner` skill.
> - **Quality over speed.** Do **NOT** compress, batch, or shortcut these tests. The goal is to verify product quality, not to finish quickly. Execute every command exactly as written and evaluate every result against the pass criteria.
> - **Parallel execution.** Running tests in sub-agents in parallel is acceptable only when the test objectives have **NO** overlap in the resources they create, modify, or verify.
> - Execute steps sequentially within each test. HALT on any mismatch.
> - Capture all command outputs and compare against Expected Results exactly.
> - On MacOS, you may need to leave the sandbox to interact with the system under test.
> - Use `$fb workflow events $WF_ID --follow` to monitor workflow execution (not --watch or describe --watch).
```

For cloud environment docs, append:

```markdown
> - AWS/Azure/GCP tests require cloud credentials. The verification runner skill CANNOT execute cloud tests directly. These tests are designed for human execution or for an AI runner with explicit cloud access.
```

### Environment-Specific Sections

Some environments require additional sections that don't apply universally. These are permitted and should NOT be stripped during normalization:

- **Pre-Test Orphan Rescue** — cloud docs may include this before tests to clean up resources leaked by prior failed runs
- **Cloud credential warnings** — additional guidance header lines for cloud docs
- **Multi-account env blocks** — AWS docs may export variables for multiple accounts (nonprod + marketplace)
- **Substrate inspection notes** — docs testing container internals may add `docker exec` or `kubectl exec` guidance

These are functional content, not formatting variance. Preserve them.

## Standardized Test Patterns

When writing test commands, use these exact patterns. The runner skill recognizes them and executes them mechanically, reducing deliberation about *how* to run a step. The runner still compares output against Expected Result and Pass Criteria with full rigor — patterns speed up execution, not evaluation.

### Pattern: Workflow Execute-and-Verify

For tests that submit a workflow and verify it completes successfully:

```bash
export WF_ID=$($fb workflow start $FIXTURES/workflows/<fixture>.yaml --name <name> -o json | jq -r '.ID')
$fb workflow events $WF_ID --follow
$fb workflow log $WF_ID <job-name>
```

### Pattern: Service Workflow Verify-and-Stop

For tests with `persist: true` services that don't terminate on their own:

```bash
export WF_ID=$($fb workflow start $FIXTURES/workflows/<fixture>.yaml --name <name> -o json | jq -r '.ID')
$fb workflow events $WF_ID <verify-job-name> --follow
# ... verification commands ...
$fb workflow stop $WF_ID
```

Never use `events --follow` without a stage scope on a service workflow — it will hang.

### Pattern: Expected Error

For tests where a command SHOULD fail:

```bash
<command> 2>&1
```

Pass Criteria for expected-error tests MUST include at minimum:
- `- [ ] Exit code is non-zero`
- `- [ ] Error message contains '<expected text>'`

### Pattern: Provisioner CRUD

Add and verify:
```bash
$fb volume provisioner add <name> -f $FIXTURES/provisioners/<fixture>.yaml
$fb volume provisioner list
```

Inspect:
```bash
$fb volume provisioner info <name> -o json
```

Remove:
```bash
$fb volume provisioner remove <name> -y
```

### Pattern: Volume Lifecycle

Create:
```bash
$fb volume create <provisioner> <volume-name> [--size <size>]
$fb volume list --provisioner <provisioner>
```

Cleanup (disable then delete):
```bash
$fb volume disable <provisioner> <volume-name>
$fb volume delete <provisioner> <volume-name> -y
```

### Pattern: User Context Switch

Switch to a different user, perform actions, then switch back:

```bash
$fb context use <target-context>
$fb context login --direct -u <user> -p <password> --insecure
# ... actions as this user ...
$fb context use <original-context>
$fb context login --direct -u <original-user> -p <original-password> --insecure
```

### Pattern: Idempotent Resource Creation

For setup blocks that may run against an environment with leftover resources:

```bash
$fb <resource> <create-command> <args> 2>/dev/null || true
```

### Pattern: Teardown Resource Deletion

For cleanup blocks where resources may already be gone:

```bash
$fb <resource> <delete-command> <args> -y 2>/dev/null || true
```

## Verification Creation Process

### Phase 1: Gather Spec Requirements (Source of Truth)

This phase establishes the mandatory verification baseline. Everything in this phase MUST be covered.

#### Step 1.1: Read Input Documents

Read both the engineering implementation plan and design document thoroughly. Extract:

- Feature requirements and acceptance criteria
- Jira story keys and their titles
- Confluence page references
- Architecture decisions and their implications
- API changes, CLI changes, schema changes
- Migration behaviors and backward compatibility requirements
- Error cases and edge cases called out in the design

#### Step 1.2: Fetch Jira Issues

For every Jira issue referenced in the input documents, use MCP tools to fetch the full details:

- Use `mcp__claude_ai_Atlassian__getJiraIssue` (or `mcp__claude_ai_Atlassian_2__getJiraIssue`) to fetch each issue
- Extract: summary, description, acceptance criteria, comments with decisions
- Follow epic links to find child stories that may have additional requirements
- Check for linked issues that add constraints or dependencies

**Build a requirements registry** — a structured list of every spec requirement with its Jira source:

```
| Jira Key   | Requirement Summary                        | Acceptance Criteria (extracted)           |
|------------|--------------------------------------------|------------------------------------------|
| FUZZ-XXXX  | [from issue summary]                       | [specific testable criteria from issue]   |
```

If MCP tools are unavailable, extract requirements from what's documented in the research and design documents, but warn the user that direct Jira verification was not performed.

#### Step 1.3: Fetch Confluence Pages

For every Confluence page referenced in the input documents:

- Use `mcp__claude_ai_Atlassian__getConfluencePage` (or `mcp__claude_ai_Atlassian_2__getConfluencePage`) to fetch page content
- Extract behavioral specifications, examples, Q&A decisions, and edge cases
- These often contain the most detailed and specific requirements (e.g., "always try to migrate", "default-deny semantics")
- Pay special attention to examples sections — these often define exact expected behavior

Add any additional requirements from Confluence to the requirements registry.

#### Step 1.4: Cross-Reference and Validate

Compare requirements from Jira, Confluence, the research doc, and the design doc:

- Identify any requirements in Jira/Confluence NOT mentioned in the research/design docs — these still need verification
- Identify design decisions that have testable implications (e.g., "default-deny means empty access lists = no access")
- Flag any conflicting requirements between sources for the user to resolve

### Phase 2: Analyze Verification Scope

#### Step 2.1: Categorize Requirements by Verification Environment

For each requirement in the registry, determine which deployment environment(s) can verify it:

**Environment hierarchy (cheapest first):**

1. **Local CLI** — No cluster needed. Tests CLI command hierarchy, help text, template generation, offline transformations, YAML parsing, version behavior. Use when the feature has CLI-only aspects.

2. **Docker Compose** (`fuzzy compose`) — Lightweight full-stack. Tests API interactions, CRUD operations, workflow submission, authentication, basic end-to-end flows. Use when you need a running backend but not Kubernetes-specific features. **This is usually faster than Kind** and should be preferred for most functional tests.

3. **Binary + Compose** — Same as compose but runs the main service as a local binary. Use when tests benefit from debugger attachment, real-time stdout, or fast iteration without container rebuilds. Only include this environment if the feature has complex server-side behavior worth debugging.

4. **Kind** (local Kubernetes) — Full Kubernetes environment. Tests operator behavior, CRD interactions, multi-node scenarios, Kubernetes-specific storage (PVC driver), node scheduling. Use when the feature requires Kubernetes primitives.

5. **Cloud (AWS/GCP/Azure)** — Production-like environment. Tests cloud-specific drivers (EFS/NFS), multi-node distributed storage, real authentication (Keycloak), cloud networking, migration from existing deployments. Use when the feature has cloud-specific behavior or you need to verify production-like conditions.

Not every feature needs every environment. Include only environments that add verification value. Most features need at minimum Local CLI (if CLI changes) + one server environment (usually Compose).

#### Step 2.2: Study Codebase for Test Context

Use the Explore agent or direct file searches to understand:

- What CLI commands exist for the feature (command hierarchy, flags, output formats)
- What APIs are involved (gRPC services, REST endpoints)
- What configuration is needed (YAML files, environment variables, contexts)
- How authentication and authorization work for the feature
- What the compose environment provides (services, ports, default credentials)

This context is essential for writing accurate, copy-pasteable commands.

#### Step 2.2a: Enumerate Existing Testdata and Plan Fixtures (Required)

**Before proposing any new test fixtures, you MUST inventory what already exists.** The goal is reuse first, extend second, create new only as a last resort.

1. Search for existing fixtures in TWO places:
   - **Source repo testdata**: `apps/fuzzball/testdata/` (and feature-specific subdirectories like `storage/v4/`)
   - **Existing verification suites**: any `fixtures/` directories in prior verification docs for the same project

2. For every fixture found, record: path, what it exercises, and which spec requirement(s) it could cover.

3. When planning each test case, apply this decision order:
   1. **Reuse** — use an existing fixture unchanged (preferred)
   2. **Extend** — add a field/variant to an existing fixture if the change doesn't break other tests
   3. **Create new** — only when no existing fixture fits; justify in the test's Background section

4. **Fixture placement**: ALL fixtures used by verification docs MUST live in a `fixtures/` directory beside the verification documents — NOT in temp directories, NOT only in the source repo's testdata. This makes the verification suite self-contained.

   - Create `fixtures/` in the output directory with subdirectories by type: `fixtures/provisioners/`, `fixtures/workflows/`, `fixtures/segments/`, etc.
   - **Copy** reused fixtures from the source repo into `fixtures/` so the verification suite doesn't depend on having the repo checked out at a specific path.
   - Reference all fixtures via a `$FIXTURES` environment variable pointing to this directory.
   - If a new fixture is also useful for unit tests, add it to `apps/fuzzball/testdata/` in the source repo as well — but the verification suite's copy is the primary reference.

5. **Deduplication**: If copying fixtures from multiple sources, deduplicate by content. Same filename + same content → single copy. Same filename + different content → suffix with the environment or variant name (e.g., `wf-unsegmented-kind.yaml` vs `wf-unsegmented.yaml`).

6. **Runtime working files**: If a test must write a file to disk (e.g., downloading an object for round-trip verification), use a `scratch/` directory beside `fixtures/` (NOT inside it). The `fixtures/` directory is strictly read-only input; `scratch/` is for runtime output that tests create and clean up.

#### Step 2.3: Design Test ID Convention

Use the conventions defined in the Document Schema section (Test ID Conventions). Group tests by functional area within each environment (setup, CRUD, workflows, access control, migration, cleanup).

### Phase 3: Write Verification Documents

#### Step 3.1: Plan the Document Structure

Before writing, present the planned structure to the user for approval:

Use AskUserQuestion to present:

1. Which environments will be included and why
2. How many documents per environment
3. The test ID convention
4. The spec coverage matrix (which Jira stories map to which tests)
5. Any spec requirements that cannot be verified and why

Wait for user approval before writing documents. The user may want to add environments, adjust groupings, or clarify requirements.

#### Step 3.2: Write the README.md

The README is the entry point. It must contain:

```markdown
# [Feature Name] Manual Verification Tests

**Feature:** [Feature name and Jira epic keys]
**Branch:** [Branch name from research doc]
**Last Updated:** [Today's date]
**Spec:** [Links to Confluence pages] | [Links to Jira epics]

---

## Overview

[1-2 paragraphs describing what this verification suite covers and how it's organized]

**Start with the environment that matches your setup. Tests within each folder are numbered and should be run in order.**

---

## Test Folders

### [01-folder-name/](./01-folder-name/) — [Environment Description]

[1-2 sentences describing what this environment tests and when to use it]

| # | File         | What it Tests |
| - | ------------ | ------------- |
| 1 | `01-file.md` | [Summary]     |
| 2 | `02-file.md` | [Summary]     |

---

[Repeat for each environment folder...]

---

## Spec Coverage Matrix

Each test maps to a Jira story. This matrix shows which tests cover which spec requirements.

| Jira      | Requirement   | [Env1]     | [Env2]     | [Env3]     |
| --------- | ------------- | ---------- | ---------- | ---------- |
| FUZZ-XXXX | [Requirement] | [Test IDs] | [Test IDs] | [Test IDs] |

---

## Tips

[Feature-specific tips for testers: debugging, common flags, log locations, etc.]
```

**The Spec Coverage Matrix is mandatory.** Every Jira story from the requirements registry must appear in this matrix with at least one test reference. If a story cannot be verified in any environment, it must appear with a note explaining why.

#### Step 3.3: Write Environment Setup

Each verification document is self-sufficient and includes its own setup and teardown (Principle 7). However, include a shared **Environment Setup** section pattern that every document in an environment folder replicates:

1. **Environment Variables** — `export` block with `$fb`, `$FIXTURES`, `$FUZZBALL_REPO`, and environment-specific vars
2. **Prerequisites** — tools, versions, ports, access requirements
3. **Build and start** — build binaries/containers, start compose/kind environment
4. **Authentication** — configure CLI context and log in
5. **Baseline verification** — confirm the environment is in the expected initial state

Each document repeats this pattern so it can be run independently.

**Cloud environment exception (Principle 15):** For cloud environments (AWS/Azure/GCP), deploying infrastructure is too expensive to repeat per-document. Cloud environments MAY have a dedicated `00-*-environment-setup.md` that deploys the cluster and a `99-*-environment-teardown.md` that destroys it. All other cloud docs assume the cluster is deployed but must be self-sufficient for everything else (creating their own provisioners, volumes, users, groups, and cleaning them up).

Include known issues and manual workarounds (e.g., bootstrap race conditions, macOS-specific limitations, port conflicts).

#### Step 3.4: Write Feature Verification Documents

Each verification document covers a functional area. Follow this structure for every document:

````markdown
# NN - [Document Title]

**Suite**: [folder name]
**Purpose**: [What this document verifies]
**Estimated Time**: [minutes]

> **Required:** Environment variables from `01-environment-setup.md` "Environment Setup" section are set (`$VAR1`, `$VAR2`, `$alias`).

---

## [TEST-ID]: [Test Title]

**Spec Reference**: [Jira key(s)] ([requirement summary])
**Prerequisite**: [Previous test IDs that must pass first]
**Purpose**: [What specifically this test verifies and why it matters]

### Background (if needed)

[Explain concepts, architecture, or behavior being tested — helps tester understand what they're verifying]

### Steps

1. [Step with copy-pasteable command]
   ```bash
   command here
   ```
````

> **Note:** [Explain why this command/flag/value is used]

2. [Next step]
   ```bash
   next command
   ```

### Expected Result

- [Specific, observable outcomes]
- [Include example output where helpful]

### Pass Criteria

- [Precise, unambiguous criteria — can be used as checkboxes]

---

[Repeat for each test case...]

---

## Summary

| Test ID | Description   | Depends On     |
| ------- | ------------- | -------------- |
| [ID]    | [Description] | [Dependencies] |

```
**Rules for writing test cases:**

- Every test MUST have a `Spec Reference` line linking to the Jira story it verifies. Tests that verify non-spec behaviors (e.g., debugging support, cleanup) use `Spec Reference: N/A`
- Commands must use env vars, not hardcoded paths. Set vars once in the setup doc, reference everywhere
- Include `> **Note:**` blocks to explain non-obvious flags, workarounds, or context
- Include `> **Known Issue:**` blocks for bugs or limitations the tester will encounter
- YAML/config fixtures MUST be checked-in files in `fixtures/`, referenced via `$FIXTURES`. Do NOT use heredocs to create fixture files at runtime — the fixture must exist before the test runs
- Capture resource IDs in env vars (`export WF_ID=$(...  -o json | jq -r '.ID')`) for use in subsequent commands. Verify the JSON field casing (`.ID` vs `.id`) against the source code
- Test both happy path AND error cases (permission denied, already exists, not found)
- Include cleanup steps at the end of each document or in a dedicated cleanup document

#### Step 3.5: Write Teardown Sections

Every verification document includes its own teardown section at the end (Principle 7). The teardown must:

1. Clean up test-created resources (volumes, provisioners, users, contexts) — **while the environment is still running**
2. Use `2>/dev/null || true` for cleanup commands that may fail if resources were already deleted
3. Leave the environment in the same state it was found in (other documents may run after this one)

**Do NOT create standalone cleanup-only documents** (except for cloud environment teardown per Principle 15).

For compose/kind environments, include environment shutdown (compose down, kind cleanup) at the end of each document's teardown section — since each document is self-sufficient, it starts and stops its own environment.

### Phase 4: Validate Coverage

#### Step 4.1: Audit the Spec Coverage Matrix

Before presenting the final output, verify:

1. **Every Jira story** from the requirements registry has at least one test in the coverage matrix
2. **Every acceptance criterion** has a corresponding pass criterion in at least one test
3. **No test lacks a Spec Reference** (except cleanup and setup tests which use N/A)
4. **The cheapest environment** that can verify each requirement is used (don't test CLI parsing in Kind if it can be tested locally)

If any gaps exist, either add tests or document why the requirement cannot be verified.

#### Step 4.2: Update Parent Index (if present)

If the output directory sits inside a `/new-eng-feature`-style documentation tree, the parent scaffold will contain an `index.md` that must stay in sync with what you just wrote. Check for and update these:

1. **`<output-directory>/index.md`** (the verifications folder index) — if it exists, refresh it to list:
   - `README.md` (the suite overview you just wrote)
   - Every environment folder and its documents, with short descriptions
   - A `Last Updated:` timestamp

2. **`<output-directory>/../index.md`** (the feature root index) — if it exists and has a row for verifications, update that row's status/link if needed. Do not rewrite unrelated rows.

If neither index exists, the skill was invoked standalone outside the orchestrator — skip this step and note it in the final summary so the user knows no parent indexes were touched.

**When the orchestrator (`/new-eng-feature` or `/eng-feature-followup`) invokes this skill, it performs its own post-skill index reconciliation. Do not duplicate that work — a simple refresh of `<output-directory>/index.md` is sufficient; the orchestrator will handle the root.**

#### Step 4.3: Present Summary to User

After writing all documents, present:

1. Total number of environments and documents created
2. Total number of test cases
3. The complete Spec Coverage Matrix
4. Any spec requirements that could not be verified and why
5. Suggested order for running the verification suite

Ask the user if they want any changes before finalizing.

## Document Quality Checklist

Before completing, verify every document against this checklist:

### Schema Compliance
- [ ] Document follows the exact section order from Document Schema
- [ ] Tests are at H2 (`##`), subsections at H3 (`###`) — no H3 tests with H4 subsections
- [ ] Part groupings use non-heading separators, not `##` headings
- [ ] Teardown section is named `## Teardown` (not "Cleanup" or "Document Cleanup")
- [ ] Environment variables section is named `## Environment Variables`
- [ ] Every test has all required fields: Spec Reference, Prerequisite, Purpose, Steps, Expected Result, Pass Criteria
- [ ] Test IDs follow the convention for their environment (MVT-CC-*, MVT-KD-*, AWS-*, AZ-*)
- [ ] AI guidance header uses the standardized text from the schema

### Structure & Content
- [ ] Every command is copy-pasteable (uses env vars, not hardcoded paths)
- [ ] Every test has a Spec Reference linking to Jira
- [ ] Every test has Prerequisites listing dependencies
- [ ] Every test has explicit Pass Criteria (not just "it works")
- [ ] Every test has an Expected Result section (distinct from Pass Criteria)
- [ ] Expected Results include concrete output examples where possible
- [ ] Known issues and manual workarounds are documented inline
- [ ] Env vars are defined once and referenced consistently
- [ ] Summary table at the end of every document
- [ ] README has complete Spec Coverage Matrix with every Jira story

### Self-Sufficiency
- [ ] Every document has its own setup section (can run independently)
- [ ] Every document has its own teardown section (cleans up after itself)
- [ ] No document says "see doc X for prerequisites" (except cloud setup doc)
- [ ] No document depends on running other docs first

### Fixtures & Files
- [ ] ALL fixtures are in the `fixtures/` directory (not in `/tmp`, not inline heredocs to temp)
- [ ] Every `$FIXTURES/...` reference points to a file that exists
- [ ] Runtime working files use `scratch/` not `fixtures/`
- [ ] No `/tmp` or `$TMPDIR` usage anywhere in any document

### CLI Consistency
- [ ] CLI conventions verified against source code (not copied from old docs)
- [ ] Same binary alias used throughout (e.g., `$fb`)
- [ ] Same workflow monitoring pattern used throughout (`events --follow`)
- [ ] Same JSON field casing used throughout (e.g., `.ID`)
- [ ] No `events --follow` on non-terminating service workflows without stage scoping
- [ ] Every service/persist workflow has an explicit `$fb workflow stop` after verification
- [ ] No "press Ctrl-C" steps

### AI Executability
- [ ] AI guidance header at the top of every verification document
- [ ] MacOS sandbox note included in guidance header
- [ ] Cloud docs note that runner skill cannot execute cloud tests directly

## Important Guidelines

1. **Jira/Confluence is truth** — If the research doc says X but Jira says Y, verify with the user but default to Jira. Spec requirements are non-negotiable for verification coverage.

2. **Don't invent requirements** — Verify what the spec says, plus implementation-specific behaviors from the design doc. Don't add tests for hypothetical scenarios not implied by the spec.

3. **Match the codebase** — Use actual CLI commands, actual flag names, actual API endpoints from the code. Don't guess at command syntax — read the code or existing testdata to confirm.

4. **Explain provisioner/volume/auth semantics** — These docs are often used by people less familiar with the feature. Background sections and inline notes turn verification into education.

5. **Error tests are as important as happy path** — Permission denied, duplicate names, missing prerequisites, disabled resources — these are spec requirements too and must be verified.

6. **Keep documents self-contained within their environment** — A tester running only the compose suite should never need to reference a Kind doc. Cross-references within an environment folder are fine.

7. **Reuse checked-in testdata — don't grow the tree** — Phase 2.2a enumeration is required. Prefer existing fixtures (reuse → extend → create new, in that order). Copy reused fixtures into the verification suite's `fixtures/` directory so the suite is self-contained. Reference fixtures via `$FIXTURES`, not hardcoded paths or `$TESTDATA`.

8. **Version-specific behaviors need version-specific tests** — If the feature involves v1→v4 migration, test both v1 input and v4 output. If it involves API versioning, test both versions.

9. **Verify CLI conventions against source code** — Do not copy CLI syntax from existing docs or from memory. Before writing any commands, read the actual CLI source code to confirm: command names, flag names, output field casing, and available subcommands. CLI conventions change between releases; stale syntax creates broken tests.

10. **Never use /tmp for anything** — No temp files for fixtures, no temp files for intermediate output, no heredocs writing YAML to temp paths. Fixtures go in `fixtures/`. Runtime output goes in variables or `scratch/`. This is non-negotiable.

11. **Events --follow on services will hang** — Service workflows with `persist: true` never terminate. Using `events --follow` without scoping to a terminating stage will cause the test runner (human or AI) to hang indefinitely. Always scope to the verify job stage or use polling for services.
```
