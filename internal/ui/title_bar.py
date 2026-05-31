"""可拖动标题栏组件 - 带模式标签页"""

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QButtonGroup,
)
from PySide6.QtCore import Qt, Signal, QPoint


class TitleBar(QWidget):
    """自定义标题栏，支持模式切换标签页和收起状态"""

    toggle_expand = Signal()
    close_clicked = Signal()
    mouse_pressed = Signal(QPoint)
    mouse_moved = Signal(QPoint)
    mouse_released = Signal()
    mode_changed = Signal(str)  # "chat", "plan", "orchestration"
    collapsed_send_clicked = Signal()
    collapsed_text_changed = Signal(str)
    collapsed_return_pressed = Signal()

    MODES = [
        ("chat", "对话"),
        ("plan", "Plan"),
        ("orchestration", "编排"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_expanded = True
        self._drag_pos = None
        self._is_dragging = False

        self.setObjectName("titleBar")
        self.setFixedHeight(36)

        self.setup_ui()
        self._apply_collapsed_state(False)

    def setup_ui(self):
        """初始化 UI 组件"""
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 0, 10, 0)
        self.layout.setSpacing(6)

        # ====== Expanded mode layout ======
        # Mode tabs
        self.mode_tab_widget = QWidget()
        self.mode_tab_widget.setObjectName("modeTab")
        tab_layout = QHBoxLayout(self.mode_tab_widget)
        tab_layout.setContentsMargins(2, 2, 2, 2)
        tab_layout.setSpacing(0)

        self._tab_group = QButtonGroup(self)
        self._tab_buttons = {}
        for mode_id, mode_label in self.MODES:
            btn = QPushButton(mode_label, self)
            btn.setObjectName("modeTabBtn")
            btn.setCheckable(True)
            btn.setFixedHeight(22)
            self._tab_group.addButton(btn)
            self._tab_buttons[mode_id] = btn
            tab_layout.addWidget(btn)

        self._tab_group.buttonClicked.connect(self._on_mode_tab_clicked)
        self._tab_buttons["chat"].setChecked(True)

        self.layout.addWidget(self.mode_tab_widget)

        # Spacer
        self.layout.addStretch(1)

        # Title label
        self.title_label = QLabel("⌘ AI", self)
        self.title_label.setObjectName("titleLabel")
        self.layout.addWidget(self.title_label)

        # Minimize button
        self.min_btn = QPushButton("−", self)
        self.min_btn.setObjectName("windowBtn")
        self.min_btn.setToolTip("最小化")
        self.min_btn.setFixedSize(24, 24)
        self.min_btn.clicked.connect(self.on_minimize)
        self.layout.addWidget(self.min_btn)

        # Close button
        self.close_btn = QPushButton("×", self)
        self.close_btn.setObjectName("closeBtn")
        self.close_btn.setToolTip("隐藏")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.clicked.connect(self.on_close)
        self.layout.addWidget(self.close_btn)

        # ====== Collapsed mode layout ======
        self.collapsed_input = QLineEdit()
        self.collapsed_input.setObjectName("collapsedInput")
        self.collapsed_input.setPlaceholderText("输入消息...")
        self.collapsed_input.textChanged.connect(self.collapsed_text_changed.emit)
        self.collapsed_input.returnPressed.connect(self.collapsed_return_pressed.emit)
        # hidden by default
        self.collapsed_input.hide()

        self.collapsed_send_btn = QPushButton("发送")
        self.collapsed_send_btn.setObjectName("sendBtn")
        self.collapsed_send_btn.setFixedHeight(22)
        self.collapsed_send_btn.setEnabled(False)
        self.collapsed_send_btn.clicked.connect(self.collapsed_send_clicked.emit)
        self.collapsed_send_btn.hide()

        self.layout.insertWidget(1, self.collapsed_input, stretch=1)
        self.layout.insertWidget(2, self.collapsed_send_btn)

    def _on_mode_tab_clicked(self, btn):
        for mode_id, tab_btn in self._tab_buttons.items():
            if tab_btn is btn:
                self.mode_changed.emit(mode_id)
                break

    def set_mode(self, mode_id: str):
        """Set active mode tab"""
        if mode_id in self._tab_buttons:
            self._tab_buttons[mode_id].setChecked(True)

    def get_mode(self) -> str:
        """Get currently active mode"""
        for mode_id, btn in self._tab_buttons.items():
            if btn.isChecked():
                return mode_id
        return "chat"

    def set_collapsed_text(self, text: str):
        """Update collapsed input text"""
        self.collapsed_input.setText(text)

    def get_collapsed_text(self) -> str:
        """Get collapsed input text"""
        return self.collapsed_input.text()

    def set_collapsed_send_enabled(self, enabled: bool):
        """Enable/disable collapsed send button"""
        self.collapsed_send_btn.setEnabled(enabled)

    def _apply_collapsed_state(self, collapsed: bool):
        """Toggle visibility of expanded vs collapsed elements"""
        self.mode_tab_widget.setVisible(not collapsed)
        self.title_label.setVisible(not collapsed)
        self.min_btn.setVisible(not collapsed)
        self.close_btn.setVisible(not collapsed)
        self.collapsed_input.setVisible(collapsed)
        self.collapsed_send_btn.setVisible(collapsed)

        if collapsed:
            self.setProperty("state", "collapsed")
            self.setFixedHeight(32)
        else:
            self.setProperty("state", None)
            self.setFixedHeight(36)

        # Force style recalculation
        self.style().unpolish(self)
        self.style().polish(self)

    def set_expanded(self, expanded: bool):
        """Toggle expanded/collapsed"""
        self._is_expanded = expanded
        self._apply_collapsed_state(not expanded)

    def is_expanded(self):
        return self._is_expanded

    def on_minimize(self):
        window = self.window()
        if window:
            window.showMinimized()

    def on_close(self):
        self.close_clicked.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
            self._is_dragging = False
            self.mouse_pressed.emit(self._drag_pos)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            new_pos = event.globalPosition().toPoint()
            delta = new_pos - self._drag_pos
            if delta.manhattanLength() > 3:
                self._is_dragging = True
                self.mouse_moved.emit(new_pos)
                self._drag_pos = new_pos
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.mouse_released.emit()
            self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            if (not self.min_btn.geometry().contains(pos)
                    and not self.close_btn.geometry().contains(pos)
                    and not self.collapsed_send_btn.geometry().contains(pos)):
                self.toggle_expand.emit()
        super().mouseDoubleClickEvent(event)
