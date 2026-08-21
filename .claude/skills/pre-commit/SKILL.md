---
name: pre-commit
description: Run pre-flight lint, build, and test checks before committing code. Discovers the repository's own tooling (pre-commit, make, mage, cargo, go, npm, etc.) and runs checks using native build systems. Use when the user asks to "run pre-commit", "preflight check", "verify before committing", "run lint build test", or "check my changes are clean".
argument-hint: "[scope] — defaults to changed files for lint, full project for build/test"
---

# Pre-Commit Preflight Checks

Run lint, build, and test checks against the current repository using its native tooling. This skill is language-agnostic and repo-agnostic — it discovers what to run rather than assuming a specific stack.

## Outcome Model

Every phase produces one of three outcomes:

- **PASS** — the check ran and succeeded (exit 0)
- **FAIL** — the check ran and failed (exit non-zero)
- **SKIPPED** — no tooling found, or tool not installed (exit 127 / command not found)

**Critical rule**: never summarize as "all checks passed" if any phase was SKIPPED. A skip means coverage is incomplete, not that the code is clean. Report skips prominently.

## Phase 0: Discovery

Before running anything, discover the repository's tooling. Check sources in this priority order:

### 1. CLAUDE.md / Project Instructions

Read `CLAUDE.md` (and any nested CLAUDE.md files) at the repo root. These often name the authoritative lint/build/test commands. If explicit commands are specified, they take precedence over auto-discovery for that phase.

### 2. CI Workflows

Read `.github/workflows/*.yml` (or `.gitlab-ci.yml`, `Jenkinsfile`, `.circleci/config.yml`). CI definitions are the highest-signal answer to "what does this repo consider lint/build/test." Mirror what CI actually runs when build-system targets are ambiguous.

### 3. Build System Detection

Check for these at the repo root:

| File | System | How to list targets |
|------|--------|-------------------|
| `Makefile` / `GNUmakefile` | make | Grep the file for `.PHONY` lines and `^[a-zA-Z0-9_.-]+:` patterns. Try `make help` if a `help` target exists. **Do NOT use `make -p`** — it evaluates `$(shell ...)` at parse time and can execute arbitrary commands. |
| `Magefile.go` / `magefile.go` | mage | `mage -l` (safe list command) |
| `Justfile` | just | `just --list` |
| `Taskfile.yml` | task | `task --list` |
| `Cargo.toml` | cargo | Built-in targets (clippy, build, test) |
| `go.mod` | go | Built-in tools (vet, build, test) |
| `package.json` | npm/yarn | Read `scripts` section from the file |
| `pyproject.toml` / `setup.py` | python | Check for configured tools (ruff, pytest, etc.) |
| `CMakeLists.txt` | cmake | cmake build |
| `build.gradle` / `build.gradle.kts` | gradle | `./gradlew tasks --quiet` |
| `pom.xml` | maven | Built-in phases (compile, test) |

### 4. Linter Config Detection

| Config file | Tool |
|-------------|------|
| `.pre-commit-config.yaml` | pre-commit framework |
| `.golangci.yml` / `.golangci.yaml` / `.golangci.toml` | golangci-lint (subsumes `go vet` — prefer this when present) |
| `.eslintrc*` / `eslint.config.*` | ESLint |
| `.rustfmt.toml` / `clippy.toml` | rustfmt / clippy |
| `.flake8` / ruff config in `pyproject.toml` | Python linters |
| `.rubocop.yml` | RuboCop |

### 5. Language Detection (fallback)

If no build system provides clear targets, detect the primary language from manifest files (`go.mod`, `Cargo.toml`, `package.json`, `pyproject.toml`, etc.) and use language-default tooling.

After discovery, log what was found before proceeding.

## Phase 1: Lint

**Scope**: default to changed/staged files, not the full tree. Full-tree lint on a large repo surfaces failures in files the user never touched. Use `--all-files` only if the user explicitly asks.

Run ALL applicable linting tools found (they may cover different checks):

### 1a. pre-commit (if `.pre-commit-config.yaml` exists)

```
git stash list  # note stash state
git status --porcelain > /tmp/pre-status.txt
pre-commit run  # runs on staged files by default
git status --porcelain > /tmp/post-status.txt
diff /tmp/pre-status.txt /tmp/post-status.txt
```

