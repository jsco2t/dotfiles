"""The agent roster, pipeline stages, and task-type rules.

This module is the single source of truth shared by the CLI and the hooks.
Agent definitions live in ~/.claude/agents/<name>.md; every name here must have
a matching file whose frontmatter pins the model and effort listed here and
registers the budget hook (``orch doctor`` checks).
"""
from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Tuple

# ---------------------------------------------------------------- agents
#
# role:
#   author    creates or modifies deliverables inside declared workspaces
#   planner   writes the plan package during PLANNING
#   readonly  never writes outside its own report files in the workflow dir
# model / effort: what the agent definition's frontmatter must pin.
AGENTS: Dict[str, Dict[str, str]] = {
    # Task workers (group B): create or modify things.
    "code-author": {"role": "author", "kind": "worker", "model": "opus", "effort": "xhigh"},
    "test-author": {"role": "author", "kind": "worker", "model": "opus", "effort": "xhigh"},
    "doc-author": {"role": "author", "kind": "worker", "model": "opus", "effort": "high"},
    "kb-author": {"role": "author", "kind": "worker", "model": "opus", "effort": "high"},
    "tutorial-author": {"role": "author", "kind": "worker", "model": "opus", "effort": "high"},
    "education-author": {"role": "author", "kind": "worker", "model": "opus", "effort": "high"},
    "planning-author": {"role": "planner", "kind": "worker", "model": "opus", "effort": "xhigh"},
    "test-planner": {"role": "planner", "kind": "worker", "model": "opus", "effort": "high"},
    # Skill-driven specialists (group A): research, review, verify, integrate, gate.
    "codebase-researcher": {"role": "readonly", "kind": "specialist", "model": "opus", "effort": "high"},
    "domain-researcher": {"role": "readonly", "kind": "specialist", "model": "opus", "effort": "high"},
    "code-reviewer": {"role": "readonly", "kind": "specialist", "model": "opus", "effort": "xhigh"},
    "test-reviewer": {"role": "readonly", "kind": "specialist", "model": "opus", "effort": "high"},
    "doc-reviewer": {"role": "readonly", "kind": "specialist", "model": "opus", "effort": "high"},
    "architecture-reviewer": {"role": "readonly", "kind": "specialist", "model": "opus", "effort": "xhigh"},
    "ux-reviewer": {"role": "readonly", "kind": "specialist", "model": "opus", "effort": "high"},
    "task-verifier": {"role": "readonly", "kind": "specialist", "model": "opus", "effort": "high"},
    "project-manager": {"role": "readonly", "kind": "specialist", "model": "opus", "effort": "high"},
    "atlassian-liaison": {"role": "readonly", "kind": "specialist", "model": "sonnet", "effort": "high"},
    "github-liaison": {"role": "readonly", "kind": "specialist", "model": "sonnet", "effort": "high"},
}

# The frontmatter hook every roster agent registers (PreToolUse, matcher "*").
BUDGET_HOOK_COMMAND = 'python3 "$HOME/.claude/skills/task-orchestrator/scripts/hook.py" budget'

ROSTER: FrozenSet[str] = frozenset(AGENTS)
AUTHORS: FrozenSet[str] = frozenset(n for n, a in AGENTS.items() if a["role"] == "author")
PLANNERS: FrozenSet[str] = frozenset(n for n, a in AGENTS.items() if a["role"] == "planner")
READONLY: FrozenSet[str] = frozenset(n for n, a in AGENTS.items() if a["role"] == "readonly")
REVIEWERS: FrozenSet[str] = frozenset(
    {"code-reviewer", "test-reviewer", "doc-reviewer", "architecture-reviewer", "ux-reviewer"}
)
RESEARCHERS: FrozenSet[str] = frozenset({"codebase-researcher", "domain-researcher"})
LIAISONS: FrozenSet[str] = frozenset({"atlassian-liaison", "github-liaison"})

# Agents that may act as the "author" of a work/fix stage (the deliverable
# producer for a task). Researchers and liaisons produce their deliverable as a
# report in the workflow dir (research findings, a dry-run / executed external
# action), never by writing into a workspace.
WORK_AGENTS: FrozenSet[str] = AUTHORS | {"planning-author"} | RESEARCHERS | LIAISONS

# ---------------------------------------------------------------- stages
#
# stage -> (agent types allowed to report it, required result fields beyond the base set)
BASE_FIELDS: Tuple[str, ...] = ("workflow", "stage", "status", "verdict", "report")

