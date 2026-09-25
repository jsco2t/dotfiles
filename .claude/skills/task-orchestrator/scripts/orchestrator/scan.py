"""Integrity scan: flag changes that could make a goal cheaper instead of meeting it.

Runs over a task's diff (start snapshot -> current). Every hit must be
adjudicated by the task-verifier and the project-manager ("justified by <task
doc / plan reference>" or "violation"); the PM's acceptance must cite the scan
digest it adjudicated, so a newer scan invalidates an older acceptance.

A hit is not proof of wrongdoing — a task may legitimately delete an obsolete
test. It is a mandatory question: "why is this OK?"
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .common import sha256_json

TEST_PATH_RES = [re.compile(p) for p in (
    r"_test\.go$",
    r"(^|/)test_[^/]*\.py$",
    r"_test\.py$",
    r"(^|/)tests?/",
    r"\.(test|spec)\.[cm]?[jt]sx?$",
    r"(^|/)__tests__/",
    r"(^|/)testdata/",
    r"(^|/)spec/",
    r"_spec\.rb$",
    r"Tests?\.(java|cs|kt)$",
)]

GATE_CONFIG_RES = [re.compile(p) for p in (
    r"(^|/)\.golangci\.(ya?ml|toml|json)$",
    r"(^|/)\.github/workflows/",
    r"(^|/)(GNU)?[Mm]akefile$",
    r"(^|/)[Mm]agefile[^/]*\.go$",
    r"(^|/)magefiles/",
    r"(^|/)[Jj]ustfile$",
    r"(^|/)Taskfile\.ya?ml$",
    r"(^|/)\.pre-commit-config\.ya?ml$",
    r"(^|/)pyproject\.toml$",
    r"(^|/)setup\.cfg$",
    r"(^|/)tox\.ini$",
    r"(^|/)pytest\.ini$",
    r"(^|/)\.coveragerc$",
    r"(^|/)codecov\.ya?ml$",
    r"(^|/)clippy\.toml$",
    r"(^|/)\.?rustfmt\.toml$",
    r"(^|/)\.eslintrc",
    r"(^|/)eslint\.config\.",
    r"(^|/)(jest|vitest)\.config\.",
    r"(^|/)\.gitlab-ci\.ya?ml$",
    r"(^|/)Jenkinsfile$",
    r"(^|/)\.markdownlint",
)]

FIXTURE_RES = [re.compile(p) for p in (
    r"\.golden$",
    r"(^|/)testdata/",
    r"(^|/)fixtures?/",
    r"(^|/)__snapshots__/",
    r"\.snap$",
)]

ADDED_LINE_RULES = {
    "test_skip_added": [re.compile(p) for p in (
        r"\bt\.Skip(Now|f)?\(",
        r"#\[ignore\]",
        r"@pytest\.mark\.(skip|skipif|xfail)\b",
        r"\bpytest\.(skip|xfail)\(",
        r"@unittest\.(skip|skipIf|skipUnless|expectedFailure)\b",
        r"\b(it|describe|test|context)\.skip\(",
        r"\bx(it|describe|test)\(",
        r"@Disabled\b",
        r"@Ignore\b",
    )],
    "focused_test_added": [re.compile(p) for p in (
        r"\b(it|describe|test|context)\.only\(",
        r"\bf(it|describe)\(",
    )],
    "lint_suppression_added": [re.compile(p) for p in (
        r"//\s*nolint",
        r"#\s*noqa",
        r"#!?\[allow\(",
        r"eslint-disable",
        r"#\s*type:\s*ignore",
        r"@ts-(ignore|expect-error|nocheck)",
        r"#\s*pylint:\s*disable",
        r"//\s*lint:ignore",
        r"#\s*nosec\b",
        r"//\s*#?nosec\b",
        r"@SuppressWarnings",
        r"#\s*pragma:\s*no cover",
        r"istanbul ignore",
    )],
    "deferral_marker_added": [re.compile(p) for p in (
        r"\bTODO\b",
        r"\bFIXME\b",
        r"\bXXX\b",
        r"\bHACK\b",
        r"\bTBD\b",
        r"(?i)\bnot\s+(yet\s+)?implemented\b",
        r"\bunimplemented!\(",
        r"\btodo!\(",
        r"raise\s+NotImplementedError",
        r"NotImplementedException",
    )],
}

TEST_DECL_RES = [re.compile(p) for p in (
    r"^\s*func\s+(Test|Benchmark|Fuzz|Example)\w*\s*\(",
    r"^\s*(async\s+)?def\s+test_\w*\s*\(",
    r"^\s*#\[(tokio::)?test\]",
    r"^\s*(it|test|describe)\s*\(\s*['\"`]",
    r"\bt\.Run\(\s*\"",
    r"^\s*@Test\b",
)]

ASSERT_RES = [re.compile(p) for p in (
    r"\b(assert|require)\.[A-Z]\w*\(",
    r"\bt\.(Error|Errorf|Fatal|Fatalf|Fail|FailNow)\(",
    r"\bassert(_eq|_ne|_matches)?!\(",
    r"^\s*assert\s",
    r"\bself\.assert\w+\(",
    r"\bexpect\(",
    r"\bpytest\.raises\(",
    r"\bassertThat\(",
)]

CATEGORY_HELP = {
    "test_skip_added": "a test was skipped, ignored, or marked expected-to-fail",
    "focused_test_added": "a focused test (.only / fit) silently disables the rest of a suite",
    "lint_suppression_added": "a linter/type-checker/coverage suppression was added",
    "deferral_marker_added": "a TODO / not-implemented / stub marker was added (possible deferral)",
    "test_removed": "a test declaration was removed",
    "test_file_deleted": "a test file was deleted",
    "assertions_reduced": "a test file lost more assertions than it gained",
    "gate_config_changed": "build/lint/test/CI configuration changed (could weaken the gate)",
    "fixture_changed": "golden files / fixtures / snapshots changed (can hide regressions)",
    "outside_expected_paths": "a file outside the task's expected paths changed (possible unplanned work)",
    "tests_changed_after_checkpoint": "tests changed after the red/baseline checkpoint (possible weakening)",
}


def is_test_path(path: str) -> bool:
    return any(r.search(path) for r in TEST_PATH_RES)


def _matches(rules: Sequence[re.Pattern], text: str) -> bool:
    return any(r.search(text) for r in rules)


def parse_unified(diff_text: str) -> List[Dict[str, Any]]:
    """Split `git diff -U0` output into per-file records."""
    files: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            match = re.match(r"diff --git a/(.+) b/(.+)$", line)
            current = {
                "path": match.group(2) if match else line[11:],
                "old_path": match.group(1) if match else "",
                "added": [],
                "removed": [],
                "new": False,
                "deleted": False,
            }
            files.append(current)
            continue
        if current is None:
            continue
        if line.startswith("new file mode"):
            current["new"] = True
        elif line.startswith("deleted file mode"):
            current["deleted"] = True
        elif line.startswith("+++ ") or line.startswith("--- "):
            continue
        elif line.startswith("+"):
            current["added"].append(line[1:])
        elif line.startswith("-"):
            current["removed"].append(line[1:])
    return files


def _prefix_ok(path: str, prefixes: Sequence[str]) -> bool:
    for pre in prefixes:
        pre = pre.strip("/")
        if not pre or pre == ".":
            return True
        if path == pre or path.startswith(pre + "/"):
            return True
    return False


def _strip(path: str, prefix: str) -> str:
    if prefix and path.startswith(prefix + "/"):
        return path[len(prefix) + 1:]
    return path


def scan(
    diff_text: str,
    expected_paths: Sequence[str] = (),
    prefix: str = "",
    tests_changed_after_checkpoint: Iterable[str] = (),
) -> Dict[str, Any]:
    hits: List[Dict[str, Any]] = []

    def hit(category: str, path: str, text: str = "") -> None:
        hits.append({"category": category, "file": path, "text": text.strip()[:200]})

    for record in parse_unified(diff_text):
        path = _strip(record["path"], prefix)
        test_file = is_test_path(path)
        if record["deleted"] and test_file:
            hit("test_file_deleted", path)
        for line in record["added"]:
            for category, rules in ADDED_LINE_RULES.items():
                if _matches(rules, line):
                    hit(category, path, line)
        for line in record["removed"]:
            if _matches(TEST_DECL_RES, line):
                hit("test_removed", path, line)
        if test_file:
            added = sum(1 for line in record["added"] if _matches(ASSERT_RES, line))
            removed = sum(1 for line in record["removed"] if _matches(ASSERT_RES, line))
            if removed > added:
                hit("assertions_reduced", path, f"assertion-like lines: -{removed} +{added}")
        if any(r.search(path) for r in GATE_CONFIG_RES):
            hit("gate_config_changed", path)
        if any(r.search(path) for r in FIXTURE_RES):
            hit("fixture_changed", path)
        if expected_paths and not _prefix_ok(path, expected_paths):
            hit("outside_expected_paths", path)
    for path in tests_changed_after_checkpoint:
        hit("tests_changed_after_checkpoint", path)

    hits.sort(key=lambda h: (h["category"], h["file"], h["text"]))
    for index, item in enumerate(hits, start=1):
        item["id"] = f"H{index}"
    by_category: Dict[str, int] = {}
    for item in hits:
        by_category[item["category"]] = by_category.get(item["category"], 0) + 1
    digest = sha256_json([[h["category"], h["file"], h["text"]] for h in hits])[:16]
    return {"hits": hits, "by_category": by_category, "digest": digest}


def render_markdown(result: Dict[str, Any], title: str) -> str:
    lines = [f"# Integrity scan — {title}", ""]
    lines.append(f"Digest: `{result['digest']}` · Hits: {len(result['hits'])}")
    lines.append("")
    if not result["hits"]:
        lines.append("No integrity hits. Nothing requires adjudication.")
        return "\n".join(lines) + "\n"
    lines.append(
        "Every hit below must be adjudicated by the task-verifier and the "
        "project-manager as **justified** (cite the task/plan text that "
        "requires it) or **violation**."
    )
    lines.append("")
    for category, count in sorted(result["by_category"].items()):
        lines.append(f"- `{category}` ×{count} — {CATEGORY_HELP.get(category, '')}")
    lines.append("")
    for item in result["hits"]:
        detail = f" — `{item['text']}`" if item["text"] else ""
        lines.append(f"- **{item['id']}** `{item['category']}` in `{item['file']}`{detail}")
    return "\n".join(lines) + "\n"
