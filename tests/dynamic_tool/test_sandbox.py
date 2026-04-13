"""Unit tests for ToolCodeSandbox security detection."""

from internal.agent.tool.dynamic.sandbox import ToolCodeSandbox, SecurityViolation, quick_check


class TestToolCodeSandbox:
    """Test cases for ToolCodeSandbox security analysis."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.sandbox = ToolCodeSandbox()

    def test_accept_valid_code(self):
        """Test that valid, safe code passes the check."""
        code = '''"""A safe tool."""
import json
import math
from collections import defaultdict
from internal.agent.tool.base import Tool

class SafeTool(Tool):
    @property
    def name(self) -> str:
        return "safe_tool"
    
    @property
    def description(self) -> str:
        return "A safe tool that does math"
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"},
            },
            "required": ["x", "y"],
        }
    
    async def execute(self, x, y):
        """Calculate hypotenuse."""
        return math.sqrt(x**2 + y**2)
'''
        is_safe, violations = self.sandbox.analyze(code)
        assert is_safe
        assert len(violations) == 0

    def test_reject_syntax_error(self):
        """Test that code with syntax errors is rejected."""
        bad_code = '''This is not valid Python code
class BrokenTool:
    def execute(
        missing closing parenthesis
'''
        is_safe, violations = self.sandbox.analyze(bad_code)
        assert not is_safe
        assert len(violations) == 1
        assert "Syntax error" in violations[0].message

    def test_reject_forbidden_modules_os(self):
        """Test that importing os module is rejected."""
        code = '''import os
from internal.agent.tool.base import Tool

class BadTool(Tool):
    async def execute(self):
        return os.listdir('/')
'''
        is_safe, violations = self.sandbox.analyze(code)
        assert not is_safe
        assert any("Forbidden module: os" in v.message for v in violations)

    def test_reject_forbidden_modules_subprocess(self):
        """Test that importing subprocess is rejected."""
        code = '''import subprocess
from internal.agent.tool.base import Tool

class BadTool(Tool):
    async def execute(self):
        return subprocess.run(['echo', 'hi'])
'''
        is_safe, violations = self.sandbox.analyze(code)
        assert not is_safe
        assert any("Forbidden module: subprocess" in v.message for v in violations)

    def test_allow_allowed_modules_submodule(self):
        """Test that allowed submodules like urllib.request are allowed."""
        code = '''import urllib.request
from internal.agent.tool.base import Tool

class GoodTool(Tool):
    async def execute(self, url):
        return urllib.request.urlopen(url).read()
'''
        is_safe, violations = self.sandbox.analyze(code)
        # urllib is root module, which is in ALLOWED_MODULES per security.py
        assert is_safe
        assert len(violations) == 0

    def test_reject_untrusted_non_whitelist_modules(self):
        """Test that modules not in whitelist are rejected."""
        code = '''import numpy
from internal.agent.tool.base import Tool

class BadTool(Tool):
    async def execute(self):
        return numpy.array([1, 2, 3])
'''
        is_safe, violations = self.sandbox.analyze(code)
        assert not is_safe
        assert any("Untrusted module: numpy" in v.message for v in violations)

    def test_reject_direct_eval_call(self):
        """Test that direct calls to eval are rejected."""
        code = '''from internal.agent.tool.base import Tool

class BadTool(Tool):
    async def execute(self, code):
        return eval(code)
'''
        is_safe, violations = self.sandbox.analyze(code)
        assert not is_safe
        assert any("Call to forbidden function: eval" in v.message for v in violations)

    def test_reject_direct_exec_call(self):
        """Test that direct calls to exec are rejected."""
        code = '''from internal.agent.tool.base import Tool

class BadTool(Tool):
    async def execute(self, code):
        exec(code)
'''
        is_safe, violations = self.sandbox.analyze(code)
        assert not is_safe
        assert any("Call to forbidden function: exec" in v.message for v in violations)

    def test_reject_access_to___import__(self):
        """Test that access to __import__ is detected."""
        code = '''from internal.agent.tool.base import Tool

class BadTool(Tool):
    async def execute(self):
        importer = __import__
        os = importer('os')
'''
        is_safe, violations = self.sandbox.analyze(code)
        assert not is_safe
        assert any("Forbidden builtin: __import__" in v.message for v in violations)

    def test_reject_eval_as_attribute_access(self):
        """Test that eval accessed as attribute is detected."""
        code = '''from internal.agent.tool.base import Tool

class BadTool(Tool):
    def eval(self, code):
        return compile(code, '<string>', 'exec')
        
    async def execute(self, code):
        return self.eval(code)
    '''
        is_safe, violations = self.sandbox.analyze(code)
        assert not is_safe
        assert any("Access to forbidden attribute: eval" in v.message for v in violations)

    def test_reject_multiple_violations(self):
        """Test that multiple violations are all detected."""
        code = '''import os
import subprocess
from internal.agent.tool.base import Tool

class BadTool(Tool):
    async def execute(self, code):
        return eval(code)
'''
        is_safe, violations = self.sandbox.analyze(code)
        assert not is_safe
        assert len(violations) >= 3
        # Should find all three violations
        found_forbidden_module = any("Forbidden module: os" in v.message for v in violations)
        found_forbidden_module2 = any("Forbidden module: subprocess" in v.message for v in violations)
        found_forbidden_func = any("Call to forbidden function: eval" in v.message for v in violations)
        assert found_forbidden_module
        assert found_forbidden_module2
        assert found_forbidden_func

    def test_accept_empty_code(self):
        """Test empty file - actually shouldn't happen in practice."""
        is_safe, violations = self.sandbox.analyze("")
        # Empty is technically valid syntax
        assert is_safe

    def test_import_from_forbidden(self):
        """Test ImportFrom of forbidden module."""
        code = '''from os import path
from internal.agent.tool.base import Tool

class BadTool(Tool):
    async def execute(self):
        return path.exists('/')
'''
        is_safe, violations = self.sandbox.analyze(code)
        assert not is_safe
        assert any("Forbidden module: os" in v.message for v in violations)


class TestQuickCheck:
    """Test the quick_check helper function."""

    def test_quick_check_safe(self):
        """Test quick_check returns True for safe code."""
        code = '''import math
result = math.sqrt(16)
'''
        assert quick_check(code) is True

    def test_quick_check_unsafe(self):
        """Test quick_check returns False for unsafe code."""
        code = '''import os
result = os.listdir('.')
'''
        assert quick_check(code) is False


class TestSecurityViolation:
    """Test SecurityViolation exception class."""

    def test_with_line_number(self):
        """Test SecurityViolation with line number."""
        exc = SecurityViolation("Test message", 42)
        assert "Line 42: Test message" in str(exc)
        assert exc.line == 42

    def test_without_line_number(self):
        """Test SecurityViolation without line number."""
        exc = SecurityViolation("Test message")
        assert "Test message" in str(exc)
        assert exc.line is None
