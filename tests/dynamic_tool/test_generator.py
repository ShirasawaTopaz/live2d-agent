"""Unit tests for ToolGenerator."""

import pytest
from internal.agent.tool.dynamic.generator import ToolGenerator, ToolGenerationError


class TestToolGenerator:
    """Test cases for ToolGenerator class."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.generator = ToolGenerator()

    def test_generate_simple_tool(self):
        """Test generating a simple tool with default parameters."""
        code = self.generator.generate(
            name="calculator",
            description="A simple calculator that adds two numbers",
            parameters={
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "First number"},
                    "b": {"type": "number", "description": "Second number"},
                },
                "required": ["a", "b"],
            },
            implementation="    result = a + b\n    return f\"The sum of {a} + {b} is {result}\"",
        )
        assert code is not None
        assert len(code) > 0
        assert "class Calculator(Tool)" in code
        assert "calculator" in code
        assert "A simple calculator that adds two numbers" in code
        # Check that security validation passed
        assert "result = a + b" in code

    def test_generate_with_default_parameters(self):
        """Test generating with default parameters (single input)."""
        code = self.generator.generate(
            name="reverse_string",
            description="Reverse a given input string",
        )
        assert '"input": {' in code
        assert '"type": "string"' in code

    def test_generate_with_extra_imports(self):
        """Test generating with extra allowed imports."""
        code = self.generator.generate(
            name="json_parser",
            description="Parse JSON string",
            extra_imports=["json"],
            implementation="    return json.loads(input)",
        )
        assert "import json" in code
        assert "json_parser" in code

    def test_generate_with_extra_imports_forbidden(self):
        """Test that forbidden extra imports are rejected."""
        with pytest.raises(ToolGenerationError) as exc_info:
            self.generator.generate(
                name="os_tool",
                description="Try to import os",
                extra_imports=["os"],
            )
        assert "Unauthorized import: os" in str(exc_info.value)

    def test_invalid_tool_name(self):
        """Test that invalid tool names are rejected."""
        with pytest.raises(ToolGenerationError):
            self.generator.generate(
                name="123invalid",  # Can't start with number
                description="Invalid name tool",
            )

        with pytest.raises(ToolGenerationError):
            self.generator.generate(
                name="invalid-name",  # Contains hyphen
                description="Invalid name tool",
            )

    def test_validate_valid_code(self):
        """Test validation of valid code."""
        valid_code = '''"""Test tool."""
import math
from internal.agent.tool.base import Tool

class TestTool(Tool):
    @property
    def name(self) -> str:
        return "test"
    
    @property
    def description(self) -> str:
        return "Test tool"
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "number", "description": "Number"},
            },
            "required": ["x"],
        }
    
    async def execute(self, x):
        return math.sqrt(x)
'''
        is_valid, errors = self.generator.validate(valid_code)
        assert is_valid
        assert errors is None

    def test_validate_invalid_code(self):
        """Test validation of code containing forbidden operations."""
        invalid_code = '''"""Bad tool."""
import os
from internal.agent.tool.base import Tool

class BadTool(Tool):
    @property
    def name(self) -> str:
        return "bad"
    
    @property
    def description(self) -> str:
        return "Bad tool"
    
    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}
    
    async def execute(self):
        return eval("print('hello')")
'''
        is_valid, errors = self.generator.validate(invalid_code)
        assert not is_valid
        assert len(errors) > 0
        assert any("Forbidden module: os" in err for err in errors)
        assert any("Forbidden builtin: eval" in err for err in errors)

    def test_to_pascal_case_conversion(self):
        """Test that snake_case to PascalCase conversion works."""
        from internal.agent.tool.dynamic.templates import to_pascal_case

        assert to_pascal_case("hello_world") == "HelloWorld"
        assert to_pascal_case("test_tool") == "TestTool"
        assert to_pascal_case("simple") == "Simple"
        assert to_pascal_case("my_awesome_tool") == "MyAwesomeTool"

    def test_to_snake_case_conversion(self):
        """Test that PascalCase to snake_case conversion works."""
        from internal.agent.tool.dynamic.templates import to_snake_case

        assert to_snake_case("HelloWorld") == "hello_world"
        assert to_snake_case("TestTool") == "test_tool"
        assert to_snake_case("Simple") == "simple"
        assert to_snake_case("MyAwesomeTool") == "my_awesome_tool"

    def test_generate_with_template(self):
        """Test generating using a named template."""
        from internal.agent.tool.dynamic.templates import IMPLEMENTATION_TEMPLATES

        assert "simple" in IMPLEMENTATION_TEMPLATES
        code = self.generator.generate(
            name="simple_calc",
            description="Simple calculation",
            template="calc",
        )
        assert code is not None
        assert len(code) > 0


class TestGenerateToolCodeHelper:
    """Test the generate_tool_code helper function."""

    def test_generate_tool_code_helper(self):
        """Test that the helper function works correctly."""
        from internal.agent.tool.dynamic.generator import generate_tool_code

        code = generate_tool_code(
            name="helper_test",
            description="Test helper function",
        )
        assert "class HelperTest(Tool)" in code
        assert "helper_test" in code
