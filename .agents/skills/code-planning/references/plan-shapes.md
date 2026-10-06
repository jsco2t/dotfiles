# Adaptable Plan Shapes

Choose the shortest shape that makes the requested decisions and handoff clear.
These are outlines, not required schemas. Omit inapplicable sections and replace
instructions with concrete content. Follow an existing artifact's conventions
when updating it.

## Compact plan

Use for a bounded fix or change, including a delivery-only request with a few
requirements. Keep traceability in the prose or bullets rather than adding tables
that merely repeat them.

```markdown
# Plan: <change>

**Depth:** Delivery | Implementation | Task breakdown
**Readiness:** Ready | Needs clarification | Provisional
**Sources:** <relevant supplied context and evidence>

## Problem and intended outcome

<Reported/current behavior, desired behavior, conditions, and evidence. For a bug,
state the supported cause or the investigation still needed.>

## Delivery and acceptance

<What changes or ships and the observable criteria that establish completion.
Include relevant constraints and agreed scope boundaries.>

## Approach and work sequence

<Ordered work with verified change points at implementation depth. Include directly
related tests in the work. At delivery depth, describe only delivery dependencies
and the solution shape justified by available information.>

## Verification

<Existing coverage, the meaningful gap, planned cases with inputs/actions/assertions,
and checks. Distinguish repository commands verified to exist from commands run.>

## Decisions, risks, and unresolved questions

<Only consequential items. For each blocking question, state what it affects and
the answer needed. If none remain, say so briefly or omit this section.>
```

## Expanded plan

Use for multiple delivery boundaries, complex behavior, architecture choices,
migrations, or significant coordination. Keep it in one document unless task
context warrants separate files. Include implementation and task sections only
at the requested depth.

```markdown
# Plan: <change>

**Depth:** <requested planning depth>
**Readiness:** <status and affected portions if provisional>
**Sources:** <specifications, issues, repository/revision when useful>
**Updated:** <current timestamp using the user's or repository's convention>

## Summary

<Lead with what will be delivered and the problem it closes.>

## Problem and current system

<Current and desired behavior, evidence, affected flow and dependent callers.
Separate reported observations, verified facts, and root-cause hypotheses.>

## Scope and requirements

<Goals, agreed exclusions, relevant compatibility and operational constraints.>

| Requirement | Behavior or constraint | Acceptance | Source / decision |
| --- | --- | --- | --- |
| R-1 | <required outcome> | <observable result> | <authority> |

## Deliverables

| Deliverable | What ships or changes | Requirements | Acceptance |
| --- | --- | --- | --- |
| D-1 | <concrete artifact or change> | R-1 | <deliverable-specific criterion> |

## Approach and decisions

<Solution shape, consequential alternatives and rationale. At implementation
depth add verified change points, interfaces, failure handling, and proposed new
elements. Include migration and rollout only when required.>

## Verification strategy

<Current test patterns and coverage, validation gaps, lowest reliable test levels,
reused helpers, deterministic setup and cleanup. Explain boundary tests and exclusions.>

| Case | Requirement | Setup / input | Action | Expected result | Level / location |
| --- | --- | --- | --- | --- | --- |
| V-1 | R-1 | <fixture> | <operation> | <observable assertion> | <verified or proposed> |

## Work sequence or tasks

| Task | Outcome and scope | Depends on | Acceptance / verification |
| --- | --- | --- | --- |
| T-1 | <implementation with related tests> | <IDs or none> | D-1 / V-1 |

<Expand tasks inline or link separate task files when useful. Explain coordination
for shared files/contracts. Add estimates and critical path only when useful or requested.>

## Coverage and Definition of Done

| Requirement | Deliverables | Work | Verification | Gap |
| --- | --- | --- | --- | --- |
| R-1 | D-1 | T-1 | V-1 or existing coverage | <none or unresolved issue> |

<At delivery depth omit Work. Do not label planned coverage as already verified.>

<List only gates spanning deliverables, such as integration compatibility or a
migration sequence; do not duplicate each deliverable's acceptance.>

## Dependencies, risks, and open questions

<External prerequisites and material risks with mitigation. For each unresolved
question state affected requirements/tasks, who can answer if known, and what is
needed to proceed. Separate agreed decisions from provisional assumptions.>
```

## Separate task documents

Split only where independent assignment and substantial context warrant it, or
when requested. Keep the main plan as the source of shared requirements and
decisions, and link tasks from it. Use stable IDs and local naming conventions;
numbered `tasks/01-<area>.md` files are a fallback, not a mandatory workspace.

Each assignable task should contain:

- **Outcome and scope:** what this task delivers and the shared plan references.
- **Prerequisites:** task IDs, contract decisions, environment needs, or discovery
  results required before work can begin.
- **Change points:** verified components, paths, symbols, and proposed new artifacts.
- **Implementation and related tests:** enough direction to proceed without
  rediscovering the plan; distinguish necessary discovery from settled changes.
- **Acceptance and verification:** observable completion and the relevant cases
  or commands. Do not equate writing tests with proving the behavior.
- **Coordination and risks:** meaningful overlaps, compatibility constraints, and
  uncertainties. Include effort and its assumptions only when estimates are useful.

For many tasks, summarize the dependency graph, coverage ownership, and any useful
parallel lanes in the main plan. Avoid repeating the entire specification in every
task file. Update existing relevant indexes only when needed to keep the requested
artifacts discoverable; preserve identifiers and links.
