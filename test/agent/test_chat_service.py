import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from internal.agent.chat_service import ChatService
from internal.agent.tool.base import Tool
from internal.websocket.client import Client


class DemoTool(Tool):
    @property
    def name(self) -> str:
        return "demo_tool"

    @property
    def description(self) -> str:
        return "Demo tool"

    @property
    def parameters(self) -> dict:
        return {"type": "object"}

    async def execute(self, **kwargs):
        return f"tool-result:{kwargs['value']}"


class FakeToolRegistry:
    def __init__(self, tool: Tool):
        self.tools = {tool.name: tool}
        self.is_none = False

    def get_definitions(self) -> list[dict]:
        return [{"type": "function", "function": {"name": "demo_tool"}}]


class FakeBubbleTiming:
    def __init__(self):
        self.single_bubbles: list[str] = []
        self.displayed_texts: list[tuple[str, int]] = []

    @staticmethod
    def should_skip_content(_content: str) -> bool:
        return False

    async def send_single_bubble(self, content, _ws, _bubble_widget):
        self.single_bubbles.append(content)

    async def display_text(self, text, _ws, _bubble_widget, **kwargs):
        self.displayed_texts.append((text, kwargs.get("text_color", 0xFFFFFF)))


class FakeWs(Client):
    def __init__(self):
        self.conn = None
        self._session = SimpleNamespace(closed=True)

    async def close(self):
        return None

    async def send(self, message: bytes):
        return None


class FakeModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.history = []
        self.config = SimpleNamespace(streaming=False)
        self._tools_supported = True
        self.calls = []

    async def chat(self, message, tools=None):
        self.calls.append((message, tools))
        return self.responses.pop(0)


class FakeAgent:
    def __init__(self, responses):
        self.model = FakeModel(responses)
        self.tool_registry = FakeToolRegistry(DemoTool())
        self.memory = None
        self.bubble_widget = None
        self.bubble_timing = FakeBubbleTiming()
        self.max_tool_calls = 5
        self._compression_task = None
        self.rag = None

    @staticmethod
    def calculate_bubble_duration(_text: str) -> int:
        return 5000

    async def initialize_memory(self):
        return None

    async def _compress_context_in_background(self):
        return None


class FakeMemory:
    def __init__(self, messages):
        self._initialized = True
        self.messages = list(messages)
        self.added_messages = []
        self.saved = False

    def add_message(self, message):
        self.added_messages.append(message)
        self.messages.append(message)

    async def get_current_messages(self):
        return self.messages.copy()

    def should_compress(self):
        return False

    async def save_current(self):
        self.saved = True


async def _run_chat_service_executes_tool_calls_before_returning_content():
    agent = FakeAgent(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "demo_tool",
                            "arguments": '{"value": 3}',
                        },
                    }
                ],
            },
            {"role": "assistant", "content": "final answer"},
        ]
    )
    service = ChatService(agent)

    response = await service.chat("hello", FakeWs())

    assert response == {"role": "assistant", "content": "final answer"}
    assert agent.model.history == [
        {"role": "tool", "tool_call_id": "call_1", "content": "tool-result:3"}
    ]
    assert agent.bubble_timing.single_bubbles == ["final answer"]
    assert agent.model.calls[0][0] == "hello"
    assert agent.model.calls[1][0] is None


def test_chat_service_executes_tool_calls_before_returning_content():
    asyncio.run(_run_chat_service_executes_tool_calls_before_returning_content())


async def _run_chat_service_fallback_tool_call_in_content_executes_tool_result_bubble():
    agent = FakeAgent([])
    service = ChatService(agent)

    await service.try_parse_and_send_bubble(
        '<tool_call>{"name":"demo_tool","arguments":{"value":5}}</tool_call>',
        FakeWs(),
    )

    assert agent.bubble_timing.single_bubbles == []
    assert agent.bubble_timing.displayed_texts == [("tool-result:5", 0xFFFFFF)]


def test_chat_service_fallback_tool_call_in_content_executes_tool_result_bubble():
    asyncio.run(_run_chat_service_fallback_tool_call_in_content_executes_tool_result_bubble())


async def _run_chat_service_with_memory_keeps_system_and_does_not_duplicate_long_input():
    agent = FakeAgent([{"role": "assistant", "content": "final answer"}])
    long_input = "长" * 2000
    agent.memory = FakeMemory([{"role": "system", "content": "persona prefix"}])
    service = ChatService(agent)

    response = await service.chat(long_input, FakeWs())

    assert response == {"role": "assistant", "content": "final answer"}
    assert agent.model.calls[0][0] is None
    assert agent.model.history == [
        {"role": "system", "content": "persona prefix"},
        {"role": "user", "content": long_input},
    ]
    assert [msg["role"] for msg in agent.memory.added_messages] == ["user", "assistant"]


def test_chat_service_with_memory_keeps_system_and_does_not_duplicate_long_input():
    asyncio.run(_run_chat_service_with_memory_keeps_system_and_does_not_duplicate_long_input())
