import time
import asyncio
from internal.agent.tool.base import Tool
from internal.websocket.client import (
    DisplayBubbleText,
    Live2dDisplayBubbleText,
    send_message,
)


class DisplayBubbleTextTool(Tool):
    # 气泡显示时间管理
    _last_bubble_time: float = 0.0  # 最后一次气泡显示开始时间
    _last_bubble_duration: float = 0.0  # 最后一次气泡显示时长（秒）

    @staticmethod
    def calculate_bubble_duration(text: str) -> int:
        """
        根据文本长度计算气泡显示时长

         计算公式:
         - 基础时间: 3000ms (3秒)
         - 每10个字符增加5000ms
         - 最长不超过30000ms (30秒)
         - 最少不低于5000ms (5秒)
        """
        if not text:
            return 5000

        # 计算文本长度（中文字符算2个字符，英文算1个）
        char_count = 0
        for char in text:
            if "\u4e00" <= char <= "\u9fff":  # 中文字符
                char_count += 2
            else:
                char_count += 1

        # 基础3秒，每10个字符加5秒
        base_duration = 3000
        additional_duration = (char_count // 10) * 5000
        total_duration = base_duration + additional_duration

        # 限制在5秒到30秒之间
        min_duration = 5000
        max_duration = 30000
        total_duration = max(min_duration, min(total_duration, max_duration))

        return total_duration

    def _wait_for_bubble_interval(self, current_duration: int) -> float:
        """
        计算需要等待的时间以确保上一个气泡完全显示后再显示新气泡

        参数:
            current_duration: 当前气泡的显示时长（毫秒）

        返回需要等待的秒数（如果不需要等待返回0）
        """
        current_time = time.time()
        last_bubble_end_time = self._last_bubble_time + (
            self._last_bubble_duration / 1000
        )

        if current_time < last_bubble_end_time:
            # 需要等待到上一个气泡结束
            return last_bubble_end_time - current_time

        return 0.0

    def _update_bubble_time(self, duration: int) -> None:
        """更新最后一次气泡显示信息"""
        self._last_bubble_time = time.time()
        self._last_bubble_duration = duration

    @property
    def name(self) -> str:
        return "display_bubble_text"

    @property
    def description(self) -> str:
        return "向用户显示气泡文本消息。当需要向用户显示消息时调用此工具。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "要显示的文本内容"},
                "choices": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "选项列表（可选）",
                },
                "textFrameColor": {
                    "type": "integer",
                    "description": "气泡框颜色（默认0x000000黑色）",
                },
                "textColor": {
                    "type": "integer",
                    "description": "文字颜色（默认0xFFFFFF白色）",
                },
                "duration": {
                    "type": "integer",
                    "description": "显示时长毫秒（默认根据文本长度自动计算）",
                },
            },
            "required": ["text"],
        }

    @staticmethod
    def _should_skip_content(text: str) -> bool:
        """检查是否应该跳过显示该内容（系统完成标记等）"""
        text_stripped = text.strip()
        # 跳过 {"status":"done"} 类型的完成标记
        if text_stripped == '{"status":"done"}' or text_stripped == '{"status": "done"}':
            return True
        # 跳过中文系统完成标记
        if "不需要额外回复" in text_stripped or "对话已经完成" in text_stripped:
            return True
        # 跳过纯日志输出（如果日志意外混入内容）
        if " - DEBUG - " in text_stripped or " - INFO - " in text_stripped:
            return True
        return False

    async def execute(self, **kwargs) -> None:
        # 如果用户没有指定duration，则根据文本长度智能计算
        duration = kwargs.get("duration")
        text = kwargs.get("text", "")
        
        # 检查是否应该跳过显示该内容
        if self._should_skip_content(text):
            return
        
        if duration is None:
            duration = self.calculate_bubble_duration(text)

        # 获取 Qt 气泡组件，如果存在则使用 Qt 气泡显示
        bubble_widget = kwargs.get("bubble_widget")
        if bubble_widget is not None:
            # 使用 Qt 气泡显示
            # 新气泡直接替换旧气泡，不需要等待旧气泡显示完
            # clear 已经停止之前的定时器和动画
            bubble_widget.clear()
            bubble_widget.set_text(text)
            bubble_widget.show_with_duration(duration)
            # 更新最后一次气泡显示时间（从当前开始）
            self._update_bubble_time(duration)
            return

        # 没有 Qt 气泡组件，回退到 Live2D WebSocket 气泡
        bubble_data = Live2dDisplayBubbleText(
            id=kwargs.get("id", 0),
            text=text,
            choices=kwargs.get("choices", []),
            textFrameColor=kwargs.get("textFrameColor", 0x000000),
            textColor=kwargs.get("textColor", 0xFFFFFF),
            duration=duration,
        )

        # 检查ws不为空
        ws = kwargs.get("ws")
        if ws is None:
            return

        # Live2D需要等待，因为它没有替换机制，不能重叠
        # 检查气泡时间间隔
        wait_time = self._wait_for_bubble_interval(duration)
        if wait_time > 0:
            await asyncio.sleep(wait_time)

        # 发送气泡
        await send_message(ws, DisplayBubbleText, DisplayBubbleText, bubble_data)
        # 更新最后一次气泡显示时间
        self._update_bubble_time(duration)
