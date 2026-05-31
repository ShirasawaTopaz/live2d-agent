import random
from collections.abc import Callable
from typing import Optional

from PySide6.QtWidgets import QWidget, QApplication, QTextBrowser
from PySide6.QtCore import (
    Qt,
    QPoint,
    QSettings,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
)
from PySide6.QtGui import QFont

from internal.ui.markdown_renderer import MarkdownRenderer


class BubbleWidget(QWidget):

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._drag_pos: Optional[QPoint] = None
        self._is_dragging: bool = False
        self._is_fading_out: bool = False

        self.full_text: str = ""
        self.displayed_text: str = ""
        self.char_index: int = 0
        self._display_duration_ms: int = 15000

        self._typewriter_timer = QTimer(self)
        self._typewriter_timer.setSingleShot(True)
        self._chinese_punctuation = set("，。！？、；：""''……—")

        self._max_width: int = 800
        self._padding: int = 12
        self._opacity: float = 1.0

        self._settings = QSettings("Live2oder", "BubbleWidget")

        self._animation = QPropertyAnimation(self, b"windowOpacity")
        self._animation.setDuration(500)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.finished.connect(self._on_animation_finished)

        self._hide_timer = QTimer()
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.fade_out_and_hide)

        self._typewriter_timer.timeout.connect(self._on_typewriter_tick)

        saved_theme = self._settings.value("theme", "dark")
        self._theme: str = str(saved_theme) if saved_theme is not None else "dark"

        self._setup_window_flags()
        self._setup_ui()

        self.load_position()
        self._apply_browser_theme()

        self.hide()

    def _setup_window_flags(self):
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowOpacity(self._opacity)

    def _setup_ui(self):
        font = QFont()
        font.setFamilies(["system-ui", "-apple-system", "Segoe UI", "Roboto", "Microsoft YaHei", "PingFang SC", "Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", "sans-serif"])
        font.setPointSize(24)
        font.setWeight(QFont.Weight.Normal)
        self.setFont(font)

        self._current_height: int = 120
        self.resize(self._max_width, self._current_height)
        self.setFixedWidth(self._max_width)

        self._markdown_renderer = MarkdownRenderer()
        self._browser = QTextBrowser(self)
        self._browser.setOpenExternalLinks(False)
        self._browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._browser.setFrameShape(QTextBrowser.Shape.NoFrame)
        self._apply_browser_theme()
        self._browser.setGeometry(self._padding, 5, self._max_width - 2 * self._padding, self._current_height - 10)

    def _apply_browser_theme(self):
        if self._theme == "dark":
            self._browser.setStyleSheet("""
                QTextBrowser { background: transparent; color: #ddd; font-size: 24px; }
                QTextBrowser pre { background: #2d2d2d; color: #ccc; padding: 8px; border-radius: 4px; }
                QTextBrowser code { background: #3d3d3d; color: #e6db74; padding: 1px 4px; border-radius: 3px; }
            """)
        else:
            self._browser.setStyleSheet("""
                QTextBrowser { background: transparent; color: #333; font-size: 24px; }
                QTextBrowser pre { background: #f5f5f5; color: #333; padding: 8px; border-radius: 4px; }
                QTextBrowser code { background: #eee; color: #c7254e; padding: 1px 4px; border-radius: 3px; }
            """)

    def paintEvent(self, event):
        pass

    def clear(self):
        if self._animation.state() == QPropertyAnimation.State.Running:
            self._animation.stop()

        self._is_fading_out = False

        if self._hide_timer.isActive():
            self._hide_timer.stop()

        if self._typewriter_timer.isActive():
            self._typewriter_timer.stop()

        self.displayed_text = ""
        self.full_text = ""
        self.char_index = 0
        self._browser.clear()
        self.setWindowOpacity(1.0)
        self.show()

    def set_text(self, text: str):
        self.full_text = text
        self.char_index = len(text)
        self.displayed_text = text

        if self._hide_timer.isActive():
            self._hide_timer.stop()

        if self._is_fading_out:
            self._is_fading_out = False
            if self._animation.state() == QPropertyAnimation.State.Running:
                self._animation.stop()
            self.setWindowOpacity(1.0)
            self.show()

        html = self._markdown_renderer.to_html(text)
        self._browser.setHtml(html)
        self._browser.show()

        self.update()

    def show_with_duration(self, duration_ms: int = 15000):
        final_duration = max(1, duration_ms)
        self._display_duration_ms = final_duration

        if self._animation.state() == QPropertyAnimation.State.Running:
            self._animation.stop()

        self._is_fading_out = False

        if self._hide_timer.isActive():
            self._hide_timer.stop()

        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self.activateWindow()
        QApplication.processEvents()

        self._hide_timer.start(final_duration)

    def sync_scroll_to_audio(
        self,
        position_provider: Callable[[], int | None],
        duration_provider: Callable[[], int | None] | None = None,
        *,
        duration_ms: int | None = None,
    ) -> None:
        pass

    def clear_audio_scroll_sync(self) -> None:
        pass

    def fade_out_and_hide(self):
        if not self.isVisible():
            return

        self._is_fading_out = True
        self._animation.setStartValue(self.windowOpacity())
        self._animation.setEndValue(0.0)
        self._animation.start()

    def _on_animation_finished(self):
        if not self._is_fading_out:
            return
        if self.windowOpacity() >= 1.0:
            return
        self.hide()
        self.setWindowOpacity(1.0)
        self._is_fading_out = False

    def set_theme(self, theme: str):
        self._theme = theme
        self._settings.setValue("theme", theme)
        self._apply_browser_theme()

    def save_position(self):
        self._settings.setValue("position", self.pos())

    def load_position(self):
        if self._settings.contains("position"):
            pos = self._settings.value("position")
            if isinstance(pos, QPoint):
                self.move(pos)
                return

        screen_geo = QApplication.primaryScreen().geometry()
        x = (screen_geo.width() - self.width()) // 2
        y = screen_geo.height() - self.height() - 150
        self.move(x, y)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
            self._is_dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            new_pos = event.globalPosition().toPoint()
            delta = new_pos - self._drag_pos
            if delta.manhattanLength() > 3:
                self._is_dragging = True
                self.move(self.pos() + delta)
                self._drag_pos = new_pos
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_dragging:
                self.save_position()
            self._drag_pos = None
        super().mouseReleaseEvent(event)

    def _on_typewriter_tick(self):
        if self.char_index >= len(self.full_text):
            if self._typewriter_timer.isActive():
                self._typewriter_timer.stop()
            text_length = len(self.displayed_text)
            duration = 15000 + min(text_length * 500, 45000)
            self._hide_timer.start(duration)
            return

        self.char_index += 1
        self.displayed_text = self.full_text[:self.char_index]

        html = self._markdown_renderer.to_html(self.displayed_text)
        self._browser.setHtml(html)
        self.update()

        if self.char_index < len(self.full_text):
            next_char = self.full_text[self.char_index]
            if next_char in self._chinese_punctuation:
                interval = random.randint(250, 450)
            else:
                interval = 30
            self._typewriter_timer.start(interval)

    def start_typewriter(self, full_text: str):
        if self._typewriter_timer.isActive():
            self._typewriter_timer.stop()

        if self._hide_timer.isActive():
            self._hide_timer.stop()

        if self._is_fading_out:
            self._is_fading_out = False
            if self._animation.state() == QPropertyAnimation.State.Running:
                self._animation.stop()
            self.setWindowOpacity(1.0)
            self.show()

        self.full_text = full_text
        self.char_index = 0
        self.displayed_text = ""
        self._browser.clear()
        self._browser.show()
        self._typewriter_timer.start(30)

    def update_text_wrap(self):
        pass

    def adjust_size_to_content(self):
        self.setFixedHeight(120)
