import asyncio
from types import SimpleNamespace

from internal.app.live2d_agent_app import Live2DAgentApp


class FakeModel:
    def __init__(self) -> None:
        self.history = [{"role": "assistant", "content": "old"}]
        self._system_prompt_resolved = False

    async def _resolve_system_prompt(self) -> str:
        return "resolved system prompt"


class FakeMemory:
    def __init__(self) -> None:
        self._initialized = True
        self.reset_calls: list[str | None] = []
        self.messages: list[dict[str, str]] = []

    async def reset_active_context(self, title: str | None = None) -> None:
        self.reset_calls.append(title)
        self.messages = []

    def add_message(self, message: dict[str, str]) -> None:
        self.messages.append(message)

    async def get_current_messages(self) -> list[dict[str, str]]:
        return list(self.messages)


class FakeAgent:
    def __init__(self) -> None:
        self.model = FakeModel()
        self.memory = FakeMemory()

    async def initialize_memory(self) -> None:
        self.memory._initialized = True


def test_reset_context_preserves_system_prompt() -> None:
    async def scenario() -> None:
        app = Live2DAgentApp()
        app.agent = FakeAgent()
        cleared = []
        app.input_box = SimpleNamespace(clear_input=lambda: cleared.append(True))

        await app.reset_context()

        assert app.agent.memory.reset_calls == ["default"]
        assert app.agent.model.history == []
        assert app.agent.model._system_prompt_resolved is False
        assert app.agent.memory.messages == []
        assert cleared == [True]

    asyncio.run(scenario())


def test_initialize_applies_bootstrap_context_and_wires_runtime(monkeypatch) -> None:
    app = Live2DAgentApp()
    config = SimpleNamespace(live2dSocket="ws://example")
    qt_app = SimpleNamespace()
    websocket = SimpleNamespace()
    agent = SimpleNamespace()
    input_box = SimpleNamespace(
        message_sent=SimpleNamespace(connect=lambda _fn: None),
        visibility_changed=SimpleNamespace(connect=lambda _fn: None),
        close_requested=SimpleNamespace(connect=lambda _fn: None),
        clear_context_requested=SimpleNamespace(connect=lambda _fn: None),
    )
    bubble_widget = SimpleNamespace()
    context = SimpleNamespace(
        config=config,
        qt_app=qt_app,
        websocket=websocket,
        agent=agent,
        input_box=input_box,
        bubble_widget=bubble_widget,
    )
    shown: list[bool] = []
    tray_calls: list[tuple[object, object]] = []
    attached: list[object] = []

    async def fake_bootstrap_application():
        return context

    monkeypatch.setattr("internal.app.bootstrap.bootstrap_application", fake_bootstrap_application)
    monkeypatch.setattr(
        "internal.app.live2d_agent_app.connect_input_signals",
        lambda _input_box, **_kwargs: None,
    )
    monkeypatch.setattr("internal.app.tray.create_tray_icon", lambda **kwargs: tray_calls.append((kwargs["qt_app"], kwargs["input_box"])) or SimpleNamespace())
    monkeypatch.setattr("internal.app.tray.setup_window_position", lambda qt_app_arg, input_box_arg: tray_calls.append((qt_app_arg, input_box_arg)))
    monkeypatch.setattr(app, "show_input_box", lambda: shown.append(True))
    monkeypatch.setattr(app.runtime_state, "attach", lambda websocket_arg: attached.append(websocket_arg))

    async def scenario() -> None:
        await app.initialize()

        assert app.config is config
        assert app.qt_app is qt_app
        assert app.ws is websocket
        assert app.agent is agent
        assert app.input_box is input_box
        assert app.bubble_widget is bubble_widget
        assert attached == [websocket]
        assert shown == [True]
        assert tray_calls == [(qt_app, input_box), (qt_app, input_box)]

    asyncio.run(scenario())


def test_initialize_propagates_bootstrap_failure_without_partial_show(monkeypatch) -> None:
    app = Live2DAgentApp()
    shown: list[bool] = []

    async def fake_bootstrap_application():
        raise RuntimeError("bootstrap failed")

    monkeypatch.setattr("internal.app.bootstrap.bootstrap_application", fake_bootstrap_application)
    monkeypatch.setattr(app, "show_input_box", lambda: shown.append(True))

    async def scenario() -> None:
        try:
            await app.initialize()
        except RuntimeError as exc:
            assert str(exc) == "bootstrap failed"
        else:
            raise AssertionError("RuntimeError not raised")

        assert shown == []

    asyncio.run(scenario())
