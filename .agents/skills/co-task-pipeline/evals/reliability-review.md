# Co-task-pipeline reliability review — 2026-11-21

The pipeline had real recovery deadlocks, beyond the cost of managing substantial work.
Its previous improvements were useful, but ordinary tasks still lacked some of the recovery
authority promised by the instructions. Whole-file test pins also prevented normal shared
suite evolution. This revision addresses those causes and reduces routine helper calls.

## Existing behavior and recent history

The skill scopes a request, records requirements and workspaces, renders a readable plan,
requires independent plan review, then delivers with one main-session writer. Its helper
persists checkpoints, task evidence, test pins, check workers/receipts, delegation records,
amendments, final review and completion reports. New runs do not require human scope/plan
approval; older runs retain their saved authority.

Relevant repository history inspected:

| Commit | Improvement | Remaining issue investigated here |
| --- | --- | --- |
| `6d19abc` — October 29 | Requirements coverage, review provenance and constrained delegation | Coordination mechanics still needed explicit records. |
| `6a3840a` — November 3 | Recoverable check workers, incremental repairs, scoped reuse and evaluation fixtures | Pins remained whole-file locks across later work. |
| `d160ffe` — November 4 | More recovery, provenance and evaluation checks | Some ordinary corrections still led to operator gates. |
| `11ef616` — November 10 | Autonomous scope/plan entry, readable plans, stdin/batches, compact snapshots, monitoring, dirty verification and honest test correction | Several mechanisms remained restricted to tasks declared adaptive; shared pins could deadlock. |
| `e53848f` — November 11 | Explicit typed `unresolved` review lists | Correctly closed an evidence-validation gap; it did not address recovery reachability. |

The earlier [execution audit](hidlins-execution-audit.md) recorded lengthy waits over fixture
mistakes and repeated acceptance. Those saved measurements explain the motivation; they are
not measurements of this revision. Other pipeline variants were inspected as comparisons
but remain unchanged. No historical run or installed skill was modified.

## Findings and changes

| Demonstrated problem | Resulting behavior |
| --- | --- |
| An ordinary task could neither refine checks nor correct its pinned tests because it lacked `adaptive: true`. | Autonomous tasks can refine details, repair defects and use reviewed corrections within existing outcomes. Legacy allowances remain. |
| A later task explicitly owning the same test file could append a passing case but could not complete, update the completed pin owner, or reopen it while running. | The active writer can record reviewed evolution of a completed owner's shared tests, preserving its delivery record and original evidence. |
| A second repair adding a failing case could not record red until the earlier shared-file pin was corrected; that correction required green. | The new repair can record genuine red first. Current green and reviewed preservation of earlier coverage remain completion requirements. |
| Multiple pins on one suite needed mutually blocking updates; semantic corrections could not gather honest replacement proof. | One focused review/update covers the group. Valid earlier proof can be retained; each invalid proof has its own actual baseline receipt and disposition. A mistaken characterization can become genuine red, never the reverse. |
| Widening to an untouched pre-existing file outside monitoring required operator adoption. | Newly observed originals can enter the manager's baseline before editing. Existing observations cannot be rewritten or concurrent monitored edits adopted. |
| Glob traversal prefixes widened monitoring to unrelated siblings. | Snapshot selection uses actual patterns, independently of traversal prefixes, for Git and walk snapshots. |
| Routine completion needed separate check, done and next calls; delegation needed a separate attach even when collecting the return immediately. | `done --verify` runs only missing/stale task checks and returns the next action. `agent finish --agent-id` can attach the actual host identity and record the return together. Earlier attach remains available for recovery. |
| Instructions repeated procedures, imposed model-routing paperwork and recommended artificial per-regression files. | Shorter guidance explains decision ownership and the normal delivery loop; model settings default to inheritance, with explicit routing still supported. Shared suites remain usable. |

The operating instructions now distinguish a genuine requirement/authority decision from
a helper refusal or engineering mistake. The agent diagnoses and repairs the latter.
Meaningful pins, requirement coverage, independent review and real check receipts remain:
they protect evidence and delivery, rather than merely recording phase transitions.

## Review coverage

Inspection covered invocation/scoping, requirements and plan validation, independent review,
task sequencing, adaptive repairs, amendments, test correction, check caching/execution,
interruption/effect recovery, snapshots/checkpoint storage, context packets, delegation,
metrics/artifacts, closeout, legacy behavior, bundled tests and evaluation claims.

The standard task loop falls from `start`, `check`, `done`, `next` to `start`, `done --verify`
when no diagnostic check is needed. Initial plan-review records can use reserve/finish/accept
instead of reserve/attach/finish/accept. These are command-count changes, not measured model
latency or token savings. Check reuse still depends on complete inputs and the environment.
The active skill/reference instructions decreased from 726 to 606 lines; conditional proof
details remain in the execution reference rather than the main task loop.

## Test-forward validation and limits

New delivery regressions were run failing before their corresponding runtime fixes. They
exercise actual local check workers and isolated baselines, including rejected missing proof,
red-to-pin downgrade, stale evidence and concurrent monitored edits. Added recovery paths
retain original test copies/logs and do not accept prose in place of check receipts.

Independent forward evaluation used `/root/pipeline_forward_check`, with temporary fixtures
only. It reproduced the initial ordinary-task/shared-suite blockers, found the additional
red/green loop and semantic group deadlock, then completed the corrected semantic scenario
through `final` using two real baseline worker proofs. Its negative checks rejected stale
reviews with narrowed inputs, omitted per-pin proof and red-to-pin downgrades. Final source
inspection found no remaining blocker in those paths.

Reviewer identities inside automated fixtures are scripted data, not claims that their
review contents came from an independent agent. The actual independent evaluator inspected
the behavior and evidence separately. This work validates local transitions and concrete
recovery scenarios; it does not establish real-workload throughput, model quality, or all
environment behavior. No comparative token or end-to-end speedup claim is made.

Validation commands:

```sh
python3 -B -m unittest discover -s .agents/skills/co-task-pipeline/tests -v
/usr/bin/python3 -B /home/duser/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/co-task-pipeline
git diff --check
```

The complete bundled suite passed: **139 tests in 197.091 seconds**, including 13 new
delivery regressions and the 126 existing compatibility/evaluation tests. A focused follow-up
also passed the added negative proof-disposition and red-to-pin checks. Skill validation,
Python syntax, local reference links and diff whitespace checks passed.

Python syntax and local Markdown reference links were also checked without generating
repository artifacts. All changes are confined to this repository's co-task-pipeline skill;
test workspaces and transient execution logs live under the system temporary directory.
