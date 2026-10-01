"""Examples of every structured file in a workflow, printed on demand by `tp schema <name>`
so SKILL.md does not have to carry them."""
from __future__ import annotations

SCHEMAS = {
    "scope": {
        "title": "Stratum KB", "output": "Markdown KB under kb/, one folder per area, linked from kb/index.md",
        "deliverables": [{"id": "D1", "kind": "kb", "what": "KB covering the code, build, and a source map",
                          "where": "kb"}],
        "terms": [{"term": "comprehensive", "means": "every top-level area has an article",
                   "not": "code-quality judgements"}],
        "non_goals": ["No changes to the stratum repository"],
        "participants": [
            {"agent": "kb-author", "role": "author", "why": "Writes every article for D1."},
            {"agent": "doc-reviewer", "role": "reviewer", "why": "Reviews the finished KB for accuracy."},
            {"agent": "codebase-researcher", "role": "research", "why": "Maps dash/, which the survey cannot see."}],
        "review": "final  (none | final | per-task, rarely)",
        "budget_minutes": 180,
        "research": {"budget_minutes": 30, "why": "dash/ is 9k lines the survey only sizes; omit research when none"},
        "workspaces": [{"name": "kb", "path": "/abs/kb", "mode": "write"},
                       {"name": "src", "path": "/abs/repo", "mode": "read"}],
        "answers": [{"q": "What output?", "a": "<the human's words>"}],
    },
    "plan": {
        "title": "...", "summary": "<= 80 words", "questions": ["<non-blocking, shown at approval>"],
        "conventions": ["wf:conventions.md  (optional: every brief starts from it; frozen with the plan)"],
        "tasks": [{"id": "T01", "title": "Architecture overview", "serves": ["D1"], "agent": "kb-author",
                   "workspace": "kb", "paths": ["architecture/overview.md"],
                   "sources": ["src:internal/cluster/**", "research:R1", "wf:notes/terms.md"],
                   "brief": "<= 150 words", "acceptance": ["<1-6 objective criteria>"], "checks": ["docs"],
                   "estimate_min": 15, "depends_on": [],
                   "test_cmd": "<code tasks: go test ./pkg/x -run TestY>", "tests_paths": ["<code tasks>"],
                   "test_mode": "red | pin", "model": "sonnet | opus | haiku (optional)"}],
        "review_batches": [{"id": "B1", "tasks": ["T01", "T02"]}],
        "checks": {"vet": {"cmd": "go vet ./...", "cwd": "src"}}, "final_checks": ["docs-all"],
    },
    "research": {
        "answers": [{"q": "<the question>", "a": "<the answer>", "evidence": ["path:line, URL, or issue key"]}],
        "followups": [{"question": "<one narrow question not pursued>", "why": "<what was seen>",
                       "agent": "<who could answer it>"}],
        "unknowns": ["<what could not be established>"],
        "areas": [{"name": "(map purpose only)", "paths": ["..."], "size": "<files / lines>", "note": "..."}],
    },
    "result": {
        "task": "T01", "step": "author | tests | impl | fix", "status": "done | blocked | needs_input",
        "summary": "<= 80 words", "changed": ["<paths relative to the workspace>"], "noticed": ["..."],
        "questions": ["<with needs_input>"], "disputes": [{"finding": "F1", "why": "<evidence>"}],
    },
    "review": {
        "batch": "B1", "verdict": "pass | changes",
        "findings": [{"id": "F1", "state": "wrong | missing | unclear | broken | gap | weak | cosmetic",
                      "blocking": True, "confidence": 90, "where": "<workspace-relative path>:<line>",
                      "task": "<T## if known>",
                      "issue": "<complete sentence>", "fix": "<what would make it right>"}],
        "noticed": [],
    },
}
