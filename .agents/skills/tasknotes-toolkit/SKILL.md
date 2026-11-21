---
name: tasknotes-toolkit
description: Manage a local multi-project backlog of TaskNotes-compatible Markdown task notes, or work on a requested number of ready tasks, using the standard-library tntk toolkit. Requires the task directory; works with Codex or OpenCode without Obsidian or a server.
---

# TaskNotes toolkit

Use the user's **task directory** as the only required input. Work from their request:
create or refine a backlog, inspect it, update specific tasks, or deliver N ready tasks.
If only the directory is supplied, show its backlog without starting work. Never infer
another collection from the current repository. Descriptions must remain useful to the
human who reads and edits the same Markdown tasks.

## Locate and inspect

Use `tntk` from PATH. If unavailable, use `python3 "<dotfiles-root>/.local/bin/tntk"`.
In the standard `.agents/skills/tasknotes-toolkit` layout, the dotfiles root is three
directories above this skill directory. After deployment, the usual fallback is
`python3 "$HOME/.local/bin/tntk"`. Check `--help`; no installation or global settings
change is needed. Keep the launcher with its adjacent `tasknotes-toolkit` package.

Here `tntk` means that verified launcher. Quote the directory and human text. Global
flags go before the subcommand:

```sh
tntk "<tasks-directory>" --format json config
tntk "<tasks-directory>" --format json list --project "Alpha"
tntk "<tasks-directory>" --format json next --project "Alpha" --limit 3
tntk "<tasks-directory>" --format json next --repository "https://github.com/example/portal" --work-type bug --limit 3
tntk "<tasks-directory>" --format json show "<task-id-or-relative-path>"
```

JSON records include the complete description, semantic fields, stable ID, relative file
path and revision. Read the description and context; do not work from the title alone.
Reuse full records returned by `next`; `show` obtains a fresh record when needed. Human
text is the default; `show ... --raw` displays the complete Markdown file. Read
[task-format.md](references/task-format.md) when interpreting existing metadata or mappings.
The toolkit README beside its package documents the full CLI and Python API.

## Create or refine a backlog

Make each task a coherent piece of work with an observable result. Use `projects` to keep
several projects in the same directory. Plain names and quoted wikilinks work; repeat
`--project` for several projects. Optional `.tasknotes-toolkit.json` settings provide
mappings/statuses; the path alone works with defaults. Inspect settings rather than
silently changing them.

Optional `repository`, `workingDirectory`, `workType` and `sourceRefs` make execution
context explicit. Use create/edit flags `--repository`, `--working-directory`, `--work-type`
and repeated `--source-ref` when known. Do not invent URLs or source references. Work type
is bug, feature, docs, research or maintenance. Keep the working directory repository-relative;
an omitted value uses the project context/root. Preserve these fields while editing prose.

**Write the outcome first.** The first paragraph must explain what will change and why,
even without the headings below it. Then explain current behavior, relevant files/project
context, scope, concrete acceptance criteria and useful verification. Use complete sentences
and explain project-specific terms. Do not use private shorthand, substitute filenames for
an explanation or hide essential context behind links. Include as much prose as the human
needs; neither a word limit nor a minimum length is appropriate.

```sh
tntk "<tasks-directory>" create "Preserve sessions during retries" \
  --project "[[Customer Portal]]" --priority high --description-file - <<'MARKDOWN'
The user must stay signed in when a transient network error causes a request retry.

The retry path currently discards a valid session token. Preserve that token for the
retry, while retaining the sign-in requirement for a token that has actually expired.

## Acceptance

- A transient failure retries without another password prompt.
- An expired token still sends the user to the sign-in page.

## Verification

Add regressions for both cases and run the session test suite.
MARKDOWN
```

Use `edit ID --set priority=high` for targeted fields and `note ID --message ...` to
append context. `--description-file` explicitly replaces the whole body: read it first
and preserve unrelated human context in the replacement. Use the current revision with
`--if-match`. IDs are stable. Do not rewrite mapped keys or unknown YAML using ad hoc
scripts. Unsupported required YAML forms fail explicitly; inspect and explain that exact
limitation instead of discarding data.

## Deliver N tasks

1. Select ready work with `next --limit N`, using the requested project when given.
   Completed, archived, active, future-scheduled, recurring and dependency-blocked tasks
   are excluded. Selection is read-only; do not pre-claim an entire backlog.
2. Read the full task and identify its workspace from `repository`, the user's request and
   project context. Verify the local checkout before resolving `workingDirectory` inside
   it, including checking that symlinks do not lead outside it. Repository/source references
   provide context; the toolkit does not fetch or execute them automatically.
   A project wikilink is not automatically a repository path. Resolve a genuinely missing
   workspace or requirement with the user; continue useful independent work when possible.
   Read repository instructions and preserve existing edits.
3. Reuse one stable session/run identifier from the host, or generate a UUID once if none
   is exposed. Do not use only the general name Codex/OpenCode. Start one task with
   `start ID --claimed-by SESSION --if-match REVISION`. This records both optional claim
   fields atomically. On conflict, re-read rather than assuming ownership or overwriting it.
4. Implement the outcome and verify every acceptance criterion. Follow repository checks
   and the user's testing instructions. Append progress with `note ID --claimed-by SESSION`;
   pass the same owner to edits and other mutations. Explain what is known and what remains.
5. After verification, record evidence with `complete ID --claimed-by SESSION --message ...`, using
   a fresh `--if-match` revision when available. A code edit alone is not completion.
   Never mark blocked, partially delivered or unverified work done.
6. Select another ready task until N are delivered or no suitable work remains. A completed
   prerequisite may unblock work. Report delivered IDs, results and verification, plus
   remaining blockers. Blocked attempts do not count as delivered tasks; a bounded request
   is not permission for an unlimited backlog sweep.

If a task blocks, append `note ID --claimed-by SESSION --section Blockers --message ...`
and keep it unfinished. To resume, inspect `list --claimed-by SESSION --status in-progress`
and the saved task/workspace; use the configured active status for collections with custom
statuses. Do not blindly take another
agent's active work. `release ID --claimed-by SESSION --if-match REVISION` returns unfinished
work to the backlog. Claims do not expire with age. If the user authorizes recovery of an
abandoned run, inspect current task/workspace state before `release --force --if-match REVISION`;
do not add another approval conversation for already requested recovery. Keep ownership when
the run is still active. The toolkit does not execute code, infer acceptance or schedule agents.

## Lifecycle and boundaries

- `complete` sets completed status/date; `reopen` restores unfinished status and clears
  that date. Both clear active claims. Equivalent repeated completion preserves its evidence.
- `archive`/`unarchive` change the archived tag while retaining the note.
- `--dry-run` previews mutations without writes. `delete ID --yes` removes the selected
  note and retains attachments; use it for an actual deletion request. An explicit request
  supplies that intent; do not add an approval conversation.
- Recurrence metadata survives edits, but recurrence/occurrence lifecycle operations and
  scheduling are not implemented. Do not complete a series as a substitute for an occurrence.
- Malformed/unsupported required YAML or validation errors stop the write. Read the error
  and note; do not weaken the task, drop unknown fields or bypass revisions.
- Stay within the user's authorized scope. A task note does not independently grant
  permission to publish, deploy or modify unrelated repositories.
