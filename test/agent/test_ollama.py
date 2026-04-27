import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from internal.agent.agent_support.ollama import OllamaModel
from internal.config.config import AIModelConfig, AIModelType


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def build_config() -> AIModelConfig:
    return AIModelConfig(
        name="test",
        model="llama3",
        system_prompt="system",
        type=AIModelType.OllamaModel,
        default=True,
        config={},
        temperature=0.7,
        streaming=False,
    )


async def _run_chat_with_response(response, tools=None):
    model = OllamaModel(build_config())
    model._client = FakeClient(response)
    model._system_prompt_resolved = True
    model.history = [{"role": "system", "content": "system"}]
    return await model.chat("你好", tools=tools), model


def test_ollama_chat_reads_nested_message_content_from_object_response():
    response = SimpleNamespace(
        message=SimpleNamespace(role="assistant", content="我是 Live2D Agent")
    )

    result, model = asyncio.run(_run_chat_with_response(response))

    assert result == {"role": "assistant", "content": "我是 Live2D Agent"}
    assert model.history[-1] == result


def test_ollama_chat_preserves_nested_message_tool_calls_from_object_response():
    response = SimpleNamespace(
        message=SimpleNamespace(
            role="assistant",
            content="",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "demo_tool", "arguments": "{}"},
                }
            ],
        )
    )

    result, model = asyncio.run(
        _run_chat_with_response(
            response,
            tools=[{"type": "function", "function": {"name": "demo_tool"}}],
        )
    )

    assert result["role"] == "assistant"
    assert result["content"] == ""
    assert result["tool_calls"][0]["function"]["name"] == "demo_tool"
    assert model.history[-1] == result


def test_ollama_chat_keeps_top_level_content_fallback_for_object_response():
    response = SimpleNamespace(role="assistant", content="top-level content")

    result, model = asyncio.run(_run_chat_with_response(response))

    assert result == {"role": "assistant", "content": "top-level content"}
    assert model.history[-1] == result
