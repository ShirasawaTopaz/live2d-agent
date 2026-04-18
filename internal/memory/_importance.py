"""
Message Importance Scorer - Phase 2 Enhancement
Scores messages by importance to prioritize retention during compression
"""

import re
import logging
from typing import List
from enum import IntEnum

from internal.memory._types import Message


logger = logging.getLogger(__name__)


class MessagePriority(IntEnum):
    """Message priority levels for compression decisions"""
    CRITICAL = 4   # Never compress: user preferences, decisions, tool results
    HIGH = 3       # Compress last: important facts, topic changes
    MEDIUM = 2     # Compress after high priority
    LOW = 1        # Compress first: acknowledgments, pleasantries
    MINIMAL = 0    # Can be dropped entirely


class ImportanceScorer:
    """Message importance scorer for smart compression"""

    PREFERENCE_PATTERNS = [
        r"(?:我|我的|我喜欢|我不喜欢|我希望|我想要|偏好|喜欢|讨厌|想要)",
        r"(?:always|never|prefer|like|dislike|hate|want|need|wish)",
    ]

    DECISION_PATTERNS = [
        r"(?:决定|确定|就|好了|开始|执行|完成|好了|没问题|可以)",
        r"(?:decided|decided|let's|go ahead|proceed|start|finish|done|ok|okay)",
    ]

    TOOL_RESULT_PATTERNS = [
        r"role.*tool",
        r"tool_calls",
        r"tool_call_id",
    ]

    TOPIC_CHANGE_PATTERNS = [
        r"^对了|^(?:那|那么)么|顺便|还有个|另外|还有",
        r"^by the way|also|another thing|one more",
    ]

    ACKNOWLEDGMENT_PATTERNS = [
        r"^好[的]?$|^嗯$|^啊$|^哦$|^ok$|^okay$|^好的",
        r"^ok$|^yeah$|^yes$|^yep$|^sure$|^got it$",
    ]

    def __init__(self):
        self._pref_re = re.compile("|".join(self.PREFERENCE_PATTERNS), re.IGNORECASE)
        self._decision_re = re.compile("|".join(self.DECISION_PATTERNS), re.IGNORECASE)
        self._tool_re = re.compile("|".join(self.TOOL_RESULT_PATTERNS), re.IGNORECASE)
        self._topic_re = re.compile("|".join(self.TOPIC_CHANGE_PATTERNS), re.IGNORECASE)
        self._ack_re = re.compile("|".join(self.ACKNOWLEDGMENT_PATTERNS), re.IGNORECASE)

    def score_message(self, message: Message) -> MessagePriority:
        """Score a single message by importance"""
        role = message.get("role", "")
        content = message.get("content", "")

        if not isinstance(content, str):
            content = str(content)

        content_lower = content.lower()
        content_len = len(content)

        if role == "system":
            return MessagePriority.CRITICAL

        if role == "tool" or "tool_calls" in message:
            return MessagePriority.CRITICAL

        if self._tool_re.search(str(message)):
            return MessagePriority.CRITICAL

        if self._pref_re.search(content_lower):
            logger.debug(f"Matched preference pattern: {content[:50]}...")
            return MessagePriority.CRITICAL

        if self._decision_re.search(content_lower):
            return MessagePriority.HIGH

        if content_len > 500:
            return MessagePriority.HIGH

        if self._topic_re.match(content):
            return MessagePriority.HIGH

        if self._ack_re.match(content) and content_len < 20:
            return MessagePriority.LOW

        if content_len < 30:
            return MessagePriority.MEDIUM

        return MessagePriority.MEDIUM

    def sort_by_priority(self, messages: List[Message]) -> List[Message]:
        """Sort messages by priority (low to high) for compression decisions"""
        scored = [(self.score_message(msg), msg) for msg in messages]
        scored.sort(key=lambda x: x[0])
        return [msg for _, msg in scored]

    def get_compression_order(self, messages: List[Message]) -> List[int]:
        """Get message indices in order they should be compressed"""
        scored = [
            (i, self.score_message(msg), len(msg.get("content", "")))
            for i, msg in enumerate(messages)
        ]
        scored.sort(key=lambda x: (x[1], -x[2]))
        return [i for i, _, _ in scored]