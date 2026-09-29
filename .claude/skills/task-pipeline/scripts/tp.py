#!/usr/bin/env python3
"""tp — the /task-pipeline state CLI. The manager session runs it; agents never do.

Every workflow command takes `-w <workflow dir>`. `tp next` always says what to do next.
Refusals print `ERROR: ...` and exit 2."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline import docscheck, run, survey  # noqa: E402
from pipeline import plan as planmod  # noqa: E402
from pipeline import scope as scopemod  # noqa: E402
from pipeline.common import TPError, Workflow, now_iso  # noqa: E402


def cmd_init(wf: Workflow, args: argparse.Namespace) -> str:
    if wf.exists():
        raise TPError(f"{wf.root} already holds a workflow — `tp -w {wf.root} status`.")
    wf.meta.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.request_file, wf.root / "request.md")
    state = {"version": 1, "title": args.title, "phase": "SCOPING", "created": now_iso(),
             "budget_minutes": args.budget, "tasks": {}, "recon": {}, "in_flight": {}}
    wf.save(state)
    wf.event("init", title=args.title)
    return (f"workflow created at {wf.root} (SCOPING).\n"
            f"Next: `tp -w {wf.root} survey <repo> --name <ws>` for each source repo, then draft scope.json.")


def cmd_survey(wf: Workflow, args: argparse.Namespace) -> str:
    wf.load()
    data = survey.survey(Path(args.path))
    out = wf.root / "survey" / f"{args.name}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(data, indent=1))
    wf.event("survey", name=args.name, files=data["files"])
    return survey.summary(data, out)


def cmd_check_docs(args: argparse.Namespace) -> str:
    repos = {}
    for spec in args.repo or []:
        name, _, path = spec.partition("=")
        repos[name] = Path(path)
    errors, warnings, stats = docscheck.check([Path(p) for p in args.paths], repos,
                                              Path(args.root) if args.root else None)
    if args.strict:
        errors += warnings
        warnings = []
    if errors:
        raise TPError(*errors[:60], f"{len(errors)} problems in {stats['files']} files.")
    head = [f"WARN: {w}" for w in warnings[:60]]
    return "\n".join(head + [f"docs ok: {stats['files']} files, {stats['links']} links, {stats['citations']} "
                             f"citations, {len(warnings)} doubtful citations."])


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tp", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-w", "--workflow", help="the workflow directory")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create a workflow (SCOPING)")
    s.add_argument("--title", required=True)
    s.add_argument("--request-file", required=True, help="the human's request, verbatim")
    s.add_argument("--budget", type=int, help="minutes for the whole job, planning included")

    s = sub.add_parser("status", help="compact status")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("next", help="what to do next")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("survey", help="deterministic structure map of a repository")
    s.add_argument("path")
    s.add_argument("--name", required=True)

    s = sub.add_parser("roster", help="participant suggestions")
    s.add_argument("what", choices=["suggest"])
    s.add_argument("--kinds", required=True, help="comma-separated deliverable kinds")

    s = sub.add_parser("scope", help="check or confirm scope.json")
    s.add_argument("what", choices=["check", "confirm"])
    s.add_argument("--answer", help="the human's confirmation, verbatim (confirm)")

    s = sub.add_parser("recon", help="add a planning recon item")
    s.add_argument("what", choices=["add"])
    s.add_argument("id")
    s.add_argument("--agent", required=True)
    s.add_argument("--questions-file", required=True, help="one question per line, at most 3")
    s.add_argument("--done-when", required=True)

    s = sub.add_parser("plan", help="check or submit plan.json")
    s.add_argument("what", choices=["check", "submit"])

    s = sub.add_parser("approve", help="record the human's approval")
    s.add_argument("--answer", required=True)
    s = sub.add_parser("revise", help="record the human's revision request")
    s.add_argument("--feedback", required=True)
    s.add_argument("--scope", action="store_true", help="the scope itself changes (back to SCOPING)")

    for name, helptext in (("dispatch", "write the brief for the next step and mark it in flight"),
                           ("sample", "the fact-check sample for a task")):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("id")
    s = sub.add_parser("record", help="record an agent's hand-back and run the gates")
    s.add_argument("id")
    s.add_argument("--agent-id", help="the agent's id, for fix rounds by the same agent")
    s = sub.add_parser("accept", help="accept a task after your fact check")
    s.add_argument("id")
    s.add_argument("--note", required=True)
    s = sub.add_parser("reject", help="reject a task after your fact check (a fix round)")
    s.add_argument("id")
    s.add_argument("--reason", required=True)
    s = sub.add_parser("exception", help="raise something only the human can decide")
    s.add_argument("--summary", required=True)
    s.add_argument("--task")
    s = sub.add_parser("resolve", help="record the human's decision")
    s.add_argument("--task")
    s.add_argument("--action", required=True, choices=["answer", "retry", "skip", "reopen", "accept"])
    s.add_argument("--answer", required=True)
    s = sub.add_parser("note", help="log something noticed outside the plan")
    s.add_argument("text")
    sub.add_parser("final", help="package checks and the report")
    sub.add_parser("report", help="timings")

    s = sub.add_parser("check-docs", help="check Markdown links and path:line citations")
    s.add_argument("paths", nargs="+")
    s.add_argument("--repo", action="append", help="name=path of a source repo that citations point into")
    s.add_argument("--root", help="index file every document must be reachable from")
    s.add_argument("--strict", action="store_true", help="doubtful citations are errors, not warnings")
    return p


def dispatch(args: argparse.Namespace) -> str:
    if args.cmd == "roster":
        return scopemod.cmd_suggest([k.strip() for k in args.kinds.split(",") if k.strip()])
    if args.cmd == "check-docs":
        return cmd_check_docs(args)
    if not args.workflow:
        raise TPError(f"`tp {args.cmd}` needs -w <workflow dir>.")
    wf = Workflow(Path(args.workflow))
    c = args.cmd
    if c == "init":
        return cmd_init(wf, args)
    if c == "status":
        return run.cmd_status(wf, args.json)
    if c == "next":
        return run.cmd_next(wf, args.json)
    if c == "survey":
        return cmd_survey(wf, args)
    if c == "scope":
        if args.what == "check":
            return scopemod.cmd_check(wf)
        if not args.answer:
            raise TPError("scope confirm needs --answer with the human's words.")
        return scopemod.cmd_confirm(wf, args.answer)
    if c == "recon":
        return run.cmd_recon_add(wf, args.id, args.agent, Path(args.questions_file), args.done_when)
    if c == "plan":
        return planmod.cmd_check(wf) if args.what == "check" else planmod.cmd_submit(wf)
    if c == "approve":
        return planmod.cmd_approve(wf, args.answer)
    if c == "revise":
        return planmod.cmd_revise(wf, args.feedback, args.scope)
    if c == "dispatch":
        return run.cmd_dispatch(wf, args.id)
    if c == "record":
        return run.cmd_record(wf, args.id, args.agent_id)
    if c == "sample":
        return run.cmd_sample(wf, args.id)
    if c == "accept":
        return run.cmd_accept(wf, args.id, args.note)
    if c == "reject":
        return run.cmd_reject(wf, args.id, args.reason)
    if c == "exception":
        return run.cmd_exception(wf, args.summary, args.task)
    if c == "resolve":
        return run.cmd_resolve(wf, args.task, args.action, args.answer)
    if c == "note":
        wf.load()
        wf.noticed("manager", args.text)
        return "noted in noticed.md (shown to the human at approval and in the report)."
    if c == "final":
        return run.cmd_final(wf)
    if c == "report":
        return run.cmd_report(wf)
    raise TPError(f"unknown command {c}")


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        print(dispatch(args))
        return 0
    except TPError as exc:
        for line in exc.lines:
            print(f"ERROR: {line}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