STAGES: Dict[str, Dict[str, Any]] = {
    # planning
    "pm-research-plan": {"agents": frozenset({"project-manager"}), "fields": ("approved", "rejected")},
    "research": {"agents": RESEARCHERS | LIAISONS, "fields": ()},  # + `item` (ledger.validate_result)
    "pm-research": {"agents": frozenset({"project-manager"}), "fields": ()},
    "plan": {"agents": frozenset({"planning-author"}), "fields": ("plan_revision",)},
    "test-plan": {"agents": frozenset({"test-planner"}), "fields": ("plan_revision",)},
    "plan-review": {
        "agents": frozenset({"architecture-reviewer", "doc-reviewer", "ux-reviewer", "test-reviewer"}),
        "fields": ("plan_revision", "plan_hash"),
    },
    "pm-plan": {"agents": frozenset({"project-manager"}), "fields": ("plan_hash",)},
    # loops
    "pm-loop-entry": {"agents": frozenset({"project-manager"}), "fields": ("loop",)},
    "pm-loop-exit": {"agents": frozenset({"project-manager"}), "fields": ("loop", "snapshot")},
    # tasks
    "readiness": {"agents": frozenset({"task-verifier"}), "fields": ("task", "attempt")},
    "pm-start": {"agents": frozenset({"project-manager"}), "fields": ("task", "attempt")},
    "work": {"agents": WORK_AGENTS, "fields": ("task", "attempt", "round")},
    "fix": {"agents": WORK_AGENTS, "fields": ("task", "attempt", "round")},
    "pm-scope": {"agents": frozenset({"project-manager"}), "fields": ("task", "attempt", "round", "snapshot")},
    "verification": {
        "agents": frozenset({"task-verifier"}),
        "fields": ("task", "attempt", "round", "snapshot", "criteria"),
    },
    "review": {"agents": REVIEWERS, "fields": ("task", "attempt", "round", "snapshot", "findings")},
    "pm-accept": {
        "agents": frozenset({"project-manager"}),
        "fields": ("task", "attempt", "snapshot", "scan_digest"),
    },
    "pm-resolution": {"agents": frozenset({"project-manager"}), "fields": ("task",)},
    # final
    "final-review": {"agents": REVIEWERS, "fields": ("round", "snapshot", "findings")},
    "final-fix": {"agents": WORK_AGENTS, "fields": ("round",)},
    "final-verification": {
        "agents": frozenset({"task-verifier"}),
        "fields": ("round", "snapshot", "criteria"),
    },
    "pm-final": {"agents": frozenset({"project-manager"}), "fields": ("snapshot",)},
    # any phase: the PM's review of an agent's interim report (time budget reached)
    "pm-interim": {"agents": frozenset({"project-manager"}),
                   "fields": ("interim_agent", "decision", "grant_minutes")},
    # plumbing
    "selftest": {"agents": ROSTER, "fields": ()},
}

VERDICTS = frozenset({"pass", "fail", "n/a"})
# `interim`: the budget hook stopped the agent (time budget reached, or the human
# paused the workflow) and it wrote an interim report instead of finishing.
STATUSES = frozenset({"complete", "needs_input", "blocked", "interim"})
# pm-interim decisions. continue: on course, carry on. redirect: carry on, but only
# on what the PM names. split: finish the answered part now; the rest becomes new,
# separately approved research.
INTERIM_DECISIONS = ("continue", "redirect", "split")
MAX_GRANT_MINUTES = 60

# Stages whose verdict is a gate (must be pass/fail, never n/a).
GATE_STAGES = frozenset(
    s for s in STAGES if s.startswith("pm-") or s in {
        "readiness", "verification", "review", "final-review", "final-verification", "plan-review",
    }
)

# ---------------------------------------------------------------- task types
#
# authors:        allowed author sequences (each a tuple, run in order)
# min_reviewers:  reviewers that MUST pass; a plan may add more, never fewer
# test_forward:   allowed test_forward modes (first is the default expectation)
# needs_checks:   red_green commands required for these modes
TASK_TYPES: Dict[str, Dict[str, Any]] = {
    "code": {
        "authors": (("test-author", "code-author"),),
        "min_reviewers": ("code-reviewer", "test-reviewer"),
        "test_forward": ("red-green", "characterization", "not-applicable"),
    },
    "test": {
        "authors": (("test-author",),),
        "min_reviewers": ("test-reviewer", "code-reviewer"),
        "test_forward": ("characterization",),
    },
    "docs": {
        "authors": (("doc-author",),),
        "min_reviewers": ("doc-reviewer",),
        "test_forward": ("not-applicable",),
    },
    "kb": {
        "authors": (("kb-author",),),
        "min_reviewers": ("doc-reviewer",),
        "test_forward": ("not-applicable",),
    },
    "tutorial": {
        "authors": (("tutorial-author",),),
        "min_reviewers": ("doc-reviewer",),
        "test_forward": ("not-applicable",),
    },
    "education": {
        "authors": (("education-author",),),
        "min_reviewers": ("doc-reviewer",),
        "test_forward": ("not-applicable",),
    },
    "pm": {
        "authors": (("planning-author",),),
        "min_reviewers": ("doc-reviewer",),
        "test_forward": ("not-applicable",),
    },
    "research": {
        "authors": (("codebase-researcher", "doc-author"), ("domain-researcher", "doc-author")),
        "min_reviewers": ("doc-reviewer",),
        "test_forward": ("not-applicable",),
    },
    "integration": {
        "authors": (("atlassian-liaison",), ("github-liaison",)),
        "min_reviewers": (),
        "test_forward": ("not-applicable",),
    },
}

