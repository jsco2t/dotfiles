"""Dispatch briefs: small files an agent reads instead of a long prompt. Each one is a
complete contract for one step and ends with a file-based hand-back."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .common import limit, style_core

HEADER = ("This dispatch comes from /task-pipeline. This brief is your complete contract: it replaces "
          "the task-orchestrator contract, the `orch-result` block, and any report path your definition "
          "names. Do not use the Agent tool or any skill that dispatches sub-agents — apply your skill's "
          "method yourself, in one pass. {box}")

RESULT_SCHEMA = ('{{"task": "{tid}", "step": "{step}", "status": "done | blocked | needs_input", '
                 '"summary": "<= 80 words, answer-first", "changed": ["<paths relative to the workspace>"], '
                 '"noticed": ["<one line per thing outside this task; never act on it>"], '
                 '"questions": ["<only with needs_input>"], "disputes": [{{"finding": "F1", "why": "<evidence>"}}]}}')

REVIEW_SCHEMA = ('{{"task": "{tid}", "verdict": "pass | changes", "findings": [{{"id": "F1", '
                 '"state": "wrong | missing | unclear | broken | gap | weak | cosmetic", "blocking": true, '
                 '"where": "path:line", "issue": "<complete sentence: what is wrong and what a reader would observe>", '
                 '"fix": "<what would make it right>"}}], "noticed": []}}')

RECON_SCHEMA = ('{"answers": [{"q": "<the question>", "a": "<the answer>", "evidence": ["path or URL"]}], '
                '"areas": [{"name": "...", "paths": ["..."], "size": "<files / lines>", "note": "..."}], '
                '"unknowns": ["<what you could not establish>"]}')


def _handback(path: Path, schema: str) -> List[str]:
    return ["## Hand back", "", f"Write `{path}`:", "", "```json", schema, "```", "",
            f"Then reply with exactly one line: `RESULT {path}`. Nothing else — the file is the report."]


def _style() -> List[str]:
    return ["## Style (every sentence you write: summaries, findings, and the deliverable's prose "
            "unless its own conventions differ)", "", style_core(), ""]


def _task_body(task: Dict[str, Any], ctx: Dict[str, Any]) -> List[str]:
    out = ["## Task", "", f"{task['title']}. {task['brief']}", "",
           f"Serves: {ctx['serves']}. Full scope: `{ctx['scope_md']}`.", "", "## Write only", ""]
    out += [f"- `{p}`" for p in ctx["write_paths"]]
    out += ["", "Any other change you think is needed: one line in `noticed`, never an edit."]
    if ctx["readonly"]:
        out += ["Read-only (never modify, build into, or leave files in): "
                + "; ".join(f"`{p}`" for p in ctx["readonly"]) + "."]
    out += ["", "## Start from", ""] + [f"- `{s}`" for s in ctx["sources"]]
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
        out += ["Your task, paths, and style are unchanged from your first brief.", ""]
    return "\n".join(out + _handback(result, RESULT_SCHEMA.format(tid=task["id"], step="fix"))) + "\n"


def review(task: Dict[str, Any], n: int, ctx: Dict[str, Any], result: Path) -> str:
    out = [f"# /task-pipeline brief — {task['id']} review {n}", "",
           HEADER.format(box="Time box: about 10 min."), "", "## Review", "",
           f"Task under review: {task['title']}. {task['brief']}", "", "Deliverables:"]
    out += [f"- `{p}`" for p in ctx["write_paths"]]
    out += ["", "Check claims against:"] + [f"- `{s}`" for s in ctx["sources"]]
    out += ["", "Acceptance criteria:"] + [f"- {a}" for a in task["acceptance"]]
    if ctx.get("disputes"):
        out += ["", f"Rule on the author's disputes in `{ctx['disputes']}`."]
    out += ["", "Do not edit any file. Judge only this task's deliverables against its criteria and sources; "
            "anything else is one line in `noticed`. A finding is blocking when the deliverable is wrong, "
            "misses a criterion, or would mislead its reader. `verdict` is `changes` exactly when a finding "
            "is blocking. Verify each finding against the source before you report it.", ""]
    out += _style()
    return "\n".join(out + _handback(result, REVIEW_SCHEMA.format(tid=task["id"]))) + "\n"


def recon(rid: str, item: Dict[str, Any], scope_md: Path, surveys: List[Path], result: Path) -> str:
    box = (f"Time box: {limit('recon_minutes')} min, hard. This is planning recon: answer with a map (areas, "
           "paths, sizes) that lets the manager split the work into tasks. Do not research or write the "
           "deliverable's content — each task researches its own area later.")
    out = [f"# /task-pipeline recon brief — {rid}", "", HEADER.format(box=box), "", "## Questions", ""]
    out += [f"{i}. {q}" for i, q in enumerate(item["questions"], 1)]
    out += ["", f"Done when: {item['done_when']}", "", "## Context", "", f"- Scope: `{scope_md}`"]
    out += [f"- Survey already done (do not repeat it): `{s}`" for s in surveys]
    out += ["", _style()[0], "", style_core(), ""]
    out += _handback(result, RECON_SCHEMA)
    out.insert(-1, f"At most {limit('recon_output_bytes')} bytes; a larger file is refused.")
    return "\n".join(out) + "\n"


def prompt(brief: Path, result: Path) -> str:
    return f"Read and follow {brief}. When done, reply with exactly one line: RESULT {result}"


def dispatch_line(agent: str, desc: str, text: str, agent_id: Optional[str], model: Optional[str]) -> str:
    if agent_id:
        return f"SendMessage(to={json.dumps(agent_id)}, message={json.dumps(text)})"
    extra = f", model={json.dumps(model)}" if model else ""
    return (f"Agent(subagent_type={json.dumps(agent)}, description={json.dumps(desc)}{extra}, "
            f"prompt={json.dumps(text)})")
