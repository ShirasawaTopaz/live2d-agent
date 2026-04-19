import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from internal.memory._context import ContextManager
from internal.memory._long_term import LongTermMemory
from internal.memory._small_model_profile import SmallModelMemoryProfile
from internal.memory._summary import Summarizer, STRUCTURED_SECTIONS
from internal.memory._types import ConversationTurn, LongTermEntry
from internal.memory.storage._base import BaseStorage


class _DummyStorage(BaseStorage):
    async def save_session(self, session_id: str, data: dict) -> None:
        return None

    async def load_session(self, session_id: str) -> dict | None:
        return None

    async def delete_session(self, session_id: str) -> bool:
        return False

    async def list_sessions(self):
        return []

    async def save_long_term(self, entry: LongTermEntry) -> None:
        return None

    async def query_long_term(self, query: str, limit: int = 10):
        return []

    async def delete_long_term(self, entry_id: str) -> bool:
        return False

    async def init(self) -> None:
        return None


def _small_profile() -> SmallModelMemoryProfile:
    return SmallModelMemoryProfile(
        enabled=True,
        reason="test-small-model",
        summary_style="compact_summary",
        compression_aggressiveness="aggressive",
        preserve_recent_count=3,
        summary_length_cap=320,
        injection_compactness="tight",
    )


def _make_turn(role: str, content: str) -> ConversationTurn:
    return ConversationTurn(message={"role": role, "content": content}, timestamp=datetime.now())


def test_legacy_summary_normalization_preserves_structured_sections_and_slots():
    summarizer = Summarizer(iterative_mode=True, profile=_small_profile())
    turns = [
        _make_turn("system", "你是助手"),
        _make_turn("user", "我喜欢黑咖啡，不要加糖。"),
        _make_turn("assistant", "收到。"),
        _make_turn("user", "周三前帮我整理东京三日行程。"),
        _make_turn("assistant", "好的。"),
        _make_turn("user", "预算是 3000 元，航班还没定。"),
    ]

    raw_summary = """
偏好:
- 喜欢黑咖啡，不加糖
事实:
- 预算 3000 元
任务:
- 周三前整理东京三日行程
问题:
- 航班尚未确定
"""
    new_turns, summary_entry = summarizer.compress_with_iterative(
        turns=turns,
        new_summary_text=raw_summary,
        start_idx=1,
        end_idx=4,
    )

    for section in STRUCTURED_SECTIONS:
        assert f"## {section}" in summary_entry.content

    assert "黑咖啡" in summary_entry.content
    assert "3000 元" in summary_entry.content
    assert "东京三日行程" in summary_entry.content
    assert "航班尚未确定" in summary_entry.content
    assert len(summary_entry.content) <= 320
    assert any(turn.message.get("role") == "system" for turn in new_turns)


def test_iterative_compression_deduplicates_and_stays_bounded():
    summarizer = Summarizer(iterative_mode=True, profile=_small_profile())
    turns = [
        _make_turn("system", "你是助手"),
        _make_turn("system", "以下是之前对话的摘要：\n## 用户偏好\n- 喜欢黑咖啡\n## 重要事实\n- 预算 3000 元\n## 任务与承诺\n- 周三前整理东京行程\n## 未解决问题\n- 航班未定\n## 最新上下文\n- 今天刚确认出行"),
        _make_turn("user", "再补充，还是喜欢黑咖啡，预算 3000 元不变。"),
        _make_turn("assistant", "已更新。"),
    ]
    new_summary = """
## 用户偏好
- 喜欢黑咖啡
## 重要事实
- 预算 3000 元
## 任务与承诺
- 周三前整理东京行程
## 未解决问题
- 航班未定
## 最新上下文
- 新增了酒店筛选
"""

    _, summary_entry = summarizer.compress_with_iterative(
        turns=turns,
        new_summary_text=new_summary,
        start_idx=2,
        end_idx=3,
    )

    assert summary_entry.content.count("喜欢黑咖啡") == 1
    assert summary_entry.content.count("预算 3000 元") == 1
    assert len(summary_entry.content) <= 320


def test_profile_aware_recent_preservation_count_used_in_truncate():
    context_manager = ContextManager(
        max_messages=20,
        max_tokens=4096,
        compression_threshold=10,
        preserve_recent_count=5,
        profile=_small_profile(),
    )
    turns = [_make_turn("user", f"msg-{idx}") for idx in range(8)]

    _, start_idx, end_idx = context_manager.truncate(turns, keep_last=5)

    assert start_idx == 0
    # 8 total, preserve 3 recent => compress [0..4]
    assert end_idx == 4


def test_long_term_injection_compact_for_small_profile():
    now = datetime.now()
    entries = [
        LongTermEntry(
            id=f"id-{i}",
            content=f"这是一段比较长的历史记忆内容 {i}，用于验证压缩注入是否会被裁剪并且保持紧凑格式。",
            keywords=["测试"],
            source_session_id="s",
            created_at=now - timedelta(minutes=i),
        )
        for i in range(5)
    ]
    long_term = LongTermMemory(storage=_DummyStorage(), enabled=True, profile=_small_profile())

    prompt = long_term.build_injection_prompt(entries)

    assert prompt.startswith("\n\n## 记忆\n")
    assert prompt.count("\n- ") <= 3
    assert len(prompt) <= 240
