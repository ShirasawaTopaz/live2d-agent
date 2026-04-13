"""可拖动标题栏组件"""

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QColor


class TitleBar(QWidget):
    """自定义标题栏，支持拖动和双击展开/收起"""

    toggle_expand = Signal()  # 双击标题栏触发展开/收起
    close_clicked = Signal()  # 关闭按钮被点击
    mouse_pressed = Signal(QPoint)  # 鼠标按下信号
    mouse_moved = Signal(QPoint)  # 鼠标移动信号
    mouse_released = Signal()  # 鼠标释放信号

    def __init__(self, parent=None, title: str = "Agent Chat"):
        super().__init__(parent)
        self._title = title
        self._is_expanded = True
        self._drag_pos = None
        self._is_dragging = False

        self.setObjectName("titleBar")
        self.setFixedHeight(36)

        self.setup_ui()
        self.setup_shadow()

    def setup_ui(self):
        """初始化 UI 组件"""
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(12, 0, 12, 0)
        self.layout.setSpacing(8)

        # 图标
        self.icon_label = QLabel("🤖", self)
        self.icon_label.setFixedSize(22, 22)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.icon_label)

        # 标题
        self.title_label = QLabel(self._title, self)
        self.title_label.setObjectName("titleLabel")
        self.layout.addWidget(self.title_label)

        self.layout.addStretch()

        # 最小化按钮
        self.min_btn = QPushButton("−", self)
        self.min_btn.setObjectName("windowBtn")
        self.min_btn.setToolTip("最小化")
        self.min_btn.setFixedSize(26, 26)
        self.min_btn.clicked.connect(self.on_minimize)
        self.layout.addWidget(self.min_btn)

        # 关闭按钮
        self.close_btn = QPushButton("×", self)
        self.close_btn.setObjectName("closeBtn")
        self.close_btn.setToolTip("隐藏")
        self.close_btn.setFixedSize(26, 26)
        self.close_btn.clicked.connect(self.on_close)
        self.layout.addWidget(self.close_btn)

    def setup_shadow(self):
        """设置阴影效果"""
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(10)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

    def on_minimize(self):
        """最小化窗口"""
        window = self.window()
        if window:
            window.showMinimized()

    def on_close(self):
        """关闭按钮点击 - 发出信号让主程序退出"""
        self.close_clicked.emit()

    def mousePressEvent(self, event):
        """鼠标按下事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
            self._is_dragging = False
            self.mouse_pressed.emit(self._drag_pos)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """鼠标移动事件 - 拖动窗口"""
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            new_pos = event.globalPosition().toPoint()
            delta = new_pos - self._drag_pos

            # 如果移动距离超过阈值，认为是拖动
            if delta.manhattanLength() > 3:
                self._is_dragging = True
                self.mouse_moved.emit(new_pos)
                self._drag_pos = new_pos

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """鼠标释放事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.mouse_released.emit()
            self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """鼠标双击事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            # 检查是否点击在按钮区域之外
            pos = event.position().toPoint()
            if not self.min_btn.geometry().contains(
                pos
            ) and not self.close_btn.geometry().contains(pos):
                self.toggle_expand.emit()
        super().mouseDoubleClickEvent(event)

    def set_title(self, title: str):
        """设置标题"""
        self._title = title
        self.title_label.setText(title)

    def get_title(self) -> str:
        """获取标题"""
        return self._title
