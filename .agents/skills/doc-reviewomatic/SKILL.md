---
name: doc-reviewomatic
description: Multi-perspective documentation review for local changes and GitHub PRs. Use to review documentation accuracy, commands, examples, readability, grammar, frontmatter, structure, and house-style consistency; post inline PR comments; resolve this skill's prior comments; or scan for doc-only PRs.
---

# Doc Review-O-Matic

Review documentation through technical accuracy, language quality, and structural consistency. Verify claims against the real system and keep feedback constructive.

## Inputs

Accept:

- `mode`: `local`, `review`, `resolve`, or `scan`.
- `scope`: documentation paths, a diff, commit or range, branch changes, staged changes, or unstaged changes.
- `pr-ref`: PR URL, number, or `#number`; omit to discover from the current branch.
- `--auto-comment`: post all reportable findings without another selection step.
- `--confidence=N`: threshold; default 80.
- Caller-provided source context, sibling examples, style guidance, diff-visible lines, prior findings, or authorization.

Infer `review` from a PR reference and `local` otherwise. Ask only if ambiguity changes the result. In delegated use, accept supplied scope and decisions without asking again.

For local mode without a scope, prefer branch changes against `main` or `origin/main`, then staged and unstaged changes. Report an empty documentation scope plainly.

## Requirements and Skill Boundaries

- Review documentation only; do not edit files.
- Include `.md`, `.mdx`, `.rst`, `.txt`, `.adoc`, `.asciidoc`, and documentation content under project-specific docs directories. Exclude code and configuration unless needed to verify a documentation claim.
- Posting, replying, and resolving on GitHub require explicit authorization unless `--auto-comment` or delegated authorization applies.
- Anchor inline PR findings to changed documentation lines. Read surrounding prose and referenced source for context.
- Resolve only threads marked `<!-- doc-reviewomatic -->`.
- Read applicable `AGENTS.md`; treat `CLAUDE.md` only as legacy repository guidance.
- Read at least one relevant sibling document before reporting a structural or style inconsistency.
- Verify commands, keys, APIs, links, and feature claims against authoritative local source whenever possible.
- Report only findings at or above the active threshold. A clean review is valid.
- Keep PR comments respectful and provide replacement text when practical.
- Return complete results to the direct user or delegating caller.

### GitHub access (load on demand)

Uses the local GitHub toolkit (`ghtk`, stdlib-only, works in-sandbox — no sandbox bypass needed). Full reference: `~/.local/bin/github-toolkit/README.md` (read only when needed). **Below, `ghtk` is shorthand for `python3 "$HOME/.local/bin/github-toolkit/ghtk"`** — invoke it by that explicit path. Add `--json` for machine-readable output.

```bash
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr get [PR_REF]
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr threads PR_NUMBER --unresolved-only --mine-only --marker '<!-- doc-reviewomatic -->' --include-outdated
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr comment PR_NUMBER --comments-file /path/to/comments.json --marker '<!-- doc-reviewomatic -->'
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr reply THREAD_ID --body "reply"
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr resolve THREAD_ID
python3 "$HOME/.local/bin/github-toolkit/ghtk" pr scan --drop-drafts --file-glob '*.md' --file-glob '*.mdx' --file-glob '*.rst' --file-glob '*.adoc' --file-glob '*.asciidoc'
```

## Core Skill Process

### 1. Gather documentation scope

Use the supplied local scope. Common commands:

```bash
git diff main...HEAD
git diff
git diff --cached
git diff main...HEAD -- path/to/file.md
```

Filter the result to documentation files. If none remain, report that there is nothing to review and stop.

For `review` or `resolve`, discover the PR (`ghtk pr get`), save its metadata, fetch `ghtk pr diff PR_NUMBER`, and filter to documentation. In resolve mode fetch owned unresolved threads with `ghtk pr threads PR_NUMBER --unresolved-only --mine-only --marker '<!-- doc-reviewomatic -->' --include-outdated`.

For `scan`, run `ghtk pr scan --drop-drafts --all-files-match --file-glob '*.md' --file-glob '*.mdx' --file-glob '*.rst' --file-glob '*.adoc' --file-glob '*.asciidoc'`. Present doc-only PRs and their files, then review one at a time. Ask before each unless the caller authorized queue processing.

