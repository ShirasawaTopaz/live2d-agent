"""UI and integration plugins are attach-based, so they test without Qt."""

from __future__ import annotations


from internal.cordis import FiberState
from internal.plugins import app as plugin_app


class FakeWidget:
    def __init__(self) -> None:
        self.closed = False
        self.shown = 0
        self.raised = 0
        self.activated = 0
        self.theme = ""
        self.messages: list[dict] = []

    def show(self) -> None:
        self.shown += 1

    def raise_(self) -> None:
        self.raised += 1

    def activateWindow(self) -> None:
        self.activated += 1

    def hide(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    def set_theme(self, theme: str) -> None:
        self.theme = theme

    def add_message(self, message: dict) -> None:
        self.messages.append(message)


class FakeInputBox(FakeWidget):
    def __init__(self) -> None:
        super().__init__()
        self.agent = None

    def set_agent(self, agent) -> None:  # noqa: ANN001
        self.agent = agent


class FakeHotkeyManager:
    def __init__(self) -> None:
        self.registered: dict[str, object] = {}

    def register(self, combo: str, callback) -> None:  # noqa: ANN001
        self.registered[combo] = callback

    def unregister(self, combo: str) -> None:
        self.registered.pop(combo, None)


class FakeClipboard:
    def __init__(self) -> None:
        self.enabled = False
        self.on_action = None

    def set_on_action(self, callback) -> None:  # noqa: ANN001
        self.on_action = callback

    def set_enabled(self, value: bool) -> None:
        self.enabled = value


async def test_ui_plugins_attach_and_release_widgets() -> None:
    context = await plugin_app.create_plugin_context(watch=False)
    try:
        ctx = context.ctx
        bubble = ctx.get("ui/bubble-widget")
        widget = FakeWidget()
        bubble.attach(widget)

        assert bubble.attached is True
        bubble.set_theme("midnight")
        assert widget.theme == "midnight"

        output = ctx.get("outputs/bubble")
        output.attach()
        assert output.widget is widget

        input_box = ctx.get("ui/input-box")
        fake_input = FakeInputBox()
        input_box.attach(fake_input)
        input_box.show()
        assert fake_input.shown == 1
        assert fake_input.raised == 1
    finally:
        await context.dispose()


async def test_ui_plugin_close_is_an_effect() -> None:
    context = await plugin_app.create_plugin_context(watch=False)
    ctx = context.ctx
    widget = FakeWidget()
    ctx.get("ui/chat-history").attach(widget)
    history = ctx.get("ui/chat-history")
    assert history is not None

    entry_state = {entry["id"]: entry["state"] for entry in context.loader.report()}
    assert entry_state["chat-history"] == FiberState.ACTIVE.value

    await context.dispose()
    assert widget.closed is True


async def test_hotkey_plugin_binds_after_attach() -> None:
    context = await plugin_app.create_plugin_context(watch=False)
    try:
        hotkeys = context.ctx.get("integration/hotkey")
        calls: list[str] = []
        hotkeys.bind("ctrl+alt+s", lambda: calls.append("summon"))
        assert hotkeys.register("ctrl+alt+s", lambda: calls.append("summon")) is False

        manager = FakeHotkeyManager()
        hotkeys.attach(manager)

        assert "ctrl+alt+s" in manager.registered
        manager.registered["ctrl+alt+s"]()
        assert calls == ["summon"]
    finally:
        await context.dispose()


async def test_clipboard_plugin_toggles_monitor() -> None:
    context = await plugin_app.create_plugin_context(watch=False)
    try:
        clipboard = context.ctx.get("integration/clipboard")
        monitor = FakeClipboard()
        clipboard.attach(monitor)
        clipboard.on_action = lambda action, text: None
        clipboard.attach(monitor)

        assert clipboard.start() is True
        assert monitor.enabled is True
        assert monitor.on_action is not None

        clipboard.stop()
        assert monitor.enabled is False
    finally:
        await context.dispose()


async def test_scheduler_reads_tray_from_store() -> None:
    context = await plugin_app.create_plugin_context(watch=False)
    try:
        ctx = context.ctx
        tray = ctx.get("ui/tray")
        icon = FakeWidget()
        tray.attach(icon)

        assert ctx.store["tray_icon"] is icon
        scheduler = ctx.get("scheduler")
        assert scheduler is not None
        assert scheduler.enabled is False
    finally:
        await context.dispose()


async def test_browser_tools_are_contributed_as_effects() -> None:
    context = await plugin_app.create_plugin_context(watch=False)
    try:
        ctx = context.ctx
        browser = ctx.get("integration/browser")
        registry = ctx.get("tools").registry

        browser.register_tools = False
        assert browser.contribute_tools() == 0

        browser.register_tools = True
        owner = ctx.extend(name="browser-contributor")

        class StubTool:
            def __init__(self, name: str) -> None:
                self.name = name
                self.description = name
                self.parameters = {"type": "object", "properties": {}}

        class FakeController:
            def close(self) -> None:
                pass

            async def open(self, url: str = "") -> str:
                return url

            async def extract(self) -> str:
                return ""

            async def click(self, selector: str = "") -> str:
                return selector

            async def type_text(self, selector: str = "", text: str = "") -> str:
                return text

            async def search(self, query: str = "") -> str:
                return query

            async def scroll(self, direction: str = "down") -> str:
                return direction

            async def close_browser(self) -> str:
                return "closed"

            def get_tools(self) -> list:
                return [StubTool("browser_scroll")]

        browser.attach(FakeController())
        assert browser.contribute_tools(owner) == 1
        assert "browser_scroll" in registry.tools

        await owner.dispose()
        assert "browser_scroll" not in registry.tools
    finally:
        await context.dispose()
