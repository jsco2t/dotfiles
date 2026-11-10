# Codex pipeline efficiency implementation plan

Deliver a faster Codex task pipeline that scopes the requested outcome, resolves material questions before implementation, writes a readable plan, obtains independent plan review, and then executes without human scope or plan approval. Changes are confined to this skill and its bundled runtime, references, tests, and evaluation notes. Historical hidlins runs and other agents’ skills remain untouched.

## Evidence and investigation

Inspect both supplied hidlins runs using their saved requests, contracts, histories, check logs, agent records, and metrics. Compare the latest OpenCode commit (550c466) with Codex’s existing behavior. Record measured causes and limitations in a companion execution audit. Distinguish wall time and human waits from active work; token usage is unavailable unless actually recorded.

Initial evidence: the Apple run recorded 415 helper calls, 245 check executions, no check reuse, and roughly 9.6 hours of explicit question waits. Its state is 36 MB with 41,789 checkpoint paths. The Linux checkpoint is 116 MB with 37,089 paths and remains EXECUTING in the supplied copy. Both monitor an entire project documentation workspace using recursive walking, including historical pipeline evidence. Current plan.md is a JSON fence rather than an implementation document.

## Implementation units

1. Replace required initial human gates in new workflows with scope settlement and independently reviewed plan acceptance. Keep legacy workflows resumable without rewriting saved contracts or inventing user approval. Require no pending questions at entry to implementation. Bind independent review to the exact scope and plan fingerprint; reject stale or unresolved reviews. Render plan.md as real prose, tasks, acceptance criteria, dependencies, and verification commands. During execution use its current task and requirements to stay on track.
2. Reduce bookkeeping round trips and artifact churn. Accept structured JSON on stdin for payload commands and provide a sequential batch command that saves each successful operation, stops at the first failure, and returns the next action. Keep durable evidence under .tp, human documents at the workflow root, and no transient payload/packet/diff copies by default. Reject JSON reads/writes disguised with a Markdown extension. Preserve original red checkpoints, logs, and effect receipts.
3. Reduce avoidable verification and snapshot cost. Allow explicitly bounded workspace monitoring, with conservative full monitoring as the legacy default; always include declared write files and literal check inputs. Use scoped complete check inputs, current check evidence in review packets, focused repair checks and one meaningful integration gate. Reconcile completed worker receipts automatically before advancing, without retrying unknown effects. Preserve source freshness, one writer, and meaningful regression checkpoints.
4. Prevent scope drift and routine human interruptions. Allow documented manager amendments only inside the settled scope with unchanged outcomes, acceptance criteria and existing regression obligations. Never auto-adopt other actors’ edits. Record worthwhile unrelated observations once for final reporting without requiring a human to accept a follow-up obligation. Require concrete evidence for necessary environment repairs; stop speculative harness, licensing, platform, or benchmark work unless requested or a demonstrated blocker.
5. Update skill/reference instructions and add targeted runtime regressions covering autonomous entry, review freshness, no open questions, human-readable Markdown, batch partial failure, stdin, scoped monitoring, recovery and closeout. Run the existing full bundled suite and fix compatibility regressions. Obtain a bounded independent final review and reconcile confirmed findings.

## Acceptance and verification

The new default can complete a real temporary workflow from scoping through final report with an actual independent plan-review record and no human approval commands. Unresolved material questions, stale review, unauthorized scope expansion, concurrent edits, stale/failed checks, weakened regression pins, and unknown external effects still stop dependent work. Markdown files contain readable Markdown, and helper payloads need no throwaway files. Existing legacy regression and evaluation tests continue to pass. Only .agents/skills/co-task-pipeline changes appear in git diff.

## Limits

No speedup or token reduction is claimed from synthetic tests. Saved metrics establish the historical costs; regression tests establish behavior. Real comparative latency/token claims require comparable future complete runs. Environment and external publishing permissions remain governed by actual user authorization and host permissions.

## Independent review and reconciled decisions

The independent OpenCode audit agent reviewed this plan before implementation. Three findings were accepted: bounded monitoring must explicitly state its detection limit; historical contracts must remain untouched; independent plan acceptance must require an attached, completed reviewer record tied to the exact request, scope and rendered plan. New runs enforce payload extensions; historical runs remain readable but any JSON payload mislabeled .md must be resubmitted through stdin or .json without rewriting old evidence. Helper records are provenance supplied by the host agent, not authenticated proof of host identity.

The human clarified that honest test repairs, including mistakes beyond formatting, belong to the agent. Add a correction path with an independent focused reviewer, saved original pin/copies/logs, current green evidence, and verified regression proof. A fixture/build/import failure is never behavioral red. If old assertions and valid red proof remain unchanged, retain them; otherwise reproduce corrected tests on a trustworthy isolated pre-fix baseline and save the actual log/identity before replacement. Never restore live production just to replay a test. No human approval is required for a same-contract correction.

Add compact immutable checkpoint storage for new runs, and distinguish delivered-task status from dirty verification. Preserve accepted task evidence while prerequisite/check changes trigger affected verification at a coherent boundary. This directly addresses the repeated acceptance/dependency deadlocks observed in both runs.

## Completed implementation and validation

All five implementation units are complete. Runtime changes include autonomous settlement and
independently bound plan acceptance; readable contract rendering; stdin and durable sequential
batches; explicit monitoring and ignored check-input coverage; compressed deduplicated
checkpoint objects; automatic worker receipt recovery; transitive verification dirtiness;
agent-owned test correction with actual isolated baseline worker evidence; and bounded retry
diagnosis. Operational references and historical evaluation labeling are updated.

Independent review used `/root/opencode_audit` for OpenCode comparison, plan review and bounded
runtime reconciliation (requested TERRA/high; actual serving settings unreported). The plan
review findings were reconciled above. Runtime findings prompted exact check-amendment review,
mandatory corrected-test/contract/proof binding, real proof receipts instead of supplied exit
statuses, no autonomous mechanical-label bypass, ignored glob enumeration, transitive dirty
verification, live-baseline reference/symlink rejection and nonzero plan-review capacity.
The final bounded recheck found no remaining blocker in those fixes. Baseline execution is
evidence bookkeeping, not OS isolation or authenticated host identity.

`/root/run_audit` independently examined the two histories and fact-checked the saved audit
(requested SOL/high; actual serving settings unreported). Its two metric corrections are
included: the 13.6 MB fingerprint cache belongs to Apple; stable duplicate passing Linux
checks total 56 extra executions / 4.5 minutes. Token consumption remains unmeasured.

Final command: `python3 -B -m unittest discover -s .agents/skills/co-task-pipeline/tests -v`.
Result: **121 tests passed in 86.480 seconds**, including all 108 historical compatibility and
evaluation regressions plus 13 autonomous workflow regressions. The final autonomous tests
exercise a genuine corrected-test baseline failure, current green, narrowed reviewer inputs,
crash receipt recovery without replay, stale scoping answers, meaningful Markdown, batch
failure persistence, ignored dependencies and retained completion across a dependency chain.
Python runtime syntax, local documentation links and `git diff --check` also passed.

Changes are limited to this repository's `.agents/skills/co-task-pipeline` directory. No live
skill, system setting, other agent variant, hidlins source or historical run was modified.
No comparative future latency/token claim is made from regression tests.
