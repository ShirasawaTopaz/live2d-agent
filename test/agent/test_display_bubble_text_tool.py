import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from internal.agent.tool.live2d import display_bubble_text
from internal.agent.tool.live2d.display_bubble_text import DisplayBubbleTextTool
from internal.websocket.client import SetExpression


class FakeBubbleTiming:
    def __init__(self):
        self.calls = []

    async def display_text(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return kwargs.get("duration", 0)


async def test_display_bubble_text_tool_wraps_expression_rotation(monkeypatch):
    sent_messages = []

    async def fake_send_message(ws, msg_type, msg_id, data):
        sent_messages.append((msg_type, msg_id, data))

    monkeypatch.setattr(display_bubble_text, "send_message", fake_send_message)
    tool = DisplayBubbleTextTool(expression_count=2)

    await tool.execute(ws=object(), text="one", duration=1)
    await tool.execute(ws=object(), text="two", duration=1)
    await tool.execute(ws=object(), text="three", duration=1)

    expression_messages = [message for message in sent_messages if message[0] == SetExpression]
    assert [message[2].expId for message in expression_messages] == [0, 1, 0]


async def test_display_bubble_text_tool_does_not_rotate_when_expressions_disabled(monkeypatch):
    sent_messages = []

    async def fake_send_message(ws, msg_type, msg_id, data):
        sent_messages.append((msg_type, msg_id, data))

    monkeypatch.setattr(display_bubble_text, "send_message", fake_send_message)
    tool = DisplayBubbleTextTool(expression_count=2, expressions_enabled=False)

    await tool.execute(ws=object(), text="hello", duration=1)

    expression_messages = [message for message in sent_messages if message[0] == SetExpression]
    assert expression_messages == []
    assert sent_messages[-1][0] == display_bubble_text.DisplayBubbleText


async def test_display_bubble_text_tool_uses_bubble_timing_when_available(monkeypatch):
    sent_messages = []

    async def fake_send_message(ws, msg_type, msg_id, data):
        sent_messages.append((msg_type, msg_id, data))

    monkeypatch.setattr(display_bubble_text, "send_message", fake_send_message)
    bubble_timing = FakeBubbleTiming()
    tool = DisplayBubbleTextTool(expression_count=2)

    await tool.execute(
        ws=object(),
        text="hello",
        duration=1234,
        choices=["A", "B"],
        bubble_timing=bubble_timing,
        bubble_widget=object(),
    )

    assert sent_messages == []
    assert len(bubble_timing.calls) == 1
    args, kwargs = bubble_timing.calls[0]
    assert args[0] == "hello"
    assert kwargs["duration"] == 1234
    assert kwargs["rotate_expression"] is True
    assert kwargs["choices"] == ["A", "B"]
