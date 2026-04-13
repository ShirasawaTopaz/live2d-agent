from __future__ import annotations

import asyncio
import logging
from typing import Callable, Coroutine, Optional


from .client import Client, new_client, close_client

LOGGER = logging.getLogger(__name__)


class ConnectionState:
    """WebSocket 连接状态"""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    CLOSING = "closing"


class ExponentialBackoff:
    """指数退避重连策略"""

    def __init__(
        self,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        multiplier: float = 2.0,
        jitter: float = 0.1,
    ):
        """
        Args:
            initial_delay: 初始重连延迟（秒）
            max_delay: 最大重连延迟（秒）
            multiplier: 延迟倍增系数
            jitter: 随机抖动因子范围 (0-1)
        """
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.jitter = jitter
        self._current_delay = initial_delay
        self._attempts = 0

    def reset(self) -> None:
        """重置重连尝试计数"""
        self._current_delay = self.initial_delay
        self._attempts = 0

    def next_delay(self) -> float:
        """计算下一次重连延迟"""
        import random

        delay = self._current_delay
        # 添加随机抖动
        jitter_amount = delay * self.jitter
        delay = delay + random.uniform(-jitter_amount, jitter_amount)

        # 更新下一次延迟（不超过最大值）
        self._current_delay = min(self._current_delay * self.multiplier, self.max_delay)
        self._attempts += 1

        return max(0, delay)

    @property
    def attempts(self) -> int:
        """获取当前重连尝试次数"""
        return self._attempts


class ReconnectingWebSocket:
    """支持自动重连的 WebSocket 客户端"""

    def __init__(
        self,
        url: str,
        backoff: Optional[ExponentialBackoff] = None,
        max_reconnect_attempts: int = 0,  # 0 表示无限重试
        on_connect: Optional[Callable[[Client], Coroutine]] = None,
        on_disconnect: Optional[Callable[[Optional[Exception]], Coroutine]] = None,
    ):
        """
        Args:
            url: WebSocket 服务器地址
            backoff: 退避策略，默认使用指数退避
            max_reconnect_attempts: 最大重连尝试次数，0 表示无限
            on_connect: 连接成功回调
            on_disconnect: 断开连接回调
        """
        self.url = url
        self.backoff = backoff or ExponentialBackoff()
        self.max_reconnect_attempts = max_reconnect_attempts
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect

        self._client: Optional[Client] = None
        self._state = ConnectionState.DISCONNECTED
        self._reconnect_task: Optional[asyncio.Task] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._shutdown = asyncio.Event()
        self._connected = asyncio.Event()

    @property
    def state(self) -> str:
        """获取当前连接状态"""
        return self._state

    @property
    def client(self) -> Optional[Client]:
        """获取当前客户端实例"""
        return self._client

    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._state == ConnectionState.CONNECTED and self._client is not None

    async def connect(self) -> None:
        """建立连接，失败会自动重连"""
        if self._state != ConnectionState.DISCONNECTED:
            LOGGER.warning(f"连接已经在进行中，当前状态: {self._state}")
            return

        self._state = ConnectionState.CONNECTING
        self._shutdown.clear()
        self._connected.clear()
        self.backoff.reset()

        await self._do_connect()

    async def _do_connect(self) -> bool:
        """实际执行连接"""
        try:
            LOGGER.info(f"正在连接到: {self.url}")
            self._client = await new_client(self.url)
            self._state = ConnectionState.CONNECTED
            self._connected.set()
            LOGGER.info(f"连接成功: {self.url}")

            self.backoff.reset()

            if self.on_connect:
                await self.on_connect(self._client)

            return True
        except Exception as e:
            LOGGER.error(f"连接失败: {e}")
            self._client = None
            self._state = ConnectionState.DISCONNECTED
            self._connected.clear()

            if self.on_disconnect:
                await self.on_disconnect(e)

            return False

    async def disconnect(self) -> None:
        """断开连接，停止重连"""
        self._shutdown.set()
        self._state = ConnectionState.CLOSING

        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        if self._client:
            await close_client(self._client)
            self._client = None

        self._state = ConnectionState.DISCONNECTED
        self._connected.clear()
        LOGGER.info("已断开连接")

        if self.on_disconnect:
            await self.on_disconnect(None)

    async def wait_connected(self, timeout: Optional[float] = None) -> bool:
        """等待连接完成

        Args:
            timeout: 超时时间（秒），None 表示无限等待

        Returns:
            是否成功连接
        """
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=timeout)
            return self.is_connected
        except asyncio.TimeoutError:
            return False

    async def send(self, message: bytes) -> None:
        """发送消息

        Args:
            message: 要发送的消息
        """
        if not self.is_connected or self._client is None:
            raise RuntimeError("WebSocket 未连接")
        await self._client.send(message)

    def start_receive_loop(
        self,
        receive_queue: asyncio.Queue,
    ) -> asyncio.Task:
        """启动接收循环，会自动处理重连

        Args:
            receive_queue: 接收消息队列

        Returns:
            接收任务
        """
        from .client import receive_message

        async def receive_loop():
            while not self._shutdown.is_set():
                if self.is_connected and self._client is not None:
                    try:
                        await receive_message(self._client, receive_queue)
                    except (ConnectionError, asyncio.CancelledError, RuntimeError):
                        # 连接断开，触发重连
                        if not self._shutdown.is_set():
                            LOGGER.warning("WebSocket 连接断开，准备重连...")
                            await self._handle_disconnect(None)
                    except Exception as e:
                        LOGGER.error(f"接收消息出错: {e}")
                        if not self._shutdown.is_set():
                            await self._handle_disconnect(e)
                else:
                    # 等待连接建立
                    try:
                        await self.wait_connected(timeout=1.0)
                    except asyncio.TimeoutError:
                        continue

        self._receive_task = asyncio.create_task(receive_loop())
        return self._receive_task

    async def _handle_disconnect(self, error: Optional[Exception]) -> None:
        """处理连接断开，启动重连"""
        if self._state == ConnectionState.CLOSING or self._shutdown.is_set():
            return

        # 检查重连尝试次数
        if (
            self.max_reconnect_attempts > 0
            and self.backoff.attempts >= self.max_reconnect_attempts
        ):
            LOGGER.error(
                f"已达到最大重连尝试次数 ({self.max_reconnect_attempts})，停止重连"
            )
            self._state = ConnectionState.DISCONNECTED
            if self.on_disconnect:
                await self.on_disconnect(error)
            return

        self._state = ConnectionState.RECONNECTING
        self._connected.clear()

        if self.on_disconnect:
            await self.on_disconnect(error)

        # 关闭旧连接
        if self._client:
            try:
                await close_client(self._client)
            except Exception as e:
                LOGGER.debug(f"关闭旧连接出错: {e}")
            self._client = None

        # 计算退避延迟
        delay = self.backoff.next_delay()
        LOGGER.info(
            f"将在 {delay:.1f} 秒后进行第 {self.backoff.attempts + 1} 次重连"
        )

        # 等待延迟后重连
        async def do_reconnect():
            try:
                await asyncio.sleep(delay)
                if self._shutdown.is_set():
                    return
                await self._do_connect()
                if not self.is_connected and not self._shutdown.is_set():
                    # 连接失败，继续重连循环
                    await self._handle_disconnect(None)
            except asyncio.CancelledError:
                LOGGER.debug("重连任务被取消")
            except Exception as e:
                LOGGER.error(f"重连任务出错: {e}")
                if not self._shutdown.is_set():
                    await self._handle_disconnect(e)

        self._reconnect_task = asyncio.create_task(do_reconnect())
