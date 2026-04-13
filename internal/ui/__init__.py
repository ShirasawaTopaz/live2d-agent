"""UI 模块 - PySide6 悬浮输入框"""

from .input_box import FloatingInputBox
from .styles import get_styles, STYLES
from .title_bar import TitleBar
from .history_manager import InputHistory
from .bubble_widget import BubbleWidget

__all__ = [
    "FloatingInputBox",
    "get_styles",
    "STYLES",
    "TitleBar",
    "InputHistory",
    "BubbleWidget",
]
