# Scheduler Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a background scheduler that lets the Agent execute cron-like tasks, file-watch triggers, and polling tasks — all running on asyncio with extensible trigger sources.

**Architecture:** Pure asyncio engine (no APScheduler dependency). `TriggerSource` ABC enables pluggable event sources. `CronTask` / `WatchTask` / `PollingTask` are persisted to disk via `TaskStore`. When a task fires, it runs through the Agent in its own isolated session and pushes results via `QSystemTrayIcon` notifications.

**Tech Stack:** Python 3.12+, asyncio, `watchdog` (for file watcher), existing `Agent`, existing `internal/session/` (for task isolation)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `internal/scheduler/__init__.py` | Package exports |
| Create | `internal/scheduler/types.py` | Task / TriggerSource / Event data classes |
| Create | `internal/scheduler/triggers.py` | CronTrigger, FileWatcher, PollingTrigger |
| Create | `internal/scheduler/store.py` | Task persistence (JSON) |
| Create | `internal/scheduler/engine.py` | SchedulerEngine core |
| Create | `internal/scheduler/notification.py` | Desktop + bubble notifications |
| Modify | `internal/app/live2d_agent_app.py` | Initialize scheduler on startup |
| Create | `test/scheduler/__init__.py` | Test package marker |
| Create | `test/scheduler/test_triggers.py` | Trigger unit tests |
| Create | `test/scheduler/test_engine.py` | Engine integration tests |
| Create | `test/scheduler/test_store.py` | Persistence round-trip tests |

---

### Task 1: Scheduler Types

**Files:**
- Create: `internal/scheduler/__init__.py`
- Create: `internal/scheduler/types.py`

- [ ] **Step 1: Create `internal/scheduler/__init__.py`**

```python
"""Background scheduler for proactive Agent tasks."""

from internal.scheduler.types import Task, CronTask, WatchTask, PollingTask, TriggerSource, Event
from internal.scheduler.triggers import CronTrigger, FileWatcher, PollingTrigger
from internal.scheduler.engine import SchedulerEngine
from internal.scheduler.notification import NotificationManager

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
    "NotificationManager",
]
```

- [ ] **Step 2: Create `internal/scheduler/types.py`**

```python
"""Type definitions for the scheduler system."""

import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


# ── Event ────────────────────────────────────────────────────

@dataclass
class Event:
    """A trigger event payload."""
    source: str          # "cron", "file_watch", "polling", etc.
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)
    # For file events: {"path": "...", "event_type": "created"}
    # For cron events:  {"cron_expr": "0 9 * * *"}


# ── TriggerSource ─────────────────────────────────────────────

class TriggerSource(ABC):
    """Pluggable event source. Implementations define how to wait for
    the next event and how to clean up.
    """

    @abstractmethod
    async def start(self, callback: Callable[[Event], Any]) -> None:
        """Start listening. Calls `callback(event)` for each triggered event."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop listening and clean up resources."""
        ...

    def describe(self) -> str:
        """Human-readable description of this trigger."""
        return self.__class__.__name__


# ── Task types ────────────────────────────────────────────────

@dataclass
class Task:
    """Base scheduled task."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    prompt: str = ""
    created_by: str = "user"  # "user" or "agent"
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    last_fired_at: float | None = None

    def describe_trigger(self) -> str:
        return "unknown"

    def to_dict(self) -> dict[str, Any]:
        d = {
            "task_id": self.task_id,
            "prompt": self.prompt,
            "created_by": self.created_by,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "last_fired_at": self.last_fired_at,
        }
        return d

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
    cron_expr: str | None = None   # e.g. "*/30 * * * *"
    run_at: float | None = None     # One-shot unix timestamp

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
            task_id=data["task_id"],
            prompt=data.get("prompt", ""),
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
    trigger_source_name: str = ""          # e.g. "file_watcher", "process_watcher"
    trigger_config: dict[str, Any] = field(default_factory=dict)
    # e.g. {"path": "/home/user/Downloads", "patterns": ["*.pdf"]}
    filter_rules: dict[str, Any] = field(default_factory=dict)
    # Optional: only fire if event matches {"event_type": "created"}

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
            task_id=data["task_id"],
            prompt=data.get("prompt", ""),
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
    interval: float = 3600.0           # Seconds between polls
    stop_condition: str | None = None  # Prompt to evaluate whether to stop

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
            task_id=data["task_id"],
            prompt=data.get("prompt", ""),
            created_by=data.get("created_by", "user"),
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", time.time()),
            last_fired_at=data.get("last_fired_at"),
            interval=data.get("interval", 3600.0),
            stop_condition=data.get("stop_condition"),
        )


# ── Task factory ──────────────────────────────────────────────

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
```

