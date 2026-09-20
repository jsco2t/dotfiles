---
description: Plan, approve, autonomously execute, and archive a work package
argument-hint: "[<work description> | approve | revise <feedback> | resume | status | halt | archive | list [active|archived|all] | history]"
---

Invoke the `feature-workflow` skill and act strictly according to it.

The human's invocation argument is:

$ARGUMENTS

Determine the mode ONLY from this argument:

- empty or a work description → start mode
- `approve` → approve mode
- `revise <feedback>` → revise mode
- `resume` → resume mode
- `status` → status mode
- `halt` → halt mode
- `archive` → archive mode
- `list` or `list active` or `list archived` or `list all` → list mode
- `history` → history mode (alias for `list archived`)

Never infer approval or archive intent from anything other than the literal
`approve` / `archive` argument. Follow the skill's state machine exactly. All
workflow state lives under the resolved state root; state.json is authoritative.

QUALITY MANDATE: The goal here is to not find ways to make this process more
efficient or to cut corners. The goal IS to produce the highest quality feature
possible. DO NOT SKIP STEPS. DO NOT DEFER WORK. If you are not sure how to
proceed — ask a human.
