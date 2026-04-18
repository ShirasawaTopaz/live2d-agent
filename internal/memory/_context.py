"""
Context Window Manager - Reference Implementation
⚠️  This is reference design code, not yet production-ready
"""

import logging
from typing import List, Tuple

from internal.memory._types import ConversationTurn, Message
from internal.memory._session import SessionManager


logger = logging.getLogger(__name__)


class ContextManager:
    """上下文窗口管理器
    监控对话长度，当超过阈值时触发压缩，避免超出LLM上下文窗口
    """

    def __init__(
        self,
        max_messages: int = 20,
        max_tokens: int = 4096,
        compression_threshold: int = 15,
        preserve_recent_count: int = 5,
        token_trigger_ratio: float = 0.7,
    ):
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self.compression_threshold = compression_threshold
        self.preserve_recent_count = preserve_recent_count
        self.token_trigger_ratio = token_trigger_ratio

    def should_compress(self, session_manager: SessionManager) -> bool:
        """检查是否需要压缩（基于消息数和token数）"""
        message_count = session_manager.message_count()
        estimated_tokens = session_manager.estimate_total_tokens()
        token_limit = int(self.max_tokens * self.token_trigger_ratio)

        if message_count > self.compression_threshold:
            logger.debug(
                f"Should compress: message_count={message_count} > threshold={self.compression_threshold}"
            )
            return True

        if estimated_tokens > token_limit:
            logger.debug(
                f"Should compress: estimated_tokens={estimated_tokens} > {token_limit} (70% of {self.max_tokens})"
            )
            return True

        return False

    def truncate(
        self,
        turns: List[ConversationTurn],
        keep_last: int,
    ) -> Tuple[List[ConversationTurn], int, int]:
        """截断：保留system prompt + 最后N条消息 + 最近5条不压缩
        返回: (新的轮次列表, 起始索引, 结束索引)
        """
        first_user_idx = 0
        for i, turn in enumerate(turns):
            role = turn.message.get("role", "")
            if role != "system":
                first_user_idx = i
                break

        total_user_messages = len(turns) - first_user_idx
        preserve_count = min(self.preserve_recent_count, total_user_messages)
        compress_count = total_user_messages - preserve_count

        keep_start = max(first_user_idx, len(turns) - preserve_count)

        if keep_start > first_user_idx:
            new_turns = turns[:first_user_idx] + turns[keep_start:]
            logger.debug(
                f"Truncate: preserving {preserve_count} recent messages, "
                f"compressing {keep_start - first_user_idx} old messages"
            )
            return new_turns, first_user_idx, keep_start - 1
        else:
            return turns, 0, 0

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """粗略估算token数量，按照1token ≈ 4字符估算"""
        return len(text) // 4

    @staticmethod
    def estimate_message_tokens(message: Message) -> int:
        """估算单条消息token数"""
        content = message.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        return ContextManager.estimate_tokens(content)

    def estimate_total_tokens(self, messages: List[Message]) -> int:
        """估算总token数"""
        total = 0
        for msg in messages:
            total += self.estimate_message_tokens(msg)
        return total

    def exceeds_token_limit(self, messages: List[Message]) -> bool:
        """检查是否超过token限制"""
        estimated = self.estimate_total_tokens(messages)
        return estimated > self.max_tokens
