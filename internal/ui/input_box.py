"""悬浮输入框主模块"""

from collections import deque
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
from PySide6.QtCore import Qt, Signal, Slot, QSettings, QPoint, QTimer
from PySide6.QtGui import QKeyEvent

from .title_bar import TitleBar
from .styles import get_styles


class FloatingInputBox(QWidget):
    """置顶悬浮输入框

    特性:
    - 无边框窗口，始终置顶
    - 支持拖动定位
    - 支持主题切换
    - 集成历史记录管理
    - 支持清空当前活动上下文
    """


    # 信号定义
    message_sent = Signal(str)  # 用户发送消息时触发 (text,)
    visibility_changed = Signal(bool)  # 可见性变化时触发 (is_visible,)
    input_changed = Signal(str)  # 输入内容变化时触发 (text,)
    close_requested = Signal()  # 点击标题栏关闭按钮时触发
    clear_context_requested = Signal()  # 请求清空当前活动上下文时触发

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        agent: Optional[Any] = None,
        title: str = "Agent Chat",
    ):
        super().__init__(parent)

        # 依赖注入
        self.agent = agent

        # 状态管理
        self._is_expanded = True
        self._history = deque(maxlen=50)
        self._history_index = -1
        self._current_input = ""
        self._is_loading = False
        self._drag_pos: Optional[QPoint] = None
        self._is_dragging = False
        # 模式状态
        self._plan_mode_enabled = False
        self._orchestration_mode_enabled = False

        # 设置
        self._settings = QSettings("Live2oder", "FloatingInputBox")
        self._theme = self._settings.value("theme", "dark")
        self._opacity = float(self._settings.value("opacity", 1.0))

        # 初始化 UI
        self.setObjectName("floatingInputBox")
        self.setup_window_flags()
        self.setup_ui()
        self.apply_theme(self._theme)
        self.load_settings()

        # 初始化完成
        self._initialized = True

    def setup_window_flags(self):
        """设置窗口标志"""
        flags = (
            Qt.WindowType.FramelessWindowHint  # 无边框
            | Qt.WindowType.WindowStaysOnTopHint  # 始终置顶
            | Qt.WindowType.Tool  # 工具窗口（不在任务栏显示）
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
        self.title_bar = TitleBar(self, title="Agent Chat")
        self.title_bar.toggle_expand.connect(self.toggle_expand)
        self.title_bar.close_clicked.connect(self.on_close_clicked)
        self.title_bar.mouse_pressed.connect(self.on_title_pressed)
        self.title_bar.mouse_moved.connect(self.on_title_moved)
        self.title_bar.mouse_released.connect(self.on_title_released)
        self.main_layout.addWidget(self.title_bar)

        # 内容区域
        self.content_widget = QWidget(self)
        self.content_widget.setObjectName("contentWidget")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(12, 12, 12, 12)
        self.content_layout.setSpacing(10)

        # 文本输入框
        self.text_edit = QTextEdit(self)
        self.text_edit.setPlaceholderText(
            "输入消息... (Shift+Enter 换行, Ctrl+Enter 发送)"
        )
        self.text_edit.setMaximumHeight(150)
        self.text_edit.setMinimumHeight(60)
        self.text_edit.textChanged.connect(self.on_text_changed)
        self.text_edit.installEventFilter(self)
        self.content_layout.addWidget(self.text_edit, stretch=1)

        # 底部工具栏
        self.bottom_bar = QHBoxLayout()
        self.bottom_bar.setSpacing(8)

        # 左侧工具按钮
        self.clear_btn = QPushButton("清空", self)
        self.clear_btn.setObjectName("toolBtn")
        self.clear_btn.setToolTip("清空输入框 (Ctrl+L)")
        self.clear_btn.clicked.connect(self.clear_input)
        self.bottom_bar.addWidget(self.clear_btn)

        self.history_btn = QPushButton("历史", self)
        self.history_btn.setObjectName("toolBtn")
        self.history_btn.setToolTip("浏览历史 (Ctrl+↑/↓)")
        self.bottom_bar.addWidget(self.history_btn)

        # 清空上下文按钮
        self.new_context_btn = QPushButton("清空上下文", self)
        self.new_context_btn.setObjectName("toolBtn")
        self.new_context_btn.setToolTip("清空当前活动上下文")
        self.new_context_btn.clicked.connect(self.on_clear_context_clicked)
        self.bottom_bar.addWidget(self.new_context_btn)

        # 模式切换复选框
        self.plan_mode_checkbox = QPushButton("Plan模式", self)
        self.plan_mode_checkbox.setObjectName("toolBtn")
        self.plan_mode_checkbox.setCheckable(True)
        self.plan_mode_checkbox.setChecked(False)
        self.plan_mode_checkbox.setToolTip("启用Plan模式")
        self.plan_mode_checkbox.clicked.connect(self.on_plan_mode_toggled)
        self.bottom_bar.addWidget(self.plan_mode_checkbox)

        self.orchestration_mode_checkbox = QPushButton("编排模式", self)
        self.orchestration_mode_checkbox.setObjectName("toolBtn")
        self.orchestration_mode_checkbox.setCheckable(True)
        self.orchestration_mode_checkbox.setChecked(False)
        self.orchestration_mode_checkbox.setToolTip("启用编排模式")
        self.orchestration_mode_checkbox.clicked.connect(self.on_orchestration_mode_toggled)
        self.bottom_bar.addWidget(self.orchestration_mode_checkbox)

        self.bottom_bar.addStretch()

        # 字符计数
        self.char_count_label = QLabel("0/2000", self)
        self.char_count_label.setObjectName("charCount")
        self.bottom_bar.addWidget(self.char_count_label)

        # 发送按钮
        self.send_btn = QPushButton("发送", self)
        self.send_btn.setToolTip("发送消息 (Enter)")
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
        self.setMinimumSize(320, 140)
        self.resize(400, 180)

    def apply_theme(self, theme: str = "dark"):
        """应用主题样式"""
        self._theme = theme
        styles = get_styles(theme)
        self.setStyleSheet(styles["main"])
        self.content_widget.setStyleSheet(styles["main"])

    def load_settings(self):
        """加载保存的设置"""
        # 加载位置
        from PySide6.QtCore import QPoint

        pos = self._settings.value("position", None)
        if pos and isinstance(pos, QPoint):
            self.move(pos)
        else:
            # 默认位置：屏幕右下角
            screen = QApplication.primaryScreen().geometry()
            self.move(
                screen.width() - self.width() - 20,
                screen.height() - self.height() - 100,
            )

        # 加载大小
        size = self._settings.value("size", None)
        if size:
            self.resize(size)

        # 加载展开状态
        self._is_expanded = self._settings.value("expanded", True) in [
            True,
            "true",
            "True",
            1,
        ]
        if not self._is_expanded:
            self.collapse()

    def save_settings(self):
        """保存当前设置"""
        self._settings.setValue("position", self.pos())
        self._settings.setValue("size", self.size())
        self._settings.setValue("expanded", self._is_expanded)
        self._settings.setValue("theme", self._theme)
        self._settings.sync()

    # === 槽函数 ===

    @Slot()
    def toggle_expand(self):
        """切换展开/收起状态"""
        if self._is_expanded:
            self.collapse()
        else:
            self.expand()

    def expand(self):
        """展开输入框"""
        self._is_expanded = True
        self.content_widget.show()
        self.setMinimumHeight(140)
        self.resize(self.width(), 180)

    def collapse(self):
        """收起输入框"""
        self._is_expanded = False
        self.content_widget.hide()
        self.setMinimumHeight(36)
        self.setMaximumHeight(36)
        self.resize(self.width(), 36)

    @Slot(QPoint)
    def on_title_pressed(self, pos: QPoint):
        """标题栏鼠标按下"""
        self._drag_pos = pos
        self._is_dragging = False

    @Slot(QPoint)
    def on_title_moved(self, pos: QPoint):
        """标题栏鼠标移动 - 拖动窗口"""
        if self._drag_pos:
            delta = pos - self._drag_pos
            if delta.manhattanLength() > 3:
                self._is_dragging = True
                self.move(self.pos() + delta)
                self._drag_pos = pos

    @Slot()
    def on_title_released(self):
        """标题栏鼠标释放"""
        self._drag_pos = None
        self._is_dragging = False

    @Slot()
    def on_close_clicked(self):
        """标题栏关闭按钮点击 - 触发关闭请求"""
        self.close_requested.emit()

    @Slot()
    def on_clear_context_clicked(self):
        """清空上下文按钮点击 - 触发清空当前活动上下文请求"""
        self.clear_context_requested.emit()

    @Slot()
    def on_text_changed(self):
        """文本变化处理"""
        text = self.text_edit.toPlainText()
        length = len(text)

        # 更新字符计数
        self.char_count_label.setText(f"{length}/2000")

        # 限制最大长度
        if length > 2000:
            cursor = self.text_edit.textCursor()
            self.text_edit.setPlainText(text[:2000])
            self.text_edit.setTextCursor(cursor)

        # 发送信号
        self.input_changed.emit(text)

    @Slot()
    def clear_input(self):
        """清空输入框"""
        self.text_edit.clear()

    @Slot()
    def send_message(self):
        """发送消息"""
        # Prevent double sending while still processing
        if self._is_loading:
            return  # silently ignore

        text = self.text_edit.toPlainText().strip()
        if not text:
            return

        # 根据当前模式添加标记
        if self._plan_mode_enabled:
            text = f"[Plan模式] {text}"
        elif self._orchestration_mode_enabled:
            text = f"[编排模式] {text}"

        # 添加到历史
        self._history.append(text)
        self._history_index = -1
        self._current_input = ""

        # Set loading flag BEFORE clearing and emitting
        self._is_loading = True

        # 清空输入框
        self.text_edit.clear()

        # 发射信号
        self.message_sent.emit(text)

    # === 事件处理 ===

    def eventFilter(self, obj, event):
        """事件过滤器 - 处理快捷键"""
        if obj == self.text_edit and event.type() == event.Type.KeyPress:
            key_event: QKeyEvent = event
            modifiers = key_event.modifiers()
            key = key_event.key()

            # Ctrl+Enter 发送
            if (
                key == Qt.Key.Key_Return
                and modifiers == Qt.KeyboardModifier.ControlModifier
            ):
                if self._is_loading:
                    return True  # swallow the event to prevent double sending
                self.send_message()
                return True

            # Shift+Enter 换行（默认行为）
            if (
                key == Qt.Key.Key_Return
                and modifiers == Qt.KeyboardModifier.ShiftModifier
            ):
                return False  # 让默认处理

            # Enter 单独按下 - 检查是否需要发送
            if key == Qt.Key.Key_Return and modifiers == Qt.KeyboardModifier.NoModifier:
                if self._is_loading:
                    return True  # swallow the event to prevent double sending
                # 检查是否只有单行文本
                text = self.text_edit.toPlainText()
                if "\n" not in text or len(text.split("\n")) <= 2:
                    self.send_message()
                    return True

            # Ctrl+L 清空
            if key == Qt.Key.Key_L and modifiers == Qt.KeyboardModifier.ControlModifier:
                self.clear_input()
                return True

            # Ctrl+↑ 上一条历史
            if (
                key == Qt.Key.Key_Up
                and modifiers == Qt.KeyboardModifier.ControlModifier
            ):
                prev = self.get_previous_history()
                if prev is not None:
                    self.text_edit.setPlainText(prev)
                    # 移动光标到末尾
                    cursor = self.text_edit.textCursor()
                    cursor.movePosition(cursor.MoveOperation.End)
                    self.text_edit.setTextCursor(cursor)
                return True

            # Ctrl+↓ 下一条历史
            if (
                key == Qt.Key.Key_Down
                and modifiers == Qt.KeyboardModifier.ControlModifier
            ):
                next_text = self.get_next_history()
                if next_text is not None:
                    self.text_edit.setPlainText(next_text)
                    cursor = self.text_edit.textCursor()
                    cursor.movePosition(cursor.MoveOperation.End)
                    self.text_edit.setTextCursor(cursor)
                return True

            # Esc 隐藏窗口
            if key == Qt.Key.Key_Escape:
                self.hide()
                self.visibility_changed.emit(False)
                return True

        return super().eventFilter(obj, event)

    def get_previous_history(self) -> Optional[str]:
        """获取上一条历史"""
        if self._history_index == -1:
            self._current_input = self.text_edit.toPlainText()

        if not self._history:
            return None

        self._history_index = min(self._history_index + 1, len(self._history) - 1)
        return self._history[-(self._history_index + 1)]

    def get_next_history(self) -> Optional[str]:
        """获取下一条历史"""
        if self._history_index <= 0:
            self._history_index = -1
            return self._current_input

        self._history_index -= 1
        if self._history_index >= 0:
            return self._history[-(self._history_index + 1)]
        return self._current_input

    def closeEvent(self, event):
        """关闭事件 - 保存设置"""
        self.save_settings()
        super().closeEvent(event)

    def hideEvent(self, event):
        """隐藏事件"""
        self.save_settings()
        self.visibility_changed.emit(False)
        super().hideEvent(event)

    def showEvent(self, event):
        """显示事件"""
        self.visibility_changed.emit(True)
        # 延迟聚焦到输入框
        QTimer.singleShot(100, self.text_edit.setFocus)
        super().showEvent(event)

    def set_agent(self, agent: Any):
        """设置 Agent 实例"""
        self.agent = agent

    def get_agent(self) -> Optional[Any]:
        """获取 Agent 实例"""
        return self.agent

    def is_expanded(self) -> bool:
        """获取展开状态"""
        return self._is_expanded

    def set_theme(self, theme: str):
        """设置主题"""
        self.apply_theme(theme)
        self._settings.setValue("theme", theme)

    def get_theme(self) -> str:
        """获取当前主题"""
        return self._theme

    # === 模式管理 ===

    @Slot(bool)
    def on_plan_mode_toggled(self, checked: bool):
        """Plan模式切换处理"""
        self._plan_mode_enabled = checked
        # 更新按钮样式以反映状态
        if checked:
            self.plan_mode_checkbox.setStyleSheet("background-color: #4CAF50; color: white;")
            self.text_edit.setPlaceholderText("输入Plan模式指令... (Shift+Enter 换行, Ctrl+Enter 发送)")
        else:
            self.plan_mode_checkbox.setStyleSheet("")
            # 如果编排模式也未启用，恢复默认占位符
            if not self._orchestration_mode_enabled:
                self.text_edit.setPlaceholderText("输入消息... (Shift+Enter 换行, Ctrl+Enter 发送)")

    @Slot(bool)
    def on_orchestration_mode_toggled(self, checked: bool):
        """编排模式切换处理"""
        self._orchestration_mode_enabled = checked
        # 更新按钮样式以反映状态
        if checked:
            self.orchestration_mode_checkbox.setStyleSheet("background-color: #2196F3; color: white;")
            self.text_edit.setPlaceholderText("输入编排模式指令... (Shift+Enter 换行, Ctrl+Enter 发送)")
        else:
            self.orchestration_mode_checkbox.setStyleSheet("")
            # 如果Plan模式也未启用，恢复默认占位符
            if not self._plan_mode_enabled:
                self.text_edit.setPlaceholderText("输入消息... (Shift+Enter 换行, Ctrl+Enter 发送)")

    def is_plan_mode_enabled(self) -> bool:
        """获取Plan模式状态"""
        return self._plan_mode_enabled

    def is_orchestration_mode_enabled(self) -> bool:
        """获取编排模式状态"""
        return self._orchestration_mode_enabled

    def set_plan_mode(self, enabled: bool):
        """设置Plan模式状态"""
        self.plan_mode_checkbox.setChecked(enabled)

    def set_orchestration_mode(self, enabled: bool):
        """设置编排模式状态"""
        self.orchestration_mode_checkbox.setChecked(enabled)
