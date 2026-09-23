"""Core plugin: background scheduler (``ctx.scheduler``)."""

from __future__ import annotations

from typing import Any

from internal.cordis import Schema, Service
from internal.scheduler.engine import SchedulerEngine
from internal.scheduler.notification import NotificationManager
from internal.scheduler.store import TaskStore

plugin_name = "scheduler"

module_schema = Schema.object({})


class SchedulerService(Service):
    """Owns the cron/watch/polling scheduler engine."""

    def __init__(self, ctx: Any, name: str = "scheduler") -> None:
        super().__init__(ctx, name)
        self.engine: SchedulerEngine | None = None
        self.data_dir = "./data/scheduler"

    @property
    def enabled(self) -> bool:
        return self.engine is not None

    def build(self, config: Any = None, notification: Any = None, agent: Any = None) -> SchedulerEngine | None:
        resolved = config if config is not None else self._config_from_app()
        if resolved is None or not getattr(resolved, "enabled", False):
            self.engine = None
            return None
        self.data_dir = getattr(resolved, "data_dir", self.data_dir) or self.data_dir
        store = TaskStore(data_dir=self.data_dir)
        if notification is None:
            notification = NotificationManager(
                tray_icon=self.ctx.store.get("tray_icon"),
                websocket=self.ctx.store.get("websocket"),
            )
        self.engine = SchedulerEngine(store=store, notification=notification, agent=agent)
        return self.engine

    async def ensure(self) -> SchedulerEngine | None:
        engine = self.engine if self.engine is not None else self.build()
        if engine is None:
            return None
        await engine.initialize()
        return engine

    async def stop(self) -> None:
        engine = self.engine
        if engine is None:
            return
        stop = getattr(engine, "stop", None)
        if callable(stop):
            result = stop()
            if hasattr(result, "__await__"):
                await result

    def _config_from_app(self) -> Any:
        config_service = self.ctx.get("config")
        if config_service is None:
            return None
        return getattr(config_service, "scheduler", None)


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    service = SchedulerService(ctx, "scheduler")
    if isinstance(config, dict):
        service.config = config
    ctx.service("scheduler", service)
