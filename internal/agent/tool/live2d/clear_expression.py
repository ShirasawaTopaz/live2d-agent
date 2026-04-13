from dataclasses import dataclass
from internal.agent.tool.base import Tool
from internal.websocket.client import (
    ClearExpression,
    send_message,
)


@dataclass(slots=True)
class Live2dClearExpression:
    id: int


class ClearExpressionTool(Tool):
    @property
    def name(self) -> str:
        return "clear_expression"

    @property
    def description(self) -> str:
        return "清除 Live2D 模型的所有表情。当需要清除当前所有表情恢复默认状态时使用此工具。"

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
        expression_data = Live2dClearExpression(
            id=kwargs.get("id", 0),
        )

        ws = kwargs.get("ws")
        if ws is None:
            return

        await send_message(ws, ClearExpression, ClearExpression, expression_data)
