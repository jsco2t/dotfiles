"""Dispatch briefs: small files an agent reads instead of a long prompt. Each one is a
complete contract for one step and ends with a file-based hand-back."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .common import limit, style_core

HEADER = ("This dispatch comes from /task-pipeline. This brief is your complete contract: it replaces any "
          "result format or report path your definition names. Do not start sub-agents with the `task` tool: "
          "the pipeline runs at most 3 agents and you are one of them. "
          "When you load a skill that can start sub-agents, pass it `--max-agents=0` and apply its lenses "
          "yourself, one after another. {box}")

RESULT_SCHEMA = ('{{"task": "{tid}", "step": "{step}", "status": "done | blocked | needs_input", '
                 '"summary": "<= 80 words, answer-first", "changed": ["<paths relative to the workspace>"], '
                 '"noticed": ["<one line per thing outside this task; never act on it>"], '
                 '"questions": ["<only with needs_input>"], "disputes": [{{"finding": "F1", "why": "<evidence>"}}]}}')

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
                       '"issue": "<complete sentence: what is wrong and what a reader or user would observe>", '
                       '"fix": "<what would make it right>"}}], "noticed": []}}')

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


def _handback(path: Path, schema: str) -> List[str]:
    return ["## Hand back", "", f"Write `{path}`:", "", "```json", schema, "```", "",
            f"Then reply with exactly one line: `RESULT {path}`. Nothing else — the file is the report."]


def _style() -> List[str]:
    return ["## Style (every sentence you write: summaries, findings, and the deliverable's prose "
            "unless its own conventions differ)", "", style_core(), ""]


def _conventions_line(ctx: Dict[str, Any]) -> List[str]:
    if not ctx.get("conventions"):
        return []
    return ["", "Conventions every task followed (judge the work by them too): "
            + "; ".join(f"`{c}`" for c in ctx["conventions"]) + "."]


def _decisions(ctx: Dict[str, Any]) -> List[str]:
    """Answers given during the run (question → answer): they settle those questions and win where
    the brief is silent or says otherwise. Nothing when there are none."""
    if not ctx.get("decisions"):
        return []
    return (["## Decisions made during the run", "",
             "Each settles its question; follow it where it differs from anything else in this brief.", ""]
            + [f"- {d}" for d in ctx["decisions"]] + [""])


def _task_body(task: Dict[str, Any], ctx: Dict[str, Any]) -> List[str]:
    out = ["## Task", "", f"{task['title']}. {task['brief']}", "",
           f"Serves: {ctx['serves']}. Full scope: `{ctx['scope_md']}`.", ""] + _decisions(ctx) + ["## Write only", ""]
    out += [f"- `{p}`" for p in ctx["write_paths"]]
    out += ["", "Any other change you think is needed: one line in `noticed`, never an edit."]
    if ctx["readonly"]:
        out += ["Read-only (never modify, build into, or leave files in): "
                + "; ".join(f"`{p}`" for p in ctx["readonly"]) + "."]
    out += ["", "## Start from", ""] + [f"- `{c}` (conventions for every task: read first)"
                                        for c in ctx.get("conventions", [])]
    out += [f"- `{s}`" for s in ctx["sources"]]
    out += ["", "Read anything in the read-only workspaces that an acceptance criterion needs (callers, "
            "tests, docs); the fence is on what you write, not on what you read."]
    out += ["", "## Done when", ""] + [f"- {a}" for a in task["acceptance"]]
    if ctx["checks"]:
        out += ["", "The pipeline then checks your work and fails the step unless: " + "; ".join(ctx["checks"]) + "."]
    return out + [""]


def author(task: Dict[str, Any], step: str, rnd: int, ctx: Dict[str, Any], result: Path) -> str:
    box = f"Time box: about {task['estimate_min']} min. If the task cannot fit, stop and hand back `blocked`."
    title = {"author": "author", "tests": "tests first", "impl": "implementation"}[step]
    out = [f"# /task-pipeline brief — {task['id']} {title}", "", HEADER.format(box=box), ""]
    if step == "tests":
        mode = task.get("test_mode", "red")
        out += ["## This step: tests only", "",
                f"Write the tests for this task first, in {', '.join(f'`{p}`' for p in ctx['tests_paths'])}. "
                + ("They must fail now, for the reason the task names (red): "
                   if mode == "red" else "They pin today's behaviour and must pass now: ")
                + f"`{task['test_cmd']}`. Do not write production code.", ""]
    elif step == "impl":
        out += ["## This step: implementation", "",
                f"Make the tests pass: `{task['test_cmd']}` must succeed. Do not edit the tests "
                f"({', '.join(f'`{p}`' for p in ctx['tests_paths'])}); if one is wrong, hand back `blocked` "
                "and say why.", ""]
    out += _task_body(task, ctx) + _style()
    return "\n".join(out + _handback(result, RESULT_SCHEMA.format(tid=task["id"], step=step))) + "\n"


def fix(task: Dict[str, Any], rnd: int, ctx: Dict[str, Any], findings: List[str], result: Path,
        same_agent: bool) -> str:
    out = [f"# /task-pipeline brief — {task['id']} fix round {rnd}", ""]
    if not same_agent:
        out += [HEADER.format(box=f"Time box: about {task['estimate_min']} min."), ""]
    out += ["## Fix", "", f"Round {rnd} of {ctx.get('cap', limit('max_fix_rounds'))}. Address every blocking item below: fix it, or "
            "dispute it with evidence in `disputes`. Change nothing else.", ""]
    out += [f"- {f}" for f in findings] + [""]
    if not same_agent:
        out += _task_body(task, ctx) + _style()
    else:
        out += _decisions(ctx) + ["Your task, paths, and style are unchanged from your first brief.", ""]
    return "\n".join(out + _handback(result, RESULT_SCHEMA.format(tid=task["id"], step="fix"))) + "\n"


def review(task: Dict[str, Any], n: int, ctx: Dict[str, Any], result: Path) -> str:
    out = [f"# /task-pipeline brief — {task['id']} review {n}", "",
           HEADER.format(box="Time box: about 10 min."), "", "## Review", "",
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


def research(rid: str, item: Dict[str, Any], scope_md: Path, surveys: List[Path], result: Path) -> str:
    purpose = item.get("purpose", "map")
    minutes = item.get("minutes", limit("research_item_minutes"))
    box = f"Time box: {minutes} min, hard. Planning research ({purpose}): {PURPOSE_FRAMING[purpose]}"
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


def batch_review(bid: str, reviewer: str, tasks: List[Dict[str, Any]], ctx: Dict[str, Any], result: Path) -> str:
    out = [f"# /task-pipeline review brief — {bid} · {reviewer}", "",
           HEADER.format(box="Time box: about 20 min for the batch."), "", "## Review this batch as a whole", "",
           f"Every task below is finished and accepted. Review them together, through your lens only, in one pass. "
           f"The change, as a structured file: `{ctx['changes']}` (files, and the exact diff command for each "
           "workspace under version control).", "", "Deliverables, by task:"]
    for t in tasks:
        out.append(f"- {t['id']} {t['title']}: " + ", ".join(f"`{p}`" for p in ctx["paths"][t["id"]]))
        out += [f"  - done when: {a}" for a in t["acceptance"]]
    if ctx.get("decisions"):
        out += [""] + _decisions(ctx)[:-1]
    out += _conventions_line(ctx)
    out += ["", "Check claims against: " + "; ".join(f"`{s}`" for s in ctx["sources"]) + ".", "",
            "Do not edit any file. Give each finding the workspace-relative path and line it is about, so the "
            "pipeline can route it to the task that owns the file. A finding is blocking when the work is wrong, "
            "misses a criterion, or would mislead or break things for its reader or user. `verdict` is `changes` "
            "exactly when a finding is blocking. Verify each finding against the source before you report it. "
            "Anything outside these deliverables is one line in `noticed`.", ""]
    out += _style()
    return "\n".join(out + _handback(result, BATCH_REVIEW_SCHEMA.format(bid=bid))) + "\n"


def verify(bid: str, reviewer: str, findings: List[Dict[str, Any]], ctx: Dict[str, Any], result: Path,
           same_agent: bool) -> str:
    out = [f"# /task-pipeline verification brief — {bid} · {reviewer}", ""]
    if not same_agent:
        out += [HEADER.format(box="Time box: about 8 min."), ""]
    out += ["## Verify the fixes", "",
           "The authors have addressed the findings below that the manager accepted. For each one, check whether "
           "it is resolved; do not start a new review. Report only findings that are still unresolved, and any new "
           f"problem the fixes themselves introduced. The change: `{ctx['changes']}`. Do not edit any file.", ""]
    if ctx.get("decisions"):
        out += _decisions(ctx)
    out += [f"- {f['id']} ({f['state']}) at {f['where']}: {f['issue']}" for f in findings] + [""]
    return "\n".join(out + _handback(result, VERIFY_SCHEMA.format(bid=bid))) + "\n"


def prompt(brief: Path, result: Path) -> str:
    return f"Read and follow {brief}. When done, reply with exactly one line: RESULT {result}"


def dispatch_line(agent: str, desc: str, text: str, agent_id: Optional[str], model: Optional[str]) -> str:
    """The manager's OpenCode `task` call, as a literal. agent_id resumes that agent's session."""
    if agent_id:
        return f"task(task_id={json.dumps(agent_id)}, prompt={json.dumps(text)})"
    extra = f", model={json.dumps(model)}" if model else ""
    return (f"task(subagent_type={json.dumps(agent)}, description={json.dumps(desc)}{extra}, "
            f"prompt={json.dumps(text)})")
