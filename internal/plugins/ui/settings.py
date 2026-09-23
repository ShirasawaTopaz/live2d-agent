"""UI plugin: settings window (``ui/settings``)."""

from __future__ import annotations

from typing import Any, Callable

from internal.cordis import Schema, Service

plugin_name = "ui/settings"

module_schema = Schema.object({})


class SettingsService(Service):
    """Owns the settings window and routes config saves."""

    def __init__(self, ctx: Any, name: str = "ui/settings") -> None:
        super().__init__(ctx, name)
        self.widget: Any = None
        self.factory: Callable[..., Any] | None = None
        self.on_saved: Callable[..., Any] | None = None

    @property
    def attached(self) -> bool:
        return self.widget is not None

    def attach(self, widget: Any) -> Any:
        self.widget = widget
        return widget

    def create(self, config_path: str | None = None) -> Any:
        if self.widget is None:
            if self.factory is None:
                from internal.ui.settings_window import SettingsWindow

                self.factory = SettingsWindow
            path = config_path if config_path is not None else self._default_config_path()
            self.widget = self.factory(config_path=path, on_saved=self.on_saved)
        return self.widget

    @staticmethod
    def _default_config_path() -> str:
        from internal.config.config import Config

        return Config.DEFAULT_CONFIG_PATH

    def show(self, config_path: str | None = None) -> Any:
        widget = self.create(config_path)
        if widget is not None:
            widget.show()
            widget.raise_()
            widget.activateWindow()
        return widget

    def close(self) -> None:
        widget = self.widget
        self.widget = None
        if widget is not None and hasattr(widget, "close"):
            widget.close()


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    _ = config
    ctx.service("ui/settings", SettingsService(ctx, "ui/settings"))
