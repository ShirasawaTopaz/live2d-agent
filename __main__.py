# 2026/3/8
# Shirasawa
# 目前golang（旧代码）和python（新代码）同时存在，但实际主线是python。留两套代码是我怕我迁移不完全，留着旧代码保险一点。

import asyncio
import logging
import sys

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QFont
from PySide6.QtCore import QPoint, Qt

from internal.agent.agent import create_agent
from internal.config.config import Config
from internal.websocket.reconnect import ReconnectingWebSocket, ExponentialBackoff
from internal.ui import FloatingInputBox, BubbleWidget

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


class Live2oderApp:
    """Live2oder 应用主类"""

    def __init__(self):
        self.qt_app: QApplication | None = None
        self.input_box: FloatingInputBox | None = None
        self.bubble_widget: BubbleWidget | None = None
        self.tray_icon: QSystemTrayIcon | None = None
        self.agent = None
        self.ws: ReconnectingWebSocket | None = None
        self.config: Config | None = None
        self._running = False
        self._processing = False
        self._receive_task: asyncio.Task | None = None
        self._receive_queue: asyncio.Queue | None = None

    async def initialize(self):
        """初始化应用"""
        logger.info("正在初始化 Live2oder...")

        # 加载配置
        self.config = await Config.load()

        # 初始化 PromptManager（在创建 Agent 之前确保模块已加载）
        from internal.prompt_manager import PromptManager

        await PromptManager.load()

        # 创建 Qt 应用
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.qt_app.setStyle("Fusion")

        # 设置应用属性
        self.qt_app.setApplicationName("Live2oder")
        self.qt_app.setApplicationDisplayName("Live2oder Agent")

        # 创建支持自动重连的 WebSocket 连接
        # 使用指数退避策略：初始延迟1秒，最大延迟60秒，倍增系数2
        backoff = ExponentialBackoff(
            initial_delay=1.0,
            max_delay=60.0,
            multiplier=2.0,
            jitter=0.1
        )
        self.ws = ReconnectingWebSocket(
            url=self.config.live2dSocket,
            backoff=backoff,
            max_reconnect_attempts=0,  # 无限重试
        )

        # 连接回调
        async def on_connect(client):
            logger.info(f"WebSocket 已连接到 {self.config.live2dSocket}")

        # 断开连接回调
        async def on_disconnect(error):
            if error:
                logger.warning(f"WebSocket 断开连接: {error}")
            else:
                logger.info("WebSocket 正常断开")

        self.ws.on_connect = on_connect
        self.ws.on_disconnect = on_disconnect

        # 建立初始连接
        await self.ws.connect()

        # 启动自动重连的接收循环，持续读取 WebSocket 消息
        self._receive_queue: asyncio.Queue = asyncio.Queue()
        self._receive_task = self.ws.start_receive_loop(self._receive_queue)

        # 持续消费队列（丢弃消息，我们暂时不需要处理 incoming 事件）
        async def consume_loop():
            while self._running:
                try:
                    msg = await self._receive_queue.get()
                    logger.debug(
                        f"Received message from Live2D: msg={msg.msg} msgId={msg.msgId}"
                    )
                    self._receive_queue.task_done()
                except Exception as e:
                    if self._running:
                        logger.debug(f"消息消费循环退出: {e}")
                    break

        asyncio.create_task(consume_loop())

        # 创建 Agent
        memory_config = self.config.memory if self.config.memory is not None else None
        sandbox_config = (
            self.config.sandbox if self.config.sandbox is not None else None
        )
        self.agent = create_agent(
            self.config.get_default_model_config(), memory_config, sandbox_config
        )

        # 创建悬浮输入框
        self.input_box = FloatingInputBox(agent=self.agent, title="Agent Chat")

        # 创建悬浮气泡窗口
        self.bubble_widget = BubbleWidget()
        # 同步主题
        if self.input_box:
            self.bubble_widget.set_theme(self.input_box._theme)

        # 将气泡窗口传递给 agent
        if self.agent:
            self.agent.bubble_widget = self.bubble_widget

        # 连接信号
        self.setup_signals()

        # 创建系统托盘
        self.setup_tray_icon()

        # 设置窗口位置
        self.setup_window_position()

        # 显示输入框
        if self.input_box:
            self.input_box.show()
            self.input_box.raise_()
            self.input_box.activateWindow()
            logger.info("输入框已显示")

        logger.info("Live2oder 初始化完成")

    def setup_signals(self):
        """设置信号连接"""
        if not self.input_box:
            return

        # 连接消息信号
        self.input_box.message_sent.connect(self.on_message_sent)
        self.input_box.visibility_changed.connect(self.on_visibility_changed)
        self.input_box.close_requested.connect(self.quit)

    def setup_tray_icon(self):
        """设置系统托盘图标"""
        logger.debug(
            f"QSystemTrayIcon.isSystemTrayAvailable() = {QSystemTrayIcon.isSystemTrayAvailable()}"
        )
        logger.debug(
            f"QSystemTrayIcon.supportsMessages() = {QSystemTrayIcon.supportsMessages()}"
        )

        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("系统托盘不可用，输入框将始终显示，可通过标题栏关闭按钮退出")
            # 没有托盘时，确保输入框显示
            if self.input_box:
                self.input_box.show()
                self.input_box.raise_()
            return

        # 创建托盘图标
        self.tray_icon = QSystemTrayIcon(self.qt_app)
        self.tray_icon.setToolTip("Live2oder Agent - 点击显示输入框")

        # 创建一个简单的图标（使用 Qt 内置图标或创建像素图）
        from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush

        # 创建一个简单的 32x32 像素图标
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制一个蓝色圆角矩形作为图标
        painter.setBrush(QBrush(QColor("#4a9eff")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(2, 2, 28, 28, 6, 6)

        # 绘制一个白色的 "L" 字母
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "L")

        painter.end()

        icon = QIcon(pixmap)

        # 验证图标是否有效
        if icon.isNull() or icon.availableSizes():
            logger.warning("创建的图标可能无效，尝试使用备用图标")
            # 使用 Qt 内置图标作为备用
            from PySide6.QtWidgets import QStyle

            if self.qt_app is not None:
                icon = self.qt_app.style().standardIcon(
                    QStyle.StandardPixmap.SP_ComputerIcon
                )

        self.tray_icon.setIcon(icon)
        if self.qt_app is not None:
            self.qt_app.setWindowIcon(icon)

        logger.debug(
            f"托盘图标已设置: icon.isNull()={icon.isNull()}, sizes={icon.availableSizes() if not icon.isNull() else 'N/A'}"
        )

        # 创建托盘菜单
        menu = QMenu()

        # 显示/隐藏
        show_action = menu.addAction("显示输入框")
        show_action.triggered.connect(self.show_input_box)

        hide_action = menu.addAction("隐藏输入框")
        hide_action.triggered.connect(self.hide_input_box)

        menu.addSeparator()

        # 设置
        settings_action = menu.addAction("设置")
        settings_action.triggered.connect(self.open_settings)

        menu.addSeparator()

        # 退出
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self.quit)

        self.tray_icon.setContextMenu(menu)

        # 连接激活信号
        self.tray_icon.activated.connect(self.on_tray_activated)

        # 显示托盘图标
        self.tray_icon.show()

        # 验证托盘图标是否可见
        import time

        time.sleep(0.1)  # 给系统一点时间来显示图标
        if self.tray_icon.isVisible():
            logger.info("系统托盘图标已成功显示")
            # 显示气泡通知提示用户
            try:
                self.tray_icon.showMessage(
                    "Live2oder Agent",
                    "程序已在系统托盘运行，点击图标显示/隐藏输入框",
                    QSystemTrayIcon.MessageIcon.Information,
                    5000,  # 5秒
                )
                logger.info("已显示托盘气泡通知")
            except Exception as e:
                logger.warning(f"显示气泡通知失败: {e}")
        else:
            logger.warning("系统托盘图标未能显示，可能需要检查系统设置")

    def setup_window_position(self):
        """设置窗口初始位置"""
        if not self.input_box:
            return

        # 加载保存的位置
        from PySide6.QtCore import QSettings

        settings = QSettings("Live2oder", "FloatingInputBox")
        pos = settings.value("position", None)

        if pos and isinstance(pos, QPoint):
            self.input_box.move(pos)
        else:
            # 默认位置：屏幕右下角
            screen = self.qt_app.primaryScreen().geometry()
            self.input_box.move(
                screen.width() - self.input_box.width() - 20,
                screen.height() - self.input_box.height() - 100,
            )

    # === 槽函数 ===

    def on_message_sent(self, text: str):
        """处理用户发送的消息"""
        logger.info(f"用户输入: {text}")

        # 创建异步任务处理消息
        asyncio.create_task(self.process_message(text))

    async def process_message(self, text: str):
        """异步处理消息"""
        # Guard against concurrent processing
        if self._processing:
            logger.warning("Already processing a message, skipping duplicate")
            return

        self._processing = True

        # If应用正在退出，不处理新消息
        if not self._running:
            self._processing = False
            return

        try:
            # 显示加载状态
            if self.input_box:
                self.input_box.setEnabled(False)

             # 调用 Agent 处理
            if self.agent and self.ws:
                if self.ws.is_connected and self.ws.client:
                    response = await self.agent.chat(text, self.ws.client)
                    logger.info(f"Agent 响应: {response}")
                else:
                    logger.error("WebSocket 未连接，无法发送消息")
                    # TODO: 可以在这里添加用户提示（气泡提示）

        except Exception as e:
            logger.error(f"处理消息时出错: {e}")

        finally:
            self._processing = False
            if self.input_box and self._running:
                self.input_box.setEnabled(True)
                self.input_box.text_edit.setFocus()
                # Clear the loading flag in input_box
                self.input_box._is_loading = False

    def on_visibility_changed(self, is_visible: bool):
        """处理可见性变化"""
        logger.debug(f"输入框可见性变化: {is_visible}")

    def on_tray_activated(self, reason):
        """处理托盘图标激活"""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # 单击切换显示/隐藏
            if self.input_box:
                if self.input_box.isVisible():
                    self.hide_input_box()
                else:
                    self.show_input_box()

    def show_input_box(self):
        """显示输入框"""
        if self.input_box:
            self.input_box.show()
            self.input_box.raise_()
            self.input_box.activateWindow()

    def hide_input_box(self):
        """隐藏输入框"""
        if self.input_box:
            self.input_box.hide()

    def open_settings(self):
        """打开设置"""
        logger.info("打开设置对话框")
        # TODO: 实现设置对话框

    def quit(self):
        """退出应用"""
        logger.info("正在退出...")
        self._running = False

    async def run(self):
        """运行应用"""
        await self.initialize()
        self._running = True

        try:
            # 主循环
            while self._running:
                self.qt_app.processEvents()
                await asyncio.sleep(0.016)  # 约 60 FPS

        except KeyboardInterrupt:
            logger.info("收到中断信号")
        finally:
            await self.cleanup()

    async def cleanup(self):
        """清理资源"""
        logger.info("正在清理资源...")

        # 保存设置
        if self.input_box:
            try:
                self.input_box.save_settings()
            except Exception as e:
                logger.error(f"保存设置失败: {e}")

        # 保存气泡位置
        if self.bubble_widget:
            try:
                self.bubble_widget.save_position()
            except Exception as e:
                logger.error(f"保存气泡位置失败: {e}")

         # 断开 WebSocket 连接，停止重连
        if self.ws:
            try:
                await asyncio.wait_for(self.ws.disconnect(), timeout=5.0)
                logger.info("WebSocket 已关闭，重连已停止")
            except asyncio.TimeoutError:
                logger.warning("关闭 WebSocket 超时，强制继续")
            except Exception as e:
                logger.error(f"关闭 WebSocket 出错: {e}")

        # 取消后台消费任务 - 由 ReconnectingWebSocket 管理接收任务
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                logger.debug("消息消费任务已取消")
            except Exception as e:
                logger.error(f"消息消费任务出错: {e}")

        # 退出 Qt 应用
        if self.qt_app:
            self.qt_app.quit()
            logger.info("Qt 应用已退出")


if __name__ == "__main__":
    app = Live2oderApp()
    asyncio.run(app.run())
