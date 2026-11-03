"""Compact context, measured activity, bounded delegation and explicit effect receipts."""
import json
import os
from datetime import datetime
from pathlib import Path

import checks
from snapshot import digest

READ_ONLY = {"metrics", "packet"}
COMMANDS = READ_ONLY | {"activity", "usage", "agent", "operation", "recover", "repair"}
CATEGORIES = ("research", "implementation", "verification", "bookkeeping", "waiting")
MODELS = {"SOL": "gpt-6.1-sol", "TERRA": "gpt-6.1-terra"}


def seconds(start, end):
    return max(0.0, (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())


def pause(wf, reason, ended=None):
    active = wf.state.pop("active_activity", None)
    if active:
        active.update(ended=ended or wf.timestamp(), end_reason=reason)
        wf.state.setdefault("activities", []).append(active)
        wf.event("activity-end", **active)


def switch(wf, category, label, task=None, operation=None):
    pause(wf, "phase transition")
    wf.state["active_activity"] = dict(category=category, label=label, task=task,
                                        started=wf.timestamp(), automatic=True, operation=operation)


def record_call(wf, command, elapsed, success):
    # Receipts measure helper invocations, not all model/runtime tool calls.
    with (wf.meta / "telemetry.jsonl").open("a") as stream:
        stream.write(json.dumps(dict(at=wf.timestamp(), command=command,
                                    seconds=elapsed, success=success)) + "\n")


def metrics(wf):
    state = wf.state
    receipts = []
    path = wf.meta / "telemetry.jsonl"
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                receipts.append(json.loads(line))
            except ValueError:
                pass  # An interrupted append is unmeasured, never an invented complete call.
    activities = {category: 0.0 for category in CATEGORIES}
    for item in state.get("activities", []):
        activities[item["category"]] += seconds(item["started"], item["ended"])
    active = state.get("active_activity")
    if active:
        activities[active["category"]] += seconds(active["started"], wf.timestamp())
    events = state["history"]
    checks_run = [e for e in events if e["action"] == "check"]
    wait_started, operator_wait = None, 0.0
    for event in events:
        if event["action"] == "question" and wait_started is None:
            wait_started = event["at"]
        if event["action"] in ("answer", "amend") and wait_started:
            operator_wait += seconds(wait_started, event["at"])
            wait_started = None
    if wait_started:
        operator_wait += seconds(wait_started, wf.timestamp())
    agents = list(state.get("agents", {}).values())
    usage = list(state.get("usage", {}).values())
    totals = {key: sum(item["measurements"].get(key, 0) for item in usage)
              for key in ("input_tokens", "cached_input_tokens", "output_tokens", "tool_calls", "repeated_reads")
              if any(key in item["measurements"] for item in usage)}
    wall = seconds(state["created"], state.get("completed", wf.timestamp()))
    return dict(schema=1, wall_seconds=wall,
                helper_calls=dict(count=len(receipts), elapsed_seconds=sum(r["seconds"] for r in receipts)),
                checks=dict(executed=len(checks_run), reused=sum(e["action"] == "check-reuse" for e in events),
                            seconds=sum(seconds(e["started"], e["ended"]) for e in checks_run)),
                activities=activities, covered_phase_seconds=sum(activities.values()),
                unclassified_wall_seconds=max(0.0, wall - sum(activities.values())),
                activity_measurement="automatic helper-boundary phase wall spans, optionally refined by explicit main spans; not CPU-active time",
                operator_wait_seconds=operator_wait,
                tasks=dict(done=sum(t["status"] == "done" for t in state["tasks"].values()), total=len(state["tasks"])),
                agents=dict(assigned=len(agents), accepted=sum(a.get("accepted") is True for a in agents),
                            seconds=sum(seconds(a["started"], a.get("ended", wf.timestamp())) for a in agents),
                            models={model: sum(a["model"] == model for a in agents) for model in MODELS}),
                usage=totals or None, usage_sources=[u["source"] for u in usage],
                reviewed_requirements=(len(state["review"].get("requirements", [])) if state.get("review")
                                       and state["review"]["verdict"] == "pass" else 0),
                limits="Saved progress is not a fresh artifact audit. Helper/check/agent durations overlap activity spans; do not add them. Tokens/tool totals are imported, missing means unmeasured.")


def packet(wf, task_id=None, agent_id=None, limit=16000):
    state = wf.state
    scope = state.get("scope")
    if scope is None:
        raise ValueError("confirm scope before building a packet")
    task = next((t for t in (state.get("plan") or {}).get("tasks", []) if t["id"] == task_id), None)
    if task_id and task is None:
        raise ValueError("unknown task")
    agent = state.get("agents", {}).get(agent_id) if agent_id else None
    if agent_id and agent is None:
        raise ValueError("unknown agent")
    wanted = set(task.get("requirements", [])) if task else set((agent or {}).get("requirements", []))
    requirements = [r for r in scope.get("requirements", []) if not wanted or r["id"] in wanted]
    entry = state["tasks"].get(task_id, {})
    result = dict(workflow=str(wf.root), phase=state["phase"], request_file=str(wf.root / "request.md"),
                  scope_file=str(wf.root / "scope.json"), plan_file=str(wf.root / "plan.json"),
                  research_file=str(wf.root / "research.md"), requirements=requirements,
                  constraints=scope["constraints"], non_goals=scope["non_goals"], workspaces=scope["workspaces"],
                  task=task, status=entry.get("status"), pending_question=state.get("question"),
                  repairs=[dict(id=r["id"], status=r["status"], reason=r["reason"],
                                test_log=r.get("test_checkpoint", {}).get("log")) for r in entry.get("repairs", [])],
                  checks={name: state["checks"].get(name) for name in (task or {}).get("checks", [])},
                  operations=[{k: v for k, v in op.items() if k not in ("before", "contract")}
                              for op in state.get("operations", {}).values() if op["status"] in ("running", "unknown")],
                  agent=agent,
                  decisions=[{k: e[k] for k in ("at", "action", "answer", "reason", "by", "evidence") if k in e}
                             for e in state["history"] if e["action"] in ("scope-confirm", "approve", "amend", "answer")],
                  instruction="Read linked authority when needed; no child agents or external mutations in delegated roles. Preserve existing work and prior regressions.")
    encoded = json.dumps(result, indent=2)
    if len(encoded.encode()) > limit:
        raise ValueError("essential packet exceeds byte limit; narrow assignment instead of silently dropping constraints")
    return encoded


def execute(wf, args, api):
    state = wf.state
    if args.command == "metrics":
        return json.dumps(metrics(wf), indent=2)
    if args.command == "packet":
        return packet(wf, args.task, args.agent, args.max_bytes)
    if args.command == "recover":
        recovered = checks.recover(wf)
        wf.event("recover", operations=recovered)
        return json.dumps(dict(recovered=recovered, unresolved=[op["id"] for op in state.get("operations", {}).values()
                                                               if op["status"] in ("running", "unknown")]))
    if args.command == "repair":
        import repairs
        return repairs.execute(wf, args, api)
    api.need(state["phase"] not in ("COMPLETE", "HALTED") or args.command in ("operation", "agent", "activity"),
             "workflow halted or complete")
    if args.command == "activity":
        if args.action == "begin":
            api.need(state["phase"] not in ("COMPLETE", "HALTED"), "cannot start activity in halted/completed workflow")
            api.need(not state.get("active_activity") or state["active_activity"].get("automatic"),
                     "finish the explicit active span before beginning another")
            pause(wf, "explicit activity refines automatic phase")
            api.need(not args.task or args.task in state["tasks"], "unknown activity task")
            state["active_activity"] = dict(category=args.category, label=args.label, task=args.task, started=api.now())
        else:
            api.need(state.get("active_activity"), "no activity is running")
            pause(wf, args.evidence)
        return "Activity recorded."
    if args.command == "usage":
        item = api.read(args.file)
        fields = {"input_tokens", "cached_input_tokens", "output_tokens", "tool_calls", "repeated_reads"}
        api.need(isinstance(item, dict) and set(item) == {"id", "source", "measurements"}
                 and api.text(item.get("id")) and api.text(item.get("source"))
                 and isinstance(item.get("measurements"), dict) and item["measurements"]
                 and set(item["measurements"]) <= fields
                 and all(type(v) is int and v >= 0 for v in item["measurements"].values()),
                 "usage needs id, measured source, and nonnegative integer measurements")
        if "cached_input_tokens" in item["measurements"] and "input_tokens" in item["measurements"]:
            api.need(item["measurements"]["cached_input_tokens"] <= item["measurements"]["input_tokens"], "cached input exceeds total input")
        # Replace a cumulative reading from one source; repeated imports do not double count.
        state.setdefault("usage", {})[item["id"]] = item
        wf.event("usage", source=item["source"], id=item["id"])
        return "Measured usage recorded; overlapping sources must not be imported twice."
    if args.command == "agent":
        agents = state.setdefault("agents", {})
        if args.action == "reserve":
            api.need(state["phase"] in ("PLANNING", "EXECUTING") and not state.get("question"), "agent work needs confirmed scope and no pending question")
            brief = api.read(args.file)
            scope = state["scope"]
            api.need(api.read(wf.root / "scope.json") == scope, "scope drift; inspect before delegation")
            api.need(args.id not in agents, "agent assignment id already exists")
            api.need(isinstance(brief, dict) and brief.get("role") in ("research", "review")
                     and brief.get("model") in MODELS and brief.get("reasoning") in ("medium", "high")
                     and all(api.text(brief.get(k)) for k in ("question", "done_when", "model_reason"))
                     and api.strings(brief.get("paths")), "brief needs bounded role/question/paths/stop condition and SOL/TERRA choice with reason")
            for raw_path in brief["paths"]:
                path = Path(raw_path).resolve()
                api.need(Path(raw_path).is_absolute() and any(
                    path == Path(w["path"]) or Path(w["path"]) in path.parents for w in scope["workspaces"]),
                    "agent starting paths must belong to approved read/write workspaces")
            requested = brief.get("requirements", [])
            api.need(api.strings(requested) and set(requested) <= {r["id"] for r in scope.get("requirements", [])},
                     "agent work must serve named approved requirements")
            allowance = min(scope.get("max_agents", 0), args.capacity)
            api.need(sum(a["status"] in ("reserved", "running", "unknown") for a in agents.values()) < allowance,
                     "agent allowance/runtime capacity exhausted; do not spawn or nest")
            api.need(not brief.get("task") or brief["task"] in state["tasks"], "unknown agent task")
            snapshot = wf.snapshot(scope, state.get("plan") or {"tasks": []})
            agents[args.id] = dict(brief, id=args.id, status="reserved", started=api.now(), source=digest(snapshot),
                                  requested_model=MODELS[brief["model"]], actual_model=None, actual_reasoning=None, no_children=True)
            wf.event("agent-reserve", id=args.id, model=brief["model"], reason=brief["model_reason"], requirements=requested)
            return packet(wf, brief.get("task"), args.id)
        agent = agents.get(args.id)
        api.need(agent is not None, "unknown agent assignment")
        if args.action == "attach":
            api.need(agent["status"] == "reserved" and api.text(args.agent_id), "attach actual identity to a reserved assignment")
            agent.update(status="running", agent_id=args.agent_id, actual_model=args.actual_model, actual_reasoning=args.actual_reasoning)
        elif args.action == "finish":
            api.need(agent["status"] == "running", "only a running agent can finish")
            result = api.read(args.file)
            api.need(isinstance(result, dict) and set(result) <= {"accepted", "summary", "validation", "evidence", "coverage", "unresolved"}
                     and type(result.get("accepted")) is bool
                     and api.text(result.get("summary")) and api.text(result.get("validation"))
                     and api.strings(result.get("evidence")), "agent result needs accepted, summary, evidence and parent validation")
            scope = state["scope"]
            current = digest(wf.snapshot(scope, state.get("plan") or {"tasks": []}))
            api.need(not result["accepted"] or current == agent["source"], "review source changed; validate/review affected changes before accepting")
            agent.update(result, status="done", ended=api.now())
        else:
            api.need(agent["status"] in ("reserved", "running", "unknown"), "agent is already settled")
            agent.update(status="cancelled", ended=api.now(), cancellation_evidence=args.evidence)
        wf.event("agent-" + args.action, id=args.id)
        return "Agent record updated; the helper does not launch/interrupt agents."
    if args.command == "operation":
        operations = state.setdefault("operations", {})
        if args.action == "begin":
            wf.runnable()
            api.need(args.id not in operations and args.task in state["tasks"] and state["tasks"][args.task]["status"] == "running",
                     "new effect receipt needs a running owning task and unique id")
            api.need(not any(op["status"] in ("running", "unknown") for op in operations.values()), "resolve prior operation before another effect")
            operations[args.id] = dict(id=args.id, kind=args.kind, status="running", task=args.task,
                                       intent=args.intent, started=api.now(), authority=args.authority)
        else:
            op = operations.get(args.id)
            api.need(op is not None and op["status"] in ("running", "unknown"), "no unresolved operation receipt")
            result = api.read(args.file)
            api.need(isinstance(result, dict) and set(result) == {"status", "evidence"}
                     and result.get("status") in ("completed", "failed", "cancelled")
                     and api.text(result.get("evidence")), "effect result needs actual status and read-back/reconciliation evidence")
            if op["kind"] == "check":
                api.need(op["status"] == "unknown" and result["status"] in ("failed", "cancelled"),
                         "checks can pass only from worker receipts; unknown checks require inspected failure/cancellation")
                process = checks.read_receipt((wf.root / op["receipt"]).with_name("process.json")) or {}
                for pid in (op.get("worker_pid"), process.get("pid")):
                    if pid:
                        try:
                            os.kill(pid, 0)
                        except ProcessLookupError:
                            continue
                        api.need(False, "recorded process may still be alive; inspect/stop it before resolving the unknown check")
            op.update(result, ended=api.now())
        wf.event("operation-" + args.action, operation=args.id)
        return "Effect receipt recorded; perform only already-authorized actions and inspect before retrying unknown outcomes."
    raise ValueError("unknown tracking command")


def add_parsers(commands):
    commands.add_parser("metrics")
    commands.add_parser("recover")
    item = commands.add_parser("packet")
    item.add_argument("task", nargs="?")
    item.add_argument("--agent")
    item.add_argument("--max-bytes", type=int, default=16000)
    item = commands.add_parser("usage")
    item.add_argument("--file", required=True)
    item = commands.add_parser("activity")
    actions = item.add_subparsers(dest="action", required=True)
    begin = actions.add_parser("begin")
    begin.add_argument("category", choices=CATEGORIES)
    begin.add_argument("--label", required=True)
    begin.add_argument("--task")
    end = actions.add_parser("end")
    end.add_argument("--evidence", required=True)
    item = commands.add_parser("agent")
    actions = item.add_subparsers(dest="action", required=True)
    for action in ("reserve", "attach", "finish", "cancel"):
        child = actions.add_parser(action)
        child.add_argument("--id", required=True)
        if action in ("reserve", "finish"):
            child.add_argument("--file", required=True)
        if action == "reserve":
            child.add_argument("--capacity", type=int, required=True, help="total usable child capacity: assigned children plus free slots, excluding parent")
        if action == "attach":
            child.add_argument("--agent-id", required=True)
            child.add_argument("--actual-model")
            child.add_argument("--actual-reasoning", choices=("medium", "high"))
        if action == "cancel":
            child.add_argument("--evidence", required=True)
    item = commands.add_parser("operation")
    actions = item.add_subparsers(dest="action", required=True)
    begin = actions.add_parser("begin")
    begin.add_argument("--id", required=True)
    begin.add_argument("--kind", choices=("commit", "delivery"), required=True)
    begin.add_argument("--task", required=True)
    begin.add_argument("--intent", required=True)
    begin.add_argument("--authority", required=True)
    finish = actions.add_parser("finish")
    finish.add_argument("--id", required=True)
    finish.add_argument("--file", required=True)
    item = commands.add_parser("repair")
    actions = item.add_subparsers(dest="action", required=True)
    for action in ("start", "test", "done"):
        child = actions.add_parser(action)
        child.add_argument("task")
        if action in ("start", "done"):
            child.add_argument("--file", required=True)
        if action in ("test", "done"):
            child.add_argument("--id", required=True)
        if action == "test":
            child.add_argument("--stage", choices=("red", "pin"), required=True)
            child.add_argument("--note", required=True)
