"""ListToolsTool - Meta-tool for listing all available tools (built-in and dynamic)."""

from typing import Any

from internal.agent.tool.base import Tool, ToolResult
from internal.agent.register import ToolRegistry
from internal.agent.tool.dynamic.storage import DynamicToolStorage


class ListToolsTool(Tool):
    """List all available tools including both built-in static tools and dynamically generated tools.

    Returns detailed information about each tool, including whether it's dynamic and
    metadata for generated tools.
    """

    def __init__(self, registry: ToolRegistry, storage: DynamicToolStorage):
        self.registry = registry
        self.storage = storage

    @property
    def name(self) -> str:
        return "list_tools"

    @property
    def description(self) -> str:
        return (
            "List all available tools including both built-in (static) and dynamically generated tools. "
            "Returns detailed information about each tool. Use detailed=true to include full parameters schema."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "include_dynamic": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include dynamically generated tools in the output",
                },
                "include_builtin": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include built-in static tools in the output",
                },
                "detailed": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include full parameters schema for each tool",
                },
            },
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        include_dynamic = kwargs.get("include_dynamic", True)
        include_builtin = kwargs.get("include_builtin", True)
        detailed = kwargs.get("detailed", False)

        result: dict[str, Any] = {
            "total_count": 0,
            "built_in": [],
            "dynamic": [],
        }

        # Get all dynamic tool names from storage index
        dynamic_tool_names = {info["name"] for info in self.storage.list()}

        for name, tool in self.registry.tools.items():
            is_dynamic = name in dynamic_tool_names

            # Apply filtering
            if is_dynamic and not include_dynamic:
                continue
            if not is_dynamic and not include_builtin:
                continue

            # Build tool info
            tool_info: dict[str, Any] = {
                "name": tool.name,
                "description": tool.description,
                "is_dynamic": is_dynamic,
            }

            if detailed:
                tool_info["parameters"] = tool.parameters

            # Add metadata for dynamic tools
            if is_dynamic:
                info = self.storage.info(name)
                if info:
                    tool_info["created_at"] = info.get("created_at")
                    tool_info["updated_at"] = info.get("updated_at")
                    tool_info["metadata"] = info.get("metadata", {})
                result["dynamic"].append(tool_info)
            else:
                result["built_in"].append(tool_info)

            result["total_count"] += 1

        return ToolResult(
            name=self.name,
            success=True,
            result=result,
            error=None,
        )
