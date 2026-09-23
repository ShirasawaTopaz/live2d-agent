"""Integration plugin: clipboard monitor (``integration/clipboard``)."""

from __future__ import annotations

from typing import Any, Callable

from internal.cordis import Schema, Service

plugin_name = "integration/clipboard"

module_schema = Schema.object({})


class ClipboardService(Service):
    """Owns the clipboard monitor and its action callback."""

    def __init__(self, ctx: Any, name: str = "integration/clipboard") -> None:
        super().__init__(ctx, name)
        self.monitor: Any = None
        self.factory: Callable[[], Any] | None = None
        self.on_action: Callable[..., Any] | None = None

    @property
    def attached(self) -> bool:
        return self.monitor is not None

    def attach(self, monitor: Any) -> Any:
        self.monitor = monitor
        if self.on_action is not None and hasattr(monitor, "set_on_action"):
            monitor.set_on_action(self.on_action)
        return monitor

    def create(self) -> Any:
        if self.monitor is None:
            if self.factory is None:
                from internal.integration import ClipboardMonitor

                self.factory = ClipboardMonitor
            self.attach(self.factory())
        return self.monitor

    def start(self) -> bool:
        monitor = self.create()
        if monitor is None or not hasattr(monitor, "set_enabled"):
            return False
        monitor.set_enabled(True)
        return True

    def stop(self) -> None:
        monitor = self.monitor
        self.monitor = None
        if monitor is not None and hasattr(monitor, "set_enabled"):
            monitor.set_enabled(False)


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    _ = config
    service = ClipboardService(ctx, "integration/clipboard")
    ctx.service("integration/clipboard", service)
    ctx.effect(service.stop)
