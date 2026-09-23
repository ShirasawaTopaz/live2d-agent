"""Plugin slot: the agent conversation loop (``agent/loop``).

The minimal loop is ``chat → model → tool calls → bubble output`` with a
``max_tool_calls`` bound. Two implementations are interchangeable by editing
``cordis.yml``:

* ``agent.loop`` – the default loop, delegating to ``Agent.chat_service`` so
  the production behaviour (streaming, Live2D expression scheduling, tool
  ordering, confirmation-bubble suppression, RAG and session routing) is kept.
* ``agent.loop_minimal`` – a reduced loop without streaming, expression
  scheduling, or memory injection, useful as a template for replacements.

Both satisfy the same ``AgentLoop`` contract, and every step emits a
waterfall/emit hook so other plugins can observe or override the flow:

``agent/chat/start`` → ``agent/chat/request`` (waterfall) →
``bubble/stream`` (waterfall) → ``agent/tool/call`` (waterfall) →
``agent/chat/finished``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from internal.cordis import Schema, Service

plugin_name = "agent/loop"

module_schema = Schema.object(
    {
        "max_tool_calls": Schema.natural().default(5),
    }
)


@dataclass(slots=True)
class ChatResult:
    """Normalised outcome of one loop turn."""

    content: str = ""
    role: str = "assistant"
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    streamed: bool = False
    raw: Any = None


class AgentLoop(Protocol):
    """Contract every agent-loop plugin must satisfy."""

    max_tool_calls: int

    async def run(self, message: Any, ws: Any) -> ChatResult: ...


class DefaultAgentLoop(Service):
    """Delegates to the existing :class:`ChatService` implementation."""

    def __init__(self, ctx: Any, name: str = "agent/loop") -> None:
        super().__init__(ctx, name)
        self.agent: Any = None
        self.max_tool_calls = 5

    def attach_agent(self, agent: Any) -> None:
        self.agent = agent
        max_calls = getattr(agent, "max_tool_calls", None)
        if isinstance(max_calls, int) and max_calls > 0:
            self.max_tool_calls = max_calls

    async def run(self, message: Any, ws: Any = None) -> ChatResult:
        if self.agent is None:
            raise RuntimeError("agent loop has no agent attached")
        root = self.ctx.root
        root.emit("agent/chat/start", message)
        response = await self.agent.chat(message, ws)
        result = to_chat_result(response)
        root.emit("agent/chat/finished", result)
        return result


def to_chat_result(response: Any) -> ChatResult:
    if isinstance(response, dict):
        content = str(response.get("content") or "")
        role = str(response.get("role") or "assistant")
        tool_calls = list(response.get("tool_calls") or [])
        return ChatResult(content=content, role=role, tool_calls=tool_calls, raw=response)
    content = str(getattr(response, "content", "") or "")
    role = str(getattr(response, "role", "assistant"))
    return ChatResult(content=content, role=role, raw=response)


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    service = DefaultAgentLoop(ctx, "agent/loop")
    service.max_tool_calls = int((config or {}).get("max_tool_calls") or 5)
    ctx.service("agent/loop", service)
