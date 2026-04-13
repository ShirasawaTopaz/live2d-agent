"""单行滚动语音气泡 - 显示 AI 回复文字

特性:
- 无边框窗口，始终置顶
- 支持流式输出逐字显示（打字机效果）
- 单行文本，长文本自动水平滚动
- 显示一定时间后自动淡出消失
- 支持拖动定位，位置持久化
- 支持深色/浅色主题
- 完全透明背景，仅显示文字
- 文字渐变色和动画效果
"""

import math
import random
from typing import Optional

from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import (
    Qt,
    QPoint,
    QSettings,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    Property,
)
from PySide6.QtGui import QFont, QPainter, QColor, QPen, QLinearGradient, QBrush, QPainterPath, QFontMetrics
from PySide6.QtGui import QTextLayout
from PySide6.QtCore import QPointF


class BubbleWidget(QWidget):
    """单行滚动语音气泡"""

    # Gradient colors - theme-aware for better contrast
    GRADIENT_START_DARK: QColor = QColor("#5BB0FF")
    GRADIENT_END_DARK: QColor = QColor("#9D88FF")
    GRADIENT_START_LIGHT: QColor = QColor("#4A90E2")
    GRADIENT_END_LIGHT: QColor = QColor("#7B68EE")
    
    # Background colors - subtle semi-transparent for readability
    BACKGROUND_DARK: QColor = QColor(20, 20, 20, 60)
    BACKGROUND_LIGHT: QColor = QColor(245, 245, 245, 60)
    
    OUTLINE_COLOR: QColor = QColor(0, 0, 0, 200)
    OUTLINE_OFFSET: int = 2

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        # 状态管理
        self._content: str = ""
        self._drag_pos: Optional[QPoint] = None
        self._is_dragging: bool = False
        self._is_fading_out: bool = False  # 是否正在进行淡出动画

        # 流式打印核心状态
        self.full_text: str = ""
        self.displayed_text: str = ""
        self.char_index: int = 0
        self._scroll_x: float = 0.0
        self.cursor_visible: bool = True
        self._scroll_animation: Optional[QPropertyAnimation] = None

        # 打字机效果
        self._typewriter_timer = QTimer(self)
        self._typewriter_timer.setSingleShot(True)
        # 中文标点集合 - 需要更长停顿
        self._chinese_punctuation = set("，。！？、；：""''……—")

        # 文本布局
        self._max_width: int = 800
        self._max_height: int = 600  # 最大高度限制，防止占满整个屏幕
        self._padding: int = 12
        self._bottom_margin: int = 30  # 底部留白
        self._opacity: float = 1.0
        self._text_color = QColor(255, 255, 255)

        # 设置持久化
        self._settings = QSettings("Live2oder", "BubbleWidget")

        # 动画
        self._animation = QPropertyAnimation(self, b"windowOpacity")
        self._animation.setDuration(500)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.finished.connect(self._on_animation_finished)

        # 自动消失定时器 - 创建一次重复使用
        self._hide_timer = QTimer()
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.fade_out_and_hide)

        # 打字机定时器
        self._typewriter_timer.timeout.connect(self._on_typewriter_tick)

        # 光标闪烁定时器
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setInterval(500)
        self._cursor_timer.timeout.connect(self._toggle_cursor)
        self._cursor_timer.start()

        # 主题
        saved_theme = self._settings.value("theme", "dark")
        self._theme: str = str(saved_theme) if saved_theme is not None else "dark"

        # 初始化窗口
        self._setup_window_flags()
        self._setup_ui()

        # 加载位置
        self.load_position()
        self._update_colors()

        # 默认隐藏
        self.hide()

    def _setup_window_flags(self):
        """设置窗口标志"""
        flags = (
            Qt.WindowType.FramelessWindowHint  # 无边框
            | Qt.WindowType.WindowStaysOnTopHint  # 始终置顶
            | Qt.WindowType.Tool  # 工具窗口（不在任务栏显示）
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowOpacity(self._opacity)

    def _setup_ui(self):
        """初始化 UI 组件"""
        # 设置字体 - 现代系统字体栈，优先使用平台原生字体，然后 emoji 字体，然后 fallback 到通用无衬线
        font = QFont()
        font.setFamilies(["system-ui", "-apple-system", "Segoe UI", "Roboto", "Microsoft YaHei", "PingFang SC", "Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", "sans-serif"])
        font.setPointSize(24)
        font.setWeight(QFont.Weight.Normal)
        self.setFont(font)

        # 固定宽度，动态高度
        self._current_height: int = 120
        self.resize(self._max_width, self._current_height)
        self.setFixedWidth(self._max_width)

    def _update_colors(self):
        """更新主题颜色 - 完全透明背景"""
        if self._theme == "dark":
            self._text_color = QColor(255, 255, 255)
        else:
            self._text_color = QColor(51, 51, 51)

        self.update()

    def paintEvent(self, event):
        """自定义绘制 - 纯QPainter实现文字效果
        - 8方向描边发光效果
        - 当前行文字渐变填充
        - 闪烁光标
        - 水平滚动效果
        - 半透明背景提高可读性
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        if not self.displayed_text:
            painter.end()
            return

        # Draw subtle semi-transparent background
        if self._theme == "dark":
            painter.fillRect(self.rect(), self.BACKGROUND_DARK)
        else:
            painter.fillRect(self.rect(), self.BACKGROUND_LIGHT)

        font_metrics = QFontMetrics(self.font())
        font_metrics.height()
        offset = self.OUTLINE_OFFSET

        y = self._padding + font_metrics.ascent()
        x = self._padding

        clip_rect = self.rect().adjusted(self._padding, 0, -self._padding, 0)
        painter.setClipRect(clip_rect)

        painter.translate(self._scroll_x, 0)

        current_text = self.displayed_text
        if current_text:
            text_width = font_metrics.horizontalAdvance(current_text)
            if text_width > 0:
                gradient = QLinearGradient(x, y, x + text_width, y)
                if self._theme == "dark":
                    gradient.setColorAt(0, self.GRADIENT_START_DARK)
                    gradient.setColorAt(1, self.GRADIENT_END_DARK)
                else:
                    gradient.setColorAt(0, self.GRADIENT_START_LIGHT)
                    gradient.setColorAt(1, self.GRADIENT_END_LIGHT)
                gradient_brush = QBrush(gradient)
                
                # Use QTextLayout to get properly segmented glyph runs
                # This allows us to separate emoji from regular text
                layout = QTextLayout(current_text, self.font())
                layout.beginLayout()
                line = layout.createLine()
                layout.endLayout()
                
                # Get glyph runs and position them correctly
                pos = layout.position()
                line_offset = line.position()
                baseline_y = y
                
                # 8 directions for outline glow effect
                outline_offsets = [
                    (-offset, -offset), (-offset, 0), (-offset, offset),
                    (0, -offset),          (0, offset),
                    (offset, -offset),  (offset, 0), (offset, offset),
                ]
                
                # Process each glyph run - emoji and text get different rendering
                offset_x = x - pos.x() + line_offset.x()
                offset_y = baseline_y - pos.y()
                for glyph_run in line.glyphRuns():
                    # Get the glyph run with correct positioning - add offset to each glyph position
                    positions = [QPointF(p.x() + offset_x, p.y() + offset_y) for p in glyph_run.positions()]
                    glyph_run.setPositions(positions)

                    # Get the font used by this glyph run
                    raw_font = glyph_run.rawFont()
                    family = raw_font.familyName()
                    if not family:
                        family = self.font().family()

                    if self._is_emoji_font(family):
                        # Emoji font - draw natively to preserve colors (no outline needed)
                        painter.drawGlyphRun(QPointF(0, 0), glyph_run)
                    else:
                        # Regular text - first draw 8-direction outline glow
                        # Use drawGlyphRun directly for 8-direction outline effect
                        outline_pen = QPen(self.OUTLINE_COLOR)
                        outline_pen.setWidth(1)
                        painter.setPen(outline_pen)
                        painter.setBrush(Qt.BrushStyle.NoBrush)

                        for dx, dy in outline_offsets:
                            painter.save()
                            painter.translate(dx, dy)
                            painter.drawGlyphRun(QPointF(0, 0), glyph_run)
                            painter.restore()
                        
                        # Then draw gradient filled glyphs on top
                        # In Qt drawGlyphRun uses the pen (not brush) for glyph coloring
                        gradient_pen = QPen(gradient_brush, 0)
                        painter.setPen(gradient_pen)
                        painter.setBrush(Qt.BrushStyle.NoBrush)
                        painter.drawGlyphRun(QPointF(0, 0), glyph_run)

            if self.cursor_visible and self.isVisible():
                cursor_x = x + text_width
                cursor_y = y - font_metrics.ascent()
                cursor_height = font_metrics.height()
                if self._theme == "dark":
                    painter.setPen(QPen(self.GRADIENT_START_DARK, 2))
                else:
                    painter.setPen(QPen(self.GRADIENT_START_LIGHT, 2))
                painter.drawLine(cursor_x, cursor_y, cursor_x, cursor_y + cursor_height)

        painter.end()
        super().paintEvent(event)

    def clear(self):
        """清空内容"""
        # 停止任何正在进行的动画
        if self._animation.state() == QPropertyAnimation.State.Running:
            self._animation.stop()

        # 清除淡出标志，防止已停止的动画完成后隐藏新内容
        self._is_fading_out = False

        # 停止自动隐藏定时器
        if self._hide_timer.isActive():
            self._hide_timer.stop()

        # 停止打字机定时器
        if self._typewriter_timer.isActive():
            self._typewriter_timer.stop()

        # 停止任何正在进行的滚动动画
        if self._scroll_animation is not None and self._scroll_animation.state() == QPropertyAnimation.State.Running:
            self._scroll_animation.stop()

        # 光标定时器保持运行 - it just toggles visibility, no need to stop

        # 清空所有文本状态
        self._content = ""
        self.displayed_text = ""
        self.full_text = ""
        self.char_index = 0
        self._scroll_x = 0.0
        # 重置大小为最小高度
        self.adjust_size_to_content()
        self.update()

        self.setWindowOpacity(1.0)
        # 确保窗口保持显示状态
        self.show()

    def set_text(self, text: str):
        """直接设置完整文本内容（无打字机动画效果）
        Used by existing tool API compatibility
        """
        self.full_text = text
        self.char_index = len(text)
        self.displayed_text = text

        # Stop any running auto-hide timer while we're still updating content
        # The timer will be restarted by show_with_duration() after all chunks are complete
        if self._hide_timer.isActive():
            self._hide_timer.stop()

        # If fade-out is in progress, interrupt it and keep visible
        if self._is_fading_out:
            self._is_fading_out = False
            if self._animation.state() == QPropertyAnimation.State.Running:
                self._animation.stop()
            self.setWindowOpacity(1.0)
            self.show()

        self._scroll_x = 0.0
        # Stop any pending scroll animation when setting new text
        if self._scroll_animation is not None and self._scroll_animation.state() == QPropertyAnimation.State.Running:
            self._scroll_animation.stop()
        self.update_text_wrap()
        self.update()

    def show_with_duration(self, duration_ms: int = 15000):
        """显示并在指定毫秒后自动消失
        
        Args:
            duration_ms: 显示时长（毫秒），默认 15000ms (15秒)
        """
        # 计算基于文本长度的显示时间
        text_length = len(self.displayed_text)
        # 基础时间 15秒，每增加10个字符增加1秒，最多30秒
        dynamic_duration = 15000 + min(text_length * 100, 15000)
        
        # 使用传入的时长或动态计算的时长，取较大值
        final_duration = max(duration_ms, dynamic_duration)
        
        # 停止之前的动画和定时器
        if self._animation.state() == QPropertyAnimation.State.Running:
            self._animation.stop()

        # 清除淡出标志，防止已停止的动画完成后隐藏新内容
        self._is_fading_out = False

        # 如果已有隐藏定时器在运行，停止它
        if self._hide_timer.isActive():
            self._hide_timer.stop()

        # 强制重置状态，确保可见
        self.setWindowOpacity(1.0)
        self.show()
        # 提升到最上层确保可见
        self.raise_()
        self.activateWindow()
        # 强制处理UI事件，确保立即更新显示
        QApplication.processEvents()

        # 重新启动定时器
        self._hide_timer.start(final_duration)

    def fade_out_and_hide(self):
        """开始淡出动画并隐藏"""
        if not self.isVisible():
            return

        # 设置淡出标志，表示我们确实想要在动画完成后隐藏
        self._is_fading_out = True
        self._animation.setStartValue(self.windowOpacity())
        self._animation.setEndValue(0.0)
        self._animation.start()

    def _on_animation_finished(self):
        """动画完成后隐藏"""
        # 只有当我们确实正在进行淡出动画时才隐藏
        if not self._is_fading_out:
            return
        # 如果透明度已经被重置为 1.0，说明我们已经中断了淡出要显示新内容
        # 不要隐藏窗口，让新内容保持显示
        if self.windowOpacity() >= 1.0:
            return
        self.hide()
        self.setWindowOpacity(1.0)
        self._is_fading_out = False

    def set_theme(self, theme: str):
        """设置主题"""
        self._theme = theme
        self._settings.setValue("theme", theme)
        self._update_colors()

    def save_position(self):
        """保存当前位置到设置"""
        self._settings.setValue("position", self.pos())

    def load_position(self):
        """加载保存的位置，或者使用默认位置（屏幕底部居中）"""
        if self._settings.contains("position"):
            pos = self._settings.value("position")
            if isinstance(pos, QPoint):
                self.move(pos)
                return

        # 默认位置：屏幕底部居中
        screen_geo = QApplication.primaryScreen().geometry()
        # 先调整大小计算位置
        self.adjust_size_to_content()
        x = (screen_geo.width() - self.width()) // 2
        y = screen_geo.height() - self.height() - 150
        self.move(x, y)

    def mousePressEvent(self, event):
        """鼠标按下 - 开始拖动"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
            self._is_dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """鼠标移动 - 拖动窗口"""
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            new_pos = event.globalPosition().toPoint()
            delta = new_pos - self._drag_pos
            if delta.manhattanLength() > 3:
                self._is_dragging = True
                self.move(self.pos() + delta)
                self._drag_pos = new_pos
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """鼠标释放 - 结束拖动"""
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_dragging:
                self.save_position()
            self._drag_pos = None
        super().mouseReleaseEvent(event)

    def _on_typewriter_tick(self):
        """打字机定时器滴答 - 输出下一个字符"""
        # 检查是否已经输出完毕
        if self.char_index >= len(self.full_text):
            # 所有文本都已显示完成
            if self._typewriter_timer.isActive():
                self._typewriter_timer.stop()
            # 打字完成后启动自动隐藏定时器，根据文本长度设置合适的显示时间
            text_length = len(self.displayed_text)
            # 基础时间 15秒，每增加10个字符增加1秒，最多30秒
            duration = 15000 + min(text_length * 100, 15000)
            self._hide_timer.start(duration)
            return

        # 输出当前字符
        self.char_index += 1
        self.displayed_text = self.full_text[:self.char_index]

        # 更新显示并处理水平滚动
        self.update_text_wrap()
        self.update()

        # 如果还没输出完，安排下一次滴答
        if self.char_index < len(self.full_text):
            next_char = self.full_text[self.char_index]
            # 根据下一个字符是否是中文标点决定间隔
            if next_char in self._chinese_punctuation:
                # 中文标点使用更长的随机停顿 250-450ms
                interval = random.randint(250, 450)
            else:
                # 普通字符 30ms
                interval = 30
            self._typewriter_timer.start(interval)

    def start_typewriter(self, full_text: str):
        """开始打字机效果，从头逐字输出"""
        # 停止之前的定时器
        if self._typewriter_timer.isActive():
            self._typewriter_timer.stop()

        # Stop auto-hide timer during typewriter output - it will be started after completion
        if self._hide_timer.isActive():
            self._hide_timer.stop()

        # Interrupt any ongoing fade-out to keep visible during typing
        if self._is_fading_out:
            self._is_fading_out = False
            if self._animation.state() == QPropertyAnimation.State.Running:
                self._animation.stop()
            self.setWindowOpacity(1.0)
            self.show()

        # 直接使用完整文本，不进行拆分
        self.full_text = full_text
        self.char_index = 0
        self.displayed_text = ""
        self._scroll_x = 0

        # 启动定时器，第一个字符使用基础间隔
        self._typewriter_timer.start(30)

    def _calculate_scroll_duration(self, scroll_distance: float) -> int:
        char_count = len(self.displayed_text)
        # 降低基础速度，减慢滚动
        speed = 0.15 + 0.15 * math.log2(max(char_count, 1))
        duration = abs(scroll_distance) / speed
        # 延长25倍动画时间（5倍基础上再延长5倍）
        duration *= 25
        # 增加最小时长，确保滚动更平滑
        return int(max(2500, min(duration, 20000)))

    def update_text_wrap(self):
        """更新文本显示 - 保持单行并添加水平滚动效果"""
        font_metrics = QFontMetrics(self.font())
        available_width = self.width() - 2 * self._padding
        
        current_text = self.displayed_text
        text_width = font_metrics.horizontalAdvance(current_text)
        
        if text_width > available_width:
            cursor_x = self._padding + text_width
            if cursor_x > self.width() - self._padding:
                target_scroll_x = -(cursor_x - self.width() + self._padding)
                
                # 先不滚动，让用户可以看见前面几个字符，3秒后再开始滚动
                self._scroll_animation = QPropertyAnimation(self, b"scroll_x")
                scroll_distance = target_scroll_x - self._scroll_x
                # 计算总动画时长
                animation_duration = self._calculate_scroll_duration(scroll_distance)
                self._scroll_animation.setDuration(animation_duration)
                self._scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
                self._scroll_animation.setStartValue(self._scroll_x)
                self._scroll_animation.setEndValue(target_scroll_x)
                
                # 3秒延时后再启动滚动动画
                QTimer.singleShot(3000, self._scroll_animation.start)
        else:
            if self._scroll_x != 0:
                self._scroll_x = 0
                # Stop any pending scroll animation if text is now short enough
                if self._scroll_animation is not None and self._scroll_animation.state() == QPropertyAnimation.State.Running:
                    self._scroll_animation.stop()
                self.update()

        self.adjust_size_to_content()

    def adjust_size_to_content(self):
        """保持固定高度用于单行显示"""
        # 固定高度为单行显示
        font_metrics = QFontMetrics(self.font())
        line_height = font_metrics.height()
        new_height = line_height + 2 * self._padding + self._bottom_margin
        # 最小高度为120px
        new_height = max(new_height, 120)
        
        # 如果高度发生变化，更新固定高度
        if new_height != self._current_height:
            self._current_height = new_height
            self.setFixedHeight(self._current_height)
            # 位置保持不变，用户可以拖动重新定位
            self.update()

    def _is_emoji_font(self, family_name: str) -> bool:
        """Check if this font family is an emoji font"""
        # Common emoji font family names across platforms
        emoji_font_names = {
            'segoe ui emoji', 'segoe ui symbol',
            'apple color emoji',
            'noto color emoji', 'notoemoji',
            'twemoji',
            'emoji one',
            'color emoji',
            'emoji'
        }
        return any(ef in family_name.lower() for ef in emoji_font_names)

    def _toggle_cursor(self):
        """切换光标可见性实现闪烁效果"""
        self.cursor_visible = not self.cursor_visible
        self.update()

    # Qt Property for scroll_x animation
    @Property(float)
    def scroll_x(self) -> float:
        """Get current scroll X offset"""
        return self._scroll_x

    @scroll_x.setter
    def scroll_x(self, value: float):
        """Set current scroll X offset and trigger repaint"""
        self._scroll_x = value
        self.update()