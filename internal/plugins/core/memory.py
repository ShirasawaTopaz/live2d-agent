"""Core plugin: conversation memory (``ctx.memory``).

``MemoryManager`` owns sessions, summaries, and compression. The plugin only
resolves its config lazily, so mounting the tree never touches the filesystem:
plugins that actually need memory call ``ensure()`` (or the agent adapter does
it while wiring an agent).
"""

from __future__ import annotations

from typing import Any

from internal.cordis import Schema, Service
from internal.memory import MemoryConfig, MemoryManager

plugin_name = "memory"

module_schema = Schema.object({})


class MemoryService(Service):
    """Owns the :class:`MemoryManager` instance for the application."""

    def __init__(self, ctx: Any, name: str = "memory") -> None:
        super().__init__(ctx, name)
        self.manager: MemoryManager | None = None
        self.memory_config: MemoryConfig | None = None

    @property
    def enabled(self) -> bool:
        config = self.config
        if isinstance(config, dict) and config.get("enabled") is not None:
            return bool(config["enabled"])
        return bool(getattr(self.memory_config, "enabled", False))

    def build(self, config: MemoryConfig | None = None) -> MemoryManager | None:
        """Create the manager when memory is enabled, else return None."""
        resolved = config if config is not None else self._config_from_app()
        self.memory_config = resolved
        if resolved is None or not getattr(resolved, "enabled", False):
            self.manager = None
            return None
        if self.manager is None:
            self.manager = MemoryManager(resolved)
        return self.manager

    async def ensure(self) -> MemoryManager | None:
        manager = self.manager if self.manager is not None else self.build()
        if manager is not None and not manager._initialized:
            await manager.init()
        return manager

    async def reset(self, title: str | None = None) -> None:
        manager = await self.ensure()
        if manager is not None:
            await manager.reset_active_context(title)

    def _config_from_app(self) -> MemoryConfig | None:
        config_service = self.ctx.get("config")
        if config_service is None:
            return None
        return getattr(config_service, "memory", None)


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    service = MemoryService(ctx, "memory")
    if isinstance(config, dict):
        service.config = config
    ctx.service("memory", service)
