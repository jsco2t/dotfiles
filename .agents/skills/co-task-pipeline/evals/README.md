# Evaluation status for the autonomous workflow

The historical agent scenarios below intentionally initialize with `--legacy-approvals` so
existing measurements, prompts and graders retain their original contract. They are not
performance evidence for the new autonomous default. The autonomous runtime is covered by
`tests/test_autonomous.py`, including independently recorded plan acceptance, real isolated
baseline reproduction for an honest test correction, dirty verification, compact checkpoint
storage and artifact rules. Those are scripted regressions, not real-agent timing/token trials.

See [hidlins-execution-audit.md](hidlins-execution-audit.md) for the two supplied run audits and
[efficiency-plan.md](efficiency-plan.md) for the implementation plan/review decisions. Future
complete-run comparisons must use the same request, model, hardware/environment and required
quality gates; record actual usage/waits instead of inferring token savings from helper counts.

# Historical complete-run evaluations

`evaluate.py` prepares small isolated tasks for a real agent, grades delivered behavior
independently, and compares compatible runs. Python standard library only. It does not
launch Codex, replay invented agent conversations, or turn scripted helper traces into
agent performance evidence.

The implemented follow-up was validated with actual agents and the complete regression suite;
see [RESULTS.md](RESULTS.md) for the dated outcomes, measurements and limits.

| Scenario | Required behavior | Independent quality gate |
| --- | --- | --- |
| `clean-review` | Review a correct library, preserve sources, write evidence, finish one cycle; reuse scoped unit results after writing the review | Held-out behavior, no false positives, write allowlist, completed workflow/review/check evidence |
| `multi-repair` | Repair three small defects in one adaptive cycle, discovering and closing each with an incremental regression checkpoint | Held-out edge cases, mutation checks proving tests catch each defect, three ordered repair steps with retained red/green evidence |
| `research-map` | Trace a three-file call path and write `map.json` without expanding into a full audit | Exact graph, normalization, storage and source citations; unchanged source files |
| `unavailable-check` | Run the mandatory unavailable command and preserve a blocked workflow | Actual failed check log, pending operator question, no false completion or replacement check |
| `interruption` | Halt after failing tests, then resume the same running task from partial work | Held-out behavior plus ordered checkpoint/halt/resume/done evidence and retained test pin |
| `recovery-cycle` | Halt at the first of three repair checkpoints; adopt an evaluator-owned unrelated edit and approved scope amendment on resume; finish all repairs | Held-out behavior/mutation gates, exact operator edit, active pin retained in current and archived evidence, ordered halt/resume/amendment/completion |

Every fixture includes pre-existing operator notes that must survive unchanged. The default
agent allowance is zero. `--max-agents 1` permits a bounded read-only research/review handoff
and asks the agent to record its actual identity and packet; it never requires unnecessary
delegation. Current grading enforces the recorded allowance. Tool transcripts should be
reviewed for unrecorded agents, premature investigation, redundant reads and oversized context.

## Run a real agent

Run from this skill's directory, or substitute absolute script paths:

```bash
python3 -B evals/evaluate.py prepare multi-repair /tmp/tp-eval-candidate-01
```

The command prints an agent prompt path, workflow path and evaluator oracle path. It freezes
only the target skill runtime in `agent/skill/` (scripts, references and SKILL.md), excluding
grader, tests and oracle. Grading rejects runtime edits. Nothing has executed beyond helper
initialization; the contracts remain **unapproved**. Inspect
the prompt, scope and plan. Start a fresh agent session with only:

- The actual skill available, and the prepared `agent/` directory as its writable task area.
- The contents of `agent/agent-prompt.txt` sent as the evaluator's **actual operator message**.
- A recorded model, reasoning setting, tool/agent allowance and runtime configuration.

The prompt explicitly confirms the supplied concrete scope and plan. Sending it is the
operator authorization; the agent records those exact words after checking the contracts.
Do not claim that generated text was an operator response if no evaluator actually sent it.
Do not seed completed task state or solve the task before the agent runs. For `interruption`,
wait until the first session really halts, then send `agent/resume-prompt.txt` as the actual
resume instruction; preserve the same workflow and workspace.

Keep `oracle/`, grader code and run records outside the agent's mounted/readable task area
where runtime isolation supports that. The agent needs read-only access to the skill/helper,
not evaluator expected outputs. Without separate mounts, the prompt prohibition is a trust
boundary, not filesystem enforcement. The agent must not inspect oracle/grader sources.
The grader executes delivered Python with a timeout, so run it in the same restricted local
sandbox used for fixture code. It cannot prove absence of writes outside that sandbox.

For `recovery-cycle`, let the first real session halt at the first repair's red checkpoint.
Then the **evaluator**, outside the agent session, runs:

```bash
python3 -B evals/evaluate.py stage-recovery /tmp/tp-eval-recovery-01/oracle/expected.json
```

