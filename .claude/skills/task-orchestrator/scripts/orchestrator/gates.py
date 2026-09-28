"""Gate checklists: what must be true before each transition, and what to do next.

There is deliberately no second state machine. Each gate is a checklist
computed from the ledger and a fresh snapshot; the first unmet item *is* the
next action. `orch status` prints it, the Stop hook quotes it, and the
transition commands (`task accept`, `loop close`, `final accept`, `submit`)
refuse to run while any item is unmet.

The snapshot rule: every verdict that evaluates work (verification, reviews,
PM scope/acceptance, green evidence, gate runs, the integrity scan) must cite
the *current* snapshot. Any change to the workspace after a verdict makes that
verdict stale, so work cannot be "fixed" after review without re-review.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import activity
from . import ledger
from . import plan as planmod
from . import research
from . import snapshot as snapmod
from .common import OrchError, Workflow
from .roster import CODE_LIKE_TYPES, RESOLVE_ACTIONS, required_final_reviewers

LEGACY_PLANNING = ("UPGRADE NEEDED — this workflow was created before workflow kinds and focused research "
                   "items, so its briefs would carry no deliverable-specific non-goals and its research would "
                   "skip the PM's approval.")


@dataclass
class Req:
    key: str
    label: str
    ok: bool
    detail: str = ""
    action: str = ""
    failed: bool = False  # a current verdict exists and it is a fail

    def line(self) -> str:
        mark = "x" if self.ok else ("!" if self.failed else " ")
        text = f"[{mark}] {self.label}"
        if self.detail:
            text += f" — {self.detail}"
        return text


def first_unmet(reqs: Sequence[Req]) -> Optional[Req]:
    for req in reqs:
        if not req.ok:
            return req
    return None


class Context:
    """Loaded state + ledger + plan package, with cached snapshots."""

    def __init__(
        self,
        wf: Workflow,
        fast: bool = False,
        state: Optional[Dict[str, Any]] = None,
        entries: Optional[List[Dict[str, Any]]] = None,
    ):
        self.wf = wf
        self.state = state if state is not None else wf.load_state()
        self.entries = entries if entries is not None else ledger.read(wf)
        self.fast = fast
        self._pkg: Optional[planmod.Package] = None
        self._snaps: Dict[Tuple[str, Tuple[str, ...]], snapmod.Snapshot] = {}

    # ------------------------------------------------------------ plan package
    @property
    def pkg(self) -> planmod.Package:
        if self._pkg is None:
            self._pkg = planmod.load_package(self.wf)
        return self._pkg

    def spec(self, task_id: str) -> planmod.TaskSpec:
        spec = self.pkg.tasks.get(task_id)
        if spec is None:
            raise OrchError(f"unknown task {task_id}")
        return spec

    def ws_path(self, name: str):
        path = planmod.workspace_path(self.pkg.gate, name)
        if path is None:
            raise OrchError(f"workspace `{name}` is not declared in gate.json")
        return path

    def scope(self, spec: planmod.TaskSpec) -> List[str]:
        return spec.expected_paths if spec.parallel_safe else []

    # ------------------------------------------------------------ snapshots
    def take(self, workspace: str, scope: Sequence[str] = ()) -> snapmod.Snapshot:
        key = (workspace, tuple(scope))
        if key not in self._snaps:
            self._snaps[key] = snapmod.take(
                self.wf,
                workspace,
                self.ws_path(workspace),
                scope=scope,
                excludes=planmod.snapshot_excludes(self.pkg.gate, workspace),
            )
        return self._snaps[key]

    def recorded_snapshot(self, **match: Any) -> Optional[snapmod.Snapshot]:
        found = ledger.latest(ledger.select(self.entries, "snapshot", **match))
        return snapmod.Snapshot.from_dict(found["snapshot"]) if found else None

    def task_snapshot(self, spec: planmod.TaskSpec) -> Optional[snapmod.Snapshot]:
        if self.fast:
            return self.recorded_snapshot(task=spec.id)
        return self.take(spec.workspace, self.scope(spec))

    def composite(self, workspaces: Sequence[str]) -> Tuple[str, List[snapmod.Snapshot]]:
        snaps: List[snapmod.Snapshot] = []
        for name in sorted(set(workspaces)):
            if self.fast:
                snap = self.recorded_snapshot(workspace=name, scope_key="full")
                if snap is None:
                    continue
            else:
                snap = self.take(name)
            snaps.append(snap)
        return snapmod.composite_id(snaps), snaps

    # ------------------------------------------------------------ ledger views
    def results(self, stage: str, **match: Any) -> List[Dict[str, Any]]:
        return ledger.results(self.entries, stage=stage, **match)

    def latest_result(self, stage: str, **match: Any) -> Optional[Dict[str, Any]]:
        return ledger.latest(self.results(stage, **match))

    def latest_kind(self, kind: str, **match: Any) -> Optional[Dict[str, Any]]:
        return ledger.latest(ledger.select(self.entries, kind, **match))


def _res(entry: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return (entry or {}).get("result") or {}


def _passed(entry: Optional[Dict[str, Any]]) -> bool:
    res = _res(entry)
    return bool(entry) and res.get("status") == "complete" and res.get("verdict") == "pass"


def _snap_id(entry: Optional[Dict[str, Any]]) -> Optional[str]:
    if not entry:
        return None
    if entry.get("kind") == "agent_result":
        return _res(entry).get("snapshot")
    snap = entry.get("snapshot")
    return snap.get("id") if isinstance(snap, dict) else snap


def _verdict_req(
    key: str,
    label: str,
    entry: Optional[Dict[str, Any]],
    now: Optional[str],
    dispatch: str,
    on_fail: str,
    extra_ok: bool = True,
    extra_detail: str = "",
) -> Req:
    """A verdict that must be a pass at the current snapshot."""
    if entry is None:
        return Req(key, label, False, "not yet run", dispatch)
    res = _res(entry)
    at = _snap_id(entry)
    if now is not None and at != now:
        return Req(key, label, False, f"stale (evaluated {at}, current {now})", dispatch)
    if res.get("status") == "interim":
        aid = (entry or {}).get("agent_id")
        return Req(key, label, False, f"stopped with an interim report ({res.get('report')})",
                   f"`orch agent continue {aid}` once `orch status` shows it is due (a time stop needs the PM's "
                   f"pm-interim review first), then SendMessage the printed text to agent {aid}")
    if res.get("status") != "complete":
        return Req(
            key,
            label,
            False,
            f"agent returned status {res.get('status')}",
            "answer its questions (see its report) and resume the same agent via SendMessage",
        )
    if res.get("verdict") != "pass" or not extra_ok:
        detail = extra_detail or f"verdict {res.get('verdict')} (report: {res.get('report')})"
        return Req(key, label, False, detail, on_fail, failed=True)
    return Req(key, label, True, f"report: {res.get('report')}")


# ================================================================== interim reports


def open_interims(ctx: Context) -> List[Dict[str, Any]]:
    """Agents whose latest valid result is an interim report not yet acted on by `orch agent continue`."""
    latest: Dict[str, Dict[str, Any]] = {}
    continued: Dict[str, int] = {}
    for entry in ctx.entries:
        aid = entry.get("agent_id")
        if not aid:
            continue
        if entry.get("kind") == "agent_result" and entry.get("valid"):
            latest[aid] = entry
        elif entry.get("kind") == "agent_continue":
            continued[aid] = max(continued.get(aid, 0), int(entry.get("seq") or 0))
    return sorted(
        (e for aid, e in latest.items()
         if _res(e).get("status") == "interim" and continued.get(aid, 0) < int(e.get("seq") or 0)),
        key=lambda e: e.get("seq", 0),
    )


def pm_interim_review(ctx: Context, interim: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The PM's latest pm-interim result for this interim report (after it was recorded)."""
    aid = interim.get("agent_id")
    return ledger.latest([
        e for e in ctx.results("pm-interim")
        if _res(e).get("interim_agent") == aid and e.get("seq", 0) > interim.get("seq", 0)
    ])


