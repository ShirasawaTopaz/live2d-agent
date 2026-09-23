"""Core plugin: Live2D websocket transport (``ctx.web``).

Owns :class:`ReconnectingWebSocket` plus the receive-queue coordinator, so
plugins that need to talk to the Live2D front end inject ``web`` instead of
building their own connection.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from internal.cordis import Schema, Service
from internal.websocket.reconnect import ExponentialBackoff, ReconnectingWebSocket

plugin_name = "web"

module_schema = Schema.object({})

logger = logging.getLogger(__name__)


class WebService(Service):
    """Connection service for the Live2D websocket endpoint."""

    def __init__(self, ctx: Any, name: str = "web") -> None:
        super().__init__(ctx, name)
        self.websocket: ReconnectingWebSocket | None = None
        self.receive_queue: asyncio.Queue[Any] | None = None
        self.receive_task: asyncio.Task[Any] | None = None
        self.consume_task: asyncio.Task[Any] | None = None
        self.is_running = False

    @property
    def connected(self) -> bool:
        return bool(self.websocket is not None and self.websocket.is_connected)

    @property
    def client(self) -> Any:
        return getattr(self.websocket, "client", None)

    async def connect(self, url: str | None = None) -> ReconnectingWebSocket:
        target = url or self._configured_url()
        backoff = ExponentialBackoff(initial_delay=1.0, max_delay=60.0, multiplier=2.0, jitter=0.1)
        websocket = ReconnectingWebSocket(url=target, backoff=backoff, max_reconnect_attempts=0)
        websocket.on_connect = self._on_connect
        websocket.on_disconnect = self._on_disconnect
        await websocket.connect()
        self.websocket = websocket
        self.receive_queue = asyncio.Queue()
        self.receive_task = websocket.start_receive_loop(self.receive_queue)
        return websocket

    async def disconnect(self) -> None:
        await self.stop_consuming()
        websocket = self.websocket
        self.websocket = None
        if websocket is not None:
            try:
                await asyncio.wait_for(websocket.disconnect(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("websocket disconnect timed out")
            except Exception as exc:  # noqa: BLE001 - shutdown must continue
                logger.error("websocket disconnect failed: %s", exc)
        if self.receive_task is not None and not self.receive_task.done():
            self.receive_task.cancel()
        self.receive_task = None
        self.receive_queue = None

    def start_consuming(self) -> None:
        self.is_running = True
        if self.consume_task is None or self.consume_task.done():
            self.consume_task = asyncio.create_task(self._consume_loop())

    async def stop_consuming(self) -> None:
        self.is_running = False
        task = self.consume_task
        self.consume_task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _consume_loop(self) -> None:
        while self.is_running:
            queue = self.receive_queue
            if queue is None:
                return
            try:
                message = await queue.get()
                queue.task_done()
                self.ctx.emit("web/message", message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                if self.is_running:
                    logger.debug("websocket consume loop ended: %s", exc)
                return

    def _configured_url(self) -> str:
        config_service = self.ctx.get("config")
        return str(getattr(config_service, "live2d_socket", "") or "")

    async def _on_connect(self, _client: Any) -> None:
        logger.info("websocket connected")
        self.ctx.emit("web/connected", self.websocket)

    async def _on_disconnect(self, error: Exception | None) -> None:
        if error:
            logger.warning("websocket disconnected: %s", error)
        self.ctx.emit("web/disconnected", error)


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    _ = config
    ctx.service("web", WebService(ctx, "web"))
