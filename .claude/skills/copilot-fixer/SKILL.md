---
name: copilot-fixer
description: Triage and respond to GitHub Copilot review comments on a PR, fixing valid issues and refuting non-issues. Also handles CI pipeline failures. Use when the user mentions Copilot comments, PR review bots, or pipeline failures on a pull request.
argument-hint: "<PR URL or number, or blank to discover from current branch>"
---

# Copilot Fixer

You triage GitHub Copilot review comments on a pull request: refute non-issues with grounded technical reasoning, and fix valid issues with full quality verification. You also handle CI pipeline failures reported on the PR.

## Critical Rules

1. **Ground every judgment in code.** Read the actual source before deciding if a Copilot comment is valid or not. Never dismiss a comment based on the comment text alone.
2. **Batch fixes, run the pipeline once.** Resolve all non-issues first, then fix all valid issues and CI failures, then run the review + lint/build/test pipeline once over the combined diff. Do not cycle the full pipeline per individual fix.
3. **Refutations are public and visible to the team.** Write them as technically grounded, professional responses — not terse dismissals. These post under Jason's name.
4. **Do not proceed without a confirmed PR.** If the PR cannot be resolved from input or branch discovery, stop and ask. No guessing.

---

## Phase 1: Resolve the Pull Request

### From Arguments

$ARGUMENTS

Parse the input:

- **PR URL** (e.g., `https://github.com/org/repo/pull/123`) — extract owner, repo, and PR number.
- **PR number** (e.g., `123` or `#123`) — use the current repo context.
- **Empty / no input** — discover from the current branch (see below).

### Branch-Based Discovery

If no PR is specified:

```bash
# Get current branch
git rev-parse --abbrev-ref HEAD

# Try to find an open PR for this branch
gh pr view --json number,url,headRefName,title,state 2>/dev/null
```

If `gh pr view` fails (no PR associated with the current branch):

```bash
# Try listing PRs with this branch as head
gh pr list --head "$(git rev-parse --abbrev-ref HEAD)" --json number,url,title,state
```

**If neither approach finds a PR: STOP.** Tell the user no PR was found for the current branch and ask them to provide the PR URL. Do not guess or proceed without a confirmed PR.

### Checkout the PR Branch

Ensure the working tree is on the PR's head branch:

```bash
gh pr checkout <number>
```

This is mandatory — fixing code on the wrong branch is the worst failure mode.

---

## Phase 2: Gather Inputs

Run these in parallel to collect both Copilot comments and CI status:

### 2.1 Fetch Copilot Review Comments

Use GraphQL to fetch review threads (not individual comments), since resolving threads requires thread IDs that are only available via GraphQL:

```bash
gh api graphql -f query='
query($owner: String!, $repo: String!, $pr: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          comments(first: 10) {
            nodes {
              id
              body
              author {
                login
                ... on Bot {
                  __typename
                }
              }
              createdAt
            }
          }
        }
      }
    }
  }
}' -f owner='{owner}' -f repo='{repo}' -F pr=<number>
```

**Identify Copilot threads dynamically.** Filter for threads where the first comment's author is a Bot whose login contains `copilot`. Do not hardcode a specific bot username — the exact login may vary across organizations and over time.

Discard threads that are already resolved or outdated.

**Scope note:** Copilot may also post an overall review-summary comment on the PR (not a per-line thread). These summary comments are not review threads and cannot be resolved — they are informational. This skill targets the per-line review threads, not the summary. If a summary comment exists, ignore it.

### 2.2 Fetch CI Check Status

```bash
gh pr checks <number> --json name,state,bucket,link,completedAt
```

Identify failing checks. For each failure, extract the run ID from the `link` field and get the logs:

```bash
# Extract run ID from the link URL, then:
gh run view <run-id> --log-failed
```

### 2.3 Classify Work

After gathering both inputs, classify what needs to be done:

| Input | Action |
|-------|--------|
| Copilot threads exist, no CI failures | Triage Copilot comments only |
| CI failures exist, no Copilot threads | Fix CI failures only |
| Both exist | Triage Copilot comments AND fix CI failures |
| Neither exists | Report "PR is clean" and stop |

Report the classification to the user before proceeding.

---

## Phase 3: Triage Copilot Comments

For each unresolved Copilot thread:

### 3.1 Read the Code

Read the file at the path and line referenced by the thread. Also read sufficient surrounding context (the function, the test, the block) to understand the code's intent.