def interim_req(ctx: Context, interim: Dict[str, Any]) -> Req:
    aid = interim.get("agent_id")
    agent = interim.get("agent_type")
    reason = interim.get("interim_reason") or "time"
    report = _res(interim).get("report")
    label = f"interim report from {agent} {aid} acted on"
    cont = f"`orch agent continue {aid}`, then SendMessage the printed text to agent {aid}"
    if reason == "pause":
        if activity.pause_requested(ctx.wf, ctx.state):
            return Req("interim", label, False, f"paused by the human ({report})",
                       "wait for the human's `/task-orchestrator resume`, then " + cont)
        return Req("interim", label, False, f"paused by the human ({report})", cont)
    review = pm_interim_review(ctx, interim)
    if review is None:
        return Req("interim", label, False, f"{reason} stop ({report}); the PM has not reviewed it",
                   f"`orch brief pm-interim --of {aid} --agent project-manager` then dispatch project-manager")
    if _res(review).get("status") != "complete":
        return Req("interim", label, False, f"the PM's review returned status {_res(review).get('status')}",
                   "answer the PM's questions (see its report) and resume the same PM agent via SendMessage")
    res = _res(review)
    return Req("interim", label, False,
               f"PM decided `{res.get('decision')}` with {res.get('grant_minutes')} more minute(s)",
               cont)


# ================================================================== tasks


