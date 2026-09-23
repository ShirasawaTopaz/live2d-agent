"""Integration plugin: browser automation (``integration/browser``).

Browser tools are contributed through the tool registry instead of being wired
into the agent, so they appear and disappear with this plugin.
"""

from __future__ import annotations

from typing import Any

from internal.cordis import Schema, Service

plugin_name = "integration/browser"

module_schema = Schema.object(
    {
        "headless": Schema.boolean().default(True),
        "register_tools": Schema.boolean().default(True),
    }
)


class BrowserService(Service):
    """Owns the Playwright browser controller."""

    inject = ["tools"]

    def __init__(self, ctx: Any, name: str = "integration/browser") -> None:
        super().__init__(ctx, name)
        self.controller: Any = None
        self.headless = True
        self.register_tools = True

    @property
    def attached(self) -> bool:
        return self.controller is not None

    def attach(self, controller: Any) -> Any:
        self.controller = controller
        return controller

    def create(self) -> Any:
        if self.controller is None:
            from internal.integration.browser import BrowserController

            self.controller = BrowserController(headless=self.headless)
        return self.controller

    def contribute_tools(self, owner: Any = None) -> int:
        """Register the browser tools on the tool registry as an effect."""
        if not self.register_tools:
            return 0
        controller = self.create()
        from internal.integration.browser import register_browser_tools

        tools = self.ctx.get("tools")
        if tools is None:
            return 0
        registry = tools.registry
        before = set(registry.tools)
        register_browser_tools(controller, registry)
        added = sorted(set(registry.tools) - before)

        def disposer() -> None:
            for name in added:
                registry.unregister(name)

        target = owner if owner is not None else self.ctx
        target.effect(disposer)
        return len(added)

    async def stop(self) -> None:
        controller = self.controller
        self.controller = None
        if controller is None:
            return
        close = getattr(controller, "close", None)
        if callable(close):
            result = close()
            if hasattr(result, "__await__"):
                await result

    def dispose(self) -> None:
        """Effect-compatible teardown: schedule ``stop`` on the kernel loop."""
        controller = self.controller
        if controller is None:
            return
        close = getattr(controller, "close", None)
        if not callable(close):
            self.controller = None
            return
        result = close()
        if hasattr(result, "__await__"):
            self.ctx.spawn(result)
        self.controller = None


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    service = BrowserService(ctx, "integration/browser")
    if isinstance(config, dict):
        service.headless = bool(config.get("headless", True))
        service.register_tools = bool(config.get("register_tools", True))
    ctx.service("integration/browser", service)
    ctx.effect(service.dispose)
