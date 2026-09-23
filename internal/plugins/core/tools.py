"""Core plugin: the tool registry (``ctx.tools``).

Tools are registered as effects, so unmounting this plugin (or any plugin that
contributed tools) removes them again. ``register_default_tools`` is still used
so the tool set stays defined in exactly one place.
"""

from __future__ import annotations

from typing import Any

from internal.cordis import Schema, Service
from internal.agent.register import ToolRegistry
from internal.agent.tool.dynamic.storage import DynamicToolStorage
from internal.agent.tool_setup import register_default_tools

plugin_name = "tools"

module_schema = Schema.object(
    {
        "dynamic_tools": Schema.boolean().default(True),
    }
)


class ToolsService(Service):
    """Owns the :class:`ToolRegistry` and the dynamic tool storage."""

    inject = ["sandbox"]

    def __init__(self, ctx: Any, name: str = "tools") -> None:
        super().__init__(ctx, name)
        self.registry = ToolRegistry()
        self.storage = DynamicToolStorage()
        self._load_dynamic = True

    def configure(self) -> ToolRegistry:
        sandbox = self.ctx.get("sandbox")
        middleware = getattr(sandbox, "middleware", sandbox)
        if self.registry.is_none:
            register_default_tools(self.registry, middleware, self.storage)
            if self._load_dynamic:
                self.registry.load_all_dynamic_tools(self.storage)
        return self.registry

    def register(self, tool: Any, owner: Any = None) -> Any:
        """Contribute a tool for the lifetime of the owning plugin.

        Pass the contributing plugin's context as ``owner`` so the tool is
        unregistered when that plugin unloads; without an owner the tool lives
        as long as the tools plugin itself.
        """
        disposer = self.registry.register_with_disposer(tool)
        target = owner if owner is not None else self.ctx
        target.effect(disposer)
        return disposer

    def definitions(self) -> list[dict[str, Any]] | None:
        if self.registry.is_none:
            return None
        return list(self.registry.get_definitions())

    def get(self, name: str) -> Any:
        return self.registry.tools.get(name)


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    service = ToolsService(ctx, "tools")
    if isinstance(config, dict) and config.get("dynamic_tools") is not None:
        service._load_dynamic = bool(config["dynamic_tools"])
    service.configure()
    ctx.service("tools", service)
