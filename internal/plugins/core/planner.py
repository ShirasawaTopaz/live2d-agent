"""Core plugin: plan storage and execution (``ctx.planner``)."""

from __future__ import annotations

from typing import Any

from internal.cordis import Schema, Service
from internal.agent.planning.planner import Planner, PlannerConfig
from internal.agent.planning.storage.json import JSONPlanStorage
from internal.agent.planning.storage.sqlite import SQLitePlanStorage

plugin_name = "planner"

module_schema = Schema.object({})


class PlannerService(Service):
    """Builds a :class:`Planner` from the planning section of the config."""

    def __init__(self, ctx: Any, name: str = "planner") -> None:
        super().__init__(ctx, name)
        self.planner: Planner | None = None

    @property
    def enabled(self) -> bool:
        return self.planner is not None

    def build(self, config: Any = None, agent: Any = None) -> Planner | None:
        resolved = config if config is not None else self._config_from_app()
        if resolved is None or not getattr(resolved, "enabled", False):
            self.planner = None
            return None
        storage_type = getattr(resolved, "storage_type", "json")
        storage_path = getattr(resolved, "storage_path", "data/plans.json")
        if storage_type == "sqlite":
            storage: Any = SQLitePlanStorage(storage_path)
        else:
            storage = JSONPlanStorage(storage_path)
        planner_config = PlannerConfig(
            max_concurrency=getattr(resolved, "max_concurrency", 1),
            max_plan_depth=getattr(resolved, "max_plan_depth", 10),
            auto_save=getattr(resolved, "auto_save", True),
        )
        if agent is None:
            agent = self.ctx.get("agent/loop")
        self.planner = Planner(storage=storage, config=planner_config, agent=agent)
        return self.planner

    def _config_from_app(self) -> Any:
        config_service = self.ctx.get("config")
        if config_service is None:
            return None
        return getattr(config_service, "planning", None)


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    service = PlannerService(ctx, "planner")
    if isinstance(config, dict):
        service.config = config
    ctx.service("planner", service)
