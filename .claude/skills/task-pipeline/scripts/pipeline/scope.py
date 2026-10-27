"""Scope: what will be delivered, who works on it, the time budget, and the research budget —
checked, rendered, and frozen when the human confirms it. Budgets are the manager's reporting
metadata: they forecast and report, and never gate or shrink the work."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .common import TPError, Workflow, catalog, limit, load_json, now_iso, sha_file

REVIEW_MODES = ("none", "final", "per-task", "both")
WORK_ROLES = ("author", "tests", "reviewer")
ROLE_ALIASES = {"recon": "research"}  # workflows created before research budgets called it recon


def load_scope(wf: Workflow) -> Dict[str, Any]:
    data = load_json(wf.scope_json, "the scope")
    if not isinstance(data, dict):
        raise TPError(f"{wf.scope_json} must hold a JSON object.")
    return data


def deliverable_kinds(scope: Dict[str, Any]) -> Set[str]:
    return {str(d["kind"]) for d in scope.get("deliverables", []) if isinstance(d, dict) and d.get("kind")}


def role_of(p: Dict[str, Any]) -> str:
    role = str(p.get("role", ""))
    return ROLE_ALIASES.get(role, role)


def agent_kinds(agent: str, role: str) -> List[str]:
    """The deliverable kinds an agent takes in one role: its catalog `role_kinds` for that role when
    set (architecture-reviewer reviews code but authors research), otherwise its `kinds`."""
    entry = catalog()["agents"].get(agent, {})
    return list(entry.get("role_kinds", {}).get(role, entry.get("kinds", [])))


def participants(scope: Dict[str, Any], role: str) -> List[str]:
    return [p["agent"] for p in scope.get("participants", []) if isinstance(p, dict) and role_of(p) == role]


def workspaces(scope: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {w["name"]: w for w in scope.get("workspaces", []) if isinstance(w, dict) and "name" in w}


def research_budget(scope: Dict[str, Any]) -> int:
    research = scope.get("research") or {}
    return int(research.get("budget_minutes") or 0) if isinstance(research, dict) else 0


def fix_tasks(scope: Dict[str, Any]) -> Dict[str, Any]:
    """The human's standing answer on fix tasks: how many small fix tasks the manager may add
    without asking, and how big each may be. A scope from before the question allows none."""
    fx = scope.get("fix_tasks")
    return fx if isinstance(fx, dict) else {"allow": 0}


FIX_TASKS_ASK = ("Ask the human, in the scope question, whether you may add small fix tasks without asking them each "
                 "time (a doc that needs one clarifying sentence, a stale comment) — and if so how many, and how many "
                 "minutes each — then record their words: \"fix_tasks\": {\"allow\": 2, \"max_minutes\": 15, "
                 "\"answer\": \"<their words>\"} (allow 0: every fix task is asked).")


def _fix_task_errors(scope: Dict[str, Any]) -> List[str]:
    fx = scope.get("fix_tasks")
    if not isinstance(fx, dict):
        return ["scope.json needs `fix_tasks`. " + FIX_TASKS_ASK]
    errs = []
    allow, cap = fx.get("allow"), limit("max_delegated_fix_tasks")
    if not isinstance(allow, int) or not 0 <= allow <= cap:
        errs.append(f"fix_tasks.allow must be a whole number from 0 to {cap}.")
    elif allow:
        minutes = fx.get("max_minutes")
        if not isinstance(minutes, int) or not 1 <= minutes <= limit("max_task_minutes"):
            errs.append(f"fix_tasks.max_minutes must be a whole number from 1 to {limit('max_task_minutes')}: how big "
                        "one fix task may be.")
    if len(str(fx.get("answer", "")).strip()) < 2:
        errs.append("fix_tasks.answer must hold the human's words, verbatim. " + FIX_TASKS_ASK)
    return errs


def final_reviewers(scope: Dict[str, Any]) -> List[str]:
    return participants(scope, "reviewer") if scope.get("review") in ("final", "both") else []


def review_units(scope: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The final review's sessions per batch: each catalog pack whose confirmed members number two
    or more runs as one session of its runner agent (each member a lens); every other confirmed
    reviewer runs as itself. kinds: what the unit reviews (its members' reviewer kinds)."""
    reviewers = final_reviewers(scope)
    units, packed = [], set()
    for runner, members in catalog().get("review_packs", {}).items():
        if runner.startswith("_"):
            continue
        chosen = [r for r in reviewers if r in members]
        if len(chosen) >= 2:
            packed |= set(chosen)
            units.append({"name": runner, "agent": runner, "lenses": chosen,
                          "kinds": sorted({k for r in chosen for k in agent_kinds(r, "reviewer")})})
    for r in reviewers:
        if r not in packed:
            units.append({"name": r, "agent": r, "lenses": [], "kinds": agent_kinds(r, "reviewer")})
    return units


