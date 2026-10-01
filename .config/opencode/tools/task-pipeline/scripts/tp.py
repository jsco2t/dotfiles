#!/usr/bin/env python3
"""tp — the /task-pipeline state CLI. The manager session runs it; agents never do.

Every workflow command takes `-w <workflow dir>`. `tp next` always says what to do next.
Refusals print `ERROR: ...` and exit 2."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline import docscheck, issuesurvey, research, review, run, schemas, survey  # noqa: E402
from pipeline import plan as planmod  # noqa: E402
from pipeline import scope as scopemod  # noqa: E402
from pipeline.common import TPError, Workflow, now_iso  # noqa: E402


def slugify(title: str, limit: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if len(slug) > limit:
        slug = slug[:limit].rsplit("-", 1)[0] if "-" in slug[:limit] else slug[:limit]
    return slug or "workflow"


def cmd_init(location: Path, args: argparse.Namespace) -> str:
    """The location the human names is a parent: the workflow creates and owns
    `<location>/<YYYY-MM-DD>-<slug>` beneath it, and every later command uses that folder."""
    location = location.expanduser().resolve()
    if Workflow(location).exists():
        raise TPError(f"{location} is itself a workflow folder; give the location it should be created under "
                      f"(its parent, {location.parent}), or `tp -w {location} status` to continue it.")
    if not Path(args.request_file).is_file():
        raise TPError(f"{args.request_file} does not exist: save the human's request there first.")
    base = f"{date.today().isoformat()}-{slugify(args.title)}"
    root, n = location / base, 1
    while root.exists():
        n += 1
        root = location / f"{base}-{n}"
    wf = Workflow(root)
    wf.meta.mkdir(parents=True)
    shutil.copyfile(args.request_file, wf.root / "request.md")
    state = {"version": 1, "title": args.title, "phase": "SCOPING", "created": now_iso(),
             "budget_minutes": args.budget, "tasks": {}, "recon": {}, "in_flight": {}}
    wf.save(state)
    wf.event("init", title=args.title, location=str(location))
    return (f"workflow: {wf.root}\n"
            f"Created under {location} (SCOPING). Use `-w {wf.root}` for every later command.\n"
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

    s = sub.add_parser("init", help="create a workflow in its own <date>-<slug> folder under a location (SCOPING)")
    s.add_argument("location", nargs="?", help="where the human wants planning documents; the workflow gets "
                   "its own sub-folder here (-w is accepted as the location too)")
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

    s = sub.add_parser("survey-issue", help="deterministic sizing of a Jira or GitHub issue (jira:KEY, gh:o/r#N)")
    s.add_argument("ref")

    for name in ("research", "recon"):  # recon: the name older workflows use
        s = sub.add_parser(name, help="planning research inside the agreed budget")
        rs = s.add_subparsers(dest="what", required=True)
        a = rs.add_parser("add", help="add one small research item")
        a.add_argument("id")
        a.add_argument("--agent", required=True)
        a.add_argument("--purpose", choices=None, default=None if name == "research" else "map",
                       help="map | requirements | investigate")
        a.add_argument("--questions-file", required=True, help="one question per line, at most 3")
        a.add_argument("--done-when", required=True)
        a.add_argument("--minutes", type=int, help="time box, at most 15 (default 15)")
        a.add_argument("--from", dest="from_ref", help="the followup this item pursues, e.g. R1.F2")
        e = rs.add_parser("extend", help="grow the research budget with the human's agreement")
        e.add_argument("--minutes", type=int, required=True)
        e.add_argument("--answer", required=True)
        d = rs.add_parser("dismiss", help="decide a followup is not worth pursuing")
        d.add_argument("ref")
        d.add_argument("--reason", required=True)
        d = rs.add_parser("drop", help="drop a research item that has not run")
        d.add_argument("id")
        d.add_argument("--reason", required=True)

    s = sub.add_parser("show", help="print one part of a structured result (research, review session, task)")
    s.add_argument("id")
    s.add_argument("--part", help="research: answers|followups|unknowns|areas · review: blocking|findings")

    s = sub.add_parser("triage", help="decide a review session's blocking findings")
    s.add_argument("id", help="review session, e.g. B1/doc-reviewer")
    s.add_argument("--accept-all", action="store_true")
    s.add_argument("--dismiss", default="", help="comma-separated finding ids that are not real problems")
    s.add_argument("--reason", help="why the dismissed findings are not real problems")
    s.add_argument("--assign", action="append", default=[], help="F#=T## for a finding no task path matched")

    s = sub.add_parser("halt", aliases=["hault"], help="stop at the next clean point and record where")
    s.add_argument("--reason", default="halt requested by the human")
    s = sub.add_parser("resume", help="continue after a halt")
    s.add_argument("--answer", required=True)

    s = sub.add_parser("schema", help="print an example of a workflow file")
    s.add_argument("name", choices=["scope", "plan", "research", "result", "review"])

    s = sub.add_parser("plan", help="check or submit plan.json")
    s.add_argument("what", choices=["check", "submit"])

    s = sub.add_parser("amend", help="amend mechanical plan details while EXECUTING (paths, test_cmd, checks, estimate, brief, sources)")
    s.add_argument("--reason", required=True)
    s = sub.add_parser("approve", help="record the human's approval")
    s.add_argument("--answer", required=True)
    s = sub.add_parser("revise", help="record the human's revision request")
    s.add_argument("--feedback", required=True)
    s.add_argument("--scope", action="store_true", help="the scope itself changes (back to SCOPING)")

    s = sub.add_parser("dispatch", help="write the brief for each id's next step and mark it in flight")
    s.add_argument("ids", nargs="+", metavar="id")
    s = sub.add_parser("sample", help="the fact-check sample for a task")
    s.add_argument("id")
    s = sub.add_parser("record", help="record an agent's hand-back and run the gates")
    s.add_argument("id")
    s.add_argument("--agent-id", help="the agent's id, for fix rounds by the same agent")
    s.add_argument("--credit", type=float, default=0.0, metavar="MIN",
                   help="minutes the agent sat waiting on the human (a permission prompt or a "
                        "question) while in flight: deduct them from the budget tally instead of "
                        "billing the human's response time as agent work")
    s.add_argument("--trim-summary", action="store_true",
                   help="the summary is over the word limit: cut it to the limit instead of failing "
                        "(manager fix for a mechanical rejection; nothing else in the result changes)")
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
    s.add_argument("--review", help="a blocked review session, e.g. B1/doc-reviewer")
    s.add_argument("--force", action="store_true",
                   help="--review accept: ship although blocking findings are held")
    s.add_argument("--by", choices=["human", "manager"],
                   help="who decided; recorded in decisions.md and carried in later briefs")
    s.add_argument("--findings", default="", help="--review reopen: comma-separated finding ids to send back")
    s.add_argument("--assign", action="append", default=[],
                   help="--review reopen: F#=T## for a finding no task path matches")
    s.add_argument("--exception", action="store_true",
                   help="resolve a workflow-level exception block (action: answer)")
    s.add_argument("--noticed", type=int, metavar="N",
                   help="resolve noticed item N (1-based, as listed by `tp noticed`) as settled")
    s.add_argument("--action", required=True, choices=["answer", "retry", "skip", "reopen", "accept", "clear"])
    s.add_argument("--answer", required=True)
    sub.add_parser("noticed", help="list the noticed, not-in-plan items")
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


def cmd_survey_issue(wf: Workflow, ref: str) -> str:
    wf.load()
    source, key = issuesurvey.parse(ref)
    data = issuesurvey.jira(key) if source == "jira" else issuesurvey.github(key)
    out = wf.root / "survey" / ("issue-" + re.sub(r"[^\w-]+", "-", key).strip("-") + ".json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(data, indent=1))
    wf.event("survey_issue", ref=ref)
    return issuesurvey.summary(data, out)


def cmd_show(wf: Workflow, tid: str, part) -> str:
    state = wf.load()
    if "/" in tid:
        return review.show(state, tid, part)
    if tid.startswith("R"):
        return research.show(wf, state, tid, part)
    results = sorted(wf.run_dir(tid).glob("result-*.json"), key=lambda p: p.stat().st_mtime)
    if not results:
        raise TPError(f"{tid} has no result yet.")
    data = json.loads(results[-1].read_text())
    if part in ("noticed", "questions", "changed", "disputes"):
        return "\n".join(map(str, data.get(part, []))) or "none."
    return f"{tid} {data.get('step')} {data.get('status')}: {data.get('summary')}"


def dispatch(args: argparse.Namespace) -> str:
    if args.cmd == "roster":
        return scopemod.cmd_suggest([k.strip() for k in args.kinds.split(",") if k.strip()])
    if args.cmd == "check-docs":
        return cmd_check_docs(args)
    if args.cmd == "schema":
        return json.dumps(schemas.SCHEMAS[args.name], indent=1)
    if args.cmd == "init":
        location = args.location or args.workflow
        if not location:
            raise TPError("`tp init <location>` needs the location the human named for planning documents.")
        return cmd_init(Path(location), args)
    if not args.workflow:
        raise TPError(f"`tp {args.cmd}` needs -w <workflow dir>.")
    wf = Workflow(Path(args.workflow))
    c = args.cmd
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
    if c == "survey-issue":
        return cmd_survey_issue(wf, args.ref)
    if c in ("research", "recon"):
        if args.what == "add":
            return research.cmd_add(wf, args.id, args.agent, args.purpose, Path(args.questions_file), args.done_when,
                                    args.minutes, args.from_ref)
        if args.what == "extend":
            return research.cmd_extend(wf, args.minutes, args.answer)
        if args.what == "dismiss":
            return research.cmd_dismiss(wf, args.ref, args.reason)
        return research.cmd_drop(wf, args.id, args.reason)
    if c == "show":
        return cmd_show(wf, args.id, args.part)
    if c == "triage":
        return review.cmd_triage(wf, args.id, args.accept_all, [x for x in args.dismiss.split(",") if x],
                                 args.reason, args.assign)
    if c in ("halt", "hault"):
        return run.cmd_halt(wf, args.reason)
    if c == "resume":
        return run.cmd_resume(wf, args.answer)
    if c == "plan":
        return planmod.cmd_check(wf) if args.what == "check" else planmod.cmd_submit(wf)
    if c == "amend":
        return planmod.cmd_amend(wf, args.reason)
    if c == "approve":
        return planmod.cmd_approve(wf, args.answer)
    if c == "revise":
        return planmod.cmd_revise(wf, args.feedback, args.scope)
    if c == "dispatch":
        done = []
        for tid in args.ids:
            try:
                done.append(run.cmd_dispatch(wf, tid))
            except TPError as exc:  # the dispatches that succeeded stay in flight: their calls must still be sent
                exc.done = "\n\n".join(done)
                exc.lines = [f"{tid}: {ln}" for ln in exc.lines]
                raise
        return "\n\n".join(done)
    if c == "record":
        return run.after_record(wf, run.cmd_record(wf, args.id, args.agent_id,
                                                   trim_summary=args.trim_summary, credit=args.credit))
    if c == "sample":
        return run.cmd_sample(wf, args.id)
    if c == "accept":
        return run.cmd_accept(wf, args.id, args.note)
    if c == "reject":
        return run.cmd_reject(wf, args.id, args.reason)
    if c == "exception":
        return run.cmd_exception(wf, args.summary, args.task)
    if c == "resolve":
        if args.noticed is not None:
            return run.cmd_resolve(wf, None, args.action, args.answer, noticed=args.noticed, by=args.by)
        if args.exception:
            return run.cmd_resolve(wf, None, "answer", args.answer, exception=True, by=args.by)
        if args.review:
            with wf.locked():
                session = wf.load()
                session.setdefault("reviews", {}).setdefault(args.review, {})["_reopen_fids"] = \
                    [x for x in args.findings.split(",") if x]
                session["reviews"][args.review]["_reopen_assign"] = list(args.assign)
                return review.resolve(wf, session, args.review, args.action, args.answer,
                                      by=args.by, force=args.force)
        return run.cmd_resolve(wf, args.task, args.action, args.answer, by=args.by)
    if c == "noticed":
        items = wf.load() and wf.noticed_items()
        if not items:
            return "no open noticed items."
        return "\n".join(f"{i}. {t}" for i, t in enumerate(items, 1))
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
        if exc.done:
            print(exc.done + "\n")
        for line in exc.lines:
            print(f"ERROR: {line}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