- [ ] **Step 3: Commit**

```bash
git add internal/scheduler/__init__.py internal/scheduler/types.py
git commit -m "feat(scheduler): add types with TriggerSource ABC and Task subclasses"
```

---

### Task 2: Trigger Implementations

**Files:**
- Create: `internal/scheduler/triggers.py`
- Create: `test/scheduler/__init__.py`
- Create: `test/scheduler/test_triggers.py`

- [ ] **Step 1: Create `test/scheduler/__init__.py`** (empty file)

```python
"""Tests for scheduler module."""
```

- [ ] **Step 2: Write tests in `test/scheduler/test_triggers.py`**

```python
"""Unit tests for trigger implementations."""

import asyncio
import time
import pytest
from internal.scheduler.types import Event
from internal.scheduler.triggers import CronTrigger


class TestCronTrigger:
    """Tests for CronTrigger."""

    def test_parse_cron_fields(self):
        trigger = CronTrigger(cron_expr="0 9 * * *")
        assert trigger.cron_expr == "0 9 * * *"

    def test_parse_every_30_minutes(self):
        trigger = CronTrigger(cron_expr="*/30 * * * *")
        assert trigger.cron_expr == "*/30 * * * *"

    def test_one_shot_timestamp(self):
        future = time.time() + 1  # 1 second from now
        trigger = CronTrigger(run_at=future)
        assert trigger.run_at == future
        assert trigger.cron_expr is None

    def test_next_fire_one_shot(self):
        future = time.time() + 10
        trigger = CronTrigger(run_at=future)
        next_fire = trigger._next_fire()
        assert next_fire is not None
        assert abs(next_fire - future) < 1.0

    def test_next_fire_every_minute(self):
        trigger = CronTrigger(cron_expr="* * * * *")
        now = time.time()
        next_fire = trigger._next_fire()
        assert next_fire is not None
        assert next_fire > now
        assert next_fire <= now + 60

    @pytest.mark.asyncio
    async def test_fires_and_stops(self):
        """Trigger should fire callback and then stop cleanly."""
        trigger = CronTrigger(run_at=time.time() + 0.1)  # 100ms
        events: list[Event] = []

        async def collect(event: Event):
            events.append(event)

        await trigger.start(collect)
        await asyncio.sleep(0.3)
        await trigger.stop()

        assert len(events) == 1
        assert events[0].source == "cron"

    @pytest.mark.asyncio
    async def test_fires_multiple_times(self):
        """Cron trigger with short interval should fire repeatedly."""
        trigger = CronTrigger(cron_expr="* * * * * *")  # Every second (6-field cron)
        # Use a one-shot approach instead to keep the test fast
        trigger2 = CronTrigger(run_at=time.time() + 0.05)
        events: list[Event] = []

        async def collect(event: Event):
            events.append(event)

        await trigger2.start(collect)
        await asyncio.sleep(0.2)
        await trigger2.stop()

        assert len(events) >= 1

    @pytest.mark.asyncio
    async def test_stop_without_start_does_not_crash(self):
        trigger = CronTrigger(run_at=time.time())
        await trigger.stop()  # Should not raise
```

- [ ] **Step 3: Run to verify failure**

```bash
cd D:/Source/live2oder && poetry run pytest test/scheduler/test_triggers.py -v
```
Expected: FAIL

- [ ] **Step 4: Implement `internal/scheduler/triggers.py`**

