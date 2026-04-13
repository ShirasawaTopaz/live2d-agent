from dataclasses import dataclass
from internal.agent.tool.base import Tool
from internal.websocket.client import (
    NextExpression,
    send_message,
)


@dataclass(slots=True)
class Live2dNextExpression:
    id: int


class NextExpressionTool(Tool):
    @property
    def name(self) -> str:
        return "next_expression"

    @property
    def description(self) -> str:
        return "切换 Live2D 模型到下一个表情。当需要轮播表情时使用此工具。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "模型ID，默认为0"},
            },
            "required": [],
        }

    async def execute(self, **kwargs) -> None:
        expression_data = Live2dNextExpression(
            id=kwargs.get("id", 0),
        )

        ws = kwargs.get("ws")
        if ws is None:
            return

        await send_message(ws, NextExpression, NextExpression, expression_data)
