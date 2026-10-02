---
name: arch-plan-reviewer
description: "Review an engineering plan for architectural soundness before implementation, with concrete risks, candidate designs, and trade-offs. Optionally compare against supplied source conventions. Report only; use arch-reviewer for implemented code."
---

# Architecture Plan Reviewer

Accept a plan path, optional source paths, and `--max-agents=N`. Read the complete
plan. Ask only for a missing plan or an ambiguity that changes the review.
Do not edit the plan or source.

Extract objectives, scope, proposed components, decisions, task order, tests,
risks, exclusions, and open questions. When source paths are provided, read
applicable `AGENTS.md` and sample relevant code and siblings to establish the
baseline. Otherwise review from requirements and language idioms and disclose
that conventions were not checked. An established pattern is not a defect solely
because another architecture is preferred.

Evaluate these dimensions separately:

1. Separation of concerns and component ownership.
2. Testability, explicit dependencies, and useful isolation boundaries.
3. Dependency direction, coupling, and ripple effects.
4. Abstraction proportional to present needs.
5. Implicit wiring, global state, reflection, initialization side effects, and temporal coupling.
6. Pattern fit for the language and supported runtime version.
7. Simplicity, comprehensibility, and avoidable complexity.
8. API surface, domain boundaries, and exposed internals.

Go favors consumer-owned small interfaces and composition; Rust uses traits and
ownership where actual polymorphism requires them; JavaScript/TypeScript favors
composition and clear module boundaries; Python favors explicit dependencies.
Apply these as decision criteria, not unconditional style rules.

If delegation is available and permitted, assign independent passes to subagents,
grouping related concerns so they share context. Respect `--max-agents=N` (default
ceiling 6), the runtime's available slots, and any caller limit; `0` means no
delegation. Each agent reviews directly without re-delegating and returns evidence,
impact, location, fix, confidence, and the perspectives covered. Otherwise perform
the same passes yourself. Do not drop coverage to fit the agent budget.

For significant decisions, state the proposed approach, evaluate it against
requirements and conventions, and compare viable alternatives only when their
consequences differ materially. Recommend a choice with trade-offs. Every
finding must name a concrete cost or risk. Anchor findings to the plan section
and decision, using states `Blocker`, `Risk`, `Alternative`, or `Gap`.

Report only findings with confidence at least 80, unless the caller supplies a
different threshold. A clean review is valid. Deduplicate overlapping findings.
Keep severity separate from confidence: severity measures impact, confidence
measures evidential certainty. Order by severity, then confidence.

Start with the scope and material limitations. For each finding use:

```text
### N. <concrete consequence>
Severity: <Critical | Important> | Confidence: <0-100> | State: <precise state>
Location: <file:line or section>

Issue: <what goes wrong, for whom, and the evidence>
Fix: <specific correction or decision>
Reviewers: <perspective(s)>
```

For whole-file reviews, omit diff provenance. Do not equate a suspected issue
with a verified defect. End with the report;
explain, save, re-run, or fix only as requested.

Include convention context when inspected, candidate approaches, findings, and
an overall readiness assessment. Do not infer runtime defects from a plan alone.

Related skills:
- [arch-reviewer](~/.agents/skills/arch-reviewer/SKILL.md)
- [design-creator](~/.agents/skills/design-creator/SKILL.md)
- [test-planning](~/.agents/skills/test-planning/SKILL.md)