CODE_LIKE_TYPES = frozenset({"code", "test"})
PROSE_TYPES = frozenset({"docs", "kb", "tutorial", "education", "pm", "research"})

TEST_FORWARD_MODES = ("red-green", "characterization", "not-applicable")

# Budgets (the user's stated maxima).
DEFAULT_BUDGETS: Dict[str, Any] = {
    "task_attempts": 3,        # full pipeline attempts per task before a human decides
    "review_passes": 3,        # verification/review passes per attempt before a human decides
    "final_review_passes": 3,  # whole-package review passes before a human decides
    "time_grants": 2,          # PM-approved time extensions per agent before a human decides
}

# Active minutes an agent may run per dispatch before the budget hook stops it and
# it writes an interim report for the PM. Agents not listed are logged, not limited.
DEFAULT_AGENT_MINUTES: Dict[str, int] = {
    "codebase-researcher": 30,
    "domain-researcher": 30,
    "atlassian-liaison": 30,
    "github-liaison": 30,
}

# Actions a human may take to leave NEEDS_HUMAN, keyed by needs_human kind.
RESOLVE_ACTIONS: Dict[str, Tuple[str, ...]] = {
    "question": ("answer",),
    "environment": ("answer", "retry"),
    "review_budget": ("continue", "waive", "retry"),
    "task_budget": ("retry",),
    "final_review_budget": ("continue", "waive"),
    "external_write": ("confirm",),
    "readiness": ("answer", "retry"),
    "continuation_budget": ("continue",),
    "integrity": ("answer",),
    "time_budget": ("continue", "answer"),
}

# ---------------------------------------------------------------- workflow kinds
#
# The kind of deliverable a workflow produces, chosen at `orch init`. It decides the
# default non-goals every brief carries and how deep planning research goes.
KINDS = ("code", "docs", "kb", "tutorial", "education", "research", "pm", "integration", "mixed")
DOC_KINDS = frozenset({"docs", "kb", "tutorial", "education"})
LEGACY_KIND = "mixed"  # workflows created before kinds existed

RECORD_DONT_INVESTIGATE = (
    "Record, don't investigate. When something outside your questions catches your eye — docs that "
    "disagree with the code, code that looks wrong, a risk, a gap — write ONE line under "
    "\"Noticed, not investigated\" in your report (what you saw, `file:line` or source) and move on. "
    "Re-verifying it, grading it, tracing its cause, or proposing a fix is investigation: do it only "
    "when your brief's own questions ask for it."
)

NON_GOALS: Dict[str, str] = {
    "docs": ("This workflow produces documentation. Document what the code and systems do today, at the "
             "commits the decisions log pins. Do not change, fix, test, benchmark, or security-review the "
             "code, and do not judge whether its behavior is correct."),
    "research": ("This workflow answers research questions. Answer the questions asked; change nothing, "
                 "and do not widen the questions."),
    "code": ("This workflow changes code through the plan's tasks. Change only what the tasks name; a "
             "defect you notice outside them is recorded for the human, not fixed."),
    "pm": ("This workflow produces project-management artifacts. Do not change code or documentation "
           "outside the planned artifacts."),
    "integration": ("This workflow performs the external actions the plan names — reads freely, writes "
                    "only after a dry-run and the human's confirmation. Nothing else."),
    "mixed": ("Stay within what the request and the approved plan ask for. Anything else you notice is "
              "recorded for the human, not pursued."),
}
for _kind in ("kb", "tutorial", "education"):
    NON_GOALS[_kind] = NON_GOALS["docs"]

# Focused research: limits enforced by `orch research add`.
MAX_RESEARCH_QUESTIONS = 3
MAX_QUESTION_WORDS = 60
MAX_DONE_WHEN_WORDS = 50
MAX_RESEARCH_CONTEXT_WORDS = 150
RESEARCH_REPORT_TARGET_LINES = 400
RESEARCH_MODES = ("map", "investigate")


def required_final_reviewers(task_types: List[str], doc_files_changed: bool) -> List[str]:
    types = set(task_types)
    out: List[str] = []
    if types & CODE_LIKE_TYPES:
        out += ["code-reviewer", "architecture-reviewer", "test-reviewer"]
    if types & PROSE_TYPES or doc_files_changed:
        out.append("doc-reviewer")
    return out
