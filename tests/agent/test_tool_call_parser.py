import pytest
import json
from internal.agent.response import ToolCallParser


class TestToolCallParser:
    def test_parse_valid_json_in_fence(self):
        """Test that tool call in markdown code fence is parsed correctly"""
        text = """
Here's the tool call I need to make:
```json
{
  "name": "file",
  "arguments": {
    "action": "read",
    "path": "README.md"
  }
}
```
"""
        result = ToolCallParser.extract_tool_calls_from_text(text)
        assert result is not None
        assert len(result) == 1
        assert result[0]["function"]["name"] == "file"
        assert result[0]["function"]["arguments"]["action"] == "read"
        assert result[0]["function"]["arguments"]["path"] == "README.md"

    def test_parse_valid_tool_call_in_tags(self):
        """Test that tool call in <tool_call> tags is parsed correctly"""
        text = "<tool_call>{\"name\": \"display_bubble_text\", \"arguments\": {\"text\": \"Hello world\"}}</tool_call>"
        
        result = ToolCallParser.extract_tool_calls_from_text(text)
        assert result is not None
        assert len(result) == 1
        assert result[0]["function"]["name"] == "display_bubble_text"
        assert result[0]["function"]["arguments"]["text"] == "Hello world"

    def test_parse_incomplete_json_recovery(self):
        """Test that slightly incomplete JSON is recovered with bracket fixing"""
        # Missing closing bracket at the end
        text = "<tool_call>{\"name\": \"file\", \"arguments\": {\"action\": \"read\", \"path\": \"test.txt\""
        
        result = ToolCallParser.extract_tool_calls_from_text(text)
        assert result is not None
        assert len(result) == 1
        assert result[0]["function"]["name"] == "file"

    def test_parse_multiple_tool_calls(self):
        """Test that multiple tool calls in one response are parsed"""
        text = """
<tool_call>
{
  "name": "tool1",
  "arguments": {"param1": "value1"}
}
</tool_call>

<tool_call>
{
  "name": "tool2", 
  "arguments": {"param2": "value2"}
}
</tool_call>
"""
        result = ToolCallParser.extract_tool_calls_from_text(text)
        assert result is not None
        assert len(result) == 2
        names = [tc["function"]["name"] for tc in result]
        assert "tool1" in names
        assert "tool2" in names

    def test_parse_completely_invalid_returns_none(self):
        """Test that completely garbage input returns empty list not exception"""
        text = "This is just some random text with no tool call at all."
        
        result = ToolCallParser.extract_tool_calls_from_text(text)
        assert result is None or len(result) == 0

    def test_parse_extra_whitespace_handled(self):
        """Test that extra whitespace and newlines don't break parsing"""
        text = """

<tool_call>

{

"name" : "test_tool" ,

"arguments" : {

"param" : "value with spaces"

}

}

</tool_call>

"""
        result = ToolCallParser.extract_tool_calls_from_text(text)
        assert result is not None
        assert len(result) == 1
        assert result[0]["function"]["name"] == "test_tool"
        assert result[0]["function"]["arguments"]["param"] == "value with spaces"

    def test_trailing_comma_fixed(self):
        """Test that trailing commas in JSON are fixed"""
        text = """<tool_call>{
            "name": "test",
            "arguments": {
                "param1": "value1",
                "param2": "value2",
            }
        }</tool_call>"""
        
        result = ToolCallParser.extract_tool_calls_from_text(text)
        assert result is not None
        assert len(result) == 1
        # Should be parsed successfully despite trailing comma
        assert result[0]["function"]["name"] == "test"

    def test_standalone_json_extracted(self):
        """Test that standalone JSON object with tool call is extracted"""
        text = """Okay, let me call this tool:
{
  "name": "web_search",
  "arguments": {
    "query": "python programming"
  }
}
That should give me the information I need.
"""
        result = ToolCallParser.extract_tool_calls_from_text(text)
        assert result is not None
        assert len(result) == 1
        assert result[0]["function"]["name"] == "web_search"

    def test_multiple_code_fences(self):
        """Test that multiple tool calls in multiple code fences are parsed"""
        text = """
First tool call:
```json
{
  "name": "first",
  "arguments": {}
}
```

Second tool call:
```json
{
  "name": "second",
  "arguments": {}
}
```
"""
        result = ToolCallParser.extract_tool_calls_from_text(text)
        assert len(result) == 2
        names = [tc["function"]["name"] for tc in result]
        assert "first" in names
        assert "second" in names
