import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from internal.websocket.client import (
    Client,
    DisplayBubbleText,
    Live2dDisplayBubbleText,
    send_message,
)

if TYPE_CHECKING:
    from internal.ui.bubble_widget import BubbleWidget


def calculate_bubble_duration(text: str) -> int:
    """Calculate bubble duration from text length."""
    if not text:
        return 5000

    char_count = 0
    for char in text:
        if "\u4e00" <= char <= "\u9fff":
            char_count += 2
        else:
            char_count += 1

    base_duration = 3000
    additional_duration = (char_count // 10) * 1000
    total_duration = base_duration + additional_duration
    return max(5000, min(total_duration, 30000))


class BubbleTimingController:
    """Owns bubble pacing, skip rules, and rendering helpers."""

    def __init__(
        self,
        *,
        time_provider: Callable[[], float] | None = None,
        sleep_func: Callable[[float], Awaitable[None]] | None = None,
        sender: Callable[[Client, int, int, object], Awaitable[None]] | None = None,
    ) -> None:
        self._time_provider = time_provider or time.time
        self._sleep = sleep_func or asyncio.sleep
        self._sender = sender or send_message
        self.last_bubble_time = 0.0
        self.last_bubble_duration = 0.0

    def wait_for_bubble_interval(self, current_duration: int) -> float:
        current_time = self._time_provider()
        last_bubble_end_time = self.last_bubble_time + (self.last_bubble_duration / 1000)
        if current_time < last_bubble_end_time:
            return last_bubble_end_time - current_time
        return 0.0

    def update_bubble_time(self, duration: int) -> None:
        self.last_bubble_time = self._time_provider()
        self.last_bubble_duration = duration

    @staticmethod
    def should_skip_content(content: str) -> bool:
        content_stripped = content.strip()
        if content_stripped in {'{"status":"done"}', '{"status": "done"}'}:
            return True
        if "不需要额外回复" in content_stripped or "对话已经完成" in content_stripped:
            return True
        if " - DEBUG - " in content_stripped or " - INFO - " in content_stripped:
            return True
        return False

    async def display_text(
        self,
        text: str,
        ws: Client,
        bubble_widget: BubbleWidget | None,
        *,
        bubble_id: int = 0,
        text_frame_color: int = 0x000000,
        text_color: int = 0xFFFFFF,
        duration: int | None = None,
        wait_for_interval: bool = True,
        update_state: bool = True,
        clear_widget: bool = True,
        show_widget: bool = True,
    ) -> int:
        display_duration = duration if duration is not None else calculate_bubble_duration(text)

        if bubble_widget is not None:
            if clear_widget:
                bubble_widget.clear()
            bubble_widget.set_text(text)
            if show_widget:
                bubble_widget.show_with_duration(display_duration)
            else:
                bubble_widget.show()
            if update_state:
                self.update_bubble_time(display_duration)
            return display_duration

        bubble_data = Live2dDisplayBubbleText(
            id=bubble_id,
            text=text,
            choices=[],
            textFrameColor=text_frame_color,
            textColor=text_color,
            duration=display_duration,
        )
        if wait_for_interval:
            wait_time = self.wait_for_bubble_interval(display_duration)
            if wait_time > 0:
                await self._sleep(wait_time)
        await self._sender(ws, DisplayBubbleText, DisplayBubbleText, bubble_data)
        if update_state:
            self.update_bubble_time(display_duration)
        return display_duration

    async def send_single_bubble(
        self,
        content: str,
        ws: Client,
        bubble_widget: BubbleWidget | None,
        *,
        default_text_color: int = 0xFFFFFF,
    ) -> None:
        if bubble_widget is not None:
            duration = calculate_bubble_duration(content)
            await self.display_text(content, ws, bubble_widget, duration=duration)
            logging.info(f"Qt bubble displayed: {content[:50]}...")
            return

        try:
            parsed = json.loads(content.strip())
        except json.JSONDecodeError:
            parsed = None

        if isinstance(parsed, dict):
            data = parsed.get("data", parsed)
            duration = data.get("duration")
            if duration is None:
                duration = calculate_bubble_duration(data.get("text", content))
            await self.display_text(
                data.get("text", content),
                ws,
                bubble_widget,
                bubble_id=data.get("id", 0),
                text_frame_color=data.get("textFrameColor", 0x000000),
                text_color=data.get("textColor", default_text_color),
                duration=duration,
            )
            logging.info(f"Parsed JSON bubble: {data}")
            return

        await self.display_text(content, ws, bubble_widget, text_color=default_text_color)
        logging.info(f"Sent plain text bubble: {content[:50]}...")

    async def send_stream_chunk(
        self,
        current_content: str,
        duration: int,
        ws: Client,
        bubble_widget: BubbleWidget | None,
        *,
        bubble_id: int = 0,
        first_chunk: bool,
        text_frame_color: int = 0x000000,
        text_color: int = 0xFFFFFF,
    ) -> None:
        if bubble_widget is not None:
            if first_chunk:
                bubble_widget.clear()
                bubble_widget.show()
            bubble_widget.set_text(current_content)
            return

        await self.display_text(
            current_content,
            ws,
            bubble_widget,
            bubble_id=bubble_id,
            text_frame_color=text_frame_color,
            text_color=text_color,
            duration=duration,
            wait_for_interval=first_chunk,
            update_state=False,
            clear_widget=False,
        )
        logging.debug(f"Stream chunk sent: {current_content[:50]}...")

    def finish_stream(self, final_content: str, bubble_widget: BubbleWidget | None) -> None:
        final_duration = calculate_bubble_duration(final_content)
        self.update_bubble_time(final_duration)
        if bubble_widget is not None:
            bubble_widget.show_with_duration(final_duration)
