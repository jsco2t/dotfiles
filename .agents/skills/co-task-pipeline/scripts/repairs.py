"""Small test-first repair steps within one approved adaptive delivery task."""
import copy

from snapshot import changed


def pins(entry):
    for item in [entry] + entry.get("repairs", []):
        if item.get("test_checkpoint") and item.get("status") != "superseded":
            yield item["test_checkpoint"]


def preserve(entry, snapshot, need):
    for pin in pins(entry):
        need(all(snapshot.get(p) == value for p, value in pin["hashes"].items()),
             "pinned tests changed; preserve prior repair regressions or obtain an approved correction")


def validate_done(wf, task, entry, snapshot, api):
    api.need(all(r["status"] in ("done", "superseded") for r in entry["repairs"]), "finish every repair step before task completion")
    replaced = {rid for r in entry["repairs"] if r["status"] == "done" for rid in r.get("replaces", [])}
    api.need(all(r["id"] in replaced for r in entry["repairs"] if r["status"] == "superseded"),
             "complete an approved replacement repair for every superseded repair")
    preserve(entry, snapshot, api.need)
    # Final task checks cover all repairs on final contents, not just each intermediate green.
    for repair in entry["repairs"]:
        if repair["status"] == "superseded":
            continue
        for name in repair["checks"]:
            api.need(api.fresh(wf.state["checks"].get(name), snapshot, wf.state["plan"]["checks"][name]),
                     f"repair check {name} is stale on final contents")