def task_checklist(ctx: Context, task_id: str) -> List[Req]:
    state = ctx.state
    info = (state.get("tasks") or {}).get(task_id)
    if info is None:
        raise OrchError(f"task {task_id} is not in workflow state (was the plan approved?)")
    spec = ctx.spec(task_id)
    status = info.get("status")
    if status == "ACCEPTED":
        return [Req("accepted", "task accepted", True, f"at {info.get('accepted_snapshot')}")]
    if status != "IN_PROGRESS":
        return [Req("start", "task started", False, f"status {status}", f"orch task start {task_id}")]

    attempt = int(info.get("attempt") or 0)
    start_seq = int(info.get("start_seq") or 0)
    snap = ctx.task_snapshot(spec)
    now = snap.id if snap else None
    brief = lambda stage, agent: f"`orch brief {task_id} {stage} --agent {agent}` then dispatch {agent}"  # noqa: E731
    fix = (
        f"start a fix round: `orch task round {task_id}`, then resume the author(s) "
        f"with `orch brief {task_id} fix --agent <author>` via SendMessage"
    )
    reqs: List[Req] = []
    match = {"task": task_id, "attempt": attempt}

    # 1. Task start verification (readiness)
    ready = ctx.latest_result("readiness", **match)
    reqs.append(
        _verdict_req(
            "readiness",
            "readiness verified (task-verifier)",
            ready,
            None,
            brief("readiness", "task-verifier"),
            "readiness failed — plan defect: `orch deviation`; environment or missing "
            "input: `orch needs-human --kind readiness`",
        )
    )
    # 2. PM check before work starts
    reqs.append(
        _verdict_req(
            "pm-start",
            "PM start check (project-manager)",
            ctx.latest_result("pm-start", **match),
            None,
            brief("pm-start", "project-manager"),
            "PM start check failed — read its report; resolve the process gap it names "
            "(re-run readiness, `orch deviation`, or `orch needs-human`)",
        )
    )

    # 3. Work by each author in order, with a checkpoint before implementation
    #    and a PM scope check between authors.
    tf = spec.test_forward
    checkpoint = None
    if spec.type == "code" and tf == "red-green":
        checkpoint = "red"
    elif spec.type == "code" and tf == "characterization":
        checkpoint = "baseline"
    previous: Optional[Dict[str, Any]] = None
    for author in spec.authors:
        work = ctx.latest_result("work", agent_type=author, status="complete", **match)
        if previous is not None:
            scope = [
                e for e in ctx.results("pm-scope", **match)
                if e["seq"] > previous["seq"] and (work is None or e["seq"] < work["seq"])
            ]
            latest_scope = ledger.latest(scope)
            reqs.append(
                _verdict_req(
                    f"pm-scope:{previous['agent_type']}",
                    f"PM scope check after {previous['agent_type']}",
                    latest_scope,
                    None,
                    brief("pm-scope", "project-manager"),
                    f"resume {previous['agent_type']} with the PM findings "
                    f"(`orch brief {task_id} work --agent {previous['agent_type']}`), then re-run pm-scope",
                )
            )
        if checkpoint and author == "code-author":
            evidence = ledger.latest(
                [
                    e for e in ledger.select(ctx.entries, "evidence", phase=checkpoint, **match)
                    if e["seq"] > start_seq and (work is None or e["seq"] < work["seq"])
                ]
            )
            expect = "fail (tests written first)" if checkpoint == "red" else "pass (behavior characterized)"
            if evidence is None:
                reqs.append(Req("checkpoint", f"{checkpoint} evidence before implementation", False,
                                f"tests must {expect}", f"`orch evidence {task_id} {checkpoint}` (normally run by test-author)"))
            elif not evidence.get("passed"):
                reqs.append(Req("checkpoint", f"{checkpoint} evidence before implementation", False,
                                f"recorded run did not {expect}: see {evidence.get('summary')}",
                                f"resume test-author: the {checkpoint} checkpoint must {expect}", failed=True))
            else:
                reqs.append(Req("checkpoint", f"{checkpoint} evidence before implementation", True,
                                f"seq {evidence['seq']}"))
        work_req = Req(
            f"work:{author}",
            f"work by {author}",
            work is not None,
            f"report: {_res(work).get('report')}" if work else "not yet run",
            "" if work else brief("work", author),
        )
        if work is None:
            for interim in open_interims(ctx):
                res = _res(interim)
                if (interim.get("agent_type") == author and res.get("task") == task_id
                        and res.get("attempt") == attempt and res.get("stage") in ("work", "fix")):
                    stop = interim_req(ctx, interim)
                    work_req = Req(work_req.key, work_req.label, False, stop.detail, stop.action)
        reqs.append(work_req)
        previous = work or previous
        if work is None:
            break

    if spec.external_writes:
        confirm = ctx.latest_kind("resolution", action="confirm", **match)
        executed = [
            e for e in ctx.results("work", status="complete", **match)
            if _res(e).get("external_action") == "executed" and confirm and e["seq"] > confirm["seq"]
        ]
        reqs.append(Req("confirm", "human confirmed the external write", confirm is not None,
                        "" if confirm else "the dry-run must be shown to the human",
                        f"`orch needs-human --kind external_write --task {task_id} --summary ... --report <dry-run report>`"))
        reqs.append(Req("executed", "external write executed after confirmation", bool(executed), "",
                        f"resume the liaison: `orch brief {task_id} work --agent <liaison>` (execute the confirmed request)"))

    # 4. Green evidence at the current snapshot (objective test run by the CLI)
    if tf in ("red-green", "characterization"):
        green = ctx.latest_kind("evidence", phase="green", **match)
        if green is None:
            reqs.append(Req("green", "green evidence at current snapshot", False, "not yet run",
                            f"`orch evidence {task_id} green` (normally run by task-verifier)"))
        elif _snap_id(green) != now:
            reqs.append(Req("green", "green evidence at current snapshot", False,
                            f"stale (ran at {_snap_id(green)})", f"`orch evidence {task_id} green`"))
        elif not green.get("passed"):
            reqs.append(Req("green", "green evidence at current snapshot", False,
                            f"tests failed: {green.get('summary')}", fix, failed=True))
        else:
            reqs.append(Req("green", "green evidence at current snapshot", True))

    # 5. Standard quality gate at the current snapshot
    if planmod.gate_commands(ctx.pkg.gate, spec.workspace, "standard"):
        gate = ctx.latest_kind("gate", scope="task", level="standard", **match)
        if gate is None:
            reqs.append(Req("gate", "standard gate at current snapshot", False, "not yet run",
                            f"`orch gate run standard --task {task_id}` (normally run by task-verifier)"))
        elif _snap_id(gate) != now:
            reqs.append(Req("gate", "standard gate at current snapshot", False,
                            f"stale (ran at {_snap_id(gate)})", f"`orch gate run standard --task {task_id}`"))
        elif not gate.get("passed"):
            reqs.append(Req("gate", "standard gate at current snapshot", False,
                            f"failed: {gate.get('summary')}", fix, failed=True))
        else:
            reqs.append(Req("gate", "standard gate at current snapshot", True))

    # 6. PM scope check after the last author pass (current snapshot)
    reqs.append(
        _verdict_req(
            "pm-scope",
            "PM scope check at current snapshot",
            ctx.latest_result("pm-scope", **match),
            now,
            brief("pm-scope", "project-manager"),
            fix + " (address the PM's scope findings; revert unplanned work)",
        )
    )

    # 7. Independent completion verification, every AC met with evidence
    verification = ctx.latest_result("verification", **match)
    crit_ok, crit_detail = True, ""
    if verification is not None:
        got = {c.get("id"): c for c in _res(verification).get("criteria") or [] if isinstance(c, dict)}
        wanted = [c.id for c in spec.criteria]
        missing = [cid for cid in wanted if cid not in got]
        unmet = [
            cid for cid in wanted
            if cid in got and (not got[cid].get("met") or not str(got[cid].get("evidence") or "").strip())
        ]
        if missing or unmet:
            crit_ok = False
            parts = []
            if missing:
                parts.append(f"not assessed: {', '.join(missing)}")
            if unmet:
                parts.append(f"unmet or no evidence: {', '.join(unmet)}")
            crit_detail = "; ".join(parts)
    reqs.append(
        _verdict_req(
            "verification",
            "completion verified, every acceptance criterion met (task-verifier)",
            verification,
            now,
            brief("verification", "task-verifier"),
            fix,
            extra_ok=crit_ok,
            extra_detail=crit_detail,
        )
    )

    # 8. Reviews — every required reviewer passes at the current snapshot
    waiver = ctx.latest_kind("resolution", action="waive", **match)
    waived = set(waiver.get("reviewers") or []) if waiver and _snap_id(waiver) == now else set()
    for reviewer in spec.required_reviewers():
        entry = ctx.latest_result("review", agent_type=reviewer, **match)
        blocking = int((_res(entry).get("findings") or {}).get("blocking") or 0) if entry else 0
        req = _verdict_req(
            f"review:{reviewer}",
            f"review by {reviewer}",
            entry,
            now,
            brief("review", reviewer),
            fix,
            extra_ok=blocking == 0,
            extra_detail=f"{blocking} blocking finding(s) (report: {_res(entry).get('report')})" if blocking else "",
        )
        if not req.ok and reviewer in waived:
            req = Req(req.key, req.label, True, f"blocking findings waived by the human (resolution seq {waiver['seq']})")
        reqs.append(req)

    # 9. Integrity scan at the current snapshot
    scan = ctx.latest_kind("scan", **match)
    if scan is None or _snap_id(scan) != now:
        reqs.append(Req("scan", "integrity scan at current snapshot", False,
                        "not yet run" if scan is None else f"stale (ran at {_snap_id(scan)})",
                        f"`orch task scan {task_id}`"))
    else:
        reqs.append(Req("scan", "integrity scan at current snapshot", True,
                        f"digest {scan.get('digest')}, {scan.get('hit_count')} hit(s)"))

    # 10. PM acceptance stamp citing the current scan
    pm = ctx.latest_result("pm-accept", **match)
    digest = scan.get("digest") if scan else None
    cites = pm is not None and _res(pm).get("scan_digest") == digest
    reqs.append(
        _verdict_req(
            "pm-accept",
            "PM acceptance stamp (project-manager)",
            pm,
            now,
            brief("pm-accept", "project-manager"),
            f"PM rejected the task — `orch task fail {task_id} --reason \"<PM findings>\"` starts the next attempt",
            extra_ok=cites or pm is None,
            extra_detail="" if cites else f"cites scan {_res(pm).get('scan_digest')}, current scan is {digest}",
        )
    )
    if pm is not None and not cites and reqs[-1].failed:
        reqs[-1] = Req("pm-accept", "PM acceptance stamp (project-manager)", False,
                       f"stale: cites scan {_res(pm).get('scan_digest')}, current is {digest}",
                       brief("pm-accept", "project-manager"))
    return reqs