**Important**: pre-commit hooks like `trailing-whitespace`, `end-of-file-fixer`, `black`, `isort`, and `gofmt` rewrite files by design and exit non-zero when they do. After running pre-commit, compare `git status --porcelain` before and after, and report exactly which files were modified. This is expected behavior — report the rewrites clearly but do not treat auto-formatting as a skill failure.

If the `pre-commit` command is not found (exit 127), mark as SKIPPED — do not install it.

### 1b. Build system lint target

If the build system has a `lint` target, run it **even if pre-commit also ran**:
- `make lint`
- `mage lint`
- `just lint`
- `task lint`

### 1c. Language-specific linter (fallback — only if neither 1a nor 1b produced a lint check)

- **Go**: `golangci-lint run` if config exists, otherwise `go vet ./...`
- **Rust**: `cargo clippy -- -D warnings`
- **JS/TS**: `npx eslint .` if config exists
- **Python**: `ruff check .` or `flake8` if config exists

**Lint failure records FAIL but does NOT abort.** Continue to build phase — the test result is usually what matters most.

## Phase 2: Build

Run the first applicable build command:

### 2a. Build system target
- `make build` (prefer explicit `build` target; fall back to default target only if `build` exists)
- `mage build`
- `just build`
- `task build`

### 2b. Language-specific build (fallback)
- **Go**: `go build ./...`
- **Rust**: `cargo build`
- **JS/TS**: `npm run build` (only if `build` script exists in package.json)
- **Python**: typically no build step — mark SKIPPED with reason "Python: no compilation step"
- **C#**: `dotnet build`
- **Java/Gradle**: `./gradlew build -x test`
- **Java/Maven**: `mvn compile`

**Build failure aborts the test phase** — tests can't pass without a successful build. Record FAIL and skip tests with reason "build failed."

## Phase 3: Test

Run the first applicable test command:

### 3a. Build system target
- `make test`
- `mage test`
- `just test`
- `task test`

### 3b. Language-specific test (fallback)
- **Go**: `go test ./...`
- **Rust**: `cargo test`
- **JS/TS**: `npm test` (only if `test` script exists and isn't the default `"echo \"Error: no test specified\" && exit 1"`)
- **Python**: `pytest` if installed, otherwise `python -m unittest discover`
- **C#**: `dotnet test`
- **Java/Gradle**: `./gradlew test`
- **Java/Maven**: `mvn test`

## Reporting

After all phases complete, report results in this format:

```
## Pre-Commit Results

### Discovery
- CLAUDE.md commands: [found / not found]
- CI config: [what was found, if anything]
- Build system: [make / mage / cargo / go / npm / none]
- Linters: [pre-commit, golangci-lint, etc.]
- Language: [Go, Rust, TypeScript, etc.]

### Results
| Phase | Tool | Command | Exit | Result |
|-------|------|---------|------|--------|
| Lint | pre-commit | `pre-commit run` | 1 | PASS (reformatted 2 files) |
| Lint | make | `make lint` | 0 | PASS |
| Build | go | `go build ./...` | 0 | PASS |
| Test | go | `go test ./...` | 1 | FAIL |

### Files Modified by Linters
- `pkg/foo/bar.go` (gofmt)
- `internal/baz/qux.go` (trailing whitespace)

### Failures
[exact error output for any FAIL results]

### Skipped
[list any SKIPPED phases with reasons]
```

Include the **exact command** and **exit code** per row so the user can rerun by hand.

## Rules

1. **Do not install tools.** If a tool is not installed (command not found / exit 127), mark SKIPPED with a warning. Never run `pip install`, `npm install -g`, `go install`, `brew install`, etc.
2. **Do not fix code.** Never pass `--fix`, `--write`, or auto-repair flags to linters. The pre-commit framework may rewrite files as part of its design — that's the exception; report what it changed. All other tools run in check-only mode.
3. **Run from the repository root.** All commands execute from the repo root directory.
4. **Missing tool is SKIPPED, not FAIL.** A tool referenced in config but not installed is a skip, not a failure. Be clear about the distinction.
5. **Respect existing config.** If a tool has a config file in the repo (`.golangci.yml`, `.eslintrc`, etc.), do not pass flags that override it.
6. **Long-running tests.** If a test suite takes more than 5 minutes, warn and ask before continuing. If the user provided a scope hint, respect it.
