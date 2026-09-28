"""Append-only workflow ledger plus orch-result and human-token handling.

The ledger (<workflow>/.orch/ledger.jsonl) is the evidence base every gate is
computed from. Two writers exist, both outside the model's direct control:

* hooks  — SubagentStop records each roster agent's result block, tagged with
           the harness-supplied agent_type/agent_id; UserPromptSubmit records
           genuine human commands.
* the CLI — records commands it ran itself (evidence, gates), snapshots, scans,
           and state transitions.

A PreToolUse hook blocks direct edits of .orch/ from every agent, so a verdict
in the ledger means the named agent actually produced it.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from .common import INTERIM_DIR, Workflow, file_lock, is_within, parse_ts, utcnow
from .roster import (
    BASE_FIELDS,
    GATE_STAGES,
    INTERIM_DECISIONS,
    MAX_GRANT_MINUTES,
    STAGES,
    STATUSES,
    VERDICTS,
)

RESULT_BLOCK_RE = re.compile(r"```orch-result[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.S)
HUMAN_PREFIX = "/task-orchestrator"
HUMAN_VERBS = frozenset(
    {"approve", "revise", "resolve", "resume", "status", "halt", "close", "list", "selftest", "upgrade",
     "scope", "proposal"}
)


# ---------------------------------------------------------------- storage


def _seq_path(wf: Workflow) -> Path:
    return wf.control / "ledger.seq"


def append(wf: Workflow, entry: Dict[str, Any]) -> Dict[str, Any]:
    """Append one entry under the workflow lock and return it (with seq/ts)."""
    wf.control.mkdir(parents=True, exist_ok=True)
    with file_lock(wf.lock_path):
        seq_file = _seq_path(wf)
        try:
            seq = int(seq_file.read_text().strip()) + 1
        except (FileNotFoundError, ValueError):
            seq = sum(1 for _ in _iter_lines(wf.ledger_path)) + 1
        record = {"seq": seq, "ts": utcnow()}
        record.update(entry)
        line = json.dumps(record, sort_keys=True, separators=(",", ":"))
        with open(wf.ledger_path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        seq_file.write_text(f"{seq}\n")
    return record


def _iter_lines(path: Path) -> Iterable[str]:
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield line
    except FileNotFoundError:
        return


def read(wf: Workflow) -> List[Dict[str, Any]]:
    out = []
    for line in _iter_lines(wf.ledger_path):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            out.append(record)
    return out


def count(wf: Workflow) -> int:
    try:
        return int(_seq_path(wf).read_text().strip())
    except (FileNotFoundError, ValueError):
        return sum(1 for _ in _iter_lines(wf.ledger_path))


# ---------------------------------------------------------------- queries


def select(entries: Iterable[Dict[str, Any]], kind: str, **match: Any) -> List[Dict[str, Any]]:
    """Entries of `kind` whose fields (or result fields) equal every `match` value."""
    out = []
    for entry in entries:
        if entry.get("kind") != kind:
            continue
        source = entry.get("result", entry) if kind == "agent_result" else entry
        ok = True
        for key, want in match.items():
            if key in ("agent_type", "agent_id", "valid"):
                have = entry.get(key)
            else:
                have = source.get(key)
            if have != want:
                ok = False
                break
        if ok:
            out.append(entry)
    return out


def results(
    entries: Iterable[Dict[str, Any]],
    stage: Optional[str] = None,
    valid_only: bool = True,
    **match: Any,
) -> List[Dict[str, Any]]:
    params = dict(match)
    if stage is not None:
        params["stage"] = stage
    found = select(entries, "agent_result", **params)
    if valid_only:
        found = [e for e in found if e.get("valid")]
    return found


def latest(items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return max(items, key=lambda e: e.get("seq", 0)) if items else None


# ---------------------------------------------------------------- result blocks


MISSING_BLOCK = "the message has no ```orch-result fenced block"
NO_BLOCK_ERROR = ("no ```orch-result fenced block in the final message or in a SubagentHandback "
                  "message sent since the last stop")


def parse_result_block(text: Optional[str]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    matches = RESULT_BLOCK_RE.findall(text or "")
    if not matches:
        return None, MISSING_BLOCK
    raw = matches[-1]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"the orch-result block is not valid JSON ({exc})"
    if not isinstance(data, dict):
        return None, "the orch-result block must be a JSON object"
    return data, None


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_result(
    result: Dict[str, Any], agent_type: str, wf: Workflow, state: Dict[str, Any]
) -> List[str]:
    """Contract checks for a roster agent's result block. Empty list = valid."""
    errors: List[str] = []
    for name in BASE_FIELDS:
        if name not in result:
            errors.append(f"missing field `{name}`")
    stage = result.get("stage")
    spec = STAGES.get(stage) if isinstance(stage, str) else None
    if spec is None:
        errors.append(f"unknown stage `{stage}`")
    else:
        if agent_type not in spec["agents"]:
            errors.append(f"agent `{agent_type}` may not report stage `{stage}`")
        for name in spec["fields"]:
            if result.get(name) is None:
                errors.append(f"stage `{stage}` requires field `{name}`")
    if result.get("workflow") != state.get("workflow_id"):
        errors.append(
            f"`workflow` is {result.get('workflow')!r}, expected {state.get('workflow_id')!r}"
        )
    status = result.get("status")
    if status not in STATUSES:
        errors.append(f"`status` must be one of {sorted(STATUSES)}")
    verdict = result.get("verdict")
    if verdict not in VERDICTS:
        errors.append(f"`verdict` must be one of {sorted(VERDICTS)}")
    elif stage in GATE_STAGES and status == "complete" and verdict == "n/a":
        errors.append(f"stage `{stage}` is a gate; a complete result needs verdict pass or fail")
    for name in ("attempt", "round", "loop", "plan_revision"):
        if name in result and result[name] is not None and not _is_int(result[name]):
            errors.append(f"`{name}` must be an integer")
    report = result.get("report")
    if isinstance(report, str) and report:
        path = Path(report).expanduser()
        if not path.is_absolute():
            path = wf.root / path
        if not is_within(path, wf.root):
            errors.append("`report` must be a path inside the workflow directory")
        elif not path.name.endswith(f".{agent_type}.md"):
            errors.append(f"`report` file name must end with `.{agent_type}.md`")
        elif (status == "interim") != (path.parent.name == INTERIM_DIR):
            errors.append("an interim result's `report` is the interim report (the `interim/` folder beside "
                          "your report, same file name); any other result's `report` is the brief's report path")
    elif "report" in result:
        errors.append("`report` must be a non-empty path")
    errors += _stage_specific(result, stage, state)
    if "criteria" in result and result["criteria"] is not None:
        crit = result["criteria"]
        if not isinstance(crit, list):
            errors.append("`criteria` must be a list")
        else:
            for item in crit:
                if not (
                    isinstance(item, dict)
                    and isinstance(item.get("id"), str)
                    and isinstance(item.get("met"), bool)
                ):
                    errors.append("each criterion needs string `id` and boolean `met`")
                    break
    if "findings" in result and result["findings"] is not None:
        findings = result["findings"]
        if not (
            isinstance(findings, dict)
            and _is_int(findings.get("blocking"))
            and findings.get("blocking", -1) >= 0
        ):
            errors.append("`findings` must be an object with integer `blocking` (>= 0)")
    tasks = state.get("tasks") or {}
    task = result.get("task")
    if task is not None and tasks and task not in tasks:
        errors.append(f"unknown task `{task}`")
    return errors


