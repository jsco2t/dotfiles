---
name: code-planning
description: Research and plan code changes from bug reports, problem descriptions, tests, issues, or existing specifications. Clarify missing requirements, define deliverables and acceptance criteria, and develop code-grounded implementation and verification plans at the requested depth, from a small fix to multi-component work. Use for planning rather than executing changes or producing a full product PRD.
---

# Code Planning

Turn the available context into a plan that explains what must be delivered, why,
how it can be built, and how completion will be demonstrated. Adapt to both the
size of the work and the maturity of its requirements. Do not require an approved
design, a feature workspace, or a complete specification before starting.

## Inputs and output

Accept any useful starting point: a bug, a prose problem description, a failing
test or test scenario, logs, an issue, a specification, an existing plan, or a
combination. Honor supplied repository paths, output locations, decisions,
constraints, and requested planning depth. Do not repeat settled questions.

Default to **one adaptable plan**. Split tasks into separate documents only when
requested or when independent assignment and substantial task context justify
it. A large change can still use one plan. Do not create a documentation workspace
or update unrelated indexes automatically.

- An explicit filename is the output file. An explicit directory defaults to
  `plan.md`, unless existing conventions identify another name.
- Use an existing plan or index to locate the intended artifact when supplied.
- Without a destination, present the plan in the conversation. Ask for a location
  only if saving is requested and the destination cannot be inferred.
- For updates, preserve stable IDs, links, decisions, and unrelated content;
  reread the current document before editing.

Plan changes; do not implement production code, tests, migrations, or deployment
as part of planning. Planning does not authorize changing issues, posting
comments, or other external writes. Use available source-access tools and their
relevant skills when needed; do not make this workflow depend on another planning
skill or a particular connector.

## 1. Establish the problem and planning depth

Research the supplied material before asking questions that it may already answer.
Identify the current or reported behavior, intended outcome, affected system,
scope boundaries, constraints, and the decisions the requested plan must settle.
Keep reported behavior distinct from behavior verified in code or reproduction.

Choose the depth from the request and evidence, and state it briefly:

- **Delivery planning:** clarify what must change, deliverables, observable
  acceptance, dependencies, and done gates. Appropriate when the request is about
  what needs to be delivered or implementation context is unavailable.
- **Implementation planning:** also establish the code path, proposed approach,
  affected components, test strategy, and actionable work sequence. Appropriate
  when asked to plan a fix or feature for implementation.
- **Task breakdown:** add assignable tasks with explicit dependencies and
  verification when the work benefits from decomposition or the user requests it.

These are cumulative depths, not mandatory phases or separate documents. A small
fix may need a short explanation and a few steps; a broad change may need design
trade-offs, migration, rollout, and a dependency graph. Do not inflate the plan
with empty sections, artificial phases, fixed task-size rules, or invented teams.
Do not downgrade a requested implementation plan to delivery planning merely
because repository access is missing; ask for the necessary context and mark the
implementation portion unresolved.

## 2. Investigate enough to support the plan

Read authoritative requirements and follow applicable `AGENTS.md` and project
guidance. For an existing system, inspect the current source, affected callers,
contracts, configuration, and nearby tests. Follow the path far enough to identify shared behavior and
compatibility implications. Verify artifact conventions, generated-file ownership,
and repository test commands before prescribing them.

Ground existing-code claims in current paths and symbols, with line references
where useful. Mark proposed files and interfaces as proposed. Never invent an
existing API, helper, command, or test. Record inaccessible sources, stale plans,
and conflicting evidence; decide whether they block the requested depth.

For a **bug**, separate the symptom, reproduction conditions, expected behavior,
root-cause evidence, and hypotheses. Use safe, focused reproduction or existing
tests when useful and authorized; do not require a reproduction if code evidence
suffices. Explain why the defect escaped existing validation and what regression
case would expose it. An unconfirmed cause requires an investigation step, not a
definitive fix presented as fact.

For a **test or example describing a problem**, extract observable behavior and
candidate requirements. A failing assertion may expose an implementation defect,
an outdated test, or an undecided contract. Check its authority and confirm
material ambiguity before treating it as the desired behavior. Do not generalize
one example into unrequested behavior or merely prescribe making the test pass.

For **new or broad work**, identify delivery boundaries and compare meaningful
approaches before decomposing them. Include performance, security, compatibility,
data lifecycle, and operational constraints when relevant; do not invent targets.

## 3. Clarify material gaps — required before completion

**Ask the user questions whenever missing, contradictory, or ambiguous information
would materially change the scope, expected behavior, acceptance criteria,
constraints, chosen approach, or readiness of the requested plan.** An Open
Questions section is not a substitute for asking. Research first, then ask before
making dependent decisions; do not wait until the final report to surface them.

Group a small number of focused questions. Explain what each answer changes and
offer a recommendation or concrete alternatives when useful. Prioritize decisions
that unlock other work. Ask about relevant gaps rather than administering a fixed
questionnaire. Continue independent research and unaffected planning while
awaiting answers.

