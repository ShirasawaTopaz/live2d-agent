"""GenerateToolTool - Meta-tool for generating new dynamic tools from natural language description."""

import logging
from datetime import datetime
from typing import Any, Optional

from internal.agent.tool.base import Tool, ToolResult
from internal.agent.register import ToolRegistry
from internal.agent.tool.dynamic.generator import ToolGenerator, ToolGenerationError
from internal.agent.tool.dynamic.storage import DynamicToolStorage
from internal.agent.tool.dynamic.audit import get_audit_logger

logger = logging.getLogger(__name__)
audit = get_audit_logger()


class GenerateToolTool(Tool):
    """Generate a new tool based on natural language description.

    This meta-tool uses the existing dynamic tool generation infrastructure to:
    1. Generate Python code for a new tool from natural language
    2. Validate the code for security using AST analysis
    3. Save it to persistent storage
    4. Register it dynamically for immediate use
    5. Run ruff check on the generated code
    """

    def __init__(
        self,
        registry: ToolRegistry,
        storage: DynamicToolStorage,
        generator: Optional[ToolGenerator] = None,
    ):
        self.registry = registry
        self.storage = storage
        self.generator = generator or ToolGenerator()

    @property
    def name(self) -> str:
        return "generate_tool"

    @property
    def description(self) -> str:
        return (
            "Generate a new tool based on natural language description. "
            "Validates the tool for security, saves it to persistent storage, "
            "and registers it for immediate use. Requires tool_name and description."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "Name of the tool to generate, must be valid snake_case Python identifier",
                },
                "description": {
                    "type": "string",
                    "description": "Natural language description of what the tool should do",
                },
                "parameters": {
                    "type": "object",
                    "description": "JSON Schema defining the tool's parameters (optional, inferred if not provided)",
                },
                "implementation": {
                    "type": "string",
                    "description": "Custom implementation code (optional, generated automatically if not provided)",
                },
                "template": {
                    "type": "string",
                    "enum": ["simple", "http", "calc"],
                    "default": "simple",
                    "description": "Template to use for the tool implementation",
                },
                "extra_imports": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of extra modules to import (must be in security whitelist)",
                },
            },
            "required": ["tool_name", "description"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        tool_name = kwargs.get("tool_name")
        description = kwargs.get("description")
        parameters = kwargs.get("parameters")
        implementation = kwargs.get("implementation")
        template = kwargs.get("template", "simple")
        extra_imports = kwargs.get("extra_imports")

        # Required parameters from JSON schema
        assert isinstance(tool_name, str)
        assert isinstance(description, str)

        # Audit log the request
        audit.log_generation_request(
            tool_name=tool_name,
            description=description,
            parameters=parameters,
            template=template,
            extra_imports=extra_imports,
        )

        # Validate tool name is a valid Python identifier
        if not tool_name.isidentifier():
            error_msg = f"Invalid tool name '{tool_name}'. Must be a valid Python identifier (letters, numbers, underscore, cannot start with a number)."
            audit.log_generation_complete(
                tool_name=tool_name,
                success=False,
                errors=[error_msg],
            )
            return ToolResult(
                name=self.name,
                success=False,
                result=None,
                error=error_msg,
            )

        # Check if tool already exists
        if self.storage.exists(tool_name) or tool_name in self.registry.tools:
            error_msg = f"Tool '{tool_name}' already exists. Use a different name or delete the existing one first using delete_tool."
            audit.log_generation_complete(
                tool_name=tool_name,
                success=False,
                errors=[error_msg],
            )
            return ToolResult(
                name=self.name,
                success=False,
                result=None,
                error=error_msg,
            )

        try:
            # Check if we've reached the dynamic tools limit
            limit_reached, current = self.storage.check_limit_reached()
            if limit_reached:
                self.storage.get_available_slots()
                error_msg = (
                    f"Maximum number of dynamic tools ({self.storage.max_dynamic_tools}) reached. "
                    f"Current count: {current}. "
                    f"Please delete some dynamic tools using delete_tool before creating new ones."
                )
                audit.log_generation_complete(
                    tool_name=tool_name,
                    success=False,
                    errors=[error_msg],
                )
                audit.log_error(
                    error_type="generation_limit_reached",
                    message=error_msg,
                    tool_name=tool_name,
                )
                return ToolResult(
                    name=self.name,
                    success=False,
                    result=None,
                    error=error_msg,
                )

            # Generate the tool code
            code = self.generator.generate(
                name=tool_name,
                description=description,
                parameters=parameters,
                implementation=implementation,
                template=template,
                extra_imports=extra_imports,
            )

            # Security check already passed in generate, get details
            from internal.agent.tool.dynamic.sandbox import ToolCodeSandbox
            sandbox = ToolCodeSandbox()
            is_safe, violations = sandbox.analyze(code)

            # Prepare metadata
            metadata = {
                "description": description,
                "generated_at": self._get_timestamp(),
                "source": "dynamic_generation",
                "template": template,
            }

            # Create, validate, save, and register through existing infrastructure
            tool = self.registry.create_and_register_dynamic_tool(
                name=tool_name,
                code=code,
                storage=self.storage,
                metadata=metadata,
            )

            # Audit log successful generation
            audit.log_generation_complete(
                tool_name=tool_name,
                success=True,
                code=code,
                security_passed=is_safe,
                security_violations=[v.message for v in violations] if violations else None,
            )

            # Audit log successful registration
            audit.log_registration(tool_name=tool_name, success=True)

            # Run ruff check on the generated file
            ruff_passed, ruff_output = self._run_ruff_check(tool_name)

            # Truncate code for display
            code_preview = self._truncate_code(code)

            logger.info(f"Successfully generated and registered dynamic tool: {tool_name}")

            return ToolResult(
                name=self.name,
                success=True,
                result={
                    "message": f"Tool '{tool_name}' generated and registered successfully",
                    "tool_name": tool_name,
                    "tool_class": tool.__class__.__name__,
                    "code_preview": code_preview,
                    "total_lines": len(code.strip().split("\n")),
                    "ruff_check_passed": ruff_passed,
                    "ruff_output": ruff_output,
                },
                error=None,
            )

        except ToolGenerationError as e:
            error_msg = str(e)
            logger.warning(f"Tool generation failed for '{tool_name}': {error_msg}")
            audit.log_generation_complete(
                tool_name=tool_name,
                success=False,
                errors=[error_msg],
            )
            audit.log_error(
                error_type="generation_failure",
                message=error_msg,
                tool_name=tool_name,
            )
            return ToolResult(
                name=self.name,
                success=False,
                result=None,
                error=f"Tool generation failed: {error_msg}",
            )
        except Exception as e:
            import traceback
            error_msg = str(e)
            tb_str = traceback.format_exc()
            logger.error(f"Unexpected error generating tool '{tool_name}': {error_msg}", exc_info=True)
            audit.log_generation_complete(
                tool_name=tool_name,
                success=False,
                errors=[error_msg],
            )
            audit.log_error(
                error_type="unexpected_exception",
                message=error_msg,
                tool_name=tool_name,
                exception=tb_str,
            )
            return ToolResult(
                name=self.name,
                success=False,
                result=None,
                error=f"Unexpected error during tool generation: {error_msg}",
            )

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now().isoformat()

    def _truncate_code(self, code: str, max_lines: int = 30) -> str:
        """Truncate code to max lines for preview."""
        lines = code.strip().split("\n")
        if len(lines) <= max_lines:
            return code
        return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"

    def _run_ruff_check(self, tool_name: str) -> tuple[bool, str]:
        """Run ruff check on the generated tool file.

        Returns:
            (passed: bool, output: str)
        """
        import subprocess
        import sys

        tool_path = self.storage.storage_path / f"{tool_name}_tool.py"
        if not tool_path.exists():
            return False, "Generated file not found"

        try:
            result = subprocess.run(
                [sys.executable, "-m", "ruff", "check", str(tool_path)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode == 0:
                return True, "No issues found"
            output = result.stdout.strip() + "\n" + result.stderr.strip()
            return False, output.strip()
        except Exception as e:
            return False, f"Failed to run ruff check: {str(e)}"
