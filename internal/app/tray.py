import logging
import time
from collections.abc import Callable
from importlib import import_module
from typing import Any


logger = logging.getLogger(__name__)


def setup_window_position(qt_app: Any, input_box: Any) -> None:
    """Set the initial window position."""
    if input_box is None:
        return
    qt_core = import_module("PySide6.QtCore")
    settings = qt_core.QSettings("Live2oder", "FloatingInputBox")
    pos = settings.value("position", None)
    if pos and isinstance(pos, qt_core.QPoint):
        input_box.move(pos)
        return
    screen = qt_app.primaryScreen().geometry()
    input_box.move(
        screen.width() - input_box.width() - 20,
        screen.height() - input_box.height() - 100,
    )


def create_tray_icon(
    *,
    qt_app: Any,
    input_box: Any,
    show_input_box: Callable[[], None],
    hide_input_box: Callable[[], None],
    open_settings: Callable[[], None],
    quit_app: Callable[[], None],
    on_activated: Callable[[Any], None],
) -> Any:
    """Create the system tray icon if the platform supports it."""
    qt_widgets = import_module("PySide6.QtWidgets")
    tray_cls = qt_widgets.QSystemTrayIcon
    logger.debug(
        "QSystemTrayIcon.isSystemTrayAvailable() = %s", tray_cls.isSystemTrayAvailable()
    )
    logger.debug("QSystemTrayIcon.supportsMessages() = %s", tray_cls.supportsMessages())
    if not tray_cls.isSystemTrayAvailable():
        logger.warning("系统托盘不可用，输入框将始终显示，可通过标题栏关闭按钮退出")
        if input_box is not None:
            input_box.show()
            input_box.raise_()
        return None

    tray_icon = tray_cls(qt_app)
    tray_icon.setToolTip("Live2oder Agent - 点击显示输入框")
    icon = _build_app_icon(qt_app)
    tray_icon.setIcon(icon)
    qt_app.setWindowIcon(icon)
    logger.debug(
        "托盘图标已设置: icon.isNull()=%s, sizes=%s",
        icon.isNull(),
        icon.availableSizes() if not icon.isNull() else "N/A",
    )

    menu = qt_widgets.QMenu()
    menu.addAction("显示输入框").triggered.connect(show_input_box)
    menu.addAction("隐藏输入框").triggered.connect(hide_input_box)
    menu.addSeparator()
    menu.addAction("设置").triggered.connect(open_settings)
    menu.addSeparator()
    menu.addAction("退出").triggered.connect(quit_app)
    tray_icon.setContextMenu(menu)
    tray_icon.activated.connect(on_activated)
    tray_icon.show()

    time.sleep(0.1)
    if tray_icon.isVisible():
        logger.info("系统托盘图标已成功显示")
        try:
            tray_icon.showMessage(
                "Live2oder Agent",
                "程序已在系统托盘运行，点击图标显示/隐藏输入框",
                tray_cls.MessageIcon.Information,
                5000,
            )
            logger.info("已显示托盘气泡通知")
        except Exception as exc:
            logger.warning("显示气泡通知失败: %s", exc)
    else:
        logger.warning("系统托盘图标未能显示，可能需要检查系统设置")
    return tray_icon


def is_trigger_activation(reason: Any) -> bool:
    tray_cls = import_module("PySide6.QtWidgets").QSystemTrayIcon
    return reason == tray_cls.ActivationReason.Trigger


def _build_app_icon(qt_app: Any) -> Any:
    qt_core = import_module("PySide6.QtCore")
    qt_gui = import_module("PySide6.QtGui")
    qt_widgets = import_module("PySide6.QtWidgets")
    pixmap = qt_gui.QPixmap(32, 32)
    pixmap.fill(qt_core.Qt.GlobalColor.transparent)

    painter = qt_gui.QPainter(pixmap)
    painter.setRenderHint(qt_gui.QPainter.RenderHint.Antialiasing)
    painter.setBrush(qt_gui.QBrush(qt_gui.QColor("#4a9eff")))
    painter.setPen(qt_core.Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, 28, 28, 6, 6)
    painter.setPen(qt_gui.QColor("#ffffff"))
    painter.setFont(qt_gui.QFont("Segoe UI", 14, qt_gui.QFont.Weight.Bold))
    painter.drawText(pixmap.rect(), qt_core.Qt.AlignmentFlag.AlignCenter, "L")
    painter.end()

    icon = qt_gui.QIcon(pixmap)
    if icon.isNull() or icon.availableSizes():
        logger.warning("创建的图标可能无效，尝试使用备用图标")
        icon = qt_app.style().standardIcon(qt_widgets.QStyle.StandardPixmap.SP_ComputerIcon)
    return icon
