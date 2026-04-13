from internal.agent.tool.base import Tool
from internal.websocket.client import (
    SetExpression,
    Live2dSetExpression,
    send_message,
)


class SetExpressionTool(Tool):
    @property
    def name(self) -> str:
        return "set_expression"

    @property
    def description(self) -> str:
        return "设置 Live2D 模型的表情。当需要让模型显示特定表情时使用此工具。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "模型ID，默认为0"},
                "expression_id": {"type": "integer", "description": "要设置的表情ID"},
            },
            "required": ["expression_id"],
        }

    async def execute(self, **kwargs) -> None:
        expression_data = Live2dSetExpression(
            id=kwargs.get("id", 0),
            expId=kwargs.get("expression_id", 0),
        )

        ws = kwargs.get("ws")
        if ws is None:
            return

        await send_message(ws, SetExpression, SetExpression, expression_data)