# ================================================================== loops


def loop_tasks(ctx: Context, loop: int) -> List[planmod.TaskSpec]:
    return ctx.pkg.tasks_in_loop(loop)


def loop_open_checklist(ctx: Context, loop: int) -> List[Req]:
    state = ctx.state
    reqs: List[Req] = []
    loops = state.get("loops") or {}
    for prior in range(1, loop):
        closed = (loops.get(str(prior)) or {}).get("status") == "CLOSED"
        reqs.append(Req(f"loop{prior}", f"loop {prior} closed", closed, "",
                        "" if closed else f"close loop {prior} first"))
    approved_seq = int(state.get("approved_seq") or 0)
    entry = ledger.latest(
        [e for e in ctx.results("pm-loop-entry", loop=loop) if e["seq"] > approved_seq]
    )
    reqs.append(
        _verdict_req(
            "pm-loop-entry",
            f"PM loop-entry check for loop {loop}",
            entry,
            None,
            f"`orch brief --loop {loop} pm-loop-entry --agent project-manager` then dispatch project-manager",
            "PM loop-entry failed — resolve what it names (plan defect: `orch deviation`)",
        )
    )
    return reqs


def loop_close_checklist(ctx: Context, loop: int) -> List[Req]:
    state = ctx.state
    tasks = loop_tasks(ctx, loop)
    reqs: List[Req] = []
    for spec in tasks:
        status = (state.get("tasks") or {}).get(spec.id, {}).get("status")
        reqs.append(Req(f"task:{spec.id}", f"{spec.id} accepted", status == "ACCEPTED", f"status {status}",
                        "" if status == "ACCEPTED" else f"finish {spec.id}"))
    workspaces = sorted({t.workspace for t in tasks})
    comp, snaps = ctx.composite(workspaces)
    for snap in snaps:
        if not planmod.gate_commands(ctx.pkg.gate, snap.workspace, "standard"):
            continue
        gate = ctx.latest_kind("gate", scope="loop", loop=loop, level="standard", workspace=snap.workspace)
        ok = bool(gate) and gate.get("passed") and _snap_id(gate) == snap.id
        detail = "not yet run" if gate is None else ("passed" if ok else (
            f"stale (ran at {_snap_id(gate)})" if _snap_id(gate) != snap.id else f"failed: {gate.get('summary')}"))
        reqs.append(Req(f"gate:{snap.workspace}", f"loop gate ({snap.workspace}) at current snapshot", bool(ok),
                        detail, f"`orch gate run standard --loop {loop} --workspace {snap.workspace}`",
                        failed=bool(gate) and not gate.get("passed") and _snap_id(gate) == snap.id))
    reqs.append(
        _verdict_req(
            "pm-loop-exit",
            f"PM loop-exit check for loop {loop}",
            ctx.latest_result("pm-loop-exit", loop=loop),
            comp,
            f"`orch brief --loop {loop} pm-loop-exit --agent project-manager` then dispatch project-manager",
            "PM loop-exit failed — cross-task problems belong to the task that caused them: "
            "`orch deviation` if a plan change is needed, otherwise raise it with the human",
        )
    )
    return reqs


