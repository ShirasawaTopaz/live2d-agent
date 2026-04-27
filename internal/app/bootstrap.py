import logging
import sys
from dataclasses import dataclass
from importlib import import_module
from typing import Any

from internal.agent.agent import create_agent
from internal.config.config import Config
from internal.prompt_manager import PromptManager
from internal.ui import BubbleWidget, FloatingInputBox
from internal.websocket.reconnect import ExponentialBackoff, ReconnectingWebSocket


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BootstrapContext:
    config: Config
    qt_app: Any
    websocket: ReconnectingWebSocket
    agent: Any
    input_box: FloatingInputBox
    bubble_widget: BubbleWidget


async def bootstrap_application() -> BootstrapContext:
    """Create config, websocket, agent, and UI components."""
    logger.info("正在初始化 Live2oder...")
    config = await load_startup_resources()
    qt_app = create_qt_application()
    agent = create_runtime_agent(config)
    websocket = await create_websocket(config)
    input_box, bubble_widget = create_ui_components(agent)

    logger.info("Live2oder 初始化完成")
    return BootstrapContext(
        config=config,
        qt_app=qt_app,
        websocket=websocket,
        agent=agent,
        input_box=input_box,
        bubble_widget=bubble_widget,
    )


async def load_startup_resources() -> Config:
    config = await Config.load()
    await PromptManager.load()
    return config


def create_qt_application() -> Any:
    qt_widgets = import_module("PySide6.QtWidgets")
    qt_app = qt_widgets.QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)
    qt_app.setStyle("Fusion")
    qt_app.setApplicationName("Live2oder")
    qt_app.setApplicationDisplayName("Live2oder Agent")
    return qt_app


def create_ui_components(agent: Any) -> tuple[FloatingInputBox, BubbleWidget]:
    input_box = FloatingInputBox(agent=agent, title="Agent Chat")
    bubble_widget = BubbleWidget()
    bubble_widget.set_theme(str(input_box._theme))
    agent.bubble_widget = bubble_widget
    return input_box, bubble_widget


def configure_websocket_callbacks(
    websocket: ReconnectingWebSocket,
    config: Config,
) -> None:
    async def on_connect(_client) -> None:
        logger.info("WebSocket 已连接到 %s", config.live2dSocket)

    async def on_disconnect(error: Exception | None) -> None:
        if error:
            logger.warning("WebSocket 断开连接: %s", error)
        else:
            logger.info("WebSocket 正常断开")

    websocket.on_connect = on_connect
    websocket.on_disconnect = on_disconnect


async def create_websocket(config: Config) -> ReconnectingWebSocket:
    backoff = ExponentialBackoff(
        initial_delay=1.0,
        max_delay=60.0,
        multiplier=2.0,
        jitter=0.1,
    )
    websocket = ReconnectingWebSocket(
        url=config.live2dSocket,
        backoff=backoff,
        max_reconnect_attempts=0,
    )

    configure_websocket_callbacks(websocket, config)
    await websocket.connect()
    return websocket


def create_runtime_agent(config: Config) -> Any:
    return create_agent(
        config.get_default_model_config(),
        config.memory if config.memory is not None else None,
        config.sandbox if config.sandbox is not None else None,
        config.planning if config.planning is not None else None,
        global_config=config,
    )
