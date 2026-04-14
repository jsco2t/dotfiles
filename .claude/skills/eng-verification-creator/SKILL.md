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
- What existing testdata or examples exist in the repo that tests can reference
- How authentication and authorization work for the feature
- What the compose environment provides (services, ports, default credentials)

This context is essential for writing accurate, copy-pasteable commands.

#### Step 2.3: Design Test ID Convention

Create a consistent test ID scheme for the feature. Follow the pattern from existing verification docs:

- **Local CLI:** `T01-CLI-NN` or `CLI-NNN`
- **Compose:** `T03-AREA-NN` (e.g., `T03-PROV-01`, `T03-WF-01`, `T03-SETUP-01`)
- **Kind:** `KIND-NN`
- **AWS/Cloud:** `AWS-AREA-NNN` (e.g., `AWS-PROV-001`, `AWS-VOL-001`)

Group tests by functional area within each environment (setup, CRUD, workflows, access control, migration, cleanup).

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

#### Step 3.3: Write Environment Setup Documents

Every environment folder starts with a setup document. It must include:

1. **Header block** with Suite, Purpose, Cluster Required, Estimated Time
2. **Environment Setup section** — env vars to set (`export VAR=value`), copy-pasteable
3. **Prerequisites** — tools, versions, ports, access requirements
4. **Branch verification** — confirm correct code is checked out
5. **Tool verification** — confirm required tools are installed and correct version
6. **Build steps** — build binaries and/or containers as needed
7. **Environment startup** — start compose/kind/cloud environment
8. **Health checks** — verify all services are running
9. **Authentication** — configure CLI context and log in
10. **Baseline verification** — confirm the environment is in the expected initial state
11. **Summary table** at the end

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
- When creating YAML/config files, use heredocs (`cat > /path << 'EOF'`) so they're copy-pasteable
- Capture resource IDs in env vars (`export WF_ID=$(...  -o json | jq -r '.id')`) for use in subsequent commands
- Test both happy path AND error cases (permission denied, already exists, not found)
- Include cleanup steps at the end of each document or in a dedicated cleanup document

#### Step 3.5: Write Cleanup Documents

Every environment folder ends with a cleanup document. It must:

1. Clean up test-created resources (volumes, provisioners, users, contexts) — **while the environment is still running**
2. Stop the environment (compose down, kind delete, cloud teardown)
3. Clean all local state (docker volumes, temp files, jetstream data)
4. Remove CLI contexts
5. Verify clean state (no orphaned containers, volumes, or files)
6. Use `2>/dev/null || true` for cleanup commands that may fail if resources were already deleted

### Phase 4: Validate Coverage

#### Step 4.1: Audit the Spec Coverage Matrix

Before presenting the final output, verify:

1. **Every Jira story** from the requirements registry has at least one test in the coverage matrix
2. **Every acceptance criterion** has a corresponding pass criterion in at least one test
3. **No test lacks a Spec Reference** (except cleanup and setup tests which use N/A)
4. **The cheapest environment** that can verify each requirement is used (don't test CLI parsing in Kind if it can be tested locally)

If any gaps exist, either add tests or document why the requirement cannot be verified.

#### Step 4.2: Present Summary to User

After writing all documents, present:

1. Total number of environments and documents created
2. Total number of test cases
3. The complete Spec Coverage Matrix
4. Any spec requirements that could not be verified and why
5. Suggested order for running the verification suite

Ask the user if they want any changes before finalizing.

## Document Quality Checklist

Before completing, verify every document against this checklist:

- [ ] Every command is copy-pasteable (uses env vars, not hardcoded paths)
- [ ] Every test has a Spec Reference linking to Jira
- [ ] Every test has Prerequisites listing dependencies
- [ ] Every test has explicit Pass Criteria (not just "it works")
- [ ] Expected Results include concrete output examples where possible
- [ ] Known issues and manual workarounds are documented inline
- [ ] Env vars are defined once (in setup doc) and referenced consistently
- [ ] Heredocs use `<< 'EOF'` (single-quoted to prevent variable expansion in YAML)
- [ ] Summary table at the end of every document
- [ ] Cleanup document removes all test artifacts
- [ ] README has complete Spec Coverage Matrix with every Jira story

## Important Guidelines

1. **Jira/Confluence is truth** — If the research doc says X but Jira says Y, verify with the user but default to Jira. Spec requirements are non-negotiable for verification coverage.

2. **Don't invent requirements** — Verify what the spec says, plus implementation-specific behaviors from the design doc. Don't add tests for hypothetical scenarios not implied by the spec.

3. **Match the codebase** — Use actual CLI commands, actual flag names, actual API endpoints from the code. Don't guess at command syntax — read the code or existing testdata to confirm.

4. **Explain provisioner/volume/auth semantics** — These docs are often used by people less familiar with the feature. Background sections and inline notes turn verification into education.

5. **Error tests are as important as happy path** — Permission denied, duplicate names, missing prerequisites, disabled resources — these are spec requirements too and must be verified.

6. **Keep documents self-contained within their environment** — A tester running only the compose suite should never need to reference a Kind doc. Cross-references within an environment folder are fine.

7. **Use testdata from the repo when it exists** — Check `apps/fuzzball/testdata/` and similar directories for existing test fixtures. Reference them with `$TESTDATA` env var rather than creating duplicate files.

8. **Version-specific behaviors need version-specific tests** — If the feature involves v1→v4 migration, test both v1 input and v4 output. If it involves API versioning, test both versions.
```
