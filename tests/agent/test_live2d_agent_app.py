import asyncio
from types import SimpleNamespace

from internal.app.live2d_agent_app import Live2DAgentApp


class FakeModel:
    def __init__(self) -> None:
        self.history = [{"role": "assistant", "content": "old"}]
        self._system_prompt_resolved = False

    async def _resolve_system_prompt(self) -> str:
        return "resolved system prompt"


class FakeMemory:
    def __init__(self) -> None:
        self._initialized = True
        self.reset_calls: list[str | None] = []
        self.messages: list[dict[str, str]] = []

    async def reset_active_context(self, title: str | None = None) -> None:
        self.reset_calls.append(title)
        self.messages = []

    def add_message(self, message: dict[str, str]) -> None:
        self.messages.append(message)

    async def get_current_messages(self) -> list[dict[str, str]]:
        return list(self.messages)


class FakeAgent:
    def __init__(self) -> None:
        self.model = FakeModel()
        self.memory = FakeMemory()

    async def initialize_memory(self) -> None:
        self.memory._initialized = True


def test_reset_context_preserves_system_prompt() -> None:
    async def scenario() -> None:
        app = Live2DAgentApp()
        app.agent = FakeAgent()
        cleared = []
        app.input_box = SimpleNamespace(clear_input=lambda: cleared.append(True))

        await app.reset_context()

        assert app.agent.memory.reset_calls == ["default"]
        assert app.agent.model.history == [
            {"role": "system", "content": "resolved system prompt"}
        ]
        assert app.agent.model._system_prompt_resolved is True
        assert app.agent.memory.messages == [
            {"role": "system", "content": "resolved system prompt"}
        ]
        assert cleared == [True]

    asyncio.run(scenario())
