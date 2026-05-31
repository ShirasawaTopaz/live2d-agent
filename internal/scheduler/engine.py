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
    CronTask, Event, PollingTask, Task, TriggerSource, WatchTask,
)
from internal.scheduler.triggers import CronTrigger, FileWatcher, PollingTrigger
from internal.scheduler.store import TaskStore
from internal.scheduler.notification import NotificationManager

logger = logging.getLogger(__name__)


class SchedulerEngine:
    """Manages scheduled task lifecycle."""

    def __init__(self, store: TaskStore, notification: NotificationManager,
                 agent: Any = None):
        self._store = store
        self._notification = notification
        self._agent = agent
        self._triggers: dict[str, TriggerSource] = {}
        self._asyncio_tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False

    @property
    def agent(self) -> Any:
        return self._agent

    @agent.setter
    def agent(self, value: Any) -> None:
        self._agent = value

    async def initialize(self) -> None:
        await self._store.init()
        self._running = True
        tasks = await self._store.list_all()
        for task in tasks:
            if task.enabled:
                await self._start_trigger(task)
        logger.info("SchedulerEngine initialized with %d tasks (%d active)",
                     len(tasks), len(self._triggers))

    async def add(self, task: Task) -> str:
        await self._store.save(task)
        if task.enabled:
            await self._start_trigger(task)
        logger.info("Task added: %s (%s)", task.task_id, task.describe_trigger())
        return task.task_id

    async def remove(self, task_id: str) -> bool:
        await self._stop_trigger(task_id)
        deleted = await self._store.delete(task_id)
        if deleted:
            logger.info("Task removed: %s", task_id)
        return deleted

    async def pause(self, task_id: str) -> None:
        await self._stop_trigger(task_id)
        task = await self._store.load(task_id)
        if task is not None:
            task.enabled = False
            await self._store.save(task)
            logger.info("Task paused: %s", task_id)

    async def resume(self, task_id: str) -> None:
        task = await self._store.load(task_id)
        if task is not None:
            task.enabled = True
            await self._store.save(task)
            await self._start_trigger(task)
            logger.info("Task resumed: %s", task_id)

    async def list_tasks(self) -> list[Task]:
        return await self._store.list_all()

    async def shutdown(self) -> None:
        self._running = False
        for task_id in list(self._triggers.keys()):
            await self._stop_trigger(task_id)
        logger.info("SchedulerEngine shut down")

    async def _start_trigger(self, task: Task) -> None:
        if task.task_id in self._triggers:
            return
        self._running = True
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
        trigger = self._triggers.pop(task_id, None)
        if trigger is not None:
            await trigger.stop()
            logger.debug("Trigger stopped for task '%s'", task_id)

    def _make_trigger(self, task: Task) -> TriggerSource | None:
        if isinstance(task, CronTask):
            if task.run_at is not None and task.run_at <= time.time():
                return None
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
            logger.warning("Unknown trigger source: %s", task.trigger_source_name)
            return None
        if isinstance(task, PollingTask):
            return PollingTrigger(interval=task.interval)
        logger.warning("Unknown task type: %s", type(task).__name__)
        return None

    async def _execute_task(self, task: Task, event: Event) -> None:
        if not self._running:
            return
        logger.info("Task '%s' triggered: %s", task.task_id, task.describe_trigger())

        prompt_parts: list[str] = []
        if event.source == "file_watch":
            prompt_parts.append(f"[事件] 新文件: {event.data.get('path', '')}")
        elif event.source == "cron":
            prompt_parts.append("[事件] 定时任务触发")
        prompt_parts.append(task.prompt)
        full_prompt = "\n".join(prompt_parts)

        response_text = ""
        try:
            if self._agent is not None:
                if hasattr(self._agent, "memory") and self._agent.memory is not None:
                    mem = self._agent.memory
                    if hasattr(mem, "new_session"):
                        await mem.new_session(f"task:{task.task_id}")
                result = await self._agent.chat(full_prompt, None)
                if isinstance(result, dict):
                    response_text = result.get("content", "")
                elif isinstance(result, str):
                    response_text = result
        except Exception:
            logger.exception("Task '%s' execution failed", task.task_id)
            response_text = "task execution error, check logs"

        task.last_fired_at = time.time()
        await self._store.save(task)

        title = task.prompt[:50]
        self._notification.notify(title, response_text)

        if isinstance(task, CronTask) and task.run_at is not None:
            logger.info("One-shot task '%s' completed, disabling", task.task_id)
            await self._stop_trigger(task.task_id)
            task.enabled = False
            await self._store.save(task)