def _stage_specific(result: Dict[str, Any], stage: Any, state: Dict[str, Any]) -> List[str]:
    """Field rules for scope proposals, out-of-plan declarations, research items, and interim reviews."""
    from .scope import validate_field

    errors: List[str] = validate_field(result.get("scope_proposals"))
    out_of_plan = result.get("out_of_plan")
    if out_of_plan is not None and not (isinstance(out_of_plan, list) and all(
            isinstance(o, dict) and str(o.get("paths") or "").strip() and str(o.get("reason") or "").strip()
            for o in out_of_plan)):
        errors.append("`out_of_plan` must be a list of {\"paths\": \"<file, directory, or glob>\", "
                      "\"reason\": \"<the acceptance criterion or finding that needs it>\"}")
    known = state.get("research_items")
    if stage == "research" and isinstance(known, dict):
        item = result.get("item")
        if not isinstance(item, str) or item not in known:
            errors.append("stage `research` requires `item`: the research item id from your brief")
    if stage == "pm-research-plan":
        ids = set(known or {})
        approved = result.get("approved")
        rejected = result.get("rejected")
        if not isinstance(approved, list) or not all(isinstance(a, str) for a in approved):
            errors.append("`approved` must be a list of research item ids")
        elif any(a not in ids for a in approved):
            errors.append(f"`approved` names unknown items: {[a for a in approved if a not in ids]}")
        if not isinstance(rejected, list) or not all(
                isinstance(r, dict) and isinstance(r.get("id"), str) and str(r.get("reason") or "").strip()
                for r in rejected):
            errors.append("`rejected` must be a list of {\"id\": \"R##\", \"reason\": \"...\"}")
        elif any(r["id"] not in ids for r in rejected):
            errors.append("`rejected` names unknown items")
        if (result.get("status") == "complete" and result.get("verdict") == "pass"
                and isinstance(rejected, list) and rejected):
            errors.append("verdict `pass` means every reviewed item was approved; with rejections it is `fail`")
    if stage == "pm-interim":
        if result.get("decision") not in INTERIM_DECISIONS:
            errors.append(f"`decision` must be one of {', '.join(INTERIM_DECISIONS)}")
        grant = result.get("grant_minutes")
        if not (isinstance(grant, int) and not isinstance(grant, bool) and 0 < grant <= MAX_GRANT_MINUTES):
            errors.append(f"`grant_minutes` must be an integer from 1 to {MAX_GRANT_MINUTES}")
        if not isinstance(result.get("interim_agent"), str) or not result.get("interim_agent"):
            errors.append("`interim_agent` must be the agent id from the brief")
    return errors