def roles() -> Dict[str, Any]:
    return catalog().get("roles", {})


def is_transport(agent: Optional[str]) -> bool:
    return agent in roles().get("transport", [])


def is_code_file(path: str) -> bool:
    return Path(str(path)).suffix.lower() in roles().get("code_extensions", [])


def validate(scope: Dict[str, Any], require_fix_tasks: bool = True) -> List[str]:
    """require_fix_tasks: False for a scope confirmed before the fix-task question existed — a
    revision or amendment of it must not force that question on the human mid-run (it allows
    no delegated fix tasks)."""
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
        if not re.fullmatch(r"[a-z0-9_-]+", str(name)) or name in names or name in ("research", "recon", "wf"):
            errs.append(f"workspace name {name!r} must be unique, lowercase, [a-z0-9_-], and not 'research' or "
                        "'wf' (source prefixes for research items and the workflow folder).")
        names.add(name)
        if mode not in ("write", "read"):
            errs.append(f"workspace {name}: mode must be write or read.")
        has_write = has_write or mode == "write"
        if not Path(str(path)).is_absolute() or not Path(str(path)).is_dir():
            errs.append(f"workspace {name}: {path} must be an existing absolute directory.")
    if not has_write:
        errs.append("at least one workspace must be mode write (where deliverables go).")

    work = reviewers = 0
    seen: Set[str] = set()
    for p in scope["participants"]:
        agent, role, why = p.get("agent", ""), role_of(p), str(p.get("why", "")).strip()
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
            if not kinds & set(agent_kinds(agent, role)):
                errs.append(f"{agent} ({role}) does not apply to {', '.join(sorted(kinds))} deliverables; "
                            f"as {role} it is for: {', '.join(agent_kinds(agent, role))}.")
    if work > limit("max_participants"):
        errs.append(f"{work} participants (authors, tests, reviewers); the limit is "
                    f"{limit('max_participants')} — keep only agents with a direct bearing on the output.")
    if reviewers > limit("max_reviewers"):
        errs.append(f"{reviewers} reviewers; the limit is {limit('max_reviewers')} — keep the lenses this change needs.")

    for kind in sorted(kinds - {"integration"}):  # tp publish posts integration work; a liaison is optional
        authors = [a for a in participants(scope, "author") if kind in agent_kinds(a, "author")]
        if not authors:
            who = ", ".join(d["id"] for d in scope["deliverables"] if d.get("kind") == kind)
            errs.append(f"no author participant for {kind} deliverables ({who}).")

    mode = scope.get("review")
    if mode not in REVIEW_MODES:
        errs.append(f"review must be one of {', '.join(REVIEW_MODES)} (final is the norm: bulk, at the end).")
    elif mode == "none" and reviewers:
        errs.append(f"review is 'none' but {', '.join(participants(scope, 'reviewer'))} is listed as a reviewer — "
                    "drop it or choose a review mode.")
    elif mode != "none" and not reviewers:
        errs.append(f"review '{mode}' needs a reviewer participant.")
    if mode == "none" and "code" in deliverable_kinds(scope):
        errs.append("code deliverables are always reviewed: set review to final (or per-task) and confirm a reviewer "
                    "(`tp roster suggest --kinds code`).")

    budget = scope.get("budget_minutes")
    if budget is not None and (not isinstance(budget, int) or not 15 <= budget <= 2880):
        errs.append("budget_minutes must be a whole number of minutes between 15 and 2880 (or null).")
    research = scope.get("research")
    rb = research_budget(scope)
    researchers = participants(scope, "research")
    if research is not None and (not isinstance(research, dict) or not isinstance(research.get("budget_minutes", 0), int)
                                 or research.get("budget_minutes", 0) < 0):
        errs.append("research must be {\"budget_minutes\": <agent-minutes>, \"why\": \"...\"}.")
    elif rb and not researchers:
        errs.append("a research budget needs at least one research participant.")
    elif rb:
        if len(str(research.get("why", "")).strip()) < 12:
            errs.append("research.why must say what is unknown enough to need research.")
    for t in scope.get("terms", []):
        if not t.get("term") or not t.get("means"):
            errs.append("each term needs `term` and `means` (and ideally `not`).")
    if require_fix_tasks or "fix_tasks" in scope:
        errs += _fix_task_errors(scope)
    return errs


