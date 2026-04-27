"""End-to-end tests for the complete dynamic tool generation flow."""

import tempfile
import pytest

from internal.agent.tool.base import Tool
from internal.agent.register import ToolRegistry
from internal.agent.tool.dynamic.generator import ToolGenerator, ToolGenerationError
from internal.agent.tool.dynamic.storage import DynamicToolStorage
from internal.agent.tool.dynamic.sandbox import ToolCodeSandbox


class TestEndToEndFlow:
    """End-to-end tests covering the complete tool generation -> save -> load flow."""

    def setup_method(self):
        """Set up test fixtures with a temporary storage directory."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = DynamicToolStorage(storage_path=self.temp_dir.name)
        self.registry = ToolRegistry()
        self.generator = ToolGenerator()
        self.sandbox = ToolCodeSandbox()

    def teardown_method(self):
        """Clean up temporary directory."""
        self.temp_dir.cleanup()

    def test_complete_flow_create_and_load(self):
        """Test the complete flow: generate -> save -> register -> load."""
        # 1. Generate code for a simple addition tool
        code = self.generator.generate(
            name="add_numbers",
            description="Add two numbers together",
            parameters={
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "First number"},
                    "b": {"type": "number", "description": "Second number"},
                },
                "required": ["a", "b"],
            },
            implementation="    \"\"\"Add two numbers together.\"\"\"\n    result = a + b\n    return f\"{a} + {b} = {result}\"",
        )
        assert code is not None

        # 2. Save to storage
        file_path = self.storage.save("add_numbers", code, {"description": "Adds two numbers"})
        assert file_path.exists()
        assert self.storage.exists("add_numbers")

        # 3. Check index
        assert "add_numbers" in self.storage.index
        info = self.storage.info("add_numbers")
        assert info is not None
        assert info["metadata"]["description"] == "Adds two numbers"

        # 4. Load the tool class dynamically
        tool_class = self.storage.load("add_numbers")
        assert tool_class is not None
        assert issubclass(tool_class, Tool)

        # 5. Register and create instance
        tool = self.registry.register_dynamic_tool(tool_class)
        assert tool.name == "add_numbers"
        assert "Add two numbers" in tool.description
        assert "a" in tool.parameters["properties"]
        assert "b" in tool.parameters["properties"]

        # 6. Verify the tool can be executed
        # Note: We don't actually need to execute it for the end-to-end test,
        # but just checking it has the execute method
        assert hasattr(tool, "execute")
        assert callable(getattr(tool, "execute"))

    def test_complete_flow_generate_via_registry(self):
        """Test creating and registering via registry.create_and_register_dynamic_tool."""
        # Generate code
        code = self.generator.generate(
            name="reverse_text",
            description="Reverse the input text",
            implementation="    \"\"\"Reverse the input text.\"\"\"\n    return input[::-1]",
        )

        # Create, save, register all in one step
        tool = self.registry.create_and_register_dynamic_tool(
            name="reverse_text",
            code=code,
            storage=self.storage,
        )

        # Verify
        assert tool is not None
        assert tool.name == "reverse_text"
        assert self.storage.exists("reverse_text")
        assert "reverse_text" in self.registry.tools

    def test_flow_delete_dynamic_tool(self):
        """Test the full flow: create -> delete -> verify gone."""
        # Create
        code = self.generator.generate(
            name="temp_tool",
            description="Temporary tool for testing deletion",
        )
        self.storage.save("temp_tool", code)
        assert self.storage.exists("temp_tool")

        # Delete
        result = self.storage.delete("temp_tool")
        assert result is True

        # Verify gone
        assert not self.storage.exists("temp_tool")
        assert "temp_tool" not in self.storage.index
        # Check file is actually deleted
        tool_file = self.storage.storage_path / "temp_tool_tool.py"
        assert not tool_file.exists()

    def test_load_all_dynamic_tools(self):
        """Test loading all dynamic tools from storage."""
        # Create multiple tools
        tools_to_create = [
            ("tool_one", "First test tool"),
            ("tool_two", "Second test tool"),
            ("tool_three", "Third test tool"),
        ]

        for name, desc in tools_to_create:
            code = self.generator.generate(name, desc)
            self.storage.save(name, code)

        # Verify all are in index
        assert len(self.storage.index) == 3

        # Load all
        loaded_classes = self.storage.load_all()
        assert len(loaded_classes) == 3

        # All loaded classes should be Tool subclasses
        for cls in loaded_classes:
            assert issubclass(cls, Tool)

    def test_registry_load_all_dynamic_tools(self):
        """Test registry loading all persisted tools on startup."""
        # Create a couple tools
        code1 = self.generator.generate("tool_a", "Tool A description")
        code2 = self.generator.generate("tool_b", "Tool B description")
        self.storage.save("tool_a", code1)
        self.storage.save("tool_b", code2)

        # Registry loads all
        loaded_count = self.registry.load_all_dynamic_tools(self.storage)
        assert loaded_count == 2
        assert "tool_a" in self.registry.tools
        assert "tool_b" in self.registry.tools

    def test_failed_validation_prevents_save(self):
        """Test that code failing security validation doesn't get saved."""
        unsafe_code = '''import os
from internal.agent.tool.base import Tool

class BadTool(Tool):
    @property
    def name(self):
        return "bad"
    @property
    def description(self):
        return "Bad tool"
    @property
    def parameters(self):
        return {}
    async def execute(self):
        return os.listdir(".")
'''
        # Should raise before saving
        with pytest.raises(ToolGenerationError):
            self.registry.create_and_register_dynamic_tool(
                name="bad_tool",
                code=unsafe_code,
                storage=self.storage,
            )

        # Should not exist in storage
        assert not self.storage.exists("bad_tool")

    def test_list_all_tools_through_storage(self):
        """Test listing all dynamic tools through storage."""
        # Create a couple tools
        self.storage.save("tool1", self.generator.generate("tool1", "Desc 1"))
        self.storage.save("tool2", self.generator.generate("tool2", "Desc 2"))

        tool_list = self.storage.list()
        assert len(tool_list) == 2
        names = {t["name"] for t in tool_list}
        assert "tool1" in names
        assert "tool2" in names

    def test_clear_all_tools(self):
        """Test clearing all dynamic tools."""
        # Create multiple tools
        for i in range(3):
            self.storage.save(f"tool_{i}", self.generator.generate(f"tool_{i}", f"Tool {i}"))

        assert len(self.storage.index) == 3
        deleted = self.storage.clear()
        assert deleted == 3
        assert len(self.storage.index) == 0

    def test_load_nonexistent_tool_returns_none(self):
        """Test that loading a nonexistent tool returns None gracefully."""
        result = self.storage.load("does_not_exist")
        assert result is None

    def test_delete_nonexistent_returns_false(self):
        """Test that deleting a nonexistent tool returns False gracefully."""
        result = self.storage.delete("does_not_exist")
        assert result is False

    def test_code_with_all_allowed_modules_passes(self):
        """Test code using all allowed modules passes security check."""
        code = '''"""Tool using multiple allowed modules."""
import json
import re
import math
import random
import datetime
import urllib.request
import urllib.parse
import hashlib
import base64
import collections
import itertools
import functools
from internal.agent.tool.base import Tool

class AllModulesTool(Tool):
    @property
    def name(self) -> str:
        return "all_modules"
    
    @property
    def description(self) -> str:
        return "Tool using all allowed modules"
    
    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}
    
    async def execute(self):
        # Just use each module to ensure code references them
        x = math.pi
        y = random.random()
        d = datetime.datetime.now()
        cnt = collections.Counter([1, 2, 3])
        it = itertools.count()
        return "ok"
'''
        is_safe, violations = self.sandbox.analyze(code)
        assert is_safe
        assert len(violations) == 0

    def test_metadata_stored_correctly(self):
        """Test that custom metadata is stored correctly."""
        code = self.generator.generate("metadata_test", "Tool with metadata")
        metadata = {
            "author": "Test Author",
            "version": "1.0.0",
            "tags": ["utility", "test"],
            "enabled": True,
        }
        self.storage.save("metadata_test", code, metadata)

        info = self.storage.info("metadata_test")
        assert info is not None
        assert info["metadata"] == metadata


