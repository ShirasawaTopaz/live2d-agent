"""UI plugin: speech bubble widget (``ui/bubble-widget``).

The bubble window is the rendering surface for the scrolling-text output
plugin. This plugin owns its lifetime; ``outputs/bubble`` only needs the widget
handle, which keeps both slots independently replaceable.
"""

from __future__ import annotations

from typing import Any, Callable

from internal.cordis import Schema, Service

plugin_name = "ui/bubble-widget"

module_schema = Schema.object({})


class BubbleWidgetService(Service):
    """Owns the Qt bubble widget handed to the output plugin."""

    def __init__(self, ctx: Any, name: str = "ui/bubble-widget") -> None:
        super().__init__(ctx, name)
        self.widget: Any = None
        self.factory: Callable[[], Any] | None = None

    @property
    def attached(self) -> bool:
        return self.widget is not None

    def attach(self, widget: Any) -> Any:
        self.widget = widget
        self.ctx.root.emit("ui/bubble-widget/attached", widget)
        return widget

    def create(self) -> Any:
        if self.widget is None:
            if self.factory is None:
                from internal.ui import BubbleWidget

                self.factory = BubbleWidget
            self.widget = self.factory()
        return self.widget

    def set_theme(self, theme: str) -> None:
        if self.widget is not None and hasattr(self.widget, "set_theme"):
            self.widget.set_theme(theme)

    def save_position(self) -> None:
        if self.widget is not None and hasattr(self.widget, "save_position"):
            self.widget.save_position()

    def stop(self) -> None:
        widget = self.widget
        self.widget = None
        if widget is not None and hasattr(widget, "close"):
            widget.close()


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    _ = config
    service = BubbleWidgetService(ctx, "ui/bubble-widget")
    ctx.service("ui/bubble-widget", service)
    ctx.effect(service.stop)
