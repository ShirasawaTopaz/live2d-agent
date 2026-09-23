"""The minimal loop and the scrolling-text output must be swappable slots."""

from __future__ import annotations

import json
from pathlib import Path

from internal.plugins import app as plugin_app
from internal.plugins.agent.loop import DefaultAgentLoop
from internal.plugins.agent.loop_minimal import MinimalAgentLoop
from internal.plugins.outputs.typewriter import (
    BubbleChunk,
    PlainBubbleOutput,
    TypewriterBubbleOutput,
    typewriter_enabled,
)


class FakeModel:
    def __init__(self, reply: str = "hello") -> None:
        self.reply = reply
        self.calls: list[tuple[object, object]] = []

    async def chat(self, message=None, tools=None):  # noqa: ANN001
        self.calls.append((message, tools))
        return {"role": "assistant", "content": self.reply}


class FakeRegistry:
    is_none = True

    def get_definitions(self) -> list[dict]:
        return []


class FakeAgent:
    def __init__(self, reply: str = "hello") -> None:
        self.model = FakeModel(reply)
        self.tool_registry = FakeRegistry()
        self.max_tool_calls = 5

    async def chat(self, message=None, ws=None):  # noqa: ANN001
        _ = ws
        return await self.model.chat(message=message, tools=None)


def _tree(tmp_path: Path, loop_name: str, output_name: str) -> Path:
    tree = tmp_path / "cordis.json"
    tree.write_text(
        json.dumps(
            [
                {"id": "logger", "name": "internal.plugins.core.logger"},
                {"id": "bubble-widget", "name": "internal.plugins.ui.bubble_widget"},
                {"id": "loop", "name": loop_name},
                {"id": "output", "name": output_name},
            ]
        ),
        encoding="utf-8",
    )
    return tree


class FakeWidget:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.typewriter_starts: list[str] = []
        self.durations: list[int] = []
        self.shown = 0

    def clear(self) -> None:
        self.texts.clear()

    def show(self) -> None:
        self.shown += 1

    def set_text(self, text: str) -> None:
        self.texts.append(text)

    def show_with_duration(self, duration_ms: int) -> None:
        self.durations.append(duration_ms)

    def start_typewriter(self, text: str) -> None:
        self.typewriter_starts.append(text)


async def test_default_loop_delegates_to_agent(tmp_path: Path) -> None:
    tree = _tree(tmp_path, "internal.plugins.agent.loop", "internal.plugins.outputs.typewriter")
    context = await plugin_app.create_plugin_context(tree, watch=False)
    try:
        loop = context.ctx.get("agent/loop")
        assert isinstance(loop, DefaultAgentLoop)
        assert loop.max_tool_calls == 5

        agent = FakeAgent("pong")
        loop.attach_agent(agent)

        events: list[str] = []
        context.ctx.root.on("agent/chat/start", lambda _msg: events.append("start"))
        context.ctx.root.on("agent/chat/finished", lambda _res: events.append("finished"))

        result = await loop.run("ping", ws=None)

        assert result.content == "pong"
        assert events == ["start", "finished"]
    finally:
        await context.dispose()


async def test_minimal_loop_is_a_drop_in_replacement(tmp_path: Path) -> None:
    tree = _tree(
        tmp_path,
        "internal.plugins.agent.loop_minimal",
        "internal.plugins.outputs.typewriter",
    )
    context = await plugin_app.create_plugin_context(tree, watch=False)
    try:
        loop = context.ctx.get("agent/loop")
        assert isinstance(loop, MinimalAgentLoop)

        agent = FakeAgent("minimal reply")
        loop.attach_agent(agent)

        result = await loop.run("ping", ws=None)

        assert result.content == "minimal reply"
        assert agent.model.calls == [("ping", None)]
    finally:
        await context.dispose()


def test_typewriter_policy_prefers_timing_controller_when_voice_is_on() -> None:
    widget = FakeWidget()

    assert typewriter_enabled(widget, enabled=True, voice_client=None) is True
    assert typewriter_enabled(widget, enabled=False, voice_client=None) is False
    assert (
        typewriter_enabled(
            widget, enabled=True, voice_client=type("V", (), {"enabled": True})()
        )
        is False
    )
    assert typewriter_enabled(None, enabled=True, voice_client=None) is False


async def test_typewriter_output_streams_and_finishes(tmp_path: Path) -> None:
    tree = _tree(tmp_path, "internal.plugins.agent.loop", "internal.plugins.outputs.typewriter")
    context = await plugin_app.create_plugin_context(tree, watch=False)
    try:
        output = context.ctx.get("outputs/bubble")
        assert isinstance(output, TypewriterBubbleOutput)

        widget = FakeWidget()
        output.attach(widget)
        assert output.use_typewriter is True

        await output.begin(BubbleChunk(text=""))
        await output.stream(BubbleChunk(text="he"))
        await output.stream(BubbleChunk(text="hello"))
        await output.finish("hello", duration_ms=1000)

        assert widget.texts[-1] == "hello"
        assert widget.durations == [1000]
        assert output.start_scrolling("hello") is True
        assert widget.typewriter_starts == ["hello"]
    finally:
        await context.dispose()


async def test_plain_output_disables_scrolling(tmp_path: Path) -> None:
    tree = _tree(
        tmp_path,
        "internal.plugins.agent.loop",
        "internal.plugins.outputs.typewriter",
    )
    context = await plugin_app.create_plugin_context(tree, watch=False)
    try:
        widget = FakeWidget()
        plain = PlainBubbleOutput(context.ctx, "outputs/bubble")
        plain.attach(widget)

        assert plain.use_typewriter is False
        assert plain.start_scrolling("hello") is False
    finally:
        await context.dispose()


async def test_bubble_waterfall_can_rewrite_chunks(tmp_path: Path) -> None:
    tree = _tree(tmp_path, "internal.plugins.agent.loop", "internal.plugins.outputs.typewriter")
    context = await plugin_app.create_plugin_context(tree, watch=False)
    try:
        output = context.ctx.get("outputs/bubble")
        widget = FakeWidget()
        output.attach(widget)

        def upper(chunk, next):
            chunk.text = chunk.text.upper()
            return next()

        context.ctx.on("bubble/stream", upper)

        await output.stream(BubbleChunk(text="quiet"))

        assert widget.texts == ["QUIET"]
    finally:
        await context.dispose()
