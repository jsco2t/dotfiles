# Delegation policy

Read this only when considering or using a subagent. The main session owns the contract,
deliverables, verification, and integration.

## Decision

Choose from the workload. Keep connected discovery and implementation local; for independent
component research or reviews, choose a bounded agent allowance during scoping. One independent plan review is required in new runs.
Do not turn a one-writer restriction into a ban on useful parallel reads. Parallel tool calls
are useful even with a single agent.

Use a bounded research or review agent when:

1. Its result answers a distinct question or supplies a valuable independent review.
2. It can work without waiting for the main session's next edit or duplicating current work.
3. The expected value justifies context setup, extra tokens, and verification of its result.
4. The approved scope allows the role and count, and the runtime exposes delegation tools.

Explain the reason briefly; use the helper assignment and returned identity as the durable record.
Record only reusable conclusions in optional `research.md`. Default to one agent when delegation is justified; at most three children may be
active, within the approved `max_agents` allowance and available runtime slots (which may
include the parent). If delegation has marginal value, keep the work
local; ask only if the uncertainty concerns a material user requirement or an agreed independent
review. Select the model using the routing policy below, respecting explicit operator choices.
Use a fresh context containing only the brief and necessary artifacts when the runtime permits;
do not copy the entire conversation into every agent by habit.

Give each new assignment a `unit` (one coherent component/review cycle or research question)
and `context: fresh|continue`. Start a **fresh** reviewer at a component boundary. Within the
same unit, `context: continue` plus `continues: <prior-assignment-id>` can reuse the reviewer
for bounded repair inspection; carry only unresolved findings and useful coverage forward.
Reset even within a unit when accumulated irrelevant context or repeated reads outweigh reuse.
Save the handoff before resetting; preserve coverage without repeating a full review.
Reconsider model/effort and record a specific rationale for every assignment. A tiny ordinary
delta does not inherit the model choice of the original broad/security review automatically.
Changing model/effort requires a fresh host thread; follow-ups inherit that thread's settings.
The helper checks declared lifecycle and attached identities; it cannot reset host context.
Older assignments without lifecycle fields remain compatible.

Never delegate implementation by default, create one agent per task, or spawn nested agents.
If the operator explicitly requests parallel implementation, present a revised plan with
disjoint write ownership and integration checks and ask to change this workflow before using
it; this helper deliberately tracks one writer. Do not bypass that limitation silently.

When a named review skill offers its own fanout, choose one owner of delegation: invoke it
in the parent with the approved remaining child allowance, or delegate the complete bounded
review with `--max-agents=0` and no children. Never multiply pipeline agents by reviewer agents
by perspective agents. A named skill's required independent coverage still applies; surface
a genuine capability/contract conflict rather than silently dropping lenses or independence.
Independent read-only units can overlap only while their source revision stays fixed. With
one child slot, the parent can inspect a disjoint lens while the child reviews, then integrate
before writing; do not run a sibling review against code the parent is actively changing.

No custom global agent configuration is required. Use the runtime's available spawn and
follow-up tools with a bounded brief. If delegation is unavailable, do the work in the main
session only when the approved contract permits it. An agreed **independent** review cannot
silently become self-review: ask to amend the method or wait for the capability.

## Model and reasoning selection

The core thread chooses a model before each assignment. The operator authorizes up to three
children and explicitly asks for SOL/TERRA routing. Use the exact supported IDs below;
record the choice and rationale rather than asking the child to select its own model.
TERRA is the cost-conscious choice for easier bounded work. Measure actual savings before
claiming every assignment is faster or cheaper; neither model is a substitute for evidence.

| Assignment | Model / reasoning | Acceptance by the parent |
| --- | --- | --- |
| Extract requirements from supplied sources, locate symbols/callers, map files, verify citations, summarize existing check logs | GPT-6.1-Terra / `medium` | Check returned evidence and reconcile all requested items. |
| Trace one bounded behavior across modules; independently review a coherent diff for correctness, regression coverage, or factual document accuracy | GPT-6.1-Terra / `high` | Validate every reported defect and ensure the requested review coverage was actually examined. |
| Ambiguous behavior, architecture, security-sensitive or concurrency analysis across subsystems, conflicting requirements, broad synthesis | GPT-6.1-SOL / `high` | Validate cross-component reasoning and reconcile conflicts; core thread retains scope/integration decisions. |

In this runtime, pass `fork_turns: "none"`, `model: "gpt-6.1-terra"` or `"gpt-6.1-sol"`, and
the selected `reasoning_effort` to `collaboration.spawn_agent`; put the self-contained
brief in `message`. A full-history fork inherits the parent's settings and cannot select a
different model. In another runtime, use only its exposed equivalent; do not invent model
flags, edit global settings, or launch a nested Codex process. If the exact selection is
unavailable, use SOL for an assignment TERRA cannot handle when SOL is available, otherwise
inherit session settings and disclose the fallback. Never silently label fallback execution
as the requested model. A runtime that reports only a requested override leaves actual
identity unreported.

