import json
from typing import Any
import uuid


class ToolCallParser:
    """tool_call响应解析"""

    @staticmethod
    def parse_tool_calls(response_message: Any) -> list[dict] | None:
        """从模型响应中提取 tool_calls"""
        if isinstance(response_message, dict):
            return response_message.get("tool_calls")
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
        return None

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
