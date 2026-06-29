import asyncio
import logging
import time
import uuid
from typing import Any

from internal.config.config import Config
from internal.config.editor import RuntimeApplyDecision
from internal.app.runtime import (
    ApplicationRuntime,
    QueueRuntimeCoordinator,
    cleanup_application,
    connect_input_signals,
    process_chat_message,
)
from internal.websocket.reconnect import ReconnectingWebSocket


logger = logging.getLogger(__name__)


class Live2DAgentApp:
    """Thin façade coordinating bootstrap, runtime, and tray concerns."""

    def __init__(self) -> None:
        self.qt_app: Any = None
        self.input_box: Any = None
        self.bubble_widget: Any = None
        self.tray_icon: Any = None
        self.agent: Any = None
        self.ws: ReconnectingWebSocket | None = None
        self.config: Any = None
        self.settings_window: Any = None
        self.chat_history_window: Any = None
        self.scheduler: Any = None
        self.hotkey_manager: Any = None
        self.clipboard_monitor: Any = None
        self.browser_controller: Any = None
        self._processing = False
        self._context_lock = asyncio.Lock()
        self.runtime_state = QueueRuntimeCoordinator()
        self.runtime = ApplicationRuntime(
            process_events=self._process_events,
            on_start=self._start_runtime,
            on_stop=self.cleanup,
        )

    async def initialize(self) -> None:
        from internal.app.bootstrap import bootstrap_application

        context = await bootstrap_application()
        self._apply_bootstrap_context(context)
        self._process_events()
        self._connect_runtime_and_input()
        self._setup_tray_and_window()
        self._process_events()
        await self._initialize_session_router()
        await self._initialize_scheduler()
        await self._initialize_integrations()
        self.show_input_box()
        self._process_events()
        logger.info("输入框已显示")

    def _apply_bootstrap_context(self, context: Any) -> None:
        self.config = context.config
        self.qt_app = context.qt_app
        self.ws = context.websocket
        self.agent = context.agent
        self.input_box = context.input_box
        self.bubble_widget = context.bubble_widget
        self.chat_history_window = context.chat_history_window

    def _connect_runtime_and_input(self) -> None:
        connect_input_signals(
            self.input_box,
            on_message_sent=self.on_message_sent,
            on_visibility_changed=self.on_visibility_changed,
            on_close_requested=self.quit,
            on_clear_context_requested=self.on_clear_context_requested,
        )
        if self.ws is not None:
            self.runtime_state.attach(self.ws)

    async def _initialize_session_router(self) -> None:
        """Initialize the session auto-router if enabled in config."""
        session_config = getattr(self.config, "session", None)
        enabled = getattr(session_config, "enabled", True) if session_config is not None else True
        if not enabled:
            return

        try:
            from internal.session import TopicClassifier, SessionRouter
            from internal.session.session_store import SessionStore

            data_dir = getattr(session_config, "data_dir", "./data/sessions") if session_config is not None else "./data/sessions"
            store = SessionStore(data_dir=data_dir)
            classifier = TopicClassifier(embedding_model=None)

            # Try loading embeddings for better classification
            try:
                from internal.rag.embeddings import EmbeddingGenerator
                emb = EmbeddingGenerator()
                emb.load()
                classifier = TopicClassifier(embedding_model=emb)
            except Exception:
                pass  # Keyword-only classification is fine

            memory = self.agent.memory if hasattr(self.agent, "memory") else None
            router = SessionRouter(
                session_store=store,
                classifier=classifier,
                memory_manager=memory,
            )
            await router.initialize()

            if self.agent is not None:
                self.agent.session_router = router

            logger.info("Session router initialized")
        except Exception:
            logger.warning("Session router initialization failed", exc_info=True)

    async def _initialize_scheduler(self) -> None:
        """Initialize the background scheduler if configured."""
        scheduler_config = getattr(self.config, "scheduler", None)
        enabled = getattr(scheduler_config, "enabled", False) if scheduler_config is not None else False
        if not enabled:
            return

        try:
            from internal.scheduler import SchedulerEngine, NotificationManager
            from internal.scheduler.store import TaskStore

            data_dir = getattr(scheduler_config, "data_dir", "./data/scheduler") if scheduler_config is not None else "./data/scheduler"
            store = TaskStore(data_dir=data_dir)
            notifier = NotificationManager(
                tray_icon=self.tray_icon,
                websocket=self.ws,
            )
            engine = SchedulerEngine(store=store, notification=notifier, agent=self.agent)
            await engine.initialize()
            self.scheduler = engine
            logger.info("Scheduler initialized")
        except Exception:
            logger.warning("Scheduler initialization failed", exc_info=True)

    async def _initialize_integrations(self) -> None:
        """Initialize integration modules (hotkeys, clipboard, browser)."""
        integration_config = getattr(self.config, "integration", None)
        if integration_config is None:
            integration_config = {}

        hotkeys_enabled = getattr(integration_config, "hotkeys_enabled", True)
        if hotkeys_enabled:
            try:
                from internal.integration import HotkeyManager
                self.hotkey_manager = HotkeyManager()
                self.hotkey_manager.register(
                    HotkeyManager.DEFAULT_SUMMON, self._on_hotkey_summon)
                self.hotkey_manager.register(
                    HotkeyManager.DEFAULT_CLIP_PROCESS, self._on_hotkey_clipboard_process)
                logger.info("Hotkeys registered")
            except Exception:
                logger.warning("Hotkey registration failed", exc_info=True)

        clipboard_enabled = getattr(integration_config, "clipboard_enabled", True)
        if clipboard_enabled:
            try:
                from internal.integration import ClipboardMonitor
                self.clipboard_monitor = ClipboardMonitor()
                self.clipboard_monitor.set_on_action(self._on_clipboard_action)
                self.clipboard_monitor.set_enabled(True)
                logger.info("Clipboard monitor started")
            except Exception:
                logger.warning("Clipboard monitor init failed", exc_info=True)

    def _on_hotkey_summon(self) -> None:
        if self.input_box is not None:
            if self.input_box.isVisible():
                self.hide_input_box()
            else:
                self.show_input_box()

    def _on_hotkey_clipboard_process(self) -> None:
        if self.input_box is None:
            return
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is None:
                return
            clipboard = app.clipboard()
            if clipboard is None:
                return
            text = clipboard.text().strip()
            if text:
                self.input_box.text_edit.setText(text)
                self.show_input_box()
        except Exception:
            logger.warning("Clipboard quick process failed", exc_info=True)

    def _on_clipboard_action(self, action: Any, text: str) -> None:
        prompt = action.resolve_prompt(text)
        if self.input_box is not None:
            self.input_box.text_edit.setText(prompt)
            self.show_input_box()

    def _setup_tray_and_window(self) -> None:
        if self.qt_app is not None:
            from internal.app.tray import create_tray_icon, setup_window_position

            self.tray_icon = create_tray_icon(
                qt_app=self.qt_app,
                input_box=self.input_box,
                show_input_box=self.show_input_box,
                hide_input_box=self.hide_input_box,
                open_settings=self.open_settings,
                quit_app=self.quit,
                on_activated=self.on_tray_activated,
                show_chat_history=self.show_chat_history,
            )
            setup_window_position(self.qt_app, self.input_box)

    def _process_events(self) -> None:
        if self.qt_app is not None and hasattr(self.qt_app, "processEvents"):
            self.qt_app.processEvents()

    def _start_runtime(self) -> None:
        self.runtime_state.start()

    def _is_running(self) -> bool:
        return self.runtime_state.is_running

    def on_message_sent(self, text: str) -> None:
        logger.info("用户输入: %s", text)
        if self.chat_history_window is not None:
            self.chat_history_window.add_message({
                "role": "user",
                "content": text,
                "message_id": str(uuid.uuid4()),
                "timestamp": time.time(),
            })
        asyncio.create_task(self.process_message(text))

    def on_clear_context_requested(self) -> None:
        logger.info("请求清空当前上下文")
        asyncio.create_task(self.reset_context())

    async def process_message(self, text: str) -> None:
        async with self._context_lock:
            if self._processing:
                logger.warning("Already processing a message, skipping duplicate")
                return
            self._processing = True
            try:
                images: list[dict] = getattr(self.input_box, "get_last_images", lambda: [])()
                await process_chat_message(
                    text=text,
                    input_box=self.input_box,
                    agent=self.agent,
                    websocket=self.ws,
                    is_running=self.runtime_state.is_running,
                    on_response=self._on_assistant_response,
                    images=images,
                )
            finally:
                self._processing = False

    def _on_assistant_response(self, response_text: str) -> None:
        if self.chat_history_window is not None:
            self.chat_history_window.add_message({
                "role": "assistant",
                "content": response_text,
                "message_id": str(uuid.uuid4()),
                "timestamp": time.time(),
            })

    async def reset_context(self) -> None:
        async with self._context_lock:
            if self.agent is None:
                return

            if getattr(self.agent, "memory", None) is not None:
                if not self.agent.memory._initialized:
                    await self.agent.initialize_memory()

                await self.agent.memory.reset_active_context("default")
                self.agent.model.history = (
                    await self.agent.memory.get_current_messages()
                ).copy()
            else:
                self.agent.model.history = []

            if self.input_box is not None:
                self.input_box.clear_input()

    def on_visibility_changed(self, is_visible: bool) -> None:
        logger.debug("输入框可见性变化: %s", is_visible)

    def on_tray_activated(self, reason: Any) -> None:
        from importlib import import_module

        qt_widgets = import_module("PySide6.QtWidgets")
        tray_cls = qt_widgets.QSystemTrayIcon
        if reason in (tray_cls.ActivationReason.Trigger, tray_cls.ActivationReason.DoubleClick):
            if self.input_box is not None and self.input_box.isVisible():
                self.hide_input_box()
            else:
                self.show_input_box()

    def show_input_box(self) -> None:
        if self.input_box is not None:
            self.input_box.show()
            self.input_box.raise_()
            self.input_box.activateWindow()

    def hide_input_box(self) -> None:
        if self.input_box is not None:
            self.input_box.hide()

    def show_chat_history(self) -> None:
        if self.chat_history_window is not None:
            self.chat_history_window.show()
            self.chat_history_window.raise_()
            self.chat_history_window.activateWindow()

    def open_settings(self) -> None:
        logger.info("打开设置窗口")
        from internal.ui.settings_window import SettingsWindow

        if self.settings_window is not None:
            self.settings_window.show()
            self.settings_window.raise_()
            self.settings_window.activateWindow()
            return

        self.settings_window = SettingsWindow(
            config_path=Config.DEFAULT_CONFIG_PATH,
            on_saved=self.on_config_saved,
        )
        self.settings_window.destroyed.connect(self._on_settings_window_destroyed)
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def _on_settings_window_destroyed(self, _obj: Any = None) -> None:
        self.settings_window = None

    def on_config_saved(self, config: Config, decision: RuntimeApplyDecision) -> None:
        asyncio.create_task(self._apply_saved_config(config, decision))

    async def _apply_saved_config(
        self,
        config: Config,
        decision: RuntimeApplyDecision,
    ) -> None:
        messages: list[str] = []

        if decision.websocket_changed:
            websocket_reloaded = await self._reload_websocket(config)
            if websocket_reloaded:
                messages.append("WebSocket 已按新地址重连。")
            else:
                messages.append("WebSocket 按新地址重连失败，请检查配置。")

        if decision.default_model_changed:
            self._reload_agent(config)
            messages.append("默认模型已热更新。")

        self.config = config

        if decision.requires_restart:
            messages.append("部分配置需重启应用后生效。")

        if messages and self.settings_window is not None:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(self.settings_window, "配置已应用", "\n".join(messages))

    async def _reload_websocket(self, config: Config) -> bool:
        from internal.app.bootstrap import create_websocket

        was_running = self.runtime_state.is_running
        old_ws = self.ws
        try:
            new_ws = await create_websocket(config)
            await self.runtime_state.stop()
            if old_ws is not None:
                await old_ws.disconnect()
            self.ws = new_ws
            self.runtime_state.attach(self.ws)
            if was_running:
                self.runtime_state.start()
            return self.ws.is_connected
        except Exception as exc:
            logger.error("WebSocket 热更新失败: %s", exc, exc_info=True)
            if was_running:
                self.runtime_state.start()
            return False

    def _reload_agent(self, config: Config) -> None:
        from internal.app.bootstrap import create_runtime_agent

        self.agent = create_runtime_agent(config)
        if self.bubble_widget is not None:
            self.agent.bubble_widget = self.bubble_widget
        if self.input_box is not None:
            self.input_box.set_agent(self.agent)

    def quit(self) -> None:
        logger.info("正在退出...")
        self.runtime_state.is_running = False

    async def run(self) -> None:
        await self.initialize()
        await self.runtime.run(self._is_running)

    async def cleanup(self) -> None:
        if self.settings_window is not None:
            self.settings_window.close()
            self.settings_window = None
        await cleanup_application(
            input_box=self.input_box,
            bubble_widget=self.bubble_widget,
            websocket=self.ws,
            runtime_state=self.runtime_state,
            qt_app=self.qt_app,
        )