### 3.2 Assess Validity

Evaluate whether the Copilot comment identifies a real issue:

**Likely non-issues (refute):**
- The comment misunderstands the code's purpose or context
- The suggestion would break existing behavior or violate project conventions
- The issue is already handled elsewhere (e.g., error handling in a caller)
- The comment flags a stylistic preference that contradicts project conventions (check CLAUDE.md)
- The comment is about code that didn't change in this PR (Copilot sometimes flags pre-existing patterns)

**Likely valid issues (fix):**
- Genuine bug: nil dereference, off-by-one, missing error check, race condition
- Security concern: injection, missing validation, leaked secrets
- Correctness: wrong logic, missing edge case, incorrect return value
- Convention violation that Copilot correctly identified

### 3.3 Record Triage Decision

For each thread, record:
- Thread ID (for GraphQL operations)
- File path and line
- Copilot's concern (one sentence)
- Your assessment: `VALID` or `NON-ISSUE`
- Reasoning (grounded in code evidence)

Present the triage summary to the user before acting:

```
Copilot Comment Triage:
──────────────────────────────────────────
1. [path:line] — "concern summary"
   Assessment: NON-ISSUE — reason
2. [path:line] — "concern summary"
   Assessment: VALID — reason, will fix
──────────────────────────────────────────
```

---

## Phase 4: Act on Non-Issues

For each thread assessed as `NON-ISSUE`:

### 4.1 Post a Refutation Reply

Reply to the thread with a technically grounded explanation of why the comment is not an issue. Structure:

- State what the code actually does (briefly)
- Explain why Copilot's concern doesn't apply
- Reference specific code, conventions, or project patterns as evidence

Tone: professional, respectful, concise. These are visible to the team.

Use GraphQL to reply (REST `in_reply_to` requires database integer IDs, but our thread query returns opaque node IDs — use GraphQL for consistency):

```bash
gh api graphql -f query='
mutation($threadId: ID!, $body: String!) {
  addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $threadId, body: $body}) {
    comment {
      id
    }
  }
}' -f threadId="<thread_node_id>" -f body="<reply>"
```

### 4.2 Resolve the Thread

Attempt to resolve the thread via GraphQL:

```bash
gh api graphql -f query='
mutation($threadId: ID!) {
  resolveReviewThread(input: {threadId: $threadId}) {
    thread {
      isResolved
    }
  }
}' -f threadId="<thread_node_id>"
```

**If resolution fails** (insufficient permissions), note it in the final report but continue. The refutation reply is the primary deliverable; resolution is a convenience. The user's expectation is "if you have the ability."

---

## Phase 5: Fix Valid Issues and CI Failures

### 5.1 Fix Valid Copilot Issues

For each thread assessed as `VALID`:

1. Post an acknowledgment reply to the thread (same GraphQL `addPullRequestReviewThreadReply` mutation as 4.1):
   > "Valid point — this is a real issue. Fixing now."
2. Implement the fix in the working tree.
3. **Do NOT resolve the thread yet.** Valid-issue threads are resolved after a successful push (Phase 7) to avoid marking threads resolved when the fix hasn't landed on the remote. A resolved thread with no pushed commit is misleading to reviewers.

### 5.2 Fix CI Failures

For each failing check:

1. Analyze the failure logs (`gh run view <run-id> --log-failed`).
2. Identify the root cause — build error, test failure, lint violation, etc.
3. Implement the fix in the working tree.

### 5.3 Handling Ambiguity

If you're uncertain whether a Copilot comment is valid, or if a CI failure's root cause is unclear, **ask the user** rather than guessing. Present your analysis and let them decide.

---

## Phase 6: Quality Verification Pipeline

After ALL fixes are applied (both Copilot fixes and CI fixes), run the quality pipeline **once** over the combined changes. This pipeline is adapted from `/task-processor` Phase 5 and Phase 6.

### A. Code Review — General

Run `/code-reviewer` against the files changed by your fixes.

- Fix any issue with confidence >= 85%
- Note issues below 85% for the report

### B. Code Review — Project-Specific

Detect the repository and run the appropriate project-specific reviewer:

| Repository | Reviewer |
|-----------|----------|
| **Fuzzball** (`apps/fuzzball/` present) | `/fz-code-reviewer` |
| **Warewulf** (`internal/app/warewulfd/` or `warewulf` in repo name) | `/ww-code-reviewer` |
| **Other repos** | Skip — note in report |

