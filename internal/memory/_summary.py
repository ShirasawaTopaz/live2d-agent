"""
Conversation Summarizer - Reference Implementation
⚠️  This is reference design code, not yet production-ready

Supports both full reconstruction and iterative summarization modes.
"""

import logging
from datetime import datetime
from typing import Optional, List, Tuple

from internal.memory._small_model_profile import SmallModelMemoryProfile
from internal.memory._types import ConversationTurn, SummaryEntry, Message


logger = logging.getLogger(__name__)


SUMMARY_PROMPT = """请你总结以下这段对话，保留所有关键信息：
用户偏好、重要事实、约定事项、未完成的任务等都需要保留。
总结要简洁明了，不超过200字。

对话内容:
{dialogue}

请直接输出总结："""

STRUCTURED_SUMMARY_PROMPT = """请你将以下对话压缩成稳定、可迭代更新的结构化摘要。

必须遵守：
1. 只保留高价值、之后仍会用到的信息。
2. 使用下面固定章节，缺失时写“无”：
## 用户偏好
- ...
## 重要事实
- ...
## 任务与承诺
- ...
## 未解决问题
- ...
## 最新上下文
- ...
3. 每条信息保持短句，避免重复。
4. 优先保留：用户偏好、重要事实、待办/承诺、未决问题、最近明确约定。
5. 输出总长度必须受控，尽量精简。

对话内容:
{dialogue}

请直接输出结构化摘要："""

ITERATIVE_SUMMARY_PROMPT = """以下是对之前对话的已有摘要：
{existing_summary}

现在需要将新的一段对话追加到摘要中。新对话内容：
{new_dialogue}

请更新摘要，保留之前的重要信息，同时添加新对话的关键内容。
总结要简洁明了，不超过200字。

请直接输出更新后的摘要："""

STRUCTURED_SECTIONS = (
    "用户偏好",
    "重要事实",
    "任务与承诺",
    "未解决问题",
    "最新上下文",
)