```python
"""Trigger implementations for the scheduler.

Built-in triggers:
- CronTrigger: cron expressions or one-shot timestamps
- FileWatcher: filesystem events via watchdog
- PollingTrigger: fixed-interval polling

All implement the TriggerSource ABC from internal.scheduler.types.
"""

import asyncio
import logging
import os
import re
import time
from collections.abc import Callable
from typing import Any

from internal.scheduler.types import Event, TriggerSource

logger = logging.getLogger(__name__)


# ── Cron field parsing ────────────────────────────────────────

_CRON_FIELD_RANGES = [
    (0, 59),   # minute
    (0, 23),   # hour
    (1, 31),   # day of month
    (1, 12),   # month
    (0, 6),    # day of week
]


def _parse_cron_field(field: str, lo: int, hi: int) -> set[int]:
    """Parse a single cron field into a set of matching values."""
    if field == "*":
        return set(range(lo, hi + 1))

    values: set[int] = set()
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, step_str = part.split("/", 1)
            step = int(step_str)

        if "-" in part:
            start, end = part.split("-", 1)
            r = range(int(start), int(end) + 1, step)
        elif part == "*":
            r = range(lo, hi + 1, step)
        else:
            v = int(part)
            values.add(v)
            continue

        values.update(r)

    return values


def _next_cron(
    cron_expr: str,
    from_time: float | None = None,
) -> float:
    """Calculate the next fire time from a 5-field cron expression.

    Args:
        cron_expr: Standard 5-field cron "M H DoM Mo DoW".
        from_time: Base timestamp (defaults to now).

    Returns:
        Unix timestamp of next fire, never more than 1 year in the future.
    """
    if from_time is None:
        from_time = time.time()

    fields = cron_expr.strip().split()
    if len(fields) != 5:
        raise ValueError(f"Expected 5 cron fields, got {len(fields)}: {cron_expr!r}")

    parsed = [
        _parse_cron_field(f, lo, hi)
        for f, (lo, hi) in zip(fields, _CRON_FIELD_RANGES)
    ]
    mins_set, hours_set, dom_set, month_set, dow_set = parsed

    # Start from the next minute
    st = time.localtime(from_time)
    current = list(st[:6])  # (Y, M, D, H, Min, Sec, WDay, YDay, DST)
    current[4] += 1  # advance one minute
    current[5] = 0

    # Cap search at 1 year forward
    deadline = from_time + 365 * 24 * 3600

    while True:
        candidate = time.mktime(time.struct_time(tuple(current) + (0, 0, -1)))
        if candidate > deadline:
            return deadline

        st = time.localtime(candidate)
        month = st.tm_mon
        dom = st.tm_mday
        hour = st.tm_hour
        minute = st.tm_min
        dow = st.tm_wday  # 0=Mon in cron, but Python uses 0=Mon

        if (
            month in month_set
            and minute in mins_set
            and hour in hours_set
        ):
            # Day: match by day-of-month OR day-of-week
            day_ok = dom in dom_set or dow in dow_set
            # If both are specified (non-*), it's OR logic per cron convention
            if day_ok:
                return candidate

        # Step forward 1 minute
        current[4] += 1
        if current[4] >= 60:
            current[4] = 0
            current[3] += 1
        if current[3] >= 24:
            current[3] = 0
            current[2] += 1


# ── CronTrigger ───────────────────────────────────────────────

class CronTrigger(TriggerSource):
    """Fires on a cron schedule or at a specific timestamp."""

    def __init__(
        self,
        cron_expr: str | None = None,
        run_at: float | None = None,
    ):
        self.cron_expr = cron_expr
        self.run_at = run_at
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self, callback: Callable[[Event], Any]) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run(callback))

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def _next_fire(self) -> float | None:
        """Calculate next fire timestamp. Returns None for past one-shot."""
        if self.run_at is not None:
            if self.run_at <= time.time():
                return None  # Already in the past
            return self.run_at
        if self.cron_expr is not None:
            return _next_cron(self.cron_expr)
        return None

    async def _run(self, callback: Callable[[Event], Any]) -> None:
        while self._running:
            next_fire = self._next_fire()
            if next_fire is None:
                if self.run_at is not None:
                    # One-shot that already fired
                    return
                # Cron without next fire? Shouldn't happen, but wait 60s
                next_fire = time.time() + 60

            wait_seconds = max(0, next_fire - time.time())
            try:
                await asyncio.sleep(wait_seconds)
            except asyncio.CancelledError:
                return

            if not self._running:
                return

            event = Event(
                source="cron",
                data={
                    "cron_expr": self.cron_expr,
                    "run_at": self.run_at,
                },
            )
            try:
                await callback(event)
            except Exception:
                logger.exception("CronTrigger callback failed")

            # One-shot: stop after firing once
            if self.run_at is not None:
                return

    def describe(self) -> str:
        if self.run_at is not None:
            return f"CronTrigger(at={time.strftime('%Y-%m-%d %H:%M', time.localtime(self.run_at))})"
        return f"CronTrigger({self.cron_expr})"


# ── FileWatcher ───────────────────────────────────────────────

class FileWatcher(TriggerSource):
    """Watches a directory for filesystem events using watchdog."""

    def __init__(
        self,
        path: str,
        patterns: list[str] | None = None,
        events: list[str] | None = None,
    ):
        self.path = path
        self.patterns = patterns or ["*"]
        self.event_types = events or ["created", "modified"]
        self._observer = None
        self._running = False

    async def start(self, callback: Callable[[Event], Any]) -> None:
        self._running = True
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            logger.error("watchdog not installed, FileWatcher unavailable")
            return

        watcher = self

        class _Handler(FileSystemEventHandler):
            def on_any_event(self2, event):
                if not watcher._running:
                    return
                event_type = event.event_type  # "created", "modified", "deleted", "moved"
                if event_type not in watcher.event_types:
                    return
                src = event.src_path
                if watcher.patterns and watcher.patterns != ["*"]:
                    import fnmatch
                    basename = os.path.basename(src)
                    if not any(fnmatch.fnmatch(basename, p) for p in watcher.patterns):
                        return
                ev = Event(
                    source="file_watch",
                    data={"path": src, "event_type": event_type},
                )
                asyncio.ensure_future(callback(ev))

        self._observer = Observer()
        self._observer.schedule(_Handler(), self.path, recursive=False)
        self._observer.start()
        logger.info("FileWatcher started on %s", self.path)

    async def stop(self) -> None:
        self._running = False
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None

    def describe(self) -> str:
        return f"FileWatcher({self.path}, patterns={self.patterns})"


# ── PollingTrigger ────────────────────────────────────────────

class PollingTrigger(TriggerSource):
    """Fires at a fixed interval."""

    def __init__(self, interval: float):
        self.interval = interval
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self, callback: Callable[[Event], Any]) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run(callback))

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self, callback: Callable[[Event], Any]) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                return
            if not self._running:
                return
            event = Event(source="polling", data={"interval": self.interval})
            try:
                await callback(event)
            except Exception:
                logger.exception("PollingTrigger callback failed")

    def describe(self) -> str:
        return f"PollingTrigger(every {self.interval}s)"
```

