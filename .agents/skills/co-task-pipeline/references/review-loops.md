# Component review and repair loops

Use this reference when reviews and fixes are the requested work. The pipeline coordinates
the named reviewer; it does not replace that review with its own generic final checklist.

## Map, then plan

Research identifies coherent responsibility boundaries, their entry points/callers, critical
invariants, and useful verification commands. Give each component a primary owner; record
cross-component edges so they are traced without duplicating entire reviews. A short map is
usually enough. Stop mapping when each unit has a clear review scope and no coverage hole.
Do not audit all dependencies or hash every tracked/vendor file to establish module seams.

Preserve the actual request. “Three cycles” means three; “up to three” permits early exit
when a complete pass finds no qualifying issues. Do not reinterpret one as the other. A
separately requested final security review remains separate. State explicitly whether the
review scope is current component source, a commit range, or a working diff; an unchanged
component is not an empty review when full-source inspection was requested. Pass that scope
to the named routing/review skill and retain all its required perspectives.

Plan one task per coherent cycle, containing review → validate findings → test-first fix →
affected verification → repair inspection → authorized commit. Use `adaptive: true` when the
findings are unknown. Initially it can have empty paths/checks and manual verification for a
clean review. Acceptance must require qualifying defects to be fixed test-first, then checked
and committed where authorized. Do not pre-create a second task just to checkpoint each review,
or another plan/approval round for each finding. Use incremental `repair` steps within the
task when findings arrive sequentially: each step has its own red/green checkpoint and
retains prior regressions. A genuinely new outcome or architecture exception still needs
one concrete decision; do not silently change outcomes through repair details.

## Execute a cycle

1. Capture the source revision/dirty baseline and resolved reviewer scope once. Read the
   applicable named skill and forward mode, confidence threshold, paths and agent allowance.
   Follow its delegation model within the pipeline's total child budget. The parent handles
   integration and fixes; reviewers read a stable snapshot. Reuse coverage notes across lenses.
2. Validate reported issues against the source. Record finding ID, confidence, trigger,
   consequence and evidence once. Fix only issues meeting the requested threshold, and do
   not turn suspicions or style preferences into defects. A clean pass is valid.
3. For qualifying findings, start a bounded `repair` step with the actual files, criterion,
   focused commands and test-first strategy. Add its regressions, inspect genuine failing
   behavior, and pin with `repair test --stage red`. Implement, check green, inspect the diff
   and close that step before the next finding. Preserve earlier test pins with separate
   regression files. Store notes inside the
   workflow rather than changing product files during the pre-fix review.
4. Run the affected component/integration gates required by the contract. Broaden when the
   change, failures, or repository rules justify it. Reuse current logs in the repair review;
   do not repeat unrelated suites, licensing inventories or benchmarks per finding. A dependency
   change needs its actual policy checks; a call-order fix need not re-audit unchanged licenses.
5. Close the cycle with finding dispositions, red/green logs, review coverage, verification
   limits and actual commit/revision. Do not create empty commits for clean passes. Start the
   next requested cycle without an extra unrequested full review between cycles. A repair
   inspection confirms fixes and regressions; it does not substitute for a requested new pass.

Maintain one compact cycle ledger. It should answer completed components/cycles, findings
closed, current activity and remaining work. After cycle one, report an evidence-based forecast
separating review, repair, checks, environment work and operator waits. If a repair needs a
material architecture/policy exception, prepare one concrete decision and ask. Routine
refinement and equivalent lint corrections use existing plan authority.

Final pipeline review verifies integration and request coverage using completed reports and
current checks. Preserve a requested whole-codebase security pass, and keep its scope distinct
from repair inspection. No finite runtime is guaranteed: defects can make repairs expensive;
the remedy is an honest forecast and efficient execution, never an invented clean result.
