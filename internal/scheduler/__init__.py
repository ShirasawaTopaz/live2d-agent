"""Background scheduler for proactive Agent tasks."""

from internal.scheduler.types import Task, CronTask, WatchTask, PollingTask, TriggerSource, Event
from internal.scheduler.store import TaskStore
from internal.scheduler.notification import NotificationManager

try:
    from internal.scheduler.triggers import CronTrigger, FileWatcher, PollingTrigger
except ImportError:
    pass

try:
    from internal.scheduler.engine import SchedulerEngine
except ImportError:
    pass

__all__ = [
    "Task",
    "CronTask",
    "WatchTask",
    "PollingTask",
    "TriggerSource",
    "Event",
    "CronTrigger",
    "FileWatcher",
    "PollingTrigger",
    "SchedulerEngine",
    "TaskStore",
    "NotificationManager",
]
