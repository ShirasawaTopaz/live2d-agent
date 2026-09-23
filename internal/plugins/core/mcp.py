"""Core plugin: MCP three-layer context management (``ctx.mcp``)."""

from __future__ import annotations

from typing import Any

from internal.cordis import Schema, Service
from internal.mcp.config import MCPConfig
from internal.mcp.manager import MCPContextManager

plugin_name = "mcp"

module_schema = Schema.object({})


class McpService(Service):
    """Owns the :class:`MCPContextManager` when MCP is configured."""

    def __init__(self, ctx: Any, name: str = "mcp") -> None:
        super().__init__(ctx, name)
        self.manager: MCPContextManager | None = None
        self.data_dir = ".mcp"

    @property
    def enabled(self) -> bool:
        return self.manager is not None

    def build(self, config: MCPConfig | None = None, data_dir: str | None = None) -> MCPContextManager | None:
        resolved = config if config is not None else self._config_from_app()
        if resolved is None:
            self.manager = None
            return None
        if data_dir:
            self.data_dir = data_dir
        if self.manager is None:
            self.manager = MCPContextManager(resolved, data_dir=self.data_dir)
        return self.manager

    def _config_from_app(self) -> MCPConfig | None:
        config_service = self.ctx.get("config")
        if config_service is None:
            return None
        return getattr(config_service, "mcp", None)


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    service = McpService(ctx, "mcp")
    if isinstance(config, dict):
        service.config = config
        service.data_dir = str(config.get("data_dir") or service.data_dir)
    ctx.service("mcp", service)
