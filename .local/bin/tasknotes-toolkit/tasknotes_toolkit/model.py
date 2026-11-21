"""TaskNotes' common field types and configurable canonical write keys."""
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
import re

from .frontmatter import RawYaml


class TaskError(ValueError):
    def __init__(self, message, code="invalid_task", details=None):
        super().__init__(message)
        self.code, self.details = code, details


NAMES = (
    "id", "title", "status", "priority", "due", "scheduled", "tags", "contexts",
    "projects", "attachments", "timeEstimate", "completedDate", "dateCreated",
    "dateModified", "recurrence", "recurrence_anchor", "complete_instances",
    "skipped_instances", "recurrence_parent", "occurrence_date", "blockedBy",
    "timeEntries", "reminders",
    "repository", "workingDirectory", "workType", "sourceRefs", "claimedBy", "claimedAt",
)
ALIASES = {
    "completedDate": ("completed_date",), "dateCreated": ("date_created",),
    "dateModified": ("date_modified",), "timeEstimate": ("time_estimate",),
    "blockedBy": ("blocked_by",), "timeEntries": ("time_entries",),
    "recurrence_anchor": ("recurrenceAnchor",),
    "complete_instances": ("completeInstances",), "skipped_instances": ("skippedInstances",),
    "recurrence_parent": ("recurrenceParent",), "occurrence_date": ("occurrenceDate",),
}
ROLE_NAMES = {alias: name for name, aliases in ALIASES.items() for alias in aliases}
DATE_FIELDS = {"completedDate", "occurrence_date"}
DATETIME_FIELDS = {"dateCreated", "dateModified", "claimedAt"}
TEMPORAL_FIELDS = {"due", "scheduled"} | DATE_FIELDS | DATETIME_FIELDS
LIST_FIELDS = {"tags", "contexts", "projects", "attachments", "complete_instances", "skipped_instances", "sourceRefs"}
OBJECT_LIST_FIELDS = {"blockedBy", "timeEntries", "reminders"}
WORK_TYPES = ("bug", "feature", "docs", "research", "maintenance")


@dataclass
class Config:
    mapping: dict = field(default_factory=lambda: {name: name for name in NAMES})
    status_values: tuple = ("none", "open", "in-progress", "done", "cancelled")
    completed_statuses: tuple = ("done",)
    default_status: str = "open"
    active_status: str = "in-progress"
    priority_values: tuple = ("none", "low", "normal", "high")
    default_priority: str = "normal"
    task_tag: str = "task"
    identification_property: str = ""
    identification_value: object = None
    title_storage: str = "frontmatter"

    @classmethod
    def from_dict(cls, settings):
        if not isinstance(settings, dict):
            raise TaskError("Task settings must be a JSON object.", "invalid_config")
        config = cls()
        mapping = settings.get("fieldMapping", settings.get("mapping", {}))
        if not isinstance(mapping, dict):
            raise TaskError("Field mapping must be an object.", "invalid_config")
        for role, key in mapping.items():
            role = ROLE_NAMES.get(role, role)
            if role in config.mapping:
                if not isinstance(key, str) or not key.strip() or "\n" in key or "\r" in key:
                    raise TaskError("Mapped field names must be nonempty single-line strings.", "invalid_config")
                config.mapping[role] = key
        if len(set(config.mapping.values())) != len(config.mapping):
            raise TaskError("Two task roles cannot write the same field.", "invalid_config")
        statuses = settings.get("customStatuses")
        if statuses is not None:
            if not isinstance(statuses, list) or not statuses or any(
                not isinstance(item, dict) or not isinstance(item.get("value"), str) or not item["value"].strip()
                for item in statuses
            ):
                raise TaskError("customStatuses must contain nonempty status values.", "invalid_config")
            config.status_values = tuple(item["value"] for item in statuses)
            config.completed_statuses = tuple(item["value"] for item in statuses if item.get("isCompleted") is True)
            if len(set(config.status_values)) != len(config.status_values) or not config.completed_statuses:
                raise TaskError("Statuses must be unique and include a completed status.", "invalid_config")
        config.default_status = settings.get("defaultTaskStatus", config.default_status)
        config.active_status = settings.get("activeStatus", "in-progress" if "in-progress" in config.status_values else config.default_status)
        if config.default_status not in config.status_values or config.default_status in config.completed_statuses:
            raise TaskError("The default status must name a configured unfinished status.", "invalid_config")
        if config.active_status not in config.status_values or config.active_status in config.completed_statuses:
            raise TaskError("The active status must be a configured unfinished status.", "invalid_config")
        priorities = settings.get("customPriorities")
        if priorities is not None:
            if not isinstance(priorities, list) or not priorities or any(
                not isinstance(p, dict) or not isinstance(p.get("value"), str) or not p["value"] for p in priorities
            ):
                raise TaskError("customPriorities must contain named values.", "invalid_config")
            config.priority_values = tuple(p["value"] for p in priorities)
        config.default_priority = settings.get("defaultTaskPriority", config.default_priority)
        if config.default_priority not in config.priority_values:
            raise TaskError("The default priority must be a configured value.", "invalid_config")
        config.task_tag = settings.get("taskTag", config.task_tag)
        if not isinstance(config.task_tag, str) or not config.task_tag.strip():
            raise TaskError("taskTag must be a nonempty string.", "invalid_config")
        if settings.get("taskIdentificationMethod") == "property":
            config.identification_property = settings.get("taskPropertyName", "")
            if not isinstance(config.identification_property, str) or not config.identification_property:
                raise TaskError("Property task identification needs taskPropertyName.", "invalid_config")
            value = settings.get("taskPropertyValue", "")
            config.identification_value = None if value == "" else (value.lower() == "true" if isinstance(value, str) and value.lower() in ("true", "false") else value)
        elif settings.get("taskIdentificationMethod", "tag") != "tag":
            raise TaskError("Task identification must use tag or property.", "invalid_config")
        if settings.get("storeTitleInFilename") is True:
            config.title_storage = "filename"
        return config


