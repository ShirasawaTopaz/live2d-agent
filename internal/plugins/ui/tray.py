"""UI plugin: system tray icon (``ui/tray``).

The tray icon is also the notification surface used by the scheduler plugin,
which reads it from ``ctx.store`` instead of holding a hard reference.
"""

from __future__ import annotations

from typing import Any, Callable

from internal.cordis import Schema, Service

plugin_name = "ui/tray"

module_schema = Schema.object({})


class TrayService(Service):
    """Owns the tray icon and exposes it to other plugins."""

    def __init__(self, ctx: Any, name: str = "ui/tray") -> None:
        super().__init__(ctx, name)
        self.icon: Any = None
        self.factory: Callable[..., Any] | None = None

    @property
    def attached(self) -> bool:
        return self.icon is not None

    def attach(self, icon: Any) -> Any:
        self.icon = icon
        self.ctx.store["tray_icon"] = icon
        return icon

    def create(self, **kwargs: Any) -> Any:
        if self.icon is None:
            if self.factory is None:
                from internal.app.tray import create_tray_icon

                self.factory = create_tray_icon
            self.attach(self.factory(**kwargs))
        return self.icon

    def stop(self) -> None:
        icon = self.icon
        self.icon = None
        self.ctx.store.pop("tray_icon", None)
        if icon is not None and hasattr(icon, "hide"):
            icon.hide()


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    _ = config
    service = TrayService(ctx, "ui/tray")
    ctx.service("ui/tray", service)
    ctx.effect(service.stop)
