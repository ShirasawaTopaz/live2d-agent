import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from internal.agent.tool.live2d import display_bubble_text
from internal.agent.tool.live2d.display_bubble_text import DisplayBubbleTextTool
from internal.websocket.client import SetExpression


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