- [ ] **Step 5: Run tests**

```bash
cd D:/Source/live2oder && poetry run pytest test/scheduler/test_triggers.py -v -x
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add internal/scheduler/triggers.py test/scheduler/__init__.py test/scheduler/test_triggers.py
git commit -m "feat(scheduler): add CronTrigger, FileWatcher, PollingTrigger implementations"
```

---

### Task 3: Task Store

**Files:**
- Create: `internal/scheduler/store.py`
- Create: `test/scheduler/test_store.py`

- [ ] **Step 1: Write tests in `test/scheduler/test_store.py`**

```python
"""Tests for scheduler task persistence."""

import tempfile
import time
import pytest
from internal.scheduler.store import TaskStore
from internal.scheduler.types import CronTask, WatchTask, PollingTask


class TestTaskStore:
    def setup_method(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = TaskStore(data_dir=self.temp_dir.name)

    def teardown_method(self):
        self.temp_dir.cleanup()

    @pytest.mark.asyncio
    async def test_init_creates_file(self):
        from pathlib import Path
        await self.store.init()
        assert (Path(self.temp_dir.name) / "tasks.json").exists()

    @pytest.mark.asyncio
    async def test_save_and_load_cron_task(self):
        await self.store.init()
        task = CronTask(
            task_id="t1",
            prompt="汇总今日待办",
            cron_expr="0 9 * * *",
        )
        await self.store.save(task)
        loaded = await self.store.load("t1")
        assert loaded is not None
        assert loaded.task_id == "t1"
        assert loaded.prompt == "汇总今日待办"
        assert isinstance(loaded, CronTask)
        assert loaded.cron_expr == "0 9 * * *"

    @pytest.mark.asyncio
    async def test_save_and_load_watch_task(self):
        await self.store.init()
        task = WatchTask(
            task_id="w1",
            prompt="分析新PDF",
            trigger_source_name="file_watcher",
            trigger_config={"path": "/tmp/downloads", "patterns": ["*.pdf"]},
        )
        await self.store.save(task)
        loaded = await self.store.load("w1")
        assert loaded is not None
        assert isinstance(loaded, WatchTask)
        assert loaded.trigger_source_name == "file_watcher"

    @pytest.mark.asyncio
    async def test_list_all(self):
        await self.store.init()
        await self.store.save(CronTask(task_id="t1", prompt="a"))
        await self.store.save(PollingTask(task_id="t2", prompt="b", interval=600))
        tasks = await self.store.list_all()
        assert len(tasks) == 2

    @pytest.mark.asyncio
    async def test_delete(self):
        await self.store.init()
        await self.store.save(CronTask(task_id="t1", prompt="x"))
        assert await self.store.delete("t1") is True
        assert await self.store.load("t1") is None
        assert await self.store.delete("nonexistent") is False

    @pytest.mark.asyncio
    async def test_load_nonexistent(self):
        await self.store.init()
        assert await self.store.load("nonexistent") is None
```

- [ ] **Step 2: Run to verify failure**

