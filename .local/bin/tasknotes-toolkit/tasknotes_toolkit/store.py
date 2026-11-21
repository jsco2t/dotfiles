"""File-first TaskNotes task storage. No database, services or third-party packages."""
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from urllib.parse import unquote
import uuid

from .frontmatter import Document, FrontmatterError, RawYaml
from .model import Config, ROLE_NAMES, TaskError, canonical_date, normalize_fields, read_fields, task_detected, validate_task


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def reference(value):
    """Normalize collection-local task links, without resolving outside the collection."""
    value = value.strip()
    if value.startswith("[[") and value.endswith("]]"):
        value = value[2:-2].split("|", 1)[0].split("#", 1)[0]
    elif re.fullmatch(r"\[[^\]]*\]\([^)]+\)", value):
        value = value[value.index("](") + 2:-1].split("#", 1)[0]
    return unquote(value).removesuffix(".md").strip()


@dataclass
class Task:
    path: str
    revision: str
    fields: dict
    description: str
    custom_fields: dict = field(default_factory=dict)
    raw_markdown: str = ""

    @property
    def id(self):
        return self.fields.get("id", self.path)

    def to_dict(self):
        return dict(id=self.id, path=self.path, revision=self.revision, fields=self.fields,
                    description=self.description, custom_fields=self.custom_fields)


