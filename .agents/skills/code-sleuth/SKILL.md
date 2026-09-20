---
name: code-sleuth
description: Investigate how code behaves, trace component interactions, find root causes, reconstruct design intent, and assess change impact using evidence from the codebase. Use for debugging, behavioral traces, dependency analysis, design forensics, and “why does this work this way?” questions.
---

# Code Sleuth

## Inputs

- Investigation question.
- Optional code locations, symptoms, reproduction details, constraints, and output path.
- Optional caller-provided project context or prior findings.

Use the current repository when it is clearly the intended codebase. Ask for a location only when it cannot be inferred safely. Default to a chat response; write a report only when requested, when an output path is supplied, or when the investigation is too large for a useful chat answer.

## Requirements and Skill Boundaries

- Ground every conclusion in inspected code, tests, configuration, logs, or history.
- Label unverified theories as hypotheses and state what would confirm them.
- Trace beyond the symptom to entry points, transformations, boundaries, state, and failure propagation.
- Look for counter-evidence before accepting a theory.
- Keep the investigation focused on the question. Do not implement fixes unless explicitly asked.
- Treat tests as evidence of intended behavior, not proof that production behavior is correct.
- Use version history when it materially explains intent or regression timing.
- When delegated, reuse supplied context and return findings, evidence, confidence, and blockers in a form the caller can consume.

## Core Skill Process

### 1. Frame the investigation

Classify the primary goal:

| Type | Goal |
|------|------|
| Bug hunt | Find the divergence and root cause |
| Interaction map | Explain boundaries, data exchange, coupling, and failure propagation |
| Change impact | Find direct and transitive dependents and contracts at risk |
| Behavioral trace | Follow execution, branches, side effects, and errors end to end |
| Design forensics | Reconstruct intent from structure, history, and comparable code |

State any scope assumption that materially affects the result.

### 2. Establish the baseline

- Identify languages, frameworks, build system, project instructions, and module layout.
- Find entry points, core types, interfaces, configuration, and tests.
- Determine expected behavior and the contracts between components.

### 3. Build the mental model

Trace control and data from entry to completion. Record:

- transformations and decision points;
- shared state, persistence, caches, and configuration;
- subsystem boundaries and returned errors;
- ordering, nil/empty, concurrency, environment, and type assumptions;
- direct and hidden coupling.

### 4. Test the explanation

For a bug, locate the first divergence between expected and actual behavior and search for sibling defects. For impact analysis, follow direct references, interface consumers, and transitive dependents. For design forensics, compare similar subsystems and inspect relevant history.

Try to disprove the leading explanation. Check edge cases and note missing coverage.

### 5. Synthesize

Lead with the finding. Then show the evidence chain, explain why the behavior occurs, state implications, and assign confidence.

## Output Formatting

For a focused answer:

```markdown
## Finding

[Direct answer and confidence]

## Evidence Chain

1. `[file:line]` — [what it proves]

## Why It Happens

[Root cause or interaction model]

## Implications

[Impact and useful next steps]
```

For a written report, add only useful sections from: `Mental Model`, `Component Map`, `Data Flow`, `Key Contracts`, `Investigation Detail`, `Confidence Assessment`, `Open Questions`, `Recommendations`, and `Evidence Log`.

Each finding must include its evidence and confidence. Report access failures, incomplete traces, conflicting evidence, and unresolved questions explicitly, including what would resolve them.
