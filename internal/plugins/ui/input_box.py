"""UI plugin: floating input box (``ui/input-box``).

Qt widgets must be created on the GUI thread, so the service constructs the
widget lazily through a factory and can adopt an instance the legacy bootstrap
already created (``attach``). Every plugin that owns a widget closes it as an
effect, so unloading a UI plugin releases the window.
"""

from __future__ import annotations

from typing import Any, Callable

from internal.cordis import Schema, Service

plugin_name = "ui/input-box"

module_schema = Schema.object({})


class InputBoxService(Service):
    """Owns the application's floating input widget."""

    def __init__(self, ctx: Any, name: str = "ui/input-box") -> None:
        super().__init__(ctx, name)
        self.widget: Any = None
        self.factory: Callable[..., Any] | None = None

    @property
    def attached(self) -> bool:
        return self.widget is not None

    def attach(self, widget: Any) -> Any:
        self.widget = widget
        return widget

    def create(self, **kwargs: Any) -> Any:
        if self.widget is None:
            if self.factory is None:
                from internal.ui import FloatingInputBox

                self.factory = FloatingInputBox
            self.widget = self.factory(**kwargs)
        return self.widget

    def show(self) -> None:
        if self.widget is None:
            return
        self.widget.show()
        self.widget.raise_()
        self.widget.activateWindow()

    def hide(self) -> None:
        if self.widget is not None:
            self.widget.hide()

    def set_agent(self, agent: Any) -> None:
        if self.widget is not None and hasattr(self.widget, "set_agent"):
            self.widget.set_agent(agent)

    def stop(self) -> None:
        widget = self.widget
        self.widget = None
        if widget is not None and hasattr(widget, "close"):
            widget.close()


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    _ = config
    service = InputBoxService(ctx, "ui/input-box")
    ctx.service("ui/input-box", service)
    ctx.effect(service.stop)
