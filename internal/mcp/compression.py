from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from internal.mcp.protocol import MCPMessage, MCPContextChunk

logger = logging.getLogger(__name__)


class CompressionStrategy(ABC):
    """压缩策略抽象基类

    定义压缩接口，不同策略实现不同压缩算法。
    """

    @abstractmethod
    async def compress(
        self,
        scope_id: str,
        messages: list[MCPMessage],
        target_tokens: int,
    ) -> MCPContextChunk:
        """压缩消息列表到目标token数

        Args:
            scope_id: 范围ID
            messages: 待压缩消息列表
            target_tokens: 目标token数

        Returns:
            压缩后的分片
        """
        ...

    def count_total_tokens(self, messages: list[MCPMessage]) -> int:
        """计算总token数"""
        return sum(m.tokens or 0 for m in messages)


class SlidingWindowCompression(CompressionStrategy):
    """滑动窗口压缩

    简单保留最新N条消息，丢弃旧消息。
    """

    def __init__(self, keep_last: int = 10) -> None:
        self.keep_last = keep_last

    async def compress(
        self,
        scope_id: str,
        messages: list[MCPMessage],
        target_tokens: int,
    ) -> MCPContextChunk:
        if len(messages) <= self.keep_last:
            return MCPContextChunk.create(
                scope_id=scope_id,
                messages=messages,
                compressed=False,
            )

        # 保留最新N条
        kept = messages[-self.keep_last :]
        discarded = messages[: -self.keep_last]

        # 创建摘要
        summary = f"保留最新{len(kept)}条消息，已压缩{len(discarded)}条旧消息。"

        chunk = MCPContextChunk.create(
            scope_id=scope_id,
            messages=kept,
            summary=summary,
            compressed=True,
        )
        logger.info(
            f"SlidingWindow compression: {len(messages)} -> {len(kept)} messages"
        )
        return chunk


class ExtractionCompression(CompressionStrategy):
    """关键信息抽取压缩

    保留用户提问和关键工具调用结果，压缩重复内容。
    """

    async def compress(
        self,
        scope_id: str,
        messages: list[MCPMessage],
        target_tokens: int,
    ) -> MCPContextChunk:
        # 保留所有用户消息和工具调用，合并助手回复
        kept: list[MCPMessage] = []
        merged_assistant = []

        for msg in messages:
            if msg.role in (msg.role.USER, msg.role.TOOL, msg.role.SYSTEM):
                # 如果有累积的助手回复，先合并
                if merged_assistant:
                    combined_text = "\n".join(m.content for m in merged_assistant)
                    kept.append(
                        MCPMessage.create(
                            role=msg.role.ASSISTANT,
                            content=f"[压缩合并] {combined_text}",
                            tokens=sum(m.tokens or 0 for m in merged_assistant),
                        )
                    )
                    merged_assistant = []
                kept.append(msg)
            elif msg.role == msg.role.ASSISTANT:
                merged_assistant.append(msg)

        # 处理剩余助手回复
        if merged_assistant and len(kept) < len(messages):
            combined_text = "\n".join(m.content for m in merged_assistant)
            kept.append(
                MCPMessage.create(
                    role=MCPMessage.role.ASSISTANT,
                    content=f"[压缩合并] {combined_text}",
                    tokens=sum(m.tokens or 0 for m in merged_assistant),
                )
            )

        summary = (
            f"抽取关键消息：保留了{len(kept)}条关键消息，"
            f"从{len(messages)}条原始消息压缩。"
        )

        chunk = MCPContextChunk.create(
            scope_id=scope_id,
            messages=kept,
            summary=summary,
            compressed=True,
        )
        logger.info(f"Extraction compression: {len(messages)} -> {len(kept)} messages")
        return chunk


class SummaryCompression(CompressionStrategy):
    """AI摘要压缩

    使用AI模型生成对话摘要，将多轮对话压缩为单个摘要。
    继承需要提供LLM调用。
    """

    def __init__(self, llm_model: Any | None = None) -> None:
        """
        Args:
            llm_model: 用于生成摘要的模型，如果None使用主模型
        """
        self.llm_model = llm_model

    async def compress(
        self,
        scope_id: str,
        messages: list[MCPMessage],
        target_tokens: int,
    ) -> MCPContextChunk:
        """该实现需要接入LLM，这里只定义接口框架

        实际LLM集成在MCPContextManager中完成，复用现有摘要逻辑。
        """
        # 保留最后一轮完整对话
        keep_last = min(3, len(messages))
        recent_messages = messages[-keep_last:] if keep_last > 0 else []
        older_messages = messages[:-keep_last] if keep_last > 0 else messages

        # 占位：实际应该调用LLM生成摘要
        total_msgs = len(older_messages)
        summary = (
            f"[摘要占位] 该段包含{total_msgs}条历史消息，"
            f"需要LLM生成摘要。当前实现保留最新{keep_last}条。"
        )

        chunk = MCPContextChunk.create(
            scope_id=scope_id,
            messages=recent_messages,
            summary=summary,
            compressed=True,
        )
        logger.info(
            f"Summary compression: {len(messages)} -> {len(recent_messages)} + summary"
        )
        return chunk


def create_compression_strategy(
    strategy_type: Any,
    llm_model: Any = None,
) -> CompressionStrategy:
    """工厂方法创建压缩策略"""
    from internal.mcp.protocol import CompressionStrategyType

    if isinstance(strategy_type, str):
        strategy_type = CompressionStrategyType(strategy_type)

    if strategy_type == CompressionStrategyType.SLIDING:
        return SlidingWindowCompression()
    elif strategy_type == CompressionStrategyType.EXTRACTION:
        return ExtractionCompression()
    elif strategy_type == CompressionStrategyType.SUMMARY:
        return SummaryCompression(llm_model)
    else:
        logger.warning(f"Unknown strategy {strategy_type}, fallback to sliding")
        return SlidingWindowCompression()
