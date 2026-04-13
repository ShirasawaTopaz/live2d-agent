from internal.agent.tool.base import Tool
from internal.websocket.client import (
    TriggerMotion,
    Live2dTriggerAction,
    send_message,
)


class TriggerMotionTool(Tool):
    @property
    def name(self) -> str:
        return "trigger_motion"

    @property
    def description(self) -> str:
        return "触发 Live2D 模型的动作。当需要让模型执行特定动作时使用此工具。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "模型ID，默认为0"},
                "motion_name": {"type": "string", "description": "要触发的动作名称"},
            },
            "required": ["motion_name"],
        }

    async def execute(self, **kwargs) -> None:
        motion_data = Live2dTriggerAction(
            id=kwargs.get("id", 0),
            type=0,
            mtn=kwargs.get("motion_name", ""),
        )

        ws = kwargs.get("ws")
        if ws is None:
            return

        await send_message(ws, TriggerMotion, TriggerMotion, motion_data)
