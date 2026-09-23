"""Core plugin: application config (``ctx.config``).

Wraps :class:`internal.config.config.Config` so plugins read configuration from
``ctx.config`` instead of importing ``Config`` directly. ``reload()`` re-reads
``config.json`` and emits ``config/updated`` for interested plugins.
"""

from __future__ import annotations

from typing import Any

from internal.cordis import Schema, Service
from internal.config.config import Config

plugin_name = "config"

module_schema = Schema.object(
    {
        "path": Schema.string().default(""),
    }
)


class ConfigService(Service):
    """Owns the application :class:`Config` instance."""

    inject = ["logger"]

    def __init__(self, ctx: Any, name: str = "config") -> None:
        super().__init__(ctx, name)
        self.value: Config | None = None
        self.path: str = Config.DEFAULT_CONFIG_PATH

    @property
    def initialized(self) -> bool:
        return self.value is not None

    def configure(self, path: str) -> None:
        if path:
            self.path = path
            Config.DEFAULT_CONFIG_PATH = path

    async def load(self, path: str | None = None) -> Config:
        if path:
            self.configure(path)
        self.value = await Config.load(self.path)
        return self.value

    async def reload(self) -> Config:
        """Re-read the config file and notify listeners."""
        value = await self.load()
        self.ctx.root.emit("config/updated", value)
        return value

    def get_default_model_config(self) -> Any:
        if self.value is None:
            raise RuntimeError("config service is not initialized")
        return self.value.get_default_model_config()

    @property
    def memory(self) -> Any:
        return getattr(self.value, "memory", None)

    @property
    def sandbox(self) -> Any:
        return getattr(self.value, "sandbox", None)

    @property
    def planning(self) -> Any:
        return getattr(self.value, "planning", None)

    @property
    def live2d_socket(self) -> str:
        return str(getattr(self.value, "live2dSocket", ""))


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    service = ConfigService(ctx, "config")
    service.configure(str((config or {}).get("path") or ""))
    ctx.service("config", service)
