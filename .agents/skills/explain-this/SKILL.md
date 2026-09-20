---
name: explain-this
description: Analyze and explain a file, directory, current working directory, or Git change by tracing relevant code paths, callers, data flow, configuration, and tests. Use when the user wants a coherent overview or asks what a local code area or commit does; do not use for code review or implementation work.
---

# Explain This

Build an evidence-grounded mental model of the target, then explain it in plain language. Optimize for understanding rather than an exhaustive inventory.

## Resolve the target

- Resolve paths relative to the directory where the skill was invoked.
- If the user gives no target, use that current directory.
- If the input names an existing file or directory, treat it as a path even if it resembles a Git ref.
- Otherwise, when the current directory is in a Git repository, try to resolve the input as a commit-ish or diff range. Accept a commit hash, tag, branch, or unambiguous range when Git can resolve it without changing the checkout.
- If the target cannot be resolved safely, report what was tried and ask for a corrected path or Git ref.

Keep the investigation read-only. Do not edit files, change branches, or modify the working tree as part of an explanation.

## Investigate

Start with a bounded survey rather than reading every file mechanically.

For a directory:

- Inspect repository guidance, manifests, high-signal documentation, entry points, module boundaries, configuration, and tests.
- Respect ignore files and normally skip generated, vendored, dependency, build-output, and binary content unless it is central to the request.
- Identify the few files that define the area's public surface and runtime behavior, then trace outward from them.

For a file:

- Determine its role before walking line by line.
- Trace important imports, callers, callees, types, state, configuration, error paths, side effects, and focused tests far enough to explain how the file participates in the larger system.
- For prose or configuration rather than source code, explain its structure, consumers, and operational effect.

For a Git change:

- Inspect metadata, file statistics, and the complete diff without checking out the revision.
- Read enough surrounding code and tests from the relevant snapshot to explain behavior, not merely restate changed lines.
- Distinguish the behavior before the change, the behavior after it, and the likely intent. Label intent as an inference unless the commit message, tests, or documentation establishes it.
- If current working-tree code is used to trace a historical change, say so when it differs materially from the target revision.

Across all target types, follow at least one representative path from an entry point or caller to the resulting output, state change, or external boundary. Prefer concrete evidence over guesses. Separate facts visible in the source from inferences about intent or runtime behavior.

## Explain

Lead with a short statement of what the target is and why it exists. Then cover the smallest useful set of topics, typically:

- the main components and their responsibilities;
- the control and data flow through a representative use case;
- important inputs, outputs, state, side effects, and failure behavior;
- how tests, configuration, or integrations constrain the behavior;
- non-obvious design choices, assumptions, or uncertainties.

Use code identifiers and clickable file references with line numbers when available. Translate implementation details into a narrative instead of presenting a raw file list or diff transcription. Include compact pseudocode or a small flow diagram only when it materially clarifies the behavior.

If the subject is too large for a useful end-to-end explanation, still provide a meaningful top-level overview and one representative trace. Then name a small set of concrete subject areas that deserve separate treatment and ask the user which one to explore next. Do not make the user choose before receiving the initial overview.