Use judgment for routine implementation choices supported by repository patterns.
Record assumptions with their rationale, but do not use an assumption to settle a
material product choice, contradictory requirement, or missing authorization.
Do not re-ask information already supplied by the user or caller.

If answers are unavailable, keep affected content explicitly provisional and
identify the question, what it blocks, and the minimum input needed. Silence or
elapsed time is not an answer. If the user explicitly requests a provisional
plan with assumptions, produce one and label the unresolved decisions; do not
claim readiness for affected implementation. In a noninteractive invocation,
return the questions to the caller instead of silently resolving them.

Summarize consequential answers and decisions in the plan with their rationale.
Keep conflicting research facts visible even when the user chooses a different
direction. Revisit clarification when later research exposes a new material gap.

## 4. Define the deliverables and approach

Connect the problem to the smallest complete delivery. Distinguish a requirement
(behavior or constraint), a deliverable (what changes or ships), and a task (work
needed to produce it). Give every required behavior an observable acceptance
criterion and an owning deliverable. Separate scope exclusions from unresolved
scope; do not treat uncertainty as an agreed non-goal.

For nontrivial work, use stable requirement, deliverable, task, and verification
IDs to support traceability. Preserve source IDs when present. A small fix can use
plain bullets and direct links rather than four ID systems.

At implementation depth, explain change points, relevant interfaces, data flow,
failure behavior, dependent callers, and testability. Select the smallest approach
that satisfies the requirements; compare alternatives only when they affect a
real decision. Describe meaningful code changes without copying large source
blocks or prescribing unverified details.

Include migrations, generated artifacts, documentation, configuration, operator
procedures, and rollout or rollback when the change requires them. Put
deliverable-specific acceptance with its deliverable; reserve the overall
Definition of Done for gates spanning deliverables. Do not add unrelated cleanup.

## 5. Plan verification and actionable work

Study relevant existing coverage and repository test patterns before proposing
tests. Map each required behavior to existing coverage, a justified new or changed
test, a manual verification gate, or an explicit unresolved gap. Explain why
existing tests are sufficient or what they miss. Explain exclusions where a
plausible verification need is deliberately left out.

Prefer the lowest reliable test level. Use integration or end-to-end coverage
when a real contract or boundary cannot be proved by unit tests. Specify the
setup/input, action, observable assertion, and regression or risk protected.
Include relevant error and boundary cases without generating an exhaustive matrix
of low-value tests. Reuse repository helpers and frameworks. Plan controlled
dependencies, deterministic execution, and cleanup where applicable.

For a bug, plan a regression test that distinguishes the defective behavior from
the desired outcome and, when practical, fails before the fix and passes after.
Explain the validation gap that allowed the bug to escape. For a behavior-preserving
refactor, identify the existing behavior that validation must protect.

At delivery depth without source access, describe behavioral verification without
inventing test filenames or symbols. At implementation depth, identify verified
test locations, reusable infrastructure, focused commands, and appropriate broader
checks. Distinguish planned commands from checks actually run; planning does not
require running a full suite.

Use an ordered sequence for small work and assignable tasks for larger work. Each
task needs an outcome, scope or verified change points, dependencies, acceptance,
and verification. Couple implementation with its directly related tests; separate
shared fixtures or cross-component validation only when independently useful.
Make prerequisite contracts and discovery work explicit. Do not disguise unknown
design work as a certain implementation task.

Keep dependencies acyclic. Claim parallel work only when contracts and overlapping
files permit it or coordination is specified. Show a critical path only when it
helps scheduling. Estimates are optional: provide them when requested or useful,
state assumptions and uncertainty, and keep task totals consistent. Do not impose
fixed durations or team sizes.

## 6. Reconcile and report readiness

Read [references/plan-shapes.md](references/plan-shapes.md) when drafting to choose
a compact or expanded presentation; use its task format only when splitting work.
Adapt headings to the user and existing documents. Keep evidence, decisions,
assumptions, and unresolved questions distinguishable.

Before reporting completion, check:

- Required behaviors and constraints have deliverables and observable acceptance.
- Deliverables have a requirement or clear scope justification; coverage gaps are
  visible. At implementation depth, each deliverable also has work and verification.
- Code claims, test patterns, paths, and commands match available evidence.
- Dependencies, indexes changed within scope, links, and any estimates agree.
- Material questions have been asked and answered, or the affected plan is marked
  provisional. No required work is hidden behind an assumption or an empty section.

Report the output location or inline plan, chosen depth, proposed delivery and
approach, verification, and any readiness gaps. Use **Ready** only when the plan
is actionable at the requested depth. Otherwise use **Needs clarification** or
**Provisional**, state the affected portions, and carry forward the specific
questions. Delivery readiness does not imply implementation readiness.

Readiness and approval are separate. Do not call a plan approved without explicit
approval, or require a ceremonial approval round when the user only asked for a
plan. If review is requested, incorporate feedback and reconcile all affected
requirements, deliverables, tasks, and verification before updating readiness.
