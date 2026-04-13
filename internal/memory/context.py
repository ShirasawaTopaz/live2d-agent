import logging
from typing import List

from internal.memory.types import Message

logger = logging.getLogger(__name__)


class ContextManager:
    """上下文窗口管理器
    监控对话长度，当超过阈值时触发压缩，避免超出LLM上下文窗口
    """

    def __init__(self, max_tokens: int, compression_threshold: int):
        self.max_tokens = max_tokens
        self.current_tokens = 0
        self.history = []
        self.compression_threshold = compression_threshold  # 压缩阈值

    def should_compress(self) -> bool:
        """检查是否需要压缩"""
        return self.current_tokens > self.max_tokens - self.compression_threshold

    def estimate_total_tokens(self, messages: List[Message]) -> int:
        """估算消息总令牌数"""
        # TODO: 实现令牌数估算
        return 0