def warnings(scope: Dict[str, Any]) -> List[str]:
    """What the scope check reports but never refuses: budgets are estimates, not gates."""
    out = []
    budget, rb = scope.get("budget_minutes"), research_budget(scope)
    lanes = limit("max_in_flight")
    if rb and isinstance(budget, int) and math.ceil(rb / lanes) >= budget:
        out.append(f"the research estimate ({rb} agent-min, about {math.ceil(rb / lanes)} min on {lanes} lanes) takes "
                   f"the whole {budget}-min budget on its own. Both are estimates: raise budget_minutes if that is "
                   "the honest forecast; never shrink the research to fit.")
    return out


def render(scope: Dict[str, Any]) -> str:
    out = [f"# Scope — {scope['title']}", "", f"**Output:** {scope['output']}", ""]
    budget = scope.get("budget_minutes")
    rb = research_budget(scope)
    out += [f"**Budget:** {budget} min, planning included." if budget else "**Budget:** none set.",
            f"**Research budget:** {rb} agent-min — {scope['research'].get('why', '')}" if rb
            else "**Research:** none — the work is specified well enough to plan directly.",
            f"**Review:** {scope['review']}.", _fix_tasks_line(scope), "", "## Deliverables"]
    out += [f"- {d['id']} ({d['kind']}): {d['what']}" + (f" — in `{d['where']}`" if d.get("where") else "")
            for d in scope["deliverables"]]
    if scope.get("terms"):
        out += ["", "## Significant terms"]
        out += [f"- **{t['term']}** — {t['means']}" + (f" Not: {t['not']}" if t.get("not") else "")
                for t in scope["terms"]]
    if scope.get("non_goals"):
        out += ["", "## Non-goals"] + [f"- {g}" for g in scope["non_goals"]]
    out += ["", "## Participants"]
    out += [f"- {p['agent']} ({role_of(p)}): {p['why']}" for p in scope["participants"]]
    out += ["", "## Workspaces"]
    out += [f"- {w['name']} ({w['mode']}): `{w['path']}`" for w in scope["workspaces"]]
    if scope.get("answers"):
        out += ["", "## Human answers"] + [f"- {a['q']} — {a['a']}" for a in scope["answers"]]
    return "\n".join(out) + "\n"


def _fix_tasks_line(scope: Dict[str, Any]) -> str:
    fx = fix_tasks(scope)
    said = f" Your answer: {fx['answer']}" if fx.get("answer") else ""
    if fx.get("allow"):
        return (f"**Fix tasks:** the manager may add up to {fx['allow']} fix tasks of {fx['max_minutes']} min or less "
                f"without asking (each one is listed in the report).{said}")
    return f"**Fix tasks:** none without asking — every fix task outside the plan is put to the human.{said}"


