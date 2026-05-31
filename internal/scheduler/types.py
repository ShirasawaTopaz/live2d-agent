"""Type definitions for the scheduler system."""

import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    """A trigger event payload."""
    source: str          # "cron", "file_watch", "polling", etc.
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)


class TriggerSource(ABC):
    """Pluggable event source."""

    @abstractmethod
    async def start(self, callback: Callable[[Event], Any]) -> None:
        """Start listening. Calls callback(event) for each triggered event."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop listening and clean up resources."""
        ...

    def describe(self) -> str:
        return self.__class__.__name__


@dataclass
class Task:
    """Base scheduled task."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    prompt: str = ""
    created_by: str = "user"
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    last_fired_at: float | None = None

    def describe_trigger(self) -> str:
        return "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "prompt": self.prompt,
            "created_by": self.created_by,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "last_fired_at": self.last_fired_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        return cls(
            task_id=data["task_id"],
            prompt=data.get("prompt", ""),
            created_by=data.get("created_by", "user"),
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", time.time()),
            last_fired_at=data.get("last_fired_at"),
        )


@dataclass
class CronTask(Task):
    """Task triggered by a cron expression or one-shot timestamp."""
    cron_expr: str | None = None
    run_at: float | None = None

    def describe_trigger(self) -> str:
        if self.run_at is not None:
            return f"at {time.strftime('%Y-%m-%d %H:%M', time.localtime(self.run_at))}"
        return f"cron({self.cron_expr})"

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["type"] = "cron"
        d["cron_expr"] = self.cron_expr
        d["run_at"] = self.run_at
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CronTask":
        return cls(
            task_id=data["task_id"], prompt=data.get("prompt", ""),
            created_by=data.get("created_by", "user"),
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", time.time()),
            last_fired_at=data.get("last_fired_at"),
            cron_expr=data.get("cron_expr"),
            run_at=data.get("run_at"),
        )


@dataclass
class WatchTask(Task):
    """Task triggered by an external event source."""
    trigger_source_name: str = ""
    trigger_config: dict[str, Any] = field(default_factory=dict)
    filter_rules: dict[str, Any] = field(default_factory=dict)

    def describe_trigger(self) -> str:
        return f"watch({self.trigger_source_name}: {self.trigger_config})"

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["type"] = "watch"
        d["trigger_source_name"] = self.trigger_source_name
        d["trigger_config"] = self.trigger_config
        d["filter_rules"] = self.filter_rules
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WatchTask":
        return cls(
            task_id=data["task_id"], prompt=data.get("prompt", ""),
            created_by=data.get("created_by", "user"),
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", time.time()),
            last_fired_at=data.get("last_fired_at"),
            trigger_source_name=data.get("trigger_source_name", ""),
            trigger_config=data.get("trigger_config", {}),
            filter_rules=data.get("filter_rules", {}),
        )


@dataclass
class PollingTask(Task):
    """Task triggered at a fixed interval."""
    interval: float = 3600.0
    stop_condition: str | None = None

    def describe_trigger(self) -> str:
        return f"every {self.interval}s"

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["type"] = "polling"
        d["interval"] = self.interval
        d["stop_condition"] = self.stop_condition
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PollingTask":
        return cls(
            task_id=data["task_id"], prompt=data.get("prompt", ""),
            created_by=data.get("created_by", "user"),
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", time.time()),
            last_fired_at=data.get("last_fired_at"),
            interval=data.get("interval", 3600.0),
            stop_condition=data.get("stop_condition"),
        )


_TASK_TYPE_MAP: dict[str, type[Task]] = {
    "cron": CronTask,
    "watch": WatchTask,
    "polling": PollingTask,
}


def task_from_dict(data: dict[str, Any]) -> Task:
    """Deserialize any Task subclass from a dict."""
    task_type = data.get("type", "")
    cls = _TASK_TYPE_MAP.get(task_type, Task)
    if hasattr(cls, "from_dict"):
        return cls.from_dict(data)
    return Task.from_dict(data)
