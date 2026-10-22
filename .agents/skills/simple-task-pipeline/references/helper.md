# Helper commands and saved progress

Run this skill's own `scripts/tp.py` using Python 3. Every workflow command needs
`-w <workflow-dir>` **before** the command. Quote shell paths and prose arguments.
The helper is independent of the agent host; it reads files and runs local commands.
Run `<command> --help` for optional flags and `schema <name>` for JSON examples.

## Commands

| Command | Purpose and important arguments |
| --- | --- |
| `init <location> --title <title> --request-file <file> [--budget N]` | Create a unique dated workflow under a parent location; never resume through init. `--budget` is a legacy total estimate. |
| `status [--json]` | Read-only phase, tasks, research, reviews, decisions pending, drift, and checkpoints. |
| `resume --answer <instruction> [--json]` | Recover halted or unhalted work; preserve phase, approvals, rounds, results, and active snapshots. |
| `halt [--reason <words>]` / `hault` | Save and stop, including unfinished local steps. |
| `next [--json]` | Select unfinished work from saved state; records a liveness marker, never starts a step. |
| `digest` | Progress and duration estimates for a human update. |
| `report` | Estimates and recorded elapsed timings; does not finish the pipeline. |
| `schema scope|plan|research|result|review` | Print a JSON example without needing a workflow. Replace example values with the actual contract. |
| `survey <repo> --name <workspace>` | Store a repository structure survey. |
| `survey-issue jira:KEY-123` / `survey-issue gh:owner/repo#123` | Read issue details using an installed CLI; `TP_JIRA`/`TP_GHTK` can configure the commands. |
| `roster suggest --kinds code,docs,...` | Suggest catalog role labels; all roles are performed by the main agent. |
| `scope check` | Validate scope.json and render scope.md. |
| `scope confirm --answer <response>` | Freeze checked scope and enter PLANNING. |
| `research add R1 --agent <role> --purpose <purpose> --questions-file <file> --done-when <criterion> [--minutes N] [--from R0.F1]` | Save a research contract. Purposes: map, requirements, investigate. Minutes are advisory, with no upper limit. |
| `research extend --minutes N [--note <reason>]` | Increase legacy research estimate metadata. Human `--answer` is optional. |
| `research dismiss R1.F1 --reason <reason>` | Settle a recorded follow-up without pursuing it. |
| `research drop R1 --reason <reason>` | Drop a pending, unrun research item. |
| `recon ...` | Compatibility alias for research commands; use research for new calls. |
| `plan check` | Validate the existing draft and render plan.md. Never erases research. |
| `plan submit` | Validate and request approval; refuses unfinished research/follow-up decisions. |
| `approve --answer <response>` | Record approval of the submitted plan and initialize execution. |
| `revise --feedback <response> [--scope]` | Return to planning, or scoping; preserve accepted progress. Requires a human revision decision. |
| `dispatch <id>` | Prepare and start exactly one local step. Id: R1, T01, or B1/doc-reviewer. Read the printed brief. |
| `record <id> [--trim-summary] [--credit N] [--dead-minutes N]` | Validate an already written result, run gates, and advance. No agent id needed. Correct invalid results in place. |
| `show <id> [--part <section>]` | Inspect a saved result: research answers/followups/unknowns/areas; review blocking/findings; task changed/questions/noticed/disputes. |
| `sample T01` | Print a source/diff sample for manual fact-checking. |
| `accept T01 --note <evidence>` | Accept a task after checking the source, diff, and test evidence. |
| `reject T01 --reason <finding>` | Route a task into a fix round. |
| `triage B1/doc-reviewer [--accept-all] [--dismiss F1,F2 --reason <reason>] [--assign F1=T01]` | Route validated blocking findings to task fixes; assign ambiguous ownership explicitly. |
| `exception --summary <question> [--task T01]` | Preserve work and block on an unresolved decision. |
| `resolve --action <action> --answer <response> ...` | Record a decision and continue the affected task, review, workflow exception, or noticed item; see below. |
| `lost T01 --summary <cause>` | Abandon a genuinely unrecoverable active task step, preserving artifacts and blocking for an explicit retry. Not needed for ordinary session loss. |
| `widen T01 --path <relative-file> [--path <file>] --reason <reason>` | Grow an execution write set, including accepted tasks, with a recorded mechanical correction. |
| `amend --reason <reason>` | Validate allowed edits to plan.json during execution and record the correction. |
| `budget extend --minutes N [--note <reason>]` | Compatibility command to increase a legacy overall estimate; gates no work. Human `--answer` is optional. |
| `clock T01 --dead-minutes N --note <reason>` | Correct recorded elapsed time for a stalled step. |
| `baseline` | Run final checks and save pre-existing failures; use before implementation. |
| `note <finding-and-consequence>` | Record an unrelated discovery in noticed.md. |
| `noticed` | List open noticed items. |
| `closeout` | List noticed items and their classifications. |
| `closeout --item N --class deferred\|followup\|observation --note <issue-and-consequence>` | Classify an item. Deferred/follow-up notes must explain the issue and consequence. |
| `closeout --ask` | Render the batched closeout decision for the human. |
| `closeout --decide --answer <response>` | Record the human's closeout decision. |
| `final` | Check completion gates, run final checks, and write report.md. |
| `check-docs <paths...> [--repo name=path] [--root <index>] [--strict]` | Check Markdown links and source citations; may run without a workflow. |

