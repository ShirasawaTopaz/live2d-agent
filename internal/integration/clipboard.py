"""Clipboard monitoring and mini action bar for quick text processing."""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ClipAction:
    """A quick action available on the clipboard mini bar."""

    id: str
    label: str
    prompt_template: str

    def resolve_prompt(self, text: str) -> str:
        return self.prompt_template.replace("{text}", text)

    @staticmethod
    def defaults() -> list["ClipAction"]:
        return [
            ClipAction(
                id="summarize", label="📝 总结",
                prompt_template="请用简洁的中文总结以下内容，保留关键信息:\n\n{text}",
            ),
            ClipAction(
                id="translate", label="🌐 翻译",
                prompt_template="请将以下内容翻译成中文:\n\n{text}",
            ),
            ClipAction(
                id="rewrite", label="🔄 改写",
                prompt_template="请改写以下内容，保持原意但使表达更流畅专业:\n\n{text}",
            ),
            ClipAction(
                id="explain_code", label="💻 解释代码",
                prompt_template="请解释以下代码的作用和工作原理:\n\n{text}",
            ),
        ]


class MiniActionBar:
    """Frameless popup widget shown near mouse position."""

    def __init__(self, actions: list[ClipAction], on_action: Any = None):
        self.actions = actions
        self.on_action = on_action
        self._widget: Any = None
        self._dismiss_timer: Any = None

    def show(self, clipboard_text: str) -> None:
        try:
            from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QApplication
            from PySide6.QtCore import Qt, QTimer, QPoint
        except ImportError:
            logger.warning("PySide6 not available, MiniActionBar disabled")
            return

        self.dismiss()
        self._widget = QWidget()
        self._widget.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.Popup
        )
        self._widget.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._widget.setStyleSheet(
            "QWidget { background: #2d2d2d; border: 1px solid #555; border-radius: 6px; padding: 4px; }"
        )
        layout = QHBoxLayout(self._widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #999; border: none; font-size: 14px; }"
            "QPushButton:hover { color: #fff; }"
        )
        close_btn.clicked.connect(self.dismiss)
        layout.addWidget(close_btn)

        for action in self.actions:
            btn = QPushButton(action.label)
            btn.setStyleSheet(
                "QPushButton { background: #3a3a3a; color: #ddd; border: none; "
                "border-radius: 4px; padding: 4px 10px; font-size: 12px; }"
                "QPushButton:hover { background: #4a6a9a; color: #fff; }"
            )
            btn.clicked.connect(
                lambda checked=False, a=action, t=clipboard_text: self._on_click(a, t)
            )
            layout.addWidget(btn)

        self._widget.adjustSize()
        cursor_pos = (
            QApplication.instance().screens()[0].cursor().pos()
            if QApplication.instance() else QPoint(100, 100)
        )
        self._widget.move(cursor_pos + QPoint(10, 10))
        self._widget.show()

        self._dismiss_timer = QTimer(self._widget)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.dismiss)
        self._dismiss_timer.start(3000)

    def _on_click(self, action: ClipAction, text: str) -> None:
        self.dismiss()
        if self.on_action is not None:
            self.on_action(action, text)

    def dismiss(self) -> None:
        if self._dismiss_timer is not None:
            self._dismiss_timer.stop()
            self._dismiss_timer = None
        if self._widget is not None:
            self._widget.close()
            self._widget.deleteLater()
            self._widget = None


class ClipboardMonitor:
    """Monitors clipboard for text changes."""

    def __init__(self, actions: list[ClipAction] | None = None):
        self.actions = actions or ClipAction.defaults()
        self.enabled = False
        self._clipboard: Any = None
        self._last_text: str = ""
        self._on_action_callback: Any = None

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if enabled:
            self._start()
        else:
            self._stop()

    def set_on_action(self, callback: Any) -> None:
        self._on_action_callback = callback

    def _start(self) -> None:
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is None:
                return
            self._clipboard = app.clipboard()
            if self._clipboard is not None:
                self._clipboard.dataChanged.connect(self._on_clipboard_change)
                logger.debug("ClipboardMonitor started")
        except Exception:
            logger.warning("Failed to start ClipboardMonitor", exc_info=True)

    def _stop(self) -> None:
        if self._clipboard is not None:
            try:
                self._clipboard.dataChanged.disconnect(self._on_clipboard_change)
            except Exception:
                pass
            self._clipboard = None
            logger.debug("ClipboardMonitor stopped")

    def _on_clipboard_change(self) -> None:
        if not self.enabled or self._clipboard is None:
            return
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            return
        mime_data = self._clipboard.mimeData()
        if mime_data is None or not mime_data.hasText():
            return
        text = mime_data.text().strip()
        if not text or len(text) < 3:
            return
        if text == self._last_text:
            return
        self._last_text = text
        logger.debug("Clipboard changed: %d chars", len(text))
        bar = MiniActionBar(self.actions, on_action=self._handle_action)
        bar.show(text)

    def _handle_action(self, action: ClipAction, text: str) -> None:
        logger.info("Clipboard action '%s' selected (%d chars)", action.id, len(text))
        if self._on_action_callback is not None:
            self._on_action_callback(action, text)
