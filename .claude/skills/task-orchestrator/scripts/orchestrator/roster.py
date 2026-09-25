"""The agent roster, pipeline stages, and task-type rules.

This module is the single source of truth shared by the CLI and the hooks.
Agent definitions live in ~/.claude/agents/<name>.md; every name here must have
a matching file (``orch doctor`` checks).
"""
from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Tuple

# ---------------------------------------------------------------- agents
#
# role:
#   author    creates or modifies deliverables inside declared workspaces
#   planner   writes the plan package during PLANNING
#   readonly  never writes outside its own report files in the workflow dir
AGENTS: Dict[str, Dict[str, str]] = {
    # Task workers (group B): create or modify things.
    "code-author": {"role": "author", "kind": "worker"},
    "test-author": {"role": "author", "kind": "worker"},
    "doc-author": {"role": "author", "kind": "worker"},
    "kb-author": {"role": "author", "kind": "worker"},
    "tutorial-author": {"role": "author", "kind": "worker"},
    "education-author": {"role": "author", "kind": "worker"},
    "planning-author": {"role": "planner", "kind": "worker"},
    "test-planner": {"role": "planner", "kind": "worker"},
    # Skill-driven specialists (group A): research, review, verify, integrate, gate.
    "codebase-researcher": {"role": "readonly", "kind": "specialist"},
    "domain-researcher": {"role": "readonly", "kind": "specialist"},
    "code-reviewer": {"role": "readonly", "kind": "specialist"},
    "test-reviewer": {"role": "readonly", "kind": "specialist"},
    "doc-reviewer": {"role": "readonly", "kind": "specialist"},
    "architecture-reviewer": {"role": "readonly", "kind": "specialist"},
    "ux-reviewer": {"role": "readonly", "kind": "specialist"},
    "task-verifier": {"role": "readonly", "kind": "specialist"},
    "project-manager": {"role": "readonly", "kind": "specialist"},
    "atlassian-liaison": {"role": "readonly", "kind": "specialist"},
    "github-liaison": {"role": "readonly", "kind": "specialist"},
}

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
    "research": {"agents": RESEARCHERS | LIAISONS, "fields": ()},
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
    # plumbing
    "selftest": {"agents": ROSTER, "fields": ()},
}

VERDICTS = frozenset({"pass", "fail", "n/a"})
STATUSES = frozenset({"complete", "needs_input", "blocked"})

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
DEFAULT_BUDGETS = {
    "task_attempts": 3,        # full pipeline attempts per task before a human decides
    "review_passes": 3,        # verification/review passes per attempt before a human decides
    "final_review_passes": 3,  # whole-package review passes before a human decides
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
}


def required_final_reviewers(task_types: List[str], doc_files_changed: bool) -> List[str]:
    types = set(task_types)
    out: List[str] = []
    if types & CODE_LIKE_TYPES:
        out += ["code-reviewer", "architecture-reviewer", "test-reviewer"]
    if types & PROSE_TYPES or doc_files_changed:
        out.append("doc-reviewer")
    return out