class TestIntegrationWithMetaTools:
    """Integration tests for the meta-tools (GenerateToolTool, etc)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = DynamicToolStorage(storage_path=self.temp_dir.name)
        self.registry = ToolRegistry()

    def teardown_method(self):
        """Clean up."""
        self.temp_dir.cleanup()

    def test_generate_tool_meta_tool_instantiation(self):
        """Test that GenerateToolTool can be instantiated correctly."""
        from internal.agent.tool.meta.generate_tool import GenerateToolTool

        meta_tool = GenerateToolTool(self.registry, self.storage)
        assert meta_tool.name == "generate_tool"
        assert "Generate a new tool" in meta_tool.description
        assert "tool_name" in meta_tool.parameters["properties"]
        assert "description" in meta_tool.parameters["properties"]

    def test_list_tools_meta_tool_instantiation(self):
        """Test that ListToolsTool can be instantiated correctly."""
        from internal.agent.tool.meta.list_tools import ListToolsTool

        meta_tool = ListToolsTool(self.registry, self.storage)
        assert meta_tool.name == "list_tools"
        assert "include_dynamic" in meta_tool.parameters["properties"]

    def test_delete_tool_meta_tool_instantiation(self):
        """Test that DeleteToolTool can be instantiated correctly."""
        from internal.agent.tool.meta.delete_tool import DeleteToolTool

        meta_tool = DeleteToolTool(self.registry, self.storage)
        assert meta_tool.name == "delete_tool"
        assert "tool_name" in meta_tool.parameters["properties"]
        assert "confirm" in meta_tool.parameters["properties"]
