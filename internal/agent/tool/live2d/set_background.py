from internal.agent.tool.base import Tool
from internal.websocket.client import (
    SetBackground,
    Live2dSetBackground,
    send_message,
)


class SetBackgroundTool(Tool):
    @property
    def name(self) -> str:
        return "set_background"

    @property
    def description(self) -> str:
        return "设置 Live2D 背景图片。当需要更改背景时使用此工具。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "背景ID，默认为0"},
                "file": {"type": "string", "description": "背景图片文件路径"},
            },
            "required": ["file"],
        }

    async def execute(self, **kwargs) -> None:
        background_data = Live2dSetBackground(
            id=kwargs.get("id", 0),
            file=kwargs.get("file", ""),
        )

        ws = kwargs.get("ws")
        if ws is None:
            return

        await send_message(ws, SetBackground, SetBackground, background_data)
