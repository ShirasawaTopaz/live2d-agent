from dataclasses import dataclass
from internal.agent.tool.base import Tool
from internal.websocket.client import (
    NextExpression,
    SetExpression,
    Live2dSetExpression,
    send_message,
)


@dataclass(slots=True)
class Live2dNextExpression:
    id: int


class NextExpressionTool(Tool):
    def __init__(self, expression_count: int | None = None) -> None:
        # Keep rotation client-side when expression count is known, because some
        # Live2D services do not wrap NextExpression back to the first item.
        self._expression_count = expression_count if expression_count is not None and expression_count > 0 else None
        self._next_expression_id = 0

    def set_expression_count(self, expression_count: int | None) -> None:
        # Preserve the current cursor while keeping it valid after config reloads.
        self._expression_count = expression_count if expression_count is not None and expression_count > 0 else None
        if self._expression_count is not None:
            self._next_expression_id %= self._expression_count

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
        ws = kwargs.get("ws")
        if ws is None:
            return

        model_id = kwargs.get("id", 0)
        expression_count = kwargs.get("expression_count", self._expression_count)
        if isinstance(expression_count, int) and expression_count > 0:
            # Send an explicit SetExpression so the sequence is deterministic:
            # 0, 1, 0, 1... instead of relying on service-side NextExpression.
            expression_id = self._next_expression_id % expression_count
            self._next_expression_id = (expression_id + 1) % expression_count
            await send_message(
                ws,
                SetExpression,
                SetExpression,
                Live2dSetExpression(id=model_id, expId=expression_id),
            )
            return

        expression_data = Live2dNextExpression(id=model_id)

        await send_message(ws, NextExpression, NextExpression, expression_data)