```bash
cd D:/Source/live2oder && poetry run pytest test/scheduler/test_store.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement `internal/scheduler/store.py`**

```python
"""Task persistence layer.

Stores all tasks in a single JSON file at <data_dir>/tasks.json.
Uses asyncio.to_thread for non-blocking I/O.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path

from internal.scheduler.types import Task, task_from_dict

logger = logging.getLogger(__name__)


class TaskStore:
    """Persist scheduled tasks to disk."""

    def __init__(self, data_dir: str = "./data/scheduler"):
        self.data_dir = Path(data_dir)
        self._filepath = self.data_dir / "tasks.json"
        self._tasks: dict[str, dict] = {}

    async def init(self) -> None:
        """Initialize storage and load existing tasks."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self._filepath.exists():
            await self._load_from_disk()
        else:
            self._tasks = {}
            await self._save_to_disk()

    # ── CRUD ──────────────────────────────────────────────

    async def save(self, task: Task) -> None:
        """Save a task (insert or update)."""
        self._tasks[task.task_id] = task.to_dict()
        await self._save_to_disk()
        logger.debug("Saved task '%s'", task.task_id)

    async def load(self, task_id: str) -> Task | None:
        """Load a single task by ID."""
        data = self._tasks.get(task_id)
        if data is None:
            return None
        return task_from_dict(data)

    async def list_all(self) -> list[Task]:
        """List all tasks."""
        return [task_from_dict(d) for d in self._tasks.values()]

    async def delete(self, task_id: str) -> bool:
        """Delete a task. Returns True if it existed."""
        if task_id in self._tasks:
            del self._tasks[task_id]
            await self._save_to_disk()
            logger.debug("Deleted task '%s'", task_id)
            return True
        return False

    # ── Internal I/O ──────────────────────────────────────

    async def _save_to_disk(self) -> None:
        content = json.dumps(
            {"tasks": list(self._tasks.values()), "updated_at": time.time()},
            ensure_ascii=False,
            indent=2,
        )
        await asyncio.to_thread(self._write_file, content)

    def _write_file(self, content: str) -> None:
        self._filepath.write_text(content, encoding="utf-8")

    async def _load_from_disk(self) -> None:
        content = await asyncio.to_thread(self._filepath.read_text, encoding="utf-8")
        try:
            data = json.loads(content)
            task_list = data.get("tasks", [])
            self._tasks = {t["task_id"]: t for t in task_list}
            logger.info("Loaded %d tasks from disk", len(self._tasks))
        except json.JSONDecodeError:
            logger.warning("Corrupt tasks.json, starting fresh")
            self._tasks = {}
