"""Dispatch briefs: small files an agent reads instead of a long prompt. Each one is a
complete contract for one step and ends with a file-based hand-back."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .common import limit, style_core

# Every turn re-reads the agent's whole context, and in past runs nine turns in ten made one call.
WORKING_RULES = ("**Working rules.** Batch independent reads and searches into one message, as parallel tool "
                 "calls. Read each region once, in one window. Never re-run a suite or build the pipeline already "
                 "ran: read the log this brief names; run only a targeted check of what you changed.")
HEADER = ("This dispatch comes from /task-pipeline. This brief is your complete contract: it replaces any "
          "result format or report path your definition names. Do not use the Agent tool: the pipeline "
          "runs at most 3 agents and you are one of them. "
          "When you load a skill that can start sub-agents, pass it `--max-agents=0` and apply its lenses "
          "yourself, one after another. {box}\n\n" + WORKING_RULES)

RESULT_SCHEMA = ('{{"task": "{tid}", "step": "{step}", "status": "done | blocked | needs_input", '
                 '"summary": "<= 80 words, answer-first", "changed": ["<paths relative to the workspace>"], '
                 '"acceptance": [{{"criterion": 1, "evidence": "<path:line, command and result, or where it shows>"}}], '
                 '"noticed": ["<one line per problem outside this task that someone must act on — not notes about your own work; never act on it>"], '
                 '"questions": ["<only with needs_input>"], "disputes": [{{"finding": "F1", "why": "<evidence>"}}]}}')
EVIDENCE_NOTE = ("With `done` from an authoring or implementation step, `acceptance` gives every numbered Done-when "
                 "item its evidence; a hand-back that leaves one out is refused.")


def _estimate(what: str) -> str:
    """The minutes a step was planned at: an estimate for forecasting, never a deadline."""
    return f"Estimate: about {what} — a planning figure, not a deadline."

REVIEW_SCHEMA = ('{{"task": "{tid}", "verdict": "pass | changes", "findings": [{{"id": "F1", '
                 '"state": "wrong | missing | unclear | broken | gap | weak | cosmetic", "blocking": true, '
                 '"confidence": 90, "where": "path:line", "issue":"<complete sentence: what is wrong and what a reader would observe>", '
                 '"fix": "<what would make it right>"}}], "noticed": []}}')

RESEARCH_SCHEMA = ('{"answers": [{"q": "<the question>", "a": "<the answer>", "evidence": ["path:line, URL, or issue key"]}], '
                   '"followups": [{"question": "<one narrow question you did not pursue>", "why": "<what you saw>", '
                   '"agent": "<who could answer it>"}], "unknowns": ["<what you could not establish>"]')  # + areas + "}"
MAP_AREAS = ', "areas": [{"name": "...", "paths": ["..."], "size": "<files / lines>", "note": "..."}]'

BATCH_REVIEW_SCHEMA = ('{{"batch": "{bid}", "verdict": "pass | changes", "findings": [{{"id": "F1", '
                       '"state": "wrong | missing | unclear | broken | gap | weak | cosmetic", "blocking": true, '
                       '"confidence": 90, "where": "<workspace-relative path>:<line>", "task": "<T## if you know it>", '
                       '"lens": "<the lens that found it, when you run several>", '
                       '"issue": "<complete sentence: what is wrong and what a reader or user would observe>", '
                       '"fix": "<what would make it right>"}}], '
                       '"near_misses": ["<path:line · confidence · the issue in one sentence>"], "noticed": []}}')

VERIFY_SCHEMA = ('{{"batch": "{bid}", "verdict": "pass | changes", "findings": [<only findings still unresolved, '
                 'or new problems the fixes introduced, same shape as your first review>]}}')

PURPOSE_FRAMING = {
    "map": "Map how the work divides — areas, paths, sizes — so the manager can split it into tasks. "
           "Do not research or write the deliverable's content; each task researches its own area later.",
    "requirements": "Extract what the named issues or pages require: acceptance criteria, constraints, "
                    "decisions, and open questions, each with its source (issue key, page, or comment). "
                    "Report what they say; do not design the solution.",
    "investigate": "Establish how the one named thing works, with `path:line` evidence for every claim. "
                   "Stay on that thing; do not survey its neighbours.",
}


def _handback(path: Path, schema: str, note: str = "") -> List[str]:
    return (["## Hand back", "", f"Write `{path}`:", "", "```json", schema, "```", ""] + ([note, ""] if note else [])
            + [f"Then reply with exactly one line: `RESULT {path}`. Nothing else — the file is the report."])


def _style() -> List[str]:
    return ["## Style (every sentence you write: summaries, findings, and the deliverable's prose "
            "unless its own conventions differ)", "", style_core(), ""]


def _decisions(ctx: Dict[str, Any]) -> List[str]:
    """Answers given during the run (question → answer): they settle those questions and win where the
    brief is silent or says otherwise. Nothing when there are none."""
    if not ctx.get("decisions"):
        return []
    return (["## Decisions made during the run", "",
             "Each settles its question. Answers marked (human) win where they differ from anything else in this "
             "brief; any other answer clarifies it and never removes or loosens a Done-when item.", ""]
            + [f"- {d}" for d in ctx["decisions"]] + [""])


def _conventions_line(ctx: Dict[str, Any]) -> List[str]:
    if not ctx.get("conventions"):
        return []
    return ["", "Conventions every task followed (judge the work by them too): "
            + "; ".join(f"`{c}`" for c in ctx["conventions"]) + "."]


def _task_body(task: Dict[str, Any], ctx: Dict[str, Any]) -> List[str]:
    out = ["## Task", "", f"{task['title']}. {task['brief']}", "",
           f"Serves: {ctx['serves']}. Full scope: `{ctx['scope_md']}`.", ""] + _decisions(ctx) + ["## Write only", ""]
    out += [f"- `{p}`" for p in ctx["write_paths"]]
    out += ["", "Any other change you think is needed: one line in `noticed`, never an edit."]
    if ctx["readonly"]:
        out += ["Read-only (never modify, build into, or leave files in): "
                + "; ".join(f"`{p}`" for p in ctx["readonly"]) + "."]
    conventions = ctx.get("conventions", [])
    out += ["", "## Start from", ""] + [f"- `{c}` (conventions for every task: read first)" for c in conventions]
    out += [f"- `{s}`" for s in ctx["sources"] if s not in conventions]
    out += ["", "Read anything in the read-only workspaces a criterion needs: the fence is on writes, not reads."]
    if ctx.get("logs"):
        out += ["", "Logs the pipeline already produced (read them; do not re-run these commands): "
                + "; ".join(f"`{p}`" for p in ctx["logs"]) + "."]
    out += ["", "## Done when", ""] + [f"{i}. {a}" for i, a in enumerate(task["acceptance"], 1)]
    if ctx["checks"]:
        out += ["", "The pipeline then checks your work and fails the step unless: " + "; ".join(ctx["checks"]) + "."]
    out += ["", "If the brief is ambiguous in a way that changes what you deliver, hand back `needs_input` with the "
            "question instead of guessing."]
    return out + [""]


def author(task: Dict[str, Any], step: str, rnd: int, ctx: Dict[str, Any], result: Path) -> str:
    box = (_estimate(f"{task['estimate_min']} min") + " Do the whole task. If it turns out bigger than its brief "
           "(files, behaviour, or topics the brief does not name), stop and hand back `blocked` saying what — "
           "never cut it down to fit, and never grow it.")
    title = {"author": "author", "tests": "tests first", "impl": "implementation",
             "build": "tests first, then the implementation"}[step]
    out = [f"# /task-pipeline brief — {task['id']} {title}", "", HEADER.format(box=box), ""]
    if step == "tests":
        mode = task.get("test_mode", "red")
        out += ["## This step: tests only", "",
                f"Write the tests for this task first, in {', '.join(f'`{p}`' for p in ctx['tests_paths'])}. "
                + ("They must fail now, for the reason the task names (red): "
                   if mode == "red" else "They pin today's behaviour and must pass now: ")
                + f"`{task['test_cmd']}`. Touch no file outside the test paths — no production code, no "
                "stubs, no 'temporary' implementations: the red check fails the step for tests that already "
                "pass, and the implementation is the next agent's step.", ""]
    elif step == "build":
        out += _build_step(task, ctx)
    elif step == "impl":
        out += ["## This step: implementation", "",
                f"Make the tests pass: `{task['test_cmd']}` must succeed. Do not edit the tests "
                f"({', '.join(f'`{p}`' for p in ctx['tests_paths'])}); if one is wrong, hand back `blocked` "
                "and say why.", ""]
    elif ctx.get("kind") == "integration":
        out += INTEGRATION
    out += _task_body(task, ctx) + _style()
    return "\n".join(out + _handback(result, RESULT_SCHEMA.format(tid=task["id"], step=step), EVIDENCE_NOTE)) + "\n"


def _build_step(task: Dict[str, Any], ctx: Dict[str, Any]) -> List[str]:
    """One fused round: tests first, observed by the pipeline, then the implementation."""
    tests = ", ".join(f"`{p}`" for p in ctx["tests_paths"])
    mode = task.get("test_mode", "red")
    if mode == "existing":
        return ["## This step: change the code; the existing tests prove it", "",
                f"The current tests ({tests}) already prove this task's criteria: write no new tests unless a "
                f"criterion is unproven. Make the change and keep `{task['test_cmd']}` green. Never weaken or "
                "delete a test to make the change pass; tests of code this task removes go with it (say so in "
                "`summary`).", ""]
    return ["## This step: tests first, then the implementation — one round", "",
            f"1. Write the tests in {tests}. Touch no production file yet.",
            f"2. Run `{ctx['red_cmd']}`. The pipeline runs `{task['test_cmd']}` and records it: "
            + ("the tests must **fail**, for the reason the task names. A suite that cannot load (an import, "
               "fixture, or build error unrelated to the missing behaviour) is not red: fix it and run again."
               if mode == "red" else "the tests must **pass** against today's code (they pin its behaviour).")
            + " It refuses while any production file has changed.",
            f"3. Implement until `{task['test_cmd']}` passes. You may add tests; never loosen or remove one you "
            "wrote. If a test proves wrong, fix it and say why in `summary` — the review checks it.", ""]


def _fix_step(ctx: Dict[str, Any], task: Dict[str, Any]) -> List[str]:
    """What kind of fix round this is, when the review routed it: test files only, or a failing
    test first for a behaviour bug the code author fixes next."""
    tests = ", ".join(f"`{p}`" for p in ctx.get("tests_paths", []))
    if ctx.get("fix_expect") == "red":
        return ["## This round: a failing test first", "",
                f"For each finding below, write a test in {tests} that fails on the current code because of the "
                f"finding (red): `{task['test_cmd']}` must fail, for that reason. Do not touch production code — the "
                "code author fixes it next, against your test. If a finding is not a real bug, dispute it.", ""]
    if ctx.get("fix_expect") == "green":
        return ["## This round: test files only", "",
                f"Change only the test files ({tests}); `{task['test_cmd']}` must still pass. Do not touch "
                "production code.", ""]
    if ctx.get("fixing") == "impl" and ctx.get("tests_paths"):
        return ["## This round: production code only", "",
                f"The test files ({tests}) belong to the test author: do not edit them. If a test is wrong, "
                "dispute it in `disputes` and the pipeline routes it to the test author.", ""]
    return []


def fix(task: Dict[str, Any], rnd: int, ctx: Dict[str, Any], findings: List[str], result: Path,
        same_agent: bool) -> str:
    out = [f"# /task-pipeline brief — {task['id']} fix round {rnd}", ""]
    if not same_agent:
        out += [HEADER.format(box=_estimate(f"{task.get('estimate_min', 5)} min")), ""]
    out += _fix_step(ctx, task)
    out += ["## Fix", "", f"Round {rnd} of {ctx.get('cap', limit('max_fix_rounds'))}. Address every blocking item below: fix it, or "
            "dispute it with evidence in `disputes`. Change nothing else.", ""]
    out += [f"- {f}" for f in findings] + [""]
    if not same_agent:
        out += _task_body(task, ctx) + _style()
    else:
        out += _decisions(ctx) + ["Your task, paths, and style are unchanged from your first brief.", ""]
    return "\n".join(out + _handback(result, RESULT_SCHEMA.format(tid=task["id"], step="fix"), EVIDENCE_NOTE)) + "\n"


def review(task: Dict[str, Any], n: int, ctx: Dict[str, Any], result: Path) -> str:
    out = [f"# /task-pipeline brief — {task['id']} review {n}", "",
           HEADER.format(box=_estimate("10 min") + " Review fully."), "", "## Review", "",
           f"Task under review: {task['title']}. {task['brief']}", "", "Deliverables:"]
    out += [f"- `{p}`" for p in ctx["write_paths"]]
    out += ["", "Check claims against:"] + [f"- `{s}`" for s in ctx["sources"]]
    out += _conventions_line(ctx)
    out += ["", "Acceptance criteria:"] + [f"- {a}" for a in task["acceptance"]]
    if ctx.get("disputes"):
        out += ["", f"Rule on the author's disputes in `{ctx['disputes']}`."]
    if ctx.get("decisions"):
        out += [""] + _decisions(ctx)[:-1]
    out += ["", "Do not edit any file. Judge only this task's deliverables against its criteria and sources; "
            "anything else is one line in `noticed`. A finding is blocking when the deliverable is wrong, "
            "misses a criterion, or would mislead its reader. `verdict` is `changes` exactly when a finding "
            "is blocking. Verify each finding against the source before you report it.", ""]
    out += _style()
    return "\n".join(out + _handback(result, REVIEW_SCHEMA.format(tid=task["id"]))) + "\n"


INTEGRATION = ["## This step: integration (transport only)", "",
               "You move approved content between systems; you never write or verify it. Take the content "
               "verbatim from the files this brief names (accepted task results, documents at HEAD, `wf:` drafts). "
               "Use Bash only for the toolkit CLI and for reading files: never run builds, tests, fixtures, or "
               "scripts against the repository, and never compose new technical claims — if the content looks "
               "wrong or stale, hand back `needs_input` saying what. Dry run first; the write happens only after "
               "the human's OK reaches you.", ""]


def research(rid: str, item: Dict[str, Any], scope_md: Path, surveys: List[Path], result: Path) -> str:
    purpose = item.get("purpose", "map")
    minutes = item.get("minutes", limit("research_item_minutes"))
    box = _estimate(f"{minutes} min") + f" Planning research ({purpose}): {PURPOSE_FRAMING[purpose]}"
    out = [f"# /task-pipeline research brief — {rid}", "", HEADER.format(box=box), "", "## Questions", ""]
    out += [f"{i}. {q}" for i, q in enumerate(item["questions"], 1)]
    out += ["", f"Done when: {item['done_when']}", "",
            "Answer these questions and nothing else. When you find something that needs more investigation, "
            "do not investigate it: write it as one narrow question in `followups`, with what you saw. The "
            "manager decides whether it becomes another research item.", "",
            "## Context", "", f"- Scope: `{scope_md}`"]
    out += [f"- Survey already done (do not repeat it): `{s}`" for s in surveys]
    out += ["", _style()[0], "", style_core(), ""]
    out += _handback(result, RESEARCH_SCHEMA + (MAP_AREAS if purpose == "map" else "") + "}")
    out.insert(-1, f"At most {limit('research_output_bytes')} bytes; a larger file is refused.")
    return "\n".join(out) + "\n"


def _lenses(ctx: Dict[str, Any]) -> List[str]:
    """A packed session's lenses: each reviewer's own definition, applied as its own full pass."""
    if not ctx.get("lenses"):
        return []
    out = ["## Your lenses — run each as its own full pass", "",
           "Apply every lens below to the whole change, one after another, each with its whole responsibility "
           "list and full rigour. Sharing what you have read between lenses is the point; blending two lenses "
           "into one vaguer pass, or skipping one, is not. Name each lens in every finding (`lens`), and report "
           "a lens that found nothing as `<lens>: no issues found` in `noticed`.", ""]
    for name, text in ctx["lenses"]:
        out += [f"### Lens: {name}", "", text.strip(), ""]
    return out


def _report_floor(ctx: Dict[str, Any]) -> List[str]:
    full, near = ctx.get("full_floor", 70), ctx.get("near_floor", 60)
    return [f"Report only what triage can use: full findings at confidence {full} or more; {near}–{full - 1} as one "
            f"line each in `near_misses` (`path:line · confidence · one sentence`); nothing lower. A near miss is "
            "never routed to an author.", ""]


def _shared_files(ctx: Dict[str, Any]) -> List[str]:
    out = []
    if ctx.get("diff_file"):
        out.append(f"The change as one diff (tracked changes against the approval baseline, then new files in "
                   f"full): `{ctx['diff_file']}` — read it in as few calls as you can instead of running git yourself.")
    if ctx.get("logs"):
        out.append("The pipeline already ran each task's tests and checks; their logs: "
                   + "; ".join(f"`{p}`" for p in ctx["logs"]) + ". Read them instead of re-running the suite; write "
                   "any targeted throwaway test under `$TMPDIR`, never in a workspace.")
    return out + ([""] if out else [])


def batch_review(bid: str, reviewer: str, tasks: List[Dict[str, Any]], ctx: Dict[str, Any], result: Path) -> str:
    out = [f"# /task-pipeline review brief — {bid} · {reviewer}", "",
           HEADER.format(box=_estimate("20 min for the batch") + " Review fully."), "",
           "## Review this batch as a whole", "",
           "Every task below is finished and accepted. Review them together, "
           + ("through each lens below, " if ctx.get("lenses") else "through your lens only, ")
           + f"in one pass. The change, as a structured file: `{ctx['changes']}` (files, and the exact diff command "
           "for each workspace under version control).", ""]
    out += _shared_files(ctx)
    out += ["Deliverables, by task:"]
    for t in tasks:
        out.append(f"- {t['id']} {t['title']}: " + ", ".join(f"`{p}`" for p in ctx["paths"][t["id"]]))
        out += [f"  - done when: {a}" for a in t.get("acceptance", [])]
    if ctx.get("decisions"):
        out += [""] + _decisions(ctx)[:-1]
    if ctx.get("manager_calls"):
        out += ["", "## Gates the manager settled — judge each one", "",
                "No human saw these. For each, decide whether it is sound; one that loosens a test or hides a "
                "defect is a blocking finding on that task.", ""] + [f"- {c}" for c in ctx["manager_calls"]]
    out += _conventions_line(ctx)
    out += ["", "Check claims against: " + "; ".join(f"`{s}`" for s in ctx["sources"]) + ".", "",
            "Do not edit any file. Give each finding the workspace-relative path and line it is about, so the "
            "pipeline can route it to the task that owns the file. A finding is blocking when the work is wrong, "
            "misses a criterion, or would mislead or break things for its reader or user. `verdict` is `changes` "
            "exactly when a finding is blocking. Verify each finding against the source before you report it. "
            "Anything outside these deliverables is one line in `noticed`.", ""]
    out += _report_floor(ctx) + _lenses(ctx)
    out += _style()
    return "\n".join(out + _handback(result, BATCH_REVIEW_SCHEMA.format(bid=bid))) + "\n"


def verify(bid: str, reviewer: str, findings: List[Dict[str, Any]], ctx: Dict[str, Any], result: Path,
           same_agent: bool) -> str:
    out = [f"# /task-pipeline verification brief — {bid} · {reviewer}", ""]
    if not same_agent:
        out += [HEADER.format(box=_estimate("8 min")), ""]
    out += ["## Verify the fixes", "",
           "The authors have addressed the findings below that the manager accepted. For each one, check whether "
           "it is resolved; do not start a new review. Report only findings that are still unresolved, and any new "
           f"problem the fixes themselves introduced. The change: `{ctx['changes']}`. Do not edit any file.", ""]
    out += _shared_files(ctx)
    out += [f"- {f['id']} ({f['state']}) at {f['where']}: {f['issue']}" for f in findings] + [""]
    return "\n".join(out + _handback(result, VERIFY_SCHEMA.format(bid=bid))) + "\n"


def prompt(brief: Path, result: Path) -> str:
    return f"Read and follow {brief}. When done, reply with exactly one line: RESULT {result}"


def dispatch_line(agent: str, desc: str, text: str, agent_id: Optional[str], model: Optional[str]) -> str:
    if agent_id:
        return f"SendMessage(to={json.dumps(agent_id)}, message={json.dumps(text)})"
    extra = f", model={json.dumps(model)}" if model else ""
    return (f"Agent(subagent_type={json.dumps(agent)}, description={json.dumps(desc)}{extra}, "
            f"prompt={json.dumps(text)})")


PLAN_REVIEW_SCHEMA = ('{{"review": "plan", "round": {rnd}, "verdict": "pass | changes", '
                      '"findings": [{{"id": "F1", "state": "missing | narrowed | wrong | unnecessary | infeasible | '
                      'unresolved", "requirement": "<R# or the request line it is about>", '
                      '"issue": "<complete sentence: what the plan gets wrong and what that would ship>", '
                      '"fix": "<what would make the plan right>"}}], '
                      '"coverage": [{{"requirement": "R1", "covered": true, "tasks": ["T01"], '
                      '"note": "<the criterion that fails if R1 is unmet>"}}], '
                      '"observations": ["<worthwhile and non-blocking>"]}}')


def plan_review(rnd: int, ctx: Dict[str, Any], result: Path) -> str:
    """The independent plan reviewer's brief: the plan against the request, the human's answers, and
    the requirements ledger, bound to one plan revision. Its verdict replaces the human's approval."""
    out = [f"# /task-pipeline plan review — round {rnd}", "",
           HEADER.format(box=_estimate("10 min") + " Review the whole plan."), "",
           "## What you review", "",
           f"The delivery plan `{ctx['plan_md']}` (readable) and `{ctx['plan_json']}` (exact), against the request "
           f"below, the human's answers, and the settled scope `{ctx['scope_md']}`. Your verdict is the only gate "
           "between this plan and its execution: nobody approves it after you, and execution runs without the "
           "human. You did not write the plan and will not carry it out. Edit nothing.", "",
           "## The request, verbatim", "", "```text", str(ctx["request"]).strip(), "```", ""]
    if ctx.get("issues"):
        out += ["Issue texts surveyed for this run (their acceptance criteria are requirements too): "
                + "; ".join(f"`{p}`" for p in ctx["issues"]) + ".", ""]
    if ctx.get("requirements"):
        out += ["## Requirements ledger (every one must be covered)", ""]
        out += [f"- **{r['id']}** — {r.get('text', '')}" + (f" — source: “{r['source']}”" if r.get("source") else "")
                for r in ctx["requirements"]] + [""]
    if ctx.get("answers"):
        out += ["## Settled with the human (these are not open questions)", ""]
        out += [f"- {a}" for a in ctx["answers"]] + [""]
    if ctx.get("noticed"):
        out += ["## Noticed during planning (not in the plan)", ""] + [f"- {n}" for n in ctx["noticed"]] + [""]
    if ctx.get("prior"):
        out += ["## Your previous round", "",
                "The plan was revised since. Check each earlier finding is resolved, then review the whole plan "
                "again: a revision can open a new gap. Where the manager dismissed a finding, its reason is shown; "
                "keep the finding only if the reason does not hold.", ""] + [f"- {p}" for p in ctx["prior"]] + [""]
    out += ["## Check, in order", "",
            "1. **Coverage.** Each requirement is served by a task whose acceptance criteria would fail if it were "
            "unmet. A task title is not coverage.",
            "2. **Narrowing.** Read each requirement's source words (and the issue's acceptance text) against the "
            "criteria meant to prove it. Fewer cases, nodes, platforms, or callers than the words say is a "
            "`narrowed` finding — unless a settled answer above allows it.",
            "3. **Prohibitions.** Anything the request says not to do (\"do not defer\", \"no new tickets\", \"test "
            "first\"): a task, deferral, or follow-up ticket that does it is `wrong`.",
            "4. **Missing work.** What the request plainly needs that no task does: verification, integration, the "
            "delivery destination it names.",
            "5. **Unnecessary work.** A task no requirement needs, however good an idea, is `unnecessary`.",
            "6. **Feasible verification.** Each code task's `test_cmd` can run in its workspace; `test_mode` fits "
            "(red: new behaviour; pin: preserve behaviour; existing: current tests already prove it — removals, "
            "ports, refactors). Criteria without a mechanical check are concrete enough to judge by reading.",
            "7. **Structure.** Dependencies are honest (a task that needs another's output says so); parallel "
            "tasks write disjoint files; a shared file has one owner.",
            "8. **Unresolved.** A decision the plan depends on that nobody has made. Name it; the manager asks the "
            "human before execution, so it must surface now.", "",
            "Ground every finding in a requirement, a request line, or a settled answer you can quote; anything "
            "else is an observation. Finding nothing is a valid, expected outcome: say so and pass the plan.", ""]
    out += _style()
    note = (f"`coverage` has one entry per requirement. `pass` only with every requirement covered and no "
            "findings; `changes` with at least one finding.")
    return "\n".join(out + _handback(result, PLAN_REVIEW_SCHEMA.format(rnd=rnd), note)) + "\n"
