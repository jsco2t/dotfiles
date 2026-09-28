"""Focused planning research.

Planning research is registered as items with `orch research add`: one agent, at
most MAX_RESEARCH_QUESTIONS short questions, a "done when" line, and a
word-limited context note. The project-manager reviews proposed items before any
is dispatched (stage pm-research-plan), and `orch brief research --item R##`
refuses an item it has not approved. That puts the scope fence in front of a
research agent instead of behind it: an item cannot carry "exhaustive, no
sampling" instructions, a forwarded lead, or an audit the request never asked for
without the PM seeing it first.

Item status is computed from the ledger; only the definition and DROPPED live in
state:

  PROPOSED    added; the PM has not reviewed it since
  REJECTED    the latest PM research-plan review after it was added rejected it
  APPROVED    approved and not yet reported on
  INTERIM     its latest result is an interim report (time budget or pause)
  NEEDS_INPUT / BLOCKED   its latest result says so
  DONE        a complete result
  DROPPED     withdrawn by the orchestrator

Workflows created before items existed have no `research_items` key in state and
keep the old free-topic research briefs (`is_legacy`).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .common import OrchError
from .roster import (
    DOC_KINDS,
    LIAISONS,
    MAX_DONE_WHEN_WORDS,
    MAX_QUESTION_WORDS,
    MAX_RESEARCH_CONTEXT_WORDS,
    MAX_RESEARCH_QUESTIONS,
    RESEARCH_MODES,
    RESEARCHERS,
)

BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def is_legacy(state: Dict[str, Any]) -> bool:
    return "research_items" not in state


def items(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return dict(state.get("research_items") or {})


def words(text: str) -> int:
    return len(text.split())


def parse_questions(text: str) -> List[str]:
    """One question per bullet / numbered line; unbulleted continuation lines join the previous one."""
    questions: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if BULLET_RE.match(raw) or not questions:
            questions.append(BULLET_RE.sub("", raw).strip())
        else:
            questions[-1] = f"{questions[-1]} {line}"
    return [q for q in questions if q]


def default_mode(agent: str, kind: str) -> Optional[str]:
    if agent != "codebase-researcher":
        return None
    return "map" if kind in DOC_KINDS else "investigate"


def validate_new(agent: str, title: str, questions: List[str], done_when: str, context: str,
                 mode: Optional[str]) -> List[str]:
    errors: List[str] = []
    if agent not in RESEARCHERS | LIAISONS:
        errors.append(f"research items are for {', '.join(sorted(RESEARCHERS | LIAISONS))}, not `{agent}`")
    if not title.strip() or words(title) > 12:
        errors.append("--title is required and at most 12 words")
    if not questions:
        errors.append("the questions file has no questions (one per `- ` bullet or numbered line)")
    if len(questions) > MAX_RESEARCH_QUESTIONS:
        errors.append(f"{len(questions)} questions; an item asks at most {MAX_RESEARCH_QUESTIONS}. Split it into "
                      "several focused items — breadth comes from more items, not bigger ones")
    for n, question in enumerate(questions, 1):
        if words(question) > MAX_QUESTION_WORDS:
            errors.append(f"question {n} is {words(question)} words (max {MAX_QUESTION_WORDS}); a question that "
                          "needs a paragraph of sub-asks is several questions")
    if not done_when.strip():
        errors.append("--done-when is required: what answer does the planner need, so the agent knows when to stop")
    elif words(done_when) > MAX_DONE_WHEN_WORDS:
        errors.append(f"--done-when is {words(done_when)} words (max {MAX_DONE_WHEN_WORDS})")
    if words(context) > MAX_RESEARCH_CONTEXT_WORDS:
        errors.append(f"the context note is {words(context)} words (max {MAX_RESEARCH_CONTEXT_WORDS}); context is "
                      "pins, paths, and constraints — not extra asks")
    if mode is not None and mode not in RESEARCH_MODES:
        errors.append(f"--mode must be one of {', '.join(RESEARCH_MODES)}")
    if mode is not None and agent != "codebase-researcher":
        errors.append("--mode applies to codebase-researcher only")
    return errors


def next_id(state: Dict[str, Any]) -> str:
    existing = [int(k[1:]) for k in items(state) if re.match(r"^R\d+$", k)]
    return f"R{(max(existing) + 1) if existing else 1:02d}"


# ---------------------------------------------------------------- status


def _latest(entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return max(entries, key=lambda e: e.get("seq", 0)) if entries else None


def _rejected_ids(result: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for entry in result.get("rejected") or []:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            out[entry["id"]] = str(entry.get("reason") or "")
        elif isinstance(entry, str):
            out[entry] = ""
    return out


def review_of(entries: List[Dict[str, Any]], item: Dict[str, Any]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """('approved' | 'rejected' | None, the PM entry) — the latest PM decision on this item since it was added."""
    after = int(item.get("added_seq") or 0)
    reviews = [
        e for e in entries
        if e.get("kind") == "agent_result" and e.get("valid") and e.get("seq", 0) > after
        and (e.get("result") or {}).get("stage") == "pm-research-plan"
        and (e.get("result") or {}).get("status") == "complete"
    ]
    for entry in sorted(reviews, key=lambda e: e.get("seq", 0), reverse=True):
        res = entry.get("result") or {}
        if item["id"] in _rejected_ids(res):
            return "rejected", entry
        if item["id"] in [a for a in res.get("approved") or [] if isinstance(a, str)]:
            return "approved", entry
    return None, None


def results_for(entries: List[Dict[str, Any]], item_id: str) -> List[Dict[str, Any]]:
    return [
        e for e in entries
        if e.get("kind") == "agent_result" and e.get("valid")
        and (e.get("result") or {}).get("stage") == "research" and (e.get("result") or {}).get("item") == item_id
    ]


def status(entries: List[Dict[str, Any]], item: Dict[str, Any]) -> Tuple[str, str]:
    """(STATUS, detail) for one item."""
    if item.get("status") == "DROPPED":
        return "DROPPED", item.get("dropped_reason") or ""
    latest = _latest(results_for(entries, item["id"]))
    if latest is not None:
        res = latest.get("result") or {}
        state = {"complete": "DONE", "interim": "INTERIM", "needs_input": "NEEDS_INPUT",
                 "blocked": "BLOCKED"}.get(str(res.get("status")), "DONE")
        return state, f"{latest.get('agent_type')} {latest.get('agent_id')}: {res.get('report')}"
    decision, review = review_of(entries, item)
    if decision == "approved":
        return "APPROVED", f"approved by the PM (seq {review['seq']})" if review else "approved"
    if decision == "rejected" and review is not None:
        return "REJECTED", _rejected_ids(review.get("result") or {}).get(item["id"]) or "rejected by the PM"
    return "PROPOSED", "awaiting the PM's research-plan review"


def statuses(entries: List[Dict[str, Any]], state: Dict[str, Any]) -> Dict[str, Tuple[str, str]]:
    return {iid: status(entries, item) for iid, item in sorted(items(state).items())}


def require_approved(entries: List[Dict[str, Any]], state: Dict[str, Any], item_id: str,
                     agent: str) -> Dict[str, Any]:
    item = items(state).get(item_id)
    if item is None:
        raise OrchError(f"no research item {item_id}; register it with `orch research add`")
    if item.get("agent") != agent:
        raise OrchError(f"research item {item_id} is for {item.get('agent')}, not {agent}")
    state_name, detail = status(entries, item)
    if state_name in ("PROPOSED", "REJECTED", "DROPPED"):
        raise OrchError(f"research item {item_id} is {state_name} ({detail}); only items the PM approved in a "
                        "research-plan review can be dispatched (`orch brief --plan pm-research-plan --agent "
                        "project-manager`)")
    if state_name == "DONE":
        raise OrchError(f"research item {item_id} is already DONE ({detail})")
    return item


def describe(item: Dict[str, Any]) -> List[str]:
    """The item as brief lines."""
    mode = f", mode `{item['mode']}`" if item.get("mode") else ""
    lines = [f"**{item['id']} — {item['title']}** (`{item['agent']}`{mode})", "", "Questions:"]
    lines += [f"{n}. {q}" for n, q in enumerate(item.get("questions") or [], 1)]
    lines += ["", f"Done when: {item.get('done_when')}"]
    if item.get("context"):
        lines += ["", f"Context: {item['context']}"]
    return lines
