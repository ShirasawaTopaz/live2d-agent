"""DeleteToolTool - Meta-tool for deleting dynamically generated tools."""

import logging
from typing import Any

from internal.agent.tool.base import Tool, ToolResult
from internal.agent.register import ToolRegistry
from internal.agent.tool.dynamic.storage import DynamicToolStorage
from internal.agent.tool.dynamic.audit import get_audit_logger

logger = logging.getLogger(__name__)
audit = get_audit_logger()


class DeleteToolTool(Tool):
    """Delete a dynamically generated tool from persistent storage and unregister it.

    Only works with dynamically generated tools, not built-in static tools.
    Requires confirmation to prevent accidental deletion.
    """

    def __init__(self, registry: ToolRegistry, storage: DynamicToolStorage):
        self.registry = registry
        self.storage = storage

    @property
    def name(self) -> str:
        return "delete_tool"

    @property
    def description(self) -> str:
        return (
            "Delete a dynamically generated tool. "
            "Removes it from persistent storage and unregisters it from the tool registry. "
            "Only works with dynamically generated tools, not built-in tools. "
            "Requires confirm=true to proceed."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "Name of the dynamic tool to delete",
                },
                "confirm": {
                    "type": "boolean",
                    "default": False,
                    "description": "Confirmation that you really want to delete this tool. Must be set to true.",
                },
            },
            "required": ["tool_name"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        tool_name = kwargs.get("tool_name")
        confirm = kwargs.get("confirm", False)

        # Required parameters from JSON schema
        assert isinstance(tool_name, str)

        # Require confirmation as safety check
        if not confirm:
            error_msg = f"Confirmation required to delete tool '{tool_name}'. Set confirm=true to proceed. This is a safety check to prevent accidental deletion."
            audit.log_deletion(
                tool_name=tool_name,
                success=False,
                error=error_msg,
            )
            return ToolResult(
                name=self.name,
                success=False,
                result=None,
                error=error_msg,
            )

        # Check if it's a dynamic tool that exists in storage
        if not self.storage.exists(tool_name):
            error_msg = f"Dynamic tool '{tool_name}' does not exist in storage. Only dynamically generated tools can be deleted with this tool. Built-in tools cannot be deleted."
            audit.log_deletion(
                tool_name=tool_name,
                success=False,
                error=error_msg,
            )
            return ToolResult(
                name=self.name,
                success=False,
                result=None,
                error=error_msg,
            )

        try:
            # Unregister from registry first
            unregistered = self.registry.unregister_dynamic_tool(tool_name)
            # Delete from storage
            deleted = self.storage.delete(tool_name)

            if deleted:
                logger.info(f"Successfully deleted dynamic tool: {tool_name}")
                audit.log_deletion(
                    tool_name=tool_name,
                    success=True,
                )
                return ToolResult(
                    name=self.name,
                    success=True,
                    result={
                        "message": f"Tool '{tool_name}' deleted successfully",
                        "tool_name": tool_name,
                        "unregistered": unregistered,
                    },
                    error=None,
                )
            else:
                error_msg = f"Failed to delete dynamic tool '{tool_name}': storage.delete returned False"
                logger.error(error_msg)
                audit.log_deletion(
                    tool_name=tool_name,
                    success=False,
                    error=error_msg,
                )
                return ToolResult(
                    name=self.name,
                    success=False,
                    result=None,
                    error=error_msg,
                )

        except Exception as e:
            import traceback
            error_msg = str(e)
            tb_str = traceback.format_exc()
            logger.error(f"Error deleting tool '{tool_name}': {error_msg}", exc_info=True)
            audit.log_deletion(
                tool_name=tool_name,
                success=False,
                error=error_msg,
            )
            audit.log_error(
                error_type="deletion_exception",
                message=error_msg,
                tool_name=tool_name,
                exception=tb_str,
            )
            return ToolResult(
                name=self.name,
                success=False,
                result=None,
                error=f"Error deleting tool: {str(e)}",
            )
