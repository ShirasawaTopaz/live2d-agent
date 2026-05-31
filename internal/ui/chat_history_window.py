from typing import Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QTextBrowser, QFrame,
)
from PySide6.QtCore import Qt, QSettings
from internal.ui.markdown_renderer import MarkdownRenderer


class _MessageBubble(QFrame):

    def __init__(self, message: dict[str, Any], renderer: MarkdownRenderer, parent=None):
        super().__init__(parent)
        self._message = message
        self._renderer = renderer
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        role = self._message.get("role", "user")
        content = self._message.get("content", "")
        token_count = self._message.get("token_count")

        header = QHBoxLayout()
        role_label = QLabel("User" if role == "user" else "Assistant")
        role_label.setStyleSheet(
            "font-weight: bold; font-size: 11px; color: #4a9eff;"
            if role == "user"
            else "font-weight: bold; font-size: 11px; color: #9d88ff;"
        )
        header.addWidget(role_label)
        header.addStretch()

        if token_count:
            total = token_count.get("total", 0)
            tok_label = QLabel(f"{total:,} tok")
            tok_label.setStyleSheet("font-size: 10px; color: #888;")
            header.addWidget(tok_label)

        layout.addLayout(header)

        html = self._renderer.to_html(content)
        browser = QTextBrowser()
        browser.setHtml(html)
        browser.setFrameShape(QTextBrowser.Shape.NoFrame)
        browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        browser.setOpenExternalLinks(False)
        browser.setStyleSheet("background: transparent; color: white; font-size: 13px;")
        doc_height = browser.document().size().height()
        browser.setFixedHeight(int(doc_height) + 10)
        layout.addWidget(browser)

        if role == "assistant":
            self.setStyleSheet("QFrame { border-bottom: 1px solid #333; }")


class ChatHistoryWindow(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._renderer = MarkdownRenderer()
        self._messages: list[dict[str, Any]] = []
        self._session_input_tokens = 0
        self._session_output_tokens = 0
        self._model_name = ""

        self.setWindowTitle("Chat History")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        )
        self.resize(500, 600)
        self.setStyleSheet("background: #1e1e1e;")
        self._settings = QSettings("Live2oder", "ChatHistoryWindow")
        self._load_settings()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(12, 8, 12, 8)
        title_label = QLabel("Chat History")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: white;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setFixedSize(60, 24)
        self._clear_btn.setStyleSheet(
            "QPushButton { background: #555; color: white; border: none; border-radius: 4px; }"
            "QPushButton:hover { background: #777; }"
        )
        self._clear_btn.clicked.connect(self.clear_messages)
        title_layout.addWidget(self._clear_btn)

        self._close_btn = QPushButton("X")
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.setStyleSheet(
            "QPushButton { background: #c0392b; color: white; border: none; border-radius: 4px; }"
            "QPushButton:hover { background: #e74c3c; }"
        )
        self._close_btn.clicked.connect(self.hide)
        title_layout.addWidget(self._close_btn)

        layout.addLayout(title_layout)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setStyleSheet(
            "QScrollArea { background: #1e1e1e; border: none; }"
            "QScrollBar:vertical { background: #2d2d2d; width: 8px; }"
            "QScrollBar::handle:vertical { background: #555; border-radius: 4px; }"
        )

        self._message_container = QWidget()
        self._message_container.setStyleSheet("background: #1e1e1e;")
        self._message_layout = QVBoxLayout(self._message_container)
        self._message_layout.setContentsMargins(0, 0, 0, 0)
        self._message_layout.setSpacing(0)
        self._message_layout.addStretch()
        self._scroll_area.setWidget(self._message_container)
        layout.addWidget(self._scroll_area)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet(
            "background: #252525; color: #888; font-size: 11px; padding: 6px 12px;"
        )
        self._update_status()
        layout.addWidget(self._status_label)

    def add_message(self, message: dict[str, Any]) -> None:
        self._messages.append(message)
        token_count = message.get("token_count")
        if message.get("role") == "assistant" and token_count:
            self._session_input_tokens += token_count.get("input", 0)
            self._session_output_tokens += token_count.get("output", 0)
        bubble = _MessageBubble(message, self._renderer, self._message_container)
        self._message_layout.insertWidget(self._message_layout.count() - 1, bubble)
        self._update_status()
        self._scroll_to_bottom()

    def clear_messages(self) -> None:
        self._messages.clear()
        self._session_input_tokens = 0
        self._session_output_tokens = 0
        while self._message_layout.count() > 1:
            item = self._message_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._update_status()

    def set_model_name(self, name: str) -> None:
        self._model_name = name
        self._update_status()

    def _update_status(self) -> None:
        parts = []
        if self._model_name:
            parts.append(f"Model: {self._model_name}")
        parts.append(
            f"\u2191{self._session_input_tokens:,} \u2193{self._session_output_tokens:,}"
        )
        parts.append(f"Total: {self._session_input_tokens + self._session_output_tokens:,}")
        self._status_label.setText("   |   ".join(parts))

    def _message_count(self) -> int:
        return len(self._messages)

    def _scroll_to_bottom(self) -> None:
        scrollbar = self._scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _load_settings(self) -> None:
        if self._settings.contains("position"):
            pos = self._settings.value("position")
            if pos:
                self.move(pos)
        if self._settings.contains("size"):
            size = self._settings.value("size")
            if size:
                self.resize(size)

    def _save_settings(self) -> None:
        self._settings.setValue("position", self.pos())
        self._settings.setValue("size", self.size())

    def hideEvent(self, event):
        self._save_settings()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._save_settings()
        self.hide()
        event.ignore()
