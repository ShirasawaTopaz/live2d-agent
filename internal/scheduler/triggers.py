"""Trigger implementations for the scheduler.

Built-in triggers:
- CronTrigger: cron expressions or one-shot timestamps
- FileWatcher: filesystem events via watchdog
- PollingTrigger: fixed-interval polling
"""

import asyncio
import logging
import os
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
    (0, 6),    # day of week (0=Monday in Python)
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


def _next_cron(cron_expr: str, from_time: float | None = None) -> float:
    """Calculate the next fire time from a 5-field cron expression."""
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

    st = time.localtime(from_time)
    current = list(st[:6])
    current[4] += 1  # advance one minute
    current[5] = 0

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
        dow = st.tm_wday  # 0=Monday in Python

        if month in month_set and minute in mins_set and hour in hours_set:
            day_ok = dom in dom_set or dow in dow_set
            if day_ok:
                return candidate

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

    def __init__(self, cron_expr: str | None = None, run_at: float | None = None):
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
        if self.run_at is not None:
            if self.run_at <= time.time():
                return None
            return self.run_at
        if self.cron_expr is not None:
            return _next_cron(self.cron_expr)
        return None

    async def _run(self, callback: Callable[[Event], Any]) -> None:
        while self._running:
            next_fire = self._next_fire()
            if next_fire is None:
                if self.run_at is not None:
                    return
                next_fire = time.time() + 60

            wait_seconds = max(0, next_fire - time.time())
            try:
                await asyncio.sleep(wait_seconds)
            except asyncio.CancelledError:
                return

            if not self._running:
                return

            event = Event(source="cron", data={
                "cron_expr": self.cron_expr,
                "run_at": self.run_at,
            })
            try:
                await callback(event)
            except Exception:
                logger.exception("CronTrigger callback failed")

            if self.run_at is not None:
                return

    def describe(self) -> str:
        if self.run_at is not None:
            return f"CronTrigger(at={time.strftime('%Y-%m-%d %H:%M', time.localtime(self.run_at))})"
        return f"CronTrigger({self.cron_expr})"


# ── FileWatcher ───────────────────────────────────────────────

class FileWatcher(TriggerSource):
    """Watches a directory for filesystem events using watchdog."""

    def __init__(self, path: str, patterns: list[str] | None = None,
                 events: list[str] | None = None):
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
                event_type = event.event_type
                if event_type not in watcher.event_types:
                    return
                src = event.src_path
                if watcher.patterns and watcher.patterns != ["*"]:
                    import fnmatch
                    basename = os.path.basename(src)
                    if not any(fnmatch.fnmatch(basename, p) for p in watcher.patterns):
                        return
                ev = Event(source="file_watch", data={
                    "path": src, "event_type": event_type,
                })
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
