import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any


logger = logging.getLogger(__name__)


def connect_input_signals(
    input_box: Any,
    *,
    on_message_sent: Callable[[str], None],
    on_visibility_changed: Callable[[bool], None],
    on_close_requested: Callable[[], None],
) -> None:
    if input_box is None:
        return
    input_box.message_sent.connect(on_message_sent)
    input_box.visibility_changed.connect(on_visibility_changed)
    input_box.close_requested.connect(on_close_requested)


async def process_chat_message(
    *,
    text: str,
    input_box: Any,
    agent: Any,
    websocket: Any,
    is_running: bool,
) -> None:
    if not is_running:
        return
    try:
        if input_box is not None:
            input_box.setEnabled(False)
        if agent and websocket:
            if websocket.is_connected and websocket.client:
                response = await agent.chat(text, websocket.client)
                logger.info("Agent 响应: %s", response)
            else:
                logger.error("WebSocket 未连接，无法发送消息")
    except Exception as exc:
        logger.error("处理消息时出错: %s", exc)
    finally:
        if input_box is not None and is_running:
            input_box.setEnabled(True)
            input_box.text_edit.setFocus()
            input_box._is_loading = False


async def cleanup_application(
    *,
    input_box: Any,
    bubble_widget: Any,
    websocket: Any,
    runtime_state: "QueueRuntimeCoordinator",
    qt_app: Any,
) -> None:
    logger.info("正在清理资源...")
    _save_widget_state(input_box, "保存设置失败", "save_settings")
    _save_widget_state(bubble_widget, "保存气泡位置失败", "save_position")
    if websocket is not None:
        try:
            await asyncio.wait_for(websocket.disconnect(), timeout=5.0)
            logger.info("WebSocket 已关闭，重连已停止")
        except asyncio.TimeoutError:
            logger.warning("关闭 WebSocket 超时，强制继续")
        except Exception as exc:
            logger.error("关闭 WebSocket 出错: %s", exc)
    await runtime_state.stop()
    if qt_app is not None:
        qt_app.quit()
        logger.info("Qt 应用已退出")


def _save_widget_state(widget: Any, failure_message: str, method_name: str) -> None:
    if widget is None:
        return
    try:
        getattr(widget, method_name)()
    except Exception as exc:
        logger.error("%s: %s", failure_message, exc)


class QueueRuntimeCoordinator:
    """Coordinate websocket receive and queue-consumer lifecycle."""

    def __init__(self) -> None:
        self.is_running = False
        self.receive_queue: asyncio.Queue[Any] | None = None
        self.receive_task: asyncio.Task[Any] | None = None
        self.consume_task: asyncio.Task[Any] | None = None

    def attach(self, websocket: Any) -> None:
        self.receive_queue = asyncio.Queue()
        self.receive_task = websocket.start_receive_loop(self.receive_queue)

    def start(self) -> None:
        self.is_running = True
        if self.consume_task is None or self.consume_task.done():
            self.consume_task = asyncio.create_task(self._consume_loop())

    async def stop(self) -> None:
        self.is_running = False

        if self.consume_task and not self.consume_task.done():
            self.consume_task.cancel()
            try:
                await self.consume_task
            except asyncio.CancelledError:
                logger.debug("消息消费循环已取消")

        self.consume_task = None

        if self.receive_task and not self.receive_task.done():
            self.receive_task.cancel()
            try:
                await self.receive_task
            except asyncio.CancelledError:
                logger.debug("消息接收循环已取消")

        self.receive_task = None

    async def _consume_loop(self) -> None:
        while self.is_running:
            if self.receive_queue is None:
                return

            try:
                msg = await self.receive_queue.get()
                logger.debug(
                    "Received message from Live2D: msg=%s msgId=%s",
                    getattr(msg, "msg", None),
                    getattr(msg, "msgId", None),
                )
                self.receive_queue.task_done()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self.is_running:
                    logger.debug("消息消费循环退出: %s", exc)
                break


class ApplicationRuntime:
    """Run the app loop while the app is marked running."""

    def __init__(
        self,
        *,
        process_events: Callable[[], None],
        on_start: Callable[[], None],
        on_stop: Callable[[], Awaitable[None]],
        frame_delay: float = 0.016,
    ) -> None:
        self._process_events = process_events
        self._on_start = on_start
        self._on_stop = on_stop
        self._frame_delay = frame_delay

    async def run(self, is_running: Callable[[], bool]) -> None:
        self._on_start()
        try:
            while is_running():
                self._process_events()
                await asyncio.sleep(self._frame_delay)
        except KeyboardInterrupt:
            logger.info("收到中断信号")
        finally:
            await self._on_stop()
