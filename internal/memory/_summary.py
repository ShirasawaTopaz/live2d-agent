"""
Conversation Summarizer - Reference Implementation
⚠️  This is reference design code, not yet production-ready
"""

import logging
from typing import List, Tuple

from internal.memory._types import ConversationTurn, SummaryEntry, Message


logger = logging.getLogger(__name__)


SUMMARY_PROMPT = """请你总结以下这段对话，保留所有关键信息：
用户偏好、重要事实、约定事项、未完成的任务等都需要保留。
总结要简洁明了，不超过200字。

对话内容:
{dialogue}

请直接输出总结："""


class Summarizer:
    """对话摘要生成器
    当对话过长时，调用LLM生成摘要，压缩上下文窗口
    """

    def __init__(
        self,
        model_name: str = "default",
        max_summary_tokens: int = 300,
    ):
        self.model_name = model_name
        self.max_summary_tokens = max_summary_tokens

    def build_summary_prompt(
        self,
        turns: List[ConversationTurn],
        start_idx: int,
        end_idx: int,
    ) -> str:
        """构建摘要提示词"""
        dialogue = []
        for i in range(start_idx, end_idx + 1):
            turn = turns[i]
            role = turn.message.get("role", "unknown")
            content = turn.message.get("content", "")
            dialogue.append(f"[{role}]: {content}")

        dialogue_text = "\n".join(dialogue)
        return SUMMARY_PROMPT.format(dialogue=dialogue_text)

    def compress_old_messages(
        self,
        turns: List[ConversationTurn],
        summary_text: str,
        start_idx: int,
        end_idx: int,
    ) -> Tuple[List[ConversationTurn], SummaryEntry]:
        """将旧消息替换为摘要
        保留system prompt，将旧消息替换为一条摘要消息
        保留最新消息不变
        """
        # 创建摘要记录
        summary_entry = SummaryEntry(
            content=summary_text,
            original_start_idx=start_idx,
            original_end_idx=end_idx,
            timestamp=turns[-1].timestamp,
        )

        # 构建新的消息列表
        # 保留所有system提示词在开头
        new_turns: List[ConversationTurn] = []

        for i, turn in enumerate(turns):
            role = turn.message.get("role", "")
            if role == "system":
                new_turns.append(turn)
            else:
                break

        # 添加摘要消息
        summary_message: Message = {
            "role": "system",
            "content": f"以下是之前对话的摘要：\n{summary_text}",
        }
        new_turns.append(ConversationTurn(message=summary_message))

        # 添加剩余的最新消息
        new_turns.extend(turns[end_idx + 1 :])

        logger.info(
            f"Compressed {end_idx - start_idx + 1} messages into summary "
            f"({len(summary_text)} chars)"
        )

        return new_turns, summary_entry