```

- [ ] **Step 4: Run tests**

```bash
cd D:/Source/live2oder && poetry run pytest test/scheduler/test_store.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add internal/scheduler/store.py test/scheduler/test_store.py
git commit -m "feat(scheduler): add TaskStore for persisting scheduled tasks"
```

---

### Task 4: Notification Manager

**Files:**
- Create: `internal/scheduler/notification.py`

- [ ] **Step 1: Implement `internal/scheduler/notification.py`**

```python
"""Notification delivery for completed scheduler tasks."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class NotificationManager:
    """Delivers scheduler task results to the user.

    Two channels:
    1. Desktop toast via QSystemTrayIcon.showMessage()
    2. Live2D bubble text via WebSocket (if connected)
    """

    def __init__(
        self,
        tray_icon: Any = None,
        websocket: Any = None,
    ):
        self._tray = tray_icon
        self._ws = websocket

    def set_tray(self, tray_icon: Any) -> None:
        self._tray = tray_icon

    def set_websocket(self, ws: Any) -> None:
        self._ws = ws

    def notify(self, title: str, message: str) -> None:
        """Send a notification through all available channels.

        Args:
            title: Short title (e.g. task description).
            message: Body text (result summary, max 200 chars).
        """
        summary = message[:200] + "..." if len(message) > 200 else message

        # Channel 1: Desktop toast
        if self._tray is not None:
            try:
                self._tray.showMessage(
                    title,
                    summary,
                    icon=self._tray.icon() if hasattr(self._tray, "icon") else 0,
                    duration=5000,  # ms
                )
                logger.debug("Tray notification sent: %s", title)
            except Exception:
                logger.warning("Failed to send tray notification", exc_info=True)

        # Channel 2: Live2D bubble (async, fire-and-forget)
        if self._ws is not None and self._ws.is_connected:
            try:
                import asyncio
                asyncio.ensure_future(self._send_bubble(title, summary))
            except Exception:
                logger.warning("Failed to schedule bubble notification", exc_info=True)

        # Also log for audit
        logger.info("Notification: [%s] %s", title, summary)

    async def _send_bubble(self, title: str, text: str) -> None:
        """Send bubble text to Live2D via WebSocket."""
        if self._ws is None or not self._ws.is_connected:
            return
        try:
            bubble_text = f"⏰ {title}\n{text}"
            await self._ws.client.send_json({
                "type": "display_bubble_text",
                "text": bubble_text,
                "duration_ms": 8000,
            })
        except Exception:
            logger.debug("Bubble notification failed (Live2D may be offline)")
```

- [ ] **Step 2: Commit**

```bash
git add internal/scheduler/notification.py
git commit -m "feat(scheduler): add NotificationManager for tray and bubble delivery"
```

---

### Task 5: Scheduler Engine

**Files:**
- Create: `internal/scheduler/engine.py`
- Create: `test/scheduler/test_engine.py`

- [ ] **Step 1: Write tests in `test/scheduler/test_engine.py`**

```python
"""Integration tests for SchedulerEngine."""

import asyncio
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from internal.scheduler.types import CronTask, PollingTask
from internal.scheduler.store import TaskStore
from internal.scheduler.notification import NotificationManager


class TestSchedulerEngine:
    def setup_method(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = TaskStore(data_dir=self.temp_dir.name)
        self.notifier = NotificationManager()

    def teardown_method(self):
        self.temp_dir.cleanup()

    @pytest.mark.asyncio
    async def test_add_and_list_tasks(self):
        from internal.scheduler.engine import SchedulerEngine

        await self.store.init()
        engine = SchedulerEngine(
            store=self.store,
            notification=self.notifier,
            agent=None,
        )

        task = CronTask(task_id="t1", prompt="test", run_at=time.time() + 3600)
        await engine.add(task)

        tasks = await engine.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].task_id == "t1"

    @pytest.mark.asyncio
    async def test_remove_task(self):
        from internal.scheduler.engine import SchedulerEngine

        await self.store.init()
        engine = SchedulerEngine(
            store=self.store,
            notification=self.notifier,
            agent=None,
        )

        task = CronTask(task_id="t1", prompt="test", run_at=time.time() + 3600)
        await engine.add(task)
        assert await engine.remove("t1") is True
        assert await engine.remove("t1") is False

    @pytest.mark.asyncio
    async def test_pause_and_resume(self):
        from internal.scheduler.engine import SchedulerEngine

        await self.store.init()
        engine = SchedulerEngine(
            store=self.store,
            notification=self.notifier,
            agent=None,
        )

        task = CronTask(task_id="t1", prompt="test", run_at=time.time() + 3600)
        await engine.add(task)

        await engine.pause("t1")
        tasks = await engine.list_tasks()
        assert tasks[0].enabled is False

        await engine.resume("t1")
        tasks = await engine.list_tasks()
        assert tasks[0].enabled is True

    @pytest.mark.asyncio
    async def test_task_fires_and_executes(self):
        from internal.scheduler.engine import SchedulerEngine

        await self.store.init()

        mock_agent = MagicMock()
        mock_agent.chat = AsyncMock(return_value={"content": "任务完成"})
        mock_agent.memory = MagicMock()
        mock_agent.memory.new_session = AsyncMock()
        mock_agent.memory.add_message = MagicMock()
        mock_agent.memory.get_current_messages = AsyncMock(return_value=[])

        engine = SchedulerEngine(
            store=self.store,
            notification=self.notifier,
            agent=mock_agent,
        )

        # Fast fire task
        task = CronTask(task_id="fast", prompt="say hello", run_at=time.time() + 0.2)
        await engine.add(task)

        await asyncio.sleep(0.5)

        # Verify it fired
        tasks = await engine.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].last_fired_at is not None

        await engine.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_stops_all_triggers(self):
        from internal.scheduler.engine import SchedulerEngine

        await self.store.init()
        engine = SchedulerEngine(
            store=self.store,
            notification=self.notifier,
            agent=None,
        )

        t1 = CronTask(task_id="t1", prompt="a", run_at=time.time() + 3600)
        t2 = PollingTask(task_id="t2", prompt="b", interval=3600)
        await engine.add(t1)
        await engine.add(t2)

        await engine.shutdown()
        # Should not hang or crash
```

- [ ] **Step 2: Run to verify failure**

```bash
cd D:/Source/live2oder && poetry run pytest test/scheduler/test_engine.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement `internal/scheduler/engine.py`**

```python
"""SchedulerEngine — core scheduling loop.

