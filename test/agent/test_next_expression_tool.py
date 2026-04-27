import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from internal.agent.tool.live2d import next_expression
from internal.agent.tool.live2d.next_expression import NextExpressionTool
from internal.websocket.client import SetExpression


async def test_next_expression_tool_wraps_after_configured_expression_count(monkeypatch):
    sent_messages = []

    async def fake_send_message(ws, msg_type, msg_id, data):
        sent_messages.append((ws, msg_type, msg_id, data))

    monkeypatch.setattr(next_expression, "send_message", fake_send_message)
    tool = NextExpressionTool(expression_count=2)

    await tool.execute(ws=object())
    await tool.execute(ws=object())
    await tool.execute(ws=object())

    assert [message[1] for message in sent_messages] == [SetExpression, SetExpression, SetExpression]
    assert [message[3].expId for message in sent_messages] == [0, 1, 0]


async def test_next_expression_tool_keeps_protocol_next_without_expression_count(monkeypatch):
    sent_messages = []

    async def fake_send_message(ws, msg_type, msg_id, data):
        sent_messages.append((ws, msg_type, msg_id, data))

    monkeypatch.setattr(next_expression, "send_message", fake_send_message)
    tool = NextExpressionTool()

    await tool.execute(ws=object())

    assert sent_messages[0][1] == next_expression.NextExpression
