---
name: pre-commit
description: Run repository-native lint, build, and test checks before committing. Use for preflight verification, pre-commit checks, or requests to confirm that changed code is clean without implementing fixes.
---

# Pre-Commit Checks

## Inputs

- Optional repository path; default to the current repository.
- Optional scope. Default lint to staged or changed files where supported, and build/test to the repository's normal scope.
- Optional caller-provided commands or prior results.

## Requirements and Skill Boundaries

- Run checks; do not implement fixes.
- Do not install missing tools or dependencies.
- Use repository instructions and wrappers before raw language commands.
- Run from the repository root unless project guidance says otherwise.
- Preserve tool configuration; do not add flags that override repository policy.
- Track every check as `PASS`, `FAIL`, or `SKIPPED`. A skipped phase means verification is incomplete.
- Pre-commit hooks may rewrite files by design. Detect and report every resulting change. Do not use repair flags for other tools.
- Continue from lint failures to build when useful. Skip tests when the required build fails.
- When delegated, honor supplied scope and commands and return exact commands, exit codes, mutations, and blockers.

## Core Skill Process

### 1. Discover authoritative commands

Use this priority:

1. `AGENTS.md` and repository-specific instructions; treat `CLAUDE.md` as legacy guidance when present.
2. CI workflows (`.github/workflows`, GitLab CI, Jenkins, CircleCI).
3. README/CONTRIBUTING documentation.
4. Build systems and scripts: Make, Mage, Just, Task, Cargo, Go, npm/yarn/pnpm, Python, CMake, Gradle, Maven.
5. Linter configuration and language defaults.

Inspect build files safely. Do not use `make -p`, which can execute `$(shell ...)` while parsing. Report discovered language, build system, linters, and commands before execution.

### 2. Run lint checks

Run all distinct applicable lint layers, such as pre-commit plus a repository lint target. Use language defaults only when repository tooling does not define the phase.

If `.pre-commit-config.yaml` exists:

1. capture `git status --porcelain` before the run;
2. run `pre-commit run` for the default changed/staged scope, or the explicitly requested scope;
3. capture status afterward;
4. distinguish formatter rewrites from remaining hook failures.

Fallback examples include `golangci-lint run` or `go vet ./...`, `cargo clippy -- -D warnings`, configured ESLint, and configured Ruff/Flake8.

### 3. Run the build

Prefer an explicit repository build target. Otherwise use an appropriate configured command such as `go build ./...`, `cargo build`, `npm run build`, `dotnet build`, `./gradlew build -x test`, or `mvn compile`. Mark a language with no meaningful build phase as skipped with a reason.

### 4. Run tests

Prefer the repository's test target, then its configured language test command. Do not run a placeholder npm test script. If the build failed and tests depend on it, mark tests skipped because the build failed.

### 5. Classify results

- `PASS`: command completed successfully, or a pre-commit formatter changed files and its affected hooks pass on the required rerun.
- `FAIL`: command ran and still failed.
- `SKIPPED`: no applicable phase, missing tool, missing dependency, or prerequisite failure.

If a required command exceeds the available execution window, report the timeout and the partial coverage. Continue monitoring only when the user requested it.

## Output Formatting

```markdown
## Pre-Commit Results

### Discovery

- **Instructions:** [sources used]
- **CI:** [configuration]
- **Build system:** [system]
- **Language:** [language]

### Results

| Phase | Tool | Command | Exit | Result |
|-------|------|---------|------|--------|

### Files Modified by Hooks

- `[path]` — [hook]

### Failures

- **[phase]:** [concise error and relevant output]

### Skipped

- **[phase]:** [reason]

### Verdict

[All required checks passed / failed / verification incomplete]
```

Include exact commands and exit codes. Never say “all checks passed” if any required phase failed or was skipped. If a command cannot run, name the missing tool or prerequisite and the coverage lost.
