# Read-only delegation

The parent writes and integrates deliverables. Use one independent plan reviewer; add bounded
research or component review only when it contributes distinct evidence worth the setup cost.
At most three children may be active, within host capacity. No nested fanout or parallel writers.
Choose one owner of delegation when a named review skill also offers fanout: the parent invokes
it with remaining capacity, or a child runs a bounded review without children.

## Assign and collect

1. Reserve with `agent reserve --id A1 --capacity <usable-child-slots> --file -`.
   The JSON brief names `role: research|review`, requirement IDs, absolute starting `paths`
   inside settled workspaces, one `question`, and `done_when`. Set `purpose: plan` for initial
   plan review, `test-correction` for pin evolution, or `amendment` for an existing check
   replacement, or `final` for an autonomous scope's independent final review. Other
   research/review assignments omit purpose. Set the owning `task` when known, except for
   whole-change final review.
2. Launch an actual host agent with that narrow brief and the necessary raw artifacts.
   Require read-only work, no external mutations and no children. The helper does not launch
   or authenticate agents. Keep reviewed inputs stable until the return is accepted.
3. Inspect the reply and verify its substantive claims against source/logs. Record one return:

   ```text
   tp agent finish --id A1 --agent-id <actual-host-id> --file -
   ```

   JSON needs `accepted`, `summary`, an `evidence` list, parent `validation`, and
   `unresolved: []` when clear. Review gates require that explicit empty list; missing or
   malformed values cannot clear them. A rejected result records concrete unresolved issues.
   If interruption recovery needs the identity before the return, use `agent attach` after
   spawning and omit `--agent-id` when finishing an already attached assignment.
4. Apply the result using `plan accept`, `test-update` or `amend` as appropriate. Reconcile
   concrete findings; do not repeatedly review unaffected work or create a separate report file
   for every small handoff. Store reusable conclusions once in optional `research.md`.

Actual model/effort remain unreported unless exposed by the host. By default, omit `model` and
`reasoning` or use `inherit`; use the session's available settings. Existing `SOL`/`TERRA`
labels with `medium`/`high` and a `model_reason` remain supported for explicitly chosen
routing. Respect user preferences and host constraints; do not block delivery on bookkeeping
about optional model settings or infer actual identity from a requested override.

## Review context and freshness

- Plan review: original request, requirement ledger, settled decisions, readable plan and its
  exact `plan check` revision, source assumptions and proposed verification. Look for missing
  or unnecessary work and unresolved decisions. A changed request/plan needs current review.
- Test correction: original/corrected tests, criteria, every affected original pin and log,
  current green and retained or reproduced regression proof. A shared-file update binds all
  affected pins in the review revision, even with narrow optional `inputs`. Preserve all
  earlier cases/assertions; do not treat new test cases as grounds for recreating old red runs.
  Semantic changes need each invalid pin's actual proof (`proof` plus optional `proofs`),
  preserving every original obligation. See [execution.md](execution.md) for grouped payloads.
- Check amendment: draft `plan_file` inside the workflow, old/new command, criteria and
  verification obligations. Confirm the replacement executes the required cases/assertions.
- Independent final review: reserve `purpose: final`, `role: review`, all requirement IDs,
  no `task` or narrowed `inputs`, after completed work and current verification. Review the
  original request, decisions, plan, whole monitored diff/source, baseline and current logs.
  Use the requested review skill and scope. Record the actual host identity and explicit
  `unresolved` list at finish. Submit `review` with `agent: <assignment-id>` and matching
  `agent_id: <host-id>`. A passing verdict requires an accepted return with `unresolved: []`;
  accepted findings may remain unresolved for a `changes` verdict that reopens owners.
  Changed source or request/plan revision requires review of the affected changes before
  completion. Legacy final reviews retain their original contract.
- Component or repair review: exact source/diff scope, pre-existing edits, current logs,
  prior findings and coverage. Return confirmed defects with trigger, consequence, evidence
  and owning task; a clean result is valid. Review fixes and integration gaps without
  repeating unaffected analysis. Preserve separately requested full-source review cycles.

Optional `inputs` uses the check workspace-to-pattern map. Include all relevant source,
tests, runners, configuration and dependencies, plus patterns for new files. Omission watches
all monitored source. Source changes require review of the affected assumptions/changes,
not automatic rejection of valid prior findings or an unrelated new audit.

## Reuse and interruption

Use a fresh narrow brief at a component boundary. Within a unit, `context: continue`,
`unit: <same-unit>` and `continues: <completed-assignment>` can reuse the same host identity
for focused repairs. The unit, task, model and effort must match; new model settings need a
new thread. Save useful findings before resetting context. Lifecycle fields are optional for
existing assignments.

On halt, interrupt the actual owned agent and `agent cancel --id A1 --evidence <actual-status>`.
After a missing handoff, inspect known agent/workspace state before retrying; slow is not lost.
Settle assignments before final delivery. If required independence is unavailable, report the
specific capability gap rather than relabeling self-review or inventing an agent identity.
