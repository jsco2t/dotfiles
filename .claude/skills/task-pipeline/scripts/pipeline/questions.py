"""Questions to the human: asked once, timestamped, answered verbatim.

Clarifying questions belong before the plan (investigate, ask, then plan); a question that comes
up mid-run parks only the item it is about. Asking never stops the run: in real runs a blocking
question held every hand-back unrecorded and every ready task undispatched for 8 to 42 hours,
while the report claimed a few minutes of waiting. The ledger is what makes that wait visible."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .common import TPError, Workflow, minutes_since, now_iso, words


def ledger(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return state.setdefault("questions", {})


def open_questions(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {qid: q for qid, q in (state.get("questions") or {}).items() if not q.get("answered")}


def open_about(state: Dict[str, Any], about: str) -> List[str]:
    return [qid for qid, q in open_questions(state).items() if q.get("about") == about]


def _render(wf: Workflow, state: Dict[str, Any]) -> None:
    """clarifications.md: every question asked and its answer, for the human, the plan reviewer,
    and every brief that cites `wf:clarifications.md`."""
    qs = state.get("questions") or {}
    if not qs:
        return
    out = ["# Clarifications", "", "Questions put to the human during this run, with their answers verbatim.", ""]
    for qid, q in qs.items():
        about = f" (about {q['about']})" if q.get("about") else ""
        out.append(f"- **{qid}{about}: {q['text']}**")
        out.append(f"  - {q['answer']} — {q.get('by', 'human')}, {q['answered']}" if q.get("answered")
                   else f"  - open since {q['asked']}")
    (wf.root / "clarifications.md").write_text("\n".join(out) + "\n")


def cmd_ask(wf: Workflow, texts: List[str], about: Optional[str]) -> str:
    texts = [" ".join(t.split()) for t in texts if t and t.strip()]
    if not texts:
        raise TPError("ask needs --question \"...\" (repeat it to ask several at once).")
    short = [t for t in texts if words(t) < 4]
    if short:
        raise TPError(f"a question the human can answer without context needs a full sentence: {short[0]!r}.")
    with wf.locked():
        state = wf.load()
        if state["phase"] == "DONE":
            raise TPError("the workflow is DONE.")
        if about and about != "workflow" and about not in state.get("tasks", {}) and about not in state.get("reviews", {}):
            raise TPError(f"--about {about}: not a task, a review session, or `workflow` (a run-wide block).")
        qs = ledger(state)
        ids = []
        for text in texts:
            if any(q["text"] == text and not q.get("answered") for q in qs.values()):
                continue  # asked already: the open one stands
            qid = f"Q{len(qs) + 1}"
            qs[qid] = {"text": text, "about": about, "asked": now_iso(), "phase": state["phase"]}
            ids.append(qid)
        wf.save(state)
        _render(wf, state)
    wf.event("ask", ids=ids, about=about)
    busy = bool(state.get("in_flight"))
    how = ("Put them to the human in plain text at the end of this turn — never AskUserQuestion while agents are in "
           "flight: it holds your turn, so their hand-backs go unrecorded until the human answers."
           if busy or state["phase"] == "EXECUTING" else
           "Nothing is in flight: one AskUserQuestion with all of them is fine (at most 4 per call).")
    return "\n".join([f"asked {', '.join(ids) or 'nothing new'}" + (f" (about {about})" if about else "") + ".", how,
                      "Keep working everything else that is ready; when they answer: "
                      "`tp answer Q# --answer \"<their words>\"`."])


def cmd_answer(wf: Workflow, qid: str, answer: str, by: str) -> str:
    """Record an answer verbatim. --by manager settles a question the evidence already answers (a
    research finding, the scope, the plan): recorded as the manager's, and the plan review sees it."""
    if by not in ("human", "manager"):
        raise TPError("--by must be human or manager.")
    if not answer.strip():
        raise TPError("--answer needs the answer, verbatim.")
    with wf.locked():
        state = wf.load()
        q = (state.get("questions") or {}).get(qid)
        if q is None:
            raise TPError(f"{qid} is not a question of this run (`tp status` lists the open ones).")
        if q.get("answered"):
            raise TPError(f"{qid} was answered at {q['answered']}: {q['answer']}")
        q.update(answer=" ".join(answer.split()), by=by, answered=now_iso(),
                 waited_min=round(minutes_since(q["asked"]), 1))
        wf.save(state)
        _render(wf, state)
    wf.decision(f"{qid}: {q['text']}", q["answer"], who=by)
    wf.event("answer", id=qid, by=by, waited=q["waited_min"], about=q.get("about"))
    tail = ""
    if q.get("about"):
        tail = (f"\nIt is about {q['about']}: carry the answer there now — `tp resolve --task|--review {q['about']} "
                f"--action ... --answer \"<their words>\" --by {by}` (whatever its block takes).")
    return f"{qid} answered ({q['waited_min']:.0f} min after it was asked); recorded in clarifications.md.{tail}"


def waiting_lines(state: Dict[str, Any]) -> List[str]:
    """For the report: how long the run waited on answers, measured from the questions themselves."""
    qs = list((state.get("questions") or {}).values())
    if not qs:
        return []
    done = [q for q in qs if q.get("answered")]
    total = sum(q.get("waited_min", 0.0) for q in done)
    longest = max(done, key=lambda q: q.get("waited_min", 0.0)) if done else None
    still = [q for q in qs if not q.get("answered")]
    out = [f"{len(qs)} question{'s' if len(qs) != 1 else ''} to the human; answers took {total:.0f} min in all"
           + (f" (longest {longest['waited_min']:.0f} min: \"{longest['text'][:90]}\")" if longest else "") + "."]
    exec_q = [q for q in done if q.get("phase") == "EXECUTING"]
    if exec_q:
        out.append(f"{len(exec_q)} of them came up during execution ({sum(q['waited_min'] for q in exec_q):.0f} min).")
    if still:
        out.append(f"{len(still)} still open: " + "; ".join(q["text"][:80] for q in still[:3]) + ".")
    return out


def status_line(state: Dict[str, Any]) -> Optional[str]:
    """One line for `tp next`: open questions, oldest first, never reprinted in full."""
    qs = open_questions(state)
    if not qs:
        return None
    parts = [f"{qid}{' (' + q['about'] + ')' if q.get('about') else ''} {minutes_since(q['asked']):.0f}m"
             for qid, q in sorted(qs.items(), key=lambda kv: kv[1]["asked"])]
    return "waiting on the human: " + ", ".join(parts) + " — keep working the rest."
