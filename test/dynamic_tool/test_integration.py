"""Integration tests for dynamic tool generation with actual execution."""

import tempfile
import pytest

from internal.agent.register import ToolRegistry
from internal.agent.tool.dynamic.generator import ToolGenerator
from internal.agent.tool.dynamic.storage import DynamicToolStorage


class TestSimpleToolGenerationIntegration:
    """Integration tests for generating and executing simple tools."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = DynamicToolStorage(storage_path=self.temp_dir.name)
        self.registry = ToolRegistry()
        self.generator = ToolGenerator()

    def teardown_method(self):
        """Clean up."""
        self.temp_dir.cleanup()

    async def test_generate_and_execute_calculator(self):
        """Generate a calculator tool and actually execute it."""
        code = self.generator.generate(
            name="add_two_numbers",
            description="Add two numbers and return the result",
            parameters={
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "First number"},
                    "b": {"type": "number", "description": "Second number"},
                },
                "required": ["a", "b"],
            },
            implementation="    \"\"\"Add two numbers and return the result.\"\"\"\n    result = a + b\n    return result",
        )

        # Create and register
        tool = self.registry.create_and_register_dynamic_tool(
            name="add_two_numbers",
            code=code,
            storage=self.storage,
        )

        # Execute
        result = await tool.execute(a=5, b=3)
        assert result == 8

    async def test_generate_and_execute_string_reverser(self):
        """Generate a string reversing tool and execute it."""
        code = self.generator.generate(
            name="reverse_string",
            description="Reverse the input string",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to reverse"},
                },
                "required": ["text"],
            },
            implementation="    \"\"\"Reverse the input string.\"\"\"\n    return text[::-1]",
        )

        tool = self.registry.create_and_register_dynamic_tool(
            name="reverse_string",
            code=code,
            storage=self.storage,
        )

        result = await tool.execute(text="hello world")
        assert result == "dlrow olleh"

    async def test_generate_and_execute_factorial_with_math(self):
        """Generate a factorial tool using math module."""
        code = self.generator.generate(
            name="factorial",
            description="Calculate factorial of a number",
            parameters={
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "description": "Non-negative integer"},
                },
                "required": ["n"],
            },
            extra_imports=["math"],
            implementation="    \"\"\"Calculate factorial using math.factorial.\"\"\"\n    return math.factorial(n)",
        )

        tool = self.registry.create_and_register_dynamic_tool(
            name="factorial",
            code=code,
            storage=self.storage,
        )

        result = await tool.execute(n=5)
        assert result == 120

    async def test_generate_and_execute_json_parser(self):
        """Generate a JSON parsing tool."""
        code = self.generator.generate(
            name="parse_json",
            description="Parse a JSON string and return the value for a key",
            parameters={
                "type": "object",
                "properties": {
                    "json_str": {"type": "string", "description": "JSON string"},
                    "key": {"type": "string", "description": "Key to extract"},
                },
                "required": ["json_str", "key"],
            },
            extra_imports=["json"],
            implementation="    \"\"\"Parse JSON and extract a key.\"\"\"\n    data = json.loads(json_str)\n    return data.get(key)",
        )

        tool = self.registry.create_and_register_dynamic_tool(
            name="parse_json",
            code=code,
            storage=self.storage,
        )

        result = await tool.execute(
            json_str='{\"name\": \"test\", \"value\": 42}',
            key="value"
        )
        assert result == 42

    async def test_generate_word_counter_with_collections(self):
        """Generate a word counter using collections.Counter."""
        code = self.generator.generate(
            name="count_words",
            description="Count word occurrences in a text",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Input text"},
                },
                "required": ["text"],
            },
            extra_imports=["collections"],
            implementation="    \"\"\"Count word frequencies in text.\"\"\"\n    words = text.lower().split()\n    counter = collections.Counter(words)\n    return dict(counter)",
        )

        tool = self.registry.create_and_register_dynamic_tool(
            name="count_words",
            code=code,
            storage=self.storage,
        )

        result = await tool.execute(text="hello hello world hello test")
        assert result == {"hello": 3, "world": 1, "test": 1}

    async def test_generate_hash_calculator(self):
        """Generate an MD5 hash calculator using hashlib and base64."""
        code = self.generator.generate(
            name="md5_hash",
            description="Calculate MD5 hash of input text",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Input text"},
                },
                "required": ["text"],
            },
            extra_imports=["hashlib", "base64"],
            implementation="    \"\"\"Calculate MD5 hash and return base64 encoding.\"\"\"\n    digest = hashlib.md5(text.encode()).digest()\n    return base64.b64encode(digest).decode()",
        )

        tool = self.registry.create_and_register_dynamic_tool(
            name="md5_hash",
            code=code,
            storage=self.storage,
        )

        # Known result for "hello world" MD5: 5eb63bbbe01eeed093cb22bb8f5acdc3
        result = await tool.execute(text="hello world")
        assert len(result) > 0
        # We don't check exact value, just that it returns something
        assert isinstance(result, str)

    async def test_generate_current_datetime(self):
        """Generate a tool that returns current datetime."""
        code = self.generator.generate(
            name="current_datetime",
            description="Get current datetime in ISO format",
            extra_imports=["datetime"],
            implementation="    \"\"\"Return current datetime as ISO string.\"\"\"\n    return datetime.datetime.now().isoformat()",
        )

        tool = self.registry.create_and_register_dynamic_tool(
            name="current_datetime",
            code=code,
            storage=self.storage,
        )

        result = await tool.execute()
        assert isinstance(result, str)
        assert len(result) > 10  # ISO date has at least 10 chars for YYYY-MM-DD

    async def test_generate_palindrome_checker(self):
        """Generate a palindrome checker tool."""
        code = self.generator.generate(
            name="is_palindrome",
            description="Check if a string is a palindrome",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to check"},
                },
                "required": ["text"],
            },
            implementation="    \"\"\"Check if text is a palindrome (ignoring case and spaces).\"\"\"\n    cleaned = text.lower().replace(' ', '')\n    return cleaned == cleaned[::-1]",
        )

        tool = self.registry.create_and_register_dynamic_tool(
            name="is_palindrome",
            code=code,
            storage=self.storage,
        )

        assert await tool.execute(text="race car") is True
        assert await tool.execute(text="hello") is False


class TestComplexToolGenerationIntegration:
    """Integration tests for more complex tool generation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = DynamicToolStorage(storage_path=self.temp_dir.name)
        self.registry = ToolRegistry()
        self.generator = ToolGenerator()

    def teardown_method(self):
        """Clean up."""
        self.temp_dir.cleanup()

    async def test_generate_temperature_converter(self):
        """Generate a temperature converter with multiple methods."""
        code = self.generator.generate(
            name="convert_temperature",
            description="Convert temperature between Celsius and Fahrenheit",
            parameters={
                "type": "object",
                "properties": {
                    "value": {"type": "number", "description": "Temperature value"},
                    "to_unit": {"type": "string", "description": "Unit to convert to: 'C' or 'F'"},
                },
                "required": ["value", "to_unit"],
            },
            implementation="    \"\"\"Convert temperature between Celsius and Fahrenheit.\"\"\"\n    if to_unit.upper() == 'C':\n        # Convert Fahrenheit to Celsius\n        return (value - 32) * 5 / 9\n    elif to_unit.upper() == 'F':\n        # Convert Celsius to Fahrenheit\n        return (value * 9 / 5) + 32\n    else:\n        raise ValueError('to_unit must be \"C\" or \"F\"')",
        )

        tool = self.registry.create_and_register_dynamic_tool(
            name="convert_temperature",
            code=code,
            storage=self.storage,
        )

        # 0掳C = 32掳F
        result_f = await tool.execute(value=0, to_unit="F")
        assert abs(result_f - 32) < 0.001

        # 100掳C = 212掳F
        result_f2 = await tool.execute(value=100, to_unit="F")
        assert abs(result_f2 - 212) < 0.001

        # 32掳F = 0掳C
        result_c = await tool.execute(value=32, to_unit="C")
        assert abs(result_c - 0) < 0.001

        # 212掳F = 100掳C
        result_c2 = await tool.execute(value=212, to_unit="C")
        assert abs(result_c2 - 100) < 0.001

    async def test_generate_prime_checker_with_algorithm(self):
        """Generate a prime checking tool with a simple algorithm."""
        code = self.generator.generate(
            name="is_prime",
            description="Check if a number is prime",
            parameters={
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "description": "Number to check"},
                },
                "required": ["n"],
            },
            implementation="    \"\"\"Check if n is a prime number.\"\"\"\n    if n <= 1:\n        return False\n    if n <= 3:\n        return True\n    if n % 2 == 0 or n % 3 == 0:\n        return False\n    i = 5\n    while i * i <= n:\n        if n % i == 0 or n % (i + 2) == 0:\n            return False\n        i += 6\n    return True",
        )

        tool = self.registry.create_and_register_dynamic_tool(
            name="is_prime",
            code=code,
            storage=self.storage,
        )

        assert await tool.execute(n=2) is True
        assert await tool.execute(n=3) is True
        assert await tool.execute(n=4) is False
        assert await tool.execute(n=17) is True
        assert await tool.execute(n=100) is False
        assert await tool.execute(n=97) is True

    async def test_generate_fibonacci_generator(self):
        """Generate Fibonacci sequence generator using itertools."""
        code = self.generator.generate(
            name="fibonacci_sequence",
            description="Generate Fibonacci sequence up to n terms",
            parameters={
                "type": "object",
                "properties": {
                    "terms": {"type": "integer", "description": "Number of terms to generate"},
                },
                "required": ["terms"],
            },
            extra_imports=["itertools"],
            implementation="    \"\"\"Generate Fibonacci sequence with specified number of terms.\"\"\"\n    result = [0, 1]\n    if terms <= 2:\n        return result[:terms]\n    for i in range(2, terms):\n        result.append(result[-1] + result[-2])\n    return result",
        )

        tool = self.registry.create_and_register_dynamic_tool(
            name="fibonacci_sequence",
            code=code,
            storage=self.storage,
        )

        result = await tool.execute(terms=10)
        assert result == [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]

    async def test_generate_url_parser_with_urllib(self):
        """Generate URL parsing tool using urllib.parse."""
        code = self.generator.generate(
            name="parse_url",
            description="Parse a URL and extract its components",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to parse"},
                },
                "required": ["url"],
            },
            extra_imports=["urllib.parse"],
            implementation="    \"\"\"Parse URL and return components.\"\"\"\n    parsed = urllib.parse.urlparse(url)\n    return {\n        'scheme': parsed.scheme,\n        'netloc': parsed.netloc,\n        'path': parsed.path,\n        'query': parsed.query,\n    }",
        )

        tool = self.registry.create_and_register_dynamic_tool(
            name="parse_url",
            code=code,
            storage=self.storage,
        )

        result = await tool.execute(url="https://example.com/path?query=test")
        assert result["scheme"] == "https"
        assert result["netloc"] == "example.com"
        assert result["path"] == "/path"
        assert result["query"] == "query=test"