# ================================================================== final


def final_workspaces(ctx: Context) -> List[str]:
    return sorted({t.workspace for t in ctx.pkg.tasks.values()})


def final_checklist(ctx: Context) -> List[Req]:
    state = ctx.state
    final = state.get("final") or {}
    reqs: List[Req] = []
    if final.get("status") != "OPEN":
        return [Req("final-start", "final review started", False, "", "`orch final start`")]
    rnd = int(final.get("round") or 0)
    comp, snaps = ctx.composite(final_workspaces(ctx))
    types = [t.type for t in ctx.pkg.tasks.values()]
    for reviewer in required_final_reviewers(types, bool(final.get("doc_files_changed"))):
        entry = ctx.latest_result("final-review", agent_type=reviewer)
        blocking = int((_res(entry).get("findings") or {}).get("blocking") or 0) if entry else 0
        waiver = ctx.latest_kind("resolution", action="waive", scope="final")
        req = _verdict_req(
            f"final-review:{reviewer}",
            f"final review by {reviewer}",
            entry,
            comp,
            f"`orch brief --final final-review --agent {reviewer}` then dispatch {reviewer}",
            "start a final fix round: `orch final round`, then resume the relevant author(s) "
            "with `orch brief --final final-fix --agent <author>`",
            extra_ok=blocking == 0,
            extra_detail=f"{blocking} blocking finding(s)" if blocking else "",
        )
        if not req.ok and waiver and _snap_id(waiver) == comp and reviewer in (waiver.get("reviewers") or []):
            req = Req(req.key, req.label, True, "blocking findings waived by the human")
        reqs.append(req)
    for snap in snaps:
        if not planmod.gate_commands(ctx.pkg.gate, snap.workspace, "final") and not planmod.gate_commands(
            ctx.pkg.gate, snap.workspace, "standard"
        ):
            continue
        gate = ctx.latest_kind("gate", scope="final", level="final", workspace=snap.workspace)
        ok = bool(gate) and gate.get("passed") and _snap_id(gate) == snap.id
        reqs.append(Req(f"final-gate:{snap.workspace}", f"final gate ({snap.workspace}) at current snapshot",
                        bool(ok), "not yet run" if gate is None else ("passed" if ok else "stale or failed"),
                        f"`orch gate run final --final --workspace {snap.workspace}`",
                        failed=bool(gate) and not gate.get("passed") and _snap_id(gate) == snap.id))
    verification = ctx.latest_result("final-verification")
    wanted = list(ctx.pkg.plan.final_criteria)
    crit_ok, crit_detail = True, ""
    if verification is not None:
        got = {c.get("id"): c for c in _res(verification).get("criteria") or [] if isinstance(c, dict)}
        bad = [f for f in wanted if f not in got or not got[f].get("met") or not str(got[f].get("evidence") or "").strip()]
        if bad:
            crit_ok, crit_detail = False, f"final criteria unmet or unassessed: {', '.join(bad)}"
    reqs.append(
        _verdict_req(
            "final-verification",
            "final acceptance criteria verified (task-verifier)",
            verification,
            comp,
            "`orch brief --final final-verification --agent task-verifier` then dispatch task-verifier",
            "start a final fix round: `orch final round`",
            extra_ok=crit_ok,
            extra_detail=crit_detail,
        )
    )
    reqs.append(
        _verdict_req(
            "pm-final",
            "PM final acceptance (project-manager)",
            ctx.latest_result("pm-final"),
            comp,
            "`orch brief --final pm-final --agent project-manager` then dispatch project-manager",
            "PM rejected the package — start a final fix round (`orch final round`) or, if the "
            "gap needs a plan change, `orch deviation`",
        )
    )
    del rnd
    return reqs


