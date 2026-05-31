"""Notification delivery for completed scheduler tasks."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class NotificationManager:
    """Delivers scheduler task results to the user.

    Two channels:
    1. Desktop toast via QSystemTrayIcon.showMessage()
    2. Live2D bubble text via WebSocket (if connected)
    """

    def __init__(self, tray_icon: Any = None, websocket: Any = None):
        self._tray = tray_icon
        self._ws = websocket

    def set_tray(self, tray_icon: Any) -> None:
        self._tray = tray_icon

    def set_websocket(self, ws: Any) -> None:
        self._ws = ws

    def notify(self, title: str, message: str) -> None:
        summary = message[:200] + "..." if len(message) > 200 else message

        if self._tray is not None:
            try:
                self._tray.showMessage(
                    title, summary,
                    icon=self._tray.icon() if hasattr(self._tray, "icon") else 0,
                    duration=5000,
                )
                logger.debug("Tray notification sent: %s", title)
            except Exception:
                logger.warning("Failed to send tray notification", exc_info=True)

        if self._ws is not None and self._ws.is_connected:
            try:
                import asyncio
                asyncio.ensure_future(self._send_bubble(title, summary))
            except Exception:
                logger.warning("Failed to schedule bubble notification", exc_info=True)

        logger.info("Notification: [%s] %s", title, summary)

    async def _send_bubble(self, title: str, text: str) -> None:
        if self._ws is None or not self._ws.is_connected:
            return
        try:
            bubble_text = f"⏰ {title}\n{text}"
            await self._ws.client.send_json({
                "type": "display_bubble_text",
                "text": bubble_text,
                "duration_ms": 8000,
            })
        except Exception:
            logger.debug("Bubble notification failed (Live2D may be offline)")
