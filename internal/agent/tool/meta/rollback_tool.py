"""RollbackTool - Meta-tool for rolling back dynamic tools to previous versions."""

import logging
from typing import Any

from internal.agent.tool.base import Tool, ToolResult
from internal.agent.register import ToolRegistry
from internal.agent.tool.dynamic.storage import DynamicToolStorage
from internal.agent.tool.dynamic.audit import get_audit_logger

logger = logging.getLogger(__name__)
audit = get_audit_logger()


class RollbackTool(Tool):
    """Rollback a dynamically generated tool to a previous version.
    
    Uses the version history to revert to an earlier version,
    keeping a rollback entry in the version history.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        storage: DynamicToolStorage,
    ):
        self.registry = registry
        self.storage = storage

    @property
    def name(self) -> str:
        return "rollback_tool"

    @property
    def description(self) -> str:
        return (
            "Rollback a dynamically generated tool to a previous version. "
            "Requires tool_name and version. Lists available versions if no version specified."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "Name of the dynamic tool to rollback",
                },
                "version": {
                    "type": "string",
                    "description": "Version to rollback to (e.g. 1.0.0). If not provided, lists available versions.",
                },
                "confirm": {
                    "type": "boolean",
                    "default": False,
                    "description": "Confirmation that you want to perform the rollback. Must be true to proceed.",
                },
            },
            "required": ["tool_name"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        tool_name = kwargs.get("tool_name")
        version = kwargs.get("version")
        confirm = kwargs.get("confirm", False)

        # Required parameters from JSON schema
        assert isinstance(tool_name, str)

        # Check if tool exists
        if not self.storage.exists(tool_name):
            error_msg = f"Dynamic tool '{tool_name}' does not exist"
            audit.log_error(
                error_type="rollback_failed",
                message=error_msg,
                tool_name=tool_name,
            )
            return ToolResult(
                name=self.name,
                success=False,
                result=None,
                error=error_msg,
            )

        # Get available versions
        versions = self.storage.version_manager.get_versions(tool_name)
        if not versions:
            error_msg = f"No version history found for '{tool_name}'"
            audit.log_error(
                error_type="rollback_failed",
                message=error_msg,
                tool_name=tool_name,
            )
            return ToolResult(
                name=self.name,
                success=False,
                result=None,
                error=error_msg,
            )

        version_list = [v.version for v in versions]
        latest = versions[-1].version if versions else None

        # If no version specified, just list available versions
        if version is None:
            return ToolResult(
                name=self.name,
                success=True,
                result={
                    "message": f"Available versions for '{tool_name}': {', '.join(version_list)}\nLatest version: {latest}\nUse rollback_tool with version and confirm=true to rollback.",
                    "tool_name": tool_name,
                    "versions": [v.to_dict() for v in versions],
                    "latest": latest,
                },
                error=None,
            )

        # Check if version exists
        version_info = self.storage.version_manager.get_version(tool_name, version)
        if version_info is None:
            error_msg = f"Version '{version}' not found for '{tool_name}'. Available: {', '.join(version_list)}"
            audit.log_error(
                error_type="rollback_failed",
                message=error_msg,
                tool_name=tool_name,
            )
            return ToolResult(
                name=self.name,
                success=False,
                result=None,
                error=error_msg,
            )

        # Require confirmation
        if not confirm:
            return ToolResult(
                name=self.name,
                success=False,
                result=None,
                error=(
                    f"Confirmation required to rollback '{tool_name}' to version {version}.\n"
                    f"Current version is {latest}.\n"
                    "Set confirm=true to proceed with rollback."
                ),
            )

        # Perform rollback
        try:
            success, error = self.storage.version_manager.rollback_to(tool_name, version)
            if not success:
                audit.log_error(
                    error_type="rollback_failed",
                    message=error or "Unknown error",
                    tool_name=tool_name,
                )
                return ToolResult(
                    name=self.name,
                    success=False,
                    result=None,
                    error=error or "Rollback failed",
                )

            # Get the rolled back code
            code = self.storage.version_manager.get_version_code(tool_name, version)
            if code is None:
                error_msg = "Failed to get code for rolled back version"
                audit.log_error(
                    error_type="rollback_failed",
                    message=error_msg,
                    tool_name=tool_name,
                )
                return ToolResult(
                    name=self.name,
                    success=False,
                    result=None,
                    error=error_msg,
                )

            # Save the rolled back code to the active tool file
            self.storage.save(tool_name, code, {
                "description": f"Rollback to version {version}",
            })

            # Unregister and reload the tool
            self.registry.unregister_dynamic_tool(tool_name)
            tool_class = self.storage.load(tool_name)
            if tool_class is None:
                error_msg = "Failed to reload rolled back tool"
                audit.log_error(
                    error_type="rollback_failed",
                    message=error_msg,
                    tool_name=tool_name,
                )
                return ToolResult(
                    name=self.name,
                    success=False,
                    result=None,
                    error=error_msg,
                )

            # Register the rolled back tool
            self.registry.register_dynamic_tool(tool_class)

            new_latest = self.storage.version_manager.get_latest_version(tool_name)
            logger.info(f"Successfully rolled back dynamic tool '{tool_name}' to version {version}")

            audit.log_error(  # Using existing audit error for lack of generic log method
                error_type="rollback_success",
                message=f"Rolled back '{tool_name}' from {latest} to {version}",
                tool_name=tool_name,
            )

            return ToolResult(
                name=self.name,
                success=True,
                result={
                    "message": f"Successfully rolled back '{tool_name}' from version {latest} to {version}",
                    "tool_name": tool_name,
                    "previous_version": latest,
                    "new_version": new_latest.version if new_latest else version,
                    "rolled_back_to": version,
                },
                error=None,
            )

        except Exception as e:
            import traceback
            error_msg = str(e)
            tb_str = traceback.format_exc()
            logger.error(f"Unexpected error rolling back tool '{tool_name}': {error_msg}", exc_info=True)
            audit.log_error(
                error_type="rollback_exception",
                message=error_msg,
                tool_name=tool_name,
                exception=tb_str,
            )
            return ToolResult(
                name=self.name,
                success=False,
                result=None,
                error=f"Unexpected error during rollback: {error_msg}",
            )
