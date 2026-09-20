---
name: eng-verification-creator
description: Create a complete manual verification suite from an engineering plan, approved design, and authoritative Jira/Confluence requirements. Use to map every requirement to copy-pasteable tests, organize coverage by cheapest suitable environment, create self-contained fixtures and documents, and produce a spec coverage matrix for human or delegated execution. Supports direct requests and delegated/chained workflows.
---

# Engineering Verification Creator

Create manual verification documents that a human or `$eng-verification-runner` can execute literally. The suite must prove specification coverage and expose gaps rather than smoothing them over.

## Inputs

Require:

1. Engineering research/implementation plan path.
2. Approved engineering design path.
3. Output directory.

Also accept a feature/index path, Jira or Confluence sources, branch/revision, environment constraints, approved scope decisions, and caller-provided requirements or output conventions.

When delegated, honor all supplied paths, decisions, and constraints. Do not repeat answered questions. If a required input cannot be inferred from an index or caller context, return the missing-input blocker before writing files.

## Requirements and Skill Boundaries

- Treat current Jira and Confluence requirements as authoritative when available. Report source conflicts; do not silently resolve them.
- Map every requirement and acceptance criterion to at least one test and binary pass criterion, or explicitly document why it cannot be verified.
- Add implementation-driven error and edge cases only when supported by the design or code. Do not invent product requirements.
- Use the cheapest environment that proves the behavior: Local CLI, Compose, Binary + Compose, Kind, then cloud.
- Confirm that each feature exists in an environment before assigning tests there.
- Make commands copy-pasteable and verify CLI names, flags, output fields, and workflow behavior against current source code.
- Make local and Compose documents self-contained and order-independent: environment setup, authentication, resources, tests, and teardown in one document.
- Allow shared `00-*-environment-setup.md` and `99-*-environment-teardown.md` only for genuinely expensive environments such as cloud deployments or multi-node Kind setups taking 10+ minutes. Each test document must still own its feature resources.
- Every document must clean up what it creates. Teardown runs while services still exist; Compose documents then stop their own stack.
- Put immutable inputs in a checked-in `fixtures/` directory beside the suite. Put runtime files in `scratch/`. Never use `/tmp`, `$TMPDIR`, or inline heredocs to create fixture files.
- Reuse fixtures before extending them; extend before creating new ones. Copy reused source-repository testdata into the suite so it is self-contained.
- Keep each test single-purpose and each document roughly 5-30 minutes where practical.
- Explain non-obvious commands, flags, feature semantics, known issues, and manual diagnostic paths.
- Never write a workflow-wide `events --follow` for a non-terminating service. Follow a terminating stage or poll, then stop the workflow explicitly.
- Cloud documents may be created, but `$eng-verification-runner` is local-only. Mark cloud documents for human execution or an explicitly cloud-authorized runner.
- Follow `AGENTS.md`; use `CLAUDE.md` only as legacy repository guidance when relevant.
- A delegated invocation must return structured completion, approval-needed, or blocker status.

## Core Skill Process

### 1. Build the requirements registry

Read the plan and design fully. Extract feature requirements, acceptance criteria, Jira keys, Confluence links, architectural decisions, APIs, CLI changes, schemas, migrations, compatibility behavior, errors, and edge cases.

Use the available Atlassian connector to fetch referenced Jira issues and Confluence pages. Include issue descriptions, acceptance criteria, relevant comments, epic children, linked constraints, examples, and Q&A decisions. If direct access is unavailable, use the local documents and report that source verification was not possible.

Create a registry:

```markdown
| Source | Requirement | Acceptance Criteria | Notes/Conflicts |
| --- | --- | --- | --- |
| FUZZ-XXXX | [Requirement] | [Testable criteria] | [Notes] |
```

Cross-check sources. Surface missing and conflicting requirements for resolution before committing affected tests.

### 2. Inspect the implementation surface

Read current code to confirm:

- CLI hierarchy, exact flags, output formats, and JSON field casing.
- Workflow start, event-follow, log, stop, and error behavior.
- APIs, authentication, authorization, configuration, and resource lifecycle.
- Compose services, ports, credentials, and feature availability.
- Kind operators, CRDs, storage, scheduling, and environment variants.
- Cloud-specific drivers, accounts, networking, and credentials.

