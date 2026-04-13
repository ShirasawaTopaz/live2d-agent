import asyncio
import logging
from typing import Type, Optional
from typing_extensions import Any
from internal.agent.tool.base import Tool
from internal.agent.tool.dynamic.storage import DynamicToolStorage
from internal.agent.tool.dynamic.generator import ToolGenerator, ToolGenerationError

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self) -> None:
        self.is_none: bool = True
        self.tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self.tools[tool.name] = tool
        if self.is_none:
            self.is_none = False

    def register_dynamic_tool(self, tool_class: Type[Tool]) -> Tool:
        """Register a dynamically loaded tool class.

        Args:
            tool_class: The tool class (not instance) loaded dynamically

        Returns:
            The created and registered tool instance
        """
        tool = tool_class()
        self.register(tool)
        return tool

    def unregister_dynamic_tool(self, name: str) -> bool:
        """Unregister a dynamic tool by name.

        Args:
            name: The name of the dynamic tool to unregister

        Returns:
            True if the tool was found and removed, False otherwise
        """
        return self.unregister(name)

    def create_and_register_dynamic_tool(
        self,
        name: str,
        code: str,
        storage: DynamicToolStorage,
        metadata: Optional[dict] = None
    ) -> Tool:
        """Create a new dynamic tool from code and register it.

        Args:
            name: Tool name
            code: The Python code implementing the tool
            storage: The DynamicToolStorage instance to use for persistence
            metadata: Optional metadata to store with the tool

        Returns:
            The created and registered tool instance

        Raises:
            ToolGenerationError: If code validation fails
        """
        # Validate the code security
        generator = ToolGenerator()
        is_valid, errors = generator.validate(code)
        if not is_valid:
            error_msg = "; ".join(errors) if errors else "Security validation failed"
            raise ToolGenerationError(error_msg)

        # Save to persistent storage
        storage.save(name, code, metadata)

        # Load the module and get the tool class
        loaded_class = storage.load(name)
        if loaded_class is None:
            raise ToolGenerationError(f"Failed to load tool '{name}' after saving")

        # Register and return
        return self.register_dynamic_tool(loaded_class)

    def load_all_dynamic_tools(self, storage: DynamicToolStorage) -> int:
        """Load all persisted dynamic tools from storage and register them.

        This should be called on application startup to load all previously
        created dynamic tools.

        Args:
            storage: The DynamicToolStorage instance containing persisted tools

        Returns:
            Number of tools successfully loaded
        """
        loaded_count = 0
        for tool_name in storage.index.keys():
            try:
                tool_class = storage.load(tool_name)
                if tool_class is not None:
                    self.register_dynamic_tool(tool_class)
                    loaded_count += 1
                    logger.info(f"Loaded dynamic tool: {tool_name}")
                else:
                    logger.error(f"Failed to load dynamic tool '{tool_name}': returned None")
            except Exception as e:
                logger.error(f"Failed to load dynamic tool '{tool_name}': {e}")
                continue
        return loaded_count

    def get_definitions(self) -> list[dict]:
        # 确保生成符合OPENAI tool_calls格式的定义
        definitions = []
        for tool in self.tools.values():
            definition = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            definitions.append(definition)
        return definitions

    def execute(self, name: str, args: dict) -> Any:
        coro = self.tools[name].execute(**args)
        try:
            loop = asyncio.get_running_loop()
            return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)

    def unregister(self, name: str) -> bool:
        """Unregister a tool by name.

        Args:
            name: The name of the tool to unregister

        Returns:
            True if the tool was found and removed, False otherwise
        """
        if name in self.tools:
            del self.tools[name]
            if not self.tools:
                self.is_none = True
            return True
        return False