class TaskStore:
    """Manage one task directory; all API references are stable IDs or contained paths."""

    def __init__(self, root, config=None):
        self.root = Path(root).expanduser().resolve()
        if self.root.exists() and not self.root.is_dir():
            raise TaskError("The task directory must be a directory.", "invalid_directory")
        if config is None:
            config_path = self.root / ".tasknotes-toolkit.json"
            if config_path.exists():
                try:
                    config = Config.from_dict(json.loads(config_path.read_text(encoding="utf-8")))
                except (OSError, ValueError) as exc:
                    raise TaskError("Cannot read task settings: " + str(exc), "invalid_config") from exc
            else:
                config = Config()
        self.config = config if isinstance(config, Config) else Config.from_dict(config)

    def _path(self, relative):
        raw = Path(relative)
        path = raw if raw.is_absolute() else self.root / raw
        if ".." in raw.parts or path.resolve() != path or path == self.root or self.root not in path.parents:
            raise TaskError("Task paths must stay inside the directory and cannot traverse symlinks.", "path_traversal")
        if path.suffix.lower() != ".md" or any(part.startswith(".") for part in path.relative_to(self.root).parts):
            raise TaskError("Select an ordinary .md task file, not hidden metadata.", "invalid_path")
        return path

    def _load(self, path):
        path = self._path(path)
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8")
            doc = Document.parse(text)
            if not task_detected(doc.data, self.config):
                raise TaskError("The selected Markdown note is not identified as a task.", "not_a_task")
            fields = read_fields(doc.data, self.config, path.name)
        except (OSError, UnicodeError, FrontmatterError) as exc:
            raise TaskError("Cannot read task " + str(path) + ": " + str(exc), "invalid_frontmatter") from exc
        known = set(self.config.mapping.values())
        custom = {key: (dict(raw_yaml=value.text) if isinstance(value, RawYaml) else value)
                  for key, value in doc.data.items() if key not in known}
        return Task(path.relative_to(self.root).as_posix(), hashlib.sha256(raw).hexdigest(),
                    fields, doc.body, custom, text)

    def _tasks(self):
        tasks = []
        if not self.root.exists():
            return tasks
        for directory, dirs, files in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and not (Path(directory) / d).is_symlink())
            for name in sorted(files):
                path = Path(directory) / name
                if name.startswith(".") or path.suffix.lower() != ".md" or path.is_symlink():
                    continue
                try:
                    task = self._load(path)
                except TaskError as exc:
                    if exc.code == "not_a_task":
                        continue
                    raise
                tasks.append(task)
        ids = [task.id for task in tasks]
        if len(set(ids)) != len(ids):
            raise TaskError("Task IDs are duplicated; fix the duplicate before selecting work.", "duplicate_task_id")
        return tasks

    def get(self, ref):
        if not isinstance(ref, str) or not ref.strip():
            raise TaskError("A task ID or relative Markdown path is required.", "not_found")
        raw = Path(ref)
        if raw.is_absolute() or ".." in raw.parts:
            path = self._path(ref)
            if not path.exists():
                raise TaskError("Task was not found: " + ref, "not_found")
            return self._load(path)
        candidate = self.root / ref
        if candidate.exists() or candidate.is_symlink() or ref.lower().endswith(".md"):
            path = self._path(ref)
            if path.exists():
                return self._load(path)
            raise TaskError("Task was not found: " + ref, "not_found")
        matches = [task for task in self._tasks() if task.id == ref]
        if not matches:
            normalized = reference(ref)
            matches = [task for task in self._tasks() if normalized in (reference(task.path), Path(task.path).stem)]
        if len(matches) != 1:
            raise TaskError("Task reference is missing or ambiguous: " + ref, "not_found" if not matches else "ambiguous_task")
        return matches[0]

    def list(self, project=None, status=None, include_archived=False, search=None, limit=None,
             repository=None, work_type=None, claimed_by=None):
        if limit is not None and (type(limit) is not int or limit <= 0):
            raise TaskError("Limit must be a positive integer.", "invalid_limit")
        result = []
        for task in self._tasks():
            fields = task.fields
            if not include_archived and "archived" in (fields.get("tags") or []):
                continue
            if project and reference(project) not in [reference(p) for p in fields.get("projects", [])]:
                continue
            if status and fields.get("status") != status:
                continue
            if repository is not None and fields.get("repository") != repository:
                continue
            if work_type is not None and fields.get("workType") != work_type:
                continue
            if claimed_by is not None and fields.get("claimedBy") != claimed_by:
                continue
            if search and search.casefold() not in (fields.get("title", "") + "\n" + task.description).casefold():
                continue
            result.append(task)
        result.sort(key=lambda task: (task.fields.get("title", "").casefold(), task.path))
        return result if limit is None else result[:limit]

    def ready(self, project=None, limit=1, today=None, repository=None, work_type=None):
        if type(limit) is not int or limit <= 0:
            raise TaskError("Limit must be a positive integer.", "invalid_limit")
        day = canonical_date(today or date.today().isoformat())
        tasks = self._tasks()
        allowed = []
        for task in self.list(project=project, repository=repository, work_type=work_type):
            fields = task.fields
            issues = [issue for issue in validate_task(fields, self.config) if issue["code"] != "missing_required"]
            if issues:
                raise TaskError("Cannot select malformed task " + task.path + "; inspect its validation issues.", "validation_failed", issues)
            if fields.get("status", self.config.default_status) not in (self.config.default_status, "none"):
                continue
            if fields.get("claimedBy"):
                continue
            if fields.get("recurrence") or fields.get("recurrence_parent"):
                continue
            if fields.get("scheduled") and fields["scheduled"][:10] > day:
                continue
            blocked = False
            for dependency in fields.get("blockedBy", []) or []:
                if not isinstance(dependency, dict) or not isinstance(dependency.get("uid"), str):
                    blocked = True
                    break
                uid = reference(dependency["uid"])
                targets = [other for other in tasks if uid in (other.id, reference(other.path), Path(other.path).stem)]
                if len(targets) != 1 or targets[0].fields.get("status") not in self.config.completed_statuses:
                    blocked = True
                    break
            if not blocked:
                allowed.append(task)
        weights = {value: i for i, value in enumerate(self.config.priority_values)}
        allowed.sort(key=lambda task: (-weights.get(task.fields.get("priority"), 0),
                                      task.fields.get("due") or "9999-12-31", task.path))
        return allowed[:limit]

    @contextmanager
    def _lock(self, dry_run=False):
        if dry_run:
            yield
            return
        self.root.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        try:
            import fcntl
            descriptor = os.open(self.root / ".tasknotes-toolkit.lock", flags, 0o600)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                yield
            finally:
                os.close(descriptor)
        except OSError as exc:
            raise TaskError("Task write failed: " + str(exc), "io_error") from exc

    def _write(self, path, text, old=None, dry_run=False):
        if dry_run:
            return
        path = self._path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = stat.S_IMODE(path.stat().st_mode) if old is not None else 0o600
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=".tntk-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(text.encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(mode)
            if old is None:
                os.link(temporary, path)  # Exclusive publication cannot overwrite an existing note.
            else:
                if path.read_bytes() != old.encode("utf-8"):
                    raise TaskError("The task changed while preparing the write; re-read it.", "conflict")
                os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _filename(self, title):
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title).strip(" .")
        while len(safe.encode("utf-8")) > 180:
            safe = safe[:-1]
        if not safe or safe.upper() in {"CON", "PRN", "AUX", "NUL", *("COM" + str(i) for i in range(1, 10)), *("LPT" + str(i) for i in range(1, 10))}:
            safe = "Task"
        path = self.root / (safe + ".md")
        suffix = 2
        while path.exists() or path.is_symlink():
            path = self.root / (safe + " (" + str(suffix) + ").md")
            suffix += 1
        return self._path(path)

    def _check(self, fields, path):
        issues = validate_task(fields, self.config)
        if isinstance(fields.get("blockedBy"), list):
            seen = set()
            for item in fields["blockedBy"]:
                if not isinstance(item, dict) or not isinstance(item.get("uid"), str) or not item["uid"].strip():
                    issues.append(dict(code="invalid_dependency_entry", severity="error", field="blockedBy", message="Dependencies need a nonempty uid."))
                    continue
                uid = reference(item["uid"])
                if uid in (fields.get("id"), reference(path.relative_to(self.root).as_posix())):
                    issues.append(dict(code="self_dependency", severity="error", field="blockedBy", message="A task cannot depend on itself."))
                if uid in seen:
                    issues.append(dict(code="duplicate_dependency_uid", severity="error", field="blockedBy", message="A dependency is repeated."))
                seen.add(uid)
                if item.get("reltype", "FINISHTOSTART") not in ("FINISHTOSTART", "STARTTOSTART", "FINISHTOFINISH", "STARTTOFINISH"):
                    issues.append(dict(code="invalid_dependency_reltype", severity="error", field="blockedBy", message="Unknown dependency relation."))
        if issues:
            raise TaskError("Task validation failed: " + "; ".join(issue["message"] for issue in issues), "validation_failed", issues)

    def _result(self, path, text):
        doc = Document.parse(text)
        fields = read_fields(doc.data, self.config, path.name)
        known = set(self.config.mapping.values())
        custom = {key: (dict(raw_yaml=value.text) if isinstance(value, RawYaml) else value) for key, value in doc.data.items() if key not in known}
        return Task(path.relative_to(self.root).as_posix(), hashlib.sha256(text.encode("utf-8")).hexdigest(), fields, doc.body, custom, text)

    def create(self, title, description, dry_run=False, **fields):
        if not isinstance(title, str) or not title.strip():
            raise TaskError("A clear task title is required.", "invalid_title")
        if not isinstance(description, str) or not description.strip():
            raise TaskError("A readable task description is required.", "missing_description")
        with self._lock(dry_run):
            path = self._filename(title)
            timestamp = now()
            values = dict(id=str(uuid.uuid4()), title=title.strip(), status=self.config.default_status,
                          priority=self.config.default_priority, tags=[self.config.task_tag],
                          dateCreated=timestamp, dateModified=timestamp)
            values.update(self._changes(fields))
            values = normalize_fields(values, self.config)
            if values.get("recurrence") and values.get("status") in self.config.completed_statuses:
                raise TaskError("Recurring completion needs occurrence semantics; this toolkit does not advance series.", "unsupported_recurrence")
            if values.get("status") in self.config.completed_statuses:
                values.setdefault("completedDate", date.today().isoformat())
                values.pop("claimedBy", None)
                values.pop("claimedAt", None)
            elif values.get("claimedBy") and values.get("claimedAt") is None:
                values["claimedAt"] = timestamp
            tags = values.get("tags") or []
            if not isinstance(tags, list):
                raise TaskError("Task tags must be a list.", "validation_failed")
            if not self.config.identification_property and self.config.task_tag not in tags:
                values["tags"] = tags + [self.config.task_tag]
            self._check(values, path)
            if any(task.id == values["id"] for task in self._tasks()):
                raise TaskError("A task already has this stable ID.", "duplicate_task_id")
            raw = {self.config.mapping.get(key, key): value for key, value in values.items()}
            if self.config.identification_property:
                raw.setdefault(self.config.identification_property, self.config.identification_value if self.config.identification_value is not None else True)
            text = Document.parse("").render(raw, body=description)
            candidate = self._result(path, text)
            self._check(candidate.fields, path)
            if not task_detected(Document.parse(text).data, self.config):
                raise TaskError("Creation settings do not produce the configured task identifier.", "invalid_task_identifier")
            self._write(path, text, dry_run=dry_run)
            return candidate

    def _changes(self, incoming):
        """Resolve semantic names and mapped/legacy keys before applying invariants."""
        reverse = {value: key for key, value in self.config.mapping.items()}
        updates = {}
        for name, value in incoming.items():
            role = name if name in self.config.mapping else reverse.get(name, ROLE_NAMES.get(name, name))
            if role in updates and updates[role] != value:
                raise TaskError("Conflicting values were supplied for one mapped task field.", "invalid_field")
            updates[role] = value
        return updates

    @staticmethod
    def _check_claim(task, claimed_by):
        if claimed_by is not None and (not isinstance(claimed_by, str) or not claimed_by.strip()):
            raise TaskError("The claimant must be a nonempty session/run identifier.", "invalid_claim")
        owner = task.fields.get("claimedBy")
        if owner is not None and owner != claimed_by:
            raise TaskError("Task is claimed by another or unidentified session; use its owner ID or an explicit revision-protected release.", "claim_conflict")

    def _release_updates(self, task):
        updates = dict(claimedBy=None, claimedAt=None)
        if task.fields.get("status") not in self.config.completed_statuses:
            updates.update(status=self.config.default_status, completedDate=None)
        return updates

    def edit(self, ref, updates=None, description=None, expected_revision=None, dry_run=False,
             claimed_by=None, _force_release=False):
        updates = self._changes(dict(updates or {}))
        with self._lock(dry_run):
            task = self.get(ref)
            if expected_revision is not None and expected_revision != task.revision:
                raise TaskError("The task changed since it was read; re-read before editing.", "conflict")
            release_updates = self._release_updates(task)
            if _force_release:
                if not expected_revision or updates != release_updates or description is not None:
                    raise TaskError("Forced release needs the current revision and can only clear the claim and reopen the task.", "invalid_release")
            else:
                self._check_claim(task, claimed_by)
            if "id" in updates and updates["id"] != task.fields.get("id"):
                raise TaskError("Task IDs are stable and cannot be rewritten.", "immutable_id")
            if description is not None and (not isinstance(description, str) or not description.strip()):
                raise TaskError("A replacement description cannot be blank.", "missing_description")
            changes = normalize_fields(updates, self.config)
            if "claimedBy" in changes:
                if changes["claimedBy"] is None:
                    changes["claimedAt"] = None
                elif changes.get("claimedAt") is None and (
                    changes["claimedBy"] != task.fields.get("claimedBy") or not task.fields.get("claimedAt")
                ):
                    changes["claimedAt"] = now()
            if "status" in changes:
                if task.fields.get("recurrence") and changes["status"] in self.config.completed_statuses:
                    raise TaskError("Complete an occurrence in TaskNotes; this toolkit will not mark a recurring series done.", "unsupported_recurrence")
                if changes["status"] in self.config.completed_statuses:
                    changes.setdefault("completedDate", task.fields.get("completedDate") or date.today().isoformat())
                elif changes["status"] is not None:
                    changes.setdefault("completedDate", None)
                if changes["status"] != self.config.active_status:
                    changes.update(claimedBy=None, claimedAt=None)
            new_fields = dict(task.fields)
            for key, value in changes.items():
                if value is None:
                    new_fields.pop(key, None)
                else:
                    new_fields[key] = value
            path = self._path(task.path)
            if self.config.title_storage == "filename" and "title" in changes and changes["title"] != task.fields["title"]:
                raise TaskError("Filename-managed titles require a reference-aware rename outside this toolkit; other fields remain editable.", "unsupported_title_rename")
            # Legacy notes without timestamps can enter the canonical schema on their first edit.
            if not new_fields.get("dateCreated"):
                new_fields["dateCreated"] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                changes["dateCreated"] = new_fields["dateCreated"]
            if new_fields == task.fields and (description is None or description == task.description):
                return task
            changes["dateModified"] = now()
            new_fields["dateModified"] = changes["dateModified"]
            self._check(new_fields, path)
            raw_changes = {self.config.mapping.get(key, key): value for key, value in changes.items()}
            try:
                text = Document.parse(task.raw_markdown).render(raw_changes, body=description)
                candidate = self._result(path, text)
            except FrontmatterError as exc:
                raise TaskError(str(exc), "unsupported_yaml") from exc
            if not task_detected(Document.parse(text).data, self.config):
                raise TaskError("The edit would remove this note's task identifier.", "invalid_task_identifier")
            self._check(candidate.fields, path)
            self._write(path, text, old=task.raw_markdown, dry_run=dry_run)
            return candidate

    def complete(self, ref, on=None, note=None, **options):
        task = self.get(ref)
        if task.fields.get("recurrence") or task.fields.get("recurrence_parent"):
            raise TaskError("Recurring tasks and materialized occurrences need TaskNotes occurrence operations.", "unsupported_recurrence")
        day = canonical_date(on or date.today().isoformat())
        status = task.fields.get("status")
        updates = dict(status=status if status in self.config.completed_statuses else self.config.completed_statuses[0],
                       completedDate=task.fields.get("completedDate") or day)
        repeated_note = note and status in self.config.completed_statuses and task.description.rstrip().endswith("## Outcome\n\n" + note.strip())
        description = self._note(task.description, note, "Outcome") if note and not repeated_note else None
        if options.get("expected_revision") is None:
            options["expected_revision"] = task.revision
        return self.edit(ref, updates, description=description, **options)

    def reopen(self, ref, **options):
        task = self.get(ref)
        if task.fields.get("recurrence") or task.fields.get("recurrence_parent"):
            raise TaskError("Recurring instances require occurrence-specific reopening.", "unsupported_recurrence")
        if options.get("expected_revision") is None:
            options["expected_revision"] = task.revision
        return self.edit(ref, dict(status=self.config.default_status, completedDate=None), **options)

    def start(self, ref, **options):
        task = self.get(ref)
        if self.config.active_status == self.config.default_status:
            raise TaskError("Configure activeStatus to a distinct unfinished status before claiming tasks.", "invalid_config")
        if task.fields.get("status") not in (self.config.default_status, "none", self.config.active_status):
            raise TaskError("Only unfinished backlog tasks can be started.", "invalid_transition")
        if options.get("expected_revision") is None:
            options["expected_revision"] = task.revision
        updates = dict(status=self.config.active_status)
        owner = options.get("claimed_by")
        if owner is not None:
            updates.update(claimedBy=owner, claimedAt=task.fields.get("claimedAt") or now())
        return self.edit(ref, updates, **options)

    def release(self, ref, claimed_by=None, expected_revision=None, dry_run=False, force=False):
        """Return work to the backlog; a stale claim never expires on its own."""
        if force and not expected_revision:
            raise TaskError("Force release requires --if-match with the revision you inspected.", "revision_required")
        task = self.get(ref)
        return self.edit(ref, self._release_updates(task),
                         claimed_by=claimed_by, expected_revision=expected_revision or task.revision,
                         dry_run=dry_run, _force_release=force)

    def archive(self, ref, archived=True, **options):
        task = self.get(ref)
        tags = list(task.fields.get("tags") or [])
        tags = [tag for tag in tags if tag != "archived"]
        if archived:
            tags.append("archived")
        if options.get("expected_revision") is None:
            options["expected_revision"] = task.revision
        return self.edit(ref, dict(tags=tags), **options)

    @staticmethod
    def _note(body, text, section):
        if not isinstance(text, str) or not text.strip():
            raise TaskError("A readable progress or result note is required.", "missing_description")
        if section not in ("Progress", "Outcome", "Blockers"):
            raise TaskError("Note section must be Progress, Outcome or Blockers.", "invalid_section")
        return body.rstrip() + "\n\n## " + section + "\n\n" + text.strip() + "\n"

    def add_note(self, ref, text, section="Progress", **options):
        task = self.get(ref)
        if options.get("expected_revision") is None:
            options["expected_revision"] = task.revision
        return self.edit(ref, description=self._note(task.description, text, section), **options)

    def delete(self, ref, expected_revision=None, dry_run=False, force=False, claimed_by=None):
        with self._lock(dry_run):
            task = self.get(ref)
            if expected_revision is not None and expected_revision != task.revision:
                raise TaskError("The task changed since it was read; deletion was refused.", "conflict")
            self._check_claim(task, claimed_by)
            if not force:
                for other in self._tasks():
                    if other.path != task.path and any(
                        isinstance(dep, dict) and reference(dep.get("uid", "")) in (task.id, reference(task.path), Path(task.path).stem)
                        for dep in other.fields.get("blockedBy", []) or []
                    ):
                        raise TaskError("Another task depends on this task; use force only for deliberate deletion.", "referenced_task")
            if not dry_run:
                path = self._path(task.path)
                if hashlib.sha256(path.read_bytes()).hexdigest() != task.revision:
                    raise TaskError("Task changed before deletion.", "conflict")
                path.unlink()
            return dict(id=task.id, path=task.path, deleted=not dry_run, dry_run=dry_run)

    def validate(self, ref=None):
        tasks = [self.get(ref)] if ref else self._tasks()
        return [dict(path=task.path, issues=validate_task(task.fields, self.config)) for task in tasks]
