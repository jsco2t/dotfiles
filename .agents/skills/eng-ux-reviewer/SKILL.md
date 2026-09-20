---
name: eng-ux-reviewer
description: Review the user experience produced by web, desktop, mobile, terminal, and command-line interface code. Use to assess responsiveness, accessibility, interaction reachability, conventions, discoverability, information architecture, feedback, and error states from live observation or code reconstruction.
---

# Engineering UX Reviewer

## Inputs

- Files, directory, diff range, branch, or description of the interface.
- Optional target platform, user population, screenshots, running environment, or caller-provided reconstruction.

With no explicit scope, use relevant unstaged changes, then the latest commit. Request a scope only when no user-facing change can be identified.

## Requirements and Skill Boundaries

- Review the experience the code produces, not general code quality, architecture, security, or test design.
- Mention a technical issue only when it directly creates visible user harm.
- Prefer live observation when safe and feasible. Clearly label code-based reconstruction.
- Ground every finding in a file and line, observed behavior, and a concrete user impact.
- Verify current standards before making precise compliance claims. Use WCAG 2.2 AA or the target platform's applicable guidance.
- Report only findings with confidence of 80 or higher. A clean review is valid.
- Do not edit code.
- Delegation is optional: independent review dimensions may run in parallel when agents are available, but the coordinating reviewer must reconcile them against one canonical interface reconstruction.
- When delegated, use supplied context, avoid repeated scope questions, and return findings plus reconstruction assumptions to the caller.

## Core Skill Process

### 1. Classify the surface and environment

Identify one or more surfaces:

| Surface | Typical evidence |
|---------|------------------|
| Web GUI | HTML, CSS, DOM, React/Vue/Svelte |
| Desktop GUI | Qt, GTK, Cocoa, WinUI, Electron/Tauri |
| Mobile GUI | SwiftUI, Compose, React Native, Flutter |
| TUI | curses, Bubble Tea, tview, ANSI screen control |
| CLI | argument parsing, help, stdout/stderr, exit codes |

Determine relevant constraints: viewport or terminal size, keyboard/touch model, color support, TTY versus pipe, screen readers, platform targets, and structured-output needs.

### 2. Observe or reconstruct the experience

For a runnable GUI, inspect key states and interactions: normal, narrow/wide, keyboard-only, loading, empty, success, and error. For a TUI, trace screen composition, focus, keys, resize behavior, and state transitions. For a CLI, reconstruct help, success/error output, flags, piping behavior, and exit codes.

Describe the reconstructed experience before judging it so the user can identify a mistaken model.

### 3. Review the experience

Evaluate only dimensions relevant to the surface:

#### Layout and responsiveness

- reflow, overflow, clipping, minimum dimensions, resizing, wrapping, truncation, touch targets;
- terminal width awareness and stable structured output.

#### Accessibility and reachability

- semantic labels and roles, contrast, non-color cues, screen-reader behavior, reduced motion;
- visible and logical focus, keyboard access, TUI navigation, `$NO_COLOR`, stderr, meaningful exit codes.

#### Patterns and conventions

- platform-native navigation, forms, shortcuts, modal behavior, TUI keys and help;
- predictable CLI flags, subcommands, `--help`, `--`, and composition with pipes.

#### Experience quality

- clear primary flow, useful defaults, prompt feedback, progress, loading/empty states, concise output, polish, and progressive disclosure.

#### Discoverability and transparency

- visible or hinted actions, complete help, discoverable keybindings, clear labels;
- no misleading consent, asymmetric opt-out, hidden destructive action, or trapped flow.

#### Information architecture

- hierarchy, grouping, terminology, density, navigation, cognitive load;
- sensible column order, pagination/streaming, scannable key/value output, machine-readable formats.

#### Errors and recovery

- user-language explanation, actionable recovery, correct placement and severity, preserved input;
- per-item results for batch work, retries where appropriate, stderr and exit semantics for CLI.

### 4. Score and filter findings

Use confidence as evidence strength, not severity:

- `90–100`: directly observed or unambiguous standards/interaction failure;
- `80–89`: well-supported convention or usability problem with meaningful impact;
- below `80`: omit or list only as an explicit question when missing context could materially change the review.

Classify severity separately:

- `Critical`: blocks use, accessibility, recovery, or truthfulness.
- `Important`: causes substantial friction, confusion, or convention breakage.

### 5. Integrate parallel review

When delegation is available, provide all reviewers the same scope and canonical reconstruction. Suggested independent dimensions are layout, accessibility, conventions, discoverability, information architecture, and errors. The coordinating reviewer deduplicates findings and performs the holistic experience-quality assessment.

## Output Formatting

```markdown
# UX Review

- **Scope:** [files/diff/interface]
- **Surface:** [type]
- **Basis:** [live observation or code reconstruction]

## Experience Reconstruction

[What the user sees and can do, including assumptions]

## Overall Assessment

[Excellent/good/adequate/poor, with the highest-impact improvement]

## Critical Findings

### [Finding]

- **Confidence:** [90–100]
- **Category:** [category]
- **Evidence:** `[path:line]` or observed state
- **Standard:** [reference, when applicable]
- **User impact:** [experience]
- **Recommendation:** [specific improvement]

## Important Findings

[Same shape]

## Summary

- **Critical:** [count]
- **Important:** [count]
- **Highest-impact improvement:** [one sentence]

## Review Limitations

- [unavailable runtime, missing state, or reconstruction uncertainty]
```

Omit empty severity sections and state explicitly when no high-confidence issues were found. Report access or runtime problems and explain which review areas they limit.