# ================================================================== planning


def research_checklist(ctx: Context) -> List[Req]:
    """Focused research items: registered, approved by the PM before dispatch, then complete."""
    state = ctx.state
    if research.is_legacy(state):
        return []
    items = research.items(state)
    live = {iid: st for iid, st in research.statuses(ctx.entries, state).items() if st[0] != "DROPPED"}
    if not live and state.get("upgraded_seq") and ctx.results("research"):
        return [Req("research-items", "research gathered", True,
                    "research from before the upgrade carries over; the PM's sufficiency check judges it")]
    if not live:
        return [Req("research-items", "focused research items registered", False, "none yet",
                    "register each question set with `orch research add --agent <agent> --title \"...\" "
                    "--questions-file <file> --done-when \"...\"` (at most 3 questions per item; more items, "
                    "not bigger ones), then the PM's research-plan review")]
    reqs: List[Req] = []
    proposed = [i for i, st in live.items() if st[0] == "PROPOSED"]
    rejected = [i for i, st in live.items() if st[0] == "REJECTED"]
    if proposed:
        reqs.append(Req("pm-research-plan", "PM approved every research item before dispatch", False,
                        f"awaiting review: {', '.join(proposed)}",
                        "`orch brief --plan pm-research-plan --agent project-manager` then dispatch project-manager"))
    elif rejected:
        reqs.append(Req("pm-research-plan", "PM approved every research item before dispatch", False,
                        "rejected: " + "; ".join(f"{i} ({live[i][1]})" for i in rejected),
                        "rework each rejected item as the PM's report says: `orch research drop <id> --reason ...`, "
                        "`orch research add` a narrower one, then the PM's research-plan review", failed=True))
    else:
        reqs.append(Req("pm-research-plan", "PM approved every research item before dispatch", True))
    interims = {(_res(e).get("item")): e for e in open_interims(ctx) if _res(e).get("stage") == "research"}
    open_items = [i for i, st in live.items() if st[0] in ("APPROVED", "INTERIM", "NEEDS_INPUT", "BLOCKED")]
    if not open_items:
        reqs.append(Req("research", "approved research complete", True,
                        f"{sum(1 for st in live.values() if st[0] == 'DONE')} item(s) done"))
        return reqs
    first = open_items[0]
    first_state = live[first][0]
    if first in interims:
        stop = interim_req(ctx, interims[first])
        detail, action = f"{first}: {stop.detail}", stop.action
    elif first_state == "APPROVED":
        agent = items[first].get("agent")
        detail = f"not yet reported: {', '.join(i for i in open_items if live[i][0] == 'APPROVED')}"
        action = (f"`orch brief --plan research --item {first} --agent {agent}` then dispatch {agent} "
                  "(at most 3 research agents at once)")
    else:
        detail = f"{first} is {first_state}: {live[first][1]}"
        action = "answer its questions (see its report) and resume the same agent via SendMessage"
    reqs.append(Req("research", "approved research complete", False, detail, action))
    return reqs