def task_detected(data, config):
    if config.identification_property:
        key = config.identification_property
        if key not in data:
            return False
        value = data[key]
        wanted = config.identification_value
        return wanted is None or (wanted in value if isinstance(value, list) else value == wanted)
    tags = data.get("tags", [])
    if isinstance(tags, RawYaml):
        raise TaskError("Cannot interpret task tags in this YAML syntax.", "unsupported_yaml")
    if isinstance(tags, str):
        tags = [tags]
    return isinstance(tags, list) and any(
        isinstance(tag, str) and (tag.lstrip("#") == config.task_tag.lstrip("#") or tag.lstrip("#").startswith(config.task_tag.lstrip("#") + "/"))
        for tag in tags
    )


def read_fields(data, config, filename):
    fields = {}
    for name, key in config.mapping.items():
        for candidate in (key,) + ALIASES.get(name, ()):
            if candidate in data:
                value = data[candidate]
                if isinstance(value, RawYaml):
                    raise TaskError("Cannot interpret task field '" + candidate + "' in this YAML syntax.", "unsupported_yaml")
                fields[name] = value
                break
    filename_title = Path(filename).stem
    if config.title_storage == "filename" and filename_title:
        fields["title"] = filename_title
    elif not isinstance(fields.get("title"), str) or not fields["title"].strip():
        fields["title"] = filename_title
    if isinstance(fields.get("status"), bool):
        fields["status"] = str(fields["status"]).lower()
    return fields


def canonical_datetime(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value
    ):
        raise TaskError("Use an ISO datetime with seconds and an explicit timezone.", "invalid_datetime_value")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError) as exc:
        raise TaskError("Invalid calendar datetime: " + value, "invalid_datetime_value") from exc


def canonical_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise TaskError("Use a calendar date in YYYY-MM-DD form.", "invalid_date_value")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise TaskError("Invalid calendar date: " + value, "invalid_date_value") from exc


def relative_directory(value):
    if (not isinstance(value, str) or not value.strip() or value.startswith("~")
            or "\\" in value or "://" in value or re.match(r"^[A-Za-z]:", value)
            or any(ord(char) < 32 for char in value)):
        raise TaskError("workingDirectory must be a repository-relative POSIX directory, or '.'.", "invalid_working_directory")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise TaskError("workingDirectory cannot be absolute or traverse a parent directory.", "invalid_working_directory")
    return path.as_posix()