Record a CLI conventions table and apply it consistently. Do not copy syntax from older verification docs without checking source.

### 3. Inventory fixtures

Search source testdata (including `apps/fuzzball/testdata/` and feature subdirectories) and existing verification-suite `fixtures/` directories. Record each fixture's path, purpose, and applicable requirements.

For every needed fixture:

1. Reuse an existing fixture unchanged.
2. Extend an existing fixture only when it will not break other consumers.
3. Create a new fixture only when neither option works; justify it in the test background.

Copy all suite inputs into `<output>/fixtures/<type>/`. Deduplicate identical content. Rename collisions by environment or variant. Use `<output>/scratch/` for runtime output and require teardown to remove it.

### 4. Design scope and coverage

Assign each requirement to the cheapest suitable environment:

- **Local CLI:** parsing, help, template generation, offline transforms, version behavior.
- **Compose:** APIs, CRUD, auth, workflows, and lightweight end-to-end behavior.
- **Binary + Compose:** server-side debugging or iteration that materially benefits from a local binary.
- **Kind:** Kubernetes operators, CRDs, PVCs, node scheduling, and cluster-specific behavior.
- **Cloud:** cloud drivers, multi-node distributed behavior, real identity/networking, and upgrade/migration cases.

Choose only environments that add distinct value. Define environment-specific test IDs:

- Compose: `MVT-CC-AREA-NN`
- Kind: `MVT-KD-AREA-NN`
- AWS: `AWS-AREA-NN`
- Azure: `AZ-AREA-NN`
- GCP: `GCP-AREA-NN`
- Local CLI: `MVT-CLI-AREA-NN`

Use short functional AREA codes such as `PROV`, `VOL`, `WF`, `AC`, `OWN`, `NFS`, `SEG`, `CLI`, `DT`, or `EP`.

Present the proposed environments, documents, test IDs, coverage mapping, and unverifiable requirements for approval. If the caller already supplied an approved structure, use it. Otherwise pause with `approval-needed` before writing the suite.

### 5. Write the suite

Create `README.md`, environment folders, documents, fixtures, and optional `scratch/`. The README must include the source links, folder index, execution guidance, and complete spec coverage matrix.

Every verification document must use this exact order:

1. Title and metadata.
2. AI runner guidance.
3. `## Environment Variables` (exports only).
4. `## Prerequisites` for local/Compose/Kind, or `## Environment Setup` for cloud.
5. Tests at H2, in document order.
6. `## Teardown`.
7. `## Summary` table.

Tests use H2; their subsections use H3. Optional group labels must be non-heading separators. Preserve legitimate environment-specific sections such as Pre-Test Orphan Rescue, credential warnings, multi-account variables, and substrate inspection notes.

### 6. Use consistent command patterns

Use source-verified variants of these patterns:

```bash
# Workflow execute and verify
export WF_ID=$($fb workflow start "$FIXTURES/workflows/<fixture>.yaml" --name <name> -o json | jq -r '.ID')
$fb workflow events "$WF_ID" --follow
$fb workflow log "$WF_ID" <job-name>

# Persistent service: follow a terminating stage, verify, then stop
export WF_ID=$($fb workflow start "$FIXTURES/workflows/<fixture>.yaml" --name <name> -o json | jq -r '.ID')
$fb workflow events "$WF_ID" <verify-stage> --follow
# verification commands
$fb workflow stop "$WF_ID"

# Expected failure: capture both streams and assert non-zero exit
<command> 2>&1

# Idempotent setup/teardown
$fb <resource> <create-command> <args> 2>/dev/null || true
$fb <resource> <delete-command> <args> -y 2>/dev/null || true
```

Expected-error pass criteria must assert a non-zero exit and relevant error text. CRUD tests must verify create/add, list/info, state transitions, and cleanup where those behaviors are in scope. Capture resource IDs in variables for later commands.

### 7. Audit and reconcile

Before completion, verify:

- Every registry requirement appears in the coverage matrix.
- Every acceptance criterion maps to a concrete pass criterion.
- Every test has all required fields and a valid Spec Reference or `N/A`.
- Each `$FIXTURES/...` path exists; no suite document uses temp paths.
- CLI commands match source and remain consistent across documents.
- Every persistent workflow has safe monitoring and explicit stop.
- Every document can start from its declared baseline and clean up independently, except the allowed expensive-environment setup boundary.

