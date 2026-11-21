"""Human-readable text and versioned JSON over one directory-first CLI."""
import argparse
import json
from pathlib import Path
import sys

from .frontmatter import FrontmatterError
from .model import TaskError, WORK_TYPES
from .store import Task, TaskStore


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise TaskError(message, "usage")


def parser():
    root = Parser(prog="tntk", description="Manage local TaskNotes Markdown tasks; Python standard library only.")
    root.add_argument("directory", help="Directory containing task Markdown notes.")
    root.add_argument("--format", choices=("text", "json"), default="text", help="Human text (default) or versioned agent JSON.")
    root.add_argument("--dry-run", action="store_true", help="Validate and preview a mutation without writing anything.")
    commands = root.add_subparsers(dest="command", required=True, parser_class=Parser)
    for name in ("list", "next"):
        command = commands.add_parser(name, help="List tasks." if name == "list" else "Select ready, unclaimed tasks without changing them.")
        command.add_argument("--project")
        command.add_argument("--repository", help="Match an exact repository identifier.")
        command.add_argument("--work-type", choices=WORK_TYPES)
        command.add_argument("--limit", type=int, default=1 if name == "next" else None)
        if name == "list":
            command.add_argument("--status")
            command.add_argument("--search")
            command.add_argument("--include-archived", action="store_true")
            command.add_argument("--claimed-by", help="Show tasks owned by this session/run.")
    create = commands.add_parser("create", help="Create a task with a readable Markdown description.")
    create.add_argument("title")
    description_options(create, required=True)
    create.add_argument("--project", action="append")
    create.add_argument("--tag", action="append")
    create.add_argument("--context", action="append")
    create.add_argument("--priority")
    create.add_argument("--due")
    create.add_argument("--scheduled")
    create.add_argument("--estimate", type=int)
    create.add_argument("--set", action="append", default=[], metavar="FIELD=JSON")
    metadata_options(create)
    for name in ("show", "edit", "start", "complete", "reopen", "archive", "unarchive", "delete", "note", "release"):
        command = commands.add_parser(name)
        command.add_argument("task", help="Stable task ID or relative .md path.")
        if name == "show":
            command.add_argument("--raw", action="store_true", help="Emit the complete original Markdown (text format only).")
        else:
            command.add_argument("--if-match", help="Require the exact revision returned by show/list/next.")
            command.add_argument("--claimed-by", help="Current session/run identifier; start records it as the owner.")
        if name == "edit":
            command.add_argument("--set", action="append", default=[], metavar="FIELD=JSON")
            command.add_argument("--unset", action="append", default=[], metavar="FIELD")
            description_options(command)
            metadata_options(command)
        if name == "complete":
            command.add_argument("--on", help="Completion day, YYYY-MM-DD; defaults to the local calendar day.")
            command.add_argument("--message", help="Append human-readable verification/result evidence.")
        if name == "delete":
            command.add_argument("--yes", action="store_true", help="Explicitly remove this task file; attachments are retained.")
            command.add_argument("--force", action="store_true", help="Delete even if another task depends on it.")
        if name == "release":
            command.add_argument("--force", action="store_true", help="Explicitly recover a claim; requires the inspected --if-match revision.")
        if name == "note":
            command.add_argument("--message", required=True)
            command.add_argument("--section", choices=("Progress", "Outcome", "Blockers"), default="Progress")
    validate = commands.add_parser("validate", help="Report schema issues without changing any files.")
    validate.add_argument("task", nargs="?")
    commands.add_parser("config", help="Show effective field mapping and task lifecycle settings.")
    return root


def metadata_options(command):
    command.add_argument("--repository", help="Portable Git repository URL or identifier; no checkout is changed.")
    command.add_argument("--working-directory", help="Repository-relative directory, or '.' for the root.")
    command.add_argument("--work-type", choices=WORK_TYPES)
    command.add_argument("--source-ref", action="append", help="Issue, requirement or discussion reference; repeat for several.")


def metadata_values(args):
    return {name: getattr(args, option) for option, name in (
        ("repository", "repository"), ("working_directory", "workingDirectory"),
        ("work_type", "workType"), ("source_ref", "sourceRefs")) if getattr(args, option, None) is not None}


def description_options(command, required=False):
    group = command.add_mutually_exclusive_group(required=required)
    group.add_argument("--description", help="Full readable Markdown description.")
    group.add_argument("--description-file", help="UTF-8 Markdown file; '-' reads standard input.")


def description(args):
    if getattr(args, "description_file", None):
        if args.description_file == "-":
            return sys.stdin.read()
        return Path(args.description_file).read_text(encoding="utf-8")
    return getattr(args, "description", None)


def fields(items):
    result = {}
    for item in items:
        key, separator, value = item.partition("=")
        if not separator or not key.strip():
            raise TaskError("--set requires FIELD=JSON, for example priority=\"high\".", "usage")
        try:
            result[key.strip()] = json.loads(value)
        except ValueError:
            # A plain string is convenient for humans; arrays/objects still need valid JSON.
            if value.startswith(("[", "{", '"')):
                raise TaskError("Structured --set values must be valid JSON.", "usage")
            result[key.strip()] = value
    return result


def serializable(value):
    if isinstance(value, Task):
        return value.to_dict()
    if isinstance(value, list):
        return [serializable(item) for item in value]
    return value


