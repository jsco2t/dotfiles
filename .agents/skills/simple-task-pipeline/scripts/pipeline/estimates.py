"""Advisory duration estimates. Legacy budget fields remain readable, never enforced."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

STAGES = ("scope", "research", "planning", "execution", "review", "closeout")


def validate(data: Dict[str, Any]) -> List[str]:
    estimates = data.get("estimates", {})
    if not isinstance(estimates, dict):
        return ["estimates must be an object of stage names and estimated minutes."]
    return [f"estimates.{key} must name a stage ({', '.join(STAGES)}) with nonnegative whole minutes."
            for key, value in estimates.items()
            if key not in STAGES or type(value) is not int or value < 0]


def calculate(scope: Dict[str, Any], plan: Optional[Dict[str, Any]] = None,
              state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Do not invent missing estimates on old workflows or require replanning to add them.
    A concrete plan supplies execution/review; research includes any saved research items.
    Other stages come from the operator-visible scope/plan estimate metadata."""
    from . import plan as planmod

    stages = dict.fromkeys(STAGES)
    for data in (scope, plan or {}):
        values = data.get("estimates", {})
        if isinstance(values, dict):
            stages.update({k: v for k, v in values.items() if k in STAGES and type(v) is int and v >= 0})
    research = scope.get("research") or {}
    if stages["research"] is None:
        stages["research"] = research.get("budget_minutes", 0) if isinstance(research, dict) else 0
    if state:
        items = state.get("recon", {}).values()
        reserved = sum(i.get("minutes", 15) for i in items if i.get("status") != "dropped")
        stages["research"] = max(stages["research"], reserved,
                                 (research.get("budget_minutes", 0) if isinstance(research, dict) else 0)
                                 + state.get("research_extra", 0))
    if plan and isinstance(plan.get("tasks"), list):
        stages["execution"] = sum(t.get("estimate_min", 0) for t in plan["tasks"])
        _, tail = planmod.review_tail(plan, scope)
        per_task = sum(planmod.REVIEW_MINUTES for t in plan["tasks"] if planmod.reviewer_for(t, scope))
        stages["review"] = tail + per_task
    complete = all(type(value) is int for value in stages.values())
    total = sum(stages.values()) if complete else scope.get("budget_minutes")
    return {"stages": stages, "total_min": total, "complete": complete}


def render(data: Dict[str, Any]) -> str:
    parts = [f"{stage} {value} min" if value is not None else f"{stage} not estimated"
             for stage, value in data["stages"].items()]
    total = data["total_min"]
    total_text = f"{total} min" if total is not None else "not estimated"
    return f"Estimates (advisory): {' · '.join(parts)} · total {total_text}."