def report_path(result: Dict[str, Any], wf: Workflow) -> Optional[Path]:
    report = result.get("report")
    if not isinstance(report, str) or not report:
        return None
    path = Path(report).expanduser()
    return path if path.is_absolute() else wf.root / path


# ---------------------------------------------------------------- human tokens


XML_COMMAND_RE = re.compile(r"<command-name>\s*/?task-orchestrator\s*</command-name>", re.I)
XML_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.S)


def _verb_and_args(rest: str) -> Tuple[str, List[str]]:
    tokens = rest.split()
    if tokens and tokens[0].lower() in HUMAN_VERBS:
        return tokens[0].lower(), tokens[1:]
    return "start", tokens


def parse_command_parts(name: Optional[str], args: Optional[str]) -> Optional[Tuple[str, List[str]]]:
    """UserPromptExpansion form: command_name + command_args."""
    if not isinstance(name, str) or name.strip().lstrip("/").lower() != HUMAN_PREFIX.lstrip("/"):
        return None
    return _verb_and_args(args or "")


def parse_human_command(prompt: Optional[str]) -> Optional[Tuple[str, List[str]]]:
    """`/task-orchestrator <verb> args...` -> (verb, args). Non-verbs are `start`.

    Accepts the raw typed form and the `<command-name>…</command-name>
    <command-args>…</command-args>` form some builds deliver for slash commands.
    """
    if not isinstance(prompt, str):
        return None
    text = prompt.strip()
    if XML_COMMAND_RE.search(text[:2000]):
        match = XML_ARGS_RE.search(text[:8000])
        return _verb_and_args(match.group(1) if match else "")
    if not text.startswith(HUMAN_PREFIX):
        return None
    rest = text[len(HUMAN_PREFIX):]
    if rest and not rest[0].isspace():
        return None
    return _verb_and_args(rest)


def consumed_refs(entries: Iterable[Dict[str, Any]]) -> set:
    return {e.get("ref") for e in entries if e.get("kind") == "consume"}


def find_human_token(
    entries: List[Dict[str, Any]],
    verb: Optional[str],
    after_ts: Optional[str] = None,
    predicate: Optional[Callable[[Dict[str, Any]], bool]] = None,
) -> Optional[Dict[str, Any]]:
    """Newest unconsumed human entry with `verb` (None = any prompt) after `after_ts`."""
    used = consumed_refs(entries)
    floor = parse_ts(after_ts) if after_ts else None
    for entry in sorted(entries, key=lambda e: e.get("seq", 0), reverse=True):
        if entry.get("kind") != "human" or entry.get("seq") in used:
            continue
        if verb is not None and entry.get("verb") != verb:
            continue
        stamp = parse_ts(entry.get("ts"))
        if floor is not None and (stamp is None or stamp <= floor):
            continue
        if predicate is not None and not predicate(entry):
            continue
        return entry
    return None