- Fix any issue with confidence >= 82%
- Note issues below 82% for the report

### C. Test Review

If any test files were changed by fixes, run `/test-reviewer` against them.

- Fix any issue with confidence >= 85%
- Note issues below 85% for the report

### D. Linting

Run the repository's native linting tooling. Detection priority:

1. **CLAUDE.md** — use what it specifies
2. **README.md / CONTRIBUTING.md**
3. **Makefile, magefiles/, justfile, package.json**
4. Language defaults as last resort

| Repository | Lint Command |
|-----------|-------------|
| **Fuzzball** | `pre-commit run --all-files` |
| **Substrate** | Check README/CLAUDE.md; typically `mage lint` |
| **Other Go** | `golangci-lint run` |
| **Other** | Detect from project config |

Fix all lint errors. Re-run until clean.

### E. Building

Run the repository's native build tooling:

| Repository | Build Commands |
|-----------|---------------|
| **Fuzzball** | `fuzzy generate` then `fuzzy build binary` |
| **Substrate** | Check README/CLAUDE.md; typically `mage build` |
| **Other Go** | `go build ./...` |
| **Other** | Detect from project config |

Fix all build errors. Re-run until clean.

### F. Testing

Run the repository's native test tooling:

| Repository | Test Command |
|-----------|-------------|
| **Fuzzball** | `fuzzy test unit` |
| **Substrate** | Check README/CLAUDE.md; typically `mage test` |
| **Other Go** | `go test ./...` |
| **Other** | Detect from project config |

Fix all test failures. Re-run until all tests pass.

---

## Phase 7: Commit and Push

### 7.1 Commit the Fixes

Stage and commit all changes with a descriptive message:

```bash
git add <specific files changed>
git commit -m "$(cat <<'EOF'
Fix Copilot review findings and CI failures

- [list each fix briefly]
EOF
)"
```

If only Copilot fixes were made, use: `"Address Copilot review feedback"`
If only CI fixes were made, use: `"Fix CI pipeline failures"`
Tailor the message to what was actually done.

### 7.2 Push

Push the changes to the remote branch:

```bash
git push
```

**This is a state-changing, teammate-visible action.** The push updates the PR that others may be watching. This is the intended behavior of this skill — the user invoked it to autonomously fix and push — but be aware of the visibility.

### 7.3 Resolve Valid-Issue Threads

Now that the fix is pushed, resolve the threads for issues assessed as `VALID` (same GraphQL `resolveReviewThread` mutation as Phase 4.2). This ordering ensures threads are only marked resolved after the fix is live on the remote.

---

## Phase 8: Report

Present a structured report:

```markdown
# Copilot Fixer Report: PR #[number]

## PR
- **Title:** [title]
- **Branch:** [branch]
- **URL:** [url]

## Copilot Comment Triage

| # | File:Line | Concern | Assessment | Action |
|---|-----------|---------|------------|--------|
| 1 | path:42   | concern | NON-ISSUE  | Refuted + resolved |
| 2 | path:87   | concern | VALID      | Fixed + resolved |

## CI Failures

| Check | Status | Action |
|-------|--------|--------|
| build | FAIL   | Fixed (missing import) |
| tests | PASS   | — |

## Quality Pipeline Results

| Step | Status | Details |
|------|--------|---------|
| A. Code Review (general) | PASS/FAIL | X found, Y fixed |
| B. Code Review (project) | PASS/FAIL | X found, Y fixed |
| C. Test Review | PASS/SKIP | details |
| D. Linting | PASS/FAIL | details |
| E. Building | PASS/FAIL | details |
| F. Testing | PASS/FAIL | details |

## Commit

- **SHA:** [short sha]
- **Message:** [commit message]
- **Pushed:** Yes/No

## Files Changed

[list of files]

## Notes

[Any observations, remaining items, or concerns]
```

---

## Error Handling

### If No Copilot Comments and No CI Failures

Report that the PR is clean. Do not fabricate work.

### If a Fix Introduces New Failures

If your fix breaks the build or tests, fix the regression before pushing. If you cannot resolve it after 2 attempts, **stop and ask the user** rather than pushing broken code.

### If GraphQL Thread Resolution Fails

Leave the refutation reply in place and note in the report that thread resolution requires elevated permissions. The reply is the substantive deliverable.

### If the Pipeline Cannot Be Detected

If you cannot determine the repo's lint/build/test tooling, ask the user. Do not skip the pipeline silently.
