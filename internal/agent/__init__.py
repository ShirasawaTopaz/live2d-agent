"""Agent package exports."""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from internal.agent import bubble_timing, chat_service, tool_setup
    from internal.agent.agent import Agent, create_agent

__all__ = [
    "Agent",
    "bubble_timing",
    "chat_service",
    "create_agent",
    "tool_setup",
]


def __getattr__(name: str):
    if name in {"Agent", "create_agent"}:
        module = import_module("internal.agent.agent")
        return getattr(module, name)

    if name in {"bubble_timing", "chat_service", "tool_setup"}:
        return import_module(f"internal.agent.{name}")

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