def planning_checklist(ctx: Context, current_hash: str) -> List[Req]:
    state = ctx.state
    rev = int(state.get("plan_revision") or 1)
    reqs: List[Req] = research_checklist(ctx)
    last_research = ledger.latest(ctx.results("research"))
    # After an upgrade, only a sufficiency check made under the new rules counts.
    floor = max(int((last_research or {}).get("seq") or 0), int(state.get("upgraded_seq") or 0))
    pm_research = ledger.latest([e for e in ctx.results("pm-research") if e["seq"] > floor])
    if research.is_legacy(state):
        dispatch = insufficient = ("upgrade the workflow first: the human types `/task-orchestrator upgrade "
                                   "<kind>`, then `orch upgrade --kind <kind>`")
    else:
        dispatch = "`orch brief --plan pm-research --agent project-manager` then dispatch project-manager"
        insufficient = ("research is insufficient — register each gap the PM names as a focused item "
                        "(`orch research add`), get it approved (pm-research-plan), dispatch it, then re-check")
    reqs.append(
        _verdict_req(
            "pm-research",
            "PM research-sufficiency check",
            pm_research,
            None,
            dispatch,
            insufficient,
        )
    )
    plan_result = ctx.latest_result("plan", plan_revision=rev, status="complete")
    reqs.append(Req("plan", f"plan package written (planning-author, revision {rev})", plan_result is not None,
                    "" if plan_result is None else f"report: {_res(plan_result).get('report')}",
                    "`orch brief --plan plan --agent planning-author` then dispatch planning-author"))
    has_code = any(t.type in CODE_LIKE_TYPES for t in ctx.pkg.tasks.values())
    if has_code:
        test_plan = ctx.latest_result("test-plan", plan_revision=rev, status="complete")
        reqs.append(Req("test-plan", "test plan written into plan.md (test-planner)", test_plan is not None, "",
                        "`orch brief --plan test-plan --agent test-planner` then dispatch test-planner"))
    doc_review = ctx.latest_result("plan-review", agent_type="doc-reviewer")
    reqs.append(
        _verdict_req(
            "plan-review:doc-reviewer",
            "plan package reviewed for accuracy and clarity (doc-reviewer)",
            doc_review,
            None,
            "`orch brief --plan plan-review --agent doc-reviewer` then dispatch doc-reviewer",
            "resume planning-author with the review findings, then re-review",
            extra_ok=_res(doc_review).get("plan_hash") == current_hash if doc_review else True,
            extra_detail="stale: the plan changed after this review" if doc_review else "",
        )
    )
    if doc_review and _passed(doc_review) and _res(doc_review).get("plan_hash") != current_hash:
        reqs[-1] = Req(reqs[-1].key, reqs[-1].label, False, "stale: the plan changed after this review",
                       "`orch brief --plan plan-review --agent doc-reviewer` then dispatch doc-reviewer")
    pkg = planmod.validate(ctx.wf, state)
    reqs.append(Req("validate", "plan package validates", not pkg.errors,
                    f"{len(pkg.errors)} error(s): run `orch validate`" if pkg.errors else "",
                    "resume planning-author with the `orch validate` errors"))
    pm = ctx.latest_result("pm-plan")
    stale = pm is not None and _res(pm).get("plan_hash") != current_hash
    req = _verdict_req(
        "pm-plan",
        "PM plan audit (project-manager)",
        None if stale else pm,
        None,
        "`orch brief --plan pm-plan --agent project-manager` then dispatch project-manager",
        "resume planning-author with the PM's findings, then re-audit",
    )
    if stale:
        req.detail = "stale: the plan changed after this audit"
    reqs.append(req)
    reqs.append(Req("submit", "plan submitted for human approval", False, "",
                    "`orch submit`, then present the plan to the human"))
    return reqs


# ================================================================== next


def needs_human_text(state: Dict[str, Any]) -> str:
    need = state.get("needs_human") or {}
    kind = need.get("kind", "?")
    actions = RESOLVE_ACTIONS.get(kind, ())
    task = f" {need['task']}" if need.get("task") else ""
    options = " | ".join(f"`/task-orchestrator resolve {a}{task} <notes>`" for a in actions)
    report = f" Report: {need['report']}." if need.get("report") else ""
    return (
        f"WAITING FOR THE HUMAN ({kind}): {need.get('summary', '')}.{report} "
        f"The human decides with: {options or '`/task-orchestrator resolve ...`'}."
    )


