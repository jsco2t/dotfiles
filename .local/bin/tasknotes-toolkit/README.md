# TaskNotes toolkit

Manage a local backlog as ordinary Markdown notes, with no Obsidian process, server,
database or Python packages to install. The `tntk` command and importable `TaskStore`
library use Python's standard library. Python 3.10+ on Linux or macOS is supported.

The task directory is the only collection setting you must supply. The CLI defaults to
human-readable text; `--format json` provides complete, versioned records for agents.
Descriptions stay in the Markdown body so a human can read and edit the same tasks.

## Run from the repository or deployed dotfiles

From this repository:

```sh
python3 .local/bin/tntk /path/to/tasks list
```

After your normal dotfiles deployment places `.local/bin` on `PATH`:

```sh
tntk /path/to/tasks list
tntk /path/to/tasks --format json next --project Alpha --limit 3
```

The launcher finds its adjacent `tasknotes-toolkit` directory; it does not install or
configure anything globally. Keep the directory and launcher together. Every command
has `--help`. Global `--format` and `--dry-run` flags go before the subcommand.

The portable agent skill is `.agents/skills/tasknotes-toolkit/SKILL.md` in this repository.
It uses standard name/description frontmatter and no agent-specific tools. OpenCode's
[skill discovery](https://opencode.ai/docs/skills/) includes `.agents/skills` and
`~/.agents/skills`; the existing dotfiles skill location can therefore serve both agents.

## Create tasks a human can understand

Start the description with the intended result and why it matters. Then explain the
relevant current behavior, scope and acceptance criteria in complete sentences. Include
the verification that will demonstrate completion. Short is fine when the work is simple;
never compress away the context your collaborator needs to participate.

```sh
tntk /path/to/tasks create 'Keep user sessions during retries' \
  --project '[[Customer Portal]]' --priority high --description-file - <<'MARKDOWN'
Keep the user's session active during a failed request retry so they can finish signing in.

The current retry path discards a valid session token. Preserve the token while retrying
the same request, and keep the existing expiry behavior when the token has actually expired.

## Acceptance

- A transient network failure retries without asking the user to sign in again.
- An expired session still sends the user to the sign-in page.

## Verification

Add a regression for each case and run the session test suite.
MARKDOWN
```

Use another project name for another backlog; tasks can belong to several projects by
repeating `--project`. Plain names and quoted Obsidian wikilinks are both accepted.

New notes use filename-safe, readable titles and numeric suffixes for collisions. They
contain stable UUIDs, `tags: [task]`, `status: open`, `priority: normal`, `dateCreated`
and `dateModified`. Titles and task IDs survive ordinary metadata/body edits.

## Optional coding-work metadata

All six fields below are optional. Ordinary tasks keep their existing behavior; missing
repository, work-type, reference and claim metadata is not invented.

| Field | Meaning |
| --- | --- |
| `repository` | Nonempty, single-line Git remote URL or repository identifier. HTTPS and SSH forms work. |
| `workingDirectory` | Repository-relative POSIX directory, such as `services/auth`; `.` means its root. |
| `workType` | `bug`, `feature`, `docs`, `research` or `maintenance`. |
| `sourceRefs` | List of nonempty issue, requirement, document or discussion references. |
| `claimedBy` | Current owning session/run identifier, distinct from a general agent/model name. |
| `claimedAt` | Claim timestamp; canonical writes use UTC ISO seconds. It requires an owner. |

```sh
tntk /path/to/tasks create 'Preserve sessions during retries' \
  --description-file details.md \
  --repository 'https://github.com/example/customer-portal' \
  --working-directory services/auth --work-type bug \
  --source-ref 'https://github.com/example/customer-portal/issues/42' \
  --source-ref '[[Login requirements]]'
tntk /path/to/tasks edit TASK_ID --work-type maintenance --working-directory .
tntk /path/to/tasks next --repository 'https://github.com/example/customer-portal' --work-type bug --limit 3
```

The same metadata flags work on `create` and `edit`. Repeated `--source-ref` flags set
the entire reference list; unspecified fields are preserved. `--set`/`--unset` also work.
`list` and `next` filter by exact repository/work type, and `list --claimed-by SESSION`
finds owned work. All six fields appear in `show` text and JSON `fields`, and support
optional `fieldMapping` entries.

The toolkit does not fetch URLs, choose a checkout or change directory. The agent resolves
the local repository before using its relative working directory. Absolute paths, parent
traversal, Windows drive/UNC paths and home expansion are refused in `workingDirectory`.
Descriptions, acceptance and evidence remain in the readable Markdown body.

## Inspect and work on a bounded number of tasks

```sh
tntk /path/to/tasks list --project 'Customer Portal'
tntk /path/to/tasks list --status in-progress
tntk /path/to/tasks list --search 'session token'
tntk /path/to/tasks --format json next --project 'Customer Portal' --limit 3
tntk /path/to/tasks show TASK_ID
tntk /path/to/tasks show 'Keep user sessions during retries.md' --raw
```

`show` includes the entire description; JSON records are never silently truncated. `next`
is read-only. It selects unarchived tasks in the configured default backlog status (or
`none`), excluding claimed, active, finished, future-scheduled and recurring tasks. Missing,
ambiguous or unfinished `blockedBy` targets block readiness. Dependency relation and gap
metadata are retained; readiness uses the referenced task's completed status, consistent
with the specification's status-based blocking rule. Priority sorts descending, then due
date and path give a stable order. Date comparisons use local calendar days.

When an agent is asked to work on N tasks, it reads each full task, checks the relevant
project/repository instructions and starts one task using its current revision. It verifies
the work and records the result before completing it. After each result, it can select the
next ready task; a finished prerequisite may have unblocked new work. Blocked tasks are
reported honestly and do not count as delivered tasks.

```sh
tntk /path/to/tasks start TASK_ID --claimed-by SESSION_ID --if-match REVISION_FROM_SHOW_OR_NEXT
tntk /path/to/tasks note TASK_ID --claimed-by SESSION_ID --message 'The session regression now reproduces the bug.'
tntk /path/to/tasks complete TASK_ID --claimed-by SESSION_ID --message 'Both regressions and the full session suite pass.'
```

The toolkit records work; it does not run a coding agent, execute commands from task bodies,
or infer that a task is done. The human/agent is responsible for implementing and verifying
the acceptance criteria. In-progress tasks remain visible for resuming work after interruption.

## Claim and resume work

`start --claimed-by SESSION` records ownership, claim time and active status in the same
locked, atomic write. Repeating it as the same owner preserves its original timestamp and
revision. Claimed tasks require that owner ID on all mutations: notes, edits, completion,
reopen, archive and deletion. Other/unidentified sessions receive `claim_conflict`.
Deletion's `--force` does not bypass ownership. Tasks without claims need no session argument.

Reuse one stable identifier for the current run/session. If the host exposes none, an agent
can generate a UUID once. The identifier coordinates cooperating users/agents; it is not an
authentication token or protection against direct file edits.

Completion, reopening and generic status changes away from the active status clear both
claim fields. Results and verification remain in the body. `release` clears ownership and
returns unfinished work to the backlog; it leaves completed work completed.

```sh
tntk /path/to/tasks list --claimed-by SESSION_ID --status in-progress
tntk /path/to/tasks release TASK_ID --claimed-by SESSION_ID --if-match CURRENT_REVISION
tntk /path/to/tasks --dry-run release TASK_ID --force --if-match CURRENT_REVISION
```

Claims never expire automatically. Inspect an abandoned task/workspace before deliberate
recovery with `release --force --if-match CURRENT_REVISION`. Force release requires that
exact current revision and only clears ownership/returns unfinished work to the backlog.
A newer task change still causes a conflict. An imported owner without a timestamp is
retained; starting as that owner supplies the timestamp. Creating an owned task supplies
its claim time when absent. Prefer atomic `start` to manual claim-field edits for normal work.

## Edit and manage the lifecycle

| Command | Behavior |
| --- | --- |
| `edit ID --set priority=high` | Change a field while retaining unrelated YAML and body text. |
| `edit ID --set 'projects=["[[Alpha]]","[[Beta]]"]'` | Explicitly replace the project list. |
| `edit ID --unset due` | Remove an optional field. |
| `edit ID --description-file details.md` | Explicitly replace the full description. |
| `note ID --section Blockers --message '…'` | Append readable context without replacing the description. |
| `complete ID --on 2026-11-21` | Set completed status/date; preserve an existing completion day. |
| `reopen ID` | Restore the default unfinished status and clear completion date. |
| `release ID --claimed-by SESSION` | Clear ownership and return unfinished work to the backlog. |
| `archive ID` / `unarchive ID` | Add/remove the `archived` tag without deleting or moving the note. |
| `--dry-run delete ID` | Validate and preview deletion without writing anything. |
| `delete ID --yes` | Delete just this task file, retaining referenced attachments. |
| `validate [ID]` | Report common field/schema issues without changing files. |
| `config` | Inspect effective mapping, identification and lifecycle settings. |

Use semantic TaskNotes names such as `status`, `completedDate`, `dateCreated` and
`timeEstimate` in `--set`, even when storage keys are mapped differently. Values can be
plain strings or JSON values; arrays/objects require valid JSON. Mutations accept
`--if-match REVISION` to reject edits based on an older file. Set/delete operations are
explicit: an omitted field is preserved. Task IDs cannot be rewritten.

Generic status edits follow the same completion rules as dedicated commands. Completing
a non-recurring task supplies `completedDate`; reopening clears it. Repeated equivalent
operations leave the file and `dateModified` unchanged. Completion without `--on` uses
the local calendar day; timestamps are UTC ISO strings at second precision.

Deletion refuses tasks referenced by other tasks unless `--force` is also supplied.
`--yes` is a command-line intent flag, not a separate approval conversation when the user
already explicitly requested that deletion. No bulk irreversible deletion is implicit.

## Optional collection configuration

Put `.tasknotes-toolkit.json` in the task directory to override defaults. No configuration
file is needed for ordinary use. The supported settings use TaskNotes plugin JSON names:

```json
{
  "fieldMapping": {"status": "state", "completedDate": "finished"},
  "customStatuses": [
    {"value": "todo", "isCompleted": false},
    {"value": "doing", "isCompleted": false},
    {"value": "shipped", "isCompleted": true}
  ],
  "defaultTaskStatus": "todo",
  "activeStatus": "doing",
  "taskIdentificationMethod": "property",
  "taskPropertyName": "type",
  "taskPropertyValue": "task"
}
```

`activeStatus` is a toolkit setting for claiming work; set it to an unfinished status
distinct from the default. Supported optional settings also include `taskTag`,
`customPriorities`, `defaultTaskPriority` and `storeTitleInFilename`. Mapping keys may use
the plugin's camelCase role names or supported canonical snake_case aliases. Invalid
configuration fails explicitly; it never silently falls back to another collection.

The toolkit reads this local JSON file or an explicitly supplied library `Config`, then
uses built-in defaults for missing fields. It does not discover or modify `.obsidian`
settings elsewhere. The default title source is frontmatter with filename fallback.
With `storeTitleInFilename: true`, filename titles are authoritative; metadata/body edits
still work, while title changes requiring reference-aware renaming are refused explicitly.

## Python library

Add `.local/bin/tasknotes-toolkit` to your Python import path, or run with `PYTHONPATH`
pointing there. No installation step is needed:

```python
from tasknotes_toolkit import TaskStore

store = TaskStore("/path/to/tasks")
task = store.create(
    "Keep sessions during retries",
    "Keep the user's session active during a transient request retry.\n\n"
    "Verify that a retry succeeds and that an expired session still requires sign-in.",
    projects=["[[Customer Portal]]"],
    priority="high",
)
task = store.start(task.id, claimed_by="run-123", expected_revision=task.revision)
task = store.add_note(task.id, "The regression reproduces the failure.", claimed_by="run-123")
# Implement and verify the requested behavior before recording completion.
task = store.complete(task.id, note="The new regression and existing session tests pass.", claimed_by="run-123")
print(task.to_dict())
```

The public API includes `create`, `get`, `list`, `ready`, `edit`, `start`, `complete`,
`reopen`, `release`, `archive`, `add_note`, `delete` and `validate`. `Task` exposes `id`, `path`,
`revision`, `fields`, `description`, `custom_fields` and `raw_markdown`. `TaskError`
contains a machine-readable `code` and optional `details`. Library mutations accept
`dry_run=True`; edit/lifecycle/delete accept `expected_revision` and optional `claimed_by`.
Use `repository`, `workingDirectory`, `workType` and `sourceRefs` as keyword metadata on
create or in the edit update dictionary. `list`/`ready` accept `repository` and `work_type`
filters; `list` also accepts `claimed_by`. `release(force=True)` requires `expected_revision`.

## Compatibility and data integrity

The storage format follows [TaskNotes core concepts](https://github.com/callumalpass/tasknotes/blob/79158a83b410340cab3cbca3b117ae221c6e9d0f/docs/core-concepts.md)
and [property types](https://github.com/callumalpass/tasknotes/blob/79158a83b410340cab3cbca3b117ae221c6e9d0f/docs/settings/property-types-reference.md).
Operation and temporal rules were checked against
[tasknotes-spec 0.3.0](https://github.com/callumalpass/tasknotes-spec/tree/10e7e09e7e2377ede37bcbdc0f58ca43295d57a2).
This is a compatible common-field toolkit, not a claim of full profile conformance.

Supported YAML includes plain/quoted scalars, block/flow lists, common nested objects,
literal/folded strings and quoted property names. Canonical list-object writes use JSON
flow objects, which are valid YAML. Unknown values using advanced YAML features remain
raw and unchanged. Required fields in unsupported YAML forms, ambiguous structure,
duplicate top-level keys and attempts to rewrite opaque values fail before saving.
The toolkit is deliberately not a complete YAML interpreter. It does not execute YAML
tags or constructors. Unchanged custom YAML, comments, field order, BOM/line endings
and body text are preserved by targeted field edits.

New and changed temporal values require real calendar dates or explicit-timezone ISO
datetimes. Existing identified notes without timestamps gain a creation timestamp from
their file metadata on their first edit. Recurrence/reminder/time-entry/integration fields
are retained. Series/occurrence completion, recurrence advancement, reminder delivery,
time tracking and vault-wide link rewriting are not implemented; unsafe recurring
lifecycle changes fail rather than silently changing series semantics.

Writes use a hidden advisory lock for cooperating toolkit writers and atomic per-file
publication/replacement. A revision hash protects edits following a read, and another
check detects intervening external writes before replacement. External editors do not
participate in this lock: it is not a universal filesystem transaction or protection
against a malicious concurrent filesystem actor. Paths cannot escape the collection
or traverse symlinks. Dry runs and ordinary reads write no files. Real writes create
`.tasknotes-toolkit.lock`; that file contains no task database.

JSON output has `schema_version: 1`, `ok`, `operation` and `data` on success. Errors have
`ok: false` and `error.code`/`error.message`, with optional details. Failures exit 2;
success exits 0. Task data includes full descriptions and file revisions. Human text
errors go to stderr; JSON errors remain machine-readable on stdout.

Run the tests against temporary collections:

```sh
python3 -B -m unittest discover -s .local/bin/tasknotes-toolkit/tests -v
```
