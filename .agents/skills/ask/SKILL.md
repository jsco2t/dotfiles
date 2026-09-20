---
name: ask
description: Answer questions through read-only codebase inspection and research. Use for explanations, factual research, codebase questions, and analysis that must not change files or external state.
---

# Ask

## Inputs

- A question or topic.
- Optional codebase paths, source material, constraints, or caller-provided context.

When delegated, treat supplied context and prior decisions as authoritative. Ask only for information that is both missing and necessary.

## Requirements and Skill Boundaries

- Stay read-only. Do not create, edit, delete, commit, push, post, or otherwise change local or external state.
- Read files and run non-mutating inspection commands when useful.
- Browse when the user requests it or when current, niche, high-stakes, or source-specific facts require verification.
- Answer honestly even when the evidence conflicts with the user's premise.
- Distinguish verified facts, reasonable inferences, and unresolved uncertainty.
- Cite code with file and line references and web research with direct source links.

## Core Skill Process

1. Identify the exact question, scope, and required level of detail.
2. Inspect relevant local code, documentation, history, or supplied artifacts.
3. Research external sources when needed, preferring primary and authoritative sources.
4. Check the evidence for contradictions, missing context, and time-sensitive assumptions.
5. Lead with the direct answer, then explain the evidence and practical implications.

## Output Formatting

Use only the sections that improve clarity:

```markdown
## Answer

[Direct answer]

## Details

[Evidence-backed explanation]

## Related Context

[Useful implications, alternatives, or pitfalls]

## Sources

[Local file references and external links]
```

Report missing access, incomplete evidence, and unresolved questions explicitly. Never hide uncertainty behind a confident conclusion.
