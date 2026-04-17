import json
import re
from typing import Any, List, Tuple, Optional
import uuid


class ToolCallParser:
    """tool_call响应解析 - enhanced with multi-format support and error recovery"""

    @staticmethod
    def parse_tool_calls(response_message: Any) -> list[dict] | None:
        """从模型响应中提取 tool_calls"""
        if isinstance(response_message, dict):
            # Already has parsed tool_calls
            if "tool_calls" in response_message:
                return response_message.get("tool_calls")
            # Check if content has tool call markup
            if "content" in response_message:
                content = response_message["content"]
                if isinstance(content, str):
                    extracted = ToolCallParser.extract_tool_calls_from_text(content)
                    if extracted:
                        return extracted
            return None
        # Handle ChatCompletionMessage object from OpenAI SDK
        if hasattr(response_message, "tool_calls"):
            if response_message.tool_calls is None:
                return None
            tool_calls = []
            for tc in response_message.tool_calls:
                if (
                    hasattr(tc, "id")
                    and hasattr(tc, "type")
                    and hasattr(tc, "function")
                ):
                    func = tc.function
                    tool_call_dict = {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": func.name if hasattr(func, "name") else "",
                            "arguments": func.arguments
                            if hasattr(func, "arguments")
                            else "{}",
                        },
                    }
                    tool_calls.append(tool_call_dict)
            return tool_calls if tool_calls else None
        # Handle plain text response that might contains tool call
        if isinstance(response_message, str):
            return ToolCallParser.extract_tool_calls_from_text(response_message)
        return None

    @staticmethod
    def extract_tool_calls_from_text(text: str) -> list[dict] | None:
        """Extract tool calls from plain text, handling multiple formats:
        1. <tool_call>{...}</tool_call>
        2. ```json\n{...}\n``` markdown code fence
        3. Various incomplete formats with recovery
        """
        tool_calls = []
        
        # 1. Try extract from markdown code fences first (common output format)
        code_fence_matches = re.findall(
            r"```(?:json)?\s*(\{.*?\})\s*```", 
            text, 
            re.DOTALL
        )
        for match in code_fence_matches:
            tool_call = ToolCallParser._try_parse_json(match.strip())
            if tool_call:
                tool_calls.append(ToolCallParser._normalize_tool_call(tool_call))
                
        # 2. Try all variants of <tool_call> tags
        if not tool_calls:
            # Pattern 1: <tool_call>...</tool_call> (complete)
            patterns = [
                r"<tool_call>(\{.*?\})</tool_call>",
                r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
                r"<tool_call>(\{.*?)>",  # incomplete closing tag
                r"<tool_call>\s*(\{.*)",  # no closing tag at all
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, text, re.DOTALL)
                for match in matches:
                    json_str = ToolCallParser._fix_incomplete_json(match.strip())
                    if not json_str:
                        continue
                    tool_call = ToolCallParser._try_parse_json(json_str)
                    if tool_call:
                        tool_calls.append(ToolCallParser._normalize_tool_call(tool_call))
                if tool_calls:
                    break
                        
        # 3. Try to find any standalone JSON objects that look like tool calls
        if not tool_calls:
            # Look for anything that has name/parameters or name/arguments
            potential_jsons = ToolCallParser._extract_potential_json_objects(text)
            for json_str in potential_jsons:
                if len(json_str) < 10:  # skip too small
                    continue
                tool_call = ToolCallParser._try_parse_json(json_str)
                if tool_call and ("name" in tool_call or "function" in tool_call):
                    tool_calls.append(ToolCallParser._normalize_tool_call(tool_call))
        
        # Validate all extracted tool calls
        valid_tool_calls = []
        for tc in tool_calls:
            if ToolCallParser._validate_tool_call(tc):
                valid_tool_calls.append(tc)
                
        return valid_tool_calls if valid_tool_calls else None

    @staticmethod
    def _extract_potential_json_objects(text: str) -> List[str]:
        """Extract all potential JSON objects from text using bracket matching."""
        results = []
        depth = 0
        start = -1
        
        for i, char in enumerate(text):
            if char == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0 and start != -1:
                    json_str = text[start:i+1]
                    results.append(json_str.strip())
                    start = -1
                        
        return results

    @staticmethod
    def _fix_incomplete_json(text: str) -> Optional[str]:
        """Try to fix incomplete JSON by adding missing closing brackets."""
        text = text.strip()
        if not text.startswith("{"):
            text = "{" + text
            
        # Count brackets
        open_brackets = text.count("{")
        close_brackets = text.count("}")
        
        if open_brackets > close_brackets:
            # Add missing closing brackets
            text += "}" * (open_brackets - close_brackets)
            
        return text

    @staticmethod
    def _try_parse_json(json_str: str) -> Optional[dict]:
        """Try to parse JSON, return None if fails."""
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Try with some common fixes
            # Remove trailing commas
            json_str = re.sub(r",\s*([\]}])", r"\1", json_str)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                return None

    @staticmethod
    def _normalize_tool_call(data: dict) -> dict:
        """Normalize different tool call formats to the standard format."""
        normalized = {
            "id": ToolCallParser.generate_tool_call_id(),
            "type": "function",
        }
        
        if "name" in data:
            normalized["function"] = {
                "name": data["name"],
                "arguments": data.get("arguments") or data.get("parameters") or {}
            }
        elif "function" in data:
            if isinstance(data["function"], dict):
                normalized["function"] = data["function"]
                if "name" not in normalized["function"] and "name" in data:
                    normalized["function"]["name"] = data["name"]
            else:
                normalized["function"] = {
                    "name": data["function"],
                    "arguments": data.get("arguments") or {}
                }
        elif "tool_name" in data:
            normalized["function"] = {
                "name": data["tool_name"],
                "arguments": data.get("parameters") or data.get("arguments") or {}
            }
            
        return normalized

    @staticmethod
    def _validate_tool_call(tool_call: dict) -> bool:
        """Validate that tool call has all required fields."""
        if not isinstance(tool_call, dict):
            return False
        if "function" not in tool_call:
            return False
        func = tool_call["function"]
        if not isinstance(func, dict):
            return False
        if "name" not in func:
            return False
        if "arguments" not in func:
            return False
        if not isinstance(func["arguments"], (dict, str)):
            return False
        return True

    @staticmethod
    def parse_arguments(tool_call: Any) -> dict:
        """解析 tool_call 中的 arguments（JSON 字符串 -> dict）"""
        if isinstance(tool_call, dict):
            arguments_str = tool_call.get("function", {}).get("arguments", "{}")
        else:
            # Handle function object from OpenAI SDK
            if hasattr(tool_call, "function") and hasattr(
                tool_call.function, "arguments"
            ):
                arguments_str = tool_call.function.arguments
            else:
                arguments_str = "{}"

        if isinstance(arguments_str, str):
            return json.loads(arguments_str)
        return arguments_str

    @staticmethod
    def generate_tool_call_id() -> str:
        """生成唯一的 tool_call_id"""
        return f"call_{uuid.uuid4().hex}"

    @staticmethod
    def create_tool_response(tool_call_id: str, content: Any) -> dict:
        """创建工具执行结果消息

        Args:
            tool_call_id: 匹配的 tool_call ID
            content: 工具执行结果（会自动序列化为 JSON）

        Returns:
            {"role": "tool", "tool_call_id": "...", "content": "..."}
        """
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        }

    @staticmethod
    def has_tool_calls(response_message: Any) -> bool:
        """检查响应是否包含 tool_calls"""
        tool_calls = ToolCallParser.parse_tool_calls(response_message)
        return tool_calls is not None and len(tool_calls) > 0