def next_action(ctx: Context, current_hash: Optional[str] = None) -> str:
    state = ctx.state
    phase = state.get("phase")
    if phase in ("PLANNING", "EXECUTING", "FINAL"):
        if state.get("halt_requested") or ctx.wf.halt_path.exists():
            return ("PAUSE REQUESTED by the human — dispatch nothing new. Running read-only agents write interim "
                    "reports and authors finish their current pass; end your turn and the workflow becomes HALTED.")
        interims = open_interims(ctx)
        if interims:
            req = interim_req(ctx, interims[0])
            return f"INTERIM — {req.label}: {req.detail}. Next: {req.action}"
        cut_off = [r for r in activity.summaries(ctx.wf, state, ctx.entries) if r["status"] == "interrupted"]
        if cut_off:
            row = cut_off[0]
            return (f"INTERRUPTED — {row['agent_type']} {row['agent_id']} ({row.get('stage') or '?'}) was running when "
                    f"its session ended. Next: `orch agent continue {row['agent_id']}` and SendMessage the printed text "
                    "to that agent id; if that fails, dispatch a fresh agent for the same stage")
    if phase == "PLANNING" and research.is_legacy(state):
        return (LEGACY_PLANNING + " Stop and ask the human which kind this workflow delivers (code, docs, kb, "
                "tutorial, education, research, pm, integration, mixed); they type `/task-orchestrator upgrade "
                "<kind>`, then run `orch upgrade --kind <kind>`.")
    if phase == "PLANNING":
        req = first_unmet(planning_checklist(ctx, current_hash or planmod.plan_hash(ctx.wf)))
        return f"PLANNING — next: {req.label}: {req.action}" if req else "PLANNING — run `orch submit`"
    if phase == "AWAITING_APPROVAL":
        return ("WAITING FOR THE HUMAN: review the plan package, then type "
                "`/task-orchestrator approve` or `/task-orchestrator revise <feedback>`.")
    if phase == "NEEDS_HUMAN":
        return needs_human_text(state)
    if phase == "PLAN_CHANGE_REQUIRED":
        return (f"WAITING FOR THE HUMAN: plan change required — {state.get('block_reason')}. "
                "The human decides with `/task-orchestrator revise <feedback>`.")
    if phase == "HALTED":
        return "HALTED by the human. They resume with `/task-orchestrator resume`."
    if phase == "DONE":
        return ("WAITING FOR THE HUMAN (acceptance testing): `/task-orchestrator close` or "
                "`/task-orchestrator revise <feedback>`.")
    if phase == "CLOSED":
        return "CLOSED."
    if phase == "FINAL":
        req = first_unmet(final_checklist(ctx))
        return f"FINAL — next: {req.label}: {req.action}" if req else "FINAL — run `orch final accept`"
    if phase != "EXECUTING":
        return f"unknown phase {phase}"

    tasks_state = state.get("tasks") or {}
    loops_state = state.get("loops") or {}
    for loop in ctx.pkg.loops():
        status = (loops_state.get(str(loop)) or {}).get("status", "PENDING")
        if status == "CLOSED":
            continue
        if status == "PENDING":
            req = first_unmet(loop_open_checklist(ctx, loop))
            return (f"LOOP {loop} — next: {req.label}: {req.action}" if req
                    else f"LOOP {loop} — run `orch loop open {loop}`")
        specs = loop_tasks(ctx, loop)
        active = [s for s in specs if tasks_state.get(s.id, {}).get("status") == "IN_PROGRESS"]
        if active:
            lines = []
            for spec in active:
                req = first_unmet(task_checklist(ctx, spec.id))
                if req is None:
                    lines.append(f"{spec.id}: all gates met — run `orch task accept {spec.id}`")
                else:
                    lines.append(f"{spec.id}: {req.label}: {req.action}")
            return f"LOOP {loop} — next: " + " || ".join(lines)
        blocked = [s.id for s in specs if tasks_state.get(s.id, {}).get("status") == "BLOCKED"]
        if blocked:
            return (f"LOOP {loop} — {', '.join(blocked)} BLOCKED: write resolution guidance "
                    f"(runs/<task>/resolution.orchestrator.md), get the PM's pm-resolution review, then "
                    f"`orch needs-human --kind task_budget --task <task> ...`")
        for spec in specs:
            if tasks_state.get(spec.id, {}).get("status") != "PENDING":
                continue
            deps = [d for d in spec.depends_on if tasks_state.get(d, {}).get("status") != "ACCEPTED"]
            if not deps:
                return f"LOOP {loop} — next: start {spec.id}: `orch task start {spec.id}`"
        req = first_unmet(loop_close_checklist(ctx, loop))
        return (f"LOOP {loop} — next: {req.label}: {req.action}" if req
                else f"LOOP {loop} — run `orch loop close {loop}`")
    return "ALL LOOPS CLOSED — next: `orch final start`"