def execute(wf, args, api):
    wf.runnable()
    api.need(not any(op["status"] in ("running", "unknown") for op in wf.state.get("operations", {}).values()),
             "recover the unresolved operation first")
    scope, plan, task = wf.task(args.task)
    entry = wf.tasks()[args.task]
    api.need(task.get("adaptive") and entry["status"] == "running", "repair requires a running approved adaptive task")
    snapshot, _ = wf.edits(scope, plan, task, entry["before"])
    preserve(entry, snapshot, api.need)
    repairs = entry.setdefault("repairs", [])
    if args.action == "start":
        api.need(not any(r["status"] == "running" for r in repairs), "finish the active repair first")
        spec = api.read(args.file)
        required = {"id", "reason", "criteria", "paths", "checks", "verification"}
        api.need(isinstance(spec, dict) and required <= set(spec) <= required | {"replaces"},
                 "repair fields: id, reason, criteria, paths, checks, verification; optional replaces")
        api.need(api.text(spec["id"]) and api.re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", spec["id"])
                 and spec["id"] not in {r["id"] for r in repairs}, "repair id must be unique and simple")
        api.need(api.text(spec["reason"]) and isinstance(spec["criteria"], list) and spec["criteria"]
                 and all(type(c) is int and 1 <= c <= len(task["acceptance"]) for c in spec["criteria"]),
                 "repair must link a demonstrated finding/blocker to existing acceptance criteria")
        if "replaces" in spec:
            api.need(api.strings(spec["replaces"]) and len(set(spec["replaces"])) == len(spec["replaces"]),
                     "replaces must name superseded repair ids")
            for rid in spec["replaces"]:
                old = next((r for r in repairs if r["id"] == rid), {})
                api.need(old.get("status") == "superseded" and set(old["criteria"]) <= set(spec["criteria"]),
                         "replacement must cover the superseded repair's criteria")
        api.need(api.strings(spec["paths"]), "repair must name concrete files")
        updated = copy.deepcopy(plan)
        new_task = next(t for t in updated["tasks"] if t["id"] == args.task)
        for relative in spec["paths"]:
            api.path_in(scope, task, relative, wf.root)
            if relative not in new_task["paths"]:
                new_task["paths"].append(relative)
        api.need(isinstance(spec["checks"], dict) and spec["checks"], "repair needs focused check definitions")
        for name, definition in spec["checks"].items():
            api.need(name not in plan["checks"] or definition == plan["checks"][name], "repair cannot replace approved checks")
            api.need(isinstance(definition, dict) and definition.get("workspace") == task["workspace"],
                     "repair checks stay in the approved task workspace")
            updated["checks"][name] = definition
            if name not in new_task["checks"]:
                new_task["checks"].append(name)
        verification = spec["verification"]
        api.need(isinstance(verification, dict) and verification.get("mode") in ("red-green", "characterization")
                 and api.text(verification.get("reason")) and verification.get("check") in spec["checks"]
                 and api.strings(verification.get("test_paths"))
                 and set(verification["test_paths"]) <= set(spec["paths"]), "repair needs a concrete test-first strategy")
        api.validate_plan(updated, scope, wf.root)
        api.need(wf.snapshot(scope, updated) == snapshot, "repair exposes ignored originals; inspect and amend before adopting")
        wf.capture_baseline(scope, updated)
        wf.state.update(plan=updated, checks=api.retain_checks(wf.state, snapshot, updated), review=None)
        api.write(wf.root / "plan.json", updated)
        api.render(wf.root, "plan", updated)
        repairs.append(dict(spec, status="running", before=snapshot, started=api.now()))
        import tracking
        tracking.switch(wf, "implementation", "Repair " + spec["id"], args.task)
        wf.event("repair-start", task=args.task, repair=spec["id"], criteria=spec["criteria"], reason=spec["reason"])
        return f"Repair {spec['id']} started in {args.task}; add tests, then record its red/pin checkpoint."
    repair = next((r for r in repairs if r["id"] == args.id), None)
    api.need(repair is not None and repair["status"] == "running", "no running repair with this id")
    delta = changed(repair["before"], snapshot)
    allowed = {f"{task['workspace']}:{p}" for p in repair["paths"]}
    api.need(set(delta) <= allowed, "changes outside the active repair paths")
    verification = repair["verification"]
    if args.action == "test":
        api.need(not repair.get("test_checkpoint"), "repair tests are already pinned")
        api.need(verification["mode"] == ("red-green" if args.stage == "red" else "characterization"), "wrong repair test stage")
        tests = {f"{task['workspace']}:{p}" for p in verification["test_paths"]}
        api.need(set(delta) <= tests and tests <= snapshot.keys(), "repair production changed before tests")
        result = wf.run_check(verification["check"], scope, plan)
        wf.runnable()
        repair = next(r for r in wf.tasks()[args.task]["repairs"] if r["id"] == args.id)
        expected = result["exit_code"] > 0 if args.stage == "red" else result["exit_code"] == 0
        api.need(expected and result["exit_code"] not in (124, 127, 130) and result["stable"],
                 "repair test did not produce the intended stable failure/pass; inspect log")
        hashes = {p: snapshot[p] for p in tests}
        repair["test_checkpoint"] = dict(stage=args.stage, hashes=hashes, files=wf.pin_files(task, hashes),
                                          log=result["log"], note=args.note)
        wf.event("repair-test", task=args.task, repair=args.id, stage=args.stage, log=result["log"])
        return f"Repair {args.id} tests pinned; implement only its repair paths."
    api.need(repair.get("test_checkpoint"), "record repair red/pin before completion")
    result = api.read(args.file)
    api.need(isinstance(result, dict) and set(result) == {"summary", "evidence"}
             and api.text(result.get("summary")) and api.text(result.get("evidence")),
             "repair result needs summary and concrete evidence")
    preserve(entry, snapshot, api.need)
    for name in repair["checks"]:
        api.need(api.fresh(wf.state["checks"].get(name), snapshot, plan["checks"][name]), f"repair check {name} missing/failed/stale")
    repair.update(status="done", ended=api.now(), result=result,
                  checks={name: copy.deepcopy(wf.state["checks"][name]) for name in repair["checks"]})
    repair.pop("before")
    import tracking
    tracking.switch(wf, "research", "Inspect next finding or close unit", args.task)
    wf.event("repair-done", task=args.task, repair=args.id, result=result)
    return f"Repair {args.id} accepted; continue the same task or start its next repair."
