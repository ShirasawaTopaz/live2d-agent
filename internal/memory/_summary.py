"""
Conversation Summarizer - Reference Implementation
⚠️  This is reference design code, not yet production-ready

Supports both full reconstruction and iterative summarization modes.
"""

import logging
from typing import List, Tuple, Optional
from datetime import datetime

from internal.memory._types import ConversationTurn, SummaryEntry, Message


logger = logging.getLogger(__name__)


SUMMARY_PROMPT = """请你总结以下这段对话，保留所有关键信息：
用户偏好、重要事实、约定事项、未完成的任务等都需要保留。
总结要简洁明了，不超过200字。

对话内容:
{dialogue}

请直接输出总结："""

ITERATIVE_SUMMARY_PROMPT = """以下是对之前对话的已有摘要：
{existing_summary}

现在需要将新的一段对话追加到摘要中。新对话内容：
{new_dialogue}

请更新摘要，保留之前的重要信息，同时添加新对话的关键内容。
总结要简洁明了，不超过200字。

请直接输出更新后的摘要："""


class Summarizer:
    """对话摘要生成器
    当对话过长时，调用LLM生成摘要，压缩上下文窗口

    Supports two modes:
    - Full reconstruction: summarize all old messages from scratch
    - Iterative: extend existing summary with only new messages
    """

    def __init__(
        self,
        model_name: str = "default",
        max_summary_tokens: int = 300,
        iterative_mode: bool = True,
    ):
        self.model_name = model_name
        self.max_summary_tokens = max_summary_tokens
        self.iterative_mode = iterative_mode

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

    def build_iterative_summary_prompt(
        self,
        existing_summary: str,
        new_dialogue: str,
    ) -> str:
        """Build prompt for iterative summarization"""
        return ITERATIVE_SUMMARY_PROMPT.format(
            existing_summary=existing_summary,
            new_dialogue=new_dialogue,
        )

    def get_existing_summary(self, turns: List[ConversationTurn]) -> Optional[str]:
        """Extract existing summary from compressed conversation"""
        for turn in turns:
            role = turn.message.get("role", "")
            content = turn.message.get("content", "")
            if role == "system" and "摘要" in content:
                match = content.split("以下是之前对话的摘要：")[-1].strip()
                if match:
                    return match
        return None

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
        summary_entry = SummaryEntry(
            content=summary_text,
            original_start_idx=start_idx,
            original_end_idx=end_idx,
            timestamp=turns[-1].timestamp,
        )

        new_turns: List[ConversationTurn] = []

        for i, turn in enumerate(turns):
            role = turn.message.get("role", "")
            if role == "system":
                new_turns.append(turn)
            else:
                break

        summary_message: Message = {
            "role": "system",
            "content": f"以下是之前对话的摘要：\n{summary_text}",
        }
        new_turns.append(ConversationTurn(message=summary_message))

        new_turns.extend(turns[end_idx + 1:])

        logger.info(
            f"Compressed {end_idx - start_idx + 1} messages into summary "
            f"({len(summary_text)} chars)"
        )

        return new_turns, summary_entry

    def compress_with_iterative(
        self,
        turns: List[ConversationTurn],
        new_summary_text: str,
        start_idx: int,
        end_idx: int,
    ) -> Tuple[List[ConversationTurn], SummaryEntry]:
        """Iterative compression - extends existing summary instead of replacing

        If there's an existing summary, extract it and merge with new summary.
        Otherwise fall back to standard compression.
        """
        existing_summary = self.get_existing_summary(turns)

        if existing_summary and self.iterative_mode:
            combined_summary = f"{existing_summary}\n\n---新增---\n{new_summary_text}"
            logger.debug(f"Extending existing summary with {len(new_summary_text)} chars of new content")
        else:
            combined_summary = new_summary_text

        return self.compress_old_messages(turns, combined_summary, start_idx, end_idx)
