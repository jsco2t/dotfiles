# Delegation policy

Read this only when considering or using a subagent. The main session owns the contract,
deliverables, verification, and integration.

## Decision

Default to no subagents. Keeping connected discovery and implementation in one context avoids
repeated reading and handoffs. Parallel tool calls are useful even with a single agent.

Request one bounded research or review agent only when:

1. Its result answers a distinct question or supplies a valuable independent review.
2. It can work without waiting for the main session's next edit or duplicating current work.
3. The expected value justifies context setup, extra tokens, and verification of its result.
4. The approved scope allows the role and count, and the runtime exposes delegation tools.

Explain the reason briefly and record the assignment and returned agent identity in
`research.md`. Default to one agent when delegation is justified; at most two may be active,
within the approved `max_agents` allowance. If uncertain whether delegation is worthwhile,
ask the operator. Inherit the session's model and reasoning settings unless the operator or
applicable instructions select them.
Use a fresh context containing only the brief and necessary artifacts when the runtime permits;
do not copy the entire conversation into every agent by habit.

Never delegate implementation by default, create one agent per task, or spawn nested agents.
If the operator explicitly requests parallel implementation, present a revised plan with
disjoint write ownership and integration checks and ask to change this workflow before using
it; this helper deliberately tracks one writer. Do not bypass that limitation silently.

No custom global agent configuration is required. Use the runtime's available spawn and
follow-up tools with a bounded brief. If delegation is unavailable, do the work in the main
session only when the approved contract permits it. An agreed **independent** review cannot
silently become self-review: ask to amend the method or wait for the capability.

## Research brief

Give the agent the exact question, why it matters to a deliverable, absolute workspace paths,
starting sources, relevant operator decisions, and a concrete stopping condition. Ask for
answers with `path:line`, primary-source URLs, or issue/comment references; unknowns; and
uninvestigated follow-ups. Let it read relevant dependencies rather than treating starting
paths as a reading fence.

Require read-only work, no external mutations, no child agents, and no scope decisions. Return
concise findings in the reply; do not require another JSON file and duplicated report for a
small answer. The parent stores reusable evidence once in `research.md` and verifies claims
that affect the plan. Ask the operator when facts leave a material choice unresolved.

## Review brief

Supply the approved criteria, baseline/current diff including pre-existing dirty and untracked
files, changed artifact paths, test evidence, and the specific review question or lenses.
Request confirmed defects with their trigger, consequence, evidence, and owning task. Finding
nothing is valid. Require a read-only pass, no fixes, no external writes, and no child agents.
For a long set of documents, partition by coherent content with no duplicate review coverage.

The parent checks each finding against the source before routing it. Store only validated
in-scope findings in the helper's review result; unresolved questions go to the operator.
Identify the actual agent in an independent review record. Do not label an agent's echo of
the author's conclusions an independent review.

Stop new assignments on halt. On a crash or interrupted handoff, inspect the workspace and
task state, record what is known, and resume only missing work. A slow agent is not proof of
failure; check progress rather than repeatedly respawning it.

The [official Codex subagent documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents)
describes the additional model work and token cost of delegation. The conservative default
above weighs that cost against useful independent review and parallel research.
