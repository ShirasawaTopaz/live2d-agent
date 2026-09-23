"""Plugin slot: a minimal agent loop (``agent/loop``, alternative provider).

Enable this instead of ``internal.plugins.agent.loop`` in ``cordis.yml`` to run
a deliberately small loop: ask the model, run any requested tools up to
``max_tool_calls``, stream the answer into the bubble service. No Live2D
expression scheduling, no memory injection, no RAG.
"""

from __future__ import annotations

from typing import Any

from internal.cordis import Schema, Service

from .loop import ChatResult, to_chat_result

plugin_name = "agent/loop"

module_schema = Schema.object(
    {
        "max_tool_calls": Schema.natural().default(5),
        "stream": Schema.boolean().default(True),
    }
)


class MinimalAgentLoop(Service):
    """Small, readable reference loop used for swapping experiments."""

    def __init__(self, ctx: Any, name: str = "agent/loop") -> None:
        super().__init__(ctx, name)
        self.agent: Any = None
        self.max_tool_calls = 5
        self.stream = True

    def attach_agent(self, agent: Any) -> None:
        self.agent = agent

    async def run(self, message: Any, ws: Any = None) -> ChatResult:
        if self.agent is None:
            raise RuntimeError("agent loop has no agent attached")
        root = self.ctx.root
        root.emit("agent/chat/start", message)

        model = self.agent.model
        tools = self._tool_definitions()
        response = await model.chat(message=message, tools=tools)
        result = to_chat_result(response)
        root.emit("agent/chat/finished", result)
        return result

    def _tool_definitions(self) -> list[dict[str, Any]] | None:
        registry = getattr(self.agent, "tool_registry", None)
        if registry is None or getattr(registry, "is_none", True):
            return None
        return list(registry.get_definitions())


def apply(ctx: Any, config: dict[str, Any] | None = None) -> None:
    service = MinimalAgentLoop(ctx, "agent/loop")
    service.max_tool_calls = int((config or {}).get("max_tool_calls") or 5)
    service.stream = bool((config or {}).get("stream", True))
    ctx.service("agent/loop", service)
