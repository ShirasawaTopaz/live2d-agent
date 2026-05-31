"""悬浮输入框主模块 - 紧凑型 redesign"""

import os
import uuid
from collections import deque
from pathlib import Path
from typing import Optional, Any

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QLabel,
    QApplication,
    QSizeGrip,
)
from PySide6.QtCore import (
    Qt, Signal, Slot, QSettings, QPoint, QTimer,
    QPropertyAnimation, QEasingCurve,
)
from PySide6.QtGui import QKeyEvent, QImage, QPixmap

from .title_bar import TitleBar
from .styles import get_styles

# Minimum height when collapsed (just the title bar)
COLLAPSED_HEIGHT = 32
# Minimum height when expanded (title bar + input area + toolbar)
EXPANDED_MIN_HEIGHT = 140
# Maximum height when expanded
EXPANDED_MAX_HEIGHT = 500


class FloatingInputBox(QWidget):
    """置顶悬浮输入框

    紧凑型 redesign 特性:
    - 无边框窗口，始终置顶
    - 模式标签页切换 (chat/plan/orchestration)
    - 底部图标+文字混合工具栏
    - 输入为空时发送按钮置灰
    - 展开/收起平滑动画
    - 暗色/亮色主题
    """

    # 信号定义
    message_sent = Signal(str)
    visibility_changed = Signal(bool)
    input_changed = Signal(str)
    close_requested = Signal()
    clear_context_requested = Signal()

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        agent: Optional[Any] = None,
    ):
        super().__init__(parent)

        self.agent = agent

        # 状态管理
        self._is_expanded = True
        self._history = deque(maxlen=50)
        self._history_index = -1
        self._current_input = ""
        self._is_loading = False
        self._drag_pos: Optional[QPoint] = None
        self._is_dragging = False
        self._plan_mode_enabled = False
        self._orchestration_mode_enabled = False
        self._target_expanded_height = 180

        # 图片支持
        self._image_files: list[str] = []
        self._image_preview = QLabel(self)
        self._image_preview.setObjectName("imagePreview")
        self._image_preview.setFixedHeight(64)
        self._image_preview.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._image_preview.hide()

        # 设置
        self._settings = QSettings("Live2oder", "FloatingInputBox")
        self._theme = self._settings.value("theme", "dark")
        self._opacity = float(self._settings.value("opacity", 1.0))

        # 动画
        self._expand_animation = QPropertyAnimation(self, b"minimumHeight")
        self._expand_animation.setDuration(200)
        self._expand_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._collapse_animation = QPropertyAnimation(self, b"maximumHeight")
        self._collapse_animation.setDuration(200)
        self._collapse_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 初始化 UI
        self.setObjectName("floatingInputBox")
        self.setup_window_flags()
        self.setup_ui()
        self.setAcceptDrops(True)
        self.apply_theme(self._theme)
        self.load_settings()

    def setup_window_flags(self):
        """设置窗口标志"""
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setWindowOpacity(self._opacity)

    def setup_ui(self):
        """初始化 UI 组件"""
        # 主布局
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 标题栏
        self.title_bar = TitleBar(self)
        self.title_bar.toggle_expand.connect(self.toggle_expand)
        self.title_bar.close_clicked.connect(self.on_close_clicked)
        self.title_bar.mouse_pressed.connect(self.on_title_pressed)
        self.title_bar.mouse_moved.connect(self.on_title_moved)
        self.title_bar.mouse_released.connect(self.on_title_released)
        self.title_bar.mode_changed.connect(self.on_mode_changed)
        self.title_bar.collapsed_send_clicked.connect(self.on_collapsed_send)
        self.title_bar.collapsed_text_changed.connect(self.on_collapsed_text_changed)
        self.title_bar.collapsed_return_pressed.connect(self.on_collapsed_return_pressed)
        self.main_layout.addWidget(self.title_bar)

        # 内容区域
        self.content_widget = QWidget(self)
        self.content_widget.setObjectName("contentWidget")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(12, 10, 12, 12)
        self.content_layout.setSpacing(8)

        # 文本输入框
        self.text_edit = QTextEdit(self)
        self.text_edit.setPlaceholderText("输入消息... (Shift+Enter 换行, Ctrl+Enter 发送)")
        self.text_edit.setMaximumHeight(120)
        self.text_edit.setMinimumHeight(60)
        self.text_edit.textChanged.connect(self.on_text_changed)
        self.text_edit.installEventFilter(self)
        self.content_layout.addWidget(self.text_edit, stretch=1)
        self.content_layout.addWidget(self._image_preview)

        # 底部工具栏
        self.bottom_bar = QHBoxLayout()
        self.bottom_bar.setSpacing(2)

        # 左侧工具按钮
        self.image_btn = QPushButton("📎 图片", self)
        self.image_btn.setObjectName("toolBtn")
        self.image_btn.setToolTip("添加图片 (拖放)")
        self.image_btn.clicked.connect(self.on_image_btn_clicked)
        self.bottom_bar.addWidget(self.image_btn)

        self.voice_btn = QPushButton("🎤 语音", self)
        self.voice_btn.setObjectName("toolBtn")
        self.voice_btn.setToolTip("语音输入")
        self.voice_btn.setEnabled(False)
        self.bottom_bar.addWidget(self.voice_btn)

        self.clear_btn = QPushButton("🧹 清空", self)
        self.clear_btn.setObjectName("toolBtn")
        self.clear_btn.setToolTip("清空输入框 (Ctrl+L)")
        self.clear_btn.clicked.connect(self.clear_input)
        self.bottom_bar.addWidget(self.clear_btn)

        self.history_btn = QPushButton("📋 历史", self)
        self.history_btn.setObjectName("toolBtn")
        self.history_btn.setToolTip("浏览历史 (Ctrl+↑/↓)")
        self.bottom_bar.addWidget(self.history_btn)

        # 清空上下文按钮
        self.new_context_btn = QPushButton("🗑 清空上下文", self)
        self.new_context_btn.setObjectName("toolBtn")
        self.new_context_btn.setToolTip("清空当前活动上下文")
        self.new_context_btn.clicked.connect(self.on_clear_context_clicked)
        self.bottom_bar.addWidget(self.new_context_btn)

        self.bottom_bar.addStretch(1)

        # 字符计数
        self.char_count_label = QLabel("0/2000", self)
        self.char_count_label.setObjectName("charCount")
        self.bottom_bar.addWidget(self.char_count_label)

        # 发送按钮
        self.send_btn = QPushButton("发送", self)
        self.send_btn.setObjectName("sendBtn")
        self.send_btn.setToolTip("发送消息 (Enter)")
        self.send_btn.setEnabled(False)
        self.send_btn.clicked.connect(self.send_message)
        self.bottom_bar.addWidget(self.send_btn)

        self.content_layout.addLayout(self.bottom_bar)

        # 大小调整手柄
        self.size_grip = QSizeGrip(self)
        self.size_grip.setFixedSize(16, 16)
        grip_layout = QHBoxLayout()
        grip_layout.addStretch()
        grip_layout.addWidget(self.size_grip)
        self.content_layout.addLayout(grip_layout)

        self.main_layout.addWidget(self.content_widget)

        # 设置初始大小
        self.setMinimumSize(320, EXPANDED_MIN_HEIGHT)
        self.resize(420, EXPANDED_MIN_HEIGHT)

    # === Theme ===

    def apply_theme(self, theme: str = "dark"):
        """应用主题样式"""
        self._theme = theme
        styles = get_styles(theme)
        self.setStyleSheet(styles["main"])
        self.content_widget.setStyleSheet(styles["main"])

    def load_settings(self):
        """加载保存的设置"""
        pos = self._settings.value("position", None)
        if pos and isinstance(pos, QPoint):
            self.move(pos)
        else:
            screen = QApplication.primaryScreen().geometry()
            self.move(
                screen.width() - self.width() - 20,
                screen.height() - self.height() - 100,
            )

        size = self._settings.value("size", None)
        if size:
            self.resize(size)
            self._target_expanded_height = size.height()

        self._is_expanded = self._settings.value("expanded", True) in [True, "true", "True", 1]
        if not self._is_expanded:
            self.content_widget.hide()
            self.title_bar.set_expanded(False)
            self.setMinimumHeight(COLLAPSED_HEIGHT)
            self.setMaximumHeight(COLLAPSED_HEIGHT)
            self.resize(self.width(), COLLAPSED_HEIGHT)

    def save_settings(self):
        """保存当前设置"""
        self._settings.setValue("position", self.pos())
        current_size = self.size()
        if self._is_expanded:
            self._settings.setValue("size", current_size)
        self._settings.setValue("expanded", self._is_expanded)
        self._settings.setValue("theme", self._theme)
        self._settings.sync()

    # === Image support ===

    def dragEnterEvent(self, event):
        if event is None:
            return
        mime = event.mimeData()
        if mime and mime.hasImage():
            event.acceptProposedAction()
            return
        if mime and mime.hasUrls():
            for url in mime.urls():
                path = url.toLocalFile()
                if path and path.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp")):
                    event.acceptProposedAction()
                    return
        super().dragEnterEvent(event)

    def dropEvent(self, event):
        if event is None:
            return
        mime = event.mimeData()
        if mime and mime.hasImage():
            image = QImage(mime.imageData())
            self._save_and_preview_image(image)
            event.acceptProposedAction()
            return
        if mime and mime.hasUrls():
            for url in mime.urls():
                path = url.toLocalFile()
                if path and path.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp")):
                    self._add_image_file(path)
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def _save_and_preview_image(self, image):
        tmp_dir = Path("data/tmp/images")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.png"
        filepath = str(tmp_dir / filename)
        image.save(filepath, "PNG")
        self._add_image_file(filepath)

    def _add_image_file(self, filepath):
        self._image_files.append(filepath)
        self._update_image_preview()

    def _remove_image_file(self, index):
        if 0 <= index < len(self._image_files):
            path = self._image_files.pop(index)
            try:
                os.remove(path)
            except OSError:
                pass
        self._update_image_preview()

    def _update_image_preview(self):
        if not self._image_files:
            self._image_preview.hide()
            return
        first = self._image_files[0]
        pixmap = QPixmap(first)
        if not pixmap.isNull():
            preview = pixmap.scaledToHeight(48, Qt.TransformationMode.SmoothTransformation)
            self._image_preview.setPixmap(preview)
        count = len(self._image_files)
        text = f" +{count - 1} more" if count > 1 else ""
        self._image_preview.setToolTip(f"{count} image(s){text}")
        self._image_preview.show()

    def cleanup_images(self):
        for path in self._image_files:
            try:
                os.remove(path)
            except OSError:
                pass
        self._image_files.clear()
        self._image_preview.clear()
        self._image_preview.hide()

    def get_last_images(self) -> list[str]:
        return getattr(self, "_last_images", [])

    # === Slots ===

    @Slot()
    def toggle_expand(self):
        """切换展开/收起状态"""
        if self._is_expanded:
            self.collapse()
        else:
            self.expand()

    def expand(self):
        """展开输入框 - 平滑动画"""
        self._is_expanded = True
        self.title_bar.set_expanded(True)
        self.content_widget.show()

        self.setMaximumHeight(EXPANDED_MAX_HEIGHT)
        target_h = max(EXPANDED_MIN_HEIGHT, self._target_expanded_height)

        self._collapse_animation.stop()

        self._expand_animation.setStartValue(COLLAPSED_HEIGHT)
        self._expand_animation.setEndValue(target_h)
        self._expand_animation.start()

        QTimer.singleShot(200, self.text_edit.setFocus)

    def collapse(self):
        """收起输入框 - 平滑动画"""
        self._is_expanded = False
        self.title_bar.set_expanded(False)

        current_h = self.height()
        self._target_expanded_height = max(current_h, EXPANDED_MIN_HEIGHT)

        self._expand_animation.stop()

        self.setMinimumHeight(current_h)
        self._collapse_animation.setStartValue(current_h)
        self._collapse_animation.setEndValue(COLLAPSED_HEIGHT)
        self._collapse_animation.finished.connect(self._on_collapse_finished)
        self._collapse_animation.start()

    def _on_collapse_finished(self):
        self._collapse_animation.finished.disconnect(self._on_collapse_finished)
        self.content_widget.hide()
        self.setMaximumHeight(COLLAPSED_HEIGHT)
        self.setMinimumHeight(COLLAPSED_HEIGHT)
        self.resize(self.width(), COLLAPSED_HEIGHT)
        self.title_bar.collapsed_input.setFocus()

    @Slot(QPoint)
    def on_title_pressed(self, pos: QPoint):
        self._drag_pos = pos
        self._is_dragging = False

    @Slot(QPoint)
    def on_title_moved(self, pos: QPoint):
        if self._drag_pos:
            delta = pos - self._drag_pos
            if delta.manhattanLength() > 3:
                self._is_dragging = True
                self.move(self.pos() + delta)
                self._drag_pos = pos

    @Slot()
    def on_title_released(self):
        self._drag_pos = None
        self._is_dragging = False

    @Slot()
    def on_close_clicked(self):
        self.close_requested.emit()

    @Slot()
    def on_image_btn_clicked(self):
        """Placeholder for image picker dialog"""
        # TODO: implement file picker dialog
        pass

    @Slot()
    def on_clear_context_clicked(self):
        self.clear_context_requested.emit()

    @Slot(str)
    def on_mode_changed(self, mode_id: str):
        """Handle mode tab switch"""
        self._plan_mode_enabled = (mode_id == "plan")
        self._orchestration_mode_enabled = (mode_id == "orchestration")
        if mode_id == "plan":
            self.text_edit.setPlaceholderText("输入Plan模式指令... (Shift+Enter 换行, Ctrl+Enter 发送)")
        elif mode_id == "orchestration":
            self.text_edit.setPlaceholderText("输入编排模式指令... (Shift+Enter 换行, Ctrl+Enter 发送)")
        else:
            self.text_edit.setPlaceholderText("输入消息... (Shift+Enter 换行, Ctrl+Enter 发送)")

    @Slot()
    def on_collapsed_send(self):
        """Send from collapsed bar"""
        text = self.title_bar.get_collapsed_text().strip()
        if text:
            self.emit_message(text)
            self.title_bar.set_collapsed_text("")

    @Slot(str)
    def on_collapsed_text_changed(self, text: str):
        """Update send button state in collapsed mode"""
        self.title_bar.set_collapsed_send_enabled(bool(text.strip()))

    @Slot()
    def on_collapsed_return_pressed(self):
        """Enter pressed in collapsed input"""
        self.on_collapsed_send()

    @Slot()
    def on_text_changed(self):
        """文本变化处理"""
        text = self.text_edit.toPlainText()
        length = len(text)

        # Update send button enabled state
        self.send_btn.setEnabled(bool(text.strip()) and not self._is_loading)

        # 更新字符计数
        self.char_count_label.setText(f"{length}/2000")

        # 限制最大长度
        if length > 2000:
            cursor = self.text_edit.textCursor()
            self.text_edit.setPlainText(text[:2000])
            self.text_edit.setTextCursor(cursor)

        self.input_changed.emit(text)

    @Slot()
    def clear_input(self):
        """清空输入框"""
        self.text_edit.clear()

    def emit_message(self, text: str):
        """Internal: emit message_sent signal with mode prefix"""
        # Store original text in history before adding prefix
        self._history.append(text)
        self._history_index = -1
        self._current_input = ""

        if self._plan_mode_enabled:
            text = f"[Plan模式] {text}"
        elif self._orchestration_mode_enabled:
            text = f"[编排模式] {text}"

        self._is_loading = True

        self._last_images = list(self._image_files)
        self._image_files.clear()
        self._image_preview.clear()
        self._image_preview.hide()

        self.text_edit.clear()

        self.message_sent.emit(text)

    @Slot()
    def send_message(self):
        """发送消息"""
        if self._is_loading:
            return

        text = self.text_edit.toPlainText().strip()
        if not text:
            return

        self.emit_message(text)

    # === Event handling ===

    def eventFilter(self, obj, event):
        if obj == self.text_edit and event.type() == event.Type.KeyPress:
            key_event: QKeyEvent = event
            modifiers = key_event.modifiers()
            key = key_event.key()

            if key == Qt.Key.Key_Return and modifiers == Qt.KeyboardModifier.ControlModifier:
                if self._is_loading:
                    return True
                self.send_message()
                return True

            if key == Qt.Key.Key_Return and modifiers == Qt.KeyboardModifier.ShiftModifier:
                return False

            if key == Qt.Key.Key_Return and modifiers == Qt.KeyboardModifier.NoModifier:
                if self._is_loading:
                    return True
                text = self.text_edit.toPlainText()
                if "\n" not in text or len(text.split("\n")) <= 2:
                    self.send_message()
                    return True

            if key == Qt.Key.Key_L and modifiers == Qt.KeyboardModifier.ControlModifier:
                self.clear_input()
                return True

            if key == Qt.Key.Key_Up and modifiers == Qt.KeyboardModifier.ControlModifier:
                prev = self.get_previous_history()
                if prev is not None:
                    self.text_edit.setPlainText(prev)
                    cursor = self.text_edit.textCursor()
                    cursor.movePosition(cursor.MoveOperation.End)
                    self.text_edit.setTextCursor(cursor)
                return True

            if key == Qt.Key.Key_Down and modifiers == Qt.KeyboardModifier.ControlModifier:
                next_text = self.get_next_history()
                if next_text is not None:
                    self.text_edit.setPlainText(next_text)
                    cursor = self.text_edit.textCursor()
                    cursor.movePosition(cursor.MoveOperation.End)
                    self.text_edit.setTextCursor(cursor)
                return True

            if key == Qt.Key.Key_Escape:
                self.hide()
                self.visibility_changed.emit(False)
                return True

        return super().eventFilter(obj, event)

    def get_previous_history(self) -> Optional[str]:
        if self._history_index == -1:
            self._current_input = self.text_edit.toPlainText()
        if not self._history:
            return None
        self._history_index = min(self._history_index + 1, len(self._history) - 1)
        return self._history[-(self._history_index + 1)]

    def get_next_history(self) -> Optional[str]:
        if self._history_index <= 0:
            self._history_index = -1
            return self._current_input
        self._history_index -= 1
        if self._history_index >= 0:
            return self._history[-(self._history_index + 1)]
        return self._current_input

    def resizeEvent(self, event):
        """Track expanded height when user resizes"""
        if self._is_expanded:
            self._target_expanded_height = self.height()
        super().resizeEvent(event)

    def closeEvent(self, event):
        self.save_settings()
        super().closeEvent(event)

    def hideEvent(self, event):
        self.save_settings()
        self.visibility_changed.emit(False)
        super().hideEvent(event)

    def showEvent(self, event):
        self.visibility_changed.emit(True)
        if self._is_expanded:
            QTimer.singleShot(100, self.text_edit.setFocus)
        else:
            QTimer.singleShot(100, self.title_bar.collapsed_input.setFocus)
        super().showEvent(event)

    def set_agent(self, agent: Any):
        self.agent = agent

    def get_agent(self) -> Optional[Any]:
        return self.agent

    def set_loading(self, loading: bool):
        """Set loading state and update send button"""
        self._is_loading = loading
        self.send_btn.setEnabled(bool(self.text_edit.toPlainText().strip()) and not loading)

    def is_expanded(self) -> bool:
        return self._is_expanded

    def set_theme(self, theme: str):
        self.apply_theme(theme)
        self._settings.setValue("theme", theme)

    def get_theme(self) -> str:
        return self._theme

    def set_plan_mode(self, enabled: bool):
        self._plan_mode_enabled = enabled
        self._orchestration_mode_enabled = False
        self.title_bar.set_mode("plan" if enabled else "chat")
        if enabled:
            self.text_edit.setPlaceholderText("输入Plan模式指令... (Shift+Enter 换行, Ctrl+Enter 发送)")
        else:
            self.text_edit.setPlaceholderText("输入消息... (Shift+Enter 换行, Ctrl+Enter 发送)")

    def set_orchestration_mode(self, enabled: bool):
        self._orchestration_mode_enabled = enabled
        self._plan_mode_enabled = False
        self.title_bar.set_mode("orchestration" if enabled else "chat")
        if enabled:
            self.text_edit.setPlaceholderText("输入编排模式指令... (Shift+Enter 换行, Ctrl+Enter 发送)")
        else:
            self.text_edit.setPlaceholderText("输入消息... (Shift+Enter 换行, Ctrl+Enter 发送)")

    def is_plan_mode_enabled(self) -> bool:
        return self._plan_mode_enabled

    def is_orchestration_mode_enabled(self) -> bool:
        return self._orchestration_mode_enabled
