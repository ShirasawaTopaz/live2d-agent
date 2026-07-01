"""Tests for Transformers.stream_chat tool fallback path."""

from unittest.mock import AsyncMock, MagicMock


class FakeTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        return "prompt"

    def encode(self, text):
        return [1, 2, 3]


class TestTransformersStreamChatToolsFallback:
    async def test_stream_chat_awaits_chat_when_tools_present(self):
        from internal.agent.agent_support.transformers import Transformers

        instance = Transformers.__new__(Transformers)
        instance._tokenizer = FakeTokenizer()
        instance._model = MagicMock()
        instance._tools_supported = True
        instance.history = []
        instance._system_prompt_resolved = True
        instance._resolved_system_prompt = ""

        chat_result = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"function": {"name": "test_tool", "arguments": "{}"}}
            ],
        }
        instance.chat = AsyncMock(return_value=chat_result)

        async def collect():
            chunks = []
            async for chunk in instance.stream_chat("hello", tools=[{"type": "function"}]):
                chunks.append(chunk)
            return chunks

        chunks = await collect()
        assert len(chunks) == 1
        assert chunks[0]["done"] is True
        assert chunks[0].get("tool_calls") is not None
        instance.chat.assert_awaited_once()
