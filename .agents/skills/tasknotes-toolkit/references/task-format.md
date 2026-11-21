# Task format and compatibility

A task is one `.md` file. YAML frontmatter holds properties; the body holds the human
description, acceptance criteria, research, progress and results. It is not a checkbox-only
format, database record or JSON file disguised as Markdown.

```markdown
---
id: "9649a52b-f7b1-43b2-8fb0-5735bd6e6126"
title: "Preserve sessions during retries"
status: "open"
priority: "high"
tags:
  - "task"
projects:
  - "[[Customer Portal]]"
dateCreated: "2026-11-21T10:00:00Z"
dateModified: "2026-11-21T10:00:00Z"
---
The user must stay signed in when a transient error causes a request retry.

The current retry discards a valid session token. Preserve it while retaining the normal
expiry behavior. Verify that both a successful retry and an expired token behave correctly.
```

The first paragraph states the outcome directly. Further detail should make the work
understandable to a human who has not read the agent conversation. Keep useful existing
paragraphs when adding acceptance criteria or progress evidence.

| Semantic field | Stored value |
| --- | --- |
| id | Stable nonempty string; new tasks receive UUIDs. |
| title | Human-readable title; filename fallback on read. |
| status | Configured status; defaults include open, in-progress, done and cancelled. |
| priority | Configured priority; default is normal. |
| projects, contexts, tags | Lists of strings; projects can contain quoted wikilinks. |
| due, scheduled | Calendar date or ISO datetime with an explicit timezone. |
| dateCreated, dateModified | ISO datetimes; new writes use UTC seconds with Z. |
| completedDate | Calendar day for a completed non-recurring task. |
| timeEstimate | Nonnegative integer minutes. |
| blockedBy | List of objects containing uid and optional relationship metadata. |
| attachments | File references retained when the task is deleted. |
| repository | Optional portable Git repository URL or identifier. |
| workingDirectory | Optional repository-relative POSIX directory; `.` is its root. |
| workType | Optional bug, feature, docs, research or maintenance classification. |
| sourceRefs | Optional list of originating issue, requirement or discussion references. |
| claimedBy | Optional current session/run owner. |
| claimedAt | Optional UTC ISO claim timestamp; requires an owner. |

These coding-work fields extend the common TaskNotes properties. Omitted values are not
invented. All six can be mapped to alternate storage keys. Use create/edit flags
`--repository`, `--working-directory`, `--work-type` and repeated `--source-ref`, or generic
`--set`/`--unset`. A supplied reference list replaces that field only. The toolkit does not
fetch references or select a checkout. Resolve the local repository first; the working
directory must remain inside it.

`start --claimed-by SESSION` atomically sets ownership, timestamp and active status. Pass
the same session ID to later mutations. Other/unidentified sessions cannot change claimed
work. `next` excludes all claims, including old claims on backlog-status notes. Claims have
no automatic expiry. `list --claimed-by SESSION` supports resumption. Completing/reopening
clears ownership, and `release` returns unfinished work to the backlog. Deliberate recovery
uses `release --force --if-match CURRENT_REVISION` after inspecting the task/workspace.
Ownership coordinates cooperating agents; it does not authenticate access to local files.

Keep descriptions in the body, not a frontmatter property. Use semantic names such as
`status` even when settings map them to another storage key. Unspecified fields, custom
YAML and unrelated Markdown are preserved. Optional `.tasknotes-toolkit.json` settings
can use native TaskNotes `fieldMapping`, `customStatuses`, `defaultTaskStatus`, task
identification and priority settings. `activeStatus` names the distinct unfinished status
used to claim tasks. `config` shows the effective settings.

Task identification defaults to the `task` tag, including hierarchical tags. A configured
property identifier is supported. Ordinary project notes without a task identifier are
not offered as tasks. Completed statuses come from configuration, not an assumption that
every collection uses `done`.

`next` uses referenced tasks' completed status to resolve dependencies. Missing/ambiguous
references block work. It does not calculate dependency durations or recurrence schedules.
Recurrence, reminder, time-entry and integration metadata survive ordinary supported edits.
Unsafe recurring lifecycle operations are refused rather than inventing occurrence state.

## YAML and storage limits

Common plain/quoted scalars, lists, nested mappings and literal/folded strings are supported.
JSON flow objects inside YAML lists are valid YAML. Advanced unknown YAML values remain
raw; required fields using unsupported syntax and attempts to rewrite opaque values produce
an error. Duplicate top-level keys and ambiguous structure are refused. This is a
source-preserving standard-library subset, not a complete YAML interpreter.

The default title source is frontmatter. With filename-managed titles, the filename is
authoritative and title edits requiring reference-aware renaming are refused. Other
metadata/body edits still work without Obsidian. The toolkit does not rewrite vault links.

The format was checked against TaskNotes revision `79158a83b410340cab3cbca3b117ae221c6e9d0f`
and canonical tasknotes-spec 0.3.0 revision `10e7e09e7e2377ede37bcbdc0f58ca43295d57a2`:

- [TaskNotes core concepts](https://github.com/callumalpass/tasknotes/blob/79158a83b410340cab3cbca3b117ae221c6e9d0f/docs/core-concepts.md)
- [TaskNotes property types](https://github.com/callumalpass/tasknotes/blob/79158a83b410340cab3cbca3b117ae221c6e9d0f/docs/settings/property-types-reference.md)
- [Canonical model and mapping](https://github.com/callumalpass/tasknotes-spec/blob/10e7e09e7e2377ede37bcbdc0f58ca43295d57a2/02-model-and-mapping.md)
- [Canonical operations](https://github.com/callumalpass/tasknotes-spec/blob/10e7e09e7e2377ede37bcbdc0f58ca43295d57a2/05-operations.md)

Compatibility means the documented common-field storage and operations. It is not a claim
of complete recurrence, extended-feature or full upstream profile conformance.