### 2. Establish the documentation baseline

Read repository guidance and at least one sibling for each affected documentation area. Capture local frontmatter, heading, shortcode, link, tone, terminology, and file-placement conventions.

Read relevant code, schemas, help text, API definitions, configuration types, or build configuration needed to verify claims. In PR modes, collect diff-visible `(file, line)` anchors.

### 3. Apply three perspectives

#### A. Technical Accuracy

Check:

- CLI commands, subcommands, flags, arguments, and realistic output.
- YAML/JSON keys and value types, environment variables, APIs, protobuf/OpenAPI references, and version constraints.
- Internal links, glossary terms, feature availability, deprecation state, and prerequisites.
- Syntax and completeness of code, configuration, and workflow examples.
- Consistent, correct technical terminology.

Do not accept plausible prose as proof. Trace each substantive claim to the actual implementation or authoritative project definition.

#### B. Readability & Language

Check:

- Clear context → action → result flow and one main idea per paragraph.
- Grammar, spelling, punctuation, capitalization, and correct inline-code formatting.
- Professional, direct, accessible tone without condescension or unsupported marketing language.
- Concise sentences, unambiguous pronouns, parallel headings, scannable procedures, and visible prerequisites or warnings.

Do not report purely subjective rewrites. Show how the current text can mislead, slow, or confuse the intended reader.

#### C. Structure & Consistency

Check against sibling documents:

- Required frontmatter fields, nesting, types, and formats.
- Heading hierarchy, section ordering, index files, file naming, placement, and weights.
- Link, image, shortcode, admonition, table, and code-fence conventions.
- Static-site generator and documentation-linter compatibility.
- Project-specific line wrapping, trailing whitespace, and final-newline rules.

Do not assume a universal frontmatter schema; derive requirements from the project.

### 4. Delegate and consolidate

If subagents are available and delegation is allowed, run one agent per perspective in parallel. Give each agent the documentation scope, relevant source, sibling samples, project guidance, threshold, and PR line constraints. Tell each to review only, not re-delegate, and return file/line, category, evidence, reader impact, exact fix when possible, and confidence.

Otherwise perform all perspectives directly. Verify findings, remove pre-existing or preference-only issues, and merge duplicates.

Confidence:

- 90–100: verified breakage or materially false guidance.
- 80–89: well-supported issue likely to affect readers or builds.
- 70–79: include only when the threshold was lowered.
- Below 70: omit.

### 5. Post authorized comments

In `review` or `scan`, show the report first. Post only authorized findings; `--auto-comment` authorizes all findings at or above threshold.

```json
[{"path":"file.md","line":42,"body":"comment text"}]
```

Run `ghtk pr comment PR_NUMBER --comments-file <file> --marker '<!-- doc-reviewomatic -->'`. Explain reader or build impact and provide corrected prose, YAML, or commands. The `--marker` value `<!-- doc-reviewomatic -->` is prefixed to every comment body.

### 6. Resolve owned comments

Read current documentation and replies for each owned thread. Classify it as `Addressed`, `Addressed differently`, `Declined with rationale`, or `Still open`. Present planned actions before mutation unless already authorized. Resolve addressed issues, acknowledge alternate fixes or reasoned declines before resolving, and leave open issues unresolved.

## Output Formatting

### Review report

```markdown
# Documentation Review Report

**Scope:** [scope]
**Threshold:** [N]

### Critical
### [Finding title]
- **File:** path:line
- **Confidence:** N
- **Reviewer:** [A, B, or C]
- **Category:** [concern]
- **Issue:** [evidence and reader/build impact]
- **Suggestion:** [exact replacement when possible]

### Important
[same fields]

### Summary
- **Total findings:** N
- **Critical:** N
- **Important:** N
- **Perspectives applied:** A, B, C
```

If no finding meets the threshold, say so directly.

After posting, report PR, count, review URL when available, and each posted file/line/category/confidence. After resolution, report reviewed, replied, resolved, left open, and failed counts.

For errors, report the failed operation and exact error, completed work, whether results are partial, and the safe next action. Ask for a PR reference if discovery fails; report empty scans or empty documentation scopes plainly; continue past isolated thread failures and list them.
