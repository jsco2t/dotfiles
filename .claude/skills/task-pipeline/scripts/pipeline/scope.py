"""Scope: what will be delivered, who works on it, and the budget — checked, rendered,
and frozen when the human confirms it."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Set

from .common import TPError, Workflow, catalog, limit, load_json, now_iso, sha_file

REVIEW_MODES = ("none", "per-task", "final", "both")
WORK_ROLES = ("author", "tests", "reviewer")


def load_scope(wf: Workflow) -> Dict[str, Any]:
    data = load_json(wf.scope_json, "the scope")
    if not isinstance(data, dict):
        raise TPError(f"{wf.scope_json} must hold a JSON object.")
    return data


def deliverable_kinds(scope: Dict[str, Any]) -> Set[str]:
    return {str(d["kind"]) for d in scope.get("deliverables", []) if isinstance(d, dict) and d.get("kind")}


def participants(scope: Dict[str, Any], role: str) -> List[str]:
    return [p["agent"] for p in scope.get("participants", []) if isinstance(p, dict) and p.get("role") == role]


def workspaces(scope: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {w["name"]: w for w in scope.get("workspaces", []) if isinstance(w, dict) and "name" in w}


def validate(scope: Dict[str, Any]) -> List[str]:
    cat = catalog()
    agents = cat["agents"]
    errs: List[str] = []
    for key in ("title", "output", "deliverables", "participants", "review", "workspaces"):
        if not scope.get(key):
            errs.append(f"scope.json needs `{key}`.")
    if errs:
        return errs

    ids: Set[str] = set()
    for d in scope["deliverables"]:
        did = d.get("id", "")
        if not re.fullmatch(r"D\d+", str(did)) or did in ids:
            errs.append(f"deliverable id {did!r} must be unique and look like D1.")
        ids.add(did)
        if d.get("kind") not in cat["kinds"]:
            errs.append(f"{did}: kind {d.get('kind')!r} is not one of {', '.join(cat['kinds'])}.")
        if not d.get("what"):
            errs.append(f"{did}: say `what` is delivered, in the human's terms.")
    if len(scope["deliverables"]) > 8:
        errs.append(f"{len(scope['deliverables'])} deliverables; the limit is 8 — group them.")
    kinds = deliverable_kinds(scope)

    names: Set[str] = set()
    has_write = False
    for w in scope["workspaces"]:
        name, path, mode = w.get("name", ""), w.get("path", ""), w.get("mode")
        if not re.fullmatch(r"[a-z0-9_-]+", str(name)) or name in names:
            errs.append(f"workspace name {name!r} must be unique, lowercase, [a-z0-9_-].")
        names.add(name)
        if mode not in ("write", "read"):
            errs.append(f"workspace {name}: mode must be write or read.")
        has_write = has_write or mode == "write"
        if not Path(str(path)).is_absolute() or not Path(str(path)).is_dir():
            errs.append(f"workspace {name}: {path} must be an existing absolute directory.")
    if not has_write:
        errs.append("at least one workspace must be mode write (where deliverables go).")

    work = 0
    reviewers = 0
    recon = 0
    seen: Set[str] = set()
    for p in scope["participants"]:
        agent, role, why = p.get("agent", ""), p.get("role", ""), str(p.get("why", "")).strip()
        key = f"{agent}/{role}"
        if key in seen:
            errs.append(f"{agent} is listed twice as {role}.")
        seen.add(key)
        entry = agents.get(agent)
        if entry is None:
            errs.append(f"{agent} is not a /task-pipeline agent (see references/catalog.json); "
                        "the manager itself plans, verifies, and gates.")
            continue
        if role not in entry["roles"]:
            errs.append(f"{agent} cannot take role {role!r}; its roles: {', '.join(entry['roles'])}.")
            continue
        if len(why) < 12:
            errs.append(f"{agent}: `why` must name the deliverable it has a direct bearing on.")
        if role in WORK_ROLES:
            work += 1
            reviewers += role == "reviewer"
            if not kinds & set(entry["kinds"]):
                errs.append(f"{agent} ({role}) does not apply to {', '.join(sorted(kinds))} deliverables; "
                            f"it is for: {', '.join(entry['kinds'])}.")
        else:
            recon += 1
    if work > limit("max_participants"):
        errs.append(f"{work} participants (authors, tests, reviewers); the limit is "
                    f"{limit('max_participants')} — keep only agents with a direct bearing on the output.")
    if reviewers > limit("max_reviewers"):
        errs.append(f"{reviewers} reviewers; the limit is {limit('max_reviewers')}.")
    if recon > limit("max_recon_agents"):
        errs.append(f"{recon} recon agents; the limit is {limit('max_recon_agents')}.")

    for kind in sorted(kinds):
        authors = [a for a in participants(scope, "author") if kind in agents.get(a, {}).get("kinds", [])]
        if not authors:
            who = ", ".join(d["id"] for d in scope["deliverables"] if d.get("kind") == kind)
            errs.append(f"no author participant for {kind} deliverables ({who}).")

    mode = scope.get("review")
    if mode not in REVIEW_MODES:
        errs.append(f"review must be one of {', '.join(REVIEW_MODES)}.")
    elif mode == "none" and reviewers:
        errs.append(f"review is 'none' but {', '.join(participants(scope, 'reviewer'))} is listed as a reviewer — "
                    "drop it or choose a review mode.")
    elif mode != "none" and not reviewers:
        errs.append(f"review '{mode}' needs a reviewer participant.")

    budget = scope.get("budget_minutes")
    if budget is not None and (not isinstance(budget, int) or not 15 <= budget <= 2880):
        errs.append("budget_minutes must be a whole number of minutes between 15 and 2880 (or null).")
    for t in scope.get("terms", []):
        if not t.get("term") or not t.get("means"):
            errs.append("each term needs `term` and `means` (and ideally `not`).")
    return errs


def render(scope: Dict[str, Any]) -> str:
    out = [f"# Scope — {scope['title']}", "", f"**Output:** {scope['output']}", ""]
    budget = scope.get("budget_minutes")
    out += [f"**Budget:** {budget} min, planning included." if budget else "**Budget:** none set.",
            f"**Review:** {scope['review']}.", "", "## Deliverables"]
    out += [f"- {d['id']} ({d['kind']}): {d['what']}" + (f" — in `{d['where']}`" if d.get("where") else "")
            for d in scope["deliverables"]]
    if scope.get("terms"):
        out += ["", "## Significant terms"]
        out += [f"- **{t['term']}** — {t['means']}" + (f" Not: {t['not']}" if t.get("not") else "")
                for t in scope["terms"]]
    if scope.get("non_goals"):
        out += ["", "## Non-goals"] + [f"- {g}" for g in scope["non_goals"]]
    out += ["", "## Participants"]
    out += [f"- {p['agent']} ({p['role']}): {p['why']}" for p in scope["participants"]]
    out += ["", "## Workspaces"]
    out += [f"- {w['name']} ({w['mode']}): `{w['path']}`" for w in scope["workspaces"]]
    if scope.get("answers"):
        out += ["", "## Human answers"] + [f"- {a['q']} — {a['a']}" for a in scope["answers"]]
    return "\n".join(out) + "\n"


def cmd_check(wf: Workflow) -> str:
    state = wf.load()
    if state["phase"] != "SCOPING":
        raise TPError(f"Scope is checked in SCOPING; the workflow is {state['phase']}.",
                      "To change a confirmed scope, the human must ask: `tp revise --scope --feedback ...`.")
    scope = load_scope(wf)
    errs = validate(scope)
    if errs:
        raise TPError(*errs)
    (wf.root / "scope.md").write_text(render(scope))
    state["scope_checked_sha"] = sha_file(wf.scope_json)
    state["budget_minutes"] = scope.get("budget_minutes")
    wf.save(state)
    wf.event("scope_check")
    return (f"scope ok — rendered {wf.root / 'scope.md'}.\n"
            "Present it to the human and ask them to confirm (AskUserQuestion). On yes: "
            "`tp scope confirm --answer \"<their words>\"`.")


def cmd_confirm(wf: Workflow, answer: str) -> str:
    state = wf.load()
    if state["phase"] != "SCOPING":
        raise TPError(f"Nothing to confirm: the workflow is {state['phase']}.")
    if not state.get("scope_checked_sha") or state["scope_checked_sha"] != sha_file(wf.scope_json):
        raise TPError("Run `tp scope check` on the current scope.json first.")
    state["scope_sha"] = state["scope_checked_sha"]
    state["phase"] = "PLANNING"
    state["scope_confirmed"] = now_iso()
    wf.save(state)
    wf.decision("scope confirm", answer)
    wf.event("scope_confirm")
    return "scope confirmed and frozen. Now PLANNING — run `tp next`."


def cmd_suggest(kinds: List[str]) -> str:
    cat = catalog()
    out = ["Minimal participants — confirm each with the human; drop any without a direct bearing on the output:"]
    for kind in kinds:
        if kind not in cat["kinds"]:
            raise TPError(f"unknown kind {kind!r}; kinds: {', '.join(cat['kinds'])}.")
        s = cat["suggest"][kind]
        if s.get("author"):
            out.append(f"  {kind}: author    {s['author']} — {cat['agents'][s['author']]['use']}")
        else:
            out.append(f"  {kind}: author    ask the human which system and which liaison writes to it")
        if s.get("tests"):
            out.append(f"  {kind}: tests     {s['tests']} — {cat['agents'][s['tests']]['use']}")
        for agent in s.get("ask", []):
            out.append(f"  {kind}: ask       {agent} (reviewer) — {cat['agents'][agent]['use']}; "
                       "only if the human wants review beyond the scripted checks")
    out.append("Recon: none by default — `tp survey` maps repository structure. Ask the human before "
               "adding a recon agent, and only for a question the survey cannot answer.")
    return "\n".join(out)
