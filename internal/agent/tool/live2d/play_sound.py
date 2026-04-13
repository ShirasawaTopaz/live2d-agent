from internal.agent.tool.base import Tool
from internal.websocket.client import (
    SetModelPlaySound,
    Live2dPlaySound,
    send_message,
)


class PlaySoundTool(Tool):
    @property
    def name(self) -> str:
        return "play_sound"

    @property
    def description(self) -> str:
        return "播放音效。当需要播放声音效果时使用此工具。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "模型ID，默认为0"},
                "sound": {"type": "string", "description": "音效文件路径"},
                "channel": {"type": "integer", "description": "声道，默认为0"},
                "volume": {"type": "number", "description": "音量，默认为1.0"},
                "delay": {"type": "integer", "description": "延迟毫秒，默认为0"},
                "loop": {"type": "boolean", "description": "是否循环播放，默认为false"},
            },
            "required": ["sound"],
        }

    async def execute(self, **kwargs) -> None:
        sound_data = Live2dPlaySound(
            id=kwargs.get("id", 0),
            channel=kwargs.get("channel", 0),
            volume=kwargs.get("volume", 1.0),
            delay=kwargs.get("delay", 0),
            loop=kwargs.get("loop", False),
            type=0,
            sound=kwargs.get("sound", ""),
        )

        ws = kwargs.get("ws")
        if ws is None:
            return

        await send_message(ws, SetModelPlaySound, SetModelPlaySound, sound_data)