## Results and recovery

The brief names the exact result file and schema. The result file **is** the report;
record it only after checking that its claims match the actual work.

| Step | Brief | Result |
| --- | --- | --- |
| Research R1 | `recon/R1.brief.md` | `recon/R1.json` |
| Task author/tests/impl | `runs/T01/brief-<step>-<round>.md` | `runs/T01/result-<step>.json` |
| Task fix | `runs/T01/brief-fix-<round>.md` | `runs/T01/result-fix.json` |
| Per-task review | `runs/T01/brief-review-<n>.md` | `runs/T01/review-<n>.json` |
| Batch review/verification | `runs/B1/brief-<role>-<n>.md` | `runs/B1/<role>-<n>.json` |

`status --json` and `resume --json` return `artifacts`, `research_results`, `in_flight`,
`checkpoints`, `task_blocks`, `blocked`, `drift`, `actions`, and `estimates`. A checkpoint
includes brief/result paths, whether those files exist, and the original snapshot paths.
Old version-1 runs without explicit artifact paths are supported by deriving the same
filenames. No dispatch, result deletion, new workspace baseline, or task reset occurs on resume.
For legacy runs missing an approved task-contract snapshot, resume captures one only when
plan.json still matches the saved approval hash. A changed draft is never adopted as approved.
Inspect current workspace edits against saved snapshots; the record gates still validate
the original write fence and pinned tests. Resume does not adopt unrelated edits.

A JSON draft interrupted mid-write needs repair in that draft file. A malformed result
needs repair at its existing result path. Neither requires repeating completed work.
Contract drift must be resolved through restoration or the explicit revision path.

The `estimates` object in scope/plan uses nonnegative whole minutes for `scope`, `research`,
`planning`, `execution`, `review`, and `closeout`. Supply all stages on new runs; legacy runs
can have unknown stages. The plan supplies concrete execution/review estimates. Its total
is the sum when all stages are known; an old `budget_minutes` can supply a legacy total.
No estimate caps, scheduling deadlines, or duration-based completion gates apply.

## Decisions and correction paths

`resolve` always takes `--action` and `--answer`. Choose one target:

- `--exception --action answer`: resolve a workflow-level blocker.
- `--task T01`: answer/retry a blocked task, skip it, reopen it, or accept where permitted.
  `answer` may put a needs_input step back in flight: continue that brief without redispatch.
  `--rebaseline-tests` with answer/retry explicitly authorizes releasing a defective pinned
  test baseline; it must reflect the actual decision, not bypass a failure.
- `--review B1/doc-reviewer`: accept, retry, clear, or reopen as permitted by
  the saved review state. Reopen can use `--findings F1,F2` and `--assign F1=T01`.
  `--force` is only for an explicit decision to accept held blocking findings.
- `--noticed N`: settle an open noticed item. Numbers follow the helper's listing.

`--by human|manager` records who made a resolution. Never attribute a judgment to the human
without their answer. Existing contract decisions can settle repeated questions.

`amend` corrects paths, test commands/paths, checks, estimates, briefs, and sources of
unfinished tasks, plus permitted check/convention metadata. It does not authorize a new
deliverable, weaker acceptance criteria, or a different review policy. `widen` grows paths
without reopening accepted work. Material contract changes use human-approved revision.
Neither command grants shell, filesystem, network, or external-service permission.

The CLI reports errors and exits 2 when a contract or state gate fails. Correct the actual
problem; do not read a failed command as an instruction to start the pipeline over.