If `<output>/index.md` exists, update it with `README.md`, environment folders, descriptions, and `Last Updated`. If invoked standalone, update a parent feature index only when it already exists and no orchestrator owns reconciliation. Otherwise report that it was intentionally left to the caller.

## Output Formatting

Use this README structure:

```markdown
# [Feature Name] Manual Verification Tests

**Feature:** [Feature and Jira epics]
**Branch/Revision:** [Branch or commit]
**Last Updated:** [Date]
**Spec:** [Jira and Confluence links]

## Overview

[Scope, environments, and execution guidance]

## Test Folders

### [01-folder-name/](./01-folder-name/) - [Environment]

[Purpose]

| # | File | What It Tests |
| --- | --- | --- |
| 1 | `01-file.md` | [Summary] |

## Spec Coverage Matrix

| Source | Requirement | [Environment 1] | [Environment 2] | Notes |
| --- | --- | --- | --- | --- |
| FUZZ-XXXX | [Requirement] | [Test IDs] | [Test IDs] | [Gap or None] |

## Tips and Known Issues

[Diagnostics, workarounds, and important semantics]
```

Use this exact document/test schema:

````markdown
# NN - Document Title (Environment Name)

**Suite:** <folder-name>
**Purpose:** <what this document verifies>
**Estimated Time:** <minutes>

> **AI Verification Runner Guidance**
> This document is designed for a human or `$eng-verification-runner`.
> - Execute every test and command in order; do not batch or shortcut them.
> - HALT on any mismatch, ambiguity, or undocumented result.
> - Capture output and compare it with Expected Result and every Pass Criterion.
> - On macOS, local environment access may require sandbox approval.
> - Use `$fb workflow events $WF_ID --follow` for terminating workflows; scope persistent services to a terminating stage and stop them explicitly.
> - Cloud tests require credentials and cannot be run by the local-only `$eng-verification-runner`.

## Environment Variables

```bash
export FUZZBALL_REPO="<absolute-path>"
export FIXTURES="<absolute-suite-path>/fixtures"
export fb="<source-verified-command-or-path>"
```

## Prerequisites

[Tools, build/start, authentication, document-owned resources, and baseline checks with exact commands]

## TEST-ID: Test Title

**Spec Reference:** FUZZ-NNNN ([requirement summary])
**Prerequisite:** Prerequisites above | [test IDs]
**Purpose:** [Single behavior and why it matters]

### Background

[Optional explanation]

### Setup

[Optional test-specific creation commands]

### Steps

1. [Action]:

   ```bash
   command
   ```

### Expected Result

- [Specific observable output or state]

### Pass Criteria

- [ ] [Binary check]

### Cleanup

[Optional test-specific cleanup]

## Teardown

[Document resource cleanup, scratch cleanup, and environment shutdown when owned]

## Summary

| Test ID | Description | Depends On |
| --- | --- | --- |
| [ID] | [Description] | [Dependencies] |
````

`Background`, per-test `Setup`, and per-test `Cleanup` are optional. All other displayed fields and sections are required. `Expected Result` describes what happens; `Pass Criteria` converts those observations into binary checks. Derive missing expected results from existing pass criteria rather than inventing new expectations.

Report to the user or caller with:

- `Status`: `complete`, `approval-needed`, `partial`, or `blocked`.
- `Outputs`: README, environment folders, document count, test count, fixtures, and indexes changed.
- `Coverage`: the complete source-to-test matrix and any unverifiable requirements.
- `Environments`: why each was selected and the recommended execution order.
- `Validation`: schema, fixture, CLI, lifecycle, and coverage audit results.
- `Problems`: source conflicts, unavailable connectors, unsupported environments, missing fixtures, or uncertain commands; use `None` when empty.
- `Next skill`: `$eng-verification-runner` for approved local documents; cloud documents require an explicitly authorized execution path.

For a blocker, state the exact missing input, approval, source conflict, or unverifiable command; list completed work and written files; and name the minimum decision or access needed. Never fabricate coverage or silently weaken a test to claim completion.