This stages only the exact unrelated `operator-update.txt`; it requires the saved halt and
real pending regression, refuses to overwrite an existing edit, and never changes pipeline
state or records approval. Send the printed `resume-prompt.txt` as the evaluator's actual
next operator message. It approves the supplied concrete scope amendment and adoption;
the agent must preserve evidence through both. Grade after final delivery as usual.
The new scenario has scripted regression coverage; it has not yet been run by a real agent.

After the agent finishes or legitimately blocks, the **evaluator** writes a record outside
`agent/`, for example `oracle/run.json`:

```json
{
  "kind": "actual-agent",
  "source": "host run/session identifier or exported transcript receipt",
  "agent_id": "actual host agent/session identifier",
  "config": {"model": "unreported", "reasoning_effort": "unreported",
             "requested_model": "requested-model", "requested_reasoning_effort": "requested-setting"},
  "tool_log": "observed.jsonl"
}
```

Keep requested settings separate from runtime-reported identity. A model override or an
agent's own claim does not prove which model actually served the run. Populate `model` and
`reasoning_effort` from host-reported metadata when available; otherwise use `unreported`,
retain the requested values separately, and disclose that actual identity/settings are unknown.
Record any host fallback explicitly rather than relabeling it as the requested configuration.

`tool_log` is optional and relative to the record directory, or an absolute path. Export
real host evidence; do not fabricate a transcript to satisfy the grader. A normalized log
can contain these event forms (omit unavailable fields):

```jsonl
{"kind":"run-start","at":"2026-11-03T10:00:00+00:00"}
{"kind":"tool_call","name":"functions.exec","helper":true,"context_bytes":800}
{"kind":"usage","input_tokens":1200,"output_tokens":200,"cached_input_tokens":500}
{"kind":"run-end","at":"2026-11-03T10:00:05+00:00"}
```

Normalize each actual call/usage receipt exactly once; `helper` explicitly identifies calls
invoking the pipeline helper. `context_bytes` measures the observed context sent in those
calls, not token usage. Missing token fields, partially covered counts and unobserved context
stay `null`/`unmeasured`. Optional `measurements` may supply observed nonnegative totals
(`elapsed_seconds`, `helper_calls`, `tool_calls`, `input_tokens`, `output_tokens`,
`cached_input_tokens`, `context_bytes`, `approval_wait_seconds`, `delegation_seconds`) with a
`source` identifying the actual receipt/log. A total that disagrees with the normalized log
is rejected. Helper history additionally supplies check executions/reuse, check duration,
repair count and agent records. Helper telemetry measures `mutating_helper_calls` and their
duration; read-only calls require host evidence and are not counted in that field; workflow wall time includes operator waits and halts.
Do not put estimated tokens or modeled savings in these fields.

```bash
python3 -B evals/evaluate.py grade /tmp/tp-eval-candidate-01/oracle/expected.json \
  --record /tmp/tp-eval-candidate-01/oracle/run.json \
  --output /tmp/tp-eval-candidate-01/oracle/grade.json
```

Exit 0 means the quality gates pass, 1 means a quality failure, 2 means an invalid invocation
or evidence format. Without a run record, results are explicitly `unverified`. Records are
trusted evaluator provenance, not cryptographic authentication. Artifact behavior and
unintended edits are judged from the held-out oracle, independently of agent verdicts.

## Compare changes

Prepare a fresh fixture for each revision; keep the scenario, agent configuration and runtime
settings the same. Run several repetitions for timing conclusions; one successful run proves
that execution worked, not a reliable speedup. Record hardware/runtime differences in the
configuration. Then:

```bash
python3 -B evals/evaluate.py compare /tmp/tp-eval-baseline-01/oracle/grade.json \
  /tmp/tp-eval-candidate-01/oracle/grade.json --output /tmp/tp-eval-comparison.json
```

Comparison rejects mismatched scenarios, fixture versions, agent/model settings, allowances
or execution provenance. It reports metrics only for **quality-passing** runs and lists
failed runs separately. No fastest-run winner or synthetic efficiency score rewards wrong
work. The helper revision is recorded separately so behavior before/after an implementation
change can be compared. Null values are not zero costs.

## Scripted smoke/regression checks

```bash
python3 -B -m unittest discover -s tests -p test_evals.py -v
```

These tests script actual helper commands against temporary files to validate preparation,
grading, unavailable checks, resume preservation and quality-aware comparison. They also
prove faulty solutions, ineffective regressions, invented review defects and unintended
content/mode/symlink edits fail independent grading. They are **not actual-agent evaluation
runs**. A scripted diagnostic record must use `kind: scripted-smoke`, never `actual-agent`.
Keep exported real-agent grades separate from unit-test output and disclose which scenarios
were actually run, which remain unrun and which measurements are unavailable.