Start at the listed effort, not medium then high for every task. If TERRA returns incomplete
or unsupported evidence, give one focused correction or move the unresolved question to SOL.
If SOL still cannot establish the answer, keep validated findings and investigate the
uncertain part in the parent or ask about a genuinely missing decision. Do not run both models routinely or
retry the same failing assignment indefinitely. Unknown facts are not permission to reduce
scope; material product choices still belong to the operator.

Record agent identity, requested and actual model/effort when exposed, question, coverage,
and evidence outcome once in the helper assignment (including reviews). Never infer actual settings
from a requested override when the runtime does not report them. Use runtime token/elapsed
measurements when available; otherwise mark them unmeasured. Measure savings on comparable
accepted work before claiming a cost or latency improvement.

The [official model selection guidance](https://learn.chatgpt.com/docs/model-selection)
recommends bounded inputs and verifiable results for Terra; its
[model page](https://developers.openai.com/api/docs/models/gpt-6.1-terra) lists medium and high
reasoning support. The role split above is this workflow's judgment, subject to evidence from
actual runs.

## Assignment and return records

Use `tp schema agent` for a brief and pass small payloads through `--file -`.
Set `purpose: plan` for the mandatory initial plan reviewer, `purpose: test-correction` with
owning task/optional repair and actual proof operation for a pinned test repair, or
`purpose: amendment` with candidate `plan_file` inside the workflow for existing check changes.
Give these reviewers the exact request, criteria, old/new contents and relevant actual logs;
accept only a verified return with no unresolved issues. See execution.md for proof requirements.

Use `tp schema agent` for a brief. It names approved requirement IDs, role, absolute starting
paths inside settled workspaces, one bounded question, stopping condition, `model: SOL|TERRA`,
`reasoning: medium|high`, and the core thread's `model_reason`.
Set `task` when execution has an owning task. Optional `inputs` uses the check-input map
format to declare the complete reviewed source, tests, shared configuration and transitive
dependencies. Include patterns for newly created source as well as current files. These inputs determine source freshness; mandatory plan/test-correction revisions are additionally
bound by the helper, so narrow inputs cannot hide changed tests or contracts. Omission retains
conservative whole-workspace freshness. Starting `paths` are navigation hints, not a substitute
for complete dependencies. Name meaningful ignored dependencies with literal input paths.

1. `tp agent reserve --id A1 --capacity <total-usable-child-slots> --file <brief.json>` checks
   the approved cap (up to three), counts reserved/running/unknown children and emits a compact
   packet. Capacity excludes the parent and includes already-assigned children plus free slots.
2. For `context: fresh`, spawn with that packet, read-only role and no children. For
   `context: continue`, follow up with the recorded host agent in the same unit. Then
   `tp agent attach --id A1 --agent-id <actual-id>`; add `--actual-model` and
   `--actual-reasoning` only when reported by the host.
   If complete essential context needs a justified larger budget, `agent reserve` accepts
   `--max-bytes`, just like `packet`; never drop constraints to fit the default limit.
3. Read and validate the returned source evidence, then `tp agent finish --id A1 --file
   <result.json>`. Result needs `accepted`, summary, evidence list and parent `validation`.
   Plan, test-correction and amendment reviews also require an explicit `unresolved` list of
   nonblank issue strings; use `[]` only when no issues remain. Acceptance requires that empty list.
   Changes to declared source inputs invalidate automatic acceptance; review current affected
   artifacts first. Unrelated operator edits still need separate adoption authority before
   implementation can continue, even when they do not invalidate this review's coverage.
4. Interrupt using host controls on halt, then `tp agent cancel --id A1 --evidence <actual-status>`.
   A missing handoff is unresolved, not a reason to respawn repeatedly. Settle all assignments
   before final delivery. The helper records authority and provenance; it never launches agents.

Use the helper assignment record as the source of truth; put reusable conclusions in
optional research.md once rather than copying the entire brief/report into multiple ledgers.

## Research brief

Give the agent the exact question, why it matters to a deliverable, absolute workspace paths,
starting sources, relevant operator decisions, and a concrete stopping condition. Ask for
answers with `path:line`, primary-source URLs, or issue/comment references; unknowns; and
uninvestigated follow-ups. Let it read relevant dependencies rather than treating starting
paths as a reading fence.

Require read-only work, no external mutations, no child agents, and no scope decisions. Return
concise findings in the reply; do not require another JSON file and duplicated report for a
small answer. The parent stores reusable conclusions once in optional `research.md` and verifies claims
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
in-scope findings in the helper's review result; material requirement questions go to the operator during scoping; routine repair decisions remain with the manager.
Identify the actual agent in an independent review record. Do not label an agent's echo of
the author's conclusions an independent review.

Stop new assignments on halt. On a crash or interrupted handoff, inspect the workspace and
task state, record what is known, and resume only missing work. A slow agent is not proof of
failure; check progress rather than repeatedly respawning it.

The [official Codex subagent documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents)
describes the additional model work and token cost of delegation. The workload-based policy
above weighs that cost against useful independent review and parallel research.
