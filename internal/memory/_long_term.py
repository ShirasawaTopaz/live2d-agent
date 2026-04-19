"""
Long-Term Memory Storage - Reference Implementation
⚠️  This is reference design code, not yet production-ready
Vector embedding support is reserved for future extension
"""

import uuid
import logging
from datetime import datetime
from typing import List

from internal.memory._small_model_profile import SmallModelMemoryProfile
from internal.memory._types import LongTermEntry, Message
from internal.memory.storage._base import BaseStorage


logger = logging.getLogger(__name__)


EXTRACT_PROMPT = """请从对话中提取需要长期记住的关键信息，包括：
1. 用户的偏好和喜好
2. 重要事实信息（生日、地址、日程等）
3. 约定和待办事项
4. 需要记住的任何重要信息

请以JSON数组格式输出，每个条目包含：
- content: 具体内容
- keywords: 关键词列表（用于检索）

示例输出:
[
  {
    "content": "用户喜欢喝咖啡，不加糖",
    "keywords": ["咖啡", "喜好", "饮料"]
  }
]

对话内容:
{dialogue}

提取结果："""


class LongTermMemory:
    """长期记忆存储
    提取对话中的关键信息进行长期存储，支持检索相关记忆
    向量嵌入支持留作未来扩展
    """

    def __init__(
        self,
        storage: BaseStorage,
        enabled: bool = True,
        profile: SmallModelMemoryProfile | None = None,
    ):
        self.storage = storage
        self.enabled = enabled
        self.profile = profile

    async def extract_and_store(
        self,
        messages: List[Message],
        session_id: str,
    ) -> List[LongTermEntry]:
        """从对话中提取关键信息并存储"""
        if not self.enabled:
            return []

        # TODO: 未来让LLM自动提取关键信息
        # 当前简化实现：用户消息如果超过一定长度，直接存储作为长期记忆
        # 完整的LLM提取留作未来扩展

        entries: List[LongTermEntry] = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user" and len(content) > 50:
                # 简化：提取前几个词作为关键词
                words = content.split()[:5]
                keywords = [word.strip("，。！？") for word in words]
                entry = LongTermEntry(
                    id=str(uuid.uuid4())[:12],
                    content=content,
                    keywords=keywords,
                    source_session_id=session_id,
                    created_at=datetime.now(),
                )
                await self.storage.save_long_term(entry)
                entries.append(entry)

        logger.info(f"Extracted and stored {len(entries)} long term entries")
        return entries

    async def query_relevant(
        self,
        query: str,
        limit: int = 5,
    ) -> List[LongTermEntry]:
        """查询与当前查询相关的长期记忆"""
        if not self.enabled:
            return []
        return await self.storage.query_long_term(query, limit)

    def build_injection_prompt(self, entries: List[LongTermEntry]) -> str:
        """构建注入到system prompt的提示文本"""
        if not entries:
            return ""

        if self.profile is not None and self.profile.enabled:
            return self._build_compact_injection_prompt(entries)

        lines = ["\n\n## 相关历史记忆：\n"]
        for i, entry in enumerate(entries, 1):
            lines.append(f"{i}. {entry.content}")
        return "\n".join(lines)

    def _build_compact_injection_prompt(self, entries: List[LongTermEntry]) -> str:
        max_entries = 3
        max_entry_chars = 72
        total_cap = 240
        rendered_entries: list[str] = []

        for entry in entries[:max_entries]:
            compact_content = self._compact_text(entry.content, max_entry_chars)
            rendered_entries.append(f"- {compact_content}")

        prompt = "\n\n## 记忆\n" + "\n".join(rendered_entries)
        if len(prompt) > total_cap:
            prompt = prompt[: total_cap - 1].rstrip() + "…"
        return prompt

    @staticmethod
    def _compact_text(text: str, max_chars: int) -> str:
        normalized = " ".join(text.split())
        if len(normalized) <= max_chars:
            return normalized
        return normalized[: max_chars - 1].rstrip() + "…"

    async def delete_entry(self, entry_id: str) -> bool:
        """删除长期记忆条目"""
        return await self.storage.delete_long_term(entry_id)