def text_output(data):
    if isinstance(data, Task):
        lines = [data.fields.get("title", data.path), "ID: " + data.id, "File: " + data.path,
                 "Status: " + str(data.fields.get("status", "open")),
                 "Revision: " + data.revision]
        for name in ("priority", "projects", "contexts", "due", "scheduled", "completedDate", "repository",
                     "workingDirectory", "workType", "sourceRefs", "claimedBy", "claimedAt"):
            if name in data.fields:
                lines.append(name + ": " + (", ".join(data.fields[name]) if isinstance(data.fields[name], list) else str(data.fields[name])))
        return "\n".join(lines) + "\n\n" + data.description
    if isinstance(data, list) and all(isinstance(item, Task) for item in data):
        if not data:
            return "No matching tasks."
        return "\n".join(
            str(i) + ". " + task.fields.get("title", task.path) + " [" + str(task.fields.get("status", "open")) + "]\n"
            + "   " + task.id + " · " + task.path
            for i, task in enumerate(data, 1)
        )
    return json.dumps(serializable(data), indent=2, ensure_ascii=False)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    output_format = "json" if any(
        arg == "--format=json" or arg == "--format" and i + 1 < len(argv) and argv[i + 1] == "json"
        for i, arg in enumerate(argv)
    ) else "text"
    operation = None
    try:
        args = parser().parse_args(argv)
        output_format, operation = args.format, args.command
        store = TaskStore(args.directory)
        options = dict(expected_revision=getattr(args, "if_match", None), dry_run=args.dry_run,
                       claimed_by=getattr(args, "claimed_by", None))
        if operation == "create":
            values = fields(args.set)
            if {"title", "description", "dry_run"} & values.keys():
                raise TaskError("Use the title/description arguments and global preview flag, not reserved --set fields.", "usage")
            for option, name in (("project", "projects"), ("tag", "tags"), ("context", "contexts"),
                                 ("priority", "priority"), ("due", "due"), ("scheduled", "scheduled"), ("estimate", "timeEstimate")):
                value = getattr(args, option)
                if value is not None:
                    values[name] = value
            values.update(metadata_values(args))
            data = store.create(args.title, description(args), dry_run=args.dry_run, **values)
        elif operation == "show":
            data = store.get(args.task)
            if args.raw:
                if args.format != "text":
                    raise TaskError("--raw is available only with text output; JSON includes the full description.", "usage")
                print(data.raw_markdown, end="")
                return 0
        elif operation == "list":
            data = store.list(project=args.project, status=args.status, search=args.search,
                              include_archived=args.include_archived, limit=args.limit,
                              repository=args.repository, work_type=args.work_type, claimed_by=args.claimed_by)
        elif operation == "next":
            data = store.ready(project=args.project, limit=args.limit, repository=args.repository, work_type=args.work_type)
        elif operation == "edit":
            updates = fields(args.set)
            updates.update(metadata_values(args))
            updates.update({name: None for name in args.unset})
            body = description(args)
            if not updates and body is None:
                raise TaskError("Provide --set, --unset or a replacement description.", "usage")
            data = store.edit(args.task, updates, description=body, **options)
        elif operation in ("start", "reopen"):
            data = getattr(store, operation)(args.task, **options)
        elif operation == "complete":
            data = store.complete(args.task, on=args.on, note=args.message, **options)
        elif operation in ("archive", "unarchive"):
            data = store.archive(args.task, archived=operation == "archive", **options)
        elif operation == "note":
            data = store.add_note(args.task, args.message, section=args.section, **options)
        elif operation == "delete":
            if not args.yes and not args.dry_run:
                raise TaskError("Deletion removes the task file. Use --dry-run to preview or --yes for an intentional delete.", "confirmation_required")
            data = store.delete(args.task, force=args.force, **options)
        elif operation == "release":
            data = store.release(args.task, force=args.force, **options)
        elif operation == "validate":
            data = store.validate(args.task)
            if any(item["issues"] for item in data):
                raise TaskError("Task schema validation found issues.", "validation_failed", data)
        elif operation == "config":
            data = dict(mapping=store.config.mapping, status_values=store.config.status_values,
                        completed_statuses=store.config.completed_statuses, default_status=store.config.default_status,
                        active_status=store.config.active_status, task_tag=store.config.task_tag,
                        title_storage=store.config.title_storage, validation_mode="strict",
                        config_file=str(store.root / ".tasknotes-toolkit.json"),
                        work_types=WORK_TYPES,
                        optional_fields=["repository", "workingDirectory", "workType", "sourceRefs", "claimedBy", "claimedAt"],
                        claims="Optional session ownership; no automatic expiry. Release with owner identity, or force plus current revision.",
                        recurrence_operations="not supported; fields are preserved")
        else:
            raise TaskError("Unknown command.", "usage")
        if output_format == "json":
            print(json.dumps(dict(schema_version=1, ok=True, operation=operation, dry_run=args.dry_run,
                                  data=serializable(data)), ensure_ascii=False))
        else:
            print(("Preview only; nothing was written.\n\n" if args.dry_run else "") + text_output(data))
        return 0
    except (TaskError, OSError, UnicodeError, FrontmatterError) as exc:
        code = exc.code if isinstance(exc, TaskError) else "io_error"
        error = dict(code=code, message=str(exc))
        if isinstance(exc, TaskError) and exc.details is not None:
            error["details"] = exc.details
        if output_format == "json":
            print(json.dumps(dict(schema_version=1, ok=False, operation=operation, error=error), ensure_ascii=False))
        else:
            print("Error: " + str(exc), file=sys.stderr)
        return 2