def cmd_check(wf: Workflow) -> str:
    state = wf.load()
    if state["phase"] != "SCOPING":
        raise TPError(f"Scope is checked in SCOPING; the workflow is {state['phase']}.",
                      "To change a confirmed scope, the human must ask: `tp revise --scope --feedback ...`.")
    scope = load_scope(wf)
    errs = validate(scope, require_fix_tasks=not state.get("scope_confirmed"))
    if errs:
        raise TPError(*errs)
    (wf.root / "scope.md").write_text(render(scope))
    state["scope_checked_sha"] = sha_file(wf.scope_json)
    state["budget_minutes"] = scope.get("budget_minutes")
    wf.save(state)
    wf.event("scope_check")
    return ("".join(f"WARN: {w}\n" for w in warnings(scope)) + f"scope ok — rendered {wf.root / 'scope.md'}.\n"
            "Present it to the human and ask them to confirm (AskUserQuestion); the budgets in it are your "
            "own estimates, shown for information, not for approval. On yes: "
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
    kept = _keep_approved_plan(wf, state)
    wf.save(state)
    wf.decision("scope confirm", answer)
    wf.event("scope_confirm")
    if kept:
        wf.decision("plan approval kept", "plan.json is unchanged since the human approved it and still fits the "
                    "confirmed scope, so that approval stands", who=None)
        wf.event("plan_approval_kept")
        return ("scope confirmed and frozen. The approved plan is unchanged and still fits it, so its approval stands: "
                "EXECUTING — run `tp next`.")
    return "scope confirmed and frozen. Now PLANNING — run `tp next`."


def _keep_approved_plan(wf: Workflow, state: Dict[str, Any]) -> bool:
    """After `tp revise --scope` mid-run, the plan the human approved stays approved when plan.json
    is byte-identical and still valid under the newly confirmed scope: asking them to approve it
    again would approve nothing new. Otherwise planning resumes as usual."""
    from . import plan as planmod
    from . import review
    revised = state.pop("revised_from", None)
    if not revised or not revised.get("plan_sha") or sha_file(wf.plan_json) != revised["plan_sha"]:
        return False
    plan, scope = planmod.load_plan(wf), load_scope(wf)
    if planmod.validate(plan, scope, state, wf.root, {t["id"] for t in plan["tasks"]}):
        return False
    state["plan_approved_sha"] = state["plan_submitted_sha"] = revised["plan_sha"]
    state["phase"] = "EXECUTING"
    planmod.merge_baselines(wf, state, scope)
    state["reviews"] = review.new_reviews(plan, scope, state.get("reviews", {}))
    state["integration"] = review.integration_ids(plan, scope)
    (wf.root / "plan.md").write_text(planmod.render(plan, scope, wf))
    return True


def cmd_budget_extend(wf: Workflow, minutes: int, answer: Optional[str], note: Optional[str]) -> str:
    """Raise the whole-job budget while PLANNING or EXECUTING. It is the manager's re-estimate —
    bookkeeping that keeps the forecast and the report honest, never a human approval and never a
    gate; when the human volunteers words, they are recorded as theirs."""
    if minutes < 1:
        raise TPError("budget extend needs a positive number of minutes.")
    if not (answer or note):
        raise TPError("say why: --note \"<your re-estimate>\", or --answer \"<the human's words>\" if they gave one.")
    with wf.locked():
        state = wf.load()
        if state["phase"] not in ("PLANNING", "EXECUTING"):
            raise TPError(f"budget extend applies while PLANNING or EXECUTING; the workflow is {state['phase']}.")
        scope = load_scope(wf)
        old = scope.get("budget_minutes")
        new = int(old or 0) + minutes
        if new > 2880:
            raise TPError(f"budget_minutes would reach {new}; the cap is 2880.")
        scope["budget_minutes"] = new
        wf.scope_json.write_text(json.dumps(scope, indent=2) + "\n")
        (wf.root / "scope.md").write_text(render(scope))
        # The frozen scope moves with the number, or every later check would read it as tampered.
        state["budget_minutes"] = new
        state["scope_sha"] = state["scope_checked_sha"] = sha_file(wf.scope_json)
        wf.save(state)
        wf.decision(f"budget extend +{minutes} min", f"{old or 'none'} → {new}: {answer or note}",
                    who="human" if answer else "manager")
        wf.event("budget_extend", minutes=minutes, budget=new)
        return (f"budget is now {new} min (was {old or 'none'}) — reported in `tp next`, `tp digest`, and the "
                "report; it gates nothing.")


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
        for agent, entry in cat["agents"].items():
            if agent != s.get("author") and "author" in entry["roles"] and kind in agent_kinds(agent, "author"):
                out.append(f"  {kind}: author?   {agent} — {entry['use']}")
        if s.get("tests"):
            out.append(f"  {kind}: tests     {s['tests']} — {cat['agents'][s['tests']]['use']}")
        for agent in s.get("ask", []):
            out.append(f"  {kind}: review?   {agent} — {cat['agents'][agent]['use']}")
        for agent in s.get("research", []):
            out.append(f"  {kind}: research? {agent} — {cat['agents'][agent]['use']}")
    out.append("Reviewers run once, at the end, in bulk — choose only the lenses this change needs.")
    out.append("Research is the manager's call, and a clear, small ask needs none; size its budget yourself as "
               "reporting metadata. Other research agents: "
               + ", ".join(sorted(a for a, e in cat["agents"].items() if "research" in e["roles"])) + ".")
    return "\n".join(out)
