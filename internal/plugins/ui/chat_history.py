"""UI plugin: chat history window (``ui/chat-history``)."""

from __future__ import annotations

from typing import Any, Callable

from internal.cordis import Schema, Service

plugin_name = "ui/chat-history"

module_schema = Schema.object({})


class ChatHistoryService(Service):
    """Owns the conversation history window."""

    def __init__(self, ctx: Any, name: str = "ui/chat-history") -> None:
        super().__init__(ctx, name)
        self.widget: Any = None
        self.factory: Callable[[], Any] | None = None

    @property
    def attached(self) -> bool:
        return self.widget is not None

    def attach(self, widget: Any) -> Any:
        self.widget = widget
        return widget

    def create(self) -> Any:
        if self.widget is None:
            if self.factory is None:
                from internal.ui.chat_history_window import ChatHistoryWindow

                self.factory = ChatHistoryWindow
            self.widget = self.factory()
        return self.widget

    def add_message(self, message: dict[str, Any]) -> None:
        if self.widget is not None and hasattr(self.widget, "add_message"):
            self.widget.add_message(message)

    def show(self) -> None:
        if self.widget is None:
            return
        self.widget.show()
        self.widget.raise_()
        self.widget.activateWindow()

    def stop(self) -> None:
        widget = self.widget
        self.widget = None
        if widget is not None and hasattr(widget, "close"):
            widget.close()


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    _ = config
    service = ChatHistoryService(ctx, "ui/chat-history")
    ctx.service("ui/chat-history", service)
    ctx.effect(service.stop)