def normalize_fields(fields, config):
    result = dict(fields)
    for name, value in fields.items():
        if value is None:
            continue
        if name in DATE_FIELDS:
            result[name] = canonical_date(value)
        elif name in DATETIME_FIELDS:
            result[name] = canonical_datetime(value)
        elif name in ("due", "scheduled"):
            result[name] = canonical_date(value) if isinstance(value, str) and "T" not in value else canonical_datetime(value)
        elif name == "status" and isinstance(value, bool):
            result[name] = str(value).lower()
        elif name == "workingDirectory":
            result[name] = relative_directory(value)
    return result


def validate_task(fields, config):
    issues = []

    def issue(code, message, name):
        issues.append(dict(code=code, severity="error", message=message, field=name))

    for name in ("title", "status", "dateCreated", "dateModified"):
        if not fields.get(name):
            issue("missing_required", "Task requires " + name + ".", name)
    if fields.get("status") in config.completed_statuses and not fields.get("recurrence") and not fields.get("completedDate"):
        issue("missing_required", "Completed non-recurring tasks require completedDate.", "completedDate")
    for name in ("title", "id", "status", "priority", "recurrence", "recurrence_anchor", "recurrence_parent"):
        if name in fields and fields[name] is not None and (not isinstance(fields[name], str) or not fields[name].strip()):
            issue("invalid_type", name + " must be a nonempty string.", name)
    for name in ("repository", "workType", "claimedBy"):
        value = fields.get(name)
        if value is not None and (not isinstance(value, str) or not value.strip()
                                  or any(ord(char) < 32 for char in value)):
            issue("invalid_type", name + " must be a nonempty, single-line string.", name)
    if fields.get("workType") is not None and fields["workType"] not in WORK_TYPES:
        issue("invalid_enum_value", "workType must be bug, feature, docs, research or maintenance.", "workType")
    if fields.get("workingDirectory") is not None:
        try:
            relative_directory(fields["workingDirectory"])
        except TaskError as exc:
            issue(exc.code, str(exc), "workingDirectory")
    if fields.get("claimedAt") is not None and not fields.get("claimedBy"):
        issue("invalid_claim", "claimedAt requires a claimedBy owner.", "claimedAt")
    if fields.get("status") is not None and fields["status"] not in config.status_values:
        issue("invalid_enum_value", "Status is not configured for this task collection.", "status")
    if fields.get("priority") is not None and fields["priority"] not in config.priority_values:
        issue("invalid_enum_value", "Priority is not configured for this task collection.", "priority")
    for name in LIST_FIELDS:
        if name in fields and fields[name] is not None and (
            not isinstance(fields[name], list) or any(not isinstance(v, str) or not v.strip() for v in fields[name])
        ):
            issue("invalid_type", name + " must be a list of nonempty strings.", name)
    for name in OBJECT_LIST_FIELDS:
        if name in fields and fields[name] is not None and (
            not isinstance(fields[name], list) or any(not isinstance(v, dict) for v in fields[name])
        ):
            issue("invalid_type", name + " must be a list of objects.", name)
    if fields.get("timeEstimate") is not None and (type(fields["timeEstimate"]) is not int or fields["timeEstimate"] < 0):
        issue("invalid_type", "timeEstimate must be a nonnegative integer number of minutes.", "timeEstimate")
    for name in TEMPORAL_FIELDS:
        if fields.get(name) is not None:
            try:
                normalize_fields({name: fields[name]}, config)
            except TaskError as exc:
                issue(exc.code, str(exc), name)
    for name in ("complete_instances", "skipped_instances"):
        if isinstance(fields.get(name), list):
            for value in fields[name]:
                try:
                    canonical_date(value)
                except TaskError as exc:
                    issue(exc.code, str(exc), name)
    if (isinstance(fields.get("complete_instances"), list) and isinstance(fields.get("skipped_instances"), list)
            and all(isinstance(v, str) for v in fields["complete_instances"] + fields["skipped_instances"])):
        if set(fields["complete_instances"]) & set(fields["skipped_instances"]):
            issue("instance_state_overlap", "An occurrence cannot be both completed and skipped.", "complete_instances")
    try:
        created = canonical_datetime(fields["dateCreated"])
        modified = canonical_datetime(fields["dateModified"])
        if modified < created:
            issue("invalid_time_range", "dateModified cannot precede dateCreated.", "dateModified")
    except (KeyError, TaskError):
        pass
    return issues
