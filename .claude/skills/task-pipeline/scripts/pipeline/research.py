"""Planning research: small, narrowly scoped items inside a research budget the human agreed
to. Each item answers at most three questions in a small JSON file; anything that needs more
investigation comes back as a followup, which the manager pursues (a new item) or dismisses.
State lives under state["recon"] (the name older workflows use)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import briefs
from . import scope as scopemod
from .common import TPError, Workflow, limit, load_json, minutes_since, now_iso, words

PURPOSES = ("map", "requirements", "investigate")
_CONTENT = [
    re.compile(r"\b(every|all)\s+(\w+\s+)?(files?|flags?|functions?|symbols?|packages?|commands?|fields?|"
               r"endpoints?|lines?|options?|types?)\b", re.I),
    re.compile(r"\bcomplete\s+(\w+\s+){0,2}(list|tree|inventory|reference|catalog(ue)?|walkthrough)\b", re.I),
    re.compile(r"\bexhaustive(ly)?\b", re.I),
]
_WHOLE_FLOW = re.compile(r"\bend[- ]to[- ]end\b", re.I)
# `investigate` may trace one named flow end to end; `map` and `requirements` may not.
BANNED = {"map": _CONTENT + [_WHOLE_FLOW], "requirements": _CONTENT + [_WHOLE_FLOW], "investigate": _CONTENT}


def items(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return state.setdefault("recon", {})


def budget(state: Dict[str, Any], scope: Dict[str, Any]) -> int:
    return scopemod.research_budget(scope) + int(state.get("research_extra", 0))


def reserved(state: Dict[str, Any]) -> int:
    return sum(int(i.get("minutes", limit("research_item_minutes"))) for i in items(state).values()
               if i["status"] != "dropped")


def summary(state: Dict[str, Any], scope: Dict[str, Any]) -> Optional[str]:
    total = budget(state, scope)
    if not total and not items(state):
        return None
    its = items(state).values()
    done = sum(i["status"] == "done" for i in its)
    open_ = sum(f["status"] == "open" for i in its for f in i.get("followups", []))
    spent = sum(i.get("actual_minutes", 0) for i in its)
    return (f"research budget: {reserved(state)} of {total} agent-min reserved · {done} of "
            f"{sum(i['status'] != 'dropped' for i in its)} items answered ({spent:.0f} min spent) · "
            f"{open_} followups undecided")


def actions(state: Dict[str, Any], free: int) -> List[Dict[str, Any]]:
    acts: List[Dict[str, Any]] = []
    for rid, item in items(state).items():
        if item["status"] == "pending" and free > 0:
            acts.append({"action": "dispatch", "id": rid, "step": "research", "agent": item["agent"],
                         "agent_id": None, "model": None})
            free -= 1
    for rid, item in items(state).items():
        for f in item.get("followups", []):
            if f["status"] == "open":
                acts.append({"action": "followup", "id": f["id"], "why": f["question"]})
    busy = [r for r, v in items(state).items() if v["status"] == "in_flight"]
    if busy:
        acts.append({"action": "wait", "ids": busy})
    return acts


def _find_followup(state: Dict[str, Any], ref: str) -> Dict[str, Any]:
    rid = ref.split(".", 1)[0]
    for f in items(state).get(rid, {}).get("followups", []):
        if f["id"] == ref:
            return f
    raise TPError(f"{ref} is not a followup of a recorded research item.")


def cmd_add(wf: Workflow, rid: str, agent: str, purpose: Optional[str], questions_file: Path, done_when: str,
            minutes: Optional[int], from_ref: Optional[str]) -> str:
    with wf.locked():
        state = wf.load()
        if state["phase"] != "PLANNING":
            raise TPError(f"Research happens only while PLANNING; the workflow is {state['phase']}.")
        scope = scopemod.load_scope(wf)
        total = budget(state, scope)
        if not total:
            raise TPError("There is no research budget in the confirmed scope. A clear, small ask needs none; if "
                          "this one does, agree a budget and researchers with the human (`tp revise --scope`).")
        errs = []
        if not re.fullmatch(r"R\d+", rid) or rid in items(state):
            errs.append(f"research id {rid!r} must be new and look like R1.")
        if purpose not in PURPOSES:
            errs.append(f"--purpose must be one of {', '.join(PURPOSES)}: map (how to split the work), "
                        "requirements (what named tickets or pages require), investigate (how one named thing works).")
        if agent not in scopemod.participants(scope, "research"):
            errs.append(f"{agent} is not a confirmed research participant in scope.json — ask the human first.")
        box = limit("research_item_minutes") if minutes is None else minutes
        if not 1 <= box <= limit("research_item_minutes"):
            errs.append(f"--minutes {box}: a research item's time box is 1 to {limit('research_item_minutes')} min — "
                        "split the question instead.")
        questions = [q.strip() for q in Path(questions_file).read_text().splitlines() if q.strip()]
        if not questions:
            errs.append("no questions.")
        if len(questions) > limit("max_research_questions"):
            errs.append(f"{len(questions)} questions; at most {limit('max_research_questions')} per item — "
                        "more questions means more items, not bigger ones.")
        for i, q in enumerate(questions, 1):
            if words(q) > 40:
                errs.append(f"question {i} is {words(q)} words; keep it under 40.")
            for pat in BANNED.get(str(purpose), []):
                m = pat.search(q)
                if m:
                    errs.append(f"question {i} asks for content, not planning research: \"{m.group(0)}\" — the task "
                                "that writes the content researches it.")
        if from_ref:
            try:
                if _find_followup(state, from_ref)["status"] != "open":
                    errs.append(f"{from_ref} is already decided.")
            except TPError as exc:
                errs += exc.lines
        if not errs and reserved(state) + box > total:
            errs.append(f"research budget: {reserved(state)} of {total} agent-min reserved; {rid} needs {box} more. "
                        "Ask the human whether to spend more (`tp research extend --minutes N --answer \"...\"`), "
                        "or drop or shrink an item.")
        if errs:
            raise TPError(*errs)
        items(state)[rid] = {"agent": agent, "purpose": purpose, "questions": questions, "done_when": done_when,
                             "minutes": box, "status": "pending", "from": from_ref}
        if from_ref:
            f = _find_followup(state, from_ref)
            f.update(status="pursued", by=rid)
        wf.save(state)
        wf.event("research_add", id=rid, agent=agent, purpose=purpose, minutes=box, source=from_ref)
        return f"{rid} added ({purpose}, {box} min). {summary(state, scope)}. `tp dispatch {rid}` when ready."


def cmd_extend(wf: Workflow, minutes: int, answer: str) -> str:
    with wf.locked():
        state = wf.load()
        if state["phase"] != "PLANNING" or minutes < 1:
            raise TPError("The research budget grows only while PLANNING, by a positive number of minutes.")
        state["research_extra"] = int(state.get("research_extra", 0)) + minutes
        wf.save(state)
        wf.decision(f"research extend +{minutes} min", answer)
        return f"research budget +{minutes} agent-min. {summary(state, scopemod.load_scope(wf))}."


def cmd_dismiss(wf: Workflow, ref: str, reason: str) -> str:
    with wf.locked():
        state = wf.load()
        f = _find_followup(state, ref)
        if f["status"] != "open":
            raise TPError(f"{ref} is already {f['status']}.")
        f.update(status="dismissed", reason=reason)
        wf.save(state)
        wf.decision(f"research dismiss {ref}", reason, who="manager")
        return f"{ref} dismissed."


def cmd_drop(wf: Workflow, rid: str, reason: str) -> str:
    with wf.locked():
        state = wf.load()
        item = items(state).get(rid)
        if item is None or item["status"] != "pending":
            raise TPError(f"{rid} is not a pending research item (only unrun items can be dropped).")
        item.update(status="dropped", reason=reason)
        wf.save(state)
        wf.decision(f"research drop {rid}", reason, who="manager")
        return f"{rid} dropped; its {item.get('minutes', limit('research_item_minutes'))} min are released."


def dispatch(wf: Workflow, state: Dict[str, Any], rid: str, slots) -> str:
    if state["phase"] != "PLANNING":
        raise TPError(f"Research happens only while PLANNING; the workflow is {state['phase']}.")
    item = items(state).get(rid)
    if item is None or item["status"] != "pending":
        raise TPError(f"{rid} is not a pending research item.")
    slots(state)
    rdir = wf.root / "recon"
    rdir.mkdir(exist_ok=True)
    brief, result = rdir / f"{rid}.brief.md", rdir / f"{rid}.json"
    if result.exists():
        result.unlink()
    surveys = sorted((wf.root / "survey").glob("*.json")) if (wf.root / "survey").exists() else []
    brief.write_text(briefs.research(rid, item, wf.root / "scope.md", surveys, result))
    item["status"] = "in_flight"
    state["in_flight"][rid] = {"step": "research", "since": now_iso(), "agent": item["agent"], "concurrent": []}
    wf.save(state)
    wf.event("dispatch", id=rid, step="research", agent=item["agent"])
    call = briefs.dispatch_line(item["agent"], f"{rid} research", briefs.prompt(brief, result), None, None)
    return (f"DISPATCH {rid} · research ({item.get('purpose', 'map')}) · {item['agent']} · "
            f"box {item.get('minutes', limit('research_item_minutes'))} min\nbrief: {brief}\nsend: {call}\n"
            f"then: tp record {rid}")


def _validate(data: Any) -> List[str]:
    if not isinstance(data, dict):
        return ["the result must be a JSON object."]
    errs = []
    answers = data.get("answers")
    if not isinstance(answers, list) or not answers or not all(isinstance(a, dict) and a.get("a") for a in answers):
        errs.append("needs `answers`: a list of {q, a, evidence} objects.")
    followups = data.get("followups", [])
    if not isinstance(followups, list) or not all(isinstance(f, dict) and f.get("question") and f.get("why")
                                                  for f in followups):
        errs.append("`followups` must be a list of {question, why, agent} objects.")
    return errs


def record(wf: Workflow, state: Dict[str, Any], rid: str) -> str:
    item = items(state).get(rid)
    if item is None or rid not in state["in_flight"]:
        raise TPError(f"{rid} is not in flight.")
    path = wf.root / "recon" / f"{rid}.json"
    if not path.exists():
        raise TPError(f"{path} is missing — the agent must write it.")
    size = path.stat().st_size
    if size > limit("research_output_bytes"):
        raise TPError(f"{path.name} is {size} bytes; the cap is {limit('research_output_bytes')} — ask the same agent "
                      "to cut it to what the questions need (SendMessage), then record again.")
    data = load_json(path, "research result")
    errs = _validate(data)
    if errs:
        raise TPError(*[f"{path}: {e}" for e in errs])
    minutes = minutes_since(state["in_flight"][rid]["since"])
    del state["in_flight"][rid]
    item["followups"] = [{"id": f"{rid}.F{i}", "question": f["question"], "why": f["why"],
                          "agent": f.get("agent"), "status": "open"}
                         for i, f in enumerate(data.get("followups", []), 1)]
    item.update(status="done", actual_minutes=round(minutes, 1))
    wf.save(state)
    wf.event("record", id=rid, step="research", minutes=round(minutes, 1))
    box = item.get("minutes", limit("research_item_minutes"))
    out = [f"{rid} done in {minutes:.0f} min{f' — over its {box}-min box' if minutes > box else ''}: "
           f"{len(data['answers'])} answers, {len(data.get('unknowns', []))} unknowns. Fact-check one answer "
           f"(`tp show {rid} --part answers`) before you rely on it."]
    if item["followups"]:
        out.append("Followups — decide each (pursue within the budget, or dismiss with a reason):")
        out += [f"  {f['id']}: {f['question']} — {f['why']}" + (f" [{f['agent']}]" if f.get("agent") else "")
                for f in item["followups"]]
    out.append(summary(state, scopemod.load_scope(wf)) or "")
    return "\n".join(out)


def show(wf: Workflow, state: Dict[str, Any], rid: str, part: Optional[str]) -> str:
    item = items(state).get(rid)
    if item is None:
        raise TPError(f"{rid} is not a research item.")
    if part == "followups":
        return "\n".join(f"{f['id']} [{f['status']}] {f['question']} — {f['why']}"
                         for f in item.get("followups", [])) or "no followups."
    path = wf.root / "recon" / f"{rid}.json"
    if item["status"] != "done" or not path.exists():
        return f"{rid}: {item['status']} ({item.get('purpose', 'map')}, {item['agent']}): " + " | ".join(item["questions"])
    data = json.loads(path.read_text())
    if part == "answers":
        return "\n".join(f"Q: {a.get('q', '')}\nA: {a['a']}" + (f"\n   evidence: {', '.join(a['evidence'])}"
                                                               if a.get("evidence") else "") for a in data["answers"])
    if part in ("unknowns", "areas"):
        return json.dumps(data.get(part, []), indent=1)
    return (f"{rid} ({item.get('purpose', 'map')}, {item['agent']}): {len(data['answers'])} answers, "
            f"{len(item.get('followups', []))} followups, {len(data.get('unknowns', []))} unknowns — parts: "
            "answers, followups, unknowns, areas")