Manages the lifecycle of scheduled tasks:
- Creates TriggerSource instances from Task definitions
- Routes trigger events to the Agent for execution
- Persists task state changes
- Delivers results via NotificationManager
"""

import asyncio
import logging
import time
from typing import Any

from internal.scheduler.types import (
    CronTask,
    Event,
    PollingTask,
    Task,
    TriggerSource,
    WatchTask,
)
from internal.scheduler.triggers import CronTrigger, FileWatcher, PollingTrigger
from internal.scheduler.store import TaskStore
from internal.scheduler.notification import NotificationManager

logger = logging.getLogger(__name__)


class SchedulerEngine:
    """Manages scheduled task lifecycle.

    Each task gets an asyncio.Task that waits on its trigger,
    fires the Agent, and persists results.
    """

    def __init__(
        self,
        store: TaskStore,
        notification: NotificationManager,
        agent: Any = None,
    ):
        self._store = store
        self._notification = notification
        self._agent = agent

        # Runtime state
        self._triggers: dict[str, TriggerSource] = {}
        self._asyncio_tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False

    @property
    def agent(self) -> Any:
        return self._agent

    @agent.setter
    def agent(self, value: Any) -> None:
        self._agent = value

    # ── Public API ─────────────────────────────────────────

    async def initialize(self) -> None:
        """Load persisted tasks and start their triggers."""
        await self._store.init()
        self._running = True

        tasks = await self._store.list_all()
        for task in tasks:
            if task.enabled:
                await self._start_trigger(task)

        logger.info("SchedulerEngine initialized with %d tasks (%d active)",
                     len(tasks), len(self._triggers))

    async def add(self, task: Task) -> str:
        """Add a new task. Starts its trigger if enabled."""
        await self._store.save(task)
        if task.enabled:
            await self._start_trigger(task)
        logger.info("Task added: %s (%s)", task.task_id, task.describe_trigger())
        return task.task_id

    async def remove(self, task_id: str) -> bool:
        """Remove a task and stop its trigger."""
        await self._stop_trigger(task_id)
        deleted = await self._store.delete(task_id)
        if deleted:
            logger.info("Task removed: %s", task_id)
        return deleted

    async def pause(self, task_id: str) -> None:
        """Pause a task (keeps it stored, stops trigger)."""
        await self._stop_trigger(task_id)
        task = await self._store.load(task_id)
        if task is not None:
            task.enabled = False
            await self._store.save(task)
            logger.info("Task paused: %s", task_id)

    async def resume(self, task_id: str) -> None:
        """Resume a paused task."""
        task = await self._store.load(task_id)
        if task is not None:
            task.enabled = True
            await self._store.save(task)
            await self._start_trigger(task)
            logger.info("Task resumed: %s", task_id)

    async def list_tasks(self) -> list[Task]:
        """List all tasks."""
        return await self._store.list_all()

    async def shutdown(self) -> None:
        """Stop all triggers and clean up."""
        self._running = False
        for task_id in list(self._triggers.keys()):
            await self._stop_trigger(task_id)
        logger.info("SchedulerEngine shut down")

    # ── Internal ───────────────────────────────────────────

    async def _start_trigger(self, task: Task) -> None:
        """Create and start a TriggerSource for the given task."""
        if task.task_id in self._triggers:
            return  # Already running

        trigger = self._make_trigger(task)
        if trigger is None:
            logger.warning("Cannot create trigger for task '%s'", task.task_id)
            return

        async def on_event(event: Event) -> None:
            await self._execute_task(task, event)

        await trigger.start(on_event)
        self._triggers[task.task_id] = trigger
        logger.debug("Trigger started for task '%s': %s", task.task_id, trigger.describe())

    async def _stop_trigger(self, task_id: str) -> None:
        """Stop and remove the trigger for a task."""
        trigger = self._triggers.pop(task_id, None)
        if trigger is not None:
            await trigger.stop()
            logger.debug("Trigger stopped for task '%s'", task_id)

    def _make_trigger(self, task: Task) -> TriggerSource | None:
        """Create the appropriate TriggerSource for a Task."""
        if isinstance(task, CronTask):
            if task.run_at is not None and task.run_at <= time.time():
                return None  # Already expired
            return CronTrigger(
                cron_expr=task.cron_expr if task.run_at is None else None,
                run_at=task.run_at,
            )

        if isinstance(task, WatchTask):
            if task.trigger_source_name == "file_watcher":
                return FileWatcher(
                    path=task.trigger_config.get("path", "."),
                    patterns=task.trigger_config.get("patterns"),
                    events=task.filter_rules.get("events"),
                )
            # Other watch sources can be added here
            logger.warning("Unknown trigger source: %s", task.trigger_source_name)
            return None

        if isinstance(task, PollingTask):
            return PollingTrigger(interval=task.interval)

        logger.warning("Unknown task type for trigger creation: %s", type(task).__name__)
        return None

    async def _execute_task(self, task: Task, event: Event) -> None:
        """Execute a task by calling the Agent with the task prompt."""
        if not self._running:
            return

        logger.info("Task '%s' triggered: %s", task.task_id, task.describe_trigger())

        # Build the full prompt
        prompt_parts: list[str] = []

        # Add event context
        if event.source == "file_watch":
            file_path = event.data.get("path", "")
            prompt_parts.append(f"[事件] 新文件: {file_path}")
        elif event.source == "cron":
            prompt_parts.append("[事件] 定时任务触发")

        prompt_parts.append(task.prompt)

        full_prompt = "\n".join(prompt_parts)

        # Execute via Agent
        response_text = ""
        try:
            if self._agent is not None:
                # Create an isolated session for this task
                if hasattr(self._agent, "memory") and self._agent.memory is not None:
                    mem = self._agent.memory
                    if hasattr(mem, "new_session"):
                        await mem.new_session(f"task:{task.task_id}")

                result = await self._agent.chat(
                    full_prompt,
                    None,  # No websocket client for background tasks
                )
                if isinstance(result, dict):
                    response_text = result.get("content", "")
                elif isinstance(result, str):
                    response_text = result
        except Exception:
            logger.exception("Task '%s' execution failed", task.task_id)
            response_text = "任务执行出错，请检查日志。"

        # Update task state
        task.last_fired_at = time.time()
        await self._store.save(task)

        # Notify
        title = task.prompt[:50]
        self._notification.notify(title, response_text)

        # Clean up one-shot tasks
        if isinstance(task, CronTask) and task.run_at is not None:
            logger.info("One-shot task '%s' completed, removing", task.task_id)
            await self._stop_trigger(task.task_id)
            # Keep in store for audit trail, but disable
            task.enabled = False
            await self._store.save(task)
```

- [ ] **Step 4: Run tests**

```bash
cd D:/Source/live2oder && poetry run pytest test/scheduler/test_engine.py -v -x
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add internal/scheduler/engine.py test/scheduler/test_engine.py
git commit -m "feat(scheduler): add SchedulerEngine core with task lifecycle management"
```

---

### Task 6: Wire into App Bootstrap

**Files:**
- Modify: `internal/app/live2d_agent_app.py`

- [ ] **Step 1: Add scheduler initialization in app startup**

In `Live2DAgentApp`, add a `scheduler` attribute and initialize it after the agent:

```python
# In Live2DAgentApp.__init__:
        self.scheduler: Any = None
```

Add initialization method:

```python
    async def _initialize_scheduler(self) -> None:
        """Initialize the background scheduler if configured."""
        scheduler_config = getattr(self.config, "scheduler", None)
        if scheduler_config is None or not getattr(scheduler_config, "enabled", False):
            logger.info("Scheduler not enabled in config, skipping")
            return

        from internal.scheduler import SchedulerEngine, NotificationManager
        from internal.scheduler.store import TaskStore

        data_dir = getattr(scheduler_config, "data_dir", "./data/scheduler")
        store = TaskStore(data_dir=data_dir)
        await store.init()

        notifier = NotificationManager(
            tray_icon=self.tray_icon,
            websocket=self.ws,
        )

        engine = SchedulerEngine(
            store=store,
            notification=notifier,
            agent=self.agent,
        )
        await engine.initialize()

        self.scheduler = engine
        logger.info("Scheduler initialized")
```

Call `await self._initialize_scheduler()` in `initialize()` after `_connect_runtime_and_input()`:

```python
    async def initialize(self) -> None:
        from internal.app.bootstrap import bootstrap_application

        context = await bootstrap_application()
        self._apply_bootstrap_context(context)
        self._connect_runtime_and_input()
        self._setup_tray_and_window()
        await self._initialize_scheduler()  # <-- ADD THIS
        self.show_input_box()
        logger.info("输入框已显示")
```

- [ ] **Step 2: Add config section to `config.example.json`**

```json
    "scheduler": {
        "enabled": false,
        "data_dir": "./data/scheduler"
    }
```

- [ ] **Step 3: Run full scheduler tests**

```bash
cd D:/Source/live2oder && poetry run pytest test/scheduler/ -v
```
Expected: ALL PASS

- [ ] **Step 4: Run full test suite for regressions**

```bash
cd D:/Source/live2oder && poetry run pytest test/ -v --timeout=30
```
Expected: No regressions

- [ ] **Step 5: Commit**

```bash
git add internal/app/live2d_agent_app.py config.example.json
git commit -m "feat(scheduler): wire SchedulerEngine into app bootstrap"
```
