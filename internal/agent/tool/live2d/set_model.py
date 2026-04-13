from internal.agent.tool.base import Tool
from internal.websocket.client import (
    SetModel,
    Live2dSetModel,
    send_message,
)


class SetModelTool(Tool):
    @property
    def name(self) -> str:
        return "set_model"

    @property
    def description(self) -> str:
        return "切换 Live2D 模型。当需要加载并显示不同的 Live2D 模型时使用此工具。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "模型ID，默认为0"},
                "file": {"type": "string", "description": "Live2D 模型文件路径"},
            },
            "required": ["file"],
        }

    async def execute(self, **kwargs) -> None:
        model_data = Live2dSetModel(
            id=kwargs.get("id", 0),
            file=kwargs.get("file", ""),
        )

        ws = kwargs.get("ws")
        if ws is None:
            return

        await send_message(ws, SetModel, SetModel, model_data)
