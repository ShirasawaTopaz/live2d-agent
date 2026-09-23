"""Code templates for AI-authored cordis plugins.

Templates are plain strings so they can be inspected, diffed, and versioned by
the evolution tools. ``kind`` selects the skeleton: ``tool``, ``loop``,
``output``, ``service``, or ``prompt``.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["PluginTemplate", "TEMPLATES", "render"]


@dataclass(frozen=True, slots=True)
class PluginTemplate:
    kind: str
    description: str
    header: str
    body: str


FOOTER = '''

def apply(ctx, config=None):
    service = {class_name}(ctx, "{service}")
    ctx.service("{service}", service)
'''

TOOL_BODY = '''

class {class_name}(Service):
    """Tool plugin: contributes one tool to the registry."""

    inject = ["tools"]

    def __init__(self, ctx, name="{service}"):
        super().__init__(ctx, name)

    async def start(self):
        tools = self.ctx.get("tools")
        if tools is not None:
            tools.register(_Tool(), owner=self.ctx)


class _Tool:
    name = "{name}"
    description = "{description}"
    parameters = {{"type": "object", "properties": {{}}, "required": []}}

    async def execute(self, **kwargs):
        return "{name} executed"
'''

SERVICE_BODY = '''

class {class_name}(Service):
    """Service plugin: exposes a named capability to other plugins."""

    def __init__(self, ctx, name="{service}"):
        super().__init__(ctx, name)

    def ping(self):
        return "{service} ok"
'''

LOOP_BODY = '''

class {class_name}(Service):
    """Agent-loop plugin: replaces the chat -> model -> tools -> bubble loop."""

    inject = ["agent/model"]

    def __init__(self, ctx, name="agent/loop"):
        super().__init__(ctx, name)
        self.agent = None
        self.max_tool_calls = 5

    def attach_agent(self, agent):
        self.agent = agent

    async def run(self, message, ws=None):
        from internal.plugins.agent.loop import ChatResult

        model = self.ctx.get("agent/model")
        response = await model.model.chat(message=message, tools=None)
        content = response.get("content", "") if isinstance(response, dict) else ""
        return ChatResult(content=str(content), raw=response)
'''

OUTPUT_BODY = '''

class {class_name}(Service):
    """Bubble-output plugin: renders assistant output."""

    def __init__(self, ctx, name="outputs/bubble"):
        super().__init__(ctx, name)
        self.widget = None

    def attach(self, widget=None, timing=None):
        self.widget = widget

    async def begin(self, chunk):
        return None

    async def stream(self, chunk):
        chunk = await self.ctx.waterfall("bubble/stream", chunk, next=lambda: chunk)
        return chunk

    async def finish(self, text, duration_ms=0):
        return None
'''

PROMPT_BODY = '''

class {class_name}(Service):
    """Prompt plugin: contributes instructions without touching code paths."""

    def __init__(self, ctx, name="{service}"):
        super().__init__(ctx, name)
        self.text = """{description}"""

    def prompt(self):
        return self.text
'''

TEMPLATES: dict[str, PluginTemplate] = {
    "tool": PluginTemplate("tool", "Adds one tool to ctx.tools", "", TOOL_BODY),
    "service": PluginTemplate("service", "Exposes a named service", "", SERVICE_BODY),
    "loop": PluginTemplate("loop", "Replaces the agent conversation loop", "", LOOP_BODY),
    "output": PluginTemplate("output", "Replaces the bubble output module", "", OUTPUT_BODY),
    "prompt": PluginTemplate("prompt", "Contributes prompt text", "", PROMPT_BODY),
}


def _class_name(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_")) or "Plugin"


def _service_name(name: str, kind: str) -> str:
    if kind == "loop":
        return "agent/loop"
    if kind == "output":
        return "outputs/bubble"
    return name.replace("_", "-")


def render(
    kind: str,
    name: str,
    *,
    description: str = "",
    service: str | None = None,
    **extra: str,
) -> str:
    """Render a plugin skeleton for ``kind``."""
    template = TEMPLATES.get(kind)
    if template is None:
        raise ValueError(f"unknown plugin kind '{kind}' (expected {sorted(TEMPLATES)})")
    class_name = _class_name(name)
    service_name = service or _service_name(name, kind)
    header = (
        f'"""{description or template.description}."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any\n\n"
        "from internal.cordis import Service\n\n"
        f'plugin_name = "{name}"\n'
    )
    body = template.body.format(
        class_name=class_name,
        name=name,
        service=service_name,
        description=description or template.description,
    )
    footer = FOOTER.format(class_name=class_name, service=service_name)
    return header + body + footer