SECTION_ALIASES = {
    "偏好": "用户偏好",
    "用户偏好": "用户偏好",
    "重要事实": "重要事实",
    "事实": "重要事实",
    "任务": "任务与承诺",
    "承诺": "任务与承诺",
    "任务与承诺": "任务与承诺",
    "待办": "任务与承诺",
    "未解决问题": "未解决问题",
    "问题": "未解决问题",
    "疑问": "未解决问题",
    "最新上下文": "最新上下文",
    "上下文": "最新上下文",
    "最近上下文": "最新上下文",
}


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
        profile: SmallModelMemoryProfile | None = None,
    ):
        self.model_name = model_name
        self.max_summary_tokens = max_summary_tokens
        self.iterative_mode = iterative_mode
        self.profile = profile

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
        if self.profile is not None and self.profile.enabled:
            return STRUCTURED_SUMMARY_PROMPT.format(dialogue=dialogue_text)
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

    def normalize_summary_text(self, summary_text: str) -> str:
        if not (self.profile is not None and self.profile.enabled):
            return summary_text

        structured = self._parse_structured_summary(summary_text)
        normalized = self._render_structured_summary(structured)
        return self._apply_summary_cap(normalized)

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
            content=self.normalize_summary_text(summary_text),
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
            "content": f"以下是之前对话的摘要：\n{summary_entry.content}",
        }
        new_turns.append(ConversationTurn(message=summary_message))

        new_turns.extend(turns[end_idx + 1:])

        logger.info(
            f"Compressed {end_idx - start_idx + 1} messages into summary "
            f"({len(summary_entry.content)} chars)"
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
            combined_summary = self._merge_summaries(existing_summary, new_summary_text)
            logger.debug(
                f"Extending existing summary with {len(new_summary_text)} chars of new content"
            )
        else:
            combined_summary = self.normalize_summary_text(new_summary_text)

        return self.compress_old_messages(turns, combined_summary, start_idx, end_idx)

    def _merge_summaries(self, existing_summary: str, new_summary_text: str) -> str:
        if not (self.profile is not None and self.profile.enabled):
            return f"{existing_summary}\n\n---新增---\n{new_summary_text}"

        existing = self._parse_structured_summary(existing_summary)
        incoming = self._parse_structured_summary(new_summary_text)
        merged: dict[str, list[str]] = {}
        for section in STRUCTURED_SECTIONS:
            merged[section] = self._merge_section_items(
                existing.get(section, []), incoming.get(section, [])
            )

        return self._apply_summary_cap(self._render_structured_summary(merged))

    def _parse_structured_summary(self, summary_text: str) -> dict[str, list[str]]:
        sections = {section: [] for section in STRUCTURED_SECTIONS}
        current_section: str | None = None

        for raw_line in summary_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith("##"):
                section_name = line.lstrip("#").strip()
                current_section = SECTION_ALIASES.get(section_name)
                continue

            item = line
            if line.startswith(("- ", "* ")):
                item = line[2:].strip()
            elif line[:2].isdigit() and "." in line[:4]:
                item = line.split(".", 1)[1].strip()

            if current_section is None:
                current_section = self._classify_line(item)
            if current_section is None:
                current_section = "重要事实"

            if not item or item == "无":
                continue

            normalized_item = self._normalize_item(item)
            if normalized_item:
                sections[current_section].append(normalized_item)

        if any(sections.values()):
            for section in STRUCTURED_SECTIONS:
                sections[section] = self._merge_section_items([], sections[section])
            return sections

        fallback_section = self._classify_line(summary_text)
        normalized_item = self._normalize_item(summary_text)
        if normalized_item:
            sections[fallback_section] = [normalized_item]
        return sections

    def _render_structured_summary(self, sections: dict[str, list[str]]) -> str:
        rendered: list[str] = []
        for section in STRUCTURED_SECTIONS:
            rendered.append(f"## {section}")
            items = sections.get(section, [])
            if items:
                for item in items:
                    rendered.append(f"- {item}")
            else:
                rendered.append("- 无")
        return "\n".join(rendered)

    def _apply_summary_cap(self, summary_text: str) -> str:
        if self.profile is None or not self.profile.enabled:
            return summary_text

        limit = self.profile.summary_length_cap
        if len(summary_text) <= limit:
            return summary_text

        structured = self._parse_structured_summary(summary_text)
        trimmed = {section: list(items) for section, items in structured.items()}
        section_priority = list(STRUCTURED_SECTIONS)
        while len(self._render_structured_summary(trimmed)) > limit:
            removed = False
            for section in reversed(section_priority):
                if trimmed[section]:
                    trimmed[section].pop()
                    removed = True
                    break
            if not removed:
                break

        capped = self._render_structured_summary(trimmed)
        if len(capped) <= limit:
            return capped
        return capped[: limit - 1].rstrip() + "…"

    @staticmethod
    def _normalize_item(item: str) -> str:
        normalized = " ".join(item.replace("：", ": ").split())
        return normalized.strip("-• ")

    def _classify_line(self, item: str) -> str:
        text = item.lower()
        if any(keyword in text for keyword in ("喜欢", "偏好", "不吃", "不喝", "prefer")):
            return "用户偏好"
        if any(keyword in text for keyword in ("待办", "任务", "承诺", "约定", "会", "需要", "todo")):
            return "任务与承诺"
        if any(keyword in text for keyword in ("问题", "疑问", "还没", "未解决", "为什么", "吗", "?", "？")):
            return "未解决问题"
        if any(keyword in text for keyword in ("最近", "当前", "这次", "刚刚", "latest")):
            return "最新上下文"
        return "重要事实"

    def _merge_section_items(
        self,
        existing_items: list[str],
        new_items: list[str],
    ) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for item in [*existing_items, *new_items]:
            normalized_key = self._dedupe_key(item)
            if normalized_key in seen:
                continue
            seen.add(normalized_key)
            merged.append(item)
        return merged

    @staticmethod
    def _dedupe_key(item: str) -> str:
        return "".join(ch.lower() for ch in item if not ch.isspace())
