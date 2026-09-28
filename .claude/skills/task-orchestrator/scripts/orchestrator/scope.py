"""The confirmed scope, and scope proposals.

Before any research, the orchestrator turns the request into `scope.md` — what
will be delivered (D1…), the significant terms (S1…) with what each means here
and what adjacent things are NOT it, the non-goals, and questions for the human —
and the human confirms it (`/task-orchestrator scope ok`). Research items and plan
requirements then cite what they serve (`--serves D1,S2`; `Serves: D1`), so every
piece of work traces to something the human confirmed, and every deliverable is
covered. scope.md is frozen with the plan.

    # Scope — <title>
    ## Deliverables
    - D1: <what will be delivered>
    ## Significant terms
    - S1: <term> — <what it means here>. Not: <adjacent things that are out>
    ## Non-goals
    - <what this work will not do>
    ## Questions
    - [ ] Q1: <question for the human>
    - [x] Q2: <question> — Answer: <the human's answer>

Scope proposals: any agent that believes the plan missed something the human
needs puts it in `scope_proposals` on its result instead of doing it —
`{"what", "why", "blocking"}`. Each gets an id `P<ledger seq>-<n>`. Only the human
decides one (`/task-orchestrator proposal accept|reject P12-1 <notes>`): approval
and final acceptance refuse while any is undecided, and a blocking one stops the
work for the human at once. An accepted proposal is in scope from then on — it
can be cited like a deliverable.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .common import Workflow, sha256_text

DELIVERABLE_RE = re.compile(r"^\s*[-*]\s+(?:\*\*)?(D\d+)(?:\*\*)?\s*[:.)\-–—]\s*(.+?)\s*$")
TERM_RE = re.compile(r"^\s*[-*]\s+(?:\*\*)?(S\d+)(?:\*\*)?\s*[:.)\-–—]\s*(.+?)\s*$")
QUESTION_RE = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(?:\*\*)?(Q\d+)(?:\*\*)?\s*[:.)\-–—]\s*(.+?)\s*$")
BULLET_RE = re.compile(r"^\s*[-*]\s+(.+?)\s*$")
SERVES_RE = re.compile(r"serves\s*:\s*((?:[DS]\d+|P\d+-\d+)(?:\s*,\s*(?:[DS]\d+|P\d+-\d+))*)", re.I)
PROPOSAL_ID_RE = re.compile(r"^P\d+-\d+$")


# ---------------------------------------------------------------- scope.md


def _sections(text: str) -> Dict[str, str]:
    from .plan import split_sections

    return split_sections(text)


def parse(wf: Workflow) -> Optional[Dict[str, Any]]:
    """The parsed scope.md, or None when there is none."""
    if not wf.scope.is_file():
        return None
    text = wf.scope.read_text(encoding="utf-8")
    from .plan import find_section

    sections = _sections(text)
    deliverables: Dict[str, str] = {}
    for line in (find_section(sections, "deliverables") or "").splitlines():
        match = DELIVERABLE_RE.match(line)
        if match:
            deliverables.setdefault(match.group(1), match.group(2))
    terms: Dict[str, str] = {}
    for line in (find_section(sections, "significant terms") or "").splitlines():
        match = TERM_RE.match(line)
        if match:
            terms.setdefault(match.group(1), match.group(2))
    non_goals = [m.group(1) for m in (BULLET_RE.match(line) for line in
                                     (find_section(sections, "non-goals") or "").splitlines()) if m]
    questions = []
    for line in (find_section(sections, "questions") or "").splitlines():
        match = QUESTION_RE.match(line)
        if match:
            box, qid, rest = match.groups()
            questions.append({"id": qid, "answered": box.lower() == "x" and bool(re.search(r"answer\s*:", rest, re.I)),
                              "text": rest})
    return {"text": text, "sha256": sha256_text(text), "deliverables": deliverables, "terms": terms,
            "non_goals": non_goals, "questions": questions,
            "has_non_goals_section": find_section(sections, "non-goals") is not None}


def problems(scope: Optional[Dict[str, Any]], for_confirm: bool = False) -> List[str]:
    if scope is None:
        return ["scope.md does not exist yet"]
    errors = []
    if not scope["deliverables"]:
        errors.append("scope.md `## Deliverables` lists no `- D1: ...` deliverables")
    if not scope["has_non_goals_section"]:
        errors.append("scope.md needs a `## Non-goals` section (write `- None beyond the deliverables.` if so)")
    for term_id, text in scope["terms"].items():
        if not re.search(r"\bnot\s*:", text, re.I):
            errors.append(f"significant term {term_id} needs `Not: <adjacent things that are out>` — that "
                          "boundary is what keeps research on the term")
    if for_confirm:
        for q in scope["questions"]:
            if not q["answered"]:
                errors.append(f"scope question {q['id']} has no answer yet: {q['text']}")
    return errors


def confirmed(wf: Workflow, state: Dict[str, Any]) -> Tuple[bool, str]:
    """(confirmed at the current content, detail)."""
    scope = parse(wf)
    if scope is None:
        return False, "no scope.md"
    if not state.get("scope_sha256"):
        return False, "not confirmed by the human"
    if state["scope_sha256"] != scope["sha256"]:
        return False, "scope.md changed after the human confirmed it"
    return True, "confirmed"


def citable(wf: Workflow, entries: List[Dict[str, Any]]) -> Dict[str, str]:
    """Every id work may cite: deliverables, significant terms, and accepted proposals."""
    scope = parse(wf) or {"deliverables": {}, "terms": {}}
    out = dict(scope["deliverables"])
    out.update(scope["terms"])
    for proposal in proposals(entries):
        if proposal["decision"] == "accept":
            out[proposal["id"]] = proposal["what"]
    return out


def parse_serves(text: str) -> List[str]:
    match = SERVES_RE.search(text or "")
    if not match:
        return []
    return [part.strip().upper() for part in match.group(1).split(",") if part.strip()]


def brief_lines(wf: Workflow) -> List[str]:
    """The scope section every brief carries once scope.md exists."""
    scope = parse(wf)
    if scope is None:
        return []
    lines = ["", "## Confirmed scope", "", f"Read {wf.scope} in full. The deliverables:"]
    lines += [f"- {k}: {v}" for k, v in scope["deliverables"].items()]
    if scope["terms"]:
        lines += ["", "Significant terms — work in these terms. Work about an adjacent thing a term names under "
                  "`Not:` fails its brief, unless the brief itself asks for a comparison:"]
        lines += [f"- {k}: {v}" for k, v in scope["terms"].items()]
    if scope["non_goals"]:
        lines += ["", "Non-goals:"] + [f"- {g}" for g in scope["non_goals"]]
    return lines


# ---------------------------------------------------------------- proposals


def proposals(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every scope proposal agents raised, with the human's decision (or None)."""
    decisions: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        if entry.get("kind") == "proposal_decision":
            decisions[str(entry.get("proposal"))] = entry
    out = []
    for entry in entries:
        if entry.get("kind") != "agent_result" or not entry.get("valid"):
            continue
        res = entry.get("result") or {}
        for n, item in enumerate(res.get("scope_proposals") or [], 1):
            if not isinstance(item, dict):
                continue
            pid = f"P{entry.get('seq')}-{n}"
            decision = decisions.get(pid)
            out.append({
                "id": pid,
                "what": str(item.get("what") or ""),
                "why": str(item.get("why") or ""),
                "blocking": bool(item.get("blocking")),
                "agent_type": entry.get("agent_type"),
                "agent_id": entry.get("agent_id"),
                "stage": res.get("stage"),
                "task": res.get("task"),
                "report": res.get("report"),
                "seq": entry.get("seq"),
                "ts": entry.get("ts"),
                "decision": (decision or {}).get("decision"),
                "decided_seq": (decision or {}).get("seq"),
            })
    return out


def undecided(entries: List[Dict[str, Any]], blocking_only: bool = False) -> List[Dict[str, Any]]:
    return [p for p in proposals(entries) if p["decision"] is None and (p["blocking"] or not blocking_only)]


def describe(proposal: Dict[str, Any]) -> str:
    where = f" ({proposal['task']})" if proposal.get("task") else ""
    kind = "BLOCKING" if proposal["blocking"] else "non-blocking"
    return (f"{proposal['id']} [{kind}] from {proposal['agent_type']}{where}: {proposal['what']} — why: "
            f"{proposal['why']} (report: {proposal['report']})")


def validate_field(value: Any) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(
            isinstance(p, dict) and str(p.get("what") or "").strip() and str(p.get("why") or "").strip()
            and isinstance(p.get("blocking"), bool) for p in value):
        return ["`scope_proposals` must be a list of {\"what\": \"...\", \"why\": \"...\", \"blocking\": true|false}"]
    return []


def unknown_ids(ids: List[str], known: Set[str]) -> List[str]:
    return [i for i in ids if i not in known]