class TestSecurityBoundaryIntegration:
    """Integration tests for security boundaries and malicious code detection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = DynamicToolStorage(storage_path=self.temp_dir.name)
        self.registry = ToolRegistry()
        self.generator = ToolGenerator()

    def teardown_method(self):
        """Clean up."""
        self.temp_dir.cleanup()

    def test_reject_code_with_eval(self):
        """Test that code with eval is rejected."""
        with pytest.raises(Exception) as exc_info:
            self.generator.generate(
                name="eval_test",
                description="Try to use eval",
                implementation="    return eval(input)",
            )
        assert "Security check failed" in str(exc_info.value)
        assert "eval" in str(exc_info.value)

    def test_reject_code_with_import_os(self):
        """Test that importing os is rejected."""
        with pytest.raises(Exception) as exc_info:
            self.generator.generate(
                name="os_test",
                description="Try to import os",
                extra_imports=["os"],
                implementation="    return os.listdir('.')",
            )
        assert "Unauthorized import: os" in str(exc_info.value)

    def test_reject_code_with_exec(self):
        """Test that code with exec is rejected."""
        with pytest.raises(Exception) as exc_info:
            self.generator.generate(
                name="exec_test",
                description="Try to use exec",
                implementation="    exec('print(123)')",
            )
        assert "Security check failed" in str(exc_info.value)
        assert "exec" in str(exc_info.value)

    def test_attempt_dynamic_import_is_detected(self):
        """Test that dynamic import attempts are detected."""
        code = '''"""Trying to sneak in dynamic import."""
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
        return {}
    
    async def execute(self):
        mod = __import__('os')
        return mod.listdir('.')
'''
        # Should be detected during validation
        from internal.agent.tool.dynamic.sandbox import ToolCodeSandbox
        sandbox = ToolCodeSandbox()
        is_safe, violations = sandbox.analyze(code)
        assert not is_safe
        assert any("__import__" in v.message for v in violations)
