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
within the approved `max_agents` allowance. If delegation has marginal value, keep the work
local; ask only if the uncertainty concerns a material user requirement or an agreed independent
review. Select the model using the routing policy below, respecting explicit operator choices.
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

## Model and reasoning selection

This skill selects `gpt-6.1-terra` for these bounded roles when the runtime offers that exact
model and reasoning setting. This is a conservative routing policy, not a claim that every
task is faster or equally accurate on Terra.

| Assignment | Model / reasoning | Acceptance by the parent |
| --- | --- | --- |
| Extract requirements from supplied sources, locate symbols/callers, map files, verify citations, summarize existing check logs | GPT-6.1-Terra / `medium` | Check returned evidence and reconcile all requested items. |
| Trace one bounded behavior across modules; independently review a coherent diff for correctness, regression coverage, or factual document accuracy | GPT-6.1-Terra / `high` | Validate every reported defect and ensure the requested review coverage was actually examined. |
| Architecture, security-sensitive or concurrency analysis across subsystems, conflicting requirements, broad final synthesis | Inherit the main session's model and reasoning | Keep scope decisions and integration in the parent; use an independent agent only if it adds value. |

In this runtime, pass `fork_turns: "none"`, `model: "gpt-6.1-terra"`, and
`reasoning_effort: "medium"` or `"high"` to `collaboration.spawn_agent`; put the self-contained
brief in `message`. A full-history fork inherits the parent's settings and cannot select a
different model. In another runtime, use only its exposed equivalent; do not invent model
flags, edit global settings, or launch a nested Codex process. If the exact selection is
unavailable, inherit the session settings and disclose that fallback.

Start at the listed effort, not medium then high for every task. If medium returns incomplete
or unsupported evidence, give one focused correction or move that unresolved question to
high. If high still cannot establish the answer, keep the validated findings and finish the
uncertain part in the parent or with the inherited model. Do not run both models routinely or
retry the same failing assignment indefinitely. Unknown facts are not permission to reduce
scope; material product choices still belong to the operator.

Record agent identity, requested and actual model/effort when exposed, question, coverage,
and evidence outcome once in `research.md` (including reviews). Never infer actual settings
from a requested override when the runtime does not report them. Use runtime token/elapsed
measurements when available; otherwise mark them unmeasured. Measure savings on comparable
accepted work before claiming a cost or latency improvement.

The [official model selection guidance](https://learn.chatgpt.com/docs/model-selection)
recommends bounded inputs and verifiable results for Terra; its
[model page](https://developers.openai.com/api/docs/models/gpt-6.1-terra) lists medium and high
reasoning support. The role split above is this workflow's judgment, subject to evidence from
actual runs.

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
files, original request and requirement ledger, changed artifact paths, existing test logs,
saved decisions, and the specific review question or lenses. Build the diff once from the
helper's original file copies, including new files; do not ask every lens to regenerate it.
Request confirmed defects with their trigger, consequence, evidence, and owning task. Finding
nothing is valid. Require a read-only pass, no fixes, no external writes, and no child agents.
For a long set of documents, partition by coherent content with no duplicate review coverage.
Read current logs before considering test execution; rerun only for a specific gap or stale
evidence. For a repair round, inspect changed fixes and affected behavior with the previous
review findings, retaining requirement coverage without repeating unaffected analysis.

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
