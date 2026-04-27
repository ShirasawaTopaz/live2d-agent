import asyncio
import sys
from types import SimpleNamespace

from internal.app import bootstrap


class FakeQApplication:
    def __init__(self, argv: list[str]) -> None:
        self.argv: list[str] = list(argv)
        self.quit_on_last_window_closed: bool | None = None
        self.style: str | None = None
        self.application_name: str | None = None
        self.application_display_name: str | None = None

    def setQuitOnLastWindowClosed(self, value: bool) -> None:
        self.quit_on_last_window_closed = value

    def setStyle(self, style: str) -> None:
        self.style = style

    def setApplicationName(self, name: str) -> None:
        self.application_name = name

    def setApplicationDisplayName(self, name: str) -> None:
        self.application_display_name = name


class FakeInputBox:
    def __init__(self, *, agent: object, title: str) -> None:
        self.agent = agent
        self.title = title
        self._theme: str = "midnight"


class FakeBubbleWidget:
    def __init__(self) -> None:
        self.theme: str | None = None

    def set_theme(self, theme: str) -> None:
        self.theme = theme


class FailingWebSocket:
    def __init__(self, url: str, backoff, max_reconnect_attempts: int) -> None:
        self.url = url
        self.backoff = backoff
        self.max_reconnect_attempts = max_reconnect_attempts
        self.on_connect = None
        self.on_disconnect = None

    async def connect(self) -> None:
        raise ConnectionError("unavailable")


def test_load_startup_resources_loads_config_and_prompts(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_config_load():
        calls.append("config")
        return SimpleNamespace(live2dSocket="ws://example")

    async def fake_prompt_load():
        calls.append("prompts")

    monkeypatch.setattr(bootstrap.Config, "load", fake_config_load)
    monkeypatch.setattr(bootstrap.PromptManager, "load", fake_prompt_load)

    async def scenario() -> None:
        config = await bootstrap.load_startup_resources()

        assert config.live2dSocket == "ws://example"
        assert calls == ["config", "prompts"]

    asyncio.run(scenario())


def test_create_qt_application_sets_expected_properties(monkeypatch) -> None:
    monkeypatch.setattr(
        bootstrap,
        "import_module",
        lambda _name: SimpleNamespace(QApplication=FakeQApplication),
    )

    qt_app = bootstrap.create_qt_application()

    assert qt_app.argv == list(sys.argv)
    assert qt_app.quit_on_last_window_closed is False
    assert qt_app.style == "Fusion"
    assert qt_app.application_name == "Live2oder"
    assert qt_app.application_display_name == "Live2oder Agent"


def test_create_ui_components_wires_agent_and_theme(monkeypatch) -> None:
    agent = SimpleNamespace()
    monkeypatch.setattr(bootstrap, "FloatingInputBox", FakeInputBox)
    monkeypatch.setattr(bootstrap, "BubbleWidget", FakeBubbleWidget)

    input_box, bubble_widget = bootstrap.create_ui_components(agent)

    assert input_box.agent is agent
    assert getattr(input_box, "title") == "Agent Chat"
    assert getattr(bubble_widget, "theme") == "midnight"
    assert agent.bubble_widget is bubble_widget


def test_configure_websocket_callbacks_sets_handlers() -> None:
    config = bootstrap.Config()
    config.live2dSocket = "ws://example"
    websocket = bootstrap.ReconnectingWebSocket(url=config.live2dSocket)

    bootstrap.configure_websocket_callbacks(websocket, config)

    assert callable(websocket.on_connect)
    assert callable(websocket.on_disconnect)


def test_create_websocket_propagates_connect_failure(monkeypatch) -> None:
    config = bootstrap.Config()
    config.live2dSocket = "ws://example"
    monkeypatch.setattr(bootstrap, "ReconnectingWebSocket", FailingWebSocket)

    async def scenario() -> None:
        try:
            await bootstrap.create_websocket(config)
        except ConnectionError as exc:
            assert str(exc) == "unavailable"
        else:
            raise AssertionError("ConnectionError not raised")

    asyncio.run(scenario())


def test_bootstrap_application_uses_split_helpers(monkeypatch) -> None:
    config = SimpleNamespace(live2dSocket="ws://example")
    qt_app = SimpleNamespace()
    websocket = SimpleNamespace()
    agent = SimpleNamespace()
    input_box = SimpleNamespace()
    bubble_widget = SimpleNamespace()
    calls: list[str] = []

    async def fake_load_startup_resources():
        calls.append("load")
        return config

    def fake_create_qt_application():
        calls.append("qt")
        return qt_app

    async def fake_create_websocket(received_config):
        calls.append("websocket")
        assert received_config is config
        return websocket

    def fake_create_runtime_agent(received_config):
        calls.append("agent")
        assert received_config is config
        return agent

    def fake_create_ui_components(received_agent):
        calls.append("ui")
        assert received_agent is agent
        return input_box, bubble_widget

    monkeypatch.setattr(bootstrap, "load_startup_resources", fake_load_startup_resources)
    monkeypatch.setattr(bootstrap, "create_qt_application", fake_create_qt_application)
    monkeypatch.setattr(bootstrap, "create_websocket", fake_create_websocket)
    monkeypatch.setattr(bootstrap, "create_runtime_agent", fake_create_runtime_agent)
    monkeypatch.setattr(bootstrap, "create_ui_components", fake_create_ui_components)

    async def scenario() -> None:
        context = await bootstrap.bootstrap_application()

        assert context.config is config
        assert context.qt_app is qt_app
        assert context.websocket is websocket
        assert context.agent is agent
        assert context.input_box is input_box
        assert context.bubble_widget is bubble_widget
        assert calls == ["load", "qt", "agent", "websocket", "ui"]

    asyncio.run(scenario())


def test_bootstrap_application_stops_before_websocket_when_agent_creation_fails(monkeypatch) -> None:
    config = SimpleNamespace(live2dSocket="ws://example")
    qt_app = SimpleNamespace()
    calls: list[str] = []

    async def fake_load_startup_resources():
        calls.append("load")
        return config

    def fake_create_qt_application():
        calls.append("qt")
        return qt_app

    def fake_create_runtime_agent(received_config):
        calls.append("agent")
        assert received_config is config
        raise ValueError("No model configuration found. Please check your config.json file.")

    async def fake_create_websocket(_received_config):
        calls.append("websocket")
        raise AssertionError("websocket should not be created when agent creation fails")

    monkeypatch.setattr(bootstrap, "load_startup_resources", fake_load_startup_resources)
    monkeypatch.setattr(bootstrap, "create_qt_application", fake_create_qt_application)
    monkeypatch.setattr(bootstrap, "create_runtime_agent", fake_create_runtime_agent)
    monkeypatch.setattr(bootstrap, "create_websocket", fake_create_websocket)

    async def scenario() -> None:
        try:
            await bootstrap.bootstrap_application()
        except ValueError as exc:
            assert "No model configuration found" in str(exc)
        else:
            raise AssertionError("ValueError not raised")

        assert calls == ["load", "qt", "agent"]

    asyncio.run(scenario())
