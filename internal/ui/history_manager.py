"""输入历史管理模块"""

from collections import deque
from typing import Optional, List


class InputHistory:
    """管理用户输入历史"""

    def __init__(self, max_size: int = 50):
        self._history: deque[str] = deque(maxlen=max_size)
        self._index: int = -1
        self._current_input: str = ""
        self._max_size = max_size

    def add(self, text: str) -> None:
        """添加新条目到历史

        Args:
            text: 要添加的文本
        """
        if text and (not self._history or self._history[-1] != text):
            self._history.append(text)
        self._index = -1
        self._current_input = ""

    def get_previous(self, current_text: str = "") -> Optional[str]:
        """获取上一条历史

        Args:
            current_text: 当前输入框的文本（首次获取时保存）

        Returns:
            上一条历史记录，如果没有则返回 None
        """
        if self._index == -1:
            self._current_input = current_text

        if not self._history:
            return None

        self._index = min(self._index + 1, len(self._history) - 1)
        return self._history[-(self._index + 1)]

    def get_next(self) -> Optional[str]:
        """获取下一条历史

        Returns:
            下一条历史记录，如果已经是最新则返回当前输入
        """
        if self._index <= 0:
            self._index = -1
            return self._current_input

        self._index -= 1
        return (
            self._history[-(self._index + 1)]
            if self._index >= 0
            else self._current_input
        )

    def clear(self) -> None:
        """清空历史"""
        self._history.clear()
        self._index = -1
        self._current_input = ""

    def get_all(self) -> List[str]:
        """获取所有历史记录（从旧到新）"""
        return list(self._history)

    def set_max_size(self, max_size: int) -> None:
        """设置最大历史记录数

        Args:
            max_size: 新的最大值
        """
        self._max_size = max_size
        # 重新创建 deque 以应用新的 maxlen
        self._history = deque(self._history, maxlen=max_size)
