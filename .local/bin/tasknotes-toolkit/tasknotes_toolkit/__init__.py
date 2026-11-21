"""Local TaskNotes-compatible task management, using the Python standard library."""

__version__ = "0.1.0"

from .model import Config, TaskError
from .store import Task, TaskStore

__all__ = ["Config", "TaskError", "Task", "TaskStore", "__version__"]
